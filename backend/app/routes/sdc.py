# ============================================================================
# FILE: sdc.py
# PATH: backend/app/routes/sdc.py
# PURPOSE: aviaSDCPS Safety Data ingestor endpoints.
#
#   POST /api/v1/sdc/validate  - validate a batch of mapped records against
#                                ICAO ADREP 2000 style field rules.
#   POST /api/v1/sdc/ingest    - commit a validated batch into the PostgreSQL
#                                registers (hazards / reports / cans / caps).
#
# The aviaSDCPS frontend (public/js/views/sdc.js) previously POSTed to the
# bare /sdc/validate and /sdc/ingest paths which had no backend -> 404. These
# routes live under /api/v1/sdc to match the frontend API base URL.
# ============================================================================

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.db.ids import tenant_uuid
from app.db.isolation import demo_scope
from app.db.session import session_scope
from app.db import db_models
from app.middleware.auth import get_tenant_user
from app.middleware.rate_limit import rate_limit
from app.services.audit_service import log_audit, request_context

router = APIRouter(prefix="/api/v1/sdc", tags=["SDC Ingestion"])


# ── Schemas ──────────────────────────────────────────────────────────────────
class SdcRecord(BaseModel):
    row_index: int = 0
    fields: Dict[str, Any] = Field(default_factory=dict)


class SdcValidateRequest(BaseModel):
    file_name: str = ""
    target_schema: str = "adrep"  # adrep | car19 | eccairs
    mappings: List[Dict[str, str]] = Field(default_factory=list)  # source -> target
    records: List[SdcRecord] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)  # legacy frontend shape


class SdcIngestRequest(BaseModel):
    batch_id: str
    file_name: str = ""
    target_schema: str = "adrep"
    mappings: List[Dict[str, str]] = Field(default_factory=list)
    row_count: int = 0


# ── Batch store (in-memory, per-process) ─────────────────────────────────────
# Keyed by batch_id -> {"tenant_id", "file_name", "target_schema", "mappings",
# "records": [ {row_index, fields, errors, warnings} ]}. A validated batch must
# exist (and belong to the caller's tenant) before /ingest will accept it.
_VALIDATED_BATCHES: Dict[str, Dict[str, Any]] = {}


# ── ADREP 2000 validation rules ──────────────────────────────────────────────
OCCURRENCE_TYPES = {"ACCIDENT", "SERIOUS_INCIDENT", "INCIDENT"}
SEVERITY_RANGE = range(1, 6)
PROBABILITY_RANGE = range(1, 6)
VALID_SCHEMAS = {"adrep", "car19", "eccairs"}


def _parse_date(value: Any) -> Optional[datetime]:
    """Best-effort parsing of an occurrence date into a datetime (UTC)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (ValueError, OSError):
            return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y",
                "%Y/%m/%d", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S", "%d %b %Y"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except ValueError:
            continue
    return None


def _validate_record(record: Dict[str, Any], fields_by_target: Dict[str, str]) -> Dict[str, Any]:
    """Validate one record against ADREP-style rules.

    Returns a dict with "errors" and "warnings" lists, each item being
    {"row":row_index, "field":..., "code":..., "message":...}.
    """
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    row = record.get("row_index", 0)

    # `fields` is the primary (task-spec) shape; legacy `rows` pass raw dicts.
    if isinstance(record.get("fields"), dict):
        data: Dict[str, Any] = record["fields"]
    else:
        data = {v: record.get(k) for k, v in fields_by_target.items() if v}

    def _bad(field: str = "") -> Dict[str, Any]:
        return {"row": row, "field": field, "code": "INVALID_FIELD",
                "message": ""}

    # occurrence_date: valid date, not in the future
    raw_date = data.get("occurrence_date") or data.get("occurrenceDate")
    if raw_date not in (None, ""):
        dt = _parse_date(raw_date)
        if dt is None:
            errors.append({**_bad("occurrence_date"),
                           "message": f"'{raw_date}' is not a valid date."})
        elif dt > datetime.now(timezone.utc):
            errors.append({**_bad("occurrence_date"),
                           "message": f"'{raw_date}' is in the future."})
    else:
        warnings.append({**_bad("occurrence_date"),
                         "message": "occurrence_date is missing (required for reports)."})

    # severity: integer 1-5
    sev = data.get("severity")
    if sev not in (None, ""):
        try:
            sev_i = int(sev)
            if sev_i not in SEVERITY_RANGE:
                errors.append({**_bad("severity"),
                               "message": f"severity must be 1-5, got '{sev}'."})
        except (TypeError, ValueError):
            errors.append({**_bad("severity"),
                           "message": f"severity must be a number, got '{sev}'."})

    # probability: integer 1-5
    prob = data.get("probability")
    if prob not in (None, ""):
        try:
            prob_i = int(prob)
            if prob_i not in PROBABILITY_RANGE:
                errors.append({**_bad("probability"),
                               "message": f"probability must be 1-5, got '{prob}'."})
        except (TypeError, ValueError):
            errors.append({**_bad("probability"),
                           "message": f"probability must be a number, got '{prob}'."})

    # location: must be non-empty if provided (optional field -> warning otherwise)
    loc = data.get("location")
    if loc in (None, ""):
        warnings.append({**_bad("location"),
                         "message": "location is empty (optional, recommended for reporting)."})

    # occurrence_type: one of ACCIDENT / SERIOUS_INCIDENT / INCIDENT
    otype = data.get("occurrence_type") or data.get("occurrenceType")
    if otype not in (None, ""):
        if str(otype).strip().upper() not in OCCURRENCE_TYPES:
            errors.append({**_bad("occurrence_type"),
                           "message": (f"occurrence_type must be one of "
                                       f"{sorted(OCCURRENCE_TYPES)}, got '{otype}'.")})
    else:
        warnings.append({**_bad("occurrence_type"),
                         "message": "occurrence_type is missing (required for classification)."})

    return {"errors": errors, "warnings": warnings}


# ── Validate batch ───────────────────────────────────────────────────────────
@router.post("/validate", response_model=dict)
@rate_limit("sdc_validate")
async def validate_batch(
    request: Request,
    payload: SdcValidateRequest,
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    if payload.target_schema.lower() not in VALID_SCHEMAS:
        raise HTTPException(status_code=400, detail=(
            f"Unsupported target_schema '{payload.target_schema}'. "
            f"Supported: {sorted(VALID_SCHEMAS)}."
        ))

    # Build source -> target field map for legacy `rows` support.
    fields_by_target: Dict[str, str] = {}
    for m in payload.mappings:
        if isinstance(m, dict) and m.get("target"):
            fields_by_target.setdefault(m["target"], m["source"])
    # Reverse: source header -> target field (to normalise legacy source-keyed
    # rows into target-keyed `fields`).
    source_of: Dict[str, str] = {src: tgt for tgt, src in fields_by_target.items()}

    # Normalise incoming records (task spec `records` or legacy `rows`).
    normalized: List[Dict[str, Any]] = []
    if payload.records:
        for rec in payload.records:
            normalized.append({"row_index": rec.row_index,
                               "fields": dict(rec.fields or {})})
    elif payload.rows:
        for idx, row in enumerate(payload.rows):
            remapped: Dict[str, Any] = {}
            for src, val in (row or {}).items():
                target = source_of.get(src, src)
                if target:
                    remapped[target] = val
            normalized.append({"row_index": idx, "fields": remapped or dict(row or {})})

    # Validate every record.
    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    for rec in normalized:
        outcome = _validate_record(rec, fields_by_target)
        rec["errors"] = outcome["errors"]
        rec["warnings"] = outcome["warnings"]
        results.append(rec)
        errors.extend(outcome["errors"])
        warnings.extend(outcome["warnings"])

    batch_id = str(uuid.uuid4())
    _VALIDATED_BATCHES[batch_id] = {
        "tenant_id": user["tenant_id"],
        "file_name": payload.file_name,
        "target_schema": payload.target_schema,
        "mappings": payload.mappings,
        "records": normalized,
    }

    return {
        "success": True,
        "batch_id": batch_id,
        "schema": payload.target_schema,
        "total_records": len(normalized),
        "errors": errors,
        "warnings": warnings,
        "valid": len(errors) == 0,
    }


# ── Ingest (commit) batch ────────────────────────────────────────────────────
def _resolve_typed(value: Any, cast: Any = str):
    if value in (None, ""):
        return None
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


@router.post("/ingest", response_model=dict)
@rate_limit("sdc_ingest")
async def ingest_batch(
    request: Request,
    payload: SdcIngestRequest,
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    tenant_id = user["tenant_id"]
    batch = _VALIDATED_BATCHES.get(payload.batch_id)
    if batch is None:
        raise HTTPException(status_code=400, detail=(
            f"batch_id '{payload.batch_id}' not found. Validate the batch first."
        ))
    if batch["tenant_id"] not in (None, tenant_id):
        raise HTTPException(status_code=403, detail="Batch does not belong to this tenant.")

    records = batch.get("records") or []
    if not records:
        raise HTTPException(status_code=400, detail="Batch contains no staged records.")

    tid_uuid = tenant_uuid(tenant_id)
    now = datetime.now(timezone.utc)
    is_demo = demo_scope()
    email = user.get("email", "")
    uid = user.get("uid", "")
    schema = payload.target_schema or batch.get("target_schema") or "adrep"

    ingested = 0
    by_type = {"hazard": 0, "occurrence": 0, "can": 0, "cap": 0}

    async with session_scope() as session:
        for rec in records:
            data: Dict[str, Any] = rec.get("fields") or {}
            # Only commit records that passed validation.
            if rec.get("errors"):
                continue
            otype = (data.get("occurrence_type") or data.get("occurrenceType") or "").strip().upper()
            title = str(data.get("title") or data.get("narrative") or "Imported SDC record").strip()
            desc = str(data.get("narrative") or title).strip()
            severity = _resolve_typed(data.get("severity"), int)
            probability = _resolve_typed(data.get("probability"), int)

            if (otype or "").upper() in OCCURRENCE_TYPES:
                model = db_models.Report(
                    tenant_id=tid_uuid,
                    report_type="voluntary" if otype != "ACCIDENT" else "mandatory",
                    status="Under Review",
                    ai_status="PENDING",
                    narrative=desc or "SDC imported occurrence",
                    location=str(data.get("location") or "Unknown").strip() or "Unknown",
                    occurrence_date=_parse_date(data.get("occurrence_date") or data.get("occurrenceDate"))
                               or now,
                    occurrence_type=otype,
                    severity=str(severity) if severity else None,
                    severity_level=severity,
                    probability_level=probability,
                    aircraft_registration=data.get("aircraftReg") or data.get("aircraft_registration"),
                    flight_number=data.get("flightNumber") or data.get("flight_number"),
                    is_demo=is_demo,
                    created_by=email,
                )
                session.add(model)
                by_type["occurrence"] += 1
                ingested += 1
            elif (data.get("record_type") or data.get("type") or "").strip().lower() in (
                "hazard", "hazards"
            ):
                model = db_models.Hazard(
                    tenant_id=tid_uuid,
                    hazard_id=f"HAZ-SDC-{uuid.uuid4().hex[:8].upper()}",
                    title=title,
                    description=desc,
                    source="SDC_IMPORT",
                    source_id="",
                    taxonomy="GENERAL",
                    severity=severity,
                    probability=probability,
                    status="Open",
                    priority="M",
                    is_demo=is_demo,
                    created_by=email,
                )
                session.add(model)
                by_type["hazard"] += 1
                ingested += 1
            else:
                # CAP / CAN shaped rows persist to the caps register as a
                # full CAN -> CAP chain. A minimal parent hazard is created so
                # the foreign keys (hazards.id -> cans.hazard_id -> caps.can_id)
                # remain valid in a single transaction.
                hazard = db_models.Hazard(
                    tenant_id=tid_uuid,
                    hazard_id=f"HAZ-SDC-{uuid.uuid4().hex[:8].upper()}",
                    title=f"SDC corrective action source: {title}",
                    description=desc or "SDC imported corrective action",
                    source="SDC_IMPORT",
                    source_id="",
                    taxonomy="GENERAL",
                    severity=severity,
                    probability=probability,
                    status="Open",
                    priority="M",
                    is_demo=is_demo,
                    created_by=email,
                )
                session.add(hazard)
                await session.flush()
                can = db_models.Can(
                    tenant_id=tid_uuid,
                    can_reference=f"CAN-SDC-{uuid.uuid4().hex[:8].upper()}",
                    hazard_id=hazard.id,
                    title=title,
                    description=desc or "SDC imported corrective action",
                    required_action=desc or "Implement corrective action",
                    issued_by=email,
                    issued_by_uid=uid,
                    issued_at=now,
                    assigned_to=data.get("assigned_to") or "Unassigned",
                    assigned_to_uid="",
                    department=data.get("department"),
                    priority="M",
                    status="Open",
                    is_demo=is_demo,
                    created_by=email,
                )
                session.add(can)
                await session.flush()
                cap = db_models.Cap(
                    cap_reference=f"CAP-SDC-{uuid.uuid4().hex[:8].upper()}",
                    tenant_id=tid_uuid,
                    can_id=can.id,
                    action_plan=desc or "SDC imported corrective action",
                    timeline="Imported",
                    resources_required="N/A",
                    implementation_plan=desc or "Imported corrective action",
                    department=data.get("department"),
                    target_completion_date=now,
                    submitted_by=email,
                    submitted_by_uid=uid,
                    submitted_at=now,
                    status="Open",
                    is_demo=is_demo,
                )
                session.add(cap)
                by_type["can"] += 1
                by_type["cap"] += 1
                ingested += 1

    # Audit the batch (accepted records only).
    ip, req_id = request_context(request)
    log_audit(
        action="SDC_BATCH_INGESTED",
        user=email,
        tenant_id=tenant_id,
        target_type="sdc_batch",
        target_id=payload.batch_id,
        ip=ip,
        request_id=req_id,
        metadata={
            "file_name": payload.file_name,
            "schema": schema,
            "requested_rows": payload.row_count,
            "ingested": ingested,
            "by_type": by_type,
        },
    )
    _VALIDATED_BATCHES.pop(payload.batch_id, None)

    return {
        "success": True,
        "batch_id": payload.batch_id,
        "ingested": ingested,
        "by_type": by_type,
        "message": f"{ingested} record(s) ingested successfully.",
    }
