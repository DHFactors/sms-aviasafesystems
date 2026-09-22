# ============================================================================
# P2-11 — MOR category-tiered regulatory timer (SN15).
# ============================================================================

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.db_models import Report
from app.db.session import session_scope
from app.services import regulatory_timer_service as rts

from _mbb import cleanup, create_tenant, run, unique_slug

TABLES = ("reports",)


def test_compute_deadline_per_category():
    base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert rts.compute_deadline(base, "A") == base + timedelta(hours=24)
    assert rts.compute_deadline(base, "B") == base + timedelta(hours=72)
    assert rts.compute_deadline(base, "C") == base + timedelta(days=7)
    assert rts.compute_deadline(base, "D") == base + timedelta(days=30)
    # Tenant default applies when no category is supplied.
    assert rts.compute_deadline(base, None, tenant_default="B") == base + timedelta(hours=72)
    # No category and no default -> no deadline.
    assert rts.compute_deadline(base, None) is None


def test_check_overdue_mors():
    slug = unique_slug("mortimer")
    tid = create_tenant(slug)
    now = datetime.now(timezone.utc)

    async def _seed():
        async with session_scope() as s:
            s.add(Report(
                tenant_id=tid, report_type="mandatory", status="NEW", narrative="n",
                location="KTM", occurrence_date=now, created_by="system",
                regulatory_category="A", regulatory_deadline_at=now - timedelta(hours=1),
                is_demo=False,
            ))
            s.add(Report(
                tenant_id=tid, report_type="mandatory", status="NEW", narrative="n",
                location="KTM", occurrence_date=now, created_by="system",
                regulatory_category="B", regulatory_deadline_at=now - timedelta(hours=1),
                regulatory_submitted_at=now, is_demo=False,
            ))

    run(_seed())
    try:
        overdue = rts.check_overdue_mors(slug)
        # Only the un-submitted, past-deadline MOR is a breach.
        assert len(overdue) == 1
        assert overdue[0]["regulatory_category"] == "A"
    finally:
        cleanup(slug, TABLES)


def test_set_mor_deadline_persists():
    slug = unique_slug("morset")
    tid = create_tenant(slug)
    now = datetime.now(timezone.utc)
    rid = None

    async def _seed():
        nonlocal rid
        async with session_scope() as s:
            r = Report(
                tenant_id=tid, report_type="mandatory", status="NEW", narrative="n",
                location="KTM", occurrence_date=now, created_by="system", is_demo=False,
            )
            s.add(r)
            await s.flush()
            rid = str(r.id)

    run(_seed())
    try:
        iso = rts.set_mor_deadline(rid, slug, category="C", submitted_at=now)
        assert iso is not None

        async def _fetch():
            async with session_scope() as s:
                return (await s.execute(
                    select(Report).where(Report.id == uuid.UUID(rid))
                )).scalars().first()

        report = run(_fetch())
        assert report.regulatory_category == "C"
        assert report.regulatory_deadline_at is not None
    finally:
        cleanup(slug, TABLES)
