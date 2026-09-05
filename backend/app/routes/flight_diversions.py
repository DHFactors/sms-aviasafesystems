from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import Dict, Any, Optional, List
from loguru import logger

from app.models.flight_diversion import (
    FlightDiversionCreate, FlightDiversionUpdate, FlightDiversionResponse,
    DiversionStats, DiversionReason, DiversionStatus
)
from app.middleware.auth import get_current_user, get_tenant_user, get_safety_manager, get_admin_user
from app.services.flight_diversion_service import FlightDiversionService
from app.services.audit_service import log_audit, request_context
from app.models.hazard import HazardCreate, HazardSource, HazardTaxonomy, HazardPriority
from app.services.hazard_service import HazardService

router = APIRouter()


_DIVERSION_REASON_TAXONOMY = {
    "Weather": HazardTaxonomy.ENVIRONMENTAL,
    "Technical": HazardTaxonomy.TECHNICAL,
    "Medical": HazardTaxonomy.HUMAN,
    "Fuel": HazardTaxonomy.TECHNICAL,
    "Security": HazardTaxonomy.ORGANIZATIONAL,
    "Operational": HazardTaxonomy.ORGANIZATIONAL,
    "Airport Closure": HazardTaxonomy.ORGANIZATIONAL,
    "Air Traffic Control": HazardTaxonomy.ORGANIZATIONAL,
    "Other": HazardTaxonomy.ORGANIZATIONAL,
}


def _auto_create_hazard_from_diversion(stored: dict, user: dict):
    try:
        tenant_id = stored.get("tenant_id")
        doc_id = stored.get("id")
        diversion_id = stored.get("diversion_id")
        if not tenant_id or not doc_id:
            return None
        reason = stored.get("reason", "")
        taxonomy = _DIVERSION_REASON_TAXONOMY.get(reason, HazardTaxonomy.ORGANIZATIONAL)
        parts = [p for p in [
            stored.get("description"),
            stored.get("reason_details"),
        ] if p and p.strip()]
        description = " ".join(parts).strip() or f"Flight diversion {diversion_id} due to {reason}."
        title = f"Flight Diversion {diversion_id} - {stored.get('flight_number', '')} {stored.get('sector_from', '')}-{stored.get('sector_to', '')} diverted to {stored.get('diverted_to', '')}"

        hazard_payload = HazardCreate(
            title=title[:200],
            description=description,
            source=HazardSource.FLIGHT_DIVERSION,
            source_id=diversion_id,
            source_url=f"/flight_diversions/detail.html?id={doc_id}",
            occurrence_type=f"Flight Diversion - {reason}",
            taxonomy=taxonomy,
            priority=HazardPriority.MEDIUM,
            tenant_id=tenant_id,
        )
        service = HazardService(tenant_id)
        created = service.create_hazard(hazard_payload.model_dump(), user)
        logger.info(f"Auto-created hazard {created.get('hazard_id')} from diversion {diversion_id}")
        if created:
            diversion_service = FlightDiversionService(tenant_id)
            diversion_service.set_hazard_link(
                doc_id,
                created.get("hazard_id"),
                f"/hazards/detail.html?id={created.get('id')}",
                user,
            )
            log_audit(
                action="HAZARD_CREATED",
                user=user.get("email"),
                tenant_id=tenant_id,
                target_type="hazard",
                target_id=created.get("id"),
                metadata={"source": "auto", "source_diversion_id": diversion_id},
            )
        return created
    except Exception as e:
        logger.warning(f"Failed to auto-create hazard from diversion: {e}")
        return None


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_diversion(
    diversion: FlightDiversionCreate,
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    tenant_id = user["tenant_id"]
    service = FlightDiversionService(tenant_id)
    stored = service.create_diversion(diversion.model_dump(), user)
    _auto_create_hazard_from_diversion(stored, user)
    return _to_diversion_response(stored)


@router.get("/", response_model=List[dict])
async def list_diversions(
    status: Optional[str] = Query(None),
    reason: Optional[str] = Query(None),
    aircraft: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    effective_tenant = user.get("tenant_id", "default")
    service = FlightDiversionService(effective_tenant)
    filters = {}
    if status:
        filters["status"] = status
    if reason:
        filters["reason"] = reason
    if aircraft:
        filters["aircraft"] = aircraft
    if search:
        filters["search"] = search

    docs = service.list_diversions(user, filters)
    return [_to_diversion_response(d) for d in docs]


@router.get("/stats", response_model=DiversionStats)
async def get_diversion_stats(
    user: Dict[str, Any] = Depends(get_current_user),
):
    service = FlightDiversionService(user.get("tenant_id", "default"))
    stats = service.get_stats(user)
    return stats


@router.get("/{diversion_id}", response_model=dict)
async def get_diversion(
    diversion_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    effective_tenant = user.get("tenant_id", "default")
    service = FlightDiversionService(effective_tenant)
    doc = service.get_diversion(diversion_id, user)
    if not doc:
        raise HTTPException(status_code=404, detail="Diversion not found")
    return _to_diversion_response(doc)


@router.patch("/{diversion_id}", response_model=dict)
async def update_diversion(
    diversion_id: str,
    data: FlightDiversionUpdate,
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    tenant_id = user["tenant_id"]
    service = FlightDiversionService(tenant_id)
    payload = {k: v for k, v in data.model_dump().items() if v is not None}
    updated = service.update_diversion(diversion_id, payload, user)
    if not updated:
        raise HTTPException(status_code=404, detail="Diversion not found")
    return _to_diversion_response(updated)


@router.delete("/{diversion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_diversion(
    diversion_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    tenant_id = user.get("tenant_id", "default")
    service = FlightDiversionService(tenant_id)
    deleted = service.delete_diversion(diversion_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Diversion not found")
    ip, request_id = request_context(request)
    log_audit(
        action="DIVERSION_DELETED",
        user=user.get("email"),
        tenant_id=tenant_id,
        target_type="flight_diversion",
        target_id=diversion_id,
        ip=ip,
        request_id=request_id,
    )


@router.post("/{diversion_id}/link-hazard", response_model=dict)
async def link_diversion_to_hazard(
    diversion_id: str,
    hazard_id: str = Query(..., min_length=1),
    user: Dict[str, Any] = Depends(get_safety_manager),
):
    if not user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Tenant access required")
    tenant_id = user["tenant_id"]
    service = FlightDiversionService(tenant_id)
    updated = service.link_to_hazard(diversion_id, hazard_id, user)
    if not updated:
        raise HTTPException(status_code=404, detail="Diversion not found")
    return _to_diversion_response(updated)


@router.delete("/{diversion_id}/link-hazard", response_model=dict)
async def unlink_diversion_from_hazard(
    diversion_id: str,
    user: Dict[str, Any] = Depends(get_safety_manager),
):
    if not user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Tenant access required")
    tenant_id = user["tenant_id"]
    service = FlightDiversionService(tenant_id)
    updated = service.unlink_from_hazard(diversion_id, user)
    if not updated:
        raise HTTPException(status_code=404, detail="Diversion not found")
    return _to_diversion_response(updated)


def _to_diversion_response(data: dict) -> dict:
    return {
        "id": data.get("id", ""),
        "tenant_id": data.get("tenant_id", ""),
        "diversion_id": data.get("diversion_id", ""),
        "date": data.get("date"),
        "flight_number": data.get("flight_number", ""),
        "aircraft_registration": data.get("aircraft_registration", ""),
        "sector_from": data.get("sector_from", ""),
        "sector_to": data.get("sector_to", ""),
        "diverted_to": data.get("diverted_to", ""),
        "reason": data.get("reason", ""),
        "reason_details": data.get("reason_details"),
        "captain": data.get("captain"),
        "first_officer": data.get("first_officer"),
        "air_hostess": data.get("air_hostess"),
        "description": data.get("description", ""),
        "additional_fuel_cost": data.get("additional_fuel_cost"),
        "passenger_impact": data.get("passenger_impact"),
        "delay_minutes": data.get("delay_minutes"),
        "remarks": data.get("remarks"),
        "status": data.get("status", "Pending"),
        "hazard_id": data.get("hazard_id"),
        "hazard_link_url": data.get("hazard_link_url"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "created_by": data.get("created_by"),
        "updated_by": data.get("updated_by"),
    }
