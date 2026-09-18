# ============================================================================
# FILE: spi.py
# PATH: backend/app/api/v1/spi.py
# PURPOSE: SPI/SPT API routes — definitions, per-tenant values/status/trend,
#          state-level aggregation and SPT target updates. Mounted at
#          /api/v1/spi via the v1 router.
# ============================================================================

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import settings
from app.middleware.auth import get_caan_user, get_current_user
from ...models.spi import SPI
from ...services.spi_service import SPIService

router = APIRouter(prefix="/spi", tags=["SPI/SPT Safety Performance"])


def require_tenant_access(user: Dict[str, Any], tenant_id: str) -> None:
    """Gate a /tenant/{tenant_id}/... route to the caller's own tenant.

    Cross-tenant roles (CAAN_SMD / SUPER_ADMIN, see settings.CROSS_TENANT_ROLES)
    may access any tenant; any other role is limited to their own tenant_id.
    Shared by the SPI and N-HRC v1 routers for both reads (GET values/status/
    trend, N-HRC KPIs) and writes (SPT target updates). Mirrors the tenant-scope
    checks in routes/tenants.py (_require_tenant_admin / _require_tenant_viewer).
    """
    if user.get("role") in settings.CROSS_TENANT_ROLES:
        return
    if user.get("tenant_id") != tenant_id:
        raise HTTPException(
            status_code=403,
            detail="tenantId does not match the authenticated user's tenant",
        )


@router.get("/definitions", response_model=List[SPI])
async def get_spi_definitions(
    user: Dict[str, Any] = Depends(get_current_user),
) -> List[SPI]:
    """Get all SPI definitions."""
    service = SPIService()
    return service.get_spi_definitions()


@router.get("/tenant/{tenant_id}/values")
async def get_tenant_spis(
    tenant_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
    hours: Optional[float] = 1000,
    flights: Optional[int] = 1000,
) -> Dict[str, Any]:
    """Get all SPI values for a tenant."""
    require_tenant_access(user, tenant_id)
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
    user: Dict[str, Any] = Depends(get_current_user),
    hours: Optional[float] = 1000,
    flights: Optional[int] = 1000,
) -> Dict[str, Any]:
    """Get SPI status for a tenant."""
    require_tenant_access(user, tenant_id)
    service = SPIService(tenant_id)
    rows = service.get_tenant_status(tenant_id, hours or 1000, flights or 1000)
    return {
        "tenant_id": tenant_id,
        "status": rows,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/tenant/{tenant_id}/trend")
async def get_tenant_spi_trend(
    tenant_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
    months: int = 6,
) -> List[Dict[str, Any]]:
    """Get SPI trend data for a tenant."""
    require_tenant_access(user, tenant_id)
    service = SPIService(tenant_id)
    return service.get_tenant_trend(tenant_id, months=max(1, min(months, 24)))


@router.get("/state/values")
async def get_state_spi_values(
    user: Dict[str, Any] = Depends(get_caan_user),
    hours: Optional[float] = 1000,
    flights: Optional[int] = 1000,
) -> Dict[str, Any]:
    """Get aggregated SPI values for the State (CAAN-only, regulator scope)."""
    service = SPIService("state")
    values = service.get_state_values(hours or 1000, flights or 1000)
    return {
        "tenant_id": "state",
        "values": values,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/state/status")
async def get_state_spi_status(
    user: Dict[str, Any] = Depends(get_caan_user),
    hours: Optional[float] = 1000,
    flights: Optional[int] = 1000,
) -> Dict[str, Any]:
    """Get SPI status for the State (CAAN-only, regulator scope)."""
    service = SPIService("state")
    rows = service.get_state_status(hours or 1000, flights or 1000)
    return {
        "tenant_id": "state",
        "status": rows,
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/tenant/{tenant_id}/targets")
async def update_spi_targets(
    tenant_id: str,
    targets: Dict[str, float],
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Update SPI targets for a tenant (SPT overrides)."""
    require_tenant_access(user, tenant_id)
    validated = {
        key: float(value)
        for key, value in targets.items()
        if isinstance(value, (int, float)) and float(value) >= 0
    }
    return {"status": "updated", "tenant_id": tenant_id, "count": len(validated)}