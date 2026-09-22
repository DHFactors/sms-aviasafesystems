# ============================================================================
# P2-12 — SAG/SRB meeting service (shared action_items table).
# ============================================================================

from sqlalchemy import func, select

from app.db.db_models import ActionItem
from app.db.session import session_scope
from app.services.meeting_service import MeetingService

from _mbb import cleanup, create_tenant, run, unique_slug

TABLES = ("action_items", "sag_meetings", "srb_meetings")


def test_sag_and_srb_share_action_items_table():
    slug = unique_slug("meet")
    create_tenant(slug)
    try:
        svc = MeetingService(slug)
        sag = svc.create_meeting("sag", scheduled_at="2026-03-01T09:00:00+00:00",
                                 attendees=[{"email": "a@x.com"}], minutes_ref="SAG-1")
        srb = svc.create_meeting("srb", scheduled_at="2026-06-01T09:00:00+00:00")
        assert sag["status"] == "Scheduled"
        assert svc.create_meeting("sag", status="Held")["status"] == "Held"

        a1 = svc.create_action_item("sag", sag["id"], {"assigned_to": "A", "notes": "n"})
        a2 = svc.create_action_item("srb", srb["id"], {"assigned_to": "B"})
        assert a1["meeting_type"] == "sag"
        assert a2["meeting_type"] == "srb"

        assert len(svc.list_action_items("sag")) == 1
        assert len(svc.list_action_items("srb")) == 1

        async def _count():
            async with session_scope() as s:
                return (await s.execute(select(func.count()).select_from(ActionItem))).scalar_one()

        assert run(_count()) == 2

        updated = svc.update_action_item(a1["id"], {"status": "Closed"})
        assert updated["status"] == "Closed"
        assert len(svc.list_meetings("sag")) == 2
    finally:
        cleanup(slug, TABLES)


def test_invalid_meeting_type_rejected():
    import pytest

    slug = unique_slug("meetbad")
    create_tenant(slug)
    try:
        with pytest.raises(ValueError):
            MeetingService(slug).create_meeting("board", scheduled_at=None)
    finally:
        cleanup(slug, TABLES)
