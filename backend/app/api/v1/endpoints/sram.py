# ============================================================================
# FILE: endpoints/sram.py
# PATH: backend/app/api/v1/endpoints/sram.py
# PURPOSE: SRAM - Safety Risk Assessment & Mitigation endpoints (ICAO Annex
#          19 / Doc 9859 / CAAN Chapter 2.3).
#
#   POST   /api/v1/sram/bowtie                    create a Bow-Tie for a hazard
#   GET    /api/v1/sram/bowtie/{hazard_id}        full Bow-Tie for a hazard
#   POST   /api/v1/sram/bowtie/{id}/threat        add a threat
#   POST   /api/v1/sram/bowtie/{id}/consequence   add a consequence
#   POST   /api/v1/sram/bowtie/{id}/control       add a control / barrier
#   POST   /api/v1/sram/risk/calculate            compute + persist risk indices
#   POST   /api/v1/sram/risk/accept               ALARP / accept a risk
#   GET    /api/v1/sram/barriers/{hazard_id}      barrier register for a hazard
#   PATCH  /api/v1/sram/barriers/{barrier_id}     score / update a barrier
#   GET    /api/v1/sram/risk-register/{tenant_id} risk register for a tenant
#
# Error mapping mirrors app/routes: SramNotFoundError -> 404,
# PermissionError -> 403, ValueError -> 422.
# ============================================================================

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.middleware.auth import get_current_user
from app.services import sram_service
from app.services.sram_service import SramNotFoundError

router = APIRouter(prefix="/sram", tags=["SRAM - Safety Risk Assessment & Mitigation"])


# ----------------------------------------------------------------------------
# Request models
# ----------------------------------------------------------------------------

class BowtieCreate(BaseModel):
    hazard_id: str = Field(..., min_length=1, max_length=120)
    top_event: Optional[str] = Field(None, max_length=1000)
    description: Optional[str] = Field(None, max_length=4000)


class ThreatCreate(BaseModel):
    threat: str = Field(..., min_length=1, max_length=1000)
    order: Optional[int] = Field(None, ge=1)
    probability: Optional[int] = Field(None, ge=1, le=5)


class ConsequenceCreate(BaseModel):
    consequence: str = Field(..., min_length=1, max_length=1000)
    severity: str = Field("C", pattern="^[A-E]$")
    order: Optional[int] = Field(None, ge=1)


class ControlCreate(BaseModel):
    control: str = Field(..., min_length=1, max_length=1000)
    control_type: Literal["preventive", "recovery"]
    order: Optional[int] = Field(None, ge=1)
    owner: Optional[str] = Field(None, max_length=200)
    action_by: Optional[str] = Field(None, max_length=200)
    implementation_status: Optional[str] = Field(
        None, pattern="^(not_started|in_progress|implemented|verified)$"
    )
    follow_up_date: Optional[str] = None
    barrier_scores: Optional[Dict[str, Any]] = None


class RiskCalculation(BaseModel):
    hazard_id: str = Field(..., min_length=1, max_length=120)
    probability_current: int = Field(..., ge=1, le=5)
    severity_current: str = Field(..., pattern="^[A-E]$")
    probability_resultant: Optional[int] = Field(None, ge=1, le=5)
    severity_resultant: Optional[str] = Field(None, pattern="^[A-E]$")
    barrier_scores: Optional[Dict[str, Any]] = None


class RiskAcceptance(BaseModel):
    risk_id: Optional[str] = None
    hazard_id: Optional[str] = None
    alarp_justification: str = Field(..., min_length=10, max_length=4000)
    status: Optional[str] = Field(None, pattern="^(open|in_progress|closed)$")
    review_date: Optional[str] = None


class BarrierUpdate(BaseModel):
    implementation_status: Optional[str] = Field(
        None, pattern="^(not_started|in_progress|implemented|verified)$"
    )
    action_by: Optional[str] = Field(None, max_length=200)
    follow_up_date: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=2000)
    barrier_scores: Optional[Dict[str, Any]] = None


# ----------------------------------------------------------------------------
# Dependency helpers
# ----------------------------------------------------------------------------

def _resolve_scope(user: dict, requested_tenant_id: Optional[str] = None) -> str:
    """Tenant slug the request may act on. Cross-tenant roles may target any
    tenant; everyone else is bound to their own."""
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


def _handle_sram_errors(exc: Exception) -> None:
    if isinstance(exc, SramNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    raise exc


# ----------------------------------------------------------------------------
# Bow-Tie
# ----------------------------------------------------------------------------

@router.post("/bowtie", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_bowtie(payload: BowtieCreate, user: dict = Depends(get_current_user)):
    try:
        result = await sram_service.create_bowtie(
            payload.hazard_id, payload.dict(), _resolve_scope(user), user
        )
    except Exception as exc:
        _handle_sram_errors(exc)
    return {"success": True, "data": result}


@router.get("/bowtie/{hazard_id}", response_model=dict)
async def get_bowtie(hazard_id: str, user: dict = Depends(get_current_user)):
    try:
        result = await sram_service.get_bowtie_by_hazard(
            hazard_id, _resolve_scope(user)
        )
    except Exception as exc:
        _handle_sram_errors(exc)
    return {"success": True, "data": result}


@router.post("/bowtie/{bowtie_id}/threat", response_model=dict, status_code=status.HTTP_201_CREATED)
async def add_threat(bowtie_id: str, payload: ThreatCreate, user: dict = Depends(get_current_user)):
    try:
        result = await sram_service.add_threat(
            bowtie_id, payload.threat, _resolve_scope(user),
            order=payload.order, probability=payload.probability,
        )
    except Exception as exc:
        _handle_sram_errors(exc)
    return {"success": True, "data": result}


@router.post("/bowtie/{bowtie_id}/consequence", response_model=dict,
             status_code=status.HTTP_201_CREATED)
async def add_consequence(bowtie_id: str, payload: ConsequenceCreate,
                          user: dict = Depends(get_current_user)):
    try:
        result = await sram_service.add_consequence(
            bowtie_id, payload.consequence, _resolve_scope(user),
            order=payload.order, severity=payload.severity,
        )
    except Exception as exc:
        _handle_sram_errors(exc)
    return {"success": True, "data": result}


@router.post("/bowtie/{bowtie_id}/control", response_model=dict,
             status_code=status.HTTP_201_CREATED)
async def add_control(bowtie_id: str, payload: ControlCreate,
                      user: dict = Depends(get_current_user)):
    try:
        result = await sram_service.add_control(
            bowtie_id, payload.control, payload.control_type, _resolve_scope(user),
            order=payload.order, owner=payload.owner,
            barrier_scores=payload.barrier_scores,
            implementation_status=payload.implementation_status,
            action_by=payload.action_by,
            follow_up_date=payload.follow_up_date,
        )
    except Exception as exc:
        _handle_sram_errors(exc)
    return {"success": True, "data": result}


# ----------------------------------------------------------------------------
# Risk
# ----------------------------------------------------------------------------

@router.post("/risk/calculate", response_model=dict)
async def calculate_risk(payload: RiskCalculation, user: dict = Depends(get_current_user)):
    try:
        result = await sram_service.calculate_risk(
            payload.hazard_id, payload.dict(), _resolve_scope(user)
        )
    except Exception as exc:
        _handle_sram_errors(exc)
    return {"success": True, "data": result}


@router.post("/risk/accept", response_model=dict)
async def accept_risk(payload: RiskAcceptance, user: dict = Depends(get_current_user)):
    if not payload.risk_id and not payload.hazard_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either risk_id or hazard_id",
        )
    try:
        result = await sram_service.accept_risk(
            payload.risk_id or payload.hazard_id or "", payload.dict(),
            _resolve_scope(user), user,
        )
    except Exception as exc:
        _handle_sram_errors(exc)
    return {"success": True, "data": result}


# ----------------------------------------------------------------------------
# Registers
# ----------------------------------------------------------------------------

@router.get("/barriers", response_model=dict)
async def get_all_barriers(user: dict = Depends(get_current_user)):
    try:
        result = await sram_service.get_barriers_all(_resolve_scope(user))
    except Exception as exc:
        _handle_sram_errors(exc)
    return {"success": True, "data": result}


@router.get("/barriers/{hazard_id}", response_model=dict)
async def get_barriers(hazard_id: str, user: dict = Depends(get_current_user)):
    try:
        result = await sram_service.get_barrier_register(
            hazard_id, _resolve_scope(user)
        )
    except Exception as exc:
        _handle_sram_errors(exc)
    return {"success": True, "data": result}


@router.patch("/barriers/{barrier_id}", response_model=dict)
async def update_barrier(barrier_id: str, payload: BarrierUpdate,
                         user: dict = Depends(get_current_user)):
    try:
        result = await sram_service.update_barrier(
            barrier_id, payload.dict(exclude_none=True), _resolve_scope(user)
        )
    except Exception as exc:
        _handle_sram_errors(exc)
    return {"success": True, "data": result}


@router.get("/risk-register/{tenant_id}", response_model=dict)
async def get_risk_register(tenant_id: str, user: dict = Depends(get_current_user)):
    try:
        result = await sram_service.get_risk_register(_resolve_scope(user, tenant_id))
    except Exception as exc:
        _handle_sram_errors(exc)
    return {"success": True, "data": result}