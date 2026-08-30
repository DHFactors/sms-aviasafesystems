# ==============================================================================
# File: backend/app/schemas/hazard_rca.py
# Description: Pydantic schemas for Hazard Tracking, ICAO Doc 9859 Risk Assessment,
#              and DoD HFACS 7.0 Root Cause Analysis (RCA).
# ==============================================================================

from typing import List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field

# HFACS 7.0 Categories and RCA Factors
HFACSCategory = Literal["ACT", "PRECOND", "SUPER", "ORG"]

class RCAFactorCreate(BaseModel):
    tier: int = Field(..., ge=1, le=4, description="1: Acts, 2: Preconditions, 3: Supervision, 4: Organization")
    category: HFACSCategory
    subcategory: str
    nanocode: str = Field(..., min_length=5, max_length=6, example="PE101")
    definition: str
    contributing_narrative: str = Field(..., min_length=5)
    order_sequence: int = 1


class RCAFactorResponse(RCAFactorCreate):
    id: str
    hazard_id: str
    created_at: datetime


# ICAO 5x5 Risk Assessment Matrix Models
RiskSeverity = Literal[1, 2, 3, 4, 5]
RiskProbability = Literal["A", "B", "C", "D", "E"]
RiskTolerability = Literal["acceptable", "tolerable", "intolerable"]

class RiskAssessmentCreate(BaseModel):
    assessment_type: Literal["initial", "residual", "periodic_review"] = "initial"
    severity_score: RiskSeverity
    severity_justification: str
    probability_score: RiskProbability
    probability_justification: str
    matrix_version: str = "ICAO_5X5_STANDARD"


class RiskAssessmentResponse(BaseModel):
    id: str
    hazard_id: str
    assessment_type: str
    severity_score: int
    severity_label: str
    probability_score: str
    probability_label: str
    risk_index: str
    tolerability: RiskTolerability
    assessed_by: str
    assessed_at: datetime


# Corrective and Preventive Action (CAPA) Models
class CAPACreate(BaseModel):
    linked_rca_nanocodes: List[str] = Field(default_factory=list)
    action_type: Literal["corrective", "preventive", "training", "procedural"]
    title: str = Field(..., min_length=3, max_length=200)
    details: str = Field(..., min_length=10)
    responsible_department: str
    assignee_email: str
    due_date: datetime


class CAPAResponse(CAPACreate):
    id: str
    hazard_id: str
    status: Literal["draft", "pending_implementation", "implemented", "verified_effective"]
    implemented_at: Optional[datetime] = None
    verified_by: Optional[str] = None
    created_at: datetime


# Root Hazard Document Models
HazardStatus = Literal["open", "under_assessment", "mitigated", "closed", "monitored"]
FunctionalArea = Literal["flight_operations", "maintenance_145", "camo", "ground_ops"]

class HazardCreate(BaseModel):
    title: str = Field(..., min_length=5, max_length=250)
    description: str = Field(..., min_length=15)
    source_type: Literal["occurrence", "audit", "voluntary_report", "spas_trend"]
    source_reference_id: Optional[str] = None
    functional_area: FunctionalArea
    assigned_owner_email: str
    target_completion_date: Optional[datetime] = None


class HazardResponse(BaseModel):
    id: str
    tenant_id: str
    title: str
    description: str
    status: HazardStatus
    source_type: str
    source_reference_id: Optional[str] = None
    functional_area: FunctionalArea
    initial_risk_index: Optional[str] = None
    initial_risk_level: Optional[str] = None
    residual_risk_index: Optional[str] = None
    residual_risk_level: Optional[str] = None
    primary_hfacs_category: Optional[str] = None
    tagged_nanocodes: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None