from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from datetime import datetime, date, time
from enum import Enum


def _coerce_date_string(value):
    """Normalise date-only / common date strings to a datetime.

    HTML date inputs and legacy records store e.g. '2026-08-25' (no time
    component). Pydantic datetime fields require a separator + time, so
    convert these to midnight UTC; otherwise return the value untouched so
    other (valid) inputs still parse normally.
    """
    if not isinstance(value, str):
        return value
    value = value.strip()
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        try:
            return datetime.combine(date.fromisoformat(value), time.min)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return value


def _coerce_datetime_fields(cls, data):
    if isinstance(data, dict):
        for name, field in cls.model_fields.items():
            ann = field.annotation
            args = getattr(ann, "__args__", None)
            if ann is datetime or (args and datetime in args):
                val = data.get(name)
                if isinstance(val, str):
                    data[name] = _coerce_date_string(val)
    return data


class CANStatus(str, Enum):
    OPEN = "Open"
    UNDER_REVIEW = "Under Review"
    CLOSED = "Closed"
    ESCALATED = "Escalated"


class CAPStatus(str, Enum):
    IN_PROGRESS = "In Progress"
    UNDER_REVIEW = "Under Review"
    COMPLETED = "Completed"
    REVISION_REQUIRED = "Revision Required"
    OVERDUE = "Overdue"


class CANPriority(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


# ─── Buddha Air FORM SMSM 8.8.2 — shared optional fields ───
# All of these are Optional and default to None so existing clients keep
# working unchanged; new fields only appear when provided.

class CANFormFields(BaseModel):
    """Optional issuance block of the Corrective Action Notice (FORM SMSM 8.8.2).

    ``initial_sra`` is the structured CAAN/ICAO 5x5 Safety Risk Assessment at
    issuance time::
        {
          "severity": 1..5, "severity_letter": "A".."E",
          "probability": 1..5, "risk_index": 1..25,
          "risk_level": "Low"|"High"|"Very High",
          "risk_outcome": "Acceptable"|"Tolerable"|"Intolerable",
          "assessed_by": "email", "assessed_at": iso-datetime
        }
    Legacy flat fields (initial_severity / initial_probability / initial_risk_index)
    remain for backward compatibility and are kept in sync server-side.
    """
    copies_to: Optional[str] = None
    requested_function: Optional[str] = None
    addressed_function: Optional[str] = None
    initial_severity: Optional[int] = Field(None, ge=1, le=5)
    initial_probability: Optional[int] = Field(None, ge=1, le=5)
    initial_risk_index: Optional[int] = Field(None, ge=1, le=25)
    initial_risk_level: Optional[str] = None
    initial_risk_outcome: Optional[str] = None
    initial_tolerability_tier: Optional[str] = None
    initial_sra: Optional[dict] = None
    classification_type: Optional[str] = None
    classification_level: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_can_dates(cls, data):
        return _coerce_datetime_fields(cls, data)


class CAPFormFields(BaseModel):
    """Optional corrective action / closure block (FORM SMSM 8.8.2).

    Mirrors the official CAA Corrective Action Plan form grid:
    Section 5.1 analysis items (1)-(5) plus identification header and the
    managerial / CAA sign-off blocks.
    """
    @model_validator(mode="before")
    @classmethod
    def _coerce_cap_dates(cls, data):
        return _coerce_datetime_fields(cls, data)

    # ── Identification header ──
    company_name: Optional[str] = None
    base_location: Optional[str] = None
    area_system_of_interest: Optional[str] = None
    finding_number: Optional[str] = None
    file_ref: Optional[str] = None
    # ── Section 5.1 analysis ──
    factual_review: Optional[str] = None          # 5.1(1)
    rca: Optional[str] = None                     # 5.1(2)
    short_term_ca: Optional[str] = None           # 5.1(3)
    long_term_ca: Optional[str] = None            # 5.1(4) - incl. induced hazards assessment
    implementation_timeline: Optional[str] = None # 5.1(5)
    # ── Sign-off blocks ──
    managerial_approval: Optional[dict] = None    # {name, signature, date}
    caa_acceptance: Optional[dict] = None         # {accepted: bool, signature, date}
    # ── Residual risk / closure ──
    residual_severity: Optional[int] = Field(None, ge=1, le=5)
    residual_probability: Optional[int] = Field(None, ge=1, le=5)
    residual_risk_index: Optional[int] = Field(None, ge=1, le=25)
    residual_risk_level: Optional[str] = None
    residual_risk_outcome: Optional[str] = None
    residual_tolerability_tier: Optional[str] = None
    residual_sra: Optional[dict] = None
    # ── Structured RCA (Fishbone / Ishikawa 5M + Management) ──
    # root_causes: [{ id, category, description, is_primary }]
    # action_items: [{ id, description, root_cause_id, owner, target_date }]
    root_causes: Optional[list] = None
    action_items: Optional[list] = None
    # Selected RCA methodology: 'bow_tie' (CAAN CAR-19 SRAM) or 'fishbone' (6M)
    rca_method: Optional[str] = Field(None, pattern="^(bow_tie|fishbone)$")
    # ── CAAN CAR-19 SRM (Bow-Tie) block persisted with the CAP submission ──
    # sram_data: { analysis_mode, severity, barriers, risk_profile, bowtie, signoffs }
    sram_data: Optional[dict] = None
    # Governance escalation — flags the CAP for Accountable Executive review
    # (high residual risk / resource blockage).
    escalated_to_ae: Optional[bool] = None
    escalated_by: Optional[str] = None
    escalated_at: Optional[datetime] = None
    escalation_reason: Optional[str] = None
    # Formal AE risk-acceptance sign-off (Doc 9859 §4.5 / CAR-19):
    # typed executive signature, decision timestamp and mandatory review date.
    ae_signature: Optional[str] = Field(None, max_length=200)
    ae_signed_at: Optional[datetime] = None
    ae_review_interval_days: Optional[int] = Field(None, ge=1, le=365)
    ae_review_date: Optional[datetime] = None
    sag_sign: Optional[str] = None
    sag_signed_by: Optional[str] = None
    sag_signed_at: Optional[datetime] = None
    manager_approval: Optional[str] = None
    ca_acceptance: Optional[str] = None
    process_owner: Optional[str] = None
    manager_confirmation: Optional[str] = None
    closing_remarks: Optional[str] = None
    closed_by: Optional[str] = None
    closed_at: Optional[datetime] = None
    closed_signature: Optional[str] = None


# ─── CAN ───

class CANCreate(CANFormFields):
    hazard_id: str = Field(...)
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10)
    required_action: str = Field(...)
    target_completion_date: datetime = Field(...)
    assigned_to: str = Field(...)
    assigned_to_uid: Optional[str] = None
    department: Optional[str] = None
    priority: str = Field(..., pattern="^(High|Medium|Low)$")
    psoe_assessment_id: Optional[str] = None


class CANUpdate(CANFormFields):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = Field(None, min_length=10)
    required_action: Optional[str] = None
    target_completion_date: Optional[datetime] = None
    assigned_to: Optional[str] = None
    assigned_to_uid: Optional[str] = None
    department: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[CANStatus] = None
    process_owner: Optional[str] = None


class CANResponse(CANFormFields, CAPFormFields):
    id: str
    can_reference: str
    hazard_id: str
    title: str
    description: str
    required_action: str
    issued_by: str
    issued_by_uid: str
    issued_at: Optional[datetime] = None
    target_completion_date: Optional[datetime] = None
    assigned_to: str
    assigned_to_uid: str
    department: Optional[str] = None
    priority: str
    status: str
    tenant_id: str
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    psoe_assessment_id: Optional[str] = None
    latest_cap: Optional[dict] = None

    model_config = {"from_attributes": True}


class CANListItem(CANFormFields):
    id: str
    can_reference: str
    hazard_id: str
    title: str
    priority: str
    status: str
    assigned_to: str
    target_completion_date: Optional[datetime] = None
    issued_at: Optional[datetime] = None


# ─── CAP ───

class CAPCreate(CAPFormFields):
    can_id: str = Field(...)
    action_plan: str = Field(..., min_length=10)
    timeline: str = Field(...)
    resources_required: Optional[str] = None
    implementation_plan: Optional[str] = None
    department: Optional[str] = None
    target_completion_date: datetime = Field(...)


class CAPUpdate(CAPFormFields):
    status: Optional[CAPStatus] = None
    action_plan: Optional[str] = None
    timeline: Optional[str] = None
    resources_required: Optional[str] = None
    implementation_plan: Optional[str] = None
    target_completion_date: Optional[datetime] = None
    review_comments: Optional[str] = None


class CAPReview(CAPFormFields):
    status: CAPStatus
    comments: Optional[str] = None
    revision_deadline: Optional[datetime] = None


class CAPResponse(CAPFormFields):
    id: str
    can_id: str
    cap_reference: str
    action_plan: str
    timeline: str
    resources_required: Optional[str] = None
    implementation_plan: Optional[str] = None
    submitted_by: str
    submitted_by_uid: str
    department: Optional[str] = None
    submitted_at: Optional[datetime] = None
    target_completion_date: Optional[datetime] = None
    status: str
    reviewed_by: Optional[str] = None
    reviewed_by_uid: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_comments: Optional[str] = None
    revision_deadline: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
