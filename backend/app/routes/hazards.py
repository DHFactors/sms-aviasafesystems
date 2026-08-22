from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from loguru import logger

from app.models.hazard import (
    HazardCreate,
    HazardUpdate,
    HazardResponse,
    HazardListItem,
    HazardStatus,
    HazardSource,
    HazardTaxonomy,
    HAZARD_CREATION_SOURCES,
    AnalysisMode,
    SramCalculateRequest,
    SramSaveRequest,
)
from app.middleware.auth import get_current_user, get_tenant_user, get_safety_manager
from app.services.hazard_service import HazardService
from app.services.audit_service import log_audit, request_context
from app.services import srm_engine

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
    archetypeId: Optional[str] = Query(None, description="Virtual archetype tenant (demo-fixed-wing / demo-rotary-wing)."),
    user: Dict[str, Any] = Depends(get_current_user),
):
    from app.services.archetype_scope import resolve_data_tenant

    svc_user = user
    # Archetype requests take precedence and scope to the virtual tenant.
    if archetypeId and str(archetypeId).strip().startswith("demo-"):
        effective_tenant = str(archetypeId).strip()
        svc_user = dict(user)
        svc_user["tenant_id"] = effective_tenant
        svc_user["role"] = "AIRLINE_ADMIN"
    else:
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
_VALID_ANALYSIS_MODES = {m.value for m in AnalysisMode}


def _severity_inputs(data: dict) -> dict:
    return {
        "pax": int(data.get("pax") or 0),
        "worker": int(data.get("worker") or 0),
        "quality": int(data.get("quality") or 0),
        "asset": int(data.get("asset") or 0),
        "rep": int(data.get("rep") or 0),
        "sec": int(data.get("sec") or 0),
        "env": int(data.get("env") or 0),
    }


def _barrier_lists(barriers: Any) -> dict:
    b = barriers or {}
    if hasattr(b, "model_dump"):
        b = b.model_dump()
    return {
        "ecb_barriers": b.get("ecb") or [],
        "erb_barriers": b.get("erb") or [],
        "ncb_barriers": b.get("ncb") or [],
        "nrb_barriers": b.get("nrb") or [],
    }


@router.post("/{hazard_id}/sram/calculate", response_model=dict)
async def calculate_sram(
    hazard_id: str,
    payload: SramCalculateRequest,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Real-time CAAN CAR-19 SRM calculation — validates the hazard exists but
    does NOT persist anything (dynamic preview for the Bow-Tie workspace)."""
    service = HazardService(user.get("tenant_id", "default"))
    doc = service.get_hazard_by_id(hazard_id, user)
    if not doc:
        raise HTTPException(status_code=404, detail="Hazard not found")

    result = srm_engine.analyse(
        severity_inputs=payload.severity.model_dump(),
        **_barrier_lists(payload.barriers),
    )
    result["bowtie"] = payload.bowtie.model_dump() if payload.bowtie else None

    ip, request_id = request_context(request)
    log_audit(
        action="SRAM_CALCULATED",
        user=user.get("email"),
        tenant_id=user.get("tenant_id"),
        target_type="hazard",
        target_id=hazard_id,
        ip=ip,
        request_id=request_id,
        metadata={"index": result["risk_profile"]["resultant_risk"]["index"]},
    )
    return result


@router.put("/{hazard_id}/sram/save", response_model=dict)
async def save_sram(
    hazard_id: str,
    payload: SramSaveRequest,
    request: Request,
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    """Validate and persist a full Bow-Tie / SRAM configuration.

    Recomputes severity and barrier scoring authoritatively, updates the hazard's
    Master Risk register (severity/probability/risk_index/risk_level/risk_outcome)
    from the resultant risk, and stores the barrier register inside sram_data.
    """
    tenant_id = user["tenant_id"]
    service = HazardService(tenant_id)
    doc = service.get_hazard_by_id(hazard_id, user)
    if not doc:
        raise HTTPException(status_code=404, detail="Hazard not found")

    data = payload.sram_data.model_dump(exclude_none=False)
    severity_block = data.get("severity") or {}
    barriers_block = data.get("barriers") or {}

    if not severity_block.get("severity_letter"):
        raise HTTPException(
            status_code=422,
            detail="sram_data.severity must contain a computed severity_letter.",
        )

    # Authoritative recomputation.
    inputs = _severity_inputs(severity_block)
    severity = srm_engine.calculate_severity(**inputs)
    if severity["severity_letter"] != severity_block.get("severity_letter"):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Severity inputs inconsistent: recomputed {severity['severity_letter']} "
                f"({severity['total_score']}) does not match stored "
                f"{severity_block.get('severity_letter')}."
            ),
        )
    severity_block.update(severity)
    severity_block.update(inputs)

    barriers = srm_engine.evaluate_barriers(
        barriers_block.get("ecb") or [],
        barriers_block.get("erb") or [],
        barriers_block.get("ncb") or [],
        barriers_block.get("nrb") or [],
    )
    risk_profile = srm_engine.evaluate_risk_profile(
        severity, barriers["ecb"], barriers["erb"], barriers["ncb"], barriers["nrb"]
    )

    # Digital sign-off defaults keyed to the required authority.
    signoffs = data.get("signoffs") or {}
    if not signoffs.get("authority"):
        signoffs["authority"] = risk_profile["signoff"]["authority"]
    if not signoffs.get("required_tolerability"):
        signoffs["required_tolerability"] = risk_profile["resultant_risk"]["tolerability"]

    sram_data = {
        "severity": severity_block,
        "barriers": barriers,
        "risk_profile": risk_profile,
        "bowtie": (data.get("bowtie") or {}),
        "fishbone": data.get("fishbone"),
        "signoffs": signoffs,
    }

    sev_num = srm_engine.SEVERITY_LETTER_TO_NUMERIC[severity["severity_letter"]]
    prob = risk_profile["resultant_risk"]["probability_value"]
    now = datetime.now(timezone.utc)

    update_payload = {
        "analysis_mode": payload.analysis_mode.value,
        "sram_data": sram_data,
        "severity": sev_num,
        "probability": prob,
        "risk_index": sev_num * prob,
        "srm_conducted": True,
        "srm_date": now,
        "srm_status": "Conducted",
        "updated_at": now,
    }
    updated = service.update_hazard(hazard_id, update_payload, user)
    if not updated:
        raise HTTPException(status_code=404, detail="Hazard not found")

    ip, request_id = request_context(request)
    log_audit(
        action="SRAM_SAVED",
        user=user.get("email"),
        tenant_id=tenant_id,
        target_type="hazard",
        target_id=hazard_id,
        ip=ip,
        request_id=request_id,
        metadata={
            "analysis_mode": payload.analysis_mode.value,
            "resultant_index": risk_profile["resultant_risk"]["index"],
            "authority": signoffs["authority"],
        },
    )
    return {
        "id": updated.get("id"),
        "hazard_id": updated.get("hazard_id"),
        "analysis_mode": updated.get("analysis_mode"),
        "sram_data": updated.get("sram_data"),
        "severity": updated.get("severity"),
        "probability": updated.get("probability"),
        "risk_index": updated.get("risk_index"),
        "risk_level": updated.get("risk_level"),
        "risk_outcome": updated.get("risk_outcome"),
    }


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
        "analysis_mode": data.get("analysis_mode", "FISHBONE_ONLY"),
        "sram_data": data.get("sram_data"),
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
