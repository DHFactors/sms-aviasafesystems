"""State Regulator model tests.

Covers the `regulators` collection service (enumerate regulators + their
operators), the /api/v1/regulators routes (authz + envelope), and regulator
scoping of the state-risk aggregation and CAAN survey-maturity endpoints so the
system generalizes to any country's regulator (CAAN/Nepal, DGCA/India, ...).
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_caan_user
from app.services.regulator_service import (
    get_regulator,
    list_regulators,
    list_regulator_operators,
    operator_tenant_ids_for_regulator,
)


# ============================================================================
# Fake Firestore (regulators + tenants)
# ============================================================================

class _FakeSnap:
    def __init__(self, data, exists=True):
        self._data = data or {}
        self.exists = exists
        self.id = self._data.get("id", "doc")

    def to_dict(self):
        return self._data


class _FakeDocRef:
    def __init__(self, store, doc_id):
        self._store = store
        self.id = doc_id

    def get(self):
        data = self._store.get(self.id)
        if data is None:
            return _FakeSnap({}, exists=False)
        return _FakeSnap(dict(data))


class _FakeRegColl:
    def __init__(self, store):
        self._store = store

    def get(self):
        return [_FakeSnap(dict({**d, "id": doc_id})) for doc_id, d in self._store.items()]

    def document(self, doc_id):
        return _FakeDocRef(self._store, doc_id)


class _FakeTenantColl:
    def __init__(self, store):
        self._store = store

    def get(self):
        return [_FakeSnap(dict({**d, "id": doc_id})) for doc_id, d in self._store.items()]

    def document(self, doc_id):
        return _FakeDocRef(self._store, doc_id)

    def where(self, field, op, value):
        return _FakeTenantQuery(self, field, op, value)


class _FakeTenantQuery:
    def __init__(self, coll, field, op, value):
        self._coll = coll
        self._field = field
        self._op = op
        self._value = value

    def get(self):
        return [
            _FakeSnap(dict({**d, "id": doc_id}))
            for doc_id, d in self._coll._store.items()
            if d.get(self._field) == self._value
        ]


def _regulator_db(regulators=None, tenants=None):
    regulators = regulators or {}
    tenants = tenants or {}

    class _DB:
        def collection(self, name):
            if name == "regulators":
                return _FakeRegColl(regulators)
            if name == "tenants":
                return _FakeTenantColl(tenants)
            raise AssertionError(f"unexpected collection {name}")

    return _DB()


def _patch_reg_db(monkeypatch, db):
    monkeypatch.setattr("app.services.regulator_service.get_db", lambda: db)


def _sample_regulators(tenants=None):
    tenants = tenants or {
        "air1": {"name": "Air One", "country": "NP", "regulator_id": "caan", "active": True},
        "air2": {"name": "Air Two", "country": "NP", "regulator_id": "caan", "active": True},
    }
    regulators = {
        "caan": {
            "id": "caan", "type": "state_regulator",
            "name": "Civil Aviation Authority of Nepal", "short_name": "CAAN",
            "country": "NP", "country_name": "Nepal", "active": True,
            "operator_tenant_ids": ["air1", "air2"],
        }
    }
    return regulators, tenants


# ============================================================================
# Service-level
# ============================================================================

def test_list_regulators(monkeypatch):
    regulators, tenants = _sample_regulators()
    _patch_reg_db(monkeypatch, _regulator_db(regulators, tenants))
    result = list_regulators()
    assert len(result) == 1
    assert result[0]["id"] == "caan"
    assert result[0]["country"] == "NP"


def test_get_regulator_with_operators(monkeypatch):
    regulators, tenants = _sample_regulators()
    _patch_reg_db(monkeypatch, _regulator_db(regulators, tenants))
    reg = get_regulator("caan")
    assert reg is not None
    assert reg["short_name"] == "CAAN"
    assert [o["tenant_id"] for o in reg["operators"]] == ["air1", "air2"]
    assert reg["operators"][0]["country"] == "NP"


def test_get_regulator_unknown(monkeypatch):
    regulators, tenants = _sample_regulators()
    _patch_reg_db(monkeypatch, _regulator_db(regulators, tenants))
    assert get_regulator("dgca") is None


def test_get_regulator_derives_operators_from_tenant_tags(monkeypatch):
    """When operator_tenant_ids is absent, operators come from tenant docs
    tagged with regulator_id (so a DGCA-style regulator for another country
    works by tagging its own operators)."""
    regulators = {
        "dgca": {"id": "dgca", "type": "state_regulator",
                 "name": "Directorate General of Civil Aviation", "short_name": "DGCA",
                 "country": "IN", "country_name": "India", "active": True},
    }
    tenants = {
        "ind-air1": {"name": "IndiAir", "country": "IN", "regulator_id": "dgca", "active": True},
        "np-air": {"name": "Nepal Air", "country": "NP", "regulator_id": "caan", "active": True},
    }
    _patch_reg_db(monkeypatch, _regulator_db(regulators, tenants))
    reg = get_regulator("dgca")
    assert [o["tenant_id"] for o in reg["operators"]] == ["ind-air1"]


def test_operator_tenant_ids_for_regulator(monkeypatch):
    regulators, tenants = _sample_regulators()
    _patch_reg_db(monkeypatch, _regulator_db(regulators, tenants))
    assert sorted(operator_tenant_ids_for_regulator("caan")) == ["air1", "air2"]
    assert operator_tenant_ids_for_regulator("unknown") == []


def test_list_regulator_operators_explicit_ids(monkeypatch):
    _patch_reg_db(monkeypatch, _regulator_db(*_sample_regulators()))
    reg = {"operator_tenant_ids": ["air1", "air2"]}
    ops = list_regulator_operators("caan", reg)
    assert [o["tenant_id"] for o in ops] == ["air1", "air2"]


# ============================================================================
# Route-level (auth + envelope)
# ============================================================================

def _caan_user():
    return {"role": "CAAN_SMD", "tenant_id": None, "uid": "caan", "email": "caan@test.np"}


def test_regulators_route_requires_caan_role():
    # No dependency override -> real get_current_user -> 401
    resp = TestClient(app).get("/api/v1/regulators")
    assert resp.status_code in (401, 403)


def test_regulators_list_route(monkeypatch):
    _patch_reg_db(monkeypatch, _regulator_db(*_sample_regulators()))
    app.dependency_overrides[get_caan_user] = _caan_user
    try:
        resp = TestClient(app).get("/api/v1/regulators")
    finally:
        app.dependency_overrides.pop(get_caan_user, None)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "success"
    assert payload["data"]["regulators"][0]["id"] == "caan"


def test_regulators_detail_route(monkeypatch):
    _patch_reg_db(monkeypatch, _regulator_db(*_sample_regulators()))
    app.dependency_overrides[get_caan_user] = _caan_user
    try:
        resp = TestClient(app).get("/api/v1/regulators/caan")
    finally:
        app.dependency_overrides.pop(get_caan_user, None)
    assert resp.status_code == 200
    reg = resp.json()["data"]["regulator"]
    assert reg["country_name"] == "Nepal"
    assert len(reg["operators"]) == 2


def test_regulators_detail_unknown(monkeypatch):
    _patch_reg_db(monkeypatch, _regulator_db(*_sample_regulators()))
    app.dependency_overrides[get_caan_user] = _caan_user
    try:
        resp = TestClient(app).get("/api/v1/regulators/dgca")
    finally:
        app.dependency_overrides.pop(get_caan_user, None)
    assert resp.status_code == 404


# ============================================================================
# Regulator scoping of state risk aggregation
# ============================================================================

class _FakeDoc:
    def __init__(self, data):
        self._data = data
        self.id = "fake-id"

    def to_dict(self):
        return self._data


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs

    def get(self):
        return [_FakeDoc(d) for d in self._docs]


def _patch_aggregation_dbs(monkeypatch, hazards, reports):
    from app.services.state_risk_service import StateRiskService

    def fake_cg(self, name):
        if name == "hazards":
            return _FakeCollection(hazards)
        return _FakeCollection(reports)

    monkeypatch.setattr(
        "app.services.state_risk_service.get_db",
        lambda: type("DB", (), {"collection_group": fake_cg})(),
    )
    _patch_reg_db(monkeypatch, _regulator_db(*_sample_regulators()))
    return StateRiskService({"uid": "caan", "role": "CAAN_SMD"})


def test_aggregate_scoped_to_regulator_operators(monkeypatch):
    svc = _patch_aggregation_dbs(
        monkeypatch,
        hazards=[
            {"tenant_id": "air1", "occurrence_category": "BIRD", "severity_level": 3, "probability_level": 3, "risk_level": "High"},
            {"tenant_id": "air2", "occurrence_category": "BIRD", "severity_level": 2, "probability_level": 2, "risk_level": "Low"},
            {"tenant_id": "other-state", "occurrence_category": "BIRD", "severity_level": 5, "probability_level": 5, "risk_level": "Very High"},
        ],
        reports=[],
    )
    scoped = svc.aggregate_state_risk(2026, 3, regulator_id="caan")
    by_cat = {r["icoc_category"]: r for r in scoped["risks"]}
    # The "other-state" tenant is NOT overseen by CAAN -> excluded.
    assert by_cat["BIRD"]["count"] == 2
    assert by_cat["BIRD"]["contributing_tenants"] == ["air1", "air2"]

    full = svc.aggregate_state_risk(2026, 3)
    by_cat_full = {r["icoc_category"]: r for r in full["risks"]}
    assert by_cat_full["BIRD"]["count"] == 3


# ============================================================================
# Regulator scoping of CAAN survey maturity
# ============================================================================

def _patch_survey_maturity_dbs(monkeypatch, surveys):
    from app.services.dashboard_service import DashboardService

    class _DB:
        def collection_group(self, name):
            assert name == "surveys"
            return _FakeCollection(surveys)

    monkeypatch.setattr("app.firebase.get_db", lambda: _DB())
    _patch_reg_db(monkeypatch, _regulator_db(*_sample_regulators()))
    return DashboardService({"uid": "caan", "role": "CAAN_SMD"})


def test_survey_maturity_scoped_to_regulator(monkeypatch):
    svc = _patch_survey_maturity_dbs(monkeypatch, surveys=[
        {"tenant_id": "air1", "safety_policy": 4.0, "safety_risk_management": 4.0,
         "safety_assurance": 4.0, "safety_promotion": 4.0, "overall_sms_maturity": 4.0},
        {"tenant_id": "air2", "safety_policy": 2.0, "safety_risk_management": 2.0,
         "safety_assurance": 2.0, "safety_promotion": 2.0, "overall_sms_maturity": 2.0},
        {"tenant_id": "other-state", "safety_policy": 5.0, "safety_risk_management": 5.0,
         "safety_assurance": 5.0, "safety_promotion": 5.0, "overall_sms_maturity": 5.0},
    ])
    scoped = svc.get_caan_survey_maturity(regulator_id="caan")
    ids = {op["tenant_id"] for op in scoped["operators"]}
    assert ids == {"air1", "air2"}
    assert scoped["state"]["response_count"] == 2

    full = svc.get_caan_survey_maturity()
    assert len(full["operators"]) == 3
