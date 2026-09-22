# ============================================================================
# FILE: aggregation_materializer.py
# PATH: backend/app/services/aggregation_materializer.py
# PURPOSE: Module C §7 (SN-C1/SN-C5) — hybrid materialization of expensive
#          SDCPS aggregates into `module_c_aggregates`. Daily scheduled run +
#          event-driven refresh; national rows carry tenant_id NULL.
# ============================================================================

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import delete, select

from app.core.config import settings
from app.db.db_models import ModuleCAggregate, Tenant
from app.db.runner import run
from app.db.session import session_scope

# Registered materializable metrics. `type` groups the metric families whose
# cadence is daily for state/operational and event-driven for critical alerts
# (Q7.1).
METRIC_REGISTRY: Dict[str, Dict[str, str]] = {
    "industry_average_maturity": {"type": "national_maturity"},
    "top_hazards": {"type": "national_hazards"},
    "state_risk_trends": {"type": "national_risk"},
}

DEFAULT_TTL_SECONDS = 24 * 3600

# Event → metrics to refresh on an aggregate-affecting event (Q7.1 hybrid).
EVENT_METRICS: Dict[str, List[str]] = {
    "survey_submitted": ["industry_average_maturity"],
    "hazard_created": ["top_hazards", "state_risk_trends"],
}


def _json_safe(value: Any) -> Any:
    """Recursively convert datetimes/dates to ISO strings for JSONB storage."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


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


class AggregationMaterializer:
    """Compute + persist national SDCPS aggregates."""

    def __init__(self, tenant_id: Optional[str] = None):
        self.tenant_id = tenant_id

    # -- public -------------------------------------------------------------

    def materialize_metric(self, metric_key: str, period: Optional[str] = None,
                           source: str = "scheduled") -> Dict[str, Any]:
        return run(self._materialize_async(metric_key, period, source))

    def materialize_all(self) -> List[Dict[str, Any]]:
        return run(self._materialize_all_async())

    def invalidate_metric(self, metric_key: str) -> int:
        return run(self._invalidate_async(metric_key))

    def trigger_for_event(self, event_type: str) -> List[Dict[str, Any]]:
        """Event-driven refresh hook (Q7.1).

        Aggregate-affecting events call this to refresh the affected metrics
        without waiting for the daily job. Callers stay decoupled from the
        metric internals.
        """
        keys = EVENT_METRICS.get(event_type, [])
        out = []
        for key in keys:
            try:
                out.append(self.materialize_metric(key, source=f"event:{event_type}"))
            except Exception as e:
                logger.warning(f"Event materialization failed for {key}: {e}")
        return out

    # -- internals ----------------------------------------------------------

    async def _tenant_slugs(self) -> List[str]:
        async with session_scope() as session:
            rows = (await session.scalars(select(Tenant.slug))).all()
        return [s for s in rows if s]

    async def _build_payload(self, metric_key: str) -> Dict[str, Any]:
        from app.services.aggregation_service import AggregationService

        slugs = await self._tenant_slugs()
        svc = AggregationService()
        if metric_key == "industry_average_maturity":
            return await svc.calculate_industry_averages(slugs)
        if metric_key == "top_hazards":
            return await svc.get_top_hazards(slugs)
        if metric_key == "state_risk_trends":
            return await svc.get_risk_trends(slugs)
        raise ValueError(f"Unknown metric_key {metric_key!r}")

    async def _materialize_async(self, metric_key, period, source):
        if metric_key not in METRIC_REGISTRY:
            raise ValueError(f"Unknown metric_key {metric_key!r}")
        payload = _json_safe(await self._build_payload(metric_key))
        metric_type = METRIC_REGISTRY[metric_key]["type"]
        now = datetime.now(timezone.utc)
        tenant_uuid_val = None
        if self.tenant_id:
            from app.db.ids import register_tenant
            tenant_uuid_val = uuid.UUID(register_tenant(self.tenant_id))

        async with session_scope() as session:
            existing = (await session.execute(
                select(ModuleCAggregate).where(
                    ModuleCAggregate.tenant_id.is_(None) if tenant_uuid_val is None
                    else ModuleCAggregate.tenant_id == tenant_uuid_val,
                    ModuleCAggregate.metric_type == metric_type,
                    ModuleCAggregate.metric_key == metric_key,
                    ModuleCAggregate.period_start.is_(None) if period is None
                    else ModuleCAggregate.period_start == _parse_period(period),
                )
            )).scalars().first()
            if existing:
                existing.payload = payload
                existing.computed_at = now
                existing.ttl_seconds = DEFAULT_TTL_SECONDS
                existing.source_version = source
                row = existing
            else:
                row = ModuleCAggregate(
                    tenant_id=tenant_uuid_val,
                    metric_type=metric_type,
                    metric_key=metric_key,
                    period_start=_parse_period(period),
                    payload=payload,
                    computed_at=now,
                    ttl_seconds=DEFAULT_TTL_SECONDS,
                    source_version=source,
                )
                session.add(row)
            await session.flush()
            result = _row_to_dict(row)

        logger.info(f"Materialized metric {metric_key} (type={metric_type}, source={source})")
        return result

    async def _materialize_all_async(self):
        out = []
        for key in METRIC_REGISTRY:
            try:
                out.append(await self._materialize_async(key, None, "scheduled"))
            except Exception as e:
                logger.error(f"Materialization failed for {key}: {e}")
        return out

    async def _invalidate_async(self, metric_key):
        async with session_scope() as session:
            result = await session.execute(
                delete(ModuleCAggregate).where(ModuleCAggregate.metric_key == metric_key)
            )
            return result.rowcount or 0


def _parse_period(period: Optional[str]) -> Optional[datetime]:
    if not period:
        return None
    if isinstance(period, datetime):
        return period
    try:
        return datetime.fromisoformat(str(period).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
