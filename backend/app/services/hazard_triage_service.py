# ============================================================================
# FILE: hazard_triage_service.py
# PATH: backend/app/services/hazard_triage_service.py
# PURPOSE: Module B §26 — human triage at hazard intake (accept / reject /
#          duplicate / escalate), reversible with audit (SN13 Decision 2).
# ============================================================================

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import or_, select

from app.core.config import settings
from app.db.db_models import Hazard, HazardTriage
from app.db.ids import register_tenant, tenant_slug
from app.db.isolation import demo_scope
from app.db.runner import run
from app.db.session import session_scope
from app.services.actor import resolve_actor_uuid
from app.services.audit_service import log_audit

TRIAGE_DECISIONS = ("Accepted", "Rejected", "Duplicate", "Escalated")

# Reversal requires the safety-manager capability (SN13 Decision 2).
SAFETY_MANAGER_ROLES = {"TENANT_ADMIN", "AIRLINE_ADMIN"}


def _row_to_dict(row: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for col in row.__table__.columns:
        value = getattr(row, col.name)
        if isinstance(value, uuid.UUID):
            value = str(value)
        elif isinstance(value, datetime):
            value = value.isoformat()
        data[col.name] = value
    return data


async def _lookup_hazard(session, tid: str, ref: str) -> Optional[Hazard]:
    conds = [Hazard.hazard_id == str(ref)]
    try:
        conds.append(Hazard.id == uuid.UUID(str(ref)))
    except (ValueError, TypeError, AttributeError):
        pass
    return (await session.execute(
        select(Hazard)
        .where(Hazard.tenant_id == uuid.UUID(tid), Hazard.is_demo == demo_scope(), or_(*conds))
        .limit(1)
    )).scalars().first()


class HazardTriageService:
    """Persistence + audit for hazard triage decisions."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    # -- public -------------------------------------------------------------

    def triage_hazard(self, hazard_id: str, user: Dict[str, Any], decision: str,
                      notes: Optional[str] = None,
                      initial_priority: Optional[str] = None) -> Dict[str, Any]:
        return run(self._triage_async(hazard_id, user, decision, notes, initial_priority))

    def reverse_triage(self, triage_id: str, user: Dict[str, Any],
                       reason: str) -> Dict[str, Any]:
        return run(self._reverse_async(triage_id, user, reason))

    def list_triage(self, hazard_id: str) -> List[Dict[str, Any]]:
        return run(self._list_async(hazard_id))

    # -- internals ----------------------------------------------------------

    async def _triage_async(self, hazard_id, user, decision, notes, initial_priority):
        if decision not in TRIAGE_DECISIONS:
            raise ValueError(f"decision must be one of {TRIAGE_DECISIONS}")
        tid = register_tenant(self.tenant_id)
        actor = await resolve_actor_uuid(user)
        now = datetime.now(timezone.utc)

        async with session_scope() as session:
            hazard = await _lookup_hazard(session, tid, hazard_id)
            if not hazard:
                raise ValueError(f"Hazard {hazard_id!r} not found for tenant {self.tenant_id}")

            row = HazardTriage(
                tenant_id=uuid.UUID(tid),
                hazard_id=hazard.id,
                triaged_by=actor,
                triaged_at=now,
                decision=decision,
                notes=notes,
                initial_priority=initial_priority,
            )
            session.add(row)

            # §26.5 decision outcomes.
            if decision == "Rejected":
                hazard.status = "Closed"
                hazard.closed_at = now
                hazard.closed_by = (user or {}).get("email") or (user or {}).get("uid")
            elif decision == "Duplicate":
                hazard.status = "Closed"
                hazard.closed_at = now
                hazard.closed_by = (user or {}).get("email") or (user or {}).get("uid")
            elif decision == "Escalated":
                hazard.priority = "H"
                hazard.priority_date = now
            hazard.updated_at = now
            await session.flush()
            result = _row_to_dict(row)
            result["tenant_id"] = tenant_slug(result["tenant_id"])
            hazard_ref = hazard.hazard_id

        log_audit(
            action="TRIAGE_DECIDED",
            user=(user or {}).get("email") or (user or {}).get("uid"),
            tenant_id=self.tenant_id,
            target_type="hazard",
            target_id=hazard_ref,
            metadata={"decision": decision, "triage_id": result["id"], "notes": notes},
        )
        logger.info(f"Hazard {hazard_ref} triaged '{decision}' for tenant {self.tenant_id}")
        return result

    async def _reverse_async(self, triage_id, user, reason):
        role = (user or {}).get("role")
        if role not in SAFETY_MANAGER_ROLES:
            raise PermissionError(
                f"Triage reversal requires one of {sorted(SAFETY_MANAGER_ROLES)}; {role!r} is not authorised"
            )
        if not (reason or "").strip():
            raise ValueError("reversal_reason is required")
        tid = register_tenant(self.tenant_id)
        actor = await resolve_actor_uuid(user)
        now = datetime.now(timezone.utc)

        async with session_scope() as session:
            original = (await session.execute(
                select(HazardTriage).where(
                    HazardTriage.id == uuid.UUID(str(triage_id)),
                    HazardTriage.tenant_id == uuid.UUID(tid),
                )
            )).scalars().first()
            if not original:
                raise ValueError(f"Triage {triage_id!r} not found for tenant {self.tenant_id}")

            row = HazardTriage(
                tenant_id=uuid.UUID(tid),
                hazard_id=original.hazard_id,
                triaged_by=actor,
                triaged_at=now,
                # A reversal row documents the reversal of the original decision.
                decision=original.decision,
                notes=reason,
                initial_priority=original.initial_priority,
                reversal_of=original.id,
                reversal_reason=reason,
                reversed_by=actor,
                reversed_at=now,
            )
            session.add(row)
            await session.flush()
            result = _row_to_dict(row)
            result["tenant_id"] = tenant_slug(result["tenant_id"])

        log_audit(
            action="TRIAGE_REVERSED",
            user=(user or {}).get("email") or (user or {}).get("uid"),
            tenant_id=self.tenant_id,
            target_type="hazard_triage",
            target_id=result["id"],
            metadata={"reversal_of": str(triage_id), "reversal_reason": reason},
        )
        logger.info(f"Triage {triage_id} reversed for tenant {self.tenant_id}")
        return result

    async def _list_async(self, hazard_id):
        tid = register_tenant(self.tenant_id)
        async with session_scope() as session:
            hazard = await _lookup_hazard(session, tid, hazard_id)
            if not hazard:
                return []
            rows = (await session.execute(
                select(HazardTriage)
                .where(HazardTriage.tenant_id == uuid.UUID(tid),
                       HazardTriage.hazard_id == hazard.id)
                .order_by(HazardTriage.triaged_at.desc())
            )).scalars().all()
        out = []
        for r in rows:
            data = _row_to_dict(r)
            data["tenant_id"] = tenant_slug(data["tenant_id"])
            out.append(data)
        return out
