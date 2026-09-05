# ============================================================================
# FILE: endpoints/psoe.py
# PATH: backend/app/api/v1/endpoints/psoe.py
# PURPOSE: CAAN PSOE (Post Safety Oversight Evaluation) - Appendix 10
#          surveillance module (SUPABASE/PostgreSQL implementation).
#
#          Module prefix: /psoe  (registered by router.py under /supabase,
#          giving /api/v1/supabase/psoe/* — a rename-safe namespace so it can
#          later take over the legacy /api/v1/psoe/* Firestore routes).
#
#   GET    /assessments                    list (filter: status, tenant_id)
#   POST   /assessments                    create draft assessment
#   GET    /assessments/{id}               assessment + findings
#   PUT    /assessments/{id}               save response set
#   POST   /assessments/{id}/calculate     compute component/overall scores
#   POST   /assessments/{id}/complete      finalise assessment
#   POST   /assessments/{id}/findings      add finding
#   PUT    /findings/{id}                  update finding
#   DELETE /findings/{id}                  delete finding
#   GET    /assessments/{id}/report        HTML surveillance report
#   GET    /questions                      question bank (21 questions)
#
# Access matrix (user-defined): Super Admin = config; State Regulator + Tenant
# Auditor = full access; Accountable Manager + Safety Manager = view-only.
# Error mapping mirrors app/routes: PsoeNotFoundError -> 404,
# PermissionError -> 403, ValueError -> 422.
# ============================================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.middleware.auth import get_current_user
from app.services import psoe_complete_service
from app.services.psoe_complete_service import (
    FINDING_STATUSES,
    FINDING_TYPES,
    PsoeNotFoundError,
)

router = APIRouter(prefix="/psoe", tags=["PSOE - Post Safety Oversight Evaluation"])

# Roles allowed to mutate assessments/findings (full access):
# regulator (CAAN_SMD / CAAN_ADMIN), auditor (CAAN_AUDITOR), super admin.
_EDIT_ROLES = frozenset(settings.CROSS_TENANT_ROLES)
_EDIT_ROLES = _EDIT_ROLES.union(settings.SUPER_ADMIN_ROLES).union(
    {"CAAN_ADMIN", "CAAN_AUDITOR"}
)


# ----------------------------------------------------------------------------
# Request models
# ----------------------------------------------------------------------------

class AssessmentCreate(BaseModel):
    title: Optional[str] = Field(None, max_length=300)
    department: Optional[str] = Field(None, max_length=200)
    scope: Optional[str] = Field(None, max_length=2000)
    auditor_name: Optional[str] = Field(None, max_length=200)
    assessor_email: Optional[str] = Field(None, max_length=320)
    assessment_date: Optional[str] = None
    template_version: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=4000)


class ResponsesUpdate(BaseModel):
    responses: Union[List[Dict[str, Any]], Dict[str, Any]] = Field(...)


class FindingCreate(BaseModel):
    finding_type: Optional[str] = Field(None, max_length=50)
    description: str = Field(..., min_length=1, max_length=5000)
    corrective_action: Optional[str] = Field(None, max_length=5000)
    status: Optional[str] = Field(None, max_length=50)
    target_date: Optional[str] = None
    closed_date: Optional[str] = None


class FindingUpdate(BaseModel):
    finding_type: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, min_length=1, max_length=5000)
    corrective_action: Optional[str] = Field(None, max_length=5000)
    status: Optional[str] = Field(None, max_length=50)
    target_date: Optional[str] = None
    closed_date: Optional[str] = None


# ----------------------------------------------------------------------------
# Dependency helpers
# ----------------------------------------------------------------------------

def _resolve_scope(user: dict, requested_tenant_id: Optional[str] = None) -> str:
    """Tenant slug the request may act on. Regulator / super-admin roles may
    target any tenant; everyone else is bound to their own."""
    user_tenant = (user or {}).get("tenant_id")
    if requested_tenant_id and requested_tenant_id != user_tenant:
        role = (user or {}).get("role")
        if role not in settings.CROSS_TENANT_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-tenant access requires a regulator or super admin role",
            )
        return requested_tenant_id
    if not user_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not scoped to a tenant",
        )
    return user_tenant


def _require_editor(user: dict) -> None:
    if (user or {}).get("role") not in _EDIT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Full PSOE access requires a regulator (CAAN) or super admin role",
        )


def _handle_psoe_errors(exc: Exception) -> None:
    if isinstance(exc, PsoeNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    raise exc


# ----------------------------------------------------------------------------
# Questions
# ----------------------------------------------------------------------------

@router.get("/questions", response_model=dict)
async def get_questions(user: dict = Depends(get_current_user)):
    """Question bank: 4 components x (5/5/6/5) = 21 questions."""
    try:
        result = await psoe_complete_service.get_questions()
    except Exception as exc:
        _handle_psoe_errors(exc)
    return {"success": True, "data": result}


# ----------------------------------------------------------------------------
# Assessments
# ----------------------------------------------------------------------------

@router.get("/assessments", response_model=dict)
async def list_assessments(
    status_filter: Optional[str] = Query(None, alias="status", max_length=50),
    tenant_id: Optional[str] = Query(None, max_length=120),
    user: dict = Depends(get_current_user),
):
    """List assessments for the user's tenant (optionally a target tenant for
    regulator / super admin roles)."""
    try:
        result = await psoe_complete_service.list_assessments(
            _resolve_scope(user, tenant_id), status=status_filter
        )
    except Exception as exc:
        _handle_psoe_errors(exc)
    return {"success": True, "data": result}


@router.post("/assessments", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_assessment(payload: AssessmentCreate, user: dict = Depends(get_current_user)):
    _require_editor(user)
    try:
        result = await psoe_complete_service.create_assessment(
            payload.dict(exclude_none=True), _resolve_scope(user), user
        )
    except Exception as exc:
        _handle_psoe_errors(exc)
    return {"success": True, "data": result}


@router.get("/assessments/{assessment_id}", response_model=dict)
async def get_assessment(assessment_id: str, user: dict = Depends(get_current_user)):
    try:
        result = await psoe_complete_service.get_assessment(
            assessment_id, _resolve_scope(user)
        )
    except Exception as exc:
        _handle_psoe_errors(exc)
    return {"success": True, "data": result}


@router.put("/assessments/{assessment_id}", response_model=dict)
async def save_responses(assessment_id: str, payload: ResponsesUpdate,
                         user: dict = Depends(get_current_user)):
    _require_editor(user)
    try:
        result = await psoe_complete_service.save_responses(
            assessment_id, payload.responses, _resolve_scope(user)
        )
    except Exception as exc:
        _handle_psoe_errors(exc)
    return {"success": True, "data": result}


@router.post("/assessments/{assessment_id}/calculate", response_model=dict)
async def calculate_scores(assessment_id: str, user: dict = Depends(get_current_user)):
    _require_editor(user)
    try:
        result = await psoe_complete_service.calculate_scores(
            assessment_id, _resolve_scope(user)
        )
    except Exception as exc:
        _handle_psoe_errors(exc)
    return {"success": True, "data": result}


@router.post("/assessments/{assessment_id}/complete", response_model=dict)
async def complete_assessment(assessment_id: str, user: dict = Depends(get_current_user)):
    _require_editor(user)
    try:
        result = await psoe_complete_service.complete_assessment(
            assessment_id, _resolve_scope(user), user
        )
    except Exception as exc:
        _handle_psoe_errors(exc)
    return {"success": True, "data": result}


@router.get("/assessments/{assessment_id}/report", response_model=dict)
async def generate_report(assessment_id: str, user: dict = Depends(get_current_user)):
    try:
        result = await psoe_complete_service.generate_report(
            assessment_id, _resolve_scope(user)
        )
    except Exception as exc:
        _handle_psoe_errors(exc)
    return {"success": True, "data": result}


# ----------------------------------------------------------------------------
# Findings
# ----------------------------------------------------------------------------

@router.post("/assessments/{assessment_id}/findings", response_model=dict,
             status_code=status.HTTP_201_CREATED)
async def add_finding(assessment_id: str, payload: FindingCreate,
                      user: dict = Depends(get_current_user)):
    _require_editor(user)
    try:
        result = await psoe_complete_service.add_finding(
            assessment_id, payload.dict(exclude_none=True), _resolve_scope(user), user
        )
    except Exception as exc:
        _handle_psoe_errors(exc)
    return {"success": True, "data": result}


@router.put("/findings/{finding_id}", response_model=dict)
async def update_finding(finding_id: str, payload: FindingUpdate,
                         user: dict = Depends(get_current_user)):
    _require_editor(user)
    try:
        result = await psoe_complete_service.update_finding(
            finding_id, payload.dict(exclude_none=True), _resolve_scope(user)
        )
    except Exception as exc:
        _handle_psoe_errors(exc)
    return {"success": True, "data": result}


@router.delete("/findings/{finding_id}", response_model=dict)
async def delete_finding(finding_id: str, user: dict = Depends(get_current_user)):
    _require_editor(user)
    try:
        result = await psoe_complete_service.delete_finding(
            finding_id, _resolve_scope(user)
        )
    except Exception as exc:
        _handle_psoe_errors(exc)
    return {"success": True, "data": result}