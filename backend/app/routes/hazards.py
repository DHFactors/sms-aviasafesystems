from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import Dict, Any, Optional, List
from loguru import logger

from app.models.hazard import HazardCreate, HazardUpdate, HazardResponse, HazardListItem, HazardStatus, HazardSource, HazardTaxonomy, HAZARD_CREATION_SOURCES
from app.middleware.auth import get_current_user, get_tenant_user, get_safety_manager
from app.services.hazard_service import HazardService
from app.services.audit_service import log_audit, request_context

router = APIRouter()


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_hazard(
    hazard: HazardCreate,
    request: Request,
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    tenant_id = user["tenant_id"]
    source_value = hazard.source.value if hasattr(hazard.source, "value") else str(hazard.source)
    if source_value not in HAZARD_CREATION_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Source '{source_value}' is not allowed. Allowed sources: {', '.join(sorted(HAZARD_CREATION_SOURCES))}. "
                   f"Note: safety reports (VSR/MOR) and flight diversions are auto-registered from their registers.",
        )
    service = HazardService(tenant_id)
    payload = hazard.model_dump()
    payload["tenant_id"] = tenant_id
    stored = service.create_hazard(payload, user)
    ip, request_id = request_context(request)
    log_audit(
        action="HAZARD_CREATED",
        user=user.get("email"),
        tenant_id=tenant_id,
        target_type="hazard",
        target_id=stored.get("id"),
        ip=ip,
        request_id=request_id,
        metadata={"source": source_value},
    )
    return _to_hazard_response(stored)


@router.get("/", response_model=List[HazardListItem])
async def list_hazards(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    taxonomy: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    svc_user = user
    effective_tenant = user.get("tenant_id")
    if user.get("role") in ["CAAN_SMD", "SUPER_ADMIN"] and tenant_id:
        effective_tenant = tenant_id

    service = HazardService(effective_tenant)
    filters = {}
    if status:
        filters["status"] = status
    if priority:
        filters["priority"] = priority
    if source:
        filters["source"] = source
    if taxonomy:
        filters["taxonomy"] = taxonomy
    if department:
        filters["department"] = department
    if search:
        filters["search"] = search
    if tenant_id and user.get("role") in ["CAAN_SMD", "SUPER_ADMIN"]:
        filters["tenant_id"] = tenant_id

    docs = service.list_hazards(svc_user, filters)
    return [_to_list_item(d) for d in docs]


@router.get("/stats", response_model=dict)
async def get_hazard_stats(
    user: Dict[str, Any] = Depends(get_current_user),
):
    service = HazardService(user.get("tenant_id", "default"))
    stats = service.get_hazard_stats(user)
    return stats


@router.get("/{hazard_id}", response_model=dict)
async def get_hazard(
    hazard_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    effective_tenant = user.get("tenant_id", "default")
    service = HazardService(effective_tenant)
    doc = service.get_hazard_by_id(hazard_id, user)
    if not doc:
        raise HTTPException(status_code=404, detail="Hazard not found")
    return _to_hazard_response(doc)


@router.put("/{hazard_id}", response_model=dict)
async def update_hazard(
    hazard_id: str,
    data: HazardUpdate,
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    tenant_id = user["tenant_id"]
    service = HazardService(tenant_id)
    payload = {k: v for k, v in data.model_dump().items() if v is not None}
    if payload.get("source"):
        source_value = payload["source"].value if hasattr(payload["source"], "value") else str(payload["source"])
        if source_value not in HAZARD_CREATION_SOURCES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Source '{source_value}' is not allowed. Allowed sources: {', '.join(sorted(HAZARD_CREATION_SOURCES))}.",
            )
    updated = service.update_hazard(hazard_id, payload, user)
    if not updated:
        raise HTTPException(status_code=404, detail="Hazard not found")
    return _to_hazard_response(updated)


@router.patch("/{hazard_id}/status", response_model=dict)
async def update_hazard_status(
    hazard_id: str,
    status: HazardStatus,
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    tenant_id = user["tenant_id"]
    service = HazardService(tenant_id)
    updated = service.update_status(hazard_id, status.value, user)
    if not updated:
        raise HTTPException(status_code=404, detail="Hazard not found")
    return _to_hazard_response(updated)


@router.patch("/{hazard_id}/assign", response_model=dict)
async def assign_hazard(
    hazard_id: str,
    assigned_to: str,
    assigned_to_uid: str,
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    tenant_id = user["tenant_id"]
    service = HazardService(tenant_id)
    updated = service.assign_hazard(hazard_id, assigned_to, assigned_to_uid, user)
    if not updated:
        raise HTTPException(status_code=404, detail="Hazard not found")
    return _to_hazard_response(updated)


_VALID_SOURCES = {s.value for s in HazardSource}
_VALID_TAXONOMIES = {t.value for t in HazardTaxonomy}


def _normalize_source(value):
    if value in _VALID_SOURCES:
        return value
    return "Internal Audit"


def _normalize_taxonomy(value, occurrence_category=None):
    if value in _VALID_TAXONOMIES:
        return value
    taxonomy_map = {
        "BIRD": "Wildlife",
        "FIRE": "Technical",
        "ENG": "Technical",
        "SYS": "Technical",
        "MAC": "Technical",
        "CFIT": "Organizational-Facilities",
        "GCOL": "Organizational-Facilities",
        "RI": "Organizational-Facilities",
        "RE": "Organizational-Facilities",
        "LOCI": "Organizational-Facilities",
        "CABIN": "Human Factors",
        "PRO": "Organizational-Documentation, Processes and Procedures",
        "ARC": "Organizational-Documentation, Processes and Procedures",
        "WX": "Environmental",
    }
    mapped = taxonomy_map.get((occurrence_category or value or "").upper())
    return mapped or "Other"


def _normalize_priority(value):
    if value in ("H", "M", "L"):
        return value
    return "M"


def _to_hazard_response(data: dict) -> dict:
    return {
        "id": data.get("id", ""),
        "hazard_id": data.get("hazard_id", ""),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "source": _normalize_source(data.get("source", "")),
        "source_id": data.get("source_id"),
        "source_url": data.get("source_url"),
        "adrep_category": data.get("adrep_category"),
        "occurrence_type": data.get("occurrence_type"),
        "taxonomy": _normalize_taxonomy(data.get("taxonomy", ""), data.get("occurrence_category")),
        "taxonomy_specific": data.get("taxonomy_specific"),
        "consequence": data.get("consequence"),
        "severity": data.get("severity"),
        "probability": data.get("probability"),
        "risk_index": data.get("risk_index"),
        "risk_level": data.get("risk_level"),
        "risk_outcome": data.get("risk_outcome"),
        "priority": _normalize_priority(data.get("priority", "")),
        "recommended_action": data.get("recommended_action"),
        "corrective_action": data.get("corrective_action"),
        "assigned_to": data.get("assigned_to"),
        "assigned_to_uid": data.get("assigned_to_uid"),
        "department": data.get("department"),
        "srm_conducted": data.get("srm_conducted", False),
        "srm_date": data.get("srm_date"),
        "srm_status": data.get("srm_status"),
        "status": data.get("status", "Open"),
        "follow_up_date": data.get("follow_up_date"),
        "closed_at": data.get("closed_at"),
        "closed_by": data.get("closed_by"),
        "tenant_id": data.get("tenant_id", ""),
        "created_by": data.get("created_by"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "remarks": data.get("remarks"),
    }


def _to_list_item(data: dict) -> dict:
    return {
        "id": data.get("id", ""),
        "hazard_id": data.get("hazard_id", ""),
        "title": data.get("title", ""),
        "source": _normalize_source(data.get("source", "")),
        "taxonomy": _normalize_taxonomy(data.get("taxonomy", ""), data.get("occurrence_category")),
        "priority": _normalize_priority(data.get("priority", "")),
        "risk_level": data.get("risk_level"),
        "status": data.get("status", "Open"),
        "assigned_to": data.get("assigned_to"),
        "department": data.get("department"),
        "created_at": data.get("created_at"),
        "severity": data.get("severity"),
        "probability": data.get("probability"),
        "risk_index": data.get("risk_index"),
    }
