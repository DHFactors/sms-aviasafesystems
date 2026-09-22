# ============================================================================
# P3-4 — SAG / SRB / action-items API.
# ============================================================================

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user
from app.services.meeting_service import MeetingService

client = TestClient(app)


def _user(role="TENANT_ADMIN", tenant_id="air1"):
    return {"uid": "u1", "email": "sm@air1.com", "role": role, "tenant_id": tenant_id}


def test_meeting_routes_require_safety_manager():
    app.dependency_overrides[get_current_user] = lambda: _user(role="STAFF")
    try:
        assert client.get("/api/v1/sag/meetings").status_code == 403
        assert client.get("/api/v1/srb/meetings").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_sag_meeting_crud(monkeypatch):
    monkeypatch.setattr(MeetingService, "create_meeting",
                        lambda self, mt, **f: {"id": "m1", "status": "Scheduled",
                                               "meeting_type": mt})
    monkeypatch.setattr(MeetingService, "list_meetings",
                        lambda self, mt, status=None: [{"id": "m1", "meeting_type": mt}])
    monkeypatch.setattr(MeetingService, "update_meeting",
                        lambda self, mt, mid, payload: {"id": mid, "status": "Held"})
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.post("/api/v1/sag/meetings",
                        json={"scheduled_at": "2026-03-01T09:00:00+00:00"})
        assert r.status_code == 201, r.text
        assert r.json()["data"]["meeting_type"] == "sag"

        g = client.get("/api/v1/sag/meetings")
        assert g.status_code == 200
        assert g.json()["data"]["meetings"][0]["meeting_type"] == "sag"

        p = client.patch("/api/v1/sag/meetings/m1", json={"status": "Held"})
        assert p.status_code == 200
        assert p.json()["data"]["status"] == "Held"
    finally:
        app.dependency_overrides.clear()


def test_srb_meeting_create(monkeypatch):
    monkeypatch.setattr(MeetingService, "create_meeting",
                        lambda self, mt, **f: {"id": "m2", "meeting_type": mt})
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.post("/api/v1/srb/meetings", json={"minutes_ref": "SRB-1"})
        assert r.status_code == 201
        assert r.json()["data"]["meeting_type"] == "srb"
    finally:
        app.dependency_overrides.clear()


def test_action_item_create_and_update(monkeypatch):
    monkeypatch.setattr(MeetingService, "create_action_item",
                        lambda self, mt, mid, payload: {"id": "a1", "meeting_type": mt})
    monkeypatch.setattr(MeetingService, "update_action_item",
                        lambda self, aid, payload: {"id": aid, "status": "Closed"})
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.post("/api/v1/action-items",
                        json={"meeting_type": "sag", "meeting_id": "m1", "assigned_to": "A"})
        assert r.status_code == 201, r.text
        assert r.json()["data"]["meeting_type"] == "sag"

        p = client.patch("/api/v1/action-items/a1", json={"status": "Closed"})
        assert p.status_code == 200
        assert p.json()["data"]["status"] == "Closed"
    finally:
        app.dependency_overrides.clear()
