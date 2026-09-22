# ============================================================================
# P2-30 — AE hazard-response-time KPI (SN9 + Dashboard §4.3).
# ============================================================================

import uuid
from datetime import datetime, timedelta, timezone

from app.db.db_models import Hazard
from app.db.isolation import demo_scope
from app.db.session import session_scope
from app.services.ae_kpi_service import DAY_CAP, METRIC_KEY, AEKPIService

from _mbb import cleanup, create_tenant, run, unique_slug

TABLES = ("hazards",)


def _seed(tid, rows):
    async def _go():
        async with session_scope() as s:
            for h in rows:
                s.add(Hazard(
                    tenant_id=tid, hazard_id=h["id"], title="t", description="d",
                    source="voluntary", taxonomy="Organizational", priority="M",
                    status=h.get("status", "Open"), is_demo=False,
                    created_at=h["created"],
                    first_priority_at=h.get("first_priority_at")))

    run(_go())


def _wipe_agg():
    from sqlalchemy import text

    async def _go():
        async with session_scope() as s:
            await s.execute(text(
                "DELETE FROM public.module_c_aggregates WHERE metric_key = :k"),
                {"k": METRIC_KEY})

    run(_go())


def test_response_time_computation():
    slug = unique_slug("aekpi")
    tid = create_tenant(slug)
    now = datetime.now(timezone.utc)
    _seed(tid, [
        # First action 2 days after creation.
        {"id": "A", "created": now - timedelta(days=10),
         "first_priority_at": now - timedelta(days=8), "status": "Open"},
        # First action 5 days after creation.
        {"id": "B", "created": now - timedelta(days=20),
         "first_priority_at": now - timedelta(days=15), "status": "Closed"},
    ])
    try:
        kpi = AEKPIService(slug).compute_hazard_response_time(slug)
        assert kpi["hazards_total"] == 2
        assert kpi["received_count"] == 1
        assert kpi["avg_days"] == 3.5  # (2 + 5) / 2
        assert kpi["received_rate"] == 0.5

        cached = AEKPIService(slug).get_cached(slug)
        assert cached["avg_days"] == 3.5
    finally:
        _wipe_agg()
        cleanup(slug, TABLES)


def test_ninety_day_gap_is_capped():
    slug = unique_slug("aekpicap")
    tid = create_tenant(slug)
    now = datetime.now(timezone.utc)
    _seed(tid, [{
        "id": "C", "created": now - timedelta(days=200),
        "first_priority_at": now - timedelta(days=50), "status": "Closed"}])
    try:
        kpi = AEKPIService(slug).compute_hazard_response_time(slug)
        assert kpi["avg_days"] == DAY_CAP
    finally:
        _wipe_agg()
        cleanup(slug, TABLES)


def test_demo_hazards_excluded():
    slug = unique_slug("aekpidemo")
    tid = create_tenant(slug)
    now = datetime.now(timezone.utc)

    async def _seed_demo():
        async with session_scope() as s:
            s.add(Hazard(
                tenant_id=tid, hazard_id="D", title="t", description="d",
                source="voluntary", taxonomy="Organizational", priority="M",
                status="Open", is_demo=True, created_at=now,
                first_priority_at=now))

    run(_seed_demo())
    try:
        kpi = AEKPIService(slug).compute_hazard_response_time(slug)
        assert kpi["hazards_total"] == 0
        assert kpi["avg_days"] is None
    finally:
        _wipe_agg()
        cleanup(slug, TABLES)
