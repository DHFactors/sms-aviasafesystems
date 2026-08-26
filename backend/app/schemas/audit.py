from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class DispatchStatus(str, Enum):
    PENDING = "pending"
    RETRYING = "retrying"
    DELIVERED = "delivered"
    FAILED = "failed"


class RegulatoryReportAuditLog(BaseModel):
    audit_id: str
    regulator_id: str
    dispatched_by_user: str
    reporting_year: int
    reporting_quarter: Optional[int] = None
    recipients: List[str] = Field(default_factory=list)
    pdf_sha256_checksum: Optional[str] = None
    attempt_count: int = 0
    status: DispatchStatus = DispatchStatus.PENDING
    last_attempt_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
