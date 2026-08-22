from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import Dict, Any, Optional, List
from loguru import logger
from datetime import datetime, timezone

from app.models.can_cap import (
    CANCreate, CANUpdate, CANResponse, CANListItem,
    CAPCreate, CAPUpdate, CAPReview, CAPResponse, CANStatus, CAPStatus
)
from app.middleware.auth import get_current_user, get_tenant_user, get_safety_manager, get_responsible_manager, get_department_scope
from app.services.can_cap_service import CanCapService
from app.services.audit_service import log_audit, request_context

router = APIRouter()


# ─── CAN Endpoints ───

@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def issue_can(
    can: CANCreate,
    request: Request,
    user: Dict[str, Any] = Depends(get_safety_manager),
):
    if not user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Tenant access required")
    # CAAN inspectors hold READ-ONLY access to operator records
    # (Headway audit / CAR-19 oversight: aggregate analytics only).
    if str(user.get("role") or "") in ("CAAN_SMD", "CAAN_INSPECTOR"):
        raise HTTPException(
            status_code=403,
            detail="CAAN inspectors have READ-ONLY access to operator CAN/CAP records",
        )
    tenant_id = user["tenant_id"]
    service = CanCapService(tenant_id)
    stored = service.issue_can(can.model_dump(), user)
    ip, request_id = request_context(request)
    log_audit(
        action="CAN_ISSUED",
        user=user.get("email"),
        tenant_id=tenant_id,
        target_type="can",
        target_id=stored.get("id"),
        ip=ip,
        request_id=request_id,
        metadata={"can_reference": stored.get("can_reference"), "hazard_id": stored.get("hazard_id")},
    )
    return _to_can_response(stored)


@router.get("/", response_model=List[CANListItem])
async def list_cans(
    hazard_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    days: Optional[int] = Query(None, ge=0, description="Only CANs issued within the last N days. 0 or omitted = All Time."),
    archetypeId: Optional[str] = Query(None, description="Virtual archetype tenant (demo-fixed-wing / demo-rotary-wing)."),
    user: Dict[str, Any] = Depends(get_current_user),
):
    from app.services.archetype_scope import resolve_data_tenant

    effective_tenant = resolve_data_tenant(archetypeId, user)
    service = CanCapService(effective_tenant)
    filters = {}
    if hazard_id:
        filters["hazard_id"] = hazard_id
    if status:
        filters["status"] = status
    if priority:
        filters["priority"] = priority
    if assigned_to:
        filters["assigned_to"] = assigned_to
    if department:
        filters["department"] = department
    if search:
        filters["search"] = search
    if days:
        filters["days"] = days

    # 145 / CAMO accounts are restricted to their own department.
    scope = get_department_scope(user)
    if scope:
        filters["department"] = scope

    docs = service.list_cans(user, filters)
    return [_to_can_list_item(d) for d in docs]


@router.get("/stats", response_model=dict)
async def get_can_stats(
    user: Dict[str, Any] = Depends(get_current_user),
):
    service = CanCapService(user.get("tenant_id", "default"))
    # 145 / CAMO accounts are restricted to their own department.
    scope = get_department_scope(user)
    can_stats = service.get_can_stats(user, department=scope)
    cap_stats = service.get_cap_stats(user, department=scope)
    return {"cans": can_stats, "caps": cap_stats}


@router.get("/caps", response_model=List[dict])
async def list_all_caps(
    status: Optional[str] = Query(None),
    can_id: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    days: Optional[int] = Query(None, ge=0, description="Only CAPs submitted within the last N days. 0 or omitted = All Time."),
    archetypeId: Optional[str] = Query(None, description="Virtual archetype tenant (demo-fixed-wing / demo-rotary-wing)."),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List all CAPs for the current tenant, each joined with the CAN it refers
    to (reference + issued date) for the CAP register page."""
    from app.services.archetype_scope import resolve_data_tenant

    effective_tenant = resolve_data_tenant(archetypeId, user)
    service = CanCapService(effective_tenant)
    filters = {}
    if status:
        filters["status"] = status
    if can_id:
        filters["can_id"] = can_id
    if department:
        filters["department"] = department
    if search:
        filters["search"] = search
    if days:
        filters["days"] = days

    # 145 / CAMO accounts are restricted to their own department.
    scope = get_department_scope(user)
    if scope:
        filters["department"] = scope

    docs = service.list_all_caps(user, filters)
    return [_to_cap_list_item(d) for d in docs]


@router.get("/{can_id}", response_model=dict)
async def get_can(
    can_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    effective_tenant = user.get("tenant_id", "default")
    service = CanCapService(effective_tenant)
    doc = service.get_can(can_id, user)
    if not doc:
        raise HTTPException(status_code=404, detail="CAN not found")
    return _to_can_response(doc)


@router.patch("/{can_id}/status", response_model=dict)
async def update_can_status(
    can_id: str,
    status: CANStatus,
    user: Dict[str, Any] = Depends(get_safety_manager),
):
    if not user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Tenant access required")
    # CAAN inspectors hold READ-ONLY access to operator records
    # (Headway audit / CAR-19 oversight: aggregate analytics only).
    if str(user.get("role") or "") in ("CAAN_SMD", "CAAN_INSPECTOR"):
        raise HTTPException(
            status_code=403,
            detail="CAAN inspectors have READ-ONLY access to operator CAN/CAP records",
        )
    tenant_id = user["tenant_id"]
    service = CanCapService(tenant_id)
    updated = service.update_can_status(can_id, status.value, user)
    if not updated:
        raise HTTPException(status_code=404, detail="CAN not found")
    return _to_can_response(updated)


@router.delete("/{can_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_can(
    can_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_safety_manager),
):
    if not user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Tenant access required")
    # CAAN inspectors hold READ-ONLY access to operator records
    # (Headway audit / CAR-19 oversight: aggregate analytics only).
    if str(user.get("role") or "") in ("CAAN_SMD", "CAAN_INSPECTOR"):
        raise HTTPException(
            status_code=403,
            detail="CAAN inspectors have READ-ONLY access to operator CAN/CAP records",
        )
    tenant_id = user["tenant_id"]
    service = CanCapService(tenant_id)
    deleted = service.delete_can(can_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="CAN not found")
    ip, request_id = request_context(request)
    log_audit(
        action="CAN_DELETED",
        user=user.get("email"),
        tenant_id=tenant_id,
        target_type="can",
        target_id=can_id,
        ip=ip,
        request_id=request_id,
    )


# ─── CAP Endpoints ───

@router.post("/{can_id}/caps", response_model=dict, status_code=status.HTTP_201_CREATED)
async def submit_cap(
    can_id: str,
    cap: CAPCreate,
    request: Request,
    user: Dict[str, Any] = Depends(get_responsible_manager),
):
    if not user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Tenant access required")
    # CAAN inspectors hold READ-ONLY access to operator records
    # (Headway audit / CAR-19 oversight: aggregate analytics only).
    if str(user.get("role") or "") in ("CAAN_SMD", "CAAN_INSPECTOR"):
        raise HTTPException(
            status_code=403,
            detail="CAAN inspectors have READ-ONLY access to operator CAN/CAP records",
        )
    tenant_id = user["tenant_id"]
    service = CanCapService(tenant_id)
    try:
        stored = service.submit_cap(cap.can_id, cap.model_dump(), user)
        ip, request_id = request_context(request)
        log_audit(
            action="CAP_SUBMITTED",
            user=user.get("email"),
            tenant_id=tenant_id,
            target_type="cap",
            target_id=stored.get("id"),
            ip=ip,
            request_id=request_id,
            metadata={"can_id": can_id},
        )
        return _to_cap_response(stored)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{can_id}/caps", response_model=List[dict])
async def list_caps(
    can_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    effective_tenant = user.get("tenant_id", "default")
    service = CanCapService(effective_tenant)
    docs = service.list_caps(can_id, user)
    return [_to_cap_list_item(d) for d in docs]


@router.get("/caps/{cap_id}", response_model=dict)
async def get_cap(
    cap_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    effective_tenant = user.get("tenant_id", "default")
    service = CanCapService(effective_tenant)
    doc = service.get_cap(cap_id, user)
    if not doc:
        raise HTTPException(status_code=404, detail="CAP not found")
    return _to_cap_response(doc)


@router.patch("/caps/{cap_id}", response_model=dict)
async def update_cap(
    cap_id: str,
    data: CAPUpdate,
    user: Dict[str, Any] = Depends(get_responsible_manager),
):
    if not user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Tenant access required")
    # CAAN inspectors hold READ-ONLY access to operator records
    # (Headway audit / CAR-19 oversight: aggregate analytics only).
    if str(user.get("role") or "") in ("CAAN_SMD", "CAAN_INSPECTOR"):
        raise HTTPException(
            status_code=403,
            detail="CAAN inspectors have READ-ONLY access to operator CAN/CAP records",
        )
    tenant_id = user["tenant_id"]
    service = CanCapService(tenant_id)
    payload = {k: v for k, v in data.model_dump().items() if v is not None}
    updated = service.update_cap(cap_id, payload, user)
    if not updated:
        raise HTTPException(status_code=404, detail="CAP not found")
    return _to_cap_response(updated)


@router.patch("/caps/{cap_id}/review", response_model=dict)
async def review_cap(
    cap_id: str,
    review: CAPReview,
    user: Dict[str, Any] = Depends(get_safety_manager),
):
    if not user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Tenant access required")
    # CAAN inspectors hold READ-ONLY access to operator records
    # (Headway audit / CAR-19 oversight: aggregate analytics only).
    if str(user.get("role") or "") in ("CAAN_SMD", "CAAN_INSPECTOR"):
        raise HTTPException(
            status_code=403,
            detail="CAAN inspectors have READ-ONLY access to operator CAN/CAP records",
        )
    tenant_id = user["tenant_id"]
    # Session isolation: master archetype tenants are immutable from the CAP
    # review path — demo AEs must use /api/v1/demo/session/decision.
    if str(tenant_id).startswith("demo-"):
        raise HTTPException(
            status_code=403,
            detail="Demo archetype data is read-only. Use /api/v1/demo/session/decision.",
        )
    service = CanCapService(tenant_id)
    updated = service.review_cap(cap_id, review.model_dump(), user)
    if not updated:
        raise HTTPException(status_code=404, detail="CAP not found")
    return _to_cap_response(updated)


@router.patch("/caps/{cap_id}/status", response_model=dict)
async def update_cap_status(
    cap_id: str,
    status: CAPStatus,
    user: Dict[str, Any] = Depends(get_responsible_manager),
):
    if not user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Tenant access required")
    # CAAN inspectors hold READ-ONLY access to operator records
    # (Headway audit / CAR-19 oversight: aggregate analytics only).
    if str(user.get("role") or "") in ("CAAN_SMD", "CAAN_INSPECTOR"):
        raise HTTPException(
            status_code=403,
            detail="CAAN inspectors have READ-ONLY access to operator CAN/CAP records",
        )
    tenant_id = user["tenant_id"]
    service = CanCapService(tenant_id)
    updated = service.update_cap(cap_id, {"status": status.value}, user)
    if not updated:
        raise HTTPException(status_code=404, detail="CAP not found")
    return _to_cap_response(updated)


# ─── Response Helpers ───

def _to_can_response(data: dict) -> dict:
    return {
        "id": data.get("id", ""),
        "can_reference": data.get("can_reference", ""),
        "hazard_id": data.get("hazard_id", ""),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "required_action": data.get("required_action", ""),
        "issued_by": data.get("issued_by", ""),
        "issued_by_uid": data.get("issued_by_uid", ""),
        "issued_at": data.get("issued_at"),
        "target_completion_date": data.get("target_completion_date"),
        "assigned_to": data.get("assigned_to", ""),
        "assigned_to_uid": data.get("assigned_to_uid", ""),
        "department": data.get("department"),
        "priority": data.get("priority", ""),
        "status": data.get("status", "Open"),
        "tenant_id": data.get("tenant_id", ""),
        "created_by": data.get("created_by"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "latest_cap": data.get("latest_cap"),
        # Buddha Air FORM SMSM 8.8.2 fields
        "copies_to": data.get("copies_to"),
        "requested_function": data.get("requested_function"),
        "addressed_function": data.get("addressed_function"),
        "initial_severity": data.get("initial_severity"),
        "initial_probability": data.get("initial_probability"),
        "initial_risk_index": data.get("initial_risk_index"),
        "initial_risk_level": data.get("initial_risk_level"),
        "initial_risk_outcome": data.get("initial_risk_outcome"),
        "initial_tolerability_tier": data.get("initial_tolerability_tier"),
        "initial_sra": data.get("initial_sra"),
        "classification_type": data.get("classification_type"),
        "classification_level": data.get("classification_level"),
        "process_owner": data.get("process_owner"),
        "rca": data.get("rca"),
        "residual_severity": data.get("residual_severity"),
        "residual_probability": data.get("residual_probability"),
        "residual_risk_index": data.get("residual_risk_index"),
        "residual_risk_level": data.get("residual_risk_level"),
        "residual_risk_outcome": data.get("residual_risk_outcome"),
        "residual_tolerability_tier": data.get("residual_tolerability_tier"),
        "residual_sra": data.get("residual_sra"),
        "root_causes": data.get("root_causes"),
        "action_items": data.get("action_items"),
        "sag_sign": data.get("sag_sign"),
        "sag_signed_by": data.get("sag_signed_by"),
        "sag_signed_at": data.get("sag_signed_at"),
        "manager_approval": data.get("manager_approval"),
        "ca_acceptance": data.get("ca_acceptance"),
        "manager_confirmation": data.get("manager_confirmation"),
        "closing_remarks": data.get("closing_remarks"),
        "closed_by": data.get("closed_by"),
        "closed_at": data.get("closed_at"),
        "closed_signature": data.get("closed_signature"),
        # RCA methodology + AE governance escalation
        # RCA methodology + AE governance escalation
        "rca_method": data.get("rca_method"),
        "escalated_to_ae": data.get("escalated_to_ae"),
        "escalated_by": data.get("escalated_by"),
        "escalated_at": data.get("escalated_at"),
        "escalation_reason": data.get("escalation_reason"),
        "ae_signature": data.get("ae_signature"),
        "ae_signed_at": data.get("ae_signed_at"),
        "ae_review_interval_days": data.get("ae_review_interval_days"),
        "ae_review_date": data.get("ae_review_date"),
        "sram_data": data.get("sram_data"),
    }


def _to_can_list_item(data: dict) -> dict:
    return {
        "id": data.get("id", ""),
        "can_reference": data.get("can_reference", ""),
        "hazard_id": data.get("hazard_id", ""),
        "title": data.get("title", ""),
        "priority": data.get("priority", ""),
        "status": data.get("status", "Open"),
        "assigned_to": data.get("assigned_to", ""),
        "department": data.get("department"),
        "target_completion_date": data.get("target_completion_date"),
        "issued_at": data.get("issued_at"),
        "copies_to": data.get("copies_to"),
        "requested_function": data.get("requested_function"),
        "addressed_function": data.get("addressed_function"),
        "initial_severity": data.get("initial_severity"),
        "initial_probability": data.get("initial_probability"),
        "initial_risk_index": data.get("initial_risk_index"),
        "initial_risk_level": data.get("initial_risk_level"),
        "initial_risk_outcome": data.get("initial_risk_outcome"),
        "initial_tolerability_tier": data.get("initial_tolerability_tier"),
        "initial_sra": data.get("initial_sra"),
        "classification_type": data.get("classification_type"),
        "classification_level": data.get("classification_level"),
    }


def _to_cap_response(data: dict) -> dict:
    return {
        "id": data.get("id", ""),
        "can_id": data.get("can_id", ""),
        "cap_reference": data.get("cap_reference", ""),
        "action_plan": data.get("action_plan", ""),
        "timeline": data.get("timeline", ""),
        "resources_required": data.get("resources_required"),
        "implementation_plan": data.get("implementation_plan"),
        "submitted_by": data.get("submitted_by", ""),
        "submitted_by_uid": data.get("submitted_by_uid", ""),
        "department": data.get("department"),
        "submitted_at": data.get("submitted_at"),
        "target_completion_date": data.get("target_completion_date"),
        "status": data.get("status", "In Progress"),
        "reviewed_by": data.get("reviewed_by"),
        "reviewed_by_uid": data.get("reviewed_by_uid"),
        "reviewed_at": data.get("reviewed_at"),
        "review_comments": data.get("review_comments"),
        "revision_deadline": data.get("revision_deadline"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        # Buddha Air FORM SMSM 8.8.2 fields
        "company_name": data.get("company_name"),
        "base_location": data.get("base_location"),
        "area_system_of_interest": data.get("area_system_of_interest"),
        "finding_number": data.get("finding_number"),
        "file_ref": data.get("file_ref"),
        "factual_review": data.get("factual_review"),
        "rca": data.get("rca"),
        "short_term_ca": data.get("short_term_ca"),
        "long_term_ca": data.get("long_term_ca"),
        "implementation_timeline": data.get("implementation_timeline"),
        "managerial_approval": data.get("managerial_approval"),
        "caa_acceptance": data.get("caa_acceptance"),
        "residual_severity": data.get("residual_severity"),
        "residual_probability": data.get("residual_probability"),
        "residual_risk_index": data.get("residual_risk_index"),
        "residual_risk_level": data.get("residual_risk_level"),
        "residual_risk_outcome": data.get("residual_risk_outcome"),
        "residual_tolerability_tier": data.get("residual_tolerability_tier"),
        "residual_sra": data.get("residual_sra"),
        "root_causes": data.get("root_causes"),
        "action_items": data.get("action_items"),
        "sag_sign": data.get("sag_sign"),
        "sag_signed_by": data.get("sag_signed_by"),
        "sag_signed_at": data.get("sag_signed_at"),
        "manager_approval": data.get("manager_approval"),
        "ca_acceptance": data.get("ca_acceptance"),
        "process_owner": data.get("process_owner"),
        "manager_confirmation": data.get("manager_confirmation"),
        "closing_remarks": data.get("closing_remarks"),
        "closed_by": data.get("closed_by"),
        "closed_at": data.get("closed_at"),
        "closed_signature": data.get("closed_signature"),
    }


def _to_cap_list_item(data: dict) -> dict:
    return {
        "id": data.get("id", ""),
        "can_id": data.get("can_id", ""),
        "can_reference": data.get("can_reference", ""),
        "can_issued_at": data.get("can_issued_at"),
        "hazard_id": data.get("hazard_id", ""),
        "priority": data.get("priority", ""),
        "cap_reference": data.get("cap_reference", ""),
        "action_plan": data.get("action_plan", ""),
        "status": data.get("status", "In Progress"),
        "department": data.get("department"),
        "submitted_by": data.get("submitted_by", ""),
        "submitted_at": data.get("submitted_at"),
        "rca": data.get("rca"),
        "residual_risk_level": data.get("residual_risk_level"),
        "residual_risk_outcome": data.get("residual_risk_outcome"),
        "residual_tolerability_tier": data.get("residual_tolerability_tier"),
        "residual_sra": data.get("residual_sra"),
        "root_causes": data.get("root_causes"),
        "action_items": data.get("action_items"),
        "ca_acceptance": data.get("ca_acceptance"),
        # RCA methodology + AE governance escalation (executive dashboard)
        "rca_method": data.get("rca_method"),
        "escalated_to_ae": data.get("escalated_to_ae"),
        "escalated_by": data.get("escalated_by"),
        "escalated_at": data.get("escalated_at"),
        "escalation_reason": data.get("escalation_reason"),
        "ae_signature": bool(data.get("ae_signature")),
        "ae_review_date": data.get("ae_review_date"),
        # Aggregate barrier health from the persisted Bow-Tie SRAM block
        "barrier_health": _barrier_health_summary(data),
    }


def _barrier_health_summary(data: dict) -> dict:
    """Count barrier health states across the CAP's persisted SRAM block.

    Returns {"effective": n, "degraded": n, "failed": n, "unrated": n} —
    drives the executive Barrier Health Ratio SPI without shipping the full
    sram_data payload in list responses.
    """
    summary = {"effective": 0, "degraded": 0, "failed": 0, "unrated": 0}
    sram = data.get("sram_data") or {}
    barriers = (sram.get("barriers") or {}) if isinstance(sram, dict) else {}
    for key in ("ecb", "erb", "ncb", "nrb"):
        for b in (barriers.get(key) or []):
            rob = str((b or {}).get("robustness") or "").lower()
            if not rob:
                summary["unrated"] += 1
            elif rob in ("excellent", "very good", "good"):
                summary["effective"] += 1
            elif rob == "fair":
                summary["degraded"] += 1
            else:
                summary["failed"] += 1
    return summary
