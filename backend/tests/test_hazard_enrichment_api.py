# ============================================================================
# P3-2 — hazard enrichment API (POST /api/v1/hazards/{id}/enrich).
# ============================================================================

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user
from app.services.hazard_enrichment_service import HazardEnrichmentService

client = TestClient(app)


def _user(role="SAFETY_OFFICER", tenant_id="air1"):
    return {"uid": "u1", "email": "so@air1.com", "role": role, "tenant_id": tenant_id}


def test_enrich_requires_safety_role():
    app.dependency_overrides[get_current_user] = lambda: _user(role="STAFF")
    try:
        r = client.post("/api/v1/hazards/HZ-1/enrich", json={"description": "x"})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_enrich_records_changes(monkeypatch):
    monkeypatch.setattr(HazardEnrichmentService, "enrich_hazard",
                        lambda self, hid, user, payload:
                        {"hazard_id": hid, "changes": [{"field": "description"}]})
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.post("/api/v1/hazards/HZ-1/enrich", json={"description": "updated"})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["changes"][0]["field"] == "description"
    finally:
        app.dependency_overrides.clear()


def test_enrich_rejects_create_only_field(monkeypatch):
    # The service rejects create-only fields; the route surfaces it as 400.
    def _raise(self, hid, user, payload):
        raise ValueError("Enrichment cannot modify create-only fields: ['source']")

    monkeypatch.setattr(HazardEnrichmentService, "enrich_hazard", _raise)
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.post("/api/v1/hazards/HZ-1/enrich", json={"source": "mandatory"})
        assert r.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_enrich_empty_body_rejected():
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        r = client.post("/api/v1/hazards/HZ-1/enrich", json={})
        assert r.status_code == 400
    finally:
        app.dependency_overrides.clear()
