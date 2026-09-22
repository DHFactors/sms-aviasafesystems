# ============================================================================
# FILE: state_spt_service.py
# PATH: backend/app/services/state_spt_service.py
# PURPOSE: Module C §9 (SPT-1..4, SN-C6) — State-level Safety Performance
#          Targets set/approved by CAAN (distinct from tenant SPTs). CAAN-only.
# ============================================================================

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select

from app.db.db_models import StateSafetyPerformanceTarget
from app.db.runner import run
from app.db.session import session_scope
from app.services.audit_service import log_audit

# CAAN-only authorisation (Module C §9 / Q4.3-style gate).
CAAN_ROLES = {"CAAN_SMD", "SUPER_ADMIN"}


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


def _require_caan(user: Dict[str, Any]) -> str:
    role = (user or {}).get("role")
    if role not in CAAN_ROLES:
        raise PermissionError(f"State SPT actions require one of {sorted(CAAN_ROLES)}")
    return (user or {}).get("email") or (user or {}).get("uid") or "caan"


class StateSPTService:
    """Persist + approve national-scope SPTs."""

    def __init__(self, tenant_id: Optional[str] = None):
        self.tenant_id = tenant_id

    # -- public -------------------------------------------------------------

    def set_state_spt(self, spi_definition_id: str, target_value: float,
                      target_period: str, user: Dict[str, Any],
                      valid_from: Optional[str] = None,
                      valid_to: Optional[str] = None) -> Dict[str, Any]:
        return run(self._set_async(spi_definition_id, target_value, target_period,
                                   user, valid_from, valid_to))

    def approve_state_spt(self, spt_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
        return run(self._approve_async(spt_id, user))

    def list_state_spts(self, period_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        return run(self._list_async(period_filter))

    def delete_state_spt(self, spt_id: str, user: Dict[str, Any]) -> bool:
        return run(self._delete_async(spt_id, user))

    # -- internals ----------------------------------------------------------

    async def _set_async(self, spi_definition_id, target_value, target_period,
                         user, valid_from, valid_to):
        actor = _require_caan(user)
        if not spi_definition_id:
            raise ValueError("spi_definition_id is required")
        try:
            target_value = float(target_value)
        except (TypeError, ValueError):
            raise ValueError("target_value must be numeric")
        target_period = (target_period or "annual").strip() or "annual"
        now = datetime.now(timezone.utc)
        async with session_scope() as session:
            row = StateSafetyPerformanceTarget(
                spi_definition_id=spi_definition_id,
                target_value=target_value,
                target_period=target_period,
                set_by=actor,
                set_at=now,
                valid_from=_parse_dt(valid_from),
                valid_to=_parse_dt(valid_to),
            )
            session.add(row)
            await session.flush()
            result = _row_to_dict(row)
        log_audit(
            action="STATE_SPT_SET", user=actor, tenant_id=None,
            target_type="state_spt", target_id=result["id"],
            metadata={"spi_definition_id": spi_definition_id, "target_value": target_value,
                      "period": target_period},
        )
        logger.info(f"State SPT set for {spi_definition_id} = {target_value} ({target_period})")
        return result

    async def _approve_async(self, spt_id, user):
        actor = _require_caan(user)
        now = datetime.now(timezone.utc)
        async with session_scope() as session:
            row = (await session.execute(
                select(StateSafetyPerformanceTarget).where(
                    StateSafetyPerformanceTarget.id == uuid.UUID(str(spt_id)))
            )).scalars().first()
            if not row:
                raise ValueError(f"State SPT {spt_id!r} not found")
            row.approved_by = actor
            row.approved_at = now
            row.updated_at = now
            await session.flush()
            result = _row_to_dict(row)
        log_audit(
            action="STATE_SPT_APPROVED", user=actor, tenant_id=None,
            target_type="state_spt", target_id=result["id"],
            metadata={"spi_definition_id": result["spi_definition_id"]},
        )
        return result

    async def _list_async(self, period_filter):
        async with session_scope() as session:
            stmt = select(StateSafetyPerformanceTarget)
            if period_filter:
                stmt = stmt.where(
                    StateSafetyPerformanceTarget.target_period == period_filter)
            stmt = stmt.order_by(StateSafetyPerformanceTarget.created_at.desc())
            rows = (await session.scalars(stmt)).all()
        return [_row_to_dict(r) for r in rows]

    async def _delete_async(self, spt_id, user):
        actor = _require_caan(user)
        async with session_scope() as session:
            row = (await session.execute(
                select(StateSafetyPerformanceTarget).where(
                    StateSafetyPerformanceTarget.id == uuid.UUID(str(spt_id)))
            )).scalars().first()
            if not row:
                return False
            await session.delete(row)
        log_audit(
            action="STATE_SPT_DELETED", user=actor, tenant_id=None,
            target_type="state_spt", target_id=str(spt_id), metadata={},
        )
        return True


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
