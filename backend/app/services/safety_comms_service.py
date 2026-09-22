# ============================================================================
# FILE: safety_comms_service.py
# PATH: backend/app/services/safety_comms_service.py
# PURPOSE: Module B §31 (SN17) — tenant safety bulletins with a
#          draft → review → published → archived lifecycle. Publication is
#          gated on the SAFETY_MANAGER capability; published_by is a users.id.
# ============================================================================

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select

from app.db.db_models import SafetyCommunication
from app.db.ids import register_tenant, tenant_slug
from app.db.runner import run
from app.db.session import session_scope
from app.services.actor import resolve_actor_uuid
from app.services.audit_service import log_audit

STATUSES = ("draft", "review", "published", "archived")

# Publication approval gate (Module B §31; Safety Manager capability).
SAFETY_MANAGER_ROLES = {"TENANT_ADMIN", "AIRLINE_ADMIN"}

# Allowed lifecycle transitions.
_TRANSITIONS = {
    "draft": {"review", "archived"},
    "review": {"published", "draft", "archived"},
    "published": {"archived"},
    "archived": set(),
}


def _row_to_dict(row: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for col in row.__table__.columns:
        value = getattr(row, col.name)
        if isinstance(value, uuid.UUID):
            value = str(value)
        elif isinstance(value, datetime):
            value = value.isoformat()
        data[col.name] = value
    data["tenant_id"] = tenant_slug(row.tenant_id)
    return data


class SafetyCommsService:
    """Persistence + lifecycle for tenant safety communications."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    # -- public -------------------------------------------------------------

    def create_draft(self, user: Dict[str, Any], title: str, body: Optional[str] = None,
                     audience: Optional[Any] = None,
                     derived_from_hazard_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        return run(self._create_draft(user, title, body, audience, derived_from_hazard_ids))

    def submit_for_review(self, comm_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
        return run(self._transition(comm_id, user, "review"))

    def publish(self, comm_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
        return run(self._transition(comm_id, user, "published"))

    def archive(self, comm_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
        return run(self._transition(comm_id, user, "archived"))

    def list_communications(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        return run(self._list(status_filter))

    # -- internals ----------------------------------------------------------

    async def _create_draft(self, user, title, body, audience, hazard_ids):
        if not (title or "").strip():
            raise ValueError("title is required")
        tid = register_tenant(self.tenant_id)
        hazard_uuids = []
        for hid in hazard_ids or []:
            try:
                hazard_uuids.append(uuid.UUID(str(hid)))
            except (ValueError, TypeError):
                continue
        async with session_scope() as session:
            row = SafetyCommunication(
                tenant_id=uuid.UUID(tid),
                title=title,
                body=body,
                status="draft",
                audience=audience,
                derived_from_hazard_ids=hazard_uuids or None,
            )
            session.add(row)
            await session.flush()
            result = _row_to_dict(row)
        log_audit(
            action="SAFETY_COMM_CREATED",
            user=(user or {}).get("email") or (user or {}).get("uid"),
            tenant_id=self.tenant_id,
            target_type="safety_communication",
            target_id=result["id"],
            metadata={"title": title},
        )
        return result

    async def _transition(self, comm_id, user, target_status):
        tid = register_tenant(self.tenant_id)
        now = datetime.now(timezone.utc)
        async with session_scope() as session:
            row = (await session.execute(
                select(SafetyCommunication).where(
                    SafetyCommunication.id == uuid.UUID(str(comm_id)),
                    SafetyCommunication.tenant_id == uuid.UUID(tid),
                )
            )).scalars().first()
            if not row:
                raise ValueError(f"Safety communication {comm_id!r} not found")

            if target_status not in _TRANSITIONS.get(row.status, set()):
                raise ValueError(
                    f"Invalid transition {row.status!r} -> {target_status!r}"
                )
            if target_status == "published":
                role = (user or {}).get("role")
                if role not in SAFETY_MANAGER_ROLES:
                    raise PermissionError(
                        f"Publishing a bulletin requires one of "
                        f"{sorted(SAFETY_MANAGER_ROLES)}; {role!r} is not authorised"
                    )
                row.published_by = await resolve_actor_uuid(user)
                row.published_at = now

            row.status = target_status
            row.updated_at = now
            await session.flush()
            result = _row_to_dict(row)

        log_audit(
            action="SAFETY_COMM_STATUS",
            user=(user or {}).get("email") or (user or {}).get("uid"),
            tenant_id=self.tenant_id,
            target_type="safety_communication",
            target_id=result["id"],
            metadata={"status": target_status},
        )
        logger.info(f"Safety communication {comm_id} -> {target_status} ({self.tenant_id})")
        return result

    async def _list(self, status_filter):
        tid = register_tenant(self.tenant_id)
        stmt = select(SafetyCommunication).where(
            SafetyCommunication.tenant_id == uuid.UUID(tid))
        if status_filter:
            if status_filter not in STATUSES:
                raise ValueError(f"status must be one of {STATUSES}")
            stmt = stmt.where(SafetyCommunication.status == status_filter)
        stmt = stmt.order_by(SafetyCommunication.created_at.desc())
        async with session_scope() as session:
            rows = (await session.scalars(stmt)).all()
        return [_row_to_dict(r) for r in rows]
