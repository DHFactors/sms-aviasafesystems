# ============================================================================
# P3-15 — Master register EIP / Overdue surface + dept filter.
# ============================================================================

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user
from app.services import master_register as mr

client = TestClient(app)


def _user(role="TENANT_ADMIN", tenant="air1", email="safety@air1.com"):
    return {"uid": "u", "email": email, "role": role, "tenant_id": tenant}


def _fake_register(*a, **k):
    return {"rows": [
        {"id": "c1", "status": "EIP", "type": "CAP"},
        {"id": "c2", "status": "Overdue", "type": "CAP"},
        {"id": "c3", "status": "Closed", "type": "CAN"},
    ], "total": 3}


def test_master_register_default_exposes_counts(monkeypatch):
    monkeypatch.setattr(mr, "build_master_register", _fake_register)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.get("/api/v1/dashboard/master-register")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["eip_count"] == 1
        assert d["overdue_count"] == 1
    finally:
        app.dependency_overrides.clear()


def test_master_register_surface_eip(monkeypatch):
    monkeypatch.setattr(mr, "build_master_register", _fake_register)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.get("/api/v1/dashboard/master-register?surface=eip")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["surface"] == "eip"
        assert d["surface_count"] == 1
        assert d["rows"][0]["id"] == "c1"
    finally:
        app.dependency_overrides.clear()


def test_master_register_surface_overdue(monkeypatch):
    monkeypatch.setattr(mr, "build_master_register", _fake_register)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.get("/api/v1/dashboard/master-register?surface=overdue")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["surface"] == "overdue"
        assert [row["id"] for row in d["rows"]] == ["c2"]
    finally:
        app.dependency_overrides.clear()


def test_master_register_bad_surface_rejected(monkeypatch):
    monkeypatch.setattr(mr, "build_master_register", _fake_register)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.get("/api/v1/dashboard/master-register?surface=bogus")
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_master_register_dept_filter_scoping(monkeypatch):
    captured = {}

    def _capture(user, department=None, **k):
        captured["department"] = department
        return {"rows": []}

    monkeypatch.setattr(mr, "build_master_register", _capture)
    app.dependency_overrides[get_current_user] = lambda: _user(email="camo@air1.com")
    try:
        r = client.get("/api/v1/dashboard/master-register?department=Part-145")
        assert r.status_code == 200
        # A department account's scope is forced to its own department (CAMO).
        assert captured["department"] == "CAMO"
    finally:
        app.dependency_overrides.clear()
