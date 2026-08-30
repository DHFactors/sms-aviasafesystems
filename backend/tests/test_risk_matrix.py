"""RC-2 risk-matrix consistency tests.

Verifies that all risk classification schemes (risk level, risk outcome and the
CAAN CAR-19 3-tier tolerability classification) use the canonical, configurable
thresholds (default low_max=5 / high_max=15) and that stored tenant thresholds
are honoured by scoring. Legacy Medium/Moderate labels fold into the High tier.
"""

from datetime import datetime, timezone

import pytest

from app.services import risk_matrix as rm
from app.services.hazard_service import HazardService
from app.services.report_service import ReportService


DEFAULT = {"low_max": 5, "medium_max": 9, "high_max": 15}
CUSTOM = {"low_max": 3, "medium_max": 6, "high_max": 12}


# ============================================================================
# Pure risk-matrix functions
# ============================================================================

def test_compute_risk_index():
    assert rm.compute_risk_index(1, 1) == 1
    assert rm.compute_risk_index(3, 3) == 9
    assert rm.compute_risk_index(5, 5) == 25


def test_get_risk_level_default_boundaries():
    assert rm.get_risk_level(1) == "Low"
    assert rm.get_risk_level(5) == "Low"
    assert rm.get_risk_level(6) == "High"
    assert rm.get_risk_level(9) == "High"
    assert rm.get_risk_level(10) == "High"
    assert rm.get_risk_level(15) == "High"
    assert rm.get_risk_level(16) == "Very High"
    assert rm.get_risk_level(25) == "Very High"


def test_get_risk_level_respects_custom_thresholds():
    assert rm.get_risk_level(5, CUSTOM) == "High"
    assert rm.get_risk_level(3, CUSTOM) == "Low"
    assert rm.get_risk_level(6, CUSTOM) == "High"
    assert rm.get_risk_level(12, CUSTOM) == "High"
    assert rm.get_risk_level(13, CUSTOM) == "Very High"


def test_get_risk_level_empty_thresholds_falls_back_to_default():
    assert rm.get_risk_level(5, {}) == "Low"
    assert rm.get_risk_level(9, {}) == "High"
    assert rm.get_risk_level(15, {}) == "High"


def test_classify_risk_is_alias_of_get_risk_level():
    """classify_risk must produce identical results to get_risk_level."""
    for index in range(1, 26):
        assert rm.classify_risk(index) == rm.get_risk_level(index)
        assert rm.classify_risk(index, CUSTOM) == rm.get_risk_level(index, CUSTOM)


def test_classify_risk_canonical_index_9_is_high():
    """Under the 3-tier scheme index 9 (3x3) classifies as High (Level III)."""
    assert rm.classify_risk(9) == "High"
    assert rm.classify_risk(4) == "Low"


def test_risk_outcome_default_boundaries():
    assert rm.risk_outcome(1, 1) == "Acceptable"
    assert rm.risk_outcome(1, 5) == "Acceptable"
    assert rm.risk_outcome(3, 3) == "Tolerable"
    assert rm.risk_outcome(4, 3) == "Tolerable"
    assert rm.risk_outcome(5, 5) == "Intolerable"


def test_risk_outcome_respects_custom_thresholds():
    assert rm.risk_outcome(3, 3, CUSTOM) == "Tolerable"
    assert rm.risk_outcome(2, 3, CUSTOM) == "Tolerable"
    assert rm.risk_outcome(1, 3, CUSTOM) == "Acceptable"


# ============================================================================
# CAAN CAR-19 3-tier tolerability classification
# ============================================================================

def test_get_tolerability_tier_default_boundaries():
    assert rm.get_tolerability_tier(1) == "LOW"
    assert rm.get_tolerability_tier(5) == "LOW"
    assert rm.get_tolerability_tier(6) == "HIGH"
    assert rm.get_tolerability_tier(15) == "HIGH"
    assert rm.get_tolerability_tier(16) == "VERY HIGH"
    assert rm.get_tolerability_tier(25) == "VERY HIGH"


def test_get_tolerability_tier_respects_custom_thresholds():
    assert rm.get_tolerability_tier(3, CUSTOM) == "LOW"
    assert rm.get_tolerability_tier(4, CUSTOM) == "HIGH"
    assert rm.get_tolerability_tier(12, CUSTOM) == "HIGH"
    assert rm.get_tolerability_tier(13, CUSTOM) == "VERY HIGH"


def test_normalize_tolerability_maps_legacy_labels():
    assert rm.normalize_tolerability("Low") == "LOW"
    assert rm.normalize_tolerability("Acceptable") == "LOW"
    assert rm.normalize_tolerability("Medium") == "HIGH"
    assert rm.normalize_tolerability("Moderate") == "HIGH"
    assert rm.normalize_tolerability("High") == "HIGH"
    assert rm.normalize_tolerability("Tolerable") == "HIGH"
    assert rm.normalize_tolerability("Very High") == "VERY HIGH"
    assert rm.normalize_tolerability("Critical") == "VERY HIGH"
    assert rm.normalize_tolerability("Intolerable") == "VERY HIGH"
    assert rm.normalize_tolerability(None) == "HIGH"
    assert rm.normalize_tolerability("") == "HIGH"


def test_classify_tolerability_full_payload():
    cfg = rm.classify_tolerability(9)
    assert cfg["tier"] == "HIGH"
    assert cfg["risk_level"] == "High"
    assert cfg["outcome"] == "Tolerable"
    assert cfg["level"] == "Level III"
    assert cfg["risk_index"] == 9

    low = rm.classify_tolerability(2)
    assert low["tier"] == "LOW"
    assert low["level"] == "Level II"
    assert low["outcome"] == "Acceptable"

    vh = rm.classify_tolerability(25)
    assert vh["tier"] == "VERY HIGH"
    assert vh["level"] == "Level IV"
    assert vh["outcome"] == "Intolerable"


def test_risk_outcome_by_index_matches_outcome():
    assert rm.risk_outcome_by_index(4) == "Acceptable"
    assert rm.risk_outcome_by_index(9) == "Tolerable"
    assert rm.risk_outcome_by_index(16) == "Intolerable"
    assert rm.risk_outcome_by_index(9, CUSTOM) == "Tolerable"
    assert rm.risk_outcome_by_index(13, CUSTOM) == "Intolerable"


def test_get_thresholds_uses_stored_config(monkeypatch):
    monkeypatch.setattr(rm, "get_risk_matrix_config", lambda tid: {"thresholds": dict(CUSTOM)})
    assert rm.get_thresholds("airline1") == CUSTOM


def test_get_thresholds_falls_back_when_missing(monkeypatch):
    monkeypatch.setattr(rm, "get_risk_matrix_config", lambda tid: {})
    assert rm.get_thresholds("airline1") == DEFAULT


def test_get_thresholds_falls_back_on_error(monkeypatch):
    def boom(tid):
        raise RuntimeError("unavailable")
    monkeypatch.setattr(rm, "get_risk_matrix_config", boom)
    assert rm.get_thresholds("airline1") == DEFAULT


# ============================================================================
# Hazard + report service: classification uses canonical thresholds
# (service calls hit live PostgreSQL; rows are cleaned up after each test)
# ============================================================================

import asyncio

from sqlalchemy import delete

from app.db.db_models import Report, Hazard
from app.db.ids import register_tenant
from app.db.session import session_scope


async def _cleanup_airline1():
    tid = register_tenant("airline1")
    async with session_scope() as s:
        await s.execute(delete(Report).where(Report.tenant_id == tid))
        await s.execute(delete(Hazard).where(Hazard.tenant_id == tid))


@pytest.fixture(autouse=True)
def _cleanup_postgres_rows():
    yield
    asyncio.run(_cleanup_airline1())


def _hazard_payload(**overrides):
    payload = {
        "title": "Engine failure risk",
        "description": "Repeated engine failures observed during approach.",
        "source": "MOR",
        "taxonomy": "Technical",
        "priority": "M",
        "severity": 3,
        "probability": 3,
        "tenant_id": "airline1",
    }
    payload.update(overrides)
    return payload


def test_hazard_create_uses_canonical_scheme(monkeypatch):
    monkeypatch.setattr("app.services.hazard_service.get_thresholds",
                        lambda tid: dict(DEFAULT))

    doc = HazardService("airline1").create_hazard(_hazard_payload(), {"uid": "u1"})
    assert doc["risk_index"] == 9
    assert doc["risk_level"] == "High"
    assert doc["risk_outcome"] == "Tolerable"
    assert doc["tolerability_tier"] == "HIGH"


def test_hazard_create_honours_stored_thresholds(monkeypatch):
    monkeypatch.setattr("app.services.hazard_service.get_thresholds",
                        lambda tid: dict(CUSTOM))

    doc = HazardService("airline1").create_hazard(_hazard_payload(), {"uid": "u1"})
    assert doc["risk_index"] == 9
    assert doc["risk_level"] == "High"
    assert doc["risk_outcome"] == "Tolerable"


def test_hazard_create_classifies_from_risk_index_only(monkeypatch):
    monkeypatch.setattr("app.services.hazard_service.get_thresholds",
                        lambda tid: dict(DEFAULT))

    payload = _hazard_payload(severity=None, probability=None, risk_index=9, risk_level=None)
    doc = HazardService("airline1").create_hazard(payload, {"uid": "u1"})
    assert doc["risk_level"] == "High"


# ============================================================================
# Report service: stored thresholds honoured by scoring
# ============================================================================

def _report_payload():
    return {
        "report_type": "voluntary",
        "narrative": "Test narrative describing an operational incident.",
        "location": "KTM",
        "occurrence_date": datetime.now(timezone.utc),
        "severity_level": 3,
        "probability_level": 3,
        "is_anonymous": False,
    }


def test_report_create_uses_canonical_scheme(monkeypatch):
    monkeypatch.setattr("app.services.report_service.get_thresholds",
                        lambda tid: dict(DEFAULT))

    doc = ReportService("airline1").create_report(_report_payload(), {"uid": "u1"})
    assert doc["risk_index"] == 9
    assert doc["risk_level"] == "High"


def test_report_create_honours_stored_thresholds(monkeypatch):
    monkeypatch.setattr("app.services.report_service.get_thresholds",
                        lambda tid: dict(CUSTOM))

    doc = ReportService("airline1").create_report(_report_payload(), {"uid": "u1"})
    assert doc["risk_index"] == 9
    assert doc["risk_level"] == "High"
