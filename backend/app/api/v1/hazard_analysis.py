# ==============================================================================
# File: backend/app/api/v1/hazard_analysis.py
# Description: FastAPI routes for multi-tenant Hazard Logging, Risk Matrix scoring,
#              HFACS 7.0 Nanocode Tagging, and CAPA creation.
# ==============================================================================

from fastapi import APIRouter, Depends, Header, HTTPException, status
from typing import List, Optional
from app.schemas.hazard_rca import (
    HazardCreate,
    RCAFactorCreate,
    RiskAssessmentCreate,
    CAPACreate,
)
from app.services.hazard_service import HazardService
from app.firebase import get_firestore_db

router = APIRouter(prefix="/hazards", tags=["Hazard & RCA Analysis"])


def get_hazard_service(db=Depends(get_firestore_db)) -> HazardService:
    return HazardService(db=db)


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_new_hazard(
    payload: HazardCreate,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    service: HazardService = Depends(get_hazard_service)
):
    """Creates a new tracked hazard in the tenant's safety registry."""
    user_info = {"email": f"safety@{x_tenant_id}.com.np", "name": "Safety Officer"}
    hazard_id = await service.create_hazard(x_tenant_id, payload.dict(), user_info)
    return {"status": "success", "hazard_id": hazard_id}


@router.post("/{hazard_id}/rca", response_model=dict, status_code=status.HTTP_201_CREATED)
async def attach_hfacs_rca(
    hazard_id: str,
    payload: RCAFactorCreate,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    service: HazardService = Depends(get_hazard_service)
):
    """Tags a specific DoD HFACS 7.0 nanocode factor to the hazard analysis."""
    factor_id = await service.add_rca_factor(x_tenant_id, hazard_id, payload.dict())
    return {"status": "success", "factor_id": factor_id}


@router.post("/{hazard_id}/assessments", response_model=dict, status_code=status.HTTP_201_CREATED)
async def record_risk_matrix_assessment(
    hazard_id: str,
    payload: RiskAssessmentCreate,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    service: HazardService = Depends(get_hazard_service)
):
    """Records an ICAO 5x5 initial or residual safety risk matrix evaluation."""
    assessor = f"safety@{x_tenant_id}.com.np"
    res = await service.record_assessment(x_tenant_id, hazard_id, payload.dict(), assessor)
    return {"status": "success", "assessment": res}


@router.post("/{hazard_id}/capas", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_hazard_capa(
    hazard_id: str,
    payload: CAPACreate,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    service: HazardService = Depends(get_hazard_service)
):
    """Assigns a corrective and preventive action mitigating the root cause."""
    capa_id = await service.add_capa(x_tenant_id, hazard_id, payload.dict())
    return {"status": "success", "capa_id": capa_id}