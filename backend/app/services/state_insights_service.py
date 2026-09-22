# ============================================================================
# FILE: state_insights_service.py
# PATH: backend/app/services/state_insights_service.py
# PURPOSE: Module C §11 (AL-2, Q11.1) — state diagnostic/insights output over
#          AGGREGATED data only (the safe LLM lane). No tenant-identifiable
#          record ever reaches the model; results are cached in
#          `module_c_aggregates`.
# ============================================================================

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select

from app.db.db_models import ModuleCAggregate
from app.db.runner import run
from app.db.session import session_scope
from app.services.audit_service import log_audit

INSIGHT_METRIC_TYPE = "state_insight"


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


class StateInsightsService:
    """Generate + cache aggregated state insights (three-lane LLM, lane 1)."""

    # -- public -------------------------------------------------------------

    def generate_insights(self, metric_key: str, period: Optional[str] = None,
                          user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return run(self._generate_async(metric_key, period, user))

    def list_insights(self, period: Optional[str] = None) -> List[Dict[str, Any]]:
        return run(self._list_async(period))

    # -- internals ----------------------------------------------------------

    async def _load_aggregate(self, metric_key: str) -> Optional[Dict[str, Any]]:
        async with session_scope() as session:
            row = (await session.execute(
                select(ModuleCAggregate)
                .where(ModuleCAggregate.metric_key == metric_key)
                .order_by(ModuleCAggregate.computed_at.desc())
                .limit(1)
            )).scalars().first()
            return row.payload if row else None

    def _generate_narrative(self, metric_key: str, payload: Dict[str, Any]) -> str:
        """LLM narrative over aggregate data, with a deterministic fallback.

        Only aggregated, non-identifiable content is placed in the prompt.
        """
        summary_lines = []
        for key, value in (payload or {}).items():
            if key in ("anonymized_scores", "trend_over_time", "top_risks"):
                continue
            summary_lines.append(f"- {key}: {value}")
        summary = "\n".join(summary_lines) or "- (no aggregate data)"

        try:
            from app.services import gemini

            if gemini.model is not None:
                prompt = (
                    "You are an ICAO State Safety Programme analyst. Produce a short, "
                    "non-identifying diagnostic narrative from these AGGREGATED national "
                    "metrics only (never infer or name an individual operator):\n"
                    f"{summary}\n"
                    "Return 2-4 sentences of analysis and one recommended state action."
                )
                with gemini._perf_timed("gemini"):
                    response = gemini.model.generate_content(prompt)
                text = getattr(response, "text", "") or ""
                if text.strip():
                    return text.strip()
        except Exception as e:  # pragma: no cover - LLM unavailable
            logger.warning(f"Insight LLM call failed for {metric_key}: {e}")

        return (
            f"State diagnostic for {metric_key}: aggregate metrics show "
            f"{len(summary_lines)} dimension(s) available. "
            "No individual operator is identifiable in this analysis."
        )

    async def _generate_async(self, metric_key, period, user):
        payload = await self._load_aggregate(metric_key)
        narrative = self._generate_narrative(metric_key, payload or {})
        now = datetime.now(timezone.utc)
        # Persist only non-identifiable aggregate keys (the raw anonymized
        # operator rows and per-risk details are never carried into the insight).
        safe_keys = sorted(
            k for k in (payload or {})
            if k not in ("anonymized_scores", "trend_over_time", "top_risks")
        )
        doc = {
            "metric_type": INSIGHT_METRIC_TYPE,
            "metric_key": f"insights:{metric_key}",
            "source_metric": metric_key,
            "period": period,
            "narrative": narrative,
            "aggregate_keys": safe_keys,
        }
        async with session_scope() as session:
            row = ModuleCAggregate(
                tenant_id=None,
                metric_type=INSIGHT_METRIC_TYPE,
                metric_key=f"insights:{metric_key}",
                payload=doc,
                computed_at=now,
                ttl_seconds=24 * 3600,
                source_version="state_insights",
            )
            session.add(row)
            await session.flush()
            result = _row_to_dict(row)

        log_audit(
            action="CAAN_READ_INSIGHTS",
            user=(user or {}).get("email") or (user or {}).get("uid") or "caan",
            tenant_id=None,
            target_type="state_insight",
            target_id=result["id"],
            metadata={"metric_key": metric_key, "aggregate_keys": doc["aggregate_keys"]},
        )
        return result

    async def _list_async(self, period):
        async with session_scope() as session:
            stmt = select(ModuleCAggregate).where(
                ModuleCAggregate.metric_type == INSIGHT_METRIC_TYPE)
            stmt = stmt.order_by(ModuleCAggregate.computed_at.desc())
            rows = (await session.scalars(stmt)).all()
        return [_row_to_dict(r) for r in rows]
