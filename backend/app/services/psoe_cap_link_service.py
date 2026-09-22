# ============================================================================
# FILE: psoe_cap_link_service.py
# PATH: backend/app/services/psoe_cap_link_service.py
# PURPOSE: Module C §14 (Q4.1b, SN-C10) — optional, manual, bidirectional
#          PSOE finding ↔ CAP linkage. Both sides are updated in one
#          transaction (psoe_findings.cap_id + caps.source_psoe_finding_id).
# ============================================================================

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import select

from app.db.db_models import Cap, PsoeFinding
from app.db.runner import run
from app.db.session import session_scope
from app.services.audit_service import log_audit


def _to_uuid(value: Any) -> uuid.UUID:
    return uuid.UUID(str(value))


class PsoeCapLinkService:
    """Bidirectional PSOE finding ↔ CAP linkage."""

    def __init__(self, tenant_id: Optional[str] = None):
        self.tenant_id = tenant_id

    # -- public -------------------------------------------------------------

    def link_finding_to_cap(self, finding_id: str, cap_id: str,
                            user: Dict[str, Any]) -> Dict[str, Any]:
        return run(self._link_async(finding_id, cap_id, user))

    def unlink_finding_from_cap(self, finding_id: str,
                                user: Dict[str, Any]) -> Dict[str, Any]:
        return run(self._unlink_async(finding_id, user))

    def list_links_for_finding(self, finding_id: str) -> Dict[str, Any]:
        return run(self._for_finding_async(finding_id))

    def list_links_for_cap(self, cap_id: str) -> Dict[str, Any]:
        return run(self._for_cap_async(cap_id))

    # -- internals ----------------------------------------------------------

    async def _link_async(self, finding_id, cap_id, user):
        async with session_scope() as session:
            finding = (await session.execute(
                select(PsoeFinding).where(PsoeFinding.id == _to_uuid(finding_id))
            )).scalars().first()
            if not finding:
                raise ValueError(f"PSOE finding {finding_id!r} not found")
            cap = (await session.execute(
                select(Cap).where(Cap.id == _to_uuid(cap_id))
            )).scalars().first()
            if not cap:
                raise ValueError(f"CAP {cap_id!r} not found")

            # Both sides updated in the same transaction.
            finding.cap_id = cap.id
            cap.source_psoe_finding_id = finding.id
            cap.updated_at = datetime.now(timezone.utc)
            await session.flush()
            result = {"finding_id": str(finding.id), "cap_id": str(cap.id)}

        log_audit(
            action="PSOE_CAP_LINKED",
            user=(user or {}).get("email") or (user or {}).get("uid"),
            tenant_id=self.tenant_id,
            target_type="psoe_finding",
            target_id=result["finding_id"],
            metadata={"cap_id": result["cap_id"]},
        )
        logger.info(f"PSOE finding {finding_id} linked to CAP {cap_id}")
        return result

    async def _unlink_async(self, finding_id, user):
        async with session_scope() as session:
            finding = (await session.execute(
                select(PsoeFinding).where(PsoeFinding.id == _to_uuid(finding_id))
            )).scalars().first()
            if not finding:
                raise ValueError(f"PSOE finding {finding_id!r} not found")
            cap_id = finding.cap_id
            finding.cap_id = None
            if cap_id is not None:
                cap = (await session.execute(
                    select(Cap).where(Cap.id == cap_id)
                )).scalars().first()
                if cap is not None and cap.source_psoe_finding_id == finding.id:
                    cap.source_psoe_finding_id = None
                    cap.updated_at = datetime.now(timezone.utc)
            await session.flush()
            result = {"finding_id": str(finding.id), "cap_id": None}

        log_audit(
            action="PSOE_CAP_UNLINKED",
            user=(user or {}).get("email") or (user or {}).get("uid"),
            tenant_id=self.tenant_id,
            target_type="psoe_finding",
            target_id=result["finding_id"],
            metadata={},
        )
        return result

    async def _for_finding_async(self, finding_id):
        async with session_scope() as session:
            finding = (await session.execute(
                select(PsoeFinding).where(PsoeFinding.id == _to_uuid(finding_id))
            )).scalars().first()
            if not finding:
                return {"finding_id": str(finding_id), "cap_id": None}
            return {"finding_id": str(finding.id),
                    "cap_id": str(finding.cap_id) if finding.cap_id else None}

    async def _for_cap_async(self, cap_id):
        async with session_scope() as session:
            cap = (await session.execute(
                select(Cap).where(Cap.id == _to_uuid(cap_id))
            )).scalars().first()
            if not cap:
                return {"cap_id": str(cap_id), "finding_id": None}
            return {"cap_id": str(cap.id),
                    "finding_id": str(cap.source_psoe_finding_id)
                    if cap.source_psoe_finding_id else None}
