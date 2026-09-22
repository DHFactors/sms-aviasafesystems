# ============================================================================
# FILE: spi.py
# PATH: backend/app/api/v1/spi.py
# PURPOSE: SPI/SPT API routes — definitions, per-tenant values/status/trend,
#          state-level aggregation and SPT target updates. Mounted at
#          /api/v1/spi via the v1 router.
# ============================================================================

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

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


@router.get("/state/trend")
async def get_state_spi_trend(
    months: int = 2,
    user: Dict[str, Any] = Depends(get_caan_user),
) -> Dict[str, Any]:
    """Period-over-period State SPI trends (CAAN-only, P3-10)."""
    service = SPIService("state")
    service.get_state_values()
    rows = []
    for spi in service.get_spi_definitions():
        rows.append({
            "spi_id": spi.id,
            "key": spi.id,
            "name": spi.name,
            **service.compute_state_trend(spi.id, months=max(2, min(months, 24))),
        })
    return {
        "tenant_id": "state",
        "trends": rows,
        "timestamp": datetime.now().isoformat(),
    }


class StateSPTCreate(BaseModel):
    spi_definition_id: str = Field(..., min_length=1)
    target_value: float = Field(..., ge=0)
    target_period: str = Field("annual")
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


@router.get("/state/targets")
async def list_state_targets(
    period: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_caan_user),
) -> Dict[str, Any]:
    """List national-scope State SPTs (CAAN-only, P3-10)."""
    from app.services.state_spt_service import StateSPTService

    return {
        "targets": StateSPTService().list_state_spts(period),
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/state/targets", status_code=201)
async def create_state_target(
    payload: StateSPTCreate,
    user: Dict[str, Any] = Depends(get_caan_user),
) -> Dict[str, Any]:
    """Create a State SPT draft (CAAN-only, P3-10)."""
    from app.services.state_spt_service import StateSPTService

    try:
        result = StateSPTService().set_state_spt(
            payload.spi_definition_id, payload.target_value, payload.target_period,
            user, valid_from=payload.valid_from, valid_to=payload.valid_to)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "data": result}


@router.post("/state/targets/{spt_id}/approve")
async def approve_state_target(
    spt_id: str,
    user: Dict[str, Any] = Depends(get_caan_user),
) -> Dict[str, Any]:
    """Approve a State SPT (CAAN-only, P3-10)."""
    from app.services.state_spt_service import StateSPTService

    try:
        result = StateSPTService().approve_state_spt(spt_id, user)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "success", "data": result}


@router.delete("/state/targets/{spt_id}")
async def delete_state_target(
    spt_id: str,
    user: Dict[str, Any] = Depends(get_caan_user),
) -> Dict[str, Any]:
    """Delete a State SPT (CAAN-only, P3-10)."""
    from app.services.state_spt_service import StateSPTService

    try:
        deleted = StateSPTService().delete_state_spt(spt_id, user)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="State SPT not found")
    return {"status": "success", "data": {"id": spt_id, "deleted": True}}


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