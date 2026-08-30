"""
CAAN CAR-19 / SRM Mathematical Engine tests.

Unit coverage for backend/app/services/srm_engine.py plus the
POST /{hazard_id}/sram/calculate and PUT /{hazard_id}/sram/save endpoints,
benchmarked against the official SRM Procedure Manual test case:

  Wheel Jack Sunk Incident (Hazard 25-1296):
    Worker=4, Quality=3, Asset=4, Rep=1 -> Weighted Score 23 -> Severity D
    Initial probability 4 (Existing BSV ~4) -> Resultant probability 1
    (Consolidated BSV ~14) -> "4D" -> "1D" Acceptable
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.db_models import Hazard
from app.db.ids import register_tenant
from app.db.session import session_scope
from app.main import app
from app.core.config import settings
from app.services import srm_engine


# ============================================================================
# Pure engine unit tests
# ============================================================================

class TestSeverity:
    def test_wheel_jack_benchmark(self):
        result = srm_engine.calculate_severity(pax=0, worker=4, quality=3, asset=4, rep=1, sec=0, env=0)
        assert result["total_score"] == 23
        assert result["severity_letter"] == "D"
        assert result["descriptor"] == "Minor"

    def test_max_score_is_catastrophic(self):
        result = srm_engine.calculate_severity(pax=5, worker=5, quality=5, asset=5, rep=5, sec=5, env=5)
        assert result["total_score"] == 65
        assert result["severity_letter"] == "A"
        assert result["descriptor"] == "Catastrophic"

    def test_zero_score_is_insignificant(self):
        result = srm_engine.calculate_severity(0, 0, 0, 0, 0, 0, 0)
        assert result["total_score"] == 0
        assert result["severity_letter"] == "E"
        assert result["descriptor"] == "Insignificant"

    def test_band_boundaries(self):
        cases = [(52, "A"), (51, "B"), (39, "B"), (38, "C"), (26, "C"),
                 (25, "D"), (13, "D"), (12, "E")]
        for score, letter in cases:
            # Find an input combo producing exactly this score.
            pax = min(5, score // 4)
            rem = score - pax * 4
            worker = min(5, rem // 3)
            rem -= worker * 3
            quality = min(5, rem // 2)
            rem -= quality * 2
            asset = min(5, rem)
            rem -= asset
            result = srm_engine.calculate_severity(pax, worker, quality, asset, rem, 0, 0)
            assert result["total_score"] == score
            assert result["severity_letter"] == letter, (score, result)

    def test_weighting_factors(self):
        # One point of PAX (×4) outweighs one point of asset (×1).
        high = srm_engine.calculate_severity(pax=1, worker=0, quality=0, asset=0, rep=0, sec=0, env=0)
        low = srm_engine.calculate_severity(pax=0, worker=0, quality=0, asset=4, rep=0, sec=0, env=0)
        assert high["total_score"] == 4
        assert low["total_score"] == 4


class TestBqv:
    def test_excellent_band(self):
        result = srm_engine.calculate_bqv(5, 5, 5, 5, 5, 5, 5)
        assert result["bqv"] == 50
        assert result["bsv"] == 5
        assert result["robustness"] == "Excellent"

    def test_poor_band(self):
        result = srm_engine.calculate_bqv(1, 1, 1, 1, 1, 1, 1)
        assert result["bqv"] == 10
        assert result["bsv"] == 1
        assert result["robustness"] == "Poor"

    def test_ineffective_band(self):
        result = srm_engine.calculate_bqv(0, 0, 0, 0, 0, 0, 0)
        assert result["bqv"] == 0
        assert result["bsv"] == 0
        assert result["robustness"] == "Ineffective"

    def test_bqv_band_boundaries(self):
        for bqv, bsv in [(50, 5), (42, 5), (41, 4), (34, 4), (33, 3), (26, 3),
                         (25, 2), (18, 2), (17, 1), (10, 1), (9, 0)]:
            bsv_out, robustness = srm_engine._lookup_band(bqv, srm_engine.BQV_BANDS)
            assert bsv_out == bsv, (bqv, bsv_out)
            assert isinstance(robustness, str) and robustness

    def test_bqv_quality_inputs_map_to_bands(self):
        # (effectiveness, cost, disinclination) weights: 3x + 5y + 2z.
        assert srm_engine.calculate_bqv(5, 5, 5, 5, 5, 5, 5)["bsv"] == 5   # 50
        assert srm_engine.calculate_bqv(4, 4, 4, 4, 4, 4, 4)["bsv"] == 4   # 40
        assert srm_engine.calculate_bqv(3, 3, 3, 3, 3, 3, 3)["bsv"] == 3   # 30
        assert srm_engine.calculate_bqv(2, 2, 2, 2, 2, 2, 2)["bsv"] == 2   # 20
        assert srm_engine.calculate_bqv(1, 1, 1, 1, 1, 1, 1)["bsv"] == 1   # 10


class TestProbability:
    def test_severity_a_bands(self):
        cfg = srm_engine.PROBABILITY_CONFIG["A"]
        bands = [(0, 5), (8, 4), (16, 3), (24, 2), (32, 1)]
        for value, pv in bands:
            result = srm_engine.calculate_probability("A", value)
            assert result["probability_value"] == pv, (value, result)

    def test_severity_d_bands(self):
        bands = [(0, 5), (3, 4), (6, 3), (9, 2), (12, 1)]
        for value, pv in bands:
            result = srm_engine.calculate_probability("D", value)
            assert result["probability_value"] == pv

    def test_severity_e_bands(self):
        bands = [(0, 5), (2, 4), (4, 3), (6, 2), (8, 1)]
        for value, pv in bands:
            result = srm_engine.calculate_probability("E", value)
            assert result["probability_value"] == pv

    def test_clamp_above_max_to_probability_1(self):
        result = srm_engine.calculate_probability("D", 999)
        assert result["probability_value"] == 1
        assert result["descriptor"] == "Extremely Improbable"

    def test_clamp_below_zero_to_probability_5(self):
        result = srm_engine.calculate_probability("D", -5)
        assert result["probability_value"] == 5
        assert result["descriptor"] == "Certain"

    def test_unknown_severity_falls_back_to_e(self):
        result = srm_engine.calculate_probability("Z", 0)
        assert result["probability_value"] == 5


class TestRiskProfile:
    def test_wheel_jack_benchmark_4d_to_1d(self):
        severity = srm_engine.calculate_severity(0, 4, 3, 4, 1, 0, 0)
        ecb = [{"bsv": 2}, {"bsv": 2}]
        erb = []
        ncb = [{"bsv": 4}, {"bsv": 3}]
        nrb = [{"bsv": 3}]

        profile = srm_engine.evaluate_risk_profile(severity, ecb, erb, ncb, nrb)
        assert profile["existing_bsv"] == 4
        assert profile["consolidated_bsv"] == 14
        assert profile["initial_risk"]["index"] == "4D"
        assert profile["initial_risk"]["tolerability"] == "Tolerable"
        assert profile["resultant_risk"]["index"] == "1D"
        assert profile["resultant_risk"]["tolerability"] == "Acceptable"
        assert profile["resultant_risk"]["descriptor"] == "Extremely Improbable"
        assert profile["signoff"]["authority"] == "Safety Manager / SAG Member"

    def test_signoff_intolerable_is_accountable_manager(self):
        severity = {"severity_letter": "A"}
        profile = srm_engine.evaluate_risk_profile(severity, [], [], [], [])
        assert profile["initial_risk"]["index"] == "5A"
        assert profile["initial_risk"]["tolerability"] == "Intolerable"
        assert profile["signoff"]["authority"] == "Accountable Manager"

    def test_signoff_tolerable_is_risk_owner(self):
        severity = {"severity_letter": "D"}
        profile = srm_engine.evaluate_risk_profile(severity, [{"bsv": 4}], [], [], [])
        assert profile["initial_risk"]["index"] == "4D"
        assert profile["signoff"]["authority"] == "Risk Owner / Functional Chief"

    def test_risk_profile_carries_3_tier_tolerance(self):
        """The SRAM engine must map tolerability outcomes onto the CAAN CAR-19
        3-tier tolerance classification (Level II/III/IV)."""
        severity = {"severity_letter": "A"}
        profile = srm_engine.evaluate_risk_profile(severity, [], [], [], [])
        assert profile["initial_risk"]["tier"] == "VERY HIGH"
        assert profile["resultant_risk"]["tier"] == "VERY HIGH"
        assert profile["tier"] == "VERY HIGH"

        tolerable = srm_engine.evaluate_risk_profile({"severity_letter": "D"}, [{"bsv": 4}], [], [], [])
        assert tolerable["initial_risk"]["tier"] == "HIGH"
        assert tolerable["tier"] == "HIGH"

        acceptable = srm_engine.evaluate_risk_profile({"severity_letter": "D"}, [{"bsv": 6}, {"bsv": 6}], [], [], [])
        assert acceptable["resultant_risk"]["tier"] == "LOW"

    def test_analyse_pipeline(self):
        result = srm_engine.analyse(
            severity_inputs={"pax": 0, "worker": 4, "quality": 3, "asset": 4, "rep": 1, "sec": 0, "env": 0},
            ecb_barriers=[{"quality": {"effectiveness": 3, "cost_benefit": 3, "practicality": 3,
                                       "acceptability": 3, "enforceability": 3, "durability": 3,
                                       "disinclination": 3}, "name": "Wheel Chocks"}],
        )
        assert result["severity"]["severity_letter"] == "D"
        assert result["barriers"]["ecb"][0]["bsv"] == 3  # all-3 quality -> bqv 30 -> Good
        assert result["risk_profile"]["initial_risk"]["index"][1] == "D"


# ============================================================================
# API endpoint tests (in-memory Firestore mock)
# ============================================================================

class MockDocumentSnapshot:
    def __init__(self, data, doc_id=None, ref=None):
        self._data = dict(data) if data else {}
        self.id = doc_id or "mock_id"
        self.reference = ref
        self.exists = True

    def to_dict(self):
        return dict(self._data)


class MockDocumentReference:
    def __init__(self, doc_id=None, parent_fs=None):
        self._stored: Dict[str, Any] = {}
        self.id = doc_id or "mock_doc_id"
        self._parent_fs = parent_fs
        self._subcollections: Dict[str, Any] = {}

    def set(self, data):
        self._stored.update(data)

    def update(self, data):
        self._stored.update(data)

    def get(self):
        return MockDocumentSnapshot(self._stored, self.id, ref=self)

    def collection(self, subcollection):
        if subcollection not in self._subcollections:
            self._subcollections[subcollection] = MockCollectionReference()
        return self._subcollections[subcollection]

    def delete(self):
        pass


class MockCollectionReference:
    def __init__(self):
        self._docs: Dict[str, MockDocumentReference] = {}
        self._add_counter = 0

    def document(self, doc_id=None):
        if doc_id is None:
            doc_id = f"auto_{self._add_counter}"
            self._add_counter += 1
        if doc_id not in self._docs:
            self._docs[doc_id] = MockDocumentReference(doc_id)
        return self._docs[doc_id]

    def add(self, data):
        doc = self.document()
        doc.set(data)
        return MagicMock(update_time=None), doc

    def get(self):
        return [doc.get() for doc in self._docs.values()]

    def limit(self, n):
        return self

    def where(self, field, op, value):
        return self

    def order_by(self, field, **kwargs):
        return self

    def stream(self):
        return [doc.get() for doc in self._docs.values()]


class MockFirestoreClient:
    def __init__(self):
        self._top: Dict[str, MockCollectionReference] = {}

    def collection(self, path):
        return self._top.setdefault(path, MockCollectionReference())

    def collection_group(self, name):
        return self.collection(name)


@pytest.fixture(autouse=True)
def mock_firebase_and_auth(monkeypatch):
    fs_client = MockFirestoreClient()
    monkeypatch.setattr("app.firebase.get_db", lambda: fs_client)
    monkeypatch.setattr(
        "app.firebase.get_tenant_collection",
        lambda tid, coll: fs_client.collection("tenants").document(tid).collection(coll),
    )
    monkeypatch.setattr(
        "app.firebase.get_cross_tenant_collection",
        lambda coll: fs_client.collection_group(coll),
    )
    monkeypatch.setattr("app.firebase.initialize_firebase", lambda: None)
    monkeypatch.setattr("app.firebase.is_firebase_ready", lambda: True)
    monkeypatch.setattr(
        "app.firebase.get_tenant_metadata",
        lambda tid: {"risk_matrix": {"thresholds": {"low_max": 5, "medium_max": 9, "high_max": 15}}},
    )
    monkeypatch.setattr("app.firebase._db", fs_client)

    import app.firebase as fb_mod
    import app.middleware.auth as auth_mod

    def fake_verify(token):
        claims = {"role": "USER", "tenant_id": None}
        if token == "AIRLINE_ADMIN_TOKEN":
            claims = {"role": "AIRLINE_ADMIN", "tenant_id": "test_airline"}
        elif token == "SAFETY_MANAGER_TOKEN":
            claims = {"role": "SAFETY_MANAGER", "tenant_id": "test_airline"}
        return {"uid": "mock_user", "email": "test@aviasafe.com", **claims}

    monkeypatch.setattr(fb_mod, "verify_firebase_token", fake_verify)
    monkeypatch.setattr(auth_mod, "verify_firebase_token", fake_verify)
    yield fs_client


@pytest.fixture
def client(mock_firebase_and_auth):
    return TestClient(app)


def _hazard_row(hazard_id: str):
    async def _get():
        async with session_scope() as s:
            return (
                await s.scalars(select(Hazard).where(Hazard.id == UUID(hazard_id)))
            ).one_or_none()
    return asyncio.run(_get())


@pytest.fixture(autouse=True)
def _cleanup_srm_hazards():
    yield
    tid = register_tenant("test_airline")

    async def _wipe():
        async with session_scope() as s:
            await s.execute(delete(Hazard).where(Hazard.tenant_id == tid))

    asyncio.run(_wipe())


def _auth_header(token="AIRLINE_ADMIN_TOKEN"):
    return {"Authorization": f"Bearer {token}"}


def _create_hazard(client, fs):
    body = {
        "title": "Wheel Jack Sunk Incident",
        "description": "Aircraft wheel jack sunk into apron surface during jacking operations.",
        "source": "Internal Audit",
        "source_id": "AUD-25-1296",
        "taxonomy": "Organizational-Facilities",
        "priority": "H",
        "tenant_id": "test_airline",
    }
    resp = client.post("/api/v1/hazards/", json=body, headers=_auth_header())
    assert resp.status_code == 201, resp.text
    hazard = resp.json()
    return hazard["id"], hazard


_WHEEL_JACK_BARRIERS = {
    "ecb": [
        {"name": "Wheel Chock Placement Check", "bsv": 2},
        {"name": "Jack Pad Inspection", "bsv": 2},
    ],
    "erb": [],
    "ncb": [
        {"name": "Load-Rated Jacking Plates", "bsv": 4},
        {"name": "Hardstand Surface Audit", "bsv": 3},
    ],
    "nrb": [{"name": "Jacking Operations SOP", "bsv": 3}],
}


class TestSramCalculateEndpoint:
    def test_calculate_returns_dynamic_metrics_without_persisting(self, client, mock_firebase_and_auth):
        hazard_id, _ = _create_hazard(client, mock_firebase_and_auth)
        payload = {
            "severity": {"pax": 0, "worker": 4, "quality": 3, "asset": 4, "rep": 1, "sec": 0, "env": 0},
            "barriers": _WHEEL_JACK_BARRIERS,
        }
        resp = client.post(
            f"/api/v1/hazards/{hazard_id}/sram/calculate",
            json=payload,
            headers=_auth_header(),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["severity"]["total_score"] == 23
        assert data["severity"]["severity_letter"] == "D"
        assert data["risk_profile"]["initial_risk"]["index"] == "4D"
        assert data["risk_profile"]["resultant_risk"]["index"] == "1D"
        assert data["risk_profile"]["resultant_risk"]["tolerability"] == "Acceptable"
        # NOT persisted.
        row = _hazard_row(hazard_id)
        assert row is not None
        assert row.sram_data is None

    def test_calculate_404_for_missing_hazard(self, client):
        payload = {"severity": {"pax": 0, "worker": 0, "quality": 0, "asset": 0, "rep": 0, "sec": 0, "env": 0}}
        resp = client.post("/api/v1/hazards/nope/sram/calculate", json=payload, headers=_auth_header())
        assert resp.status_code == 404

    def test_calculate_validates_input_ranges(self, client, mock_firebase_and_auth):
        hazard_id, _ = _create_hazard(client, mock_firebase_and_auth)
        payload = {"severity": {"pax": 9, "worker": 0, "quality": 0, "asset": 0, "rep": 0, "sec": 0, "env": 0}}
        resp = client.post(
            f"/api/v1/hazards/{hazard_id}/sram/calculate", json=payload, headers=_auth_header()
        )
        assert resp.status_code == 422


class TestSramSaveEndpoint:
    def test_save_persists_full_configuration_and_updates_master_risk(self, client, mock_firebase_and_auth):
        hazard_id, _ = _create_hazard(client, mock_firebase_and_auth)
        payload = {
            "analysis_mode": "BOWTIE_SRAM",
            "sram_data": {
                "severity": {
                    "pax": 0, "worker": 4, "quality": 3, "asset": 4, "rep": 1, "sec": 0, "env": 0,
                    "severity_letter": "D",
                },
                "barriers": _WHEEL_JACK_BARRIERS,
                "signoffs": {"name": "Capt. Test User", "role": "Safety Manager"},
            },
        }
        resp = client.put(
            f"/api/v1/hazards/{hazard_id}/sram/save",
            json=payload,
            headers=_auth_header(),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["analysis_mode"] == "BOWTIE_SRAM"
        assert data["sram_data"]["risk_profile"]["resultant_risk"]["index"] == "1D"
        assert data["sram_data"]["signoffs"]["authority"] == "Safety Manager / SAG Member"
        # Master risk register updated (D->2, probability 1).
        assert data["severity"] == 2
        assert data["probability"] == 1
        assert data["risk_index"] == 2
        assert data["risk_level"] == "Low"
        assert data["risk_outcome"] == "Acceptable"

        row = _hazard_row(hazard_id)
        assert row is not None
        assert row.analysis_mode == "BOWTIE_SRAM"
        assert row.sram_data["barriers"]["ncb"][0]["bsv"] == 4
        assert row.srm_status == "Conducted"

    def test_save_rejects_inconsistent_severity(self, client, mock_firebase_and_auth):
        hazard_id, _ = _create_hazard(client, mock_firebase_and_auth)
        payload = {
            "analysis_mode": "BOWTIE_SRAM",
            "sram_data": {
                "severity": {
                    "pax": 0, "worker": 4, "quality": 3, "asset": 4, "rep": 1, "sec": 0, "env": 0,
                    "severity_letter": "A",  # tampered: recomputes to D
                },
                "barriers": _WHEEL_JACK_BARRIERS,
            },
        }
        resp = client.put(
            f"/api/v1/hazards/{hazard_id}/sram/save", json=payload, headers=_auth_header()
        )
        assert resp.status_code == 422
        assert "inconsistent" in resp.json()["detail"].lower()

    def test_save_rejects_invalid_analysis_mode(self, client, mock_firebase_and_auth):
        hazard_id, _ = _create_hazard(client, mock_firebase_and_auth)
        payload = {
            "analysis_mode": "TURBO_SRAM",
            "sram_data": {
                "severity": {"pax": 0, "worker": 0, "quality": 0, "asset": 0, "rep": 0, "sec": 0, "env": 0,
                             "severity_letter": "E"},
                "barriers": {},
            },
        }
        resp = client.put(
            f"/api/v1/hazards/{hazard_id}/sram/save", json=payload, headers=_auth_header()
        )
        assert resp.status_code == 422

    def test_save_404_for_missing_hazard(self, client):
        payload = {
            "analysis_mode": "BOWTIE_SRAM",
            "sram_data": {
                "severity": {"pax": 0, "worker": 0, "quality": 0, "asset": 0, "rep": 0, "sec": 0, "env": 0,
                             "severity_letter": "E"},
                "barriers": {},
            },
        }
        resp = client.put("/api/v1/hazards/nope/sram/save", json=payload, headers=_auth_header())
        assert resp.status_code == 404