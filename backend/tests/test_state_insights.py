# ============================================================================
# P2-23 — state insights (aggregated LLM lane; no tenant-identifiable data).
# ============================================================================

from datetime import datetime, timezone

from sqlalchemy import text

from app.db.db_models import ModuleCAggregate
from app.db.session import session_scope
from app.services.state_insights_service import StateInsightsService

from _mbb import run, unique_slug

KEY = "insight_probe_" + unique_slug("m")


def _seed_aggregate():
    async def _go():
        async with session_scope() as s:
            s.add(ModuleCAggregate(
                tenant_id=None, metric_type="national_maturity", metric_key=KEY,
                payload={"average_overall": 3.8, "tenant_count": 5,
                         "anonymized_scores": [{"anonymized_id": "Operator-1"}]},
                computed_at=datetime.now(timezone.utc)))


    run(_go())


def _wipe():
    async def _go():
        async with session_scope() as s:
            await s.execute(text(
                "DELETE FROM public.module_c_aggregates WHERE metric_key IN (:k, :ik)"),
                {"k": KEY, "ik": f"insights:{KEY}"})

    run(_go())


def test_generate_and_list_insights():
    _seed_aggregate()
    try:
        svc = StateInsightsService()
        result = svc.generate_insights(KEY, user={"role": "CAAN_SMD", "email": "caan@x.np"})
        payload = result["payload"]
        assert payload["narrative"]
        assert payload["source_metric"] == KEY
        # No tenant-identifiable data in the insight payload.
        assert "anonymized_scores" not in payload["aggregate_keys"]
        assert "Operator-1" not in str(payload)

        listed = svc.list_insights()
        assert any(r["metric_key"] == f"insights:{KEY}" for r in listed)
    finally:
        _wipe()
