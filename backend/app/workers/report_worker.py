from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from app.repositories.audit_repo import (
    list_recent_dispatches,
    log_retry_attempt,
    record_dispatch_intent,
    update_dispatch_status,
)
from app.services.dlq_service import DlqService
from app.services.pdf_generator import CaanPdfGenerator


def generate_and_record_ssp_pdf(
    report_data: Dict[str, Any],
    regulator_id: str,
    dispatched_by_user: str,
    reporting_year: int,
    reporting_quarter: Optional[int] = None,
    recipients: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Generate a CAAN SSP oversight PDF and record the dispatch intent
    in the audit log. Returns audit metadata including the SHA-256 checksum."""
    pdf_bytes = CaanPdfGenerator.build_ssp_report_pdf(report_data)
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    audit_id = f"audit-{regulator_id}-{reporting_year}"
    if reporting_quarter:
        audit_id += f"Q{reporting_quarter}"

    record_dispatch_intent(
        audit_id=audit_id,
        regulator_id=regulator_id,
        dispatched_by_user=dispatched_by_user,
        reporting_year=reporting_year,
        reporting_quarter=reporting_quarter,
        recipients=recipients or [],
        pdf_sha256_checksum=sha256,
    )

    return {
        "audit_id": audit_id,
        "pdf_sha256": sha256,
        "pdf_size_bytes": len(pdf_bytes),
        "recipients": recipients or [],
    }
