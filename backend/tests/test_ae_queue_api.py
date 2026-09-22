# ============================================================================
# P3-7 — AE action queues (escalated CAPs + pending risk acceptances).
# ============================================================================

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user
from app.services.can_cap_service import CanCapService

client = TestClient(app)


def _user(role="ACCOUNTABLE_EXECUTIVE", tenant_id="air1"):
    return {"uid": "ae", "email": "ae@air1.com", "role": role, "tenant_id": tenant_id}


def test_escalated_caps_filter_passed_to_service(monkeypatch):
    captured = {}

    def fake_list(self, user, filters):
        captured.update(filters)
        return [{"id": "cap1", "status": "In Progress", "escalated_to_ae": True}]

    monkeypatch.setattr(CanCapService, "list_all_caps", fake_list)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.get("/api/v1/cans/caps?escalated_to_ae=true")
        assert r.status_code == 200, r.text
        assert captured.get("escalated_to_ae") is True
        assert r.json()[0]["escalated_to_ae"] is True
    finally:
        app.dependency_overrides.clear()


def test_ae_queue_requires_auth():
    r = client.get("/api/v1/cans/caps?escalated_to_ae=true")
    assert r.status_code in (401, 403)


def test_risk_register_acceptances_pending(monkeypatch):
    async def fake_reg(tid):
        return {"rows": [
            {"id": "r1", "accepted": False, "status": "open"},
            {"id": "r2", "accepted": True, "status": "closed"},
            {"id": "r3", "accepted": False, "status": "closed"},
        ]}

    from app.services import sram_service
    monkeypatch.setattr(sram_service, "get_risk_register", fake_reg)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.get("/api/v1/sram/risk-register/air1?acceptances_pending=true")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["pending_count"] == 1
        assert data["rows"][0]["id"] == "r1"
    finally:
        app.dependency_overrides.clear()
