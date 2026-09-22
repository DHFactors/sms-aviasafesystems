# ============================================================================
# P2-15 / P2-16 — AE terminal decision + EIP transitions.
# ============================================================================

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db.db_models import Can, Cap, Hazard
from app.db.isolation import demo_scope
from app.db.session import session_scope
from app.services.can_cap_service import CanCapService

from _mbb import cleanup, create_tenant, run, unique_slug

TABLES = ("caps", "cans", "hazards")


def _seed_cap(tid: str, suffix: str = "1") -> str:
    can_id, cap_id, haz_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    now = datetime.now(timezone.utc)

    async def _go():
        async with session_scope() as s:
            s.add(Hazard(id=haz_id, tenant_id=tid, hazard_id=f"CC-{suffix}",
                         title="h", description="d", source="voluntary",
                         taxonomy="Organizational", priority="M", status="Open",
                         is_demo=demo_scope()))
            await s.flush()
            s.add(Can(id=can_id, tenant_id=tid, hazard_id=haz_id,
                      can_reference=f"CAN-{suffix}", title="t", description="d",
                      required_action="a", issued_by="x", issued_by_uid="u",
                      assigned_to="y", assigned_to_uid="v", priority="High",
                      status="Open", is_demo=demo_scope()))
            await s.flush()
            s.add(Cap(id=cap_id, tenant_id=tid, can_id=can_id,
                      cap_reference=f"CAP-{suffix}", action_plan="p", timeline="t",
                      resources_required="r", implementation_plan="i",
                      target_completion_date=now, submitted_by="x",
                      submitted_by_uid="u", status="In Progress", is_demo=demo_scope()))

    run(_go())
    return str(cap_id)


def _status(cap_id: str) -> str:
    async def _go():
        async with session_scope() as s:
            row = (await s.execute(
                select(Cap).where(Cap.id == uuid.UUID(cap_id))
            )).scalars().first()
            return row.status, row.ae_signed_at

    return run(_go())


def test_ae_decide_requires_ae_role():
    slug = unique_slug("ae")
    tid = create_tenant(slug)
    cap_id = _seed_cap(tid)
    try:
        svc = CanCapService(slug)
        with pytest.raises(PermissionError):
            svc.ae_decide(cap_id, "acknowledge",
                          {"role": "SAFETY_OFFICER", "uid": "u"})
    finally:
        cleanup(slug, TABLES)


def test_ae_acknowledge_sets_eip_and_is_immutable():
    slug = unique_slug("ae2")
    tid = create_tenant(slug)
    cap_id = _seed_cap(tid)
    try:
        svc = CanCapService(slug)
        ae = {"role": "ACCOUNTABLE_EXECUTIVE", "uid": "ae", "email": "ae@x.com"}
        result = svc.ae_decide(cap_id, "acknowledge", ae, notes="ack")
        assert result["status"] == "EIP"
        assert result["ae_signed_at"] is not None

        async def _sig():
            async with session_scope() as s:
                row = (await s.execute(
                    select(Cap).where(Cap.id == uuid.UUID(cap_id))
                )).scalars().first()
                return row.ae_signature

        sig = run(_sig())
        assert sig["decision"] == "acknowledge"
        assert sig["notes"] == "ack"

        # Terminal + immutable: a second decision is rejected.
        with pytest.raises(ValueError):
            svc.ae_decide(cap_id, "direct", ae, notes="again")

        # No recall to Revision Required after the AE decision.
        with pytest.raises(ValueError):
            svc.review_cap(cap_id, {"status": "Revision Required", "comments": "no"},
                           {"role": "TENANT_ADMIN", "uid": "sm", "email": "sm@x.com"})
    finally:
        cleanup(slug, TABLES)


def test_eip_resolves_to_closed_on_completion():
    slug = unique_slug("ae3")
    tid = create_tenant(slug)
    cap_id = _seed_cap(tid, suffix="3")
    try:
        svc = CanCapService(slug)
        ae = {"role": "ACCOUNTABLE_EXECUTIVE", "uid": "ae", "email": "ae@x.com"}
        assert svc.ae_decide(cap_id, "acknowledge", ae)["status"] == "EIP"

        result = svc.review_cap(
            cap_id, {"status": "Completed", "comments": "done"},
            {"role": "TENANT_ADMIN", "uid": "sm", "email": "sm@x.com"})
        assert result["status"] == "Closed"
    finally:
        cleanup(slug, TABLES)
