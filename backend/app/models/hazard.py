from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
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


class AnalysisMode(str, Enum):
    FISHBONE_ONLY = "FISHBONE_ONLY"
    BOWTIE_SRAM = "BOWTIE_SRAM"
    COMBINED = "COMBINED"


# ── SRAM (CAAN CAR-19) models ───────────────────────────────────────────────


class SeverityInput(BaseModel):
    """7-impact severity inputs, each rated 0-5."""

    pax: int = Field(0, ge=0, le=5)
    worker: int = Field(0, ge=0, le=5)
    quality: int = Field(0, ge=0, le=5)
    asset: int = Field(0, ge=0, le=5)
    rep: int = Field(0, ge=0, le=5)
    sec: int = Field(0, ge=0, le=5)
    env: int = Field(0, ge=0, le=5)


class BarrierQuality(BaseModel):
    """Barrier Quality Value assessment, each criterion rated 1-5."""

    effectiveness: int = Field(1, ge=1, le=5)
    cost_benefit: int = Field(1, ge=1, le=5)
    practicality: int = Field(1, ge=1, le=5)
    acceptability: int = Field(1, ge=1, le=5)
    enforceability: int = Field(1, ge=1, le=5)
    durability: int = Field(1, ge=1, le=5)
    disinclination: int = Field(1, ge=1, le=5)


class BarrierConfig(BaseModel):
    """A single Bow-Tie barrier (ECM/NCM/ERB/NRB)."""

    id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    category: Optional[str] = None
    quality: Optional[BarrierQuality] = None
    bqv: Optional[int] = Field(None, ge=0, le=50)
    bsv: int = Field(0, ge=0, le=5)
    robustness: Optional[str] = None
    source_root_cause_id: Optional[str] = None  # Combined mode: promoted fishbone cause


class SramBarriers(BaseModel):
    ecb: List[BarrierConfig] = Field(default_factory=list)
    erb: List[BarrierConfig] = Field(default_factory=list)
    ncb: List[BarrierConfig] = Field(default_factory=list)
    nrb: List[BarrierConfig] = Field(default_factory=list)


class BowtieElement(BaseModel):
    id: Optional[str] = None
    label: str
    barrier_ids: Optional[List[str]] = None


class BowtieConfig(BaseModel):
    threats: List[BowtieElement] = Field(default_factory=list)
    top_event: Optional[str] = None
    consequences: List[BowtieElement] = Field(default_factory=list)


class SramCalculateRequest(BaseModel):
    severity: SeverityInput
    barriers: SramBarriers = Field(default_factory=SramBarriers)
    bowtie: Optional[BowtieConfig] = None


class SramData(BaseModel):
    severity: Dict[str, Any] = Field(default_factory=dict)
    barriers: SramBarriers = Field(default_factory=SramBarriers)
    risk_profile: Dict[str, Any] = Field(default_factory=dict)
    bowtie: BowtieConfig = Field(default_factory=BowtieConfig)
    fishbone: Optional[Dict[str, Any]] = None
    signoffs: Dict[str, Any] = Field(default_factory=dict)


class SramSaveRequest(BaseModel):
    analysis_mode: AnalysisMode
    sram_data: SramData


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
    tolerability_tier: Optional[str] = None

    priority: HazardPriority = Field(...)

    recommended_action: Optional[str] = None
    corrective_action: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_to_uid: Optional[str] = None
    department: Optional[str] = None

    srm_conducted: bool = False
    srm_date: Optional[datetime] = None
    srm_status: Optional[str] = None
    analysis_mode: AnalysisMode = AnalysisMode.FISHBONE_ONLY
    sram_data: Optional[Dict[str, Any]] = None

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
    tolerability_tier: Optional[str] = None
    priority: Optional[HazardPriority] = None
    recommended_action: Optional[str] = None
    corrective_action: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_to_uid: Optional[str] = None
    department: Optional[str] = None
    srm_conducted: Optional[bool] = None
    srm_date: Optional[datetime] = None
    srm_status: Optional[str] = None
    analysis_mode: Optional[AnalysisMode] = None
    sram_data: Optional[Dict[str, Any]] = None
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
    tolerability_tier: Optional[str] = None
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
    tolerability_tier: Optional[str] = None
    status: HazardStatus
    assigned_to: Optional[str] = None
    department: Optional[str] = None
    created_at: Optional[datetime] = None
    severity: Optional[int] = None
    probability: Optional[int] = None
    risk_index: Optional[int] = None
