# ============================================================================
# FILE: dashboard_service.py
# PATH: backend/app/services/dashboard_service.py
# VERSION: 1.0.0
# DATE CREATED: 2026-07-27
# PURPOSE: Role-aware dashboard orchestration layer.
#          Coordinates Repository and MetricsService.
# AUTHOR: Ghanshyam Acharya
# CODE OWNER: AviaSafeSystems
# ============================================================================

from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Dict, Any, List, Optional
from loguru import logger

from sqlalchemy import select

from app.core.config import settings
from app.db.db_models import Survey, SurveyResponse
from app.db.ids import register_tenant, tenant_slug
from app.db.isolation import demo_scope
from app.db.runner import run
from app.db.session import session_scope
from app.services.repository import ReportRepository, ReportFilter
from app.services.metrics_service import MetricsService
from app.services.gemini import recommend_sms_maturity_actions, sms_maturity_tier, SURVEY_PILLAR_NAMES
from app.services.risk_matrix import normalize_tolerability
from seed.config import FLIGHT_OPERATOR_TYPES

DIVERSION_COLLECTION = "flight_diversions"

SURVEY_PILLARS = ["safety_policy", "safety_risk_management", "safety_assurance", "safety_promotion"]
SMS_MATURITY_CACHE_TTL = 6 * 3600  # seconds

# Friendly labels for the SMS maturity tiers produced by the shared engine.
TIER_LABELS = {
    "strong": "Good",
    "watch": "Watch",
    "action": "Action Needed",
    "critical": "Critical",
}


class _PGSurveyDoc:
    """Lightweight Firestore-like wrapper around a Postgres Survey row.

    Presents the row as a document exposing ``to_dict()`` so the shared
    dashboard aggregation logic (_aggregate_surveys / _survey_history) is
    reused unchanged. Prevents the survey dashboards from depending on a
    Firestore collection write that the live API no longer performs.
    """

    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def to_dict(self) -> Dict[str, Any]:
        return self._data


def _survey_row_to_dict(row: Survey) -> Dict[str, Any]:
    """Map a Postgres Survey row to the dict shape the survey dashboards expect
    (identical keys to the legacy Firestore doc). `tenant_id` is the slug."""
    return {
        "tenant_id": tenant_slug(row.tenant_id),
        "submitted_at": row.submitted_at,
        "respondent_id": row.respondent_id,
        "answers": row.answers,
        "question_scores": row.question_scores or {},
        "element_scores": row.element_scores,
        "safety_policy": row.safety_policy,
        "safety_risk_management": row.safety_risk_management,
        "safety_assurance": row.safety_assurance,
        "safety_promotion": row.safety_promotion,
        "overall_sms_maturity": row.overall_sms_maturity,
        "survey_version": row.survey_version,
    }


class DashboardService:
    """Orchestrates dashboard data for all roles.

    Every public method:
      1. Determines the correct filter (tenant-isolated or cross-tenant)
      2. Queries the repository
      3. Delegates calculations to MetricsService
      4. Returns a dict ready for JSON response

    Route files import only this service — never the repository or metrics directly.
    """

    DEFAULT_DAYS = settings.DASHBOARD_DEFAULT_DAYS

    def __init__(self, user: dict):
        self.user = user
        self.role = user.get("role", "USER")
        self.tenant_id = user.get("tenant_id")
        self.repo = ReportRepository()

    # ------------------------------------------------------------------
    # Public: Airline dashboard endpoints
    # ------------------------------------------------------------------

    def get_airline_overview(self, **overrides) -> Dict[str, Any]:
        f = self._base_filter(**overrides)
        reports = self.repo.get_all_in_range(f)
        kpis = MetricsService.calculate_kpis(reports)
        ai_kpis = MetricsService.calculate_ai_kpis(reports)
        org_kpis = MetricsService.calculate_org_kpis(reports)
        return {
            "kpis": kpis,
            "ai_kpis": ai_kpis,
            "org_kpis": org_kpis,
        }

    def get_airline_sms_maturity(self, **overrides) -> Dict[str, Any]:
        """Tenant-scoped SMS maturity for the authenticated airline.

        Derives every value from the same core SMS maturity model used by the
        CAAN dashboard (_survey_docs + _aggregate_surveys + _sms_maturity_model +
        _tenant_recommendations); only the data scope differs — this tenant's
        surveys only (claims.tenant_id).
        """
        tenant_id = self.tenant_id
        days = overrides.get("days", 365)
        generated_at = datetime.now(timezone.utc)

        empty = {
            "tenant": tenant_id,
            "tenant_id": tenant_id,
            "overall_score": None,
            "tier": None,
            "tier_label": None,
            "pillars": {p: None for p in SURVEY_PILLARS},
            "assessment": {
                "strengths": [],
                "improvement_opportunities": [],
                "priority_actions": [],
            },
            "history": [],
            "latest_assessment_date": None,
            "response_count": 0,
            "period_days": days,
        }
        if not tenant_id:
            return empty

        docs = [
            d for d in self._survey_docs(days)
            if (d.to_dict().get("tenant_id") or None) == tenant_id
        ]
        data = self._aggregate_surveys(docs)
        ops = data.get("operators", [])
        op = ops[0] if ops else None
        empty["tenant"] = self._tenant_name(tenant_id)
        if not op:
            return empty

        model = self._sms_maturity_model(op)
        recs = self._tenant_recommendations(tenant_id, days, op, model, generated_at)

        latest = None
        for d in docs:
            ts = d.to_dict().get("submitted_at")
            if ts is None:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if latest is None or ts > latest:
                latest = ts

        return {
            "tenant": self._tenant_name(tenant_id),
            "tenant_id": tenant_id,
            "overall_score": model["overall_score"],
            "tier": model["tier"],
            "tier_label": model["tier_label"],
            "pillars": model["pcts"],
            "assessment": {
                "strengths": model["strengths"],
                "improvement_opportunities": model["improvement_opportunities"],
                "priority_actions": recs,
            },
            "history": self._survey_history(docs),
            "latest_assessment_date": latest.date().isoformat() if latest else None,
            "response_count": op["response_count"],
            "period_days": days,
        }

    def _sms_maturity_model(self, op: Dict[str, Any]) -> Dict[str, Any]:
        """Shared SMS maturity model derived from one aggregated operator row.

        This is the single source of the score math for both the Airline and
        CAAN dashboards: pillar percentages, tiers, strengths, and
        improvement opportunities are computed here and nowhere else.
        """
        pcts: Dict[str, float] = {}
        tiers: Dict[str, str] = {}
        low: List[Dict[str, Any]] = []
        for p in SURVEY_PILLARS:
            v = op["pillars"].get(p)
            if v is None:
                continue
            pct = round((v - 1) / 4 * 100, 1)
            pcts[p] = pct
            tiers[p] = sms_maturity_tier(pct)
            if pct < 70:
                low.append({"pillar": p, "score": v, "pct": pct, "tier": tiers[p]})

        overall_1_5 = op["overall_sms_maturity"]
        overall_pct = round((overall_1_5 - 1) / 4 * 100, 1) if overall_1_5 is not None else None
        overall_tier = sms_maturity_tier(overall_pct) if overall_pct is not None else None

        return {
            "pcts": pcts,
            "tiers": tiers,
            "overall_score": overall_pct,
            "tier": overall_tier,
            "tier_label": TIER_LABELS.get(overall_tier, overall_tier) if overall_tier else None,
            "strengths": [
                SURVEY_PILLAR_NAMES.get(p, p) for p in SURVEY_PILLARS
                if pcts.get(p) is not None and pcts[p] >= 85
            ],
            "improvement_opportunities": [
                SURVEY_PILLAR_NAMES.get(p, p) for p in SURVEY_PILLARS
                if pcts.get(p) is not None and pcts[p] < 70
            ],
            "low_pillars": low,
        }

    def _tenant_recommendations(
        self, tenant_id: str, days: int, op: Dict[str, Any],
        model: Dict[str, Any], generated_at: datetime, refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """Cache-aware SMS maturity assessment actions for a single tenant.

        Reused by both the CAAN and Airline dashboards so the AI assessment is
        generated once per tenant+period and shared across scopes.
        """
        recs: List[Dict[str, Any]] = []
        cached = self._read_sms_maturity(tenant_id, days)
        use_cache = (
            not refresh
            and cached is not None
            and cached.get("generated_at") is not None
        )
        if use_cache:
            try:
                gen_dt = cached["generated_at"]
                if hasattr(gen_dt, "timestamp"):
                    use_cache = (generated_at - gen_dt).total_seconds() < SMS_MATURITY_CACHE_TTL
                else:
                    use_cache = False
            except Exception:
                use_cache = False
        if use_cache:
            recs = cached.get("recommendations", [])
        elif model["low_pillars"]:
            recs = recommend_sms_maturity_actions(tenant_id, {
                "pillars": op["pillars"],
                "pcts": model["pcts"],
                "tiers": model["tiers"],
                "question_averages": op.get("question_averages", {}),
                "response_count": op["response_count"],
            })
            self._write_sms_maturity(tenant_id, days, {
                "period_days": days,
                "generated_at": generated_at,
                "pillars": op["pillars"],
                "pcts": model["pcts"],
                "tiers": model["tiers"],
                "overall_sms_maturity": op["overall_sms_maturity"],
                "question_averages": op.get("question_averages", {}),
                "low_pillars": model["low_pillars"],
                "recommendations": recs,
            })
        return recs

    def _tenant_name(self, tenant_id: str) -> str:
        try:
            from app.firebase import get_db
            snap = get_db().collection("tenants").document(tenant_id).get()
            if snap.exists:
                name = snap.to_dict().get("name")
                if name:
                    return name
        except Exception as e:
            logger.warning(f"Failed to read tenant name for {tenant_id}: {e}")
        return tenant_id

    def _survey_history(self, docs) -> List[Dict[str, Any]]:
        """Bucket survey docs by calendar month and aggregate each bucket.

        Reuses _aggregate_surveys so the history uses the same scoring math as
        the current-period view and the CAAN dashboard. This is the single
        source for trend charts.
        """
        buckets: Dict[str, list] = {}
        for d in docs:
            data = d.to_dict()
            ts = data.get("submitted_at")
            if ts is None:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            buckets.setdefault(ts.strftime("%Y-%m"), []).append(d)

        history = []
        for period in sorted(buckets):
            agg = self._aggregate_surveys(buckets[period])
            ops = agg.get("operators", [])
            if not ops:
                continue
            op = ops[0]
            overall = op["overall_sms_maturity"]
            overall_pct = round((overall - 1) / 4 * 100, 1) if overall is not None else None
            overall_tier = sms_maturity_tier(overall_pct) if overall_pct is not None else None

            latest_ts = None
            for d in buckets[period]:
                ts = d.to_dict().get("submitted_at")
                if ts is None:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts

            history.append({
                "period": period,
                "assessment_date": latest_ts.date().isoformat() if latest_ts else period + "-01",
                "overall_score": overall_pct,
                "tier": overall_tier,
                "tier_label": TIER_LABELS.get(overall_tier, overall_tier) if overall_tier else None,
                "pillars": {
                    p: (round((op["pillars"].get(p) - 1) / 4 * 100, 1)
                        if op["pillars"].get(p) is not None else None)
                    for p in SURVEY_PILLARS
                },
                "response_count": op["response_count"],
            })
        return history

    def get_recent_reports(self, **overrides) -> Dict[str, Any]:
        page_size = overrides.pop("page_size", 10) if "page_size" in overrides else 10
        cursor = overrides.pop("cursor", None) if "cursor" in overrides else None
        f = self._base_filter(**overrides).clone(page_size=page_size, cursor=cursor)
        return self.repo.query_reports(f)

    def get_risk_distribution(self, **overrides) -> List[Dict[str, Any]]:
        f = self._base_filter(**overrides)
        reports = self.repo.get_all_in_range(f)
        return MetricsService.calculate_risk_distribution(reports)

    def get_monthly_trends(self, **overrides) -> List[Dict[str, Any]]:
        f = self._base_filter(**overrides)
        reports = self.repo.get_all_in_range(f)
        trends = MetricsService.calculate_monthly_trends(reports)
        self._merge_diversion_trends(trends, overrides.get("days", self.DEFAULT_DAYS))
        return trends

    def _tenant_type(self) -> Optional[str]:
        """Resolve the authenticated tenant's `type` from its tenant doc."""
        if not self.tenant_id:
            return None
        try:
            from app.firebase import get_db
            doc = get_db().collection(settings.FIREBASE_COLLECTION_TENANTS).document(self.tenant_id).get()
            if doc.exists:
                return (doc.to_dict() or {}).get("type")
        except Exception as e:
            logger.warning(f"Failed to resolve tenant type for {self.tenant_id}: {e}")
        return None

    def _merge_diversion_trends(self, trends: List[Dict[str, Any]], days: int) -> None:
        """Attach a `diversions` count to each monthly trend row for flight
        operators (airline / helicopter-operator). Additive only — MRO,
        aerodrome and ground-handling tenants keep their existing rows and get
        no diversion key."""
        if self._tenant_type() not in FLIGHT_OPERATOR_TYPES:
            return
        if not self.tenant_id or not days:
            return
        try:
            from app.firebase import get_db
            db = get_db()
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            docs = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(self.tenant_id).collection(DIVERSION_COLLECTION).get()
        except Exception as e:
            logger.warning(f"Failed to load diversion trends for {self.tenant_id}: {e}")
            return

        month_counts = defaultdict(int)
        for doc in docs:
            raw = (doc.to_dict() or {}).get("date")
            if not raw:
                continue
            if isinstance(raw, str):
                try:
                    raw = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                except ValueError:
                    continue
            if raw.tzinfo is None:
                raw = raw.replace(tzinfo=timezone.utc)
            if raw < cutoff:
                continue
            month_counts[f"{raw.year}-{raw.month:02d}"] += 1

        for row in trends:
            key = f"{row['year']}-{int(row['month']):02d}"
            row["diversions"] = month_counts.get(key, 0)
        row_keys = {f"{r['year']}-{int(r['month']):02d}" for r in trends}
        for key, count in month_counts.items():
            if key not in row_keys:
                year, month = key.split("-")
                trends.append({"month": str(int(month)), "year": int(year),
                               "total": 0, "voluntary": 0, "mandatory": 0,
                               "high_risk": 0, "prediction": None, "diversions": count})
        trends.sort(key=lambda r: (r["year"], int(r["month"])))

    def get_hazard_frequency(self, **overrides) -> List[Dict[str, Any]]:
        f = self._base_filter(**overrides)
        reports = self.repo.get_all_in_range(f)
        return MetricsService.calculate_hazard_frequency(reports)

    def get_ssp_risk_trends(self, **overrides) -> Dict[str, Any]:
        f = self._base_filter(**overrides)
        reports = self.repo.get_all_in_range(f)
        return MetricsService.calculate_ssp_risk_trends(reports)

    def get_actions_summary(self, **overrides) -> Dict[str, Any]:
        f = self._base_filter(**overrides)
        reports = self.repo.get_all_in_range(f)
        return MetricsService.calculate_org_kpis(reports)

    # ------------------------------------------------------------------
    # Public: CAAN dashboard endpoints (cross-tenant, aggregated)
    # ------------------------------------------------------------------

    def _caan_reports(self, **overrides) -> list:
        try:
            f = self._caan_filter(**overrides)
            return self.repo.get_all_in_range(f)
        except Exception as e:
            logger.warning(f'CAAN dashboard query failed (missing index?): {e}')
            return []

    def get_caan_overview(self, **overrides) -> Dict[str, Any]:
        reports = self._caan_reports(**overrides)
        kpis = MetricsService.calculate_kpis(reports)
        ai_kpis = MetricsService.calculate_ai_kpis(reports)
        org_kpis = MetricsService.calculate_org_kpis(reports)

        tenant_counts = self._tenant_report_counts(reports)
        return {
            "kpis": kpis,
            "ai_kpis": ai_kpis,
            "org_kpis": org_kpis,
            "tenant_breakdown": tenant_counts,
        }

    def get_caan_trends(self, **overrides) -> Dict[str, Any]:
        reports = self._caan_reports(**overrides)
        trends = MetricsService.calculate_monthly_trends(reports)

        return {
            "monthly_trends": trends,
            "industry_avg": None,
            "prediction": None,
        }

    def get_caan_risk(self, **overrides) -> Dict[str, Any]:
        reports = self._caan_reports(**overrides)
        dist = MetricsService.calculate_risk_distribution(reports)

        tenant_severity = self._tenant_severity_breakdown(reports)
        return {
            "risk_distribution": dist,
            "tenant_severity": tenant_severity,
        }

    def get_caan_hazards(self, **overrides) -> List[Dict[str, Any]]:
        reports = self._caan_reports(**overrides)
        return MetricsService.calculate_hazard_frequency(reports)

    def get_caan_survey_maturity(self, **overrides) -> Dict[str, Any]:
        """Aggregate SMS survey maturity across all tenants.

        Pulls every survey response in the tenants/{id}/surveys collection
        group and computes, per operator, the average ICAO pillar scores and
        overall SMS maturity (1-5). Returns both the per-operator breakdown and
        the state averages. `regulator_id` scopes the aggregation to one
        State Regulator's operators (e.g. CAAN for Nepal).
        """
        days = overrides.get("days")
        docs = self._survey_docs(days)
        regulator_id = overrides.get("regulator_id")
        if regulator_id:
            from app.services.regulator_service import operator_tenant_ids_for_regulator
            allowed = set(operator_tenant_ids_for_regulator(regulator_id))
            if allowed:
                docs = [d for d in docs if (d.to_dict().get("tenant_id") or None) in allowed]
        return self._aggregate_surveys(docs)

    def get_caan_state(self, **overrides) -> Dict[str, Any]:
        """Full CAAN executive-summary payload, aggregated server-side.

        Computes every figure the State Oversight dashboard renders — the four
        KPI cards, the State Hazard Matrix (severity x probability heatmap),
        the Operator Profiles grid and the SSP risk trend — directly from the
        cross-tenant reports/hazards/responses collections. No client-side
        Firestore queries are needed: the API is the only data source.

        `days` (0 = all time) filters by the doc created_at / submitted_at.
        `regulator_id` scopes the figures to one State Regulator's operators.
        """
        days = int(overrides.get("days") or 0)
        regulator_id = overrides.get("regulator_id")

        def _doc_time(doc):
            return (doc.get("created_at") or doc.get("submitted_at") or
                    doc.get("occurrence_date"))

        def _to_dt(value):
            if value is None:
                return None
            if isinstance(value, datetime):
                return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    return None
            return None

        cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None

        # ---- Tenants (operator profiles) ----
        from app.firebase import get_db
        tenant_ids = None
        if regulator_id:
            from app.services.regulator_service import operator_tenant_ids_for_regulator
            tenant_ids = set(operator_tenant_ids_for_regulator(regulator_id))
        tenant_map: Dict[str, Dict[str, Any]] = {}
        try:
            tenants = list(get_db().collection("tenants").stream())
            for snap in tenants:
                d = snap.to_dict() or {}
                if tenant_ids is not None and snap.id not in tenant_ids:
                    continue
                tenant_map[snap.id] = {
                    "tenant_id": snap.id,
                    "name": d.get("name") or snap.id,
                    "icao": d.get("icao") or "",
                    "country": d.get("country") or "",
                    "active": d.get("active", True),
                }
        except Exception as e:
            logger.warning(f"CAAN state tenants query failed: {e}")

        # ---- Cross-tenant hazards ----
        hazards: List[Dict[str, Any]] = []
        try:
            for snap in get_db().collection_group("hazards").stream():
                d = snap.to_dict() or {}
                if tenant_ids is not None and (d.get("tenant_id") or None) not in tenant_ids:
                    continue
                t = _to_dt(_doc_time(d))
                if cutoff and (t is None or t < cutoff):
                    continue
                hazards.append(d)
        except Exception as e:
            logger.warning(f"CAAN state hazards query failed: {e}")

        # ---- Cross-tenant responses (survey participation) ----
        responses: List[Dict[str, Any]] = []
        try:
            responses = self._survey_responses(days=days, tenant_ids=tenant_ids)
        except Exception as e:
            logger.warning(f"CAAN state responses query failed: {e}")

        # ---- Cross-tenant reports (MORs + SPI trend) ----
        reports: List[Dict[str, Any]] = []
        try:
            from app.firebase import get_cross_tenant_collection
            for snap in get_cross_tenant_collection("reports").limit(5000).stream():
                d = snap.to_dict() or {}
                if tenant_ids is not None and (d.get("tenant_id") or None) not in tenant_ids:
                    continue
                t = _to_dt(_doc_time(d))
                if cutoff and (t is None or t < cutoff):
                    continue
                d["created_at"] = t.isoformat() if isinstance(t, datetime) else d.get("created_at")
                occ = d.get("occurrence_type") or d.get("occurrence_category")
                d["occurrence_category"] = occ
                d["taxonomy"] = d.get("taxonomy") or self._seed_taxonomy(occ)
                reports.append(d)
        except Exception as e:
            logger.warning(f"CAAN state reports query failed: {e}")

        # ---- Per-tenant aggregation ----
        per_tenant: Dict[str, Dict[str, Any]] = {}
        for tid in tenant_map:
            per_tenant[tid] = {"mors": 0, "high_risk_hazards": 0, "responses": 0}
        total_mors = 0
        for r in reports:
            tid = r.get("tenant_id") or "unknown"
            if tid not in per_tenant:
                per_tenant[tid] = {"mors": 0, "high_risk_hazards": 0, "responses": 0}
            if (r.get("report_type") or "").lower() == "mandatory":
                per_tenant[tid]["mors"] += 1
                total_mors += 1
        for h in hazards:
            tid = h.get("tenant_id") or "unknown"
            if tid not in per_tenant:
                per_tenant[tid] = {"mors": 0, "high_risk_hazards": 0, "responses": 0}
            if normalize_tolerability(h.get("risk_level")) in ("HIGH", "VERY HIGH"):
                per_tenant[tid]["high_risk_hazards"] += 1
        for res in responses:
            tid = res.get("tenant_id") or "unknown"
            if tid not in per_tenant:
                per_tenant[tid] = {"mors": 0, "high_risk_hazards": 0, "responses": 0}
            per_tenant[tid]["responses"] += 1

        total_high_risk_hazards = sum(v["high_risk_hazards"] for v in per_tenant.values())
        active_operators = sum(1 for t in tenant_map.values() if t["active"])

        # ---- Hazard matrix heatmap (severity x probability) ----
        heat_map = [{"severity": s, "probability": p, "count": 0} for s in range(1, 6) for p in range(1, 6)]
        level2 = level3 = level4 = 0
        for h in hazards:
            s = h.get("severity")
            p = h.get("probability")
            if isinstance(s, int) and isinstance(p, int) and 1 <= s <= 5 and 1 <= p <= 5:
                cell = next((c for c in heat_map if c["severity"] == s and c["probability"] == p), None)
                if cell:
                    cell["count"] += 1
            tier = normalize_tolerability(h.get("risk_level"))
            if tier == "LOW":
                level2 += 1
            elif tier == "HIGH":
                level3 += 1
            elif tier == "VERY HIGH":
                level4 += 1

        # ---- Operator grid (merge tenant meta + per-tenant stats + maturity) ----
        maturity = self.get_caan_survey_maturity(days=days, regulator_id=regulator_id)
        maturity_by_tenant = {o["tenant_id"]: o for o in (maturity.get("operators") or [])}
        operators = []
        for tid, meta in tenant_map.items():
            stats = per_tenant.get(tid, {"mors": 0, "high_risk_hazards": 0, "responses": 0})
            mat = maturity_by_tenant.get(tid) or {}
            operators.append({
                "tenant_id": tid,
                "name": meta["name"],
                "icao": meta["icao"],
                "country": meta["country"],
                "active": meta["active"],
                "mors": stats["mors"],
                "high_risk_hazards": stats["high_risk_hazards"],
                "responses": stats["responses"],
                "sms_maturity": mat.get("overall_sms_maturity"),
                "pillars": mat.get("pillars"),
            })

        # ---- SSP risk trend (quarterly avg risk index by category) ----
        trend = MetricsService.calculate_ssp_risk_trends(reports)

        return {
            "kpis": {
                "mors": total_mors,
                "high_risk_hazards": total_high_risk_hazards,
                "active_operators": active_operators,
                "responses": sum(v["responses"] for v in per_tenant.values()),
            },
            "operators": operators,
            "hazard_matrix": {
                "cells": heat_map,
                "level2": level2,
                "level3": level3,
                "level4": level4,
                "total": len(hazards),
            },
            "spi_trend": trend,
            "sms_maturity": maturity,
        }

    def get_caan_sms_maturity_assessment(self, **overrides) -> Dict[str, Any]:
        """Aggregate period SMS maturity and generate an AI SMS maturity assessment
        with recommended actions for every pillar scoring below 70%
        (tiers: action/critical).

        Assessments are cached per tenant in tenants/{id}/sms_maturity and
        reused within SMS_MATURITY_CACHE_TTL unless refresh=True.
        `regulator_id` scopes the assessment to one State Regulator's operators.
        """
        days = overrides.get("days", 90)
        refresh = bool(overrides.get("refresh", False))
        generated_at = datetime.now(timezone.utc)

        docs = self._survey_docs(days)
        regulator_id = overrides.get("regulator_id")
        if regulator_id:
            from app.services.regulator_service import operator_tenant_ids_for_regulator
            allowed = set(operator_tenant_ids_for_regulator(regulator_id))
            if allowed:
                docs = [d for d in docs if (d.to_dict().get("tenant_id") or None) in allowed]
        data = self._aggregate_surveys(docs)

        operators = []
        for op in data.get("operators", []):
            tid = op.get("tenant_id", "unknown")
            model = self._sms_maturity_model(op)
            recs = self._tenant_recommendations(tid, days, op, model, generated_at, refresh)
            operators.append({
                "tenant_id": tid,
                "response_count": op["response_count"],
                "overall_sms_maturity": op["overall_sms_maturity"],
                "pillars": op["pillars"],
                "pcts": model["pcts"],
                "tiers": model["tiers"],
                "low_pillars": model["low_pillars"],
                "recommendations": recs,
            })

        return {
            "period_days": days,
            "generated_at": generated_at.isoformat(),
            "operators": operators,
            "state": data.get("state"),
        }

    def _survey_docs(self, days: Optional[int] = None) -> list:
        """Fetch scored surveys from Postgres, optionally filtered to the period.

        Reads the `surveys` table (the system of record; the live submission
        API writes here) instead of the Firestore collection group, which the
        API no longer populates. Returns _PGSurveyDoc wrappers so the shared
        aggregation logic stays unchanged.
        """
        self._register_all_tenant_slugs()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None

        async def _fetch() -> List[Dict[str, Any]]:
            async with session_scope() as session:
                stmt = select(Survey).where(Survey.is_demo == demo_scope())
                if cutoff:
                    stmt = stmt.where(Survey.submitted_at >= cutoff)
                rows = (await session.scalars(stmt)).all()
                return [_survey_row_to_dict(r) for r in rows]

        try:
            return [_PGSurveyDoc(d) for d in run(_fetch())]
        except Exception as e:
            logger.warning(f"CAAN survey maturity query failed: {e}")
            return []

    def _register_all_tenant_slugs(self) -> None:
        """Populate the slug<->uuid tenant registry from Firestore so
        tenant_slug() resolves every tenant's surveys even when only the
        database row (uuid) is available. Survey data lives in Postgres, but
        tenant slugs are still authored in Firestore."""
        try:
            from app.firebase import get_db
            for snap in get_db().collection(settings.FIREBASE_COLLECTION_TENANTS).stream():
                register_tenant(snap.id)
        except Exception as e:
            logger.warning(f"Failed to register tenant slugs for survey queries: {e}")

    def _survey_responses(
        self, days: int, tenant_ids: Optional[set]
    ) -> List[Dict[str, Any]]:
        """Fetch raw survey participation from the `survey_responses` table.

        Returns per-response dicts keyed by tenant slug so the CAAN state
        operator-grid `responses` counter reflects the live Postgres rows that
        the submission API writes, rather than an unpopulated Firestore
        collection.
        """
        self._register_all_tenant_slugs()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None

        async def _fetch() -> List[str]:
            async with session_scope() as session:
                stmt = select(SurveyResponse).where(SurveyResponse.is_demo == demo_scope())
                if cutoff:
                    stmt = stmt.where(SurveyResponse.submitted_at >= cutoff)
                rows = (await session.scalars(stmt)).all()
                return [tenant_slug(r.tenant_id) for r in rows]

        slugs = run(_fetch())
        out: List[Dict[str, Any]] = []
        for slug in slugs:
            if tenant_ids is not None and slug not in tenant_ids:
                continue
            out.append({"tenant_id": slug})
        return out

    def _aggregate_surveys(self, docs) -> Dict[str, Any]:
        by_tenant: Dict[str, Dict[str, Any]] = {}
        state = {p: {"sum": 0.0, "n": 0} for p in SURVEY_PILLARS}
        state_overall = {"sum": 0.0, "n": 0}

        for d in docs:
            data = d.to_dict()
            tid = data.get("tenant_id") or "unknown"
            entry = by_tenant.setdefault(tid, {
                "tenant_id": tid,
                "response_count": 0,
                "pillars": {},
                "question_scores": {},
                "overall_sms_maturity": None,
            })
            entry["response_count"] += 1
            for p in SURVEY_PILLARS:
                v = data.get(p)
                if isinstance(v, (int, float)):
                    entry["pillars"][p] = entry["pillars"].get(p, 0.0) + float(v)
                    state[p]["sum"] += float(v)
                    state[p]["n"] += 1
            qs = data.get("question_scores")
            if isinstance(qs, dict):
                for qid, val in qs.items():
                    if isinstance(val, (int, float)):
                        bucket = entry["question_scores"].setdefault(qid, [0.0, 0])
                        bucket[0] += float(val)
                        bucket[1] += 1
            ov = data.get("overall_sms_maturity")
            if not isinstance(ov, (int, float)):
                ov = data.get("overall_sms_health")
            if isinstance(ov, (int, float)):
                state_overall["sum"] += float(ov)
                state_overall["n"] += 1

        rows = []
        for tid, entry in by_tenant.items():
            n = entry["response_count"]
            for p in SURVEY_PILLARS:
                entry["pillars"][p] = round(entry["pillars"][p] / n, 2) if entry["pillars"].get(p) else None
            entry["question_averages"] = {
                qid: round(s / c, 2) for qid, (s, c) in entry["question_scores"].items()
            }
            entry.pop("question_scores", None)
            vals = [v for v in entry["pillars"].values() if v is not None]
            entry["overall_sms_maturity"] = round(sum(vals) / len(vals), 2) if vals else None
            rows.append(entry)

        rows = sorted(rows, key=lambda t: t["overall_sms_maturity"] or 0, reverse=True)
        return {
            "operators": rows,
            "state": {
                "pillars": {
                    p: round(state[p]["sum"] / state[p]["n"], 2) if state[p]["n"] else None
                    for p in SURVEY_PILLARS
                },
                "overall_sms_maturity": round(state_overall["sum"] / state_overall["n"], 2)
                if state_overall["n"] else None,
                "response_count": sum(e["response_count"] for e in rows),
            },
        }

    def _read_sms_maturity(self, tenant_id: str, days: int) -> Optional[Dict[str, Any]]:
        try:
            from app.firebase import get_db
            ref = (
                get_db().collection("tenants").document(tenant_id)
                .collection("sms_maturity").document(f"days_{days}")
            )
            snap = ref.get()
            return snap.to_dict() if snap.exists else None
        except Exception as e:
            logger.warning(f"Failed to read sms_maturity cache for {tenant_id}: {e}")
            return None

    def _write_sms_maturity(self, tenant_id: str, days: int, data: Dict[str, Any]) -> None:
        try:
            from app.firebase import get_db
            ref = (
                get_db().collection("tenants").document(tenant_id)
                .collection("sms_maturity").document(f"days_{days}")
            )
            ref.set(data)
        except Exception as e:
            logger.warning(f"Failed to write sms_maturity cache for {tenant_id}: {e}")

    def get_caan_benchmark(self, **overrides) -> Dict[str, Any]:
        reports = self._caan_reports(**overrides)
        anon_count = sum(1 for r in reports if r.get("is_anonymous"))
        total = len(reports) or 1

        benchmark = self._state_benchmark()
        return {
            "anonymous_reporting_rate": round(anon_count / total * 100, 1),
            "industry_anon_rate": benchmark.get("industry_anon_rate"),
            "anonymous_trend": None,
            "total_reporters": len(set(r.get("created_by") for r in reports if r.get("created_by"))),
            "benchmark_data": benchmark.get("benchmark_data"),
            "state_risk": benchmark.get("state_risk"),
            "ssp_target_avg": benchmark.get("ssp_target_avg"),
            "ssp_actual_avg": benchmark.get("ssp_actual_avg"),
        }

    def _state_benchmark(self) -> Dict[str, Any]:
        """Read the persisted state-level risk register for industry benchmark
        values. Falls back to None when the register is not yet seeded."""
        try:
            from app.services.state_risk_service import _risk_collection
            rows = list(_risk_collection().stream())
            if not rows:
                return {
                    "industry_anon_rate": None,
                    "benchmark_data": None,
                    "state_risk": None,
                    "ssp_target_avg": None,
                    "ssp_actual_avg": None,
                }
            entries = [r.to_dict() for r in rows]
            top = sorted(
                [e for e in entries if e.get("current_risk_index") is not None],
                key=lambda e: e["current_risk_index"],
                reverse=True,
            )
            targets = [e.get("ssp_target") for e in entries if e.get("ssp_target") is not None]
            actuals = [e.get("actual_ssp_value") for e in entries if e.get("actual_ssp_value") is not None]
            return {
                "industry_anon_rate": None,
                "benchmark_data": {
                    "top_state_risks": [
                        {
                            "category": e.get("icoc_category"),
                            "name": e.get("name"),
                            "current_risk_index": e.get("current_risk_index"),
                            "tolerability": e.get("tolerability"),
                            "trend": e.get("trend"),
                            "contributing_tenants": e.get("contributing_tenants", []),
                        }
                        for e in top[:5]
                    ],
                    "categories_tracked": len(entries),
                    "period": {
                        "year": entries[0].get("year"),
                        "quarter": entries[0].get("quarter"),
                    },
                },
                "state_risk": entries,
                "ssp_target_avg": round(sum(targets) / len(targets), 1) if targets else None,
                "ssp_actual_avg": round(sum(actuals) / len(actuals), 1) if actuals else None,
            }
        except Exception as e:
            logger.warning(f"Failed to read state risk register for benchmark: {e}")
            return {
                "industry_anon_rate": None,
                "benchmark_data": None,
                "state_risk": None,
                "ssp_target_avg": None,
                "ssp_actual_avg": None,
            }

    # ------------------------------------------------------------------
    # Public: Super Admin dashboard endpoints
    # ------------------------------------------------------------------

    def get_admin_system(self) -> Dict[str, Any]:
        f = self._caan_filter(days=settings.DASHBOARD_ADMIN_SYSTEM_DAYS)
        weekly = self.repo.get_all_in_range(f)
        f30 = self._caan_filter(days=settings.DASHBOARD_ADMIN_TENANT_DAYS)
        monthly = self.repo.get_all_in_range(f30)

        from app.firebase import is_firebase_ready
        return {
            "status": "healthy",
            "firebase": "connected" if is_firebase_ready() else "unavailable",
            "reports_last_7d": len(weekly),
            "reports_last_30d": len(monthly),
            "active_tenants": len(set(r.get("tenant_id") for r in monthly if r.get("tenant_id"))),
            "total_unique_reporters": len(set(r.get("created_by") for r in monthly if r.get("created_by"))),
        }

    def get_admin_tenants(self) -> List[Dict[str, Any]]:
        f30 = self._caan_filter(days=settings.DASHBOARD_ADMIN_TENANT_DAYS)
        reports = self.repo.get_all_in_range(f30)

        tenant_map: Dict[str, dict] = {}
        for r in reports:
            tid = r.get("tenant_id", "unknown")
            if tid not in tenant_map:
                tenant_map[tid] = {
                    "tenant_id": tid,
                    "total_reports": 0,
                    "ai_processed": 0,
                    "active_reporters": 0,
                    "high_risk_count": 0,
                    "last_report_date": None,
                }
            tm = tenant_map[tid]
            tm["total_reports"] += 1
            if r.get("ai_status") == "COMPLETED":
                tm["ai_processed"] += 1
            if r.get("severity") == "High":
                tm["high_risk_count"] += 1
            raw_date = r.get("created_at")
            if raw_date:
                if isinstance(raw_date, str):
                    raw_date = datetime.fromisoformat(raw_date)
                if tm["last_report_date"] is None or raw_date > tm["last_report_date"]:
                    tm["last_report_date"] = raw_date

        reporters: Dict[str, set] = {}
        for r in reports:
            tid = r.get("tenant_id", "unknown")
            uid = r.get("created_by")
            if uid:
                reporters.setdefault(tid, set()).add(uid)
        for tid, users in reporters.items():
            if tid in tenant_map:
                tenant_map[tid]["active_reporters"] = len(users)

        return sorted(tenant_map.values(), key=lambda t: t["total_reports"], reverse=True)

    def get_admin_usage(self) -> Dict[str, Any]:
        f = self._caan_filter(days=settings.DASHBOARD_ADMIN_USAGE_DAYS)
        reports = self.repo.get_all_in_range(f)
        return {
            "total_reports_30d": len(reports),
            "report_types": {
                "voluntary": sum(1 for r in reports if r.get("report_type") == "voluntary"),
                "mandatory": sum(1 for r in reports if r.get("report_type") == "mandatory"),
            },
            "status_breakdown": dict(
                (s, sum(1 for r in reports if r.get("status") == s))
                for s in set(r.get("status", "UNKNOWN") for r in reports)
            ),
            "monthly_usage": MetricsService.calculate_monthly_trends(reports),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _base_filter(self, days: int = DEFAULT_DAYS, **overrides) -> ReportFilter:
        """Build a tenant-scoped filter with a date range.

        days=0 / days=None means "All Time" — no created_at cutoff is applied.
        """
        date_from = date_to = None
        if days:
            now = datetime.now(timezone.utc)
            date_from = now - timedelta(days=days)
            date_to = now
        params = dict(
            tenant_id=self.tenant_id,
            cross_tenant=False,
            date_from=date_from,
            date_to=date_to,
        )
        params.update(overrides)
        logger.debug(f"_base_filter: tenant_id={self.tenant_id}, days={days}, date_from={date_from}, date_to={date_to}")
        return ReportFilter(**params)

    def _caan_filter(self, days: int = DEFAULT_DAYS, **overrides) -> ReportFilter:
        """Build a cross-tenant filter for CAAN_SMD / SUPER_ADMIN.

        days=0 / days=None means "All Time" — no created_at cutoff is applied.
        """
        date_from = date_to = None
        if days:
            now = datetime.now(timezone.utc)
            date_from = now - timedelta(days=days)
            date_to = now
        params = dict(
            tenant_id=None,
            cross_tenant=True,
            date_from=date_from,
            date_to=date_to,
        )
        params.update(overrides)
        return ReportFilter(**params)

    _SEED_TAXONOMY = {
        "bird strike": "Wildlife",
        "bird activity": "Wildlife",
        "runway incursion": "Organizational-Facilities",
        "runway excursion": "Organizational-Facilities",
        "abnormal runway contact": "Organizational-Facilities",
        "ground collision": "Organizational-Facilities",
        "airborne conflict": "Organizational-Facilities",
        "atc operational incident": "Organizational-Documentation, Processes and Procedures",
        "procedural deviation": "Organizational-Documentation, Processes and Procedures",
        "sop deviation": "Organizational-Documentation, Processes and Procedures",
        "system/component failure": "Technical",
        "powerplant failure": "Technical",
        "maintenance hazard": "Technical",
        "weather encounter": "Environmental",
        "weather": "Environmental",
        "cabin safety event": "Human Factors",
        "cabin safety": "Human Factors",
        "human factors": "Human Factors",
        "fatigue": "Human Factors",
        "crm": "Human Factors",
        "communication": "Human Factors",
        "training": "Human Factors",
    }

    @staticmethod
    def _seed_taxonomy(occurrence: Optional[str]) -> Optional[str]:
        """Map a descriptive seed occurrence type to its SMS taxonomy so the
        state SPI trend classifies reports into the five SSP categories."""
        if not occurrence:
            return None
        return DashboardService._SEED_TAXONOMY.get(str(occurrence).strip().lower())

    @staticmethod
    def _tenant_report_counts(reports: List[dict]) -> List[Dict[str, Any]]:
        counts: Dict[str, int] = {}
        for r in reports:
            tid = r.get("tenant_id", "unknown")
            counts[tid] = counts.get(tid, 0) + 1
        return [
            {"tenant_id": tid, "report_count": cnt}
            for tid, cnt in sorted(counts.items(), key=lambda x: x[1], reverse=True)
        ]

    @staticmethod
    def _tenant_severity_breakdown(reports: List[dict]) -> List[Dict[str, Any]]:
        from collections import defaultdict, Counter
        breakdown: Dict[str, Counter] = defaultdict(Counter)
        for r in reports:
            tid = r.get("tenant_id", "unknown")
            sev = r.get("severity", "Unspecified")
            breakdown[tid][sev] += 1
        return [
            {"tenant_id": tid, "severity_counts": dict(cnt)}
            for tid, cnt in sorted(breakdown.items())
        ]
