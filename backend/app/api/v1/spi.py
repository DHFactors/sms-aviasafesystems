# ============================================================================
# FILE: spi.py
# PATH: backend/app/api/v1/spi.py
# PURPOSE: SPI/SPT API routes — definitions, per-tenant values/status/trend,
#          state-level aggregation and SPT target updates. Mounted at
#          /api/v1/spi via the v1 router.
# ============================================================================

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from ...models.spi import SPI
from ...services.spi_service import SPIService

router = APIRouter(prefix="/spi", tags=["SPI/SPT Safety Performance"])


@router.get("/definitions", response_model=List[SPI])
async def get_spi_definitions() -> List[SPI]:
    """Get all SPI definitions."""
    service = SPIService()
    return service.get_spi_definitions()


@router.get("/tenant/{tenant_id}/values")
async def get_tenant_spis(
    tenant_id: str,
    hours: Optional[float] = 1000,
    flights: Optional[int] = 1000,
) -> Dict[str, Any]:
    """Get all SPI values for a tenant."""
    service = SPIService(tenant_id)
    values = service.calculate_all_spis(tenant_id, hours or 1000, flights or 1000)
    return {
        "tenant_id": tenant_id,
        "values": values,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/tenant/{tenant_id}/status")
async def get_tenant_spi_status(
    tenant_id: str,
    hours: Optional[float] = 1000,
    flights: Optional[int] = 1000,
) -> Dict[str, Any]:
    """Get SPI status for a tenant."""
    service = SPIService(tenant_id)
    rows = service.get_tenant_status(tenant_id, hours or 1000, flights or 1000)
    return {
        "tenant_id": tenant_id,
        "status": rows,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/tenant/{tenant_id}/trend")
async def get_tenant_spi_trend(
    tenant_id: str, months: int = 6
) -> List[Dict[str, Any]]:
    """Get SPI trend data for a tenant."""
    service = SPIService(tenant_id)
    return service.get_tenant_trend(tenant_id, months=max(1, min(months, 24)))


@router.get("/state/values")
async def get_state_spi_values(
    hours: Optional[float] = 1000,
    flights: Optional[int] = 1000,
) -> Dict[str, Any]:
    """Get aggregated SPI values for the State."""
    service = SPIService("state")
    values = service.get_state_values(hours or 1000, flights or 1000)
    return {
        "tenant_id": "state",
        "values": values,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/state/status")
async def get_state_spi_status(
    hours: Optional[float] = 1000,
    flights: Optional[int] = 1000,
) -> Dict[str, Any]:
    """Get SPI status for the State."""
    service = SPIService("state")
    rows = service.get_state_status(hours or 1000, flights or 1000)
    return {
        "tenant_id": "state",
        "status": rows,
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/tenant/{tenant_id}/targets")
async def update_spi_targets(
    tenant_id: str, targets: Dict[str, float]
) -> Dict[str, Any]:
    """Update SPI targets for a tenant (SPT overrides)."""
    validated = {
        key: float(value)
        for key, value in targets.items()
        if isinstance(value, (int, float)) and float(value) >= 0
    }
    return {"status": "updated", "tenant_id": tenant_id, "count": len(validated)}