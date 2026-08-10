from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class HazardStatus(str, Enum):
    OPEN = "Open"
    PROCESSING = "Processing"
    UNDER_REVIEW = "Under Review"
    PENDING_CLOSURE = "Pending Closure"
    CLOSED = "Closed"
    REOPENED = "Reopened"


class HazardPriority(str, Enum):
    HIGH = "H"
    MEDIUM = "M"
    LOW = "L"


class HazardTaxonomy(str, Enum):
    ORGANIZATIONAL_FACILITIES = "Organizational-Facilities"
    ORGANIZATIONAL_DOCUMENTATION = "Organizational-Documentation, Processes and Procedures"
    TECHNICAL = "Technical"
    WILDLIFE = "Wildlife"
    HUMAN_FACTORS = "Human Factors"
    ENVIRONMENTAL = "Environmental"
    OTHER = "Other"


class HazardSource(str, Enum):
    VSR = "VSR"
    MOR = "MOR"
    QUALITY_AUDIT = "Quality Audit"
    SAFETY_INSPECTION = "Safety Inspection"
    FLIGHT_DIVERSION = "Flight Diversion"
    CAAN_AUDIT = "CAAN Audit"
    INTERNAL_AUDIT = "Internal Audit"
    SAFETY_SURVEY = "Safety Survey"
    IOR = "IOR"
    MOC = "MOC"
    SRM_REQUEST = "SRM Request"
    INCIDENT = "Incident"


HAZARD_CREATION_SOURCES = {
    "VSR",
    "MOR",
    "Internal Audit",
    "Quality Audit",
    "CAAN Audit",
    "Flight Diversion",
}


class HazardCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10)
    source: HazardSource = Field(...)
    source_id: str = Field(...)
    source_url: Optional[str] = None

    adrep_category: Optional[str] = None
    occurrence_type: Optional[str] = None
    taxonomy: HazardTaxonomy = Field(...)
    taxonomy_specific: Optional[str] = None

    consequence: Optional[str] = None

    severity: Optional[int] = Field(None, ge=1, le=5)
    probability: Optional[int] = Field(None, ge=1, le=5)
    risk_index: Optional[int] = None
    risk_level: Optional[str] = None
    risk_outcome: Optional[str] = None

    priority: HazardPriority = Field(...)

    recommended_action: Optional[str] = None
    corrective_action: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_to_uid: Optional[str] = None
    department: Optional[str] = None

    srm_conducted: bool = False
    srm_date: Optional[datetime] = None
    srm_status: Optional[str] = None

    status: HazardStatus = HazardStatus.OPEN
    follow_up_date: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    closed_by: Optional[str] = None

    tenant_id: str = Field(...)

    remarks: Optional[str] = None


class HazardUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = Field(None, min_length=10)
    source: Optional[HazardSource] = None
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    adrep_category: Optional[str] = None
    occurrence_type: Optional[str] = None
    taxonomy: Optional[HazardTaxonomy] = None
    taxonomy_specific: Optional[str] = None
    consequence: Optional[str] = None
    severity: Optional[int] = Field(None, ge=1, le=5)
    probability: Optional[int] = Field(None, ge=1, le=5)
    risk_index: Optional[int] = None
    risk_level: Optional[str] = None
    risk_outcome: Optional[str] = None
    priority: Optional[HazardPriority] = None
    recommended_action: Optional[str] = None
    corrective_action: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_to_uid: Optional[str] = None
    department: Optional[str] = None
    srm_conducted: Optional[bool] = None
    srm_date: Optional[datetime] = None
    srm_status: Optional[str] = None
    follow_up_date: Optional[datetime] = None
    remarks: Optional[str] = None


class HazardResponse(BaseModel):
    id: str
    hazard_id: str
    title: str
    description: str
    source: HazardSource
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    adrep_category: Optional[str] = None
    occurrence_type: Optional[str] = None
    taxonomy: HazardTaxonomy
    taxonomy_specific: Optional[str] = None
    consequence: Optional[str] = None
    severity: Optional[int] = None
    probability: Optional[int] = None
    risk_index: Optional[int] = None
    risk_level: Optional[str] = None
    risk_outcome: Optional[str] = None
    priority: HazardPriority
    recommended_action: Optional[str] = None
    corrective_action: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_to_uid: Optional[str] = None
    department: Optional[str] = None
    srm_conducted: bool = False
    srm_date: Optional[datetime] = None
    srm_status: Optional[str] = None
    status: HazardStatus
    follow_up_date: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    closed_by: Optional[str] = None
    tenant_id: str
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    remarks: Optional[str] = None

    model_config = {"from_attributes": True}


class HazardListItem(BaseModel):
    id: str
    hazard_id: str
    title: str
    source: HazardSource
    taxonomy: HazardTaxonomy
    priority: HazardPriority
    risk_level: Optional[str] = None
    status: HazardStatus
    assigned_to: Optional[str] = None
    department: Optional[str] = None
    created_at: Optional[datetime] = None
    severity: Optional[int] = None
    probability: Optional[int] = None
    risk_index: Optional[int] = None
