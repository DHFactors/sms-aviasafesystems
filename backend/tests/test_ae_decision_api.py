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
