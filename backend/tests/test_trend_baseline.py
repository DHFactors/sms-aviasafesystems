# ============================================================================
# P2-20 — trend-baseline resolver (metric_definitions overrides + min history).
# ============================================================================

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.db.db_models import MetricDefinition, Survey
from app.db.isolation import demo_scope
from app.db.session import session_scope
from app.services.trend_baseline_service import DEFAULTS, TrendBaselineService

from _mbb import cleanup, create_tenant, run, unique_slug


def test_defaults_when_no_override():
    svc = TrendBaselineService()
    assert svc.resolve_window("no_such_metric_xyz", "state") == DEFAULTS["state"]
    assert svc.resolve_window("no_such_metric_xyz", "operational") == DEFAULTS["operational"]


def test_override_and_sufficient_history():
    key = "tb_" + uuid.uuid4().hex[:8]
    slug = unique_slug("tb")
    tid = create_tenant(slug)
    now = datetime.now(timezone.utc)

    async def _seed():
        async with session_scope() as s:
            s.add(MetricDefinition(
                metric_key=key, metric_type="operational",
                window_type="rolling_90d", window_days=90, min_periods=3))
            for i in range(3):
                s.add(Survey(
                    tenant_id=tid, submitted_at=now - timedelta(days=30 * i),
                    survey_version="4.0.0", answers={}, overall_sms_maturity=4,
                    is_demo=demo_scope()))

    run(_seed())
    try:
        svc = TrendBaselineService()
        assert svc.resolve_window(key, "operational") == ("rolling_90d", 90, 3)
        assert svc.is_sufficient_history(key, slug, "operational") is True
        out = svc.compute_trend(key, slug, 4.0, "operational")
        assert out["window_type"] == "rolling_90d"
        assert out["trend"] in ("stable", "increasing", "decreasing", "insufficient data")
    finally:
        async def _wipe():
            async with session_scope() as s:
                await s.execute(
                    text("DELETE FROM public.metric_definitions WHERE metric_key = :k"),
                    {"k": key})

        run(_wipe())
        cleanup(slug, ("surveys",))


def test_insufficient_history_returns_insufficient():
    svc = TrendBaselineService()
    # A tenant with no survey history has 0 months < min_periods (12).
    out = svc.compute_trend("no_such_metric_xyz", unique_slug("nohistory"), 1.0, "state")
    assert out["trend"] == "insufficient data"
    assert out["baseline"] is None
