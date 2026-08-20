# ============================================================================
# FILE: psoe.py
# PATH: backend/app/routes/psoe.py
# PURPOSE: PSOE Audit & Surveillance endpoints (Phase 3 Step 2A). Serves the
#          CAAN SMS Procedure Manual Appendix 10 checklist template and manages
#          tenant-scoped surveillance assessments. Assessments are stored in
#          the top-level ``psoe_assessments`` collection (each doc carries
#          ``tenant_id``) so CAAN_SMD can review assessments across operators.
# ============================================================================

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger

from app.core.config import settings
from app.firebase import get_db
from app.middleware.auth import get_current_user, get_safety_manager
from app.models.psoe import (
    PSOEAnswer,
    PSOEAssessment,
    PSOEAssessmentCreate,
    PSOEAssessmentListItem,
    PSOEAssessmentUpdate,
)
from app.services.audit_service import log_audit, request_context
from app.services.psoe_service import (
    TEMPLATE_VERSION,
    load_template,
    score_assessment,
)

router = APIRouter()

PSOE_COLLECTION = "psoe_assessments"


def _coll():
    return get_db().collection(PSOE_COLLECTION)


def _doc_to_assessment(snap) -> PSOEAssessment:
    data = dict(snap.to_dict() or {})
    data["id"] = data.get("id") or snap.id
    responses = data.get("responses") or []
    data["responses"] = [PSOEAnswer.model_validate(r) if isinstance(r, dict) else r for r in responses]
    return PSOEAssessment.model_validate(data)


def _effective_tenant(user: Dict[str, Any], requested: Optional[str]) -> str:
    """Resolve the tenant scope for a request.

    Cross-tenant roles (CAAN_SMD / SUPER_ADMIN) may scope to any tenant or
    browse all; tenant-bound roles are always locked to their own tenant.
    """
    role = user.get("role")
    if role in settings.CROSS_TENANT_ROLES:
        return requested or ""
    user_tenant = user.get("tenant_id")
    if not user_tenant:
        raise HTTPException(status_code=403, detail="Tenant access required")
    if requested and requested != user_tenant:
        raise HTTPException(status_code=403, detail="Cannot access another tenant's assessments")
    return user_tenant


@router.get("/template", response_model=dict)
async def get_template():
    """Return the standard CAAN Appendix 10 surveillance questions + weights."""
    template = load_template()
    return {
        "version": template.version,
        "source": template.source,
        "scoring_scale": template.scoring_scale,
        "total_weight": template.total_weight,
        "components": [c.model_dump() for c in template.components],
    }


@router.get("/assessments", response_model=List[PSOEAssessmentListItem])
async def list_assessments(
    tenant_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List PSOE assessments for the caller's tenant (all tenants for CAAN_SMD)."""
    effective = _effective_tenant(user, tenant_id)
    try:
        docs = _coll().get()
    except Exception as e:
        logger.error(f"Failed to list PSOE assessments: {e}")
        raise HTTPException(status_code=500, detail="Assessment storage unavailable")

    items = []
    for snap in docs:
        data = snap.to_dict() or {}
        if effective and data.get("tenant_id") != effective:
            continue
        if status and data.get("status") != status:
            continue
        items.append(PSOEAssessmentListItem(
            id=data.get("id") or snap.id,
            tenant_id=data.get("tenant_id", ""),
            title=data.get("title", ""),
            status=data.get("status", "draft"),
            department=data.get("department"),
            scope=data.get("scope"),
            template_version=data.get("template_version"),
            overall_score_pct=data.get("overall_score_pct"),
            overall_level=data.get("overall_level"),
            assessment_date=data.get("assessment_date"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        ))
    items.sort(key=lambda i: i.created_at or datetime.min, reverse=True)
    return items


@router.post("/assessments", response_model=PSOEAssessment, status_code=status.HTTP_201_CREATED)
async def create_assessment(
    payload: PSOEAssessmentCreate,
    user: Dict[str, Any] = Depends(get_safety_manager),
):
    """Draft a new PSOE assessment (TENANT_ADMIN / AIRLINE_ADMIN / CAAN_SMD)."""
    if user.get("role") in settings.CROSS_TENANT_ROLES:
        tenant_id = payload.tenant_id or (user.get("tenant_id") or "")
        if not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required for CAAN_SMD assessments")
    else:
        tenant_id = user.get("tenant_id") or ""
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant access required")
        if payload.tenant_id and payload.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="Cannot create assessments for another tenant")

    scores = score_assessment(payload.responses)
    now = datetime.now(timezone.utc)
    doc = {
        "tenant_id": tenant_id,
        "title": payload.title,
        "status": "draft",
        "department": payload.department,
        "scope": payload.scope,
        "auditor_name": payload.auditor_name,
        "assessor_email": payload.assessor_email,
        "assessment_date": payload.assessment_date,
        "template_version": payload.template_version or TEMPLATE_VERSION,
        "responses": [r.model_dump() for r in payload.responses],
        "component_scores": scores["component_scores"],
        "overall_score_pct": scores["overall_score_pct"],
        "overall_level": scores["overall_level"],
        "created_by": user.get("email"),
        "created_by_uid": user.get("uid"),
        "created_at": now,
        "updated_at": now,
        "notes": payload.notes,
    }

    try:
        result = _coll().add(doc)
        doc_id = result[1].id if isinstance(result, tuple) else result.id
        doc["id"] = doc_id
        _coll().document(doc_id).update({"id": doc_id})
    except Exception as e:
        logger.error(f"Failed to persist PSOE assessment: {e}")
        raise HTTPException(status_code=500, detail="Failed to persist assessment")

    log_audit(
        action="PSOE_ASSESSMENT_CREATED",
        user=user.get("email"),
        tenant_id=tenant_id,
        target_type="psoe_assessment",
        target_id=doc_id,
        metadata={"title": payload.title, "status": "draft", "overall_score_pct": scores["overall_score_pct"]},
    )

    return PSOEAssessment.model_validate(doc)


@router.get("/assessments/{assessment_id}", response_model=PSOEAssessment)
async def get_assessment(
    assessment_id: str,
    tenant_id: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Return a single PSOE assessment with its responses and scores."""
    effective = _effective_tenant(user, tenant_id)
    try:
        snap = _coll().document(assessment_id).get()
    except Exception as e:
        logger.error(f"Failed to read PSOE assessment {assessment_id}: {e}")
        raise HTTPException(status_code=500, detail="Assessment storage unavailable")
    if snap is None or not snap.exists:
        raise HTTPException(status_code=404, detail="Assessment not found")

    data = snap.to_dict() or {}
    if effective and data.get("tenant_id") != effective:
        raise HTTPException(status_code=403, detail="Cannot access another tenant's assessment")
    return _doc_to_assessment(snap)


@router.patch("/assessments/{assessment_id}", response_model=PSOEAssessment)
async def update_assessment(
    assessment_id: str,
    payload: PSOEAssessmentUpdate,
    tenant_id: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_safety_manager),
):
    """Update an existing PSOE assessment (TENANT_ADMIN / AIRLINE_ADMIN / CAAN_SMD)."""
    effective = _effective_tenant(user, tenant_id)
    try:
        snap = _coll().document(assessment_id).get()
    except Exception as e:
        logger.error(f"Failed to read PSOE assessment {assessment_id}: {e}")
        raise HTTPException(status_code=500, detail="Assessment storage unavailable")
    if snap is None or not snap.exists:
        raise HTTPException(status_code=404, detail="Assessment not found")

    data = snap.to_dict() or {}
    if effective and data.get("tenant_id") != effective:
        raise HTTPException(status_code=403, detail="Cannot access another tenant's assessment")

    updates: Dict[str, Any] = {}
    for field in ("title", "department", "scope", "auditor_name", "assessor_email",
                  "assessment_date", "status", "notes"):
        if payload.model_fields_set and field in payload.model_fields_set:
            updates[field] = getattr(payload, field)

    if payload.responses is not None:
        updates["responses"] = [r.model_dump() for r in payload.responses]
        scores = score_assessment(payload.responses)
        updates["component_scores"] = scores["component_scores"]
        updates["overall_score_pct"] = scores["overall_score_pct"]
        updates["overall_level"] = scores["overall_level"]

    updates["updated_at"] = datetime.now(timezone.utc)
    try:
        _coll().document(assessment_id).update(updates)
    except Exception as e:
        logger.error(f"Failed to update PSOE assessment {assessment_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update assessment")

    log_audit(
        action="PSOE_ASSESSMENT_UPDATED",
        user=user.get("email"),
        tenant_id=data.get("tenant_id", ""),
        target_type="psoe_assessment",
        target_id=assessment_id,
        metadata={"updated_fields": sorted(updates.keys())},
    )

    merged = dict(data)
    merged.update(updates)
    merged["id"] = assessment_id
    responses = merged.get("responses") or []
    merged["responses"] = [PSOEAnswer.model_validate(r) if isinstance(r, dict) else r for r in responses]
    return PSOEAssessment.model_validate(merged)