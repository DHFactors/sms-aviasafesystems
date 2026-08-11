from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


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
    """Optional issuance block of the Corrective Action Notice (FORM SMSM 8.8.2)."""
    copies_to: Optional[str] = None
    requested_function: Optional[str] = None
    addressed_function: Optional[str] = None
    initial_severity: Optional[int] = Field(None, ge=1, le=5)
    initial_probability: Optional[int] = Field(None, ge=1, le=5)
    initial_risk_index: Optional[int] = Field(None, ge=1, le=25)
    classification_type: Optional[str] = None
    classification_level: Optional[str] = None


class CAPFormFields(BaseModel):
    """Optional corrective action / closure block (FORM SMSM 8.8.2)."""
    rca: Optional[str] = None
    residual_severity: Optional[int] = Field(None, ge=1, le=5)
    residual_probability: Optional[int] = Field(None, ge=1, le=5)
    residual_risk_index: Optional[int] = Field(None, ge=1, le=25)
    residual_risk_level: Optional[str] = None
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
