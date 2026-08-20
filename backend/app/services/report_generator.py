from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from collections import Counter
from loguru import logger

from app.core.config import settings
from app.firebase import get_tenant_collection, get_cross_tenant_collection
from app.services.risk_matrix import normalize_tolerability


HAZARD_COLLECTION = "hazards"
CAN_COLLECTION = "can_cap"
CAP_SUBCOLLECTION = "caps"

TIER_TO_LEVEL = {"LOW": "Low", "HIGH": "High", "VERY HIGH": "Very High"}


class ReportGenerator:
    def __init__(self, tenant_id: Optional[str] = None):
        self.tenant_id = tenant_id

    def _get_hazards(self, user: dict) -> List[dict]:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES and not self.tenant_id:
                docs = get_cross_tenant_collection(HAZARD_COLLECTION).get()
            else:
                docs = get_tenant_collection(self.tenant_id, HAZARD_COLLECTION).get()
            results = []
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                self._serialize_timestamps(data)
                results.append(data)
            return results
        except Exception as e:
            logger.error(f"Failed to fetch hazards: {e}")
            return []

    def _get_cans(self, user: dict) -> List[dict]:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES and not self.tenant_id:
                docs = get_cross_tenant_collection(CAN_COLLECTION).get()
            else:
                docs = get_tenant_collection(self.tenant_id, CAN_COLLECTION).get()
            results = []
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                caps = list(doc.reference.collection(CAP_SUBCOLLECTION).get())
                data["caps"] = []
                for cap in caps:
                    cd = cap.to_dict()
                    cd["id"] = cap.id
                    self._serialize_timestamps(cd)
                    data["caps"].append(cd)
                self._serialize_timestamps(data)
                results.append(data)
            return results
        except Exception as e:
            logger.error(f"Failed to fetch CANs: {e}")
            return []

    def generate_quarterly_report(self, year: int, quarter: int, user: dict) -> dict:
        start_month = (quarter - 1) * 3 + 1
        end_month = quarter * 3

        hazards = self._get_hazards(user)
        cans = self._get_cans(user)

        filtered_hazards = [
            h for h in hazards
            if self._in_period(h.get("created_at"), year, start_month, end_month) or
               self._in_period(h.get("closed_at"), year, start_month, end_month)
        ]

        total = len(hazards)
        new_hazards = len([h for h in hazards if self._in_period(h.get("created_at"), year, start_month, end_month)])
        closed_hazards = len([h for h in hazards if h.get("status") == "Closed" and self._in_period(h.get("closed_at"), year, start_month, end_month)])
        open_hazards = len([h for h in hazards if h.get("status") not in ("Closed",)])

        risk_dist = {"Low": 0, "High": 0, "Very High": 0}
        for h in hazards:
            tier = normalize_tolerability(h.get("risk_level"))
            risk_dist[TIER_TO_LEVEL[tier]] += 1

        top_risks = self._calculate_top_risks(hazards)
        can_cap_status = self._calculate_can_cap_status(cans)
        hazard_trends = self._calculate_hazard_trends(hazards, year)
        risk_trends = self._calculate_risk_trends(hazards, year)
        insights = self._generate_insights(risk_dist, can_cap_status, top_risks)
        ssp_indicators = self._calculate_ssp_indicators(hazards, cans, year)

        summary = {
            "total_hazards": total,
            "new_hazards": new_hazards,
            "closed_hazards": closed_hazards,
            "open_hazards": open_hazards,
            "hazards_in_period": len(filtered_hazards),
            "closure_rate": round((closed_hazards / total * 100) if total > 0 else 0, 1),
        }

        return {
            "period": f"Q{quarter} {year}",
            "year": year,
            "quarter": quarter,
            "report_type": "quarterly",
            "summary": summary,
            "data": {
                "risk_distribution": risk_dist,
                "risk_levels": self._format_risk_levels(risk_dist),
                "top_risks": top_risks,
                "can_cap_status": can_cap_status,
                "hazard_trends": hazard_trends,
                "risk_trends": risk_trends,
                "insights": insights,
                "ssp_indicators": ssp_indicators,
            },
        }

    def generate_annual_report(self, year: int, user: dict) -> dict:
        hazards = self._get_hazards(user)
        cans = self._get_cans(user)

        total = len(hazards)
        opened = len([h for h in hazards if self._in_year(h.get("created_at"), year)])
        closed = len([h for h in hazards if h.get("status") == "Closed" and self._in_year(h.get("closed_at"), year)])

        risk_dist = {"Low": 0, "High": 0, "Very High": 0}
        for h in hazards:
            tier = normalize_tolerability(h.get("risk_level"))
            risk_dist[TIER_TO_LEVEL[tier]] += 1

        hazard_trends = self._calculate_hazard_trends(hazards, year)
        risk_trends = self._calculate_risk_trends(hazards, year)
        can_cap_summary = self._calculate_can_cap_summary(cans)
        avg_closure = self._calculate_avg_closure_time(cans)
        ssp_indicators = self._calculate_ssp_indicators(hazards, cans, year)
        strategic_recs = self._generate_strategic_recommendations(risk_dist, ssp_indicators)
        operational_recs = self._generate_operational_recommendations(cans)

        summary = {
            "total_hazards": total,
            "hazards_opened": opened,
            "hazards_closed": closed,
            "closure_rate": round((closed / total * 100) if total > 0 else 0, 1),
            "can_cap_total": can_cap_summary.get("total", 0),
            "can_cap_closure_rate": can_cap_summary.get("compliance_rate", 0),
            "avg_closure_days": avg_closure,
        }

        monthly_hazard = [{"month": m, "count": 0} for m in self._month_labels()]
        for ht in hazard_trends:
            for m in monthly_hazard:
                if m["month"] == ht["month"]:
                    m["count"] = ht["count"]
                    break

        return {
            "period": str(year),
            "year": year,
            "quarter": None,
            "report_type": "annual",
            "summary": summary,
            "data": {
                "risk_distribution": risk_dist,
                "risk_levels": self._format_risk_levels(risk_dist),
                "hazard_trends": monthly_hazard,
                "risk_trends": risk_trends,
                "can_cap_summary": can_cap_summary,
                "avg_can_cap_closure_time": avg_closure,
                "ssp_indicators": ssp_indicators,
                "strategic_recommendations": strategic_recs,
                "operational_recommendations": operational_recs,
            },
        }

    def _in_period(self, dt, year: int, start_month: int, end_month: int) -> bool:
        if not dt:
            return False
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except (ValueError, TypeError):
                return False
        return dt.year == year and start_month <= dt.month <= end_month

    def _in_year(self, dt, year: int) -> bool:
        if not dt:
            return False
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except (ValueError, TypeError):
                return False
        return dt.year == year

    def _calculate_top_risks(self, hazards: List[dict]) -> List[dict]:
        categories = []
        for h in hazards:
            cat = h.get("adrep_category") or h.get("taxonomy") or "Other"
            categories.append(cat)
        counts = Counter(categories)
        return [{"category": cat, "count": cnt} for cat, cnt in counts.most_common(10)]

    def _calculate_can_cap_status(self, cans: List[dict]) -> Dict[str, int]:
        statuses = {"Open": 0, "Under Review": 0, "Closed": 0}
        for c in cans:
            s = c.get("status", "Open")
            if s in statuses:
                statuses[s] += 1
        return statuses

    def _calculate_can_cap_summary(self, cans: List[dict]) -> Dict[str, Any]:
        total = len(cans)
        closed = len([c for c in cans if c.get("status") == "Closed"])
        open_caps = sum(len(c.get("caps", [])) for c in cans if c.get("status") != "Closed")
        return {
            "total": total,
            "closed": closed,
            "open": total - closed,
            "open_caps": open_caps,
            "compliance_rate": round((closed / total * 100) if total > 0 else 0, 1),
        }

    def _calculate_avg_closure_time(self, cans: List[dict]) -> int:
        days_list = []
        for c in cans:
            created = c.get("created_at")
            for cap in c.get("caps", []):
                if cap.get("status") == "Completed" and cap.get("reviewed_at") and cap.get("created_at"):
                    try:
                        diff = (cap["reviewed_at"] - cap["created_at"]).days
                        days_list.append(diff)
                    except (TypeError, AttributeError):
                        pass
            if c.get("status") == "Closed" and created:
                updated = c.get("updated_at")
                if updated:
                    try:
                        diff = (updated - created).days
                        days_list.append(diff)
                    except (TypeError, AttributeError):
                        pass
        if not days_list:
            return 0
        return round(sum(days_list) / len(days_list))

    def _calculate_hazard_trends(self, hazards: List[dict], year: int) -> List[dict]:
        trends = []
        for m in range(1, 13):
            count = len([
                h for h in hazards
                if self._in_period(h.get("created_at"), year, m, m)
            ])
            trends.append({"month": f"{year}-{m:02d}", "count": count})
        return trends

    def _calculate_risk_trends(self, hazards: List[dict], year: int) -> List[dict]:
        trends = []
        for m in range(1, 13):
            month_hazards = [
                h for h in hazards
                if self._in_period(h.get("created_at"), year, m, m)
            ]
            levels = {"Low": 0, "High": 0, "Very High": 0}
            for h in month_hazards:
                tier = normalize_tolerability(h.get("risk_level"))
                levels[TIER_TO_LEVEL[tier]] += 1
            trends.append({
                "month": f"{year}-{m:02d}",
                "levels": levels,
            })
        return trends

    def _calculate_ssp_indicators(self, hazards: List[dict], cans: List[dict], year: int) -> Dict[str, Any]:
        total = len(hazards)
        vsr_count = len([h for h in hazards if h.get("source") == "VSR"])
        closed = len([h for h in hazards if h.get("status") == "Closed"])
        can_closed = len([c for c in cans if c.get("status") == "Closed"])
        can_total = len(cans)

        # Pull the persisted state-level register so risk_reduction_rate and
        # SSP target/actual comparison reflect the state (aggregated) view
        # instead of a hardcoded placeholder.
        state_metrics = {}
        try:
            from app.services.state_risk_service import StateRiskService
            from app.services.state_risk_service import _risk_collection
            rows = list(_risk_collection().stream())
            if rows:
                latest = max(rows, key=lambda r: (r.to_dict().get("year", 0), r.to_dict().get("quarter", 0)))
                d = latest.to_dict()
                reduction = d.get("risk_reduction_rate")
                state_metrics = {
                    "risk_reduction_rate": round(float(reduction), 1) if reduction is not None else 0.0,
                    "ssp_target_avg": self._avg_ssp_target(rows),
                    "ssp_actual_avg": self._avg_ssp_actual(rows),
                    "state_categories_tracked": len(rows),
                }
        except Exception as e:
            logger.warning(f"Failed to read state risk register for SSP indicators: {e}")
            state_metrics = {}

        return {
            "hazard_identification_rate": round((vsr_count / total * 100) if total > 0 else 0, 1),
            "closure_rate": round((closed / total * 100) if total > 0 else 0, 1),
            "can_cap_compliance_rate": round((can_closed / can_total * 100) if can_total > 0 else 0, 1),
            "risk_reduction_rate": state_metrics.get("risk_reduction_rate", 0.0),
            "ssp_target_avg": state_metrics.get("ssp_target_avg"),
            "ssp_actual_avg": state_metrics.get("ssp_actual_avg"),
            "state_categories_tracked": state_metrics.get("state_categories_tracked"),
        }

    @staticmethod
    def _avg_ssp_target(rows) -> Optional[float]:
        vals = [r.to_dict().get("ssp_target") for r in rows if r.to_dict().get("ssp_target") is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    @staticmethod
    def _avg_ssp_actual(rows) -> Optional[float]:
        vals = [r.to_dict().get("actual_ssp_value") for r in rows if r.to_dict().get("actual_ssp_value") is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    def _generate_insights(self, risk_dist: dict, can_cap_status: dict, top_risks: list) -> List[str]:
        insights = []
        high_very_high = risk_dist.get("High", 0) + risk_dist.get("Very High", 0)
        if high_very_high > 0:
            insights.append(f"{high_very_high} high/very-high risk hazards detected. Review mitigation effectiveness.")
        if can_cap_status.get("Open", 0) > 5:
            insights.append(f"CAN backlog: {can_cap_status['Open']} open actions. Prioritize review.")
        if top_risks and top_risks[0]["count"] > 3:
            insights.append(f"Top risk category: {top_risks[0]['category']} ({top_risks[0]['count']} occurrences). Focus resources.")
        if not insights:
            insights.append("Period shows stable safety performance.")
        return insights

    def _generate_strategic_recommendations(self, risk_dist: dict, ssp: dict) -> List[str]:
        recs = []
        if ssp.get("closure_rate", 100) < 80:
            recs.append("Improve hazard closure rate — target >80% within next year.")
        if risk_dist.get("High", 0) + risk_dist.get("Very High", 0) > 10:
            recs.append("Conduct comprehensive risk review for high-risk categories.")
        if ssp.get("can_cap_compliance_rate", 100) < 70:
            recs.append("Strengthen CAN/CAP compliance monitoring and escalation.")
        if not recs:
            recs.append("Maintain current SMS performance levels.")
        return recs

    def _generate_operational_recommendations(self, cans: List[dict]) -> List[str]:
        recs = []
        open_cans = len([c for c in cans if c.get("status") == "Open"])
        if open_cans > 10:
            recs.append(f"Prioritize closure of {open_cans} open CANs.")
        else:
            recs.append("Continue timely processing of corrective actions.")
        return recs

    @staticmethod
    def _format_risk_levels(dist: dict) -> list:
        colors = {"Low": "#34a853", "High": "#f57c00", "Very High": "#ea4335"}
        return [
            {"label": k, "value": v, "color": colors.get(k, "#ccc")}
            for k, v in dist.items()
        ]

    @staticmethod
    def _month_labels() -> list:
        return [f"{m:02d}" for m in range(1, 13)]

    @staticmethod
    def _serialize_timestamps(data: dict) -> None:
        for key in ("created_at", "updated_at", "closed_at", "issued_at",
                     "submitted_at", "reviewed_at", "approved_at"):
            if key in data and hasattr(data[key], "isoformat"):
                data[key] = data[key].isoformat()
