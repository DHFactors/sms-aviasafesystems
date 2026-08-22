# ============================================================================
# FILE: dashboard.py
# PATH: backend/app/routes/dashboard.py
# VERSION: 2.0.0
# DATE CREATED: 2026-07-03
# DATE REVISED: 2026-07-27
# PURPOSE: Thin route controllers for dashboard analytics.
#          No business logic — delegates entirely to DashboardService.
# AUTHOR: Ghanshyam Acharya
# CODE OWNER: AviaSafeSystems
# ============================================================================

from fastapi import APIRouter, Depends, Query
from typing import Dict, Any, Optional
from datetime import datetime

from app.core.config import settings
from app.middleware.auth import get_current_user, get_tenant_user, get_caan_user, get_admin_user
from app.services.dashboard_service import DashboardService
from loguru import logger

router = APIRouter()


def _envelope(data: Any) -> Dict[str, Any]:
    return {
        "status": "success",
        "timestamp": datetime.now(),
        "data": data,
    }


def _empty_kpis():
    return {
        "total_reports": 0, "open_reports": 0, "closed_reports": 0,
        "high_risk_reports": 0, "critical_reports": 0,
        "anonymous_percentage": 0.0, "avg_closure_days": None,
        "reporting_rate_trend": None, "repeat_occurrence_rate": None,
    }


def _empty_ai_kpis():
    return {
        "ai_processed": 0, "ai_pending": 0, "ai_failed": 0,
        "avg_processing_time_ms": None, "avg_confidence": None,
        "model_versions": {},
    }


def _empty_org_kpis():
    return {
        "active_reporters": 0, "reporting_frequency": None,
        "corrective_actions_open": 0, "corrective_actions_closed": 0,
        "safety_actions_overdue": 0, "investigation_backlog": 0,
    }


# ======================================================================
# Airline Dashboard (tenant-scoped)
# ======================================================================


@router.get("/overview")
async def get_dashboard_overview(
    days: Optional[int] = Query(90, ge=0),
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    logger.info(f"Dashboard overview request: user={user.get('email')}, role={user.get('role')}, tenant_id={user.get('tenant_id')}, days={days}")
    svc = DashboardService(user)
    try:
        data = svc.get_airline_overview(days=days)
        kpi_count = (data.get("kpis") or {}).get("total_reports", -1)
        logger.info(f"Dashboard overview result for tenant {user.get('tenant_id')}: total_reports={kpi_count}")
        return _envelope(data)
    except Exception as e:
        logger.error(f"Dashboard overview failed for tenant {user.get('tenant_id')}: {e}")
        return _envelope({
            "kpis": _empty_kpis(),
            "ai_kpis": _empty_ai_kpis(),
            "org_kpis": _empty_org_kpis(),
        })


LIST_METHODS = {"get_risk_distribution", "get_monthly_trends", "get_hazard_frequency"}


def _safe_airline(method_name: str, svc: DashboardService, **kwargs):
    try:
        fn = getattr(svc, method_name)
        return fn(**kwargs)
    except Exception as e:
        logger.error(f"{method_name} failed for tenant {svc.tenant_id}: {e}")
        return [] if method_name in LIST_METHODS else {}


@router.get("/recent")
async def get_recent_reports(
    days: Optional[int] = Query(90, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1),
    cursor: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    clamped = min(page_size, settings.REPO_MAX_PAGE_SIZE)
    if clamped != page_size:
        logger.info(f"page_size clamped from {page_size} to {clamped} for tenant {user.get('tenant_id')}")
    svc = DashboardService(user)
    data = _safe_airline("get_recent_reports", svc, days=days, page=page, page_size=clamped, cursor=cursor)
    return _envelope(data)


@router.get("/risk")
async def get_risk_distribution(
    days: Optional[int] = Query(90, ge=0),
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    svc = DashboardService(user)
    data = _safe_airline("get_risk_distribution", svc, days=days)
    return _envelope(data)


@router.get("/trends")
async def get_monthly_trends(
    days: int = Query(180, ge=0, le=730),
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    svc = DashboardService(user)
    data = _safe_airline("get_monthly_trends", svc, days=days)
    return _envelope(data)


@router.get("/risk-trends")
async def get_ssp_risk_trends(
    days: int = Query(730, ge=30, le=1825),
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    """Tenant-scoped quarterly SSP risk trend (avg risk-index per SSP category).

    Operators see only their own aggregated, anonymized risk evolution —
    never another tenant's data and never individual report content.
    """
    svc = DashboardService(user)
    data = _safe_airline("get_ssp_risk_trends", svc, days=days)
    return _envelope(data)


@router.get("/hazards")
async def get_hazard_frequency(
    days: Optional[int] = Query(90, ge=0),
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    svc = DashboardService(user)
    data = _safe_airline("get_hazard_frequency", svc, days=days)
    return _envelope(data)


@router.get("/actions")
async def get_actions_summary(
    days: Optional[int] = Query(90, ge=0),
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    svc = DashboardService(user)
    data = _safe_airline("get_actions_summary", svc, days=days)
    return _envelope(data)


@router.get("/master-register")
async def get_master_register(
    department: Optional[str] = Query(None),
    assigned_to_uid: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    user_department: Optional[str] = Query(None),
    archetypeId: Optional[str] = Query(None, description="Virtual archetype tenant (demo-fixed-wing / demo-rotary-wing)."),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Unified Master Register: hazards + CANs + CAPs in one scoped view.

    Supports department and assignee filtering. Available to any authenticated
    tenant user (their own tenant) and to CAAN/SUPER_ADMIN (all tenants).

    Assignee matching is flexible: a task matches on uid OR email OR
    normalized department (e.g. '145' resolves to 'Part-145').

    `archetypeId` (demo-* values only) scopes the register to a virtual
    archetype tenant for prospect demonstrations — safe fallback returns the
    caller's own tenant for any other value.
    """
    from app.services.archetype_scope import is_archetype_id
    from app.services.master_register import build_master_register
    from app.middleware.auth import get_department_scope

    # 145 / CAMO accounts are restricted to their own department. Force the
    # normalized department scope but keep their personal identity so they see
    # the whole department's CANs/CAPs plus anything assigned directly to them.
    scope = get_department_scope(user)
    if scope:
        department = scope

    if is_archetype_id(archetypeId):
        # Prospect demo: scope strictly to the virtual archetype tenant, then
        # merge the caller's session overlays (masters stay immutable).
        scoped_user = dict(user)
        scoped_user["tenant_id"] = str(archetypeId).strip()
        scoped_user["role"] = "AIRLINE_ADMIN"
        data = build_master_register(
            scoped_user,
            department=department,
            assigned_to_uid=assigned_to_uid,
            assigned_to_email=assigned_to or user.get("email"),
            user_department=user_department,
        )
        try:
            from app.firebase import get_db
            from demo.session_manager import apply_overlay, load_cap_overlays

            overlays = load_cap_overlays(get_db(), user.get("email"))
            if overlays:
                data["rows"] = apply_overlay(data["rows"], overlays)
                data["demo_overlays_applied"] = len(overlays)
        except Exception:
            pass  # overlay merge is best-effort; master rows still render
    else:
        data = build_master_register(
            user,
            department=department,
            assigned_to_uid=assigned_to_uid,
            assigned_to_email=assigned_to,
            user_department=user_department,
        )
    return _envelope(data)


@router.get("/airline/sms-maturity")
async def get_airline_sms_maturity(
    days: int = Query(365, ge=30, le=730),
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    """Tenant-scoped SMS maturity: overall score, ICAO pillars, SMS maturity
    assessment, and historical trends — for the authenticated airline only.
    """
    svc = DashboardService(user)
    try:
        data = svc.get_airline_sms_maturity(days=days)
    except Exception as e:
        logger.error(f"Airline SMS maturity failed for tenant {user.get('tenant_id')}: {e}")
        data = {
            "tenant": user.get("tenant_id"),
            "tenant_id": user.get("tenant_id"),
            "overall_score": None,
            "tier": None,
            "tier_label": None,
            "pillars": {},
            "assessment": {"strengths": [], "improvement_opportunities": [], "priority_actions": []},
            "history": [],
            "latest_assessment_date": None,
            "response_count": 0,
            "period_days": days,
            "error": str(e),
        }
    return _envelope(data)


# ======================================================================
# CAAN Dashboard (cross-tenant, aggregated)
# ======================================================================


@router.get("/caan/overview")
async def get_caan_overview(
    days: Optional[int] = Query(90, ge=0),
    user: Dict[str, Any] = Depends(get_caan_user),
):
    svc = DashboardService(user)
    data = svc.get_caan_overview(days=days)
    return _envelope(data)


@router.get("/caan/trends")
async def get_caan_trends(
    days: int = Query(180, ge=0, le=730),
    user: Dict[str, Any] = Depends(get_caan_user),
):
    svc = DashboardService(user)
    data = svc.get_caan_trends(days=days)
    return _envelope(data)


@router.get("/caan/risk")
async def get_caan_risk(
    days: Optional[int] = Query(90, ge=0),
    user: Dict[str, Any] = Depends(get_caan_user),
):
    svc = DashboardService(user)
    data = svc.get_caan_risk(days=days)
    return _envelope(data)


@router.get("/caan/hazards")
async def get_caan_hazards(
    days: Optional[int] = Query(90, ge=0),
    user: Dict[str, Any] = Depends(get_caan_user),
):
    svc = DashboardService(user)
    data = svc.get_caan_hazards(days=days)
    return _envelope(data)


@router.get("/caan/survey-maturity")
async def get_caan_survey_maturity(
    regulator_id: Optional[str] = Query(None, description="State Regulator id (e.g. caan) to scope the maturity view"),
    user: Dict[str, Any] = Depends(get_caan_user),
):
    svc = DashboardService(user)
    data = svc.get_caan_survey_maturity(regulator_id=regulator_id)
    return _envelope(data)


@router.get("/caan/state")
async def get_caan_state(
    days: int = Query(0, ge=0, description="Lookback window in days; 0 = all time"),
    regulator_id: Optional[str] = Query(None, description="State Regulator id (e.g. caan) to scope the state view"),
    user: Dict[str, Any] = Depends(get_caan_user),
):
    svc = DashboardService(user)
    data = svc.get_caan_state(days=days, regulator_id=regulator_id)
    return _envelope(data)


@router.get("/caan/sms-maturity-assessment")
async def get_caan_sms_maturity_assessment(
    days: int = Query(90, ge=30, le=365),
    refresh: bool = Query(False),
    regulator_id: Optional[str] = Query(None, description="State Regulator id (e.g. caan) to scope the assessment"),
    user: Dict[str, Any] = Depends(get_caan_user),
):
    svc = DashboardService(user)
    try:
        data = svc.get_caan_sms_maturity_assessment(days=days, refresh=refresh, regulator_id=regulator_id)
    except Exception as e:
        logger.error(f"CAAN SMS maturity assessment failed: {e}")
        data = {"period_days": days, "generated_at": None, "operators": [], "state": None, "error": str(e)}
    return _envelope(data)


@router.get("/caan/benchmark")
async def get_caan_benchmark(
    days: int = Query(180, ge=1, le=730),
    user: Dict[str, Any] = Depends(get_caan_user),
):
    svc = DashboardService(user)
    data = svc.get_caan_benchmark(days=days)
    return _envelope(data)


# ======================================================================
# Super Admin Dashboard (system-level)
# ======================================================================


@router.get("/admin/system")
async def get_admin_system(
    user: Dict[str, Any] = Depends(get_admin_user),
):
    svc = DashboardService(user)
    data = svc.get_admin_system()
    return _envelope(data)


@router.get("/admin/tenants")
async def get_admin_tenants(
    user: Dict[str, Any] = Depends(get_admin_user),
):
    svc = DashboardService(user)
    data = svc.get_admin_tenants()
    return _envelope(data)


@router.get("/admin/usage")
async def get_admin_usage(
    days: int = Query(30, ge=1, le=365),
    user: Dict[str, Any] = Depends(get_admin_user),
):
    svc = DashboardService(user)
    data = svc.get_admin_usage(days=days)
    return _envelope(data)
