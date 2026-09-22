# ============================================================================
# P2-17 — module_c_aggregates materialization.
# ============================================================================

from datetime import datetime, timezone

from app.db.db_models import Survey
from app.db.isolation import demo_scope
from app.db.session import session_scope
from app.services.aggregation_materializer import METRIC_REGISTRY, AggregationMaterializer

from _mbb import cleanup, create_tenant, run, unique_slug


def _seed_survey(tid):
    async def _go():
        async with session_scope() as s:
            s.add(Survey(
                tenant_id=tid, submitted_at=datetime.now(timezone.utc),
                survey_version="4.0.0", answers={}, overall_sms_maturity=4,
                safety_policy=4, safety_risk_management=4, safety_assurance=4,
                safety_promotion=4, is_demo=demo_scope()))

    run(_go())


def test_materialize_all_and_invalidate():
    slugs = [unique_slug("mat") for _ in range(3)]
    for sl in slugs:
        _seed_survey(create_tenant(sl))
    try:
        mat = AggregationMaterializer()
        row = mat.materialize_metric("industry_average_maturity")
        assert row["metric_key"] == "industry_average_maturity"
        assert row["metric_type"] == "national_maturity"
        assert row["tenant_id"] is None

        rows = mat.materialize_all()
        assert len(rows) == len(METRIC_REGISTRY)

        deleted = mat.invalidate_metric("industry_average_maturity")
        assert deleted >= 1
    finally:
        for key in METRIC_REGISTRY:
            AggregationMaterializer().invalidate_metric(key)
        for sl in slugs:
            cleanup(sl, ("surveys",))


def test_materialize_unknown_metric_rejected():
    import pytest

    with pytest.raises(ValueError):
        AggregationMaterializer().materialize_metric("nope")


def test_event_trigger_refreshes_metrics():
    slugs = [unique_slug("matev") for _ in range(3)]
    for sl in slugs:
        _seed_survey(create_tenant(sl))
    try:
        out = AggregationMaterializer().trigger_for_event("survey_submitted")
        assert len(out) == 1
        assert out[0]["source_version"] == "event:survey_submitted"
    finally:
        for key in METRIC_REGISTRY:
            AggregationMaterializer().invalidate_metric(key)
        for sl in slugs:
            cleanup(sl, ("surveys",))
