# ============================================================================
# P3-3 — MOR regulatory-submit API (POST /api/v1/reports/{id}/regulatory-submit).
# ============================================================================

from fastapi.testclient import TestClient

from app.db.ids import register_tenant
from app.main import app
from app.middleware.auth import get_current_user

client = TestClient(app)


def _user(role="AIRLINE_ADMIN", tenant_id="air1"):
    return {"uid": "u1", "email": "sm@air1.com", "role": role, "tenant_id": tenant_id}


def test_regulatory_submit_requires_safety_manager():
    app.dependency_overrides[get_current_user] = lambda: _user(role="STAFF")
    try:
        r = client.post("/api/v1/reports/R1/regulatory-submit", json={})
        assert r.status_code in (403, 422)
    finally:
        app.dependency_overrides.clear()


def test_regulatory_submit_rejects_caan():
    app.dependency_overrides[get_current_user] = lambda: {
        "uid": "c", "email": "c@caan.np", "role": "CAAN_SMD", "tenant_id": None}
    try:
        r = client.post("/api/v1/reports/R1/regulatory-submit", json={})
        assert r.status_code in (403, 422)
    finally:
        app.dependency_overrides.clear()


def test_regulatory_submit_404_for_missing(monkeypatch):
    # No report row -> 404.
    monkeypatch.setattr("app.db.pg.fetch_by", lambda *a, **k: None)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.post("/api/v1/reports/R1/regulatory-submit", json={})
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_regulatory_submit_persists(monkeypatch):
    tid = register_tenant("air1")
    monkeypatch.setattr("app.db.pg.fetch_by", lambda *a, **k: {"id": "R1", "tenant_id": tid})
    captured = {}
    monkeypatch.setattr("app.db.pg.update", lambda model, col, val, doc: captured.update(doc))
    monkeypatch.setattr("app.routes.occurrence_reports.log_audit", lambda **k: None)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.post("/api/v1/reports/R1/regulatory-submit",
                        json={"submission_ref": "CAA-123"})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["regulatory_submission_ref"] == "CAA-123"
        assert captured.get("regulatory_submission_ref") == "CAA-123"
        assert captured.get("regulatory_submitted_at") is not None
    finally:
        app.dependency_overrides.clear()
