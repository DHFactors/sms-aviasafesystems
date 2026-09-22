# ============================================================================
# P2-18 — state SPI computation (real trend; min 3 tenants).
# ============================================================================

from app.services.spi_service import SPIService


def test_state_trend_requires_min_three_tenants(monkeypatch):
    svc = SPIService()
    monkeypatch.setattr(svc, "_state_tenant_slugs", lambda: ["a", "b"])
    assert svc._state_trend_rows(months=2) is None
    trend = svc.compute_state_trend("SPI-LAG-002", months=2)
    assert trend["trend"] == "insufficient data"
    assert trend["previous_value"] is None


def test_compute_state_trend_prev_real(monkeypatch):
    svc = SPIService()
    monkeypatch.setattr(svc, "_state_tenant_slugs", lambda: ["a", "b", "c"])

    def fake_rows(months=2):
        return {
            "SPI-LAG-002": {"months": ["2026-01", "2026-02"], "values": [80.0, 92.0]},
            "SPI-LEAD-003": {"months": ["2026-01", "2026-02"], "values": [1.0, 0.4]},
        }

    monkeypatch.setattr(svc, "_state_trend_rows", fake_rows)
    # CAP closure (higher is better) increased -> improving trend.
    t = svc.compute_state_trend("SPI-LAG-002")
    assert t["previous_value"] == 80.0
    assert t["current_value"] == 92.0
    assert t["trend"] in ("increasing", "improving")

    # Diversion rate (lower is better) decreased -> improving.
    t2 = svc.compute_state_trend("SPI-LEAD-003")
    assert t2["trend"] in ("decreasing", "improving")


def test_get_state_status_has_real_trend_field(monkeypatch):
    svc = SPIService()
    monkeypatch.setattr(svc, "get_state_values", lambda *a, **k: {
        "hazard_id_rate": 5.0, "vsr_rate": 2.0, "diversion_rate": 0.4,
        "risk_reduction_rate": 80.0, "occurrence_rate": 3.0,
        "can_closure_rate": 90.0, "cap_closure_rate": 85.0, "safety_culture": 80.0,
    })
    monkeypatch.setattr(svc, "_state_trend_rows", lambda months=2: {
        "SPI-LAG-002": {"months": ["2026-01", "2026-02"], "values": [80.0, 90.0]},
    })
    rows = svc.get_state_status()
    assert rows
    for row in rows:
        assert "trend" in row
        assert row["trend"] != "stable" or row["spi_id"] != "SPI-LAG-002"
