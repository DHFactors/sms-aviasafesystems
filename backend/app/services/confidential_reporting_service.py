# ============================================================================
# FILE: confidential_reporting_service.py
# PATH: backend/app/services/confidential_reporting_service.py
# PURPOSE: Module C §5.2.4 (DP-4, P2-25) — confidential / voluntary reporting
#          class. Adds a confidentiality flag + designated custodian to a
#          Module B report; reporter identity is visible ONLY to the custodian
#          (Appendix 3 protection) and downstream consumers see a de-identified
#          projection.
# ============================================================================

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import select

from app.db.db_models import Report
from app.db.runner import run
from app.db.session import session_scope
from app.services.actor import resolve_actor_uuid
from app.services.audit_service import log_audit

# Roles permitted to act as / view a custodian's protected data.
CUSTODIAN_ROLES = {"TENANT_ADMIN", "AIRLINE_ADMIN", "SUPER_ADMIN"}

# Reporter-identity fields stripped by de-identification.
_IDENTITY_FIELDS = ("reporter_name", "reporter_email", "reporter_phone",
                    "reporter_role", "reporter_organisation")


def _to_uuid(value: Any) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


class ConfidentialReportingService:
    """DP-4 confidential reporting — flag + custodian access control."""

    def __init__(self, tenant_id: Optional[str] = None):
        self.tenant_id = tenant_id

    # -- public -------------------------------------------------------------

    def mark_confidential(self, report_id: str, custodian: Dict[str, Any],
                          user: Dict[str, Any]) -> Dict[str, Any]:
        return run(self._mark_async(report_id, custodian, user))

    def can_view_reporter_identity(self, report: Any,
                                   user: Dict[str, Any]) -> bool:
        if not getattr(report, "is_confidential", False) and not (
            isinstance(report, dict) and report.get("is_confidential")
        ):
            return True
        role = (user or {}).get("role")
        if role == "SUPER_ADMIN":
            return True
        if role not in CUSTODIAN_ROLES:
            return False
        custodian_id = (report.get("confidential_custodian_id")
                        if isinstance(report, dict)
                        else getattr(report, "confidential_custodian_id", None))
        if custodian_id is None:
            # Confidential but no designated custodian yet: custodian roles only.
            return True
        actor = self._resolve_actor_sync(user)
        return actor is not None and str(actor) == str(custodian_id)

    def deidentify(self, report: Any) -> Dict[str, Any]:
        """Return a reporter-identity-free projection for downstream use."""
        if isinstance(report, dict):
            data = dict(report)
        else:
            data = {c.name: getattr(report, c.name) for c in report.__table__.columns}
        for field in _IDENTITY_FIELDS:
            data[field] = None
        data["is_anonymous"] = True
        data["reporter_identity_protected"] = True
        return data

    def get_for_downstream(self, report_id: str,
                           user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return run(self._downstream_async(report_id, user))

    # -- internals ----------------------------------------------------------

    def _resolve_actor_sync(self, user):
        try:
            return run(resolve_actor_uuid(user))
        except Exception:
            return None

    async def _mark_async(self, report_id, custodian, user):
        cid = await resolve_actor_uuid(custodian)
        now = datetime.now(timezone.utc)
        async with session_scope() as session:
            row = (await session.execute(
                select(Report).where(Report.id == _to_uuid(report_id))
            )).scalars().first()
            if not row:
                raise ValueError(f"Report {report_id!r} not found")
            row.is_confidential = True
            row.confidential_custodian_id = cid
            row.updated_at = now
            await session.flush()
            result = {
                "id": str(row.id),
                "is_confidential": True,
                "confidential_custodian_id": str(cid) if cid else None,
            }
        log_audit(
            action="REPORT_MARKED_CONFIDENTIAL",
            user=(user or {}).get("email") or (user or {}).get("uid"),
            tenant_id=self.tenant_id,
            target_type="report",
            target_id=str(report_id),
            metadata={"custodian_id": result["confidential_custodian_id"]},
        )
        logger.info(f"Report {report_id} marked confidential (custodian={cid})")
        return result

    async def _downstream_async(self, report_id, user):
        async with session_scope() as session:
            row = (await session.execute(
                select(Report).where(Report.id == _to_uuid(report_id))
            )).scalars().first()
            if not row:
                return None
            if row.is_confidential and not self.can_view_reporter_identity(row, user):
                log_audit(
                    action="CAAN_READ_REPORT_DEIDENTIFIED",
                    user=(user or {}).get("email") or (user or {}).get("uid"),
                    tenant_id=self.tenant_id,
                    target_type="report",
                    target_id=str(report_id),
                    metadata={"deidentified": True},
                )
                return self.deidentify(row)
            return {c.name: (str(getattr(row, c.name))
                             if isinstance(getattr(row, c.name), uuid.UUID)
                             else getattr(row, c.name))
                    for c in row.__table__.columns}
