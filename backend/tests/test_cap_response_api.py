# ============================================================================
# P3-9 — department-scoped CAP response (PATCH /api/v1/cans/caps/{id}).
# ============================================================================

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user
from app.services.can_cap_service import CanCapService

client = TestClient(app)


def _user(role="USER", tenant_id="air1", email="camo@air1.com"):
    return {"uid": "u1", "email": email, "role": role, "tenant_id": tenant_id}


def test_dept_user_can_update_own_dept_cap(monkeypatch):
    monkeypatch.setattr(CanCapService, "get_cap",
                        lambda self, cid, user: {"id": cid, "department": "CAMO"})
    monkeypatch.setattr(CanCapService, "update_cap",
                        lambda self, cid, payload, user: {"id": cid, "department": "CAMO",
                                                          "status": payload.get("status")})
    app.dependency_overrides[get_current_user] = lambda: _user(email="camo@air1.com")
    try:
        r = client.patch("/api/v1/cans/caps/cap1", json={"review_comments": "done"})
        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.clear()


def test_dept_user_blocked_from_other_dept_cap(monkeypatch):
    monkeypatch.setattr(CanCapService, "get_cap",
                        lambda self, cid, user: {"id": cid, "department": "Part-145"})
    called = {"update": False}
    monkeypatch.setattr(CanCapService, "update_cap",
                        lambda *a, **k: called.update(update=True))
    app.dependency_overrides[get_current_user] = lambda: _user(email="camo@air1.com")
    try:
        r = client.patch("/api/v1/cans/caps/cap1", json={"review_comments": "x"})
        assert r.status_code == 403
        assert "Department isolation" in r.text
        assert called["update"] is False
    finally:
        app.dependency_overrides.clear()


def test_non_dept_user_unaffected(monkeypatch):
    monkeypatch.setattr(CanCapService, "get_cap",
                        lambda self, cid, user: {"id": cid, "department": "Part-145"})
    monkeypatch.setattr(CanCapService, "update_cap",
                        lambda self, cid, payload, user: {"id": cid, "status": "In Progress"})
    app.dependency_overrides[get_current_user] = lambda: _user(
        role="TENANT_ADMIN", email="safety@air1.com")
    try:
        r = client.patch("/api/v1/cans/caps/cap1", json={"review_comments": "ok"})
        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.clear()
