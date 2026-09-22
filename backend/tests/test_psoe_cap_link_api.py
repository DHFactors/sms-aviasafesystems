# ============================================================================
# P3-14 — PSOE finding ↔ CAP link endpoints.
# ============================================================================

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user
from app.services.psoe_cap_link_service import PsoeCapLinkService

client = TestClient(app)


def _manager(tenant="air1"):
    return {"uid": "sm", "email": "sm@air.com", "role": "TENANT_ADMIN",
            "tenant_id": tenant}


def test_link_requires_safety_manager():
    app.dependency_overrides[get_current_user] = lambda: {
        "uid": "u", "email": "u@air.com", "role": "STAFF", "tenant_id": "air1"}
    try:
        r = client.post("/api/v1/supabase/psoe/findings/f1/link-cap",
                        json={"cap_id": "cap1"})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_link_unlink_and_get(monkeypatch):
    monkeypatch.setattr(PsoeCapLinkService, "link_finding_to_cap",
                        lambda self, fid, cid, user: {"finding_id": fid, "cap_id": cid})
    monkeypatch.setattr(PsoeCapLinkService, "unlink_finding_from_cap",
                        lambda self, fid, user: {"finding_id": fid, "cap_id": None})
    monkeypatch.setattr(PsoeCapLinkService, "list_links_for_finding",
                        lambda self, fid: {"finding_id": fid, "cap_id": "cap1"})
    monkeypatch.setattr(PsoeCapLinkService, "list_links_for_cap",
                        lambda self, cid: {"cap_id": cid, "finding_id": "f1"})
    app.dependency_overrides[get_current_user] = lambda: _manager()
    try:
        c = client.post("/api/v1/supabase/psoe/findings/f1/link-cap",
                        json={"cap_id": "cap1"})
        assert c.status_code == 200, c.text
        assert c.json()["data"]["cap_id"] == "cap1"

        g = client.get("/api/v1/supabase/psoe/findings/f1/links")
        assert g.status_code == 200 and g.json()["data"]["cap_id"] == "cap1"

        d = client.delete("/api/v1/supabase/psoe/findings/f1/link-cap")
        assert d.status_code == 200 and d.json()["data"]["cap_id"] is None

        # CAP-side reverse lookup.
        r = client.get("/api/v1/cans/caps/cap1/linked-findings")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["finding_id"] == "f1"
    finally:
        app.dependency_overrides.clear()
