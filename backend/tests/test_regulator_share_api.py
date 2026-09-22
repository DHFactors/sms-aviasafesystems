# ============================================================================
# P3-12 — Regulator share / escalation endpoints.
# ============================================================================

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user
from app.services.aggregation_service import AggregationService

client = TestClient(app)


def _caan():
    return {"uid": "c", "email": "smd@caan.np", "role": "CAAN_SMD", "tenant_id": None}


def _airline(tenant="air1"):
    return {"uid": "a", "email": "a@air.com", "role": "AIRLINE_ADMIN", "tenant_id": tenant}


def test_share_benchmark_requires_auth():
    r = client.get("/api/v1/regulator/share/benchmark/air1")
    assert r.status_code in (401, 403)


def test_share_benchmark_operator_own_tenant_only(monkeypatch):
    async def _bench(self, tenant_id, tids):
        return {"operator_score": 3.0, "industry_average": 3.5}

    monkeypatch.setattr(AggregationService, "get_benchmarking", _bench)
    app.dependency_overrides[get_current_user] = lambda: _airline("air1")
    try:
        ok = client.get("/api/v1/regulator/share/benchmark/air1")
        assert ok.status_code == 200, ok.text
        # A tenant cannot read another tenant's benchmark.
        bad = client.get("/api/v1/regulator/share/benchmark/air2")
        assert bad.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_share_benchmark_caan_cross_tenant(monkeypatch):
    async def _bench(self, tenant_id, tids):
        return {"operator_score": 3.0, "industry_average": 3.5}

    monkeypatch.setattr(AggregationService, "get_benchmarking", _bench)
    app.dependency_overrides[get_current_user] = lambda: _caan()
    try:
        r = client.get("/api/v1/regulator/share/benchmark/air2")
        assert r.status_code == 200
        assert "use_limitation" in r.json()
    finally:
        app.dependency_overrides.clear()


def test_escalate_and_read(monkeypatch):
    monkeypatch.setattr("app.services.caan_audit.log_caan_share", lambda *a, **k: None)
    monkeypatch.setattr("app.services.caan_audit.log_caan_escalated_read", lambda *a, **k: None)
    app.dependency_overrides[get_current_user] = lambda: _caan()
    try:
        c = client.post("/api/v1/regulator/share/escalate",
                        json={"tenant_id": "air1", "item_type": "hazard",
                              "item_id": "HZ-1", "reason": "audit review",
                              "window_hours": 24})
        assert c.status_code == 201, c.text
        esc_id = c.json()["data"]["id"]
        assert c.json()["data"]["scope"] == "full_detail_minus_reporter_identity"

        g = client.get(f"/api/v1/regulator/share/escalate/{esc_id}")
        assert g.status_code == 200
        assert g.json()["data"]["tenant_id"] == "air1"

        missing = client.get("/api/v1/regulator/share/escalate/does-not-exist")
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()
