from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum


class VerificationOutcome(str, Enum):
    ACCEPTED = "Accepted"
    REVISION_REQUIRED = "Revision Required"
    INEFFECTIVE = "Ineffective"
    OVERDUE = "Overdue"


class VerificationCreate(BaseModel):
    hazard_id: str = Field(...)
    cap_id: str = Field(...)
    outcome: VerificationOutcome = Field(...)
    comments: Optional[str] = None
    evidence: Optional[List[str]] = None
    verification_date: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    revision_deadline: Optional[datetime] = None
    revision_notes: Optional[str] = None


class VerificationResponse(BaseModel):
    id: str
    hazard_id: str
    cap_id: str
    outcome: VerificationOutcome
    comments: Optional[str] = None
    evidence: List[str] = []
    verified_by: str
    verified_by_uid: str
    verification_date: datetime
    revision_deadline: Optional[datetime] = None
    revision_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClosureCreate(BaseModel):
    hazard_id: str = Field(...)
    lessons_learned: Optional[str] = None
    recommendations: Optional[str] = None
    approval_notes: Optional[str] = None


class ClosureResponse(BaseModel):
    id: str
    hazard_id: str
    lessons_learned: Optional[str] = None
    recommendations: Optional[str] = None
    approval_notes: Optional[str] = None
    approved_by: str
    approved_by_uid: str
    approved_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReopenRequest(BaseModel):
    reason: str = Field(..., min_length=5)


class VerificationStats(BaseModel):
    pending_verification: int = 0
    under_verification: int = 0
    verified: int = 0
    pending_closure: int = 0
    closed: int = 0
    reopened: int = 0
