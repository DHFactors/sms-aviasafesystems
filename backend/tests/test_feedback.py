"""
Tests for the in-product feedback endpoint (Priority 3).

Verifies:
  1. Authenticated users can submit feedback (stored to Firestore feedback
     collection with role/tenant context).
  2. Unauthenticated / invalid requests are rejected.
  3. Payload validation (empty subject/message rejected).
"""

from unittest.mock import patch

from app.main import app
from app.middleware.auth import get_current_user


def _user(role="AIRLINE_ADMIN", tenant_id="test_airline"):
    return {
        "uid": "mock_user",
        "email": "test@aviasafe.com",
        "role": role,
        "tenant_id": tenant_id,
        "claims": {"role": role, "tenant_id": tenant_id},
    }


def _override_current_user(user):
    app.dependency_overrides[get_current_user] = lambda: user


def _clear_overrides():
    app.dependency_overrides.pop(get_current_user, None)


def test_feedback_requires_auth(client):
    resp = client.post("/api/v1/feedback", json={})
    assert resp.status_code in (401, 403), resp.text


def test_feedback_rejects_empty_message(client):
    _override_current_user(_user())
    try:
        resp = client.post(
            "/api/v1/feedback",
            json={"subject": "SSM Risk Trends", "message": ""},
        )
        assert resp.status_code == 422, resp.text
    finally:
        _clear_overrides()


def test_feedback_stores_with_role_and_tenant(client):
    _override_current_user(_user(role="AIRLINE_ADMIN", tenant_id="test_airline"))
    captured = {}

    class FakeDocRef:
        id = "feedback_123"

    class FakeWriteBatch:
        def add(self, data):
            captured["data"] = data
            return (None, FakeDocRef())

    class FakeCollection:
        def add(self, data):
            captured["data"] = data
            return (None, FakeDocRef())

    class FakeDB:
        def collection(self, name):
            captured["collection"] = name
            return FakeCollection()

    with patch("app.routes.feedback.get_db", return_value=FakeDB()):
        try:
            resp = client.post(
                "/api/v1/feedback",
                json={
                    "subject": "SSM Risk Trends",
                    "message": "The line chart is very helpful.",
                    "rating": 4,
                    "page": "/safety.html",
                },
            )
            assert resp.status_code == 201, resp.text
            body = resp.json()
            assert body["status"] == "success"
            assert body["data"]["ok"] is True
            assert body["data"]["id"] == "feedback_123"
        finally:
            _clear_overrides()

    assert captured["collection"] == "feedback"
    data = captured["data"]
    assert data["tenant_id"] == "test_airline"
    assert data["role"] == "AIRLINE_ADMIN"
    assert data["rating"] == 4
    assert data["page"] == "/safety.html"
    assert data["status"] == "new"
    assert "email" in data
