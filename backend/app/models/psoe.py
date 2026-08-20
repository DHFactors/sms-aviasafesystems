# ============================================================================
# FILE: psoe.py
# PATH: backend/app/models/psoe.py
# PURPOSE: Data models for the PSOE Audit & Surveillance module (Phase 3
#          Step 2A). Aligned with the CAAN SMS Procedure Manual Appendix 10
#          four-component surveillance checklist (Safety Policy & Objectives,
#          Safety Risk Management, Safety Assurance, Safety Promotion).
# ============================================================================

from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class PSOEComponentKey(str, Enum):
    """The four CAAN Appendix 10 SMS components (ICAO Annex 19 aligned)."""

    SAFETY_POLICY = "component_1"
    SAFETY_RISK_MANAGEMENT = "component_2"
    SAFETY_ASSURANCE = "component_3"
    SAFETY_PROMOTION = "component_4"


class PSOEQuestion(BaseModel):
    """A single Appendix 10 surveillance question within a component.

    ``score`` uses the CAAN/ICAO implementation scale:
      0 = Not Implemented / Non-Compliant
      1 = Partially Implemented (Documented only)
      2 = Implemented & Operational
      3 = Fully Effective & Continuous Improvement
      None (``is_na``) = Not Applicable — excluded from the denominator.
    """

    id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    guidance: Optional[str] = None
    component: Optional[str] = None
    allow_na: bool = True
    max_score: int = Field(3, ge=1, le=3)


class PSOECategory(BaseModel):
    """A component (category) of the Appendix 10 template with its questions."""

    id: str
    name: str
    key: Optional[str] = None
    weight: int = Field(..., ge=0, le=100)
    questions: List[PSOEQuestion] = Field(default_factory=list)


class PSOETemplate(BaseModel):
    """The full Appendix 10 surveillance template (version + components)."""

    version: str
    source: str
    scoring_scale: Dict[str, str] = Field(default_factory=dict)
    components: List[PSOECategory] = Field(default_factory=list)

    @property
    def total_weight(self) -> int:
        return sum(c.weight for c in self.components)

    def question_map(self) -> Dict[str, PSOEQuestion]:
        """Return a lookup of question id -> question across all components."""
        return {q.id: q for c in self.components for q in c.questions}


class PSOEAnswer(BaseModel):
    """A single response to a template question within an assessment."""

    question_id: str = Field(..., min_length=1)
    score: Optional[int] = Field(None, ge=0, le=3, description="0-3 CAAN/ICAO scale; None when N/A")
    is_na: bool = False
    comment: Optional[str] = None
    evidence: Optional[str] = None

    @model_validator(mode="after")
    def _check_score_na(self):
        if self.is_na and self.score is not None:
            raise ValueError("A numeric score cannot be combined with is_na=True")
        return self


class PSOEAssessmentCreate(BaseModel):
    """Payload to draft a new PSOE assessment."""

    title: str = Field(..., min_length=3, max_length=200)
    tenant_id: Optional[str] = Field(None, description="Target tenant (required for CAAN_SMD / SUPER_ADMIN; ignored for tenant-bound roles)")
    department: Optional[str] = None
    scope: Optional[str] = None
    auditor_name: Optional[str] = None
    assessor_email: Optional[str] = None
    assessment_date: Optional[datetime] = None
    template_version: str = "1.0.0"
    responses: List[PSOEAnswer] = Field(default_factory=list)
    notes: Optional[str] = None


class PSOEAssessmentUpdate(BaseModel):
    """Payload to update an existing PSOE assessment."""

    title: Optional[str] = Field(None, min_length=3, max_length=200)
    department: Optional[str] = None
    scope: Optional[str] = None
    auditor_name: Optional[str] = None
    assessor_email: Optional[str] = None
    assessment_date: Optional[datetime] = None
    status: Optional[str] = Field(None, pattern="^(draft|in_progress|submitted|completed|closed)$")
    responses: Optional[List[PSOEAnswer]] = None
    notes: Optional[str] = None


class PSOEAssessment(BaseModel):
    """A persisted PSOE assessment document."""

    id: str
    tenant_id: str
    title: str
    status: str = "draft"
    department: Optional[str] = None
    scope: Optional[str] = None
    auditor_name: Optional[str] = None
    assessor_email: Optional[str] = None
    assessment_date: Optional[datetime] = None
    template_version: str
    responses: List[PSOEAnswer] = Field(default_factory=list)
    component_scores: Dict[str, Any] = Field(default_factory=dict)
    overall_score_pct: Optional[float] = None
    overall_level: Optional[str] = None
    created_by: Optional[str] = None
    created_by_uid: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class PSOEAssessmentListItem(BaseModel):
    """Summary view of an assessment for the list endpoint."""

    id: str
    tenant_id: str
    title: str
    status: str
    department: Optional[str] = None
    scope: Optional[str] = None
    auditor_name: Optional[str] = None
    assessment_date: Optional[datetime] = None
    template_version: Optional[str] = None
    overall_score_pct: Optional[float] = None
    overall_level: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None