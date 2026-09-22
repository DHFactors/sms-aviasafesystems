# ============================================================================
# P3-10 — State SPI/SPT endpoints.
# ============================================================================

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user
from app.services.spi_service import SPIService
from app.services.state_spt_service import StateSPTService

client = TestClient(app)


def _caan():
    return {"uid": "c", "email": "smd@caan.np", "role": "CAAN_SMD", "tenant_id": None}


def _airline():
    return {"uid": "a", "email": "a@air.com", "role": "AIRLINE_ADMIN", "tenant_id": "air1"}


def test_state_endpoints_require_caan():
    app.dependency_overrides[get_current_user] = lambda: _airline()
    try:
        assert client.get("/api/v1/spi/state/values").status_code == 403
        assert client.get("/api/v1/spi/state/trend").status_code == 403
        assert client.get("/api/v1/spi/state/targets").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_state_trend(monkeypatch):
    monkeypatch.setattr(SPIService, "get_state_values", lambda self, *a, **k: {})
    monkeypatch.setattr(SPIService, "compute_state_trend",
                        lambda self, sid, months=2: {"trend": "improving",
                                                    "previous_value": 1.0,
                                                    "current_value": 2.0})
    app.dependency_overrides[get_current_user] = lambda: _caan()
    try:
        r = client.get("/api/v1/spi/state/trend?months=3")
        assert r.status_code == 200, r.text
        assert r.json()["trends"][0]["trend"] == "improving"
    finally:
        app.dependency_overrides.clear()


def test_spt_create_approve_list_delete(monkeypatch):
    monkeypatch.setattr(StateSPTService, "set_state_spt",
                        lambda self, sid, val, period, user, valid_from=None, valid_to=None:
                        {"id": "spt1", "spi_definition_id": sid, "target_value": val,
                         "approved_by": None})
    monkeypatch.setattr(StateSPTService, "approve_state_spt",
                        lambda self, sid, user: {"id": sid, "approved_by": "smd@caan.np"})
    monkeypatch.setattr(StateSPTService, "list_state_spts",
                        lambda self, period=None: [{"id": "spt1"}])
    monkeypatch.setattr(StateSPTService, "delete_state_spt", lambda self, sid, user: True)
    app.dependency_overrides[get_current_user] = lambda: _caan()
    try:
        c = client.post("/api/v1/spi/state/targets",
                        json={"spi_definition_id": "SPI-LAG-002", "target_value": 95.0})
        assert c.status_code == 201, c.text
        assert c.json()["data"]["target_value"] == 95.0

        a = client.post("/api/v1/spi/state/targets/spt1/approve")
        assert a.status_code == 200 and a.json()["data"]["approved_by"]

        g = client.get("/api/v1/spi/state/targets")
        assert g.status_code == 200 and g.json()["targets"][0]["id"] == "spt1"

        d = client.delete("/api/v1/spi/state/targets/spt1")
        assert d.status_code == 200 and d.json()["data"]["deleted"] is True
    finally:
        app.dependency_overrides.clear()
