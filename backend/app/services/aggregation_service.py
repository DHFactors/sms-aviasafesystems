from typing import Dict, Any, List, Optional
from collections import Counter
import io

from loguru import logger

from app.db import pg
from app.db.db_models import Hazard, Survey, Tenant
from app.db.isolation import demo_scope
from app.db.ids import tenant_uuid


class AggregationService:
    """Industry aggregation for regulator dashboard.

    Reads straight from Postgres (hazards + survey maturity per tenant),
    anonymized, min 3 tenants. The optional `repository` argument is accepted
    for backward compatibility but is no longer used for reads.
    """

    def __init__(self, repository: Optional[Any] = None):
        self.repository = repository

    async def _get_tenant_ids(self, tenant_ids: Optional[List[str]] = None) -> List[str]:
        if tenant_ids:
            return tenant_ids
        # Discover via tenants table if available, else return empty
        try:
            tenants = pg.fetch_all(Tenant, limit=100)
            slugs = [t.get("slug") or t.get("tenant_id") or t.get("id") for t in tenants]
            return [s for s in slugs if s]
        except Exception:
            return []

    def _latest_maturity(self, tid: str) -> Optional[Dict[str, Any]]:
        """Latest survey maturity for a tenant, mapped to the Firestore-era
        maturity-assessment shape the aggregation code reads."""
        try:
            uid = tenant_uuid(tid)
        except Exception:
            uid = None
        if uid is None:
            return None
        rows = pg.fetch_all(
            Survey,
            where=[Survey.tenant_id == uid, Survey.is_demo == demo_scope()],
            order_by=Survey.submitted_at.desc(),
            limit=1,
        )
        if not rows:
            return None
        d = rows[0]
        overall = d.get("overall_sms_maturity")
        level = int(overall) if overall is not None else None
        return {
            "overall_maturity": overall,
            "component_scores": {
                "component_1": d.get("safety_policy"),
                "component_2": d.get("safety_risk_management"),
                "component_3": d.get("safety_assurance"),
                "component_4": d.get("safety_promotion"),
            },
            "level": level,
            "level_name": f"Level {level}" if level is not None else None,
            "created_at": d.get("submitted_at"),
        }

    def _hazards(self, tid: str) -> List[Dict[str, Any]]:
        """Hazards for a tenant mapped to the Firestore-era hazard shape the
        aggregation code reads (created_at as ISO string for [:10] slicing)."""
        try:
            uid = tenant_uuid(tid)
        except Exception:
            uid = None
        if uid is None:
            return []
        rows = pg.fetch_all(
            Hazard,
            where=[Hazard.tenant_id == uid, Hazard.is_demo == demo_scope()],
            order_by=Hazard.created_at.desc(),
            limit=100,
        )
        docs = []
        for d in rows:
            created = d.get("created_at")
            docs.append({
                "adrep_code": d.get("adrep_category"),
                "hfacs_code": None,
                "category": d.get("adrep_category") or d.get("taxonomy") or d.get("occurrence_type"),
                "title": d.get("title") or "",
                "risk_level": d.get("risk_level"),
                "initial_risk_level": d.get("risk_level"),
                "initial_risk_level_value": d.get("risk_index"),
                "created_at": created.isoformat() if created is not None else "",
            })
        return docs

    async def collect_maturity_scores(self, tenant_ids: List[str]) -> List[Dict[str, Any]]:
        """Collect latest maturity assessment per tenant, anonymized."""
        anonymized = []
        for idx, tid in enumerate(tenant_ids, 1):
            try:
                latest = self._latest_maturity(tid)
                if not latest:
                    continue
                # Anonymize: remove tenant_id, name
                anon = {
                    "anonymized_id": f"Operator-{idx}",
                    "overall_maturity": latest.get("overall_maturity"),
                    "component_scores": latest.get("component_scores", {}),
                    "level": latest.get("level"),
                    "level_name": latest.get("level_name"),
                    "created_at": latest.get("created_at"),
                }
                anonymized.append(anon)
            except Exception as e:
                logger.warning(f"Failed to collect maturity for {tid}: {e}")
        return anonymized

    async def calculate_industry_averages(self, tenant_ids: List[str]) -> Dict[str, Any]:
        if len(tenant_ids) < 3:
            return {"error": "Insufficient data: minimum 3 tenants required", "count": len(tenant_ids)}
        scores = await self.collect_maturity_scores(tenant_ids)
        if not scores:
            return {"error": "No maturity data", "count": 0}
        # Average overall
        avg_overall = round(sum(s["overall_maturity"] for s in scores) / len(scores), 1)
        # Average component scores
        comp_avgs = {}
        for comp in ["component_1", "component_2", "component_3", "component_4"]:
            vals = [s["component_scores"].get(comp, 0) for s in scores if comp in s["component_scores"]]
            comp_avgs[comp] = round(sum(vals) / len(vals), 1) if vals else 0
        # Distribution of levels
        level_counts = Counter(s["level"] for s in scores)
        distribution = {f"Level {lvl}": level_counts.get(lvl, 0) for lvl in range(1, 6)}
        return {
            "tenant_count": len(scores),
            "average_overall": avg_overall,
            "average_components": comp_avgs,
            "level_distribution": distribution,
            "anonymized_scores": scores,  # for heat map
        }

    async def get_top_hazards(self, tenant_ids: List[str], top_n: int = 5) -> Dict[str, Any]:
        if len(tenant_ids) < 3:
            return {"error": "Insufficient data", "count": len(tenant_ids)}
        # Aggregate hazard categories across tenants
        all_categories = []
        for tid in tenant_ids:
            try:
                hazards = self._hazards(tid)
                for h in hazards:
                    cat = h.get("adrep_code") or h.get("hfacs_code") or h.get("category") or "Unknown"
                    all_categories.append(cat)
            except Exception as e:
                logger.warning(f"Hazard aggregate failed for {tid}: {e}")
        counter = Counter(all_categories)
        top = counter.most_common(top_n)
        # Trend over time: group by month (simplified)
        return {
            "top_categories": [{"category": cat, "count": cnt} for cat, cnt in top],
            "total_hazards": len(all_categories),
            "trend": [{"period": "Last 90d", "count": len(all_categories)}],  # placeholder
        }

    async def get_risk_trends(self, tenant_ids: List[str]) -> Dict[str, Any]:
        if len(tenant_ids) < 3:
            return {"error": "Insufficient data", "count": len(tenant_ids)}
        # Collect risk levels over time (simplified: average risk per tenant)
        trends = []
        for tid in tenant_ids:
            try:
                hazards = self._hazards(tid)
                for h in hazards:
                    trends.append({
                        "date": h.get("created_at", "")[:10],
                        "risk_level": h.get("initial_risk_level") or h.get("risk_level") or "Low",
                    })
            except Exception as e:
                logger.warning(f"Risk trend failed for {tid}: {e}")
        # Aggregate by risk_level
        by_level = Counter(t["risk_level"] for t in trends)
        return {
            "total_points": len(trends),
            "by_risk_level": dict(by_level),
            "trend_over_time": trends[:20],  # sample
        }

    async def get_state_risk_register(self, tenant_ids: List[str]) -> Dict[str, Any]:
        if len(tenant_ids) < 3:
            return {"error": "Insufficient data", "count": len(tenant_ids)}
        # Aggregate top risks (high risk hazards) anonymized
        risks = []
        for tid in tenant_ids:
            try:
                hazards = self._hazards(tid)
                for h in hazards:
                    if h.get("initial_risk_level") in ("High", "Very High"):
                        risks.append({
                            "anonymized_id": f"Operator-{tenant_ids.index(tid)+1}",
                            "title": h.get("title", "")[:50],
                            "risk_level": h.get("initial_risk_level"),
                            "risk_value": h.get("initial_risk_level_value"),
                            "category": h.get("adrep_code") or "Unknown",
                        })
            except Exception as e:
                logger.warning(f"State risk failed for {tid}: {e}")
        # Sort by risk_value desc
        risks.sort(key=lambda x: x.get("risk_value", 0), reverse=True)
        return {"top_risks": risks[:10], "total_high_risks": len(risks)}

    async def get_benchmarking(self, tenant_id: str, tenant_ids: List[str]) -> Dict[str, Any]:
        if len(tenant_ids) < 3:
            return {"error": "Insufficient data", "count": len(tenant_ids)}
        # Industry average
        industry = await self.calculate_industry_averages(tenant_ids)
        if "error" in industry:
            return industry
        # Operator's own latest
        try:
            own = self._latest_maturity(tenant_id)
            own_score = own.get("overall_maturity") if own else None
        except Exception:
            own_score = None
        return {
            "tenant_id": tenant_id,  # for internal use, but anonymized in display
            "operator_score": own_score,
            "industry_average": industry["average_overall"],
            "difference": round(own_score - industry["average_overall"], 1) if own_score is not None else None,
            "industry_distribution": industry["level_distribution"],
            "anonymized": True,
        }

    # Export functions
    def export_pdf_data(self, aggregation: Dict[str, Any]) -> bytes:
        """Generate PDF bytes for regulator report (simple text-based)."""
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=letter)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, 750, "Regulator Dashboard - Industry Report")
            c.setFont("Helvetica", 10)
            y = 730
            for key, value in aggregation.items():
                if key in ("anonymized_scores", "trend_over_time", "top_risks"):
                    continue
                line = f"{key}: {value}"
                c.drawString(50, y, line[:100])
                y -= 15
                if y < 50:
                    c.showPage()
                    y = 750
            c.save()
            return buffer.getvalue()
        except ImportError:
            # Fallback: simple text
            text = f"Regulator Report\n{aggregation}\n"
            return text.encode()

    def export_excel_data(self, aggregation: Dict[str, Any]) -> bytes:
        """Generate Excel bytes for data extraction."""
        try:
            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            ws.title = "Industry Aggregation"
            ws.append(["Metric", "Value"])
            for key, value in aggregation.items():
                if isinstance(value, (dict, list)):
                    value = str(value)[:32767]
                ws.append([key, value])
            buffer = io.BytesIO()
            wb.save(buffer)
            return buffer.getvalue()
        except ImportError:
            # Fallback CSV
            import csv
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["Metric", "Value"])
            for k, v in aggregation.items():
                writer.writerow([k, str(v)[:30000]])
            return buffer.getvalue().encode()
