# ============================================================================
# P3-8 — AE terminal decision API (POST /api/v1/cans/caps/{id}/ae-decision).
# ============================================================================

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user
from app.services.can_cap_service import CanCapService

client = TestClient(app)


def _user(role="ACCOUNTABLE_EXECUTIVE", tenant_id="air1"):
    return {"uid": "ae", "email": "ae@air1.com", "role": role, "tenant_id": tenant_id}


def test_ae_decision_requires_ae_role():
    app.dependency_overrides[get_current_user] = lambda: _user(role="TENANT_ADMIN")
    try:
        r = client.post("/api/v1/cans/caps/cap1/ae-decision",
                        json={"decision_type": "acknowledge"})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_ae_decision_acknowledge_sets_eip(monkeypatch):
    monkeypatch.setattr(CanCapService, "ae_decide",
                        lambda self, cid, dt, user, notes=None:
                        {"id": cid, "status": "EIP", "ae_signature": {"decision": dt},
                         "tenant_id": "air1", "can_id": "can1", "cap_reference": "CAP-1"})
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.post("/api/v1/cans/caps/cap1/ae-decision",
                        json={"decision_type": "acknowledge", "notes": "ack"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "success"
        assert body["data"]["status"] == "EIP"
    finally:
        app.dependency_overrides.clear()


def test_ae_decision_bad_type():
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.post("/api/v1/cans/caps/cap1/ae-decision",
                        json={"decision_type": "reject"})
        assert r.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_ae_decision_immutable_conflict(monkeypatch):
    def _raise(self, cid, dt, user, notes=None):
        raise ValueError("AE decision already recorded; it is terminal and immutable")

    monkeypatch.setattr(CanCapService, "ae_decide", _raise)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.post("/api/v1/cans/caps/cap1/ae-decision",
                        json={"decision_type": "direct"})
        assert r.status_code == 400
        assert "immutable" in r.text.lower()
    finally:
        app.dependency_overrides.clear()


def test_ae_decision_404(monkeypatch):
    monkeypatch.setattr(CanCapService, "ae_decide", lambda *a, **k: None)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.post("/api/v1/cans/caps/missing/ae-decision",
                        json={"decision_type": "acknowledge"})
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


# ============================================================================
# P3-8b — AE decision PDF (GET /api/v1/cans/caps/{id}/decision.pdf).
# Hermetic: get_cap mocked on the service, signature row faked at the
# session boundary. No database.
# ============================================================================

from types import SimpleNamespace


def _decided_cap():
    return {"id": "cap1", "cap_reference": "CAP-1", "department": "CAMO",
            "ae_signed_at": "2026-01-02T00:00:00+00:00",
            "ae_signature": "ae@air1.com"}


def _decided_sig():
    return {"name": "ae@air1.com", "decision": "acknowledge",
            "notes": "Signed by ae@air1.com (AE attestation). ok",
            "signed_by": "ae@air1.com",
            "signed_at": "2026-01-02T00:00:00+00:00"}


class _FakeScalars:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalars(self):
        return _FakeScalars(self._row)


class _FakeSession:
    def __init__(self, row):
        self._row = row

    async def execute(self, stmt):
        return _FakeResult(self._row)


class _FakeSessionCM:
    def __init__(self, row):
        self._row = row

    async def __aenter__(self):
        return _FakeSession(self._row)

    async def __aexit__(self, *args):
        return False


def _patch_decision_pdf(monkeypatch, cap=None, sig="__decided__"):
    """Mock the decision-record lookup to return the raw-signature shape.

    sig="__decided__" installs the standard decided signature block;
    any other value (None, a string, a dict) is used verbatim.
    """
    resolved = _decided_sig() if sig == "__decided__" else sig
    doc = dict(cap) if cap else None
    if doc is not None:
        doc["ae_signature"] = resolved
    monkeypatch.setattr(CanCapService, "get_cap_for_decision_record",
                        lambda self, cid, user: doc)


def test_ae_decision_pdf_200(monkeypatch):
    _patch_decision_pdf(monkeypatch, _decided_cap())
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.get("/api/v1/cans/caps/cap1/decision.pdf")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
        assert "attachment" in r.headers["content-disposition"]
        assert "ae-decision-CAP-1.pdf" in r.headers["content-disposition"]
        assert r.content.startswith(b"%PDF")
    finally:
        app.dependency_overrides.clear()


def test_ae_decision_pdf_tenant_admin_200(monkeypatch):
    _patch_decision_pdf(monkeypatch, _decided_cap())
    app.dependency_overrides[get_current_user] = lambda: _user(role="TENANT_ADMIN")
    try:
        r = client.get("/api/v1/cans/caps/cap1/decision.pdf")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
    finally:
        app.dependency_overrides.clear()


def test_ae_decision_pdf_forbidden_roles(monkeypatch):
    _patch_decision_pdf(monkeypatch, _decided_cap())
    try:
        for role in ("DEPT_ADMIN", "OFFICER", "CAAN_SMD"):
            app.dependency_overrides[get_current_user] = lambda r=role: _user(role=r)
            r = client.get("/api/v1/cans/caps/cap1/decision.pdf")
            assert r.status_code == 403, (role, r.text)
    finally:
        app.dependency_overrides.clear()


def test_ae_decision_pdf_no_tenant(monkeypatch):
    _patch_decision_pdf(monkeypatch, _decided_cap())
    app.dependency_overrides[get_current_user] = lambda: _user(tenant_id=None)
    try:
        r = client.get("/api/v1/cans/caps/cap1/decision.pdf")
        assert r.status_code == 403, r.text
    finally:
        app.dependency_overrides.clear()


def test_ae_decision_pdf_missing_cap(monkeypatch):
    _patch_decision_pdf(monkeypatch, None)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.get("/api/v1/cans/caps/missing/decision.pdf")
        assert r.status_code == 404, r.text
    finally:
        app.dependency_overrides.clear()


def test_ae_decision_pdf_undecided(monkeypatch):
    cap = dict(_decided_cap(), ae_signed_at=None)
    _patch_decision_pdf(monkeypatch, cap)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.get("/api/v1/cans/caps/cap1/decision.pdf")
        assert r.status_code == 404, r.text
        assert "No AE decision recorded" in r.text
    finally:
        app.dependency_overrides.clear()


def test_ae_decision_pdf_bad_signature(monkeypatch):
    for bad in (None, "just-a-name", ["not", "a", "dict"]):
        _patch_decision_pdf(monkeypatch, _decided_cap(), sig=bad)
        app.dependency_overrides[get_current_user] = lambda: _user()
        try:
            r = client.get("/api/v1/cans/caps/cap1/decision.pdf")
            assert r.status_code == 404, (bad, r.text)
        finally:
            app.dependency_overrides.clear()


def test_ae_decision_pdf_other_tenant_unreachable(monkeypatch):
    # Cross-tenant lookup naturally misses: the tenant-scoped service
    # finds no row, so the route answers 404 (never 403, never leaked).
    _patch_decision_pdf(monkeypatch, None)
    app.dependency_overrides[get_current_user] = lambda: _user(tenant_id="other-air")
    try:
        r = client.get("/api/v1/cans/caps/cap1/decision.pdf")
        assert r.status_code == 404, r.text
    finally:
        app.dependency_overrides.clear()


def test_decision_record_keeps_raw_signature_while_get_cap_flattens(monkeypatch):
    """Guard the distinction the PDF route depends on: the decision-record
    lookup preserves the full ae_signature JSONB while get_cap's
    _cap_to_dict collapses it to the signer name."""
    from datetime import datetime, timezone

    from app.db.db_models import Cap
    from app.services import can_cap_service as ccs

    sig = {"name": "ae@air1.com", "decision": "direct", "notes": "fix it",
           "signed_by": "ae@air1.com", "signed_at": "2026-01-02T00:00:00+00:00"}
    attrs = {c.name: None for c in Cap.__table__.columns}
    attrs.update(ae_signature=dict(sig),
                 ae_signed_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                 tenant_id="tid")
    row = SimpleNamespace(**attrs)
    monkeypatch.setattr(ccs, "session_scope", lambda: _FakeSessionCM(row))

    svc = CanCapService("air1")
    raw = svc.get_cap_for_decision_record(
        "cap1", {"role": "TENANT_ADMIN", "tenant_id": "air1"})
    flat = ccs._cap_to_dict(row)
    assert raw["ae_signature"] == sig
    assert flat["ae_signature"] == "ae@air1.com"
