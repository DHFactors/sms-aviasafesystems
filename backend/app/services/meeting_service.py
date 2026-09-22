# ============================================================================
# FILE: meeting_service.py
# PATH: backend/app/services/meeting_service.py
# PURPOSE: Module B §28/§29 (SN16) — SAG (quarterly) and SRB (6-monthly)
#          meeting records plus a SHARED action_items table carrying a
#          `meeting_type` discriminator ('sag' | 'srb').
# ============================================================================

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select

from app.db.db_models import ActionItem, SagMeeting, SrbMeeting
from app.db.ids import register_tenant, tenant_slug
from app.db.runner import run
from app.db.session import session_scope

MEETING_MODELS = {"sag": SagMeeting, "srb": SrbMeeting}
MEETING_TYPES = tuple(MEETING_MODELS.keys())
MEETING_STATUSES = ("Scheduled", "Held", "Cancelled")
ACTION_STATUSES = ("Open", "In Progress", "Closed")

# Cadence defaults (Module B §28/§29 Decision 3) — informational.
MEETING_CADENCE = {"sag": "quarterly", "srb": "6-monthly"}


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


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


def _model_for(meeting_type: str):
    model = MEETING_MODELS.get(str(meeting_type or "").lower())
    if model is None:
        raise ValueError(f"meeting_type must be one of {MEETING_TYPES}")
    return model


class MeetingService:
    """Persistence for SAG/SRB meetings and their shared action items."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    # -- public -------------------------------------------------------------

    def create_meeting(self, meeting_type: str, **fields) -> Dict[str, Any]:
        return run(self._create_meeting(meeting_type, fields))

    def list_meetings(self, meeting_type: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return run(self._list_meetings(meeting_type, status))

    def update_meeting(self, meeting_type: str, meeting_id: str,
                       payload: Dict[str, Any]) -> Dict[str, Any]:
        return run(self._update_meeting(meeting_type, meeting_id, payload))

    def create_action_item(self, meeting_type: str, meeting_id: str,
                           payload: Dict[str, Any]) -> Dict[str, Any]:
        return run(self._create_action_item(meeting_type, meeting_id, payload))

    def update_action_item(self, action_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return run(self._update_action_item(action_id, payload))

    def list_action_items(self, meeting_type: Optional[str] = None,
                          meeting_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return run(self._list_action_items(meeting_type, meeting_id))

    # -- internals ----------------------------------------------------------

    async def _create_meeting(self, meeting_type, fields):
        model = _model_for(meeting_type)
        tid = register_tenant(self.tenant_id)
        status = fields.get("status") or "Scheduled"
        if status not in MEETING_STATUSES:
            raise ValueError(f"status must be one of {MEETING_STATUSES}")
        async with session_scope() as session:
            row = model(
                tenant_id=uuid.UUID(tid),
                scheduled_at=_parse_dt(fields.get("scheduled_at")),
                held_at=_parse_dt(fields.get("held_at")),
                attendees=fields.get("attendees"),
                minutes_ref=fields.get("minutes_ref"),
                minutes_summary=fields.get("minutes_summary"),
                status=status,
            )
            session.add(row)
            await session.flush()
            return _row_to_dict(row)

    async def _list_meetings(self, meeting_type, status):
        model = _model_for(meeting_type)
        tid = register_tenant(self.tenant_id)
        stmt = select(model).where(model.tenant_id == uuid.UUID(tid))
        if status:
            stmt = stmt.where(model.status == status)
        stmt = stmt.order_by(model.scheduled_at.desc().nullslast())
        async with session_scope() as session:
            rows = (await session.scalars(stmt)).all()
        return [_row_to_dict(r) for r in rows]

    async def _update_meeting(self, meeting_type, meeting_id, payload):
        model = _model_for(meeting_type)
        tid = register_tenant(self.tenant_id)
        mutable = {"scheduled_at", "held_at", "attendees", "minutes_ref",
                   "minutes_summary", "status"}
        async with session_scope() as session:
            row = (await session.execute(
                select(model).where(
                    model.id == uuid.UUID(str(meeting_id)),
                    model.tenant_id == uuid.UUID(tid),
                )
            )).scalars().first()
            if not row:
                raise ValueError(f"Meeting {meeting_id!r} not found")
            for key, value in (payload or {}).items():
                if key not in mutable:
                    continue
                if key in ("scheduled_at", "held_at"):
                    value = _parse_dt(value)
                if key == "status" and value not in MEETING_STATUSES:
                    raise ValueError(f"status must be one of {MEETING_STATUSES}")
                setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            await session.flush()
            return _row_to_dict(row)

    async def _create_action_item(self, meeting_type, meeting_id, payload):
        mt = str(meeting_type or "").lower()
        _model_for(mt)  # validates the type
        tid = register_tenant(self.tenant_id)
        async with session_scope() as session:
            row = ActionItem(
                tenant_id=uuid.UUID(tid),
                meeting_type=mt,
                meeting_id=uuid.UUID(str(meeting_id)) if meeting_id else None,
                hazard_id=uuid.UUID(str(payload["hazard_id"])) if payload.get("hazard_id") else None,
                cap_id=uuid.UUID(str(payload["cap_id"])) if payload.get("cap_id") else None,
                assigned_to=payload.get("assigned_to"),
                due_date=_parse_dt(payload.get("due_date")),
                status=payload.get("status") or "Open",
                notes=payload.get("notes"),
            )
            session.add(row)
            await session.flush()
            return _row_to_dict(row)

    async def _update_action_item(self, action_id, payload):
        tid = register_tenant(self.tenant_id)
        mutable = {"assigned_to", "due_date", "status", "notes",
                   "hazard_id", "cap_id", "meeting_id"}
        async with session_scope() as session:
            row = (await session.execute(
                select(ActionItem).where(
                    ActionItem.id == uuid.UUID(str(action_id)),
                    ActionItem.tenant_id == uuid.UUID(tid),
                )
            )).scalars().first()
            if not row:
                raise ValueError(f"Action item {action_id!r} not found")
            for key, value in (payload or {}).items():
                if key not in mutable:
                    continue
                if key == "due_date":
                    value = _parse_dt(value)
                elif key in ("hazard_id", "cap_id", "meeting_id") and value:
                    value = uuid.UUID(str(value))
                setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            await session.flush()
            return _row_to_dict(row)

    async def _list_action_items(self, meeting_type, meeting_id):
        tid = register_tenant(self.tenant_id)
        stmt = select(ActionItem).where(ActionItem.tenant_id == uuid.UUID(tid))
        if meeting_type:
            stmt = stmt.where(ActionItem.meeting_type == str(meeting_type).lower())
        if meeting_id:
            stmt = stmt.where(ActionItem.meeting_id == uuid.UUID(str(meeting_id)))
        stmt = stmt.order_by(ActionItem.created_at.desc())
        async with session_scope() as session:
            rows = (await session.scalars(stmt)).all()
        return [_row_to_dict(r) for r in rows]
