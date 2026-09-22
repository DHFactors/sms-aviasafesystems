# ============================================================================
# FILE: ae_kpi_service.py
# PATH: backend/app/services/ae_kpi_service.py
# PURPOSE: SN9 + DASHBOARD_CONTRACT §4.3 — Accountable Executive KPI:
#          average days from hazard registration to first action, and the
#          "received" (status = Open) count. Non-demo hazards only; per-hazard
#          elapsed days are capped at 30 (never-actioned included, capped).
#          Results are cached in `module_c_aggregates`.
# ============================================================================

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import select

from app.db.db_models import Can, Hazard, ModuleCAggregate
from app.db.ids import register_tenant
from app.db.runner import run
from app.db.session import session_scope

DAY_CAP = 30
METRIC_KEY = "ae_hazard_response_time"
METRIC_TYPE = "ae_kpi"


def _as_utc(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class AEKPIService:
    """Compute the AE hazard-response-time KPI for a tenant."""

    def __init__(self, tenant_id: Optional[str] = None):
        self.tenant_id = tenant_id

    # -- public -------------------------------------------------------------

    def compute_hazard_response_time(self, tenant_id: Optional[str] = None,
                                     period: Optional[str] = None) -> Dict[str, Any]:
        return run(self._compute_async(tenant_id or self.tenant_id, period))

    def get_cached(self, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return run(self._cached_async(tenant_id or self.tenant_id))

    # -- internals ----------------------------------------------------------

    async def _compute_async(self, tenant_id, period):
        tid = register_tenant(tenant_id) if tenant_id else None
        async with session_scope() as session:
            h_stmt = select(Hazard).where(Hazard.is_demo == False)  # noqa: E712
            if tid:
                h_stmt = h_stmt.where(Hazard.tenant_id == tid)
            hazards = (await session.scalars(h_stmt)).all()

            if not hazards:
                result = {"avg_days": None, "received_count": 0,
                          "hazards_total": 0, "received_rate": 0.0}
            else:
                hazard_ids = [h.id for h in hazards]
                c_stmt = (
                    select(Can.hazard_id, Can.issued_at)
                    .where(Can.is_demo == False, Can.issued_at.isnot(None))  # noqa: E712
                )
                if tid:
                    c_stmt = c_stmt.where(Can.tenant_id == tid)
                can_rows = (await session.execute(c_stmt)).all()
                first_can: Dict[Any, datetime] = {}
                for hazard_id, issued_at in can_rows:
                    issued = _as_utc(issued_at)
                    if issued is None:
                        continue
                    existing = first_can.get(hazard_id)
                    if existing is None or issued < existing:
                        first_can[hazard_id] = issued

                total_days = 0.0
                counted = 0
                received = 0
                for h in hazards:
                    if (h.status or "") == "Open":
                        received += 1
                    first_action = self._first_action(h, first_can)
                    if first_action is None:
                        continue
                    created = _as_utc(h.created_at)
                    if created is None:
                        continue
                    days = (first_action.date() - created.date()).days
                    days = max(0, min(days, DAY_CAP))
                    total_days += days
                    counted += 1
                result = {
                    "avg_days": round(total_days / counted, 2) if counted else None,
                    "received_count": received,
                    "hazards_total": len(hazards),
                    "received_rate": round(received / len(hazards), 3) if hazards else 0.0,
                }

        await self._cache_async(tid, period, result)
        return result

    def _first_action(self, hazard: Hazard, first_can: Dict[Any, datetime]) -> Optional[datetime]:
        """Earliest of first_priority_at, srm_date and the first CAN issued_at."""
        candidates = [
            _as_utc(hazard.first_priority_at),
            _as_utc(hazard.srm_date),
            first_can.get(hazard.id),
            _as_utc(hazard.priority_date),
        ]
        present = [c for c in candidates if c is not None]
        return min(present) if present else None

    async def _cache_async(self, tid, period, payload):
        now = datetime.now(timezone.utc)
        async with session_scope() as session:
            stmt = select(ModuleCAggregate).where(
                ModuleCAggregate.metric_key == METRIC_KEY,
            )
            if tid:
                stmt = stmt.where(ModuleCAggregate.tenant_id == tid)
            else:
                stmt = stmt.where(ModuleCAggregate.tenant_id.is_(None))
            existing = (await session.execute(stmt.limit(1))).scalars().first()
            if existing:
                existing.payload = payload
                existing.computed_at = now
                existing.source_version = "ae_kpi"
            else:
                session.add(ModuleCAggregate(
                    tenant_id=tid, metric_type=METRIC_TYPE, metric_key=METRIC_KEY,
                    payload=payload, computed_at=now, ttl_seconds=24 * 3600,
                    source_version="ae_kpi",
                ))
            await session.flush()

    async def _cached_async(self, tenant_id):
        tid = register_tenant(tenant_id) if tenant_id else None
        async with session_scope() as session:
            stmt = select(ModuleCAggregate).where(
                ModuleCAggregate.metric_key == METRIC_KEY)
            if tid:
                stmt = stmt.where(ModuleCAggregate.tenant_id == tid)
            else:
                stmt = stmt.where(ModuleCAggregate.tenant_id.is_(None))
            row = (await session.execute(stmt.limit(1))).scalars().first()
            return row.payload if row else None
