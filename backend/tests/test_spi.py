# Tests for the SPI/SPT framework (backend/app/services/spi_service.py and the
# /api/v1/spi routes). Pure-logic cases need no DB; the integration cases read
# the seeded demo tenants exactly like the other Postgres-backed service tests.

import pytest
from fastapi.testclient import TestClient

from app.models.spi import SPIDomain, SPIType, SPIStatus
from app.services.spi_service import SPIService


def test_definitions_include_leading_and_lagging():
    svc = SPIService()
    defs = svc.get_spi_definitions()
    assert len(defs) == 8
    types = {d.type for d in defs}
    assert SPIType.LEADING in types and SPIType.LAGGING in types
    domains = {d.domain for d in defs}
    assert SPIDomain.HAZARD_ID in domains
    assert SPIDomain.SAFETY_CULTURE in domains


def test_get_status_default_higher_is_better():
    svc = SPIService()
    assert svc.get_status(10, 10, 7, 5) == SPIStatus.NOMINAL
    assert svc.get_status(8, 10, 7, 5) == SPIStatus.WATCH
    assert svc.get_status(4, 10, 7, 5) == SPIStatus.ALERT


def test_get_status_lower_is_better():
    svc = SPIService()
    assert svc.get_status(0.4, 0.5, 0.7, 1.0, lower_is_better=True) == SPIStatus.NOMINAL
    assert svc.get_status(0.6, 0.5, 0.7, 1.0, lower_is_better=True) == SPIStatus.WATCH
    assert svc.get_status(1.2, 0.5, 0.7, 1.0, lower_is_better=True) == SPIStatus.ALERT


def test_get_trend_direction():
    svc = SPIService()
    assert svc.get_trend(5, 3) == "improving"
    assert svc.get_trend(3, 5) == "deteriorating"
    assert svc.get_trend(4, 4) == "stable"


def test_closure_rate_empty_is_nominal():
    assert SPIService._closure_rate([]) == 100.0
    assert SPIService._closure_rate([{"status": "open"}]) == 0.0
    assert SPIService._closure_rate([{"status": "closed"}]) == 100.0


def test_calculate_all_spis_shape():
    svc = SPIService()
    values = svc.calculate_all_spis("fixedwing")
    assert set(values.keys()) == {
        "hazard_id_rate",
        "vsr_rate",
        "diversion_rate",
        "risk_reduction_rate",
        "occurrence_rate",
        "can_closure_rate",
        "cap_closure_rate",
        "safety_culture",
    }
    for v in values.values():
        assert isinstance(v, (int, float))


def test_tenant_status_rows():
    svc = SPIService()
    rows = svc.get_tenant_status("rotarywing")
    assert len(rows) == 8
    for row in rows:
        assert row["key"] and row["spi_id"] and row["name"]
        assert row["status"] in {"nominal", "watch", "alert"}
        assert row["trend"] in {"improving", "stable", "deteriorating"}


def test_tenant_trend_rows():
    svc = SPIService()
    rows = svc.get_tenant_trend("fixedwing", months=6)
    assert len(rows) == 8
    for row in rows:
        assert len(row["months"]) == 6
        assert len(row["values"]) == 6


def test_state_values():
    svc = SPIService()
    values = svc.get_state_values()
    assert len(values) == 8


def test_api_definitions(client: TestClient):
    r = client.get("/api/v1/spi/definitions")
    assert r.status_code == 200
    assert len(r.json()) == 8


def test_api_tenant_values(client: TestClient):
    r = client.get("/api/v1/spi/tenant/fixedwing/values")
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == "fixedwing"
    assert len(body["values"]) == 8


def test_api_tenant_status(client: TestClient):
    r = client.get("/api/v1/spi/tenant/fixedwing/status")
    assert r.status_code == 200
    assert len(r.json()["status"]) == 8


def test_api_trend(client: TestClient):
    r = client.get("/api/v1/spi/tenant/fixedwing/trend?months=6")
    assert r.status_code == 200
    assert len(r.json()) == 8


def test_api_state_values(client: TestClient):
    r = client.get("/api/v1/spi/state/values")
    assert r.status_code == 200
    assert len(r.json()["values"]) == 8


def test_state_diversion_rate_reflects_firestore():
    svc = SPIService()
    assert svc.get_state_values()["diversion_rate"] == 7.0


def test_tenant_diversion_rates_from_firestore():
    svc = SPIService()
    assert svc.calculate_diversion_rate("fixedwing") == 3.0
    assert svc.calculate_diversion_rate("rotarywing") == 2.0
    assert svc.calculate_diversion_rate("demoairport") == 2.0
    assert svc.calculate_diversion_rate("demostate") == 0.0


def test_diversion_rate_zero_flights_guard():
    svc = SPIService()
    assert svc.calculate_diversion_rate("fixedwing", flights=0) == 0.0


def test_api_update_targets(client: TestClient):
    r = client.post(
        "/api/v1/spi/tenant/fixedwing/targets",
        json={"hazard_id_rate": 12.0, "can_closure_rate": 95.0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "updated"
    assert body["count"] == 2
