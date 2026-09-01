# ============================================================================
# FILE: nhrc.py
# PATH: backend/app/api/v1/nhrc.py
# PURPOSE: N-HRC (National High-Risk Category) API routes — tenant KPIs,
#          State (CAAN) aggregated KPIs, mapping rules, and NASP SEI /
#          contributing-factor lookups. Mounted at /api/v1/nhrc via the v1
#          router.
# ============================================================================

from fastapi import APIRouter
from typing import List

from ...services.nhrc_service import NHRCService, NHRC_MAPPING_RULES
from ...models.nhrc import NHRCKPI, NHRCCategory, NHRCMappingRule

router = APIRouter(prefix="/nhrc", tags=["N-HRC National High-Risk Categories"])


@router.get("/tenant/{tenant_id}/kpis", response_model=List[NHRCKPI])
async def get_tenant_nhrc_kpis(tenant_id: str) -> List[NHRCKPI]:
    """
    Get N-HRC KPIs for a specific tenant.
    """
    service = NHRCService(tenant_id)
    return service.calculate_nhrc_kpis(tenant_id)


@router.get("/state/kpis", response_model=List[NHRCKPI])
async def get_state_nhrc_kpis() -> List[NHRCKPI]:
    """
    Get aggregated N-HRC KPIs for the State (CAAN view).
    """
    service = NHRCService()
    return service.calculate_state_nhrc_kpis()


@router.get("/mapping-rules", response_model=List[NHRCMappingRule])
async def get_mapping_rules() -> List[NHRCMappingRule]:
    """
    Get all N-HRC mapping rules.
    """
    return NHRC_MAPPING_RULES


@router.get("/seis/{nhrc}", response_model=List[str])
async def get_nhrc_seis(nhrc: NHRCCategory) -> List[str]:
    """
    Get SEIs for a specific N-HRC.
    """
    service = NHRCService()
    return service.get_nhrc_seis(nhrc)


@router.get("/contributing-factors/{nhrc}", response_model=List[str])
async def get_contributing_factors(nhrc: NHRCCategory) -> List[str]:
    """
    Get contributing factors for a specific N-HRC.
    """
    service = NHRCService()
    return service.get_contributing_factors(nhrc)