# ============================================================================
# Module B Phase 2 services part 1 (P2-3 .. P2-8).
#
#  P2-3 follow_up_date derivation (H+24h / M+7d / L+15d; manual override wins)
#  P2-4 derived risk-overdue + CAP terminal statuses
#  P2-5 authority-tier enforcement in accept_risk
#  P2-6 two-signature acceptance workflow
#  P2-7 discrete (banded) BSV via srm_engine
#  P2-8 one sram_risk_register row per bow-tie consequence
# ============================================================================

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.db.db_models import (
    BowTieAnalysis,
    BowTieConsequence,
    Hazard,
    SramRiskRegisterEntry,
    UserProfile,
)
from app.db.ids import register_tenant
from app.db.session import session_scope
from app.services import escalation_service, sram_service
from app.services.hazard_service import HazardService, derive_follow_up_date
from app.services.sram_service import is_risk_overdue


def _run(coro):
    return asyncio.run(coro)


def _unique_slug(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _parse(value):
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _create_tenant(slug: str) -> str:
    tid = register_tenant(slug)

    async def _go():
        async with session_scope() as s:
            await s.execute(text(
                "INSERT INTO public.tenants "
                "(id, slug, name, is_demo, is_beta_sandbox, created_at, updated_at) "
                "VALUES (:id, :slug, :name, false, false, now(), now()) "
                "ON CONFLICT DO NOTHING"
            ), {"id": tid, "slug": slug, "name": slug})

    _run(_go())
    return tid


def _create_user(tid: str, uid: str) -> str:
    """Insert a users row so process_by/accepted_by FK resolution succeeds."""
    user_id = uuid.uuid4()

    async def _go():
        async with session_scope() as s:
            s.add(UserProfile(
                id=user_id, uid=uid, email=f"{uid}@test.local",
                role="SAFETY_OFFICER", tenant_id=uuid.UUID(tid),
                is_developer=False, phone_verified=False,
            ))

    _run(_go())
    return str(user_id)


def _cleanup(slug: str) -> None:
    """Best-effort teardown: per-statement commits, never raises (see
    backend/tests/_mbb.py::cleanup)."""
    import logging

    tid = register_tenant(slug)

    async def _go():
        async with session_scope() as s:
            for stmt in (
                "DELETE FROM public.sram_risk_register WHERE tenant_id = :id",
                "DELETE FROM public.bow_tie_consequences WHERE tenant_id = :id",
                "DELETE FROM public.bow_tie_analyses WHERE tenant_id = :id",
                "DELETE FROM public.hazards WHERE tenant_id = :id",
                "DELETE FROM public.users WHERE tenant_id = :id",
                "DELETE FROM public.tenants WHERE id = :id",
            ):
                try:
                    await s.execute(text(stmt), {"id": tid})
                    await s.commit()
                except Exception as e:
                    try:
                        await s.rollback()
                    except Exception:
                        pass
                    logging.getLogger(__name__).warning(
                        "test cleanup: %s failed for %s: %s",
                        stmt.split()[2], slug, e)

    try:
        _run(_go())
    except Exception as e:
        logging.getLogger(__name__).warning(
            "test cleanup: session failed for %s: %s", slug, e)


# ---------------------------------------------------------------------------
# P2-3 — follow_up_date derivation
# ---------------------------------------------------------------------------

def test_derive_follow_up_date_windows():
    anchor = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert derive_follow_up_date("H", anchor) == anchor + timedelta(hours=24)
    assert derive_follow_up_date("M", anchor) == anchor + timedelta(days=7)
    assert derive_follow_up_date("L", anchor) == anchor + timedelta(days=15)
    assert derive_follow_up_date("M", None) is None


def test_follow_up_date_created_updated_and_manual_override():
    slug = _unique_slug("hzfu")
    _create_tenant(slug)
    try:
        svc = HazardService(slug)
        user = {"uid": "u-fu", "email": "fu@example.com"}
        doc = svc.create_hazard_v1({
            "title": "Follow-up derivation", "description": "d",
            "source": "voluntary", "priority": "M", "taxonomy": "Organizational",
        }, user)
        created = _parse(doc["created_at"])
        fu = _parse(doc["follow_up_date"])
        assert abs((fu - created).total_seconds() - 7 * 86400) < 180  # M -> +7d

        # Priority change to H re-derives to +24h.
        updated = svc.update_hazard(doc["hazard_id"], {"priority": "H"}, user)
        fu_h = _parse(updated["follow_up_date"])
        assert abs((fu_h - created).total_seconds() - 86400) < 180

        # Manual override wins and survives a later priority change.
        manual = datetime(2027, 1, 1, tzinfo=timezone.utc)
        svc.update_hazard(doc["hazard_id"], {"follow_up_date": manual.isoformat()}, user)
        updated3 = svc.update_hazard(doc["hazard_id"], {"priority": "L"}, user)
        assert _parse(updated3["follow_up_date"]) == manual
    finally:
        _cleanup(slug)


# ---------------------------------------------------------------------------
# P2-4 — derived risk-overdue + CAP terminal statuses
# ---------------------------------------------------------------------------

def test_is_risk_overdue_derivation():
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=1)
    future = now + timedelta(days=1)

    assert is_risk_overdue({"status": "open", "accepted": False, "review_date": past}, now=now)
    assert not is_risk_overdue({"status": "open", "accepted": False, "review_date": future}, now=now)
    assert not is_risk_overdue({"status": "closed", "accepted": False, "review_date": past}, now=now)
    assert not is_risk_overdue({"status": "open", "accepted": True, "review_date": past}, now=now)
    # Linked CAP overdue -> overdue regardless of review_date.
    assert is_risk_overdue({"status": "open", "accepted": False, "review_date": future},
                           now=now, cap_overdue=True)
    assert not is_risk_overdue(None)


def test_cap_terminal_statuses_exclude_overdue():
    from app.routes import scheduled_jobs

    assert "Overdue" not in escalation_service.CAP_TERMINAL_STATUSES
    assert {"Completed", "Closed", "Escalated"} <= escalation_service.CAP_TERMINAL_STATUSES
    assert "Overdue" not in scheduled_jobs.CAP_TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# P2-5 / P2-6 — authority tier + two-signature acceptance
# ---------------------------------------------------------------------------

def _seed_sram_entry(tid: str, *, tolerability="Intolerable", process_by=None):
    row_id = uuid.uuid4()

    async def _go():
        async with session_scope() as s:
            s.add(SramRiskRegisterEntry(
                id=row_id, tenant_id=uuid.UUID(tid), hazard_id="HZ-ACC",
                probability_current=5, severity_current=5, risk_index_current=25,
                tolerability_current=tolerability, status="open", accepted=False,
                process_by=process_by, is_demo=False,
            ))

    _run(_go())
    return str(row_id)


def test_accept_risk_requires_process_signature():
    slug = _unique_slug("hzsign")
    tid = _create_tenant(slug)
    entry_id = _seed_sram_entry(tid, tolerability="Acceptable")
    try:
        with pytest.raises(HTTPException) as exc:
            _run(sram_service.accept_risk(
                entry_id, {"alarp_justification": "x" * 20}, slug,
                {"role": "SAG_MEMBER", "uid": "u1", "email": "e@x.com"},
            ))
        assert exc.value.status_code == 403
        assert "signature" in exc.value.detail.lower()
    finally:
        _cleanup(slug)


def test_authority_tier_enforced_and_snapshot():
    slug = _unique_slug("hzauth")
    tid = _create_tenant(slug)
    entry_id = _seed_sram_entry(tid, tolerability="Intolerable")
    try:
        # Process signature first.
        signer_uid = "srauth-" + uuid.uuid4().hex[:8]
        _create_user(tid, signer_uid)
        _run(sram_service.process_sign_acceptance(
            entry_id, slug, {"role": "SAFETY_OFFICER", "uid": signer_uid}))
        # Wrong tier (Safety Officer cannot accept an Intolerable risk).
        with pytest.raises(HTTPException) as exc:
            _run(sram_service.accept_risk(
                entry_id, {"alarp_justification": "y" * 20}, slug,
                {"role": "SAFETY_OFFICER", "uid": "u1", "email": "e@x.com"},
            ))
        assert exc.value.status_code == 403

        # Correct tier (Accountable Executive).
        result = _run(sram_service.accept_risk(
            entry_id, {"alarp_justification": "y" * 20}, slug,
            {"role": "ACCOUNTABLE_EXECUTIVE", "uid": "ae1", "email": "ae@x.com"},
        ))
        assert result["accepted"] is True
        assert result["initial_authority"] == "Accountable Manager"
        assert result["process_by"] is not None
    finally:
        _cleanup(slug)


def test_two_signature_workflow_accepts_after_process_sign():
    slug = _unique_slug("hz2sig")
    tid = _create_tenant(slug)
    entry_id = _seed_sram_entry(tid, tolerability="Acceptable")
    try:
        signer_uid = "sr2sig-" + uuid.uuid4().hex[:8]
        signer_id = _create_user(tid, signer_uid)
        signed = _run(sram_service.process_sign_acceptance(
            entry_id, slug, {"role": "SAFETY_OFFICER", "uid": signer_uid}))
        assert signed["process_by"] == signer_id
        assert signed["process_signed_at"] is not None

        result = _run(sram_service.accept_risk(
            entry_id, {"alarp_justification": "z" * 20}, slug,
            {"role": "SAG_MEMBER", "uid": "sag1", "email": "sag@x.com"},
        ))
        assert result["accepted"] is True
        assert result["resultant_authority"] == "Safety Manager / SAG Member"
    finally:
        _cleanup(slug)


# ---------------------------------------------------------------------------
# P2-7 — discrete (banded) BSV
# ---------------------------------------------------------------------------

def test_score_barriers_uses_banded_engine():
    best = sram_service._score_barriers({
        "effectiveness": 5, "cost_benefit": 5, "practicality": 5,
        "acceptability": 5, "enforceability": 5, "durability": 5, "disinclination": 5,
    })
    assert best["bqv"] == 50
    assert best["bsv"] == 5
    assert best["robustness"] == "Excellent"

    worst = sram_service._score_barriers({
        "effectiveness": 1, "cost_benefit": 1, "practicality": 1,
        "acceptability": 1, "enforceability": 1, "durability": 1, "disinclination": 1,
    })
    assert worst["bqv"] == 10
    assert worst["bsv"] == 1


def test_calculate_bsv_retired():
    from app.services import risk_calculator
    assert not hasattr(risk_calculator, "calculate_bsv")


# ---------------------------------------------------------------------------
# P2-8 — per-consequence register rows
# ---------------------------------------------------------------------------

def test_per_consequence_register_rows():
    slug = _unique_slug("hzcons")
    tid = _create_tenant(slug)
    bowtie_id = uuid.uuid4()

    async def _seed():
        async with session_scope() as s:
            s.add(Hazard(
                tenant_id=tid, hazard_id="HZ-CONS", title="Consequence test",
                description="d", source="voluntary", taxonomy="Organizational",
                status="Open", is_demo=False,
            ))
            s.add(BowTieAnalysis(
                id=bowtie_id, tenant_id=tid, hazard_id="HZ-CONS",
                hazard_title="Consequence test", status="In Progress", is_demo=False,
            ))
            s.add(BowTieConsequence(
                tenant_id=tid, bowtie_id=bowtie_id, consequence="Loss of control",
                severity_level="A", consequence_order=1, is_demo=False,
            ))
            s.add(BowTieConsequence(
                tenant_id=tid, bowtie_id=bowtie_id, consequence="Minor damage",
                severity_level="E", consequence_order=2, is_demo=False,
            ))

    _run(_seed())
    try:
        risk_profile = {
            "resultant_risk": {"probability_value": 3, "tolerability": "Tolerable"},
        }
        result = _run(sram_service.sync_consequence_register_rows(
            "HZ-CONS", slug, risk_profile, "C"))
        rows = result["rows"]
        assert len(rows) == 2, rows
        consequence_ids = {r["consequence_id"] for r in rows}
        assert None not in consequence_ids
        # Per-consequence severity: A -> 5, E -> 1.
        by_sev = {r["severity_current"]: r for r in rows}
        assert by_sev[5]["risk_index_current"] == 15  # 5 * 3
        assert by_sev[1]["risk_index_current"] == 3   # 1 * 3

        # Re-running updates in place (unique key tenant+hazard+consequence).
        again = _run(sram_service.sync_consequence_register_rows(
            "HZ-CONS", slug, risk_profile, "C"))
        assert len(again["rows"]) == 2
    finally:
        _cleanup(slug)
