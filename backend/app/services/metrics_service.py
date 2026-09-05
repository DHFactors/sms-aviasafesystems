# ============================================================================
# FILE: metrics_service.py
# PATH: backend/app/services/metrics_service.py
# VERSION: 1.0.0
# DATE CREATED: 2026-07-27
# PURPOSE: Pure calculation functions for dashboard analytics.
#          No Firestore calls — operates on data passed in.
# AUTHOR: Ghanshyam Acharya
# CODE OWNER: AviaSafeSystems
# ============================================================================

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from collections import Counter, defaultdict


class MetricsService:
    """Stateless calculation service.

    Every method takes plain dicts (from the repository) and returns
    computed results. No I/O, no side effects, easily testable.
    """

    @staticmethod
    def calculate_kpis(reports: List[dict]) -> Dict[str, Any]:
        total = len(reports)
        if total == 0:
            return {
                "total_reports": 0,
                "open_reports": 0,
                "closed_reports": 0,
                "high_risk_reports": 0,
                "critical_reports": 0,
                "anonymous_percentage": 0.0,
                "avg_closure_days": None,
                "reporting_rate_trend": None,
                "repeat_occurrence_rate": None,
            }

        open_count = sum(
            1 for r in reports if r.get("status") in ("NEW", "PROCESSING")
        )
        closed_count = sum(
            1 for r in reports if r.get("status") in ("COMPLETED", "SUBMITTED", "ARCHIVED")
        )
        high_risk = sum(1 for r in reports if r.get("severity") == "High")
        critical = sum(1 for r in reports if r.get("severity") == "Critical")
        anonymous = sum(1 for r in reports if r.get("is_anonymous"))
        anon_pct = round((anonymous / total * 100), 1) if total else 0.0

        closure_times = []
        for r in reports:
            created = r.get("created_at")
            updated = r.get("updated_at")
            status = r.get("status")
            if created and updated and status in ("COMPLETED", "SUBMITTED", "ARCHIVED"):
                if isinstance(created, str):
                    created = datetime.fromisoformat(created)
                if isinstance(updated, str):
                    updated = datetime.fromisoformat(updated)
                days = (updated - created).total_seconds() / 86400
                if days >= 0:
                    closure_times.append(days)

        avg_closure = round(sum(closure_times) / len(closure_times), 1) if closure_times else None

        type_counts = Counter(r.get("occurrence_type") for r in reports if r.get("occurrence_type"))
        total_with_type = sum(type_counts.values())
        repeat_rate = None
        if total_with_type > 0:
            repeats = sum(c for c in type_counts.values() if c > 1)
            repeat_rate = round(repeats / total_with_type * 100, 1)

        return {
            "total_reports": total,
            "open_reports": open_count,
            "closed_reports": closed_count,
            "high_risk_reports": high_risk,
            "critical_reports": critical,
            "anonymous_percentage": anon_pct,
            "avg_closure_days": avg_closure,
            "reporting_rate_trend": None,
            "repeat_occurrence_rate": repeat_rate,
        }

    @staticmethod
    def calculate_risk_distribution(reports: List[dict]) -> List[Dict[str, Any]]:
        total = len(reports) or 1
        counts = Counter(r.get("severity", "Unspecified") for r in reports)
        levels = ["Critical", "High", "Medium", "Low", "Unspecified"]
        return [
            {
                "risk_level": level,
                "count": counts.get(level, 0),
                "percentage": round(counts.get(level, 0) / total * 100, 1),
                "forecast": None,
            }
            for level in levels
        ]

    @staticmethod
    def calculate_monthly_trends(reports: List[dict]) -> List[Dict[str, Any]]:
        monthly: Dict[str, Dict] = defaultdict(
            lambda: {"total": 0, "voluntary": 0, "mandatory": 0, "high_risk": 0, "prediction": None}
        )
        for r in reports:
            raw = r.get("occurrence_date") or r.get("created_at")
            if not raw:
                continue
            if isinstance(raw, str):
                raw = datetime.fromisoformat(raw)
            key = f"{raw.year}-{raw.month:02d}"
            m = monthly[key]
            m["total"] += 1
            rtype = r.get("report_type")
            if rtype == "voluntary":
                m["voluntary"] += 1
            elif rtype == "mandatory":
                m["mandatory"] += 1
            if r.get("severity") == "High":
                m["high_risk"] += 1

        sorted_keys = sorted(monthly.keys())
        return [
            {
                "month": k.split("-")[1],
                "year": int(k.split("-")[0]),
                **monthly[k],
            }
            for k in sorted_keys
        ]

    @staticmethod
    def calculate_hazard_frequency(reports: List[dict]) -> List[Dict[str, Any]]:
        total = len(reports) or 1
        counts = Counter(
            r.get("occurrence_type", "Unspecified") for r in reports
        )
        sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [
            {
                "occurrence_type": otype,
                "count": count,
                "percentage": round(count / total * 100, 1),
                "trend_direction": None,
            }
            for otype, count in sorted_items
        ]

    @staticmethod
    def calculate_top_occurrence_types(
        reports: List[dict], top_n: int = 10
    ) -> List[Dict[str, Any]]:
        total = len(reports) or 1
        counts = Counter(
            r.get("occurrence_type", "Unspecified") for r in reports if r.get("occurrence_type")
        )
        top = counts.most_common(top_n)
        return [
            {
                "occurrence_type": otype,
                "count": count,
                "percentage": round(count / total * 100, 1),
            }
            for otype, count in top
        ]

    @staticmethod
    def calculate_closure_rate(reports: List[dict]) -> float:
        total = len(reports) or 1
        closed = sum(1 for r in reports if r.get("status") in ("COMPLETED", "SUBMITTED", "ARCHIVED"))
        return round(closed / total * 100, 1)

    @staticmethod
    def calculate_average_risk_score(reports: List[dict]) -> Optional[float]:
        scores = [
            r["risk_score"] for r in reports
            if r.get("risk_score") is not None
        ]
        if not scores:
            return None
        return round(sum(scores) / len(scores), 2)

    @staticmethod
    def calculate_ai_kpis(reports: List[dict]) -> Dict[str, Any]:
        total = len(reports)
        if total == 0:
            return {
                "ai_processed": 0, "ai_pending": 0, "ai_failed": 0,
                "avg_processing_time_ms": None, "avg_confidence": None,
                "model_versions": {},
            }

        processed = sum(1 for r in reports if r.get("ai_status") == "COMPLETED")
        pending = sum(1 for r in reports if r.get("ai_status") == "PENDING")
        failed = sum(1 for r in reports if r.get("ai_status") == "FAILED")

        processing_times = []
        confidences = []
        model_versions: Dict[str, int] = {}
        for r in reports:
            ai = r.get("ai_analysis") or {}
            pt = ai.get("processing_time_ms")
            if pt is not None:
                processing_times.append(pt)
            conf = ai.get("confidence")
            if conf is not None:
                confidences.append(conf)
            model = ai.get("ai_model")
            if model:
                model_versions[model] = model_versions.get(model, 0) + 1

        avg_time = round(sum(processing_times) / len(processing_times), 1) if processing_times else None
        avg_conf = round(sum(confidences) / len(confidences), 3) if confidences else None

        return {
            "ai_processed": processed,
            "ai_pending": pending,
            "ai_failed": failed,
            "avg_processing_time_ms": avg_time,
            "avg_confidence": avg_conf,
            "model_versions": model_versions,
        }

    @staticmethod
    def calculate_org_kpis(reports: List[dict]) -> Dict[str, Any]:
        reporters = set(r.get("created_by") for r in reports if r.get("created_by"))
        actions_open = sum(
            1 for r in reports
            for ca in (r.get("corrective_actions") or [])
            if isinstance(ca, dict) and ca.get("status") == "OPEN"
        )
        actions_closed = sum(
            1 for r in reports
            for ca in (r.get("corrective_actions") or [])
            if isinstance(ca, dict) and ca.get("status") == "CLOSED"
        )
        investigations = sum(
            1 for r in reports
            if r.get("investigation_status") in ("NOT_INVESTIGATED", "INVESTIGATING")
        )

        return {
            "active_reporters": len(reporters),
            "reporting_frequency": None,
            "corrective_actions_open": actions_open,
            "corrective_actions_closed": actions_closed,
            "safety_actions_overdue": 0,
            "investigation_backlog": investigations,
        }

    # ICAO ADREP occurrence categories → SMS taxonomy (mirrors CAAN dashboard
    # mapping and the seed ICAO_TO_TAXONOMY table). Values are the ICAO-aligned
    # 4-value set: Organizational, Technical, Human, Environmental.
    ICAO_TO_TAXONOMY = {
        "LOCI": "Organizational",
        "CFIT": "Organizational",
        "RE": "Organizational",
        "RI": "Organizational",
        "GCOL": "Organizational",
        "MAC": "Technical",
        "ENG": "Technical",
        "SYS": "Technical",
        "FIRE": "Technical",
        "BIRD": "Environmental",
        "CABIN": "Human",
        "ARC": "Organizational",
        "PRO": "Organizational",
        "WX": "Environmental",
        "OTHER": "Organizational",
    }

    @staticmethod
    def _ssp_category(report: dict) -> str:
        """Map a report to one of the five SSP risk categories used by the
        CAAN and operator risk-trend charts.
        """
        taxonomy = (
            report.get("taxonomy")
            or MetricsService.ICAO_TO_TAXONOMY.get(
                (report.get("occurrence_category") or "").upper(), "Organizational"
            )
            or "Organizational"
        )
        if taxonomy == "Technical":
            return "Technical"
        if taxonomy in ("Environmental", "Wildlife"):
            return "External"
        if taxonomy in ("Human", "Human Factors"):
            return "Human Factors"
        if taxonomy.startswith("Organizational"):
            return "Organizational"
        return "Operational"

    @staticmethod
    def _report_quarter(report: dict) -> Optional[str]:
        raw = (
            report.get("created_at")
            or report.get("occurrence_date")
        )
        if not raw:
            return None
        try:
            if isinstance(raw, str):
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            else:
                dt = raw
            return f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"
        except Exception:
            return None

    @staticmethod
    def calculate_ssp_risk_trends(reports: List[dict]) -> Dict[str, Any]:
        """Quarterly average risk-index trend per SSP category (0-100 scale).

        Aggregates only aggregate-level data (category, quarter, average risk
        index) — never individual report content. Mirrors the CAAN dashboard's
        line chart so operators see the same SSM-aligned trend for their own
        tenant.
        """
        categories = ["Operational", "Technical", "Human Factors", "Organizational", "External"]
        quarters = set()
        cells: Dict[str, Dict[str, Any]] = {}

        for r in reports:
            quarter = MetricsService._report_quarter(r)
            if not quarter:
                continue
            quarters.add(quarter)
            cat = MetricsService._ssp_category(r)
            ri = r.get("risk_index")
            if ri is None:
                continue
            try:
                score = float(ri) * 4  # normalize 1-25 → 0-100
            except (TypeError, ValueError):
                continue
            key = f"{quarter}|{cat}"
            cell = cells.setdefault(key, {"sum": 0.0, "count": 0})
            cell["sum"] += score
            cell["count"] += 1

        sorted_quarters = sorted(quarters)
        series = []
        for cat in categories:
            series.append({
                "category": cat,
                "points": [
                    {
                        "quarter": q,
                        "label": q.replace("-Q", " Q"),
                        "avg_risk_index": (
                            round(cells[f"{q}|{cat}"]["sum"] / cells[f"{q}|{cat}"]["count"], 1)
                            if cells.get(f"{q}|{cat}") and cells[f"{q}|{cat}"]["count"]
                            else None
                        ),
                    }
                    for q in sorted_quarters
                ],
            })

        return {
            "categories": categories,
            "quarters": sorted_quarters,
            "labels": [q.replace("-Q", " Q") for q in sorted_quarters],
            "series": series,
        }
