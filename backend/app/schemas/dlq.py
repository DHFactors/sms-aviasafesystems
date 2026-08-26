from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class DlqResolutionStatus(str, Enum):
    UNRESOLVED = "unresolved"
    INVESTIGATING = "investigating"
    REPLAYED = "replayed"
    DISCARDED = "discarded"


class DeadLetterRecord(BaseModel):
    dlq_id: str
    original_operation: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    attempt_count: int = 0
    max_attempts: int = 3
    resolution_status: DlqResolutionStatus = DlqResolutionStatus.UNRESOLVED
    resolution_note: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
