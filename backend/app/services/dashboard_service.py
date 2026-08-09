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
from typing import Dict, Any, List, Optional
from loguru import logger

from app.core.config import settings
from app.services.repository import ReportRepository, ReportFilter
from app.services.metrics_service import MetricsService
from app.services.gemini import recommend_sms_health_actions, sms_health_tier, SURVEY_PILLAR_NAMES

SURVEY_PILLARS = ["safety_policy", "safety_risk_management", "safety_assurance", "safety_promotion"]
SMS_HEALTH_CACHE_TTL = 6 * 3600  # seconds

# Friendly labels for the SMS health tiers produced by the shared engine.
TIER_LABELS = {
    "strong": "Good",
    "watch": "Watch",
    "action": "Action Needed",
    "critical": "Critical",
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

    def get_airline_sms_health(self, **overrides) -> Dict[str, Any]:
        """Tenant-scoped SMS health for the authenticated airline.

        Derives every value from the same core SMS health model used by the
        CAAN dashboard (_survey_docs + _aggregate_surveys + _sms_health_model +
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

        model = self._sms_health_model(op)
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

    def _sms_health_model(self, op: Dict[str, Any]) -> Dict[str, Any]:
        """Shared SMS health model derived from one aggregated operator row.

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
            tiers[p] = sms_health_tier(pct)
            if pct < 70:
                low.append({"pillar": p, "score": v, "pct": pct, "tier": tiers[p]})

        overall_1_5 = op["overall_sms_health"]
        overall_pct = round((overall_1_5 - 1) / 4 * 100, 1) if overall_1_5 is not None else None
        overall_tier = sms_health_tier(overall_pct) if overall_pct is not None else None

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
        """Cache-aware SMS health assessment actions for a single tenant.

        Reused by both the CAAN and Airline dashboards so the AI assessment is
        generated once per tenant+period and shared across scopes.
        """
        recs: List[Dict[str, Any]] = []
        cached = self._read_sms_health(tenant_id, days)
        use_cache = (
            not refresh
            and cached is not None
            and cached.get("generated_at") is not None
        )
        if use_cache:
            try:
                gen_dt = cached["generated_at"]
                if hasattr(gen_dt, "timestamp"):
                    use_cache = (generated_at - gen_dt).total_seconds() < SMS_HEALTH_CACHE_TTL
                else:
                    use_cache = False
            except Exception:
                use_cache = False
        if use_cache:
            recs = cached.get("recommendations", [])
        elif model["low_pillars"]:
            recs = recommend_sms_health_actions(tenant_id, {
                "pillars": op["pillars"],
                "pcts": model["pcts"],
                "tiers": model["tiers"],
                "question_averages": op.get("question_averages", {}),
                "response_count": op["response_count"],
            })
            self._write_sms_health(tenant_id, days, {
                "period_days": days,
                "generated_at": generated_at,
                "pillars": op["pillars"],
                "pcts": model["pcts"],
                "tiers": model["tiers"],
                "overall_sms_health": op["overall_sms_health"],
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
            overall = op["overall_sms_health"]
            overall_pct = round((overall - 1) / 4 * 100, 1) if overall is not None else None
            overall_tier = sms_health_tier(overall_pct) if overall_pct is not None else None

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
        return MetricsService.calculate_monthly_trends(reports)

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

    def get_caan_survey_health(self, **overrides) -> Dict[str, Any]:
        """Aggregate SMS survey health across all tenants.

        Pulls every survey response in the tenants/{id}/surveys collection
        group and computes, per operator, the average ICAO pillar scores and
        overall SMS health (1-5). Returns both the per-operator breakdown and
        the national averages. `regulator_id` scopes the aggregation to one
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

    def get_caan_sms_health_assessment(self, **overrides) -> Dict[str, Any]:
        """Aggregate period SMS health and generate an AI SMS health assessment
        with recommended actions for every pillar scoring below 70%
        (tiers: action/critical).

        Assessments are cached per tenant in tenants/{id}/sms_health and
        reused within SMS_HEALTH_CACHE_TTL unless refresh=True.
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
            model = self._sms_health_model(op)
            recs = self._tenant_recommendations(tid, days, op, model, generated_at, refresh)
            operators.append({
                "tenant_id": tid,
                "response_count": op["response_count"],
                "overall_sms_health": op["overall_sms_health"],
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
            "national": data.get("national"),
        }

    def _survey_docs(self, days: Optional[int] = None) -> list:
        """Fetch tenants/{id}/surveys docs, optionally filtered to the period."""
        try:
            from app.firebase import get_db
            docs = list(get_db().collection_group("surveys").get())
        except Exception as e:
            logger.warning(f"CAAN survey health query failed: {e}")
            return []
        if not days:
            return docs
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = []
        for d in docs:
            ts = d.to_dict().get("submitted_at")
            try:
                if ts is None:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    result.append(d)
            except Exception:
                continue
        return result

    def _aggregate_surveys(self, docs) -> Dict[str, Any]:
        by_tenant: Dict[str, Dict[str, Any]] = {}
        national = {p: {"sum": 0.0, "n": 0} for p in SURVEY_PILLARS}
        national_overall = {"sum": 0.0, "n": 0}

        for d in docs:
            data = d.to_dict()
            tid = data.get("tenant_id") or "unknown"
            entry = by_tenant.setdefault(tid, {
                "tenant_id": tid,
                "response_count": 0,
                "pillars": {},
                "question_scores": {},
                "overall_sms_health": None,
            })
            entry["response_count"] += 1
            for p in SURVEY_PILLARS:
                v = data.get(p)
                if isinstance(v, (int, float)):
                    entry["pillars"][p] = entry["pillars"].get(p, 0.0) + float(v)
                    national[p]["sum"] += float(v)
                    national[p]["n"] += 1
            qs = data.get("question_scores")
            if isinstance(qs, dict):
                for qid, val in qs.items():
                    if isinstance(val, (int, float)):
                        bucket = entry["question_scores"].setdefault(qid, [0.0, 0])
                        bucket[0] += float(val)
                        bucket[1] += 1
            ov = data.get("overall_sms_health")
            if isinstance(ov, (int, float)):
                national_overall["sum"] += float(ov)
                national_overall["n"] += 1

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
            entry["overall_sms_health"] = round(sum(vals) / len(vals), 2) if vals else None
            rows.append(entry)

        rows = sorted(rows, key=lambda t: t["overall_sms_health"] or 0, reverse=True)
        return {
            "operators": rows,
            "national": {
                "pillars": {
                    p: round(national[p]["sum"] / national[p]["n"], 2) if national[p]["n"] else None
                    for p in SURVEY_PILLARS
                },
                "overall_sms_health": round(national_overall["sum"] / national_overall["n"], 2)
                if national_overall["n"] else None,
                "response_count": sum(e["response_count"] for e in rows),
            },
        }

    def _read_sms_health(self, tenant_id: str, days: int) -> Optional[Dict[str, Any]]:
        try:
            from app.firebase import get_db
            ref = (
                get_db().collection("tenants").document(tenant_id)
                .collection("sms_health").document(f"days_{days}")
            )
            snap = ref.get()
            return snap.to_dict() if snap.exists else None
        except Exception as e:
            logger.warning(f"Failed to read sms_health cache for {tenant_id}: {e}")
            return None

    def _write_sms_health(self, tenant_id: str, days: int, data: Dict[str, Any]) -> None:
        try:
            from app.firebase import get_db
            ref = (
                get_db().collection("tenants").document(tenant_id)
                .collection("sms_health").document(f"days_{days}")
            )
            ref.set(data)
        except Exception as e:
            logger.warning(f"Failed to write sms_health cache for {tenant_id}: {e}")

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
                    "top_national_risks": [
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
        """Build a tenant-scoped filter with a default date range."""
        now = datetime.now(timezone.utc)
        date_from = now - timedelta(days=days)
        params = dict(
            tenant_id=self.tenant_id,
            cross_tenant=False,
            date_from=date_from,
            date_to=now,
        )
        params.update(overrides)
        logger.debug(f"_base_filter: tenant_id={self.tenant_id}, days={days}, date_from={date_from}, date_to={now}")
        return ReportFilter(**params)

    def _caan_filter(self, days: int = DEFAULT_DAYS, **overrides) -> ReportFilter:
        """Build a cross-tenant filter for CAAN_SMD / SUPER_ADMIN."""
        now = datetime.now(timezone.utc)
        params = dict(
            tenant_id=None,
            cross_tenant=True,
            date_from=now - timedelta(days=days),
            date_to=now,
        )
        params.update(overrides)
        return ReportFilter(**params)

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
