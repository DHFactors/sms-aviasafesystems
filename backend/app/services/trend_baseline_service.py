# ============================================================================
# FILE: trend_baseline_service.py
# PATH: backend/app/services/trend_baseline_service.py
# PURPOSE: Module C §10 (TB-1..4, SN-C7) — trend-baseline window resolver.
#          State metrics default to rolling_12m; operational metrics to
#          rolling_90d; per-metric overrides live in `metric_definitions`.
#          Below `min_periods` history the consumer returns "insufficient data".
# ============================================================================

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from loguru import logger
from sqlalchemy import select, text

from app.db.db_models import MetricDefinition
from app.db.ids import tenant_uuid
from app.db.runner import run
from app.db.session import session_scope

# Defaults (SN-C7 / Q10.2): 12-month state, 90-day operational.
DEFAULTS: Dict[str, Tuple[str, int, int]] = {
    "state": ("rolling_12m", 365, 12),
    "operational": ("rolling_90d", 90, 3),
}


class TrendBaselineService:
    """Resolve trend windows + assess history sufficiency."""

    # -- windows ------------------------------------------------------------

    def resolve_window(self, metric_key: str,
                       metric_type: str = "state") -> Tuple[str, int, int]:
        """Return (window_type, window_days, min_periods).

        A `metric_definitions` row matching ``metric_key`` (or the type default
        when ``metric_key`` is NULL) overrides the built-in defaults.
        """
        default = DEFAULTS.get(metric_type, DEFAULTS["state"])
        try:
            definition = run(self._lookup_definition(metric_key, metric_type))
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"metric_definitions lookup failed for {metric_key}: {e}")
            definition = None
        if not definition:
            return default
        return (
            definition.get("window_type") or default[0],
            definition.get("window_days") or default[1],
            definition.get("min_periods") or default[2],
        )

    async def _lookup_definition(self, metric_key, metric_type):
        async with session_scope() as session:
            row = (await session.execute(
                select(MetricDefinition).where(
                    MetricDefinition.metric_key == metric_key)
            )).scalars().first()
            if row is None:
                row = (await session.execute(
                    select(MetricDefinition).where(
                        MetricDefinition.metric_type == metric_type,
                        MetricDefinition.metric_key.is_(None),
                    )
                )).scalars().first()
            if row is None:
                return None
            return {
                "window_type": row.window_type,
                "window_days": row.window_days,
                "min_periods": row.min_periods,
            }

    # -- history ------------------------------------------------------------

    def is_sufficient_history(self, metric_key: str, tenant_id: Optional[str] = None,
                              metric_type: str = "state") -> bool:
        """True when the available month-span meets the window's min_periods."""
        _window_type, _window_days, min_periods = self.resolve_window(metric_key, metric_type)
        months = self._months_with_data(tenant_id)
        return months >= min_periods

    def _months_with_data(self, tenant_id: Optional[str]) -> int:
        try:
            return run(self._count_months(tenant_id))
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Month-count failed for {tenant_id}: {e}")
            return 0

    async def _count_months(self, tenant_id: Optional[str]) -> int:
        async with session_scope() as session:
            if tenant_id:
                stmt = text(
                    "SELECT count(DISTINCT date_trunc('month', submitted_at)) "
                    "FROM public.surveys WHERE tenant_id = :tid"
                )
                result = await session.execute(stmt, {"tid": tenant_uuid(tenant_id)})
            else:
                stmt = text(
                    "SELECT count(DISTINCT date_trunc('month', submitted_at)) "
                    "FROM public.surveys"
                )
                result = await session.execute(stmt)
            return int(result.scalar() or 0)

    # -- trend --------------------------------------------------------------

    def compute_trend(self, metric_key: str, tenant_id: Optional[str],
                      current_value: Optional[float],
                      metric_type: str = "state") -> Dict[str, Any]:
        """Compare ``current_value`` to the materialized baseline (if any)."""
        window_type, window_days, min_periods = self.resolve_window(metric_key, metric_type)
        if not self.is_sufficient_history(metric_key, tenant_id, metric_type):
            return {
                "trend": "insufficient data",
                "baseline": None,
                "current_value": current_value,
                "window_type": window_type,
                "window_days": window_days,
                "min_periods": min_periods,
            }
        baseline = self._baseline_from_aggregates(metric_key, tenant_id)
        if baseline is None or current_value is None:
            trend = "insufficient data"
        elif current_value > baseline:
            trend = "increasing"
        elif current_value < baseline:
            trend = "decreasing"
        else:
            trend = "stable"
        return {
            "trend": trend,
            "baseline": baseline,
            "current_value": current_value,
            "window_type": window_type,
            "window_days": window_days,
            "min_periods": min_periods,
        }

    def _baseline_from_aggregates(self, metric_key: str,
                                  tenant_id: Optional[str]) -> Optional[float]:
        from app.db.db_models import ModuleCAggregate

        try:
            rows = run(self._fetch_baselines(metric_key, tenant_id))
        except Exception:
            return None
        for row in rows:
            payload = row.get("payload") or {}
            value = payload.get("average_overall") or payload.get("value")
            if isinstance(value, (int, float)):
                return float(value)
        return None

    async def _fetch_baselines(self, metric_key, tenant_id):
        async with session_scope() as session:
            stmt = select(ModuleCAggregate).where(
                ModuleCAggregate.metric_key == metric_key)
            if tenant_id:
                stmt = stmt.where(ModuleCAggregate.tenant_id == tenant_uuid(tenant_id))
            else:
                stmt = stmt.where(ModuleCAggregate.tenant_id.is_(None))
            stmt = stmt.order_by(ModuleCAggregate.computed_at.desc())
            rows = (await session.scalars(stmt)).all()
        out = []
        for r in rows:
            out.append({"payload": r.payload})
        return out
