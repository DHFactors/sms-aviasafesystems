# ============================================================================
# P3-11 — AE dashboard KPI endpoint (GET /api/v1/dashboard/ae/kpis).
# ============================================================================

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user
from app.services.ae_kpi_service import AEKPIService
from app.services.can_cap_service import CanCapService

client = TestClient(app)


def _ae():
    return {"uid": "ae", "email": "ae@air1.com", "role": "ACCOUNTABLE_EXECUTIVE",
            "tenant_id": "air1"}


def test_ae_kpis_requires_ae_role():
    app.dependency_overrides[get_current_user] = lambda: {
        "uid": "u", "email": "u@air1.com", "role": "TENANT_ADMIN", "tenant_id": "air1"}
    try:
        assert client.get("/api/v1/dashboard/ae/kpis").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_ae_kpis_returns_numeric_strip(monkeypatch):
    monkeypatch.setattr(AEKPIService, "compute_hazard_response_time",
                        lambda self, tid, period=None:
                        {"avg_days": 3.5, "received_count": 4,
                         "hazards_total": 10, "received_rate": 0.4})
    monkeypatch.setattr(CanCapService, "list_all_caps",
                        lambda self, user, filters:
                        [{"status": "In Progress", "escalated_to_ae": True,
                          "ae_signed_at": None},   # awaiting AE decision
                         {"status": "EIP", "escalated_to_ae": True,
                          "ae_signed_at": "2026-01-01T00:00:00Z"}])  # already decided

    async def _reg(tid):
        return {"rows": [{"accepted": False, "status": "open"},
                         {"accepted": True, "status": "closed"}]}

    from app.services import sram_service
    monkeypatch.setattr(sram_service, "get_risk_register", _reg)
    app.dependency_overrides[get_current_user] = lambda: _ae()
    try:
        r = client.get("/api/v1/dashboard/ae/kpis")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["avg_days_registration_to_first_action"] == 3.5
        assert d["hazards_received"] == 4
        assert d["hazards_total"] == 10
        assert d["received_rate"] == 0.4
        assert d["eip_awaiting_ae"] == 1
        assert d["acceptances_pending"] == 1
    finally:
        app.dependency_overrides.clear()


def test_ae_kpis_period_param(monkeypatch):
    captured = {}
    monkeypatch.setattr(AEKPIService, "compute_hazard_response_time",
                        lambda self, tid, period=None:
                        {"avg_days": None, "received_count": 0,
                         "hazards_total": 0, "received_rate": 0.0})
    monkeypatch.setattr(CanCapService, "list_all_caps", lambda self, user, filters: [])
    app.dependency_overrides[get_current_user] = lambda: _ae()
    try:
        r = client.get("/api/v1/dashboard/ae/kpis?period=30d")
        assert r.status_code == 200
        assert r.json()["data"]["period_days"] == 30
        r2 = client.get("/api/v1/dashboard/ae/kpis?granularity=week")
        assert r2.json()["data"]["granularity"] == "week"
    finally:
        app.dependency_overrides.clear()
