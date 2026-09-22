# ============================================================================
# P2-9 — hazard triage service (decide + reverse with audit).
# ============================================================================

import uuid

import pytest

from app.db.db_models import Hazard
from app.db.isolation import demo_scope
from app.db.session import session_scope
from app.services.hazard_triage_service import HazardTriageService

from _mbb import cleanup, create_tenant, create_user, run, unique_slug

TABLES = ("hazard_triage", "hazards")


def _seed_hazard(tid: str) -> str:
    async def _go():
        async with session_scope() as s:
            s.add(Hazard(
                tenant_id=tid, hazard_id="TRI-001", title="Test hazard",
                description="d", source="voluntary", taxonomy="Organizational",
                priority="M", status="Open", is_demo=demo_scope(),
            ))

    run(_go())
    return "TRI-001"


def test_triage_decisions_and_reversal():
    slug = unique_slug("triage")
    tid = create_tenant(slug)
    _seed_hazard(tid)
    uid = "tri-" + uuid.uuid4().hex[:8]
    create_user(tid, uid)
    try:
        svc = HazardTriageService(slug)
        user = {"uid": uid, "email": f"{uid}@test.local", "role": "SAFETY_OFFICER"}

        esca = svc.triage_hazard("TRI-001", user, "Escalated", notes="urgent")
        assert esca["decision"] == "Escalated"

        row = svc.triage_hazard("TRI-001", user, "Accepted", notes="ok")
        assert row["decision"] == "Accepted"
        assert row["triaged_by"] is not None

        # Reversal writes a NEW row linked via reversal_of (requires safety manager).
        manager = {"uid": uid, "email": f"{uid}@test.local", "role": "TENANT_ADMIN"}
        rev = svc.reverse_triage(row["id"], manager, "decision was wrong")
        assert rev["reversal_of"] == row["id"]
        assert rev["reversal_reason"] == "decision was wrong"

        assert len(svc.list_triage("TRI-001")) == 3
    finally:
        cleanup(slug, TABLES)


def test_reversal_requires_safety_manager():
    slug = unique_slug("trirev")
    tid = create_tenant(slug)
    _seed_hazard(tid)
    uid = "trirev-" + uuid.uuid4().hex[:8]
    create_user(tid, uid)
    try:
        svc = HazardTriageService(slug)
        user = {"uid": uid, "email": f"{uid}@test.local", "role": "SAFETY_OFFICER"}
        row = svc.triage_hazard("TRI-001", user, "Accepted")
        with pytest.raises(PermissionError):
            svc.reverse_triage(row["id"], user, "nope")
    finally:
        cleanup(slug, TABLES)


def test_rejected_closes_hazard():
    slug = unique_slug("trirej")
    tid = create_tenant(slug)
    _seed_hazard(tid)
    uid = "trirej-" + uuid.uuid4().hex[:8]
    create_user(tid, uid)
    try:
        HazardTriageService(slug).triage_hazard(
            "TRI-001", {"uid": uid, "role": "SAFETY_OFFICER"}, "Rejected",
            notes="not a hazard")

        async def _go():
            async with session_scope() as s:
                from sqlalchemy import select
                h = (await s.execute(
                    select(Hazard).where(Hazard.hazard_id == "TRI-001")
                )).scalars().first()
                return h.status

        assert run(_go()) == "Closed"
    finally:
        cleanup(slug, TABLES)
