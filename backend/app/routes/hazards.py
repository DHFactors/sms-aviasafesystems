from fastapi import (
    APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status,
)
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from loguru import logger

from app.core.config import settings

from app.models.hazard import (
    HazardCreate,
    HazardUpdate,
    HazardResponse,
    HazardListItem,
    HazardStatus,
    HazardSource,
    HazardTaxonomy,
    HazardFunctionCode,
    HAZARD_CREATION_SOURCES,
    HAZARD_FUNCTION_CODES,
    revalue_taxonomy,
    AnalysisMode,
    SramCalculateRequest,
    SramSaveRequest,
)
from app.middleware.auth import get_current_user, get_tenant_user, get_safety_manager
from app.services.hazard_service import HazardService
from app.services.audit_service import log_audit, request_context
from app.services import (
    hazard_enrichment_service,
    historical_import_service,
    hazard_triage_service,
    sram_service,
    srm_engine,
)

router = APIRouter()

# P3-6: default upload cap (50 MB) per the historical-import contract.
IMPORT_MAX_BYTES = 50 * 1024 * 1024
_TRIAGE_DECISIONS = {"Accepted", "Rejected", "Duplicate", "Escalated"}


class TriageRequest(BaseModel):
    decision: str = Field(..., description="Accepted | Rejected | Duplicate | Escalated")
    notes: Optional[str] = None
    initial_priority: Optional[str] = Field(None, pattern="^[HML]$")


class EnrichmentRequest(BaseModel):
    model_config = {"extra": "allow"}

    description: Optional[str] = None
    equipment: Optional[str] = None
    taxonomy: Optional[str] = None
    top_event: Optional[str] = None
    consequence: Optional[str] = None
    recommended_action: Optional[str] = None
    follow_up_date: Optional[str] = None
    remarks: Optional[str] = None
    enrichment_data: Optional[Dict[str, Any]] = None
    enrichment_sources: Optional[List[Any]] = None


def _require_safety_officer(user: Dict[str, Any]) -> None:
    """Triage/enrich are operational safety roles (§26/§27)."""
    allowed = (
        settings.SAFETY_OFFICER_ROLES
        + settings.TENANT_ADMIN_ROLES
        + ["SUPER_ADMIN"]
    )
    if user.get("role") not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Safety Officer or higher role required",
        )


@router.post("/{hazard_id}/triage", response_model=dict, status_code=status.HTTP_201_CREATED)
async def triage_hazard(
    hazard_id: str,
    payload: TriageRequest,
    request: Request,
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    """Record a triage decision for a hazard (Module B §26 / P3-1)."""
    _require_safety_officer(user)
    if payload.decision not in _TRIAGE_DECISIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"decision must be one of {sorted(_TRIAGE_DECISIONS)}",
        )
    service = hazard_triage_service.HazardTriageService(user["tenant_id"])
    try:
        result = service.triage_hazard(
            hazard_id, user, payload.decision,
            notes=payload.notes, initial_priority=payload.initial_priority,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    ip, request_id = request_context(request)
    log_audit(
        action="HAZARD_TRIAGED",
        user=user.get("email"),
        tenant_id=user["tenant_id"],
        target_type="hazard",
        target_id=hazard_id,
        ip=ip,
        request_id=request_id,
        metadata={"decision": payload.decision, "triage_id": result["id"]},
    )
    return {"status": "success", "timestamp": datetime.now(timezone.utc), "data": result}


@router.get("/{hazard_id}/triage", response_model=dict)
async def list_hazard_triage(
    hazard_id: str,
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    """List the triage history for a hazard, newest first (P3-1)."""
    service = hazard_triage_service.HazardTriageService(user["tenant_id"])
    rows = service.list_triage(hazard_id)
    return {"status": "success", "timestamp": datetime.now(timezone.utc), "data": rows}


@router.post("/{hazard_id}/enrich", response_model=dict)
async def enrich_hazard(
    hazard_id: str,
    payload: EnrichmentRequest,
    request: Request,
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    """Enrich a hazard additively (Module B §27 / P3-2).

    Create-only fields are rejected by the service; every change is audited
    with before/after values."""
    _require_safety_officer(user)
    body = payload.model_dump(exclude_none=True)
    if not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No enrichment fields supplied")
    service = hazard_enrichment_service.HazardEnrichmentService(user["tenant_id"])
    try:
        result = service.enrich_hazard(hazard_id, user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"status": "success", "timestamp": datetime.now(timezone.utc), "data": result}


# ─── P3-6: historical import (must precede /{hazard_id} lookups) ───

@router.post("/import", response_model=dict, status_code=status.HTTP_201_CREATED)
async def import_hazards(
    request: Request,
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(get_safety_manager),
):
    """Upload a historical import file (.xlsx/.csv): parse + stage + validate."""
    if user.get("role") not in (settings.TENANT_ADMIN_ROLES + ["SUPER_ADMIN"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Tenant admin required to import historical data")
    raw = await file.read()
    if len(raw) > IMPORT_MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"File exceeds the {IMPORT_MAX_BYTES // (1024*1024)}MB limit")
    service = historical_import_service.HistoricalImportService(user["tenant_id"])
    try:
        result = service.create_batch(user, raw, file.filename or "")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    ip, request_id = request_context(request)
    log_audit(
        action="HAZARD_IMPORT_UPLOADED",
        user=user.get("email"), tenant_id=user["tenant_id"],
        target_type="import_batch", target_id=result["id"],
        ip=ip, request_id=request_id,
        metadata={"filename": file.filename, "total": result.get("total_rows")},
    )
    return {"status": "success", "timestamp": datetime.now(timezone.utc), "data": result}


@router.get("/import/{batch_id}", response_model=dict)
async def get_import_batch(
    batch_id: str,
    status_filter: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_safety_manager),
):
    """List staged rows for an import batch (review view)."""
    service = historical_import_service.HistoricalImportService(user["tenant_id"])
    rows = service.list_rows(batch_id, status_filter)
    return {"status": "success", "timestamp": datetime.now(timezone.utc),
            "data": {"batch_id": batch_id, "rows": rows}}


@router.post("/import/{batch_id}/promote", response_model=dict)
async def promote_import_batch(
    batch_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_safety_manager),
):
    """Promote a batch's valid rows to hazards (operator approval required)."""
    if user.get("role") not in (settings.TENANT_ADMIN_ROLES + ["SUPER_ADMIN"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Tenant admin required to promote an import")
    service = historical_import_service.HistoricalImportService(user["tenant_id"])
    try:
        result = service.promote_batch(batch_id, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {"status": "success", "timestamp": datetime.now(timezone.utc), "data": result}


@router.delete("/import/{batch_id}", response_model=dict)
async def reject_import_batch(
    batch_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_safety_manager),
):
    """Reject (discard) an import batch."""
    if user.get("role") not in (settings.TENANT_ADMIN_ROLES + ["SUPER_ADMIN"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Tenant admin required to reject an import")
    service = historical_import_service.HistoricalImportService(user["tenant_id"])
    try:
        result = service.reject_batch(batch_id, user, "rejected by operator")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {"status": "success", "timestamp": datetime.now(timezone.utc), "data": result}


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
_VALID_FUNCTIONS = {f.value for f in HazardFunctionCode}


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

    # SN10 / P2-8: materialise one risk-register row per bow-tie consequence.
    try:
        await sram_service.sync_consequence_register_rows(
            hazard_id, tenant_id, risk_profile, severity["severity_letter"]
        )
    except Exception as e:
        logger.warning(f"Per-consequence register sync failed for {hazard_id}: {e}")

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
        "BIRD": "Environmental",
        "FIRE": "Technical",
        "ENG": "Technical",
        "SYS": "Technical",
        "MAC": "Technical",
        "CFIT": "Organizational",
        "GCOL": "Organizational",
        "RI": "Organizational",
        "RE": "Organizational",
        "LOCI": "Organizational",
        "CABIN": "Human",
        "PRO": "Organizational",
        "ARC": "Organizational",
        "WX": "Environmental",
    }
    mapped = taxonomy_map.get((occurrence_category or value or "").upper())
    return revalue_taxonomy(mapped or "")


def _normalize_function(value):
    if value in _VALID_FUNCTIONS:
        return value
    return "GEN"


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
        "function": _normalize_function(data.get("function", "")),
        "adrep_category": data.get("adrep_category"),
        "occurrence_type": data.get("occurrence_type"),
        "taxonomy": _normalize_taxonomy(data.get("taxonomy", ""), data.get("occurrence_category")),
        "taxonomy_specific": data.get("taxonomy_specific"),
        "threat": data.get("threat"),
        "consequence": data.get("consequence"),
        "top_event": data.get("top_event"),
        "severity": data.get("severity"),
        "probability": data.get("probability"),
        "risk_index": data.get("risk_index"),
        "risk_level": data.get("risk_level"),
        "risk_outcome": data.get("risk_outcome"),
        "priority": _normalize_priority(data.get("priority", "")),
        "recommended_action": data.get("recommended_action"),
        "corrective_action": data.get("corrective_action"),
        "corrective_action_flag": data.get("corrective_action_flag", False),
        "srm_flag": data.get("srm_flag", False),
        "assigned_to": data.get("assigned_to"),
        "assigned_to_uid": data.get("assigned_to_uid"),
        "department": data.get("department"),
        "srm_conducted": data.get("srm_conducted", False),
        "srm_date": data.get("srm_date"),
        "srm_status": data.get("srm_status"),
        "analysis_mode": data.get("analysis_mode", "FISHBONE_ONLY"),
        "sram_data": data.get("sram_data"),
        "status": data.get("status", "Open"),
        "priority_date": data.get("priority_date"),
        "status_date": data.get("status_date"),
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
        "function": _normalize_function(data.get("function", "")),
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
