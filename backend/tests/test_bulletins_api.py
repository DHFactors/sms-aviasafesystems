# ============================================================================
# P3-5 — safety bulletins API + lifecycle.
# ============================================================================

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user, get_safety_manager
from app.services.safety_comms_service import SafetyCommsService

client = TestClient(app)


def _user(role="SAFETY_OFFICER", tenant_id="air1"):
    return {"uid": "u1", "email": "so@air1.com", "role": role, "tenant_id": tenant_id}


def test_bulletin_draft_allows_safety_officer(monkeypatch):
    monkeypatch.setattr(SafetyCommsService, "create_draft",
                        lambda self, user, title, body=None, audience=None, hids=None:
                        {"id": "b1", "status": "draft", "title": title})
    app.dependency_overrides[get_current_user] = lambda: _user(role="SAFETY_OFFICER")
    try:
        r = client.post("/api/v1/bulletins", json={"title": "Runway safety"})
        assert r.status_code == 201, r.text
        assert r.json()["data"]["status"] == "draft"
    finally:
        app.dependency_overrides.clear()


def test_bulletin_draft_rejects_staff():
    app.dependency_overrides[get_current_user] = lambda: _user(role="STAFF")
    try:
        r = client.post("/api/v1/bulletins", json={"title": "x"})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_bulletin_lifecycle(monkeypatch):
    monkeypatch.setattr(SafetyCommsService, "submit_for_review",
                        lambda self, cid, user: {"id": cid, "status": "review"})
    monkeypatch.setattr(SafetyCommsService, "publish",
                        lambda self, cid, user: {"id": cid, "status": "published"})
    monkeypatch.setattr(SafetyCommsService, "archive",
                        lambda self, cid, user: {"id": cid, "status": "archived"})
    monkeypatch.setattr(SafetyCommsService, "list_communications",
                        lambda self, status=None: [{"id": "b1", "status": "published"}])
    app.dependency_overrides[get_current_user] = lambda: _user(role="SAFETY_OFFICER")
    app.dependency_overrides[get_safety_manager] = lambda: _user(role="TENANT_ADMIN")
    try:
        assert client.patch("/api/v1/bulletins/b1/submit").json()["data"]["status"] == "review"
        assert client.patch("/api/v1/bulletins/b1/publish").json()["data"]["status"] == "published"
        assert client.patch("/api/v1/bulletins/b1/archive").json()["data"]["status"] == "archived"
        assert client.get("/api/v1/bulletins").json()["data"]["bulletins"][0]["status"] == "published"
    finally:
        app.dependency_overrides.clear()
