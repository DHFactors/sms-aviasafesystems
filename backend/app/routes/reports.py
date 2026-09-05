# ============================================================================
# FILE: reports.py
# PATH: backend/app/routes/reports.py
# VERSION: 2.1.0
# DATE CREATED: 2026-07-03
# DATE REVISED: 2026-07-27
# PURPOSE: API endpoints for safety report submission and retrieval.
# AUTHOR: Ghanshyam Acharya
# CODE OWNER: AviaSafeSystems
# ============================================================================

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status, Request
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from loguru import logger

from app.models.report import ReportCreate, MorCreate, ReportResponse, ReportListItem
from app.models.hazard import (
    HazardCreate,
    HazardSource,
    HazardTaxonomy,
    HazardPriority,
    revalue_taxonomy,
)
from app.middleware.auth import get_current_user, get_tenant_user, get_safety_manager
from app.core.config import settings
from app.services.report_service import ReportService
from app.services.hazard_service import HazardService
from app.services.risk_matrix import compute_risk_index, get_risk_level
from app.services.audit_service import log_audit, request_context
from app.middleware.rate_limit import rate_limit

router = APIRouter()

# ICAO ADREP occurrence category -> hazard taxonomy. Values align to the
# ICAO-aligned 4-value set after revalue_taxonomy().
TAXONOMY_FROM_OCCURRENCE = {
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


class RiskAssessmentRequest(BaseModel):
    severity: int = Field(..., ge=1, le=5, description="1-5 ICAO severity")
    probability: int = Field(..., ge=1, le=5, description="1-5 ICAO probability")
    notes: Optional[str] = None


@router.post("/", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def submit_report(
    report: ReportCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    tenant_id = user["tenant_id"]
    service = ReportService(tenant_id)
    stored = service.create_report(report.model_dump(), user)
    background_tasks.add_task(service.run_ai_analysis, stored["id"], report.narrative)
    _auto_create_hazard_from_report(stored, user)
    ip, request_id = request_context(request)
    log_audit(
        action="REPORT_SUBMITTED",
        user=user.get("email"),
        tenant_id=tenant_id,
        target_type="report",
        target_id=stored["id"],
        ip=ip,
        request_id=request_id,
        metadata={"report_type": "voluntary"},
    )
    return _to_report_response(stored)


@router.post("/mor", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
@rate_limit("mor_submit")
async def submit_mor(
    request: Request,
    report: MorCreate,
    background_tasks: BackgroundTasks,
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    """Submit an ECCAIRS-aligned Mandatory Occurrence Report.

    All ECCAIRS entities are validated:
      - REPORTER (mandatory identification)
      - AIRCRAFT (make, model, registration, operator)
      - FLIGHT (phase, type)
      - ENGINE / PROPELLER (optional)
      - PEOPLE (optional counts)
      - OCCURRENCE (date, location, type, class, category)
      - RISK (optional severity/probability)
      - INVESTIGATION (optional tracking)
    """
    tenant_id = user["tenant_id"]
    service = ReportService(tenant_id)
    payload = report.model_dump()

    risk_index = None
    sev = payload.get("severity")
    prob = payload.get("probability")
    if sev is not None and prob is not None:
        risk_index = compute_risk_index(sev, prob)

    payload["risk_index"] = risk_index
    payload["severity_level"] = sev
    payload["probability_level"] = prob
    payload["report_type"] = "mandatory"
    payload["is_anonymous"] = False
    payload["occurrence_date"] = payload.pop("occurrence_date_time")
    payload["location"] = payload.pop("occurrence_location")
    payload["country"] = payload.pop("occurrence_country")
    payload["latitude"] = payload.pop("occurrence_latitude", None)
    payload["longitude"] = payload.pop("occurrence_longitude", None)

    stored = service.create_report(payload, user)
    background_tasks.add_task(service.run_ai_analysis, stored["id"], report.narrative)
    _auto_create_hazard_from_report(stored, user)
    ip, request_id = request_context(request)
    log_audit(
        action="REPORT_SUBMITTED",
        user=user.get("email"),
        tenant_id=tenant_id,
        target_type="report",
        target_id=stored["id"],
        ip=ip,
        request_id=request_id,
        metadata={"report_type": "mandatory"},
    )
    return _to_report_response(stored)


@router.post("/vsr", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
@rate_limit("vsr_submit")
async def submit_vsr(
    request: Request,
    report: ReportCreate,
    background_tasks: BackgroundTasks,
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    """Submit a Voluntary Safety Report (VSR).

    Differences from MOR:
      - Reporter fields are optional
      - is_anonymous flag may be set
      - No engine/propeller, people, or investigation validation
    """
    tenant_id = user["tenant_id"]
    service = ReportService(tenant_id)
    payload = report.model_dump()

    sev = payload.get("severity_level")
    prob = payload.get("probability_level")
    risk_index = None
    if sev is not None and prob is not None:
        risk_index = compute_risk_index(sev, prob)

    payload["risk_index"] = risk_index
    payload["report_type"] = "voluntary"

    stored = service.create_report(payload, user)
    background_tasks.add_task(service.run_ai_analysis, stored["id"], report.narrative)
    _auto_create_hazard_from_report(stored, user)
    ip, request_id = request_context(request)
    log_audit(
        action="REPORT_SUBMITTED",
        user=user.get("email"),
        tenant_id=tenant_id,
        target_type="report",
        target_id=stored["id"],
        ip=ip,
        request_id=request_id,
        metadata={"report_type": "voluntary"},
    )
    return _to_report_response(stored)


@router.get("/", response_model=List[ReportListItem])
async def get_reports(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Retrieve safety reports.

    AIRLINE_ADMIN: reports scoped to their tenant.
    CAAN_SMD / SUPER_ADMIN: cross-tenant view.
    """
    if not user.get("tenant_id") and user.get("role") not in settings.CROSS_TENANT_ROLES:
        raise HTTPException(status_code=403, detail="User does not have tenant access")
    service = ReportService(user.get("tenant_id", "default"))

    docs = service.get_reports(user)
    return [_to_list_item(d) for d in docs]


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Retrieve a single safety report by ID."""
    if not user.get("tenant_id") and user.get("role") not in settings.CROSS_TENANT_ROLES:
        raise HTTPException(status_code=403, detail="User does not have tenant access")
    service = ReportService(user.get("tenant_id", "default"))

    doc = service.get_report_by_id(report_id, user)
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")

    return _to_report_response(doc)


@router.put("/{report_id}/risk-assessment", response_model=ReportResponse)
async def confirm_risk_assessment(
    report_id: str,
    assessment: RiskAssessmentRequest,
    user: Dict[str, Any] = Depends(get_safety_manager),
):
    """Safety Manager confirms the official ICAO risk assessment for a report.

    Severity x Probability = Risk Index determines Risk Level.
    AIRLINE_ADMIN: scoped to their tenant.
    CAAN_SMD / SUPER_ADMIN: cross-tenant access.
    """
    tenant_id = user["tenant_id"]
    service = ReportService(tenant_id)

    updated = service.confirm_risk_assessment(
        report_id=report_id,
        severity=assessment.severity,
        probability=assessment.probability,
        user=user,
        notes=assessment.notes,
    )

    return _to_report_response(updated)


def _normalize_severity(value):
    if value is None or isinstance(value, str):
        return value
    return str(value)


def _to_report_response(data: dict) -> dict:
    """Transform stored Firestore document into ReportResponse shape."""
    keys = [
        "id", "tenant_id", "report_type", "status", "ai_status",
        "narrative", "location", "occurrence_date",
        "created_by", "created_at", "updated_at",
        "is_anonymous", "flight_number", "aircraft_registration",
        "occurrence_type", "severity",
        "investigation_status",
        "ai_analysis",
        "severity_level", "probability_level", "risk_index", "risk_level",
        "risk_assessment", "ai_suggested_assessment",
        "occurrence_class", "latitude", "longitude", "country",
        "aircraft_make", "aircraft_model", "aircraft_serial_number",
        "operator", "operator_icao", "aircraft_category",
        "engine_make", "engine_model", "engine_serial_number",
        "flight_phase", "flight_type",
        "departure_airport", "destination_airport",
        "aircraft_utilisation_hours", "aircraft_utilisation_cycles",
        "crew_count", "passenger_count",
        "fatal_injuries", "serious_injuries", "minor_injuries",
        "occurrence_category", "human_factors", "contributing_factors",
        "investigation_agency",
        "reporter_name", "reporter_role", "reporter_email",
        "reporter_phone", "reporter_organisation", "reporting_date",
        "etops", "propeller_make", "propeller_model",
        "call_sign", "organisation_comments",
        "manufacturer_advised", "fdr_data_retained",
    ]
    result = {k: data.get(k) for k in keys}
    result["severity"] = _normalize_severity(result.get("severity"))
    return result


def _to_list_item(data: dict) -> dict:
    """Transform stored document into ReportListItem shape."""
    return {
        "id": data.get("id", ""),
        "tenant_id": data.get("tenant_id", ""),
        "report_type": data.get("report_type", "voluntary"),
        "status": data.get("status", "NEW"),
        "ai_status": data.get("ai_status", "PENDING"),
        "location": data.get("location", ""),
        "occurrence_date": data.get("occurrence_date"),
        "created_by": data.get("created_by", ""),
        "created_at": data.get("created_at"),
        "is_anonymous": data.get("is_anonymous", False),
        "occurrence_type": data.get("occurrence_type"),
        "severity": _normalize_severity(data.get("severity")),
        "risk_score": data.get("risk_score"),
        "risk_level": data.get("risk_level"),
        "severity_level": data.get("severity_level"),
        "probability_level": data.get("probability_level"),
        "occurrence_category": data.get("occurrence_category"),
        "aircraft_make": data.get("aircraft_make"),
        "aircraft_model": data.get("aircraft_model"),
        "operator": data.get("operator"),
        "flight_phase": data.get("flight_phase"),
    }


def _determine_hazard_taxonomy(occurrence_category: Optional[str]) -> str:
    return revalue_taxonomy(TAXONOMY_FROM_OCCURRENCE.get(occurrence_category or "", ""))


def _determine_hazard_priority(severity_level: Optional[int], probability_level: Optional[int]) -> str:
    if severity_level is None or probability_level is None:
        return "M"
    risk = compute_risk_index(severity_level, probability_level)
    if risk >= 12:
        return "H"
    elif risk >= 6:
        return "M"
    else:
        return "L"


def _auto_create_hazard_from_report(stored: dict, user: dict):
    try:
        tenant_id = stored.get("tenant_id")
        if not tenant_id:
            return
        source = HazardSource.VSR if stored.get("report_type") == "voluntary" else HazardSource.MOR
        sev = stored.get("severity_level")
        prob = stored.get("probability_level")
        taxonomy_str = _determine_hazard_taxonomy(stored.get("occurrence_category"))
        priority_str = _determine_hazard_priority(sev, prob)

        hazard_payload = HazardCreate(
            title=(stored.get("narrative") or "")[:100],
            description=stored.get("narrative", ""),
            source=source,
            source_id=stored.get("id"),
            source_url=f"/report/detail.html?id={stored.get('id')}",
            adrep_category=stored.get("occurrence_category"),
            occurrence_type=stored.get("occurrence_type"),
            taxonomy=HazardTaxonomy(taxonomy_str),
            severity=sev,
            probability=prob,
            risk_index=compute_risk_index(sev, prob) if sev and prob else None,
            priority=HazardPriority(priority_str) if priority_str in [e.value for e in HazardPriority] else HazardPriority.MEDIUM,
            tenant_id=tenant_id,
        )
        service = HazardService(tenant_id)
        created = service.create_hazard(hazard_payload.model_dump(), user)
        logger.info(f"Auto-created hazard from report {stored.get('id')}")
        if created:
            log_audit(
                action="HAZARD_CREATED",
                user=user.get("email"),
                tenant_id=tenant_id,
                target_type="hazard",
                target_id=created.get("id"),
                metadata={"source": "auto", "source_report_id": stored.get("id")},
            )
    except Exception as e:
        logger.warning(f"Failed to auto-create hazard from report: {e}")
