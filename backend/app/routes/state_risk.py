# ============================================================================
# FILE: state_risk.py
# PATH: backend/app/routes/state_risk.py
# VERSION: 1.0.0
# DATE CREATED: 2026-08-04
# PURPOSE: State-level risk register endpoints. CAAN_SMD / SUPER_ADMIN view the
#          state risk profile (aggregated across tenants, measured against
#          SSP targets). SUPER_ADMIN maintains SSP targets.
# AUTHOR: Ghanshyam Acharya
# CODE OWNER: AviaSafeSystems
# ============================================================================

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from loguru import logger

from app.middleware.auth import get_caan_user, get_admin_user
from app.services.state_risk_service import StateRiskService

router = APIRouter()


class SspTargetUpdate(BaseModel):
    ssp_target: float = Field(..., description="SSP target for this risk category (1-25 risk index)")
    risk_reduction_rate: Optional[float] = Field(None, description="Targeted annual risk reduction %")


@router.get("/register")
async def get_state_risk_register(
    year: Optional[int] = Query(None, ge=2000, le=2100),
    quarter: Optional[int] = Query(None, ge=1, le=4),
    regulator_id: Optional[str] = Query(None, description="State Regulator id (e.g. caan) to scope the register"),
    user: Dict[str, Any] = Depends(get_caan_user),
):
    """Return the state-level risk register, optionally filtered by period and
    regulator (regulator_id narrows to that regulator's operator tenants)."""
    svc = StateRiskService(user)
    rows = svc.list_register(year=year, quarter=quarter)
    if regulator_id:
        from app.services.regulator_service import operator_tenant_ids_for_regulator
        allowed = set(operator_tenant_ids_for_regulator(regulator_id))
        rows = [r for r in rows if allowed and (set(r.get("contributing_tenants") or []) & allowed)]
    return {"success": True, "count": len(rows), "risks": rows}


@router.get("/aggregate")
async def get_aggregated_state_risk(
    year: int = Query(..., ge=2000, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    regulator_id: Optional[str] = Query(None, description="State Regulator id (e.g. caan) to scope the aggregation"),
    user: Dict[str, Any] = Depends(get_caan_user),
):
    """Aggregate risk across tenants by ICAO category (live computation, not
    yet persisted). When `regulator_id` is provided the aggregation is scoped
    to that State Regulator's operators."""
    svc = StateRiskService(user)
    return {"success": True, **svc.aggregate_state_risk(year, quarter, regulator_id=regulator_id)}


@router.post("/sync")
async def sync_state_risk_register(
    year: int = Query(..., ge=2000, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    regulator_id: Optional[str] = Query(None, description="State Regulator id (e.g. caan) to scope the sync"),
    user: Dict[str, Any] = Depends(get_caan_user),
):
    """Persist the aggregated state risk into the state risk register,
    carrying over existing SSP targets where present."""
    svc = StateRiskService(user)
    result = svc.sync_register_from_aggregation(year, quarter, regulator_id=regulator_id)
    logger.info(f"State risk register synced for {year}Q{quarter} by {user.get('uid')}")
    return {"success": True, **result}


@router.put("/register/{risk_id}/ssp-target")
async def update_ssp_target(
    risk_id: str,
    body: SspTargetUpdate,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Set the SSP target for a risk category (SUPER_ADMIN only)."""
    svc = StateRiskService(user)
    updated = svc.update_ssp_target(risk_id, body.ssp_target, body.risk_reduction_rate)
    if not updated:
        raise HTTPException(status_code=404, detail="Risk register entry not found")
    logger.info(f"SSP target updated for {risk_id} by {user.get('uid')}")
    return {"success": True, "risk": updated}
