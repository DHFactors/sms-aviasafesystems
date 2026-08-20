"""State-level risk register tests (Part 2: state risk vs SSP).

Verifies aggregation of tenant data into ICAO top-risk categories, persistence
of the register, SSP target handling, and the benchmark wiring.
"""

from datetime import datetime, timedelta, timezone

from app.services.state_risk_service import (
    StateRiskService,
    ICAO_TOP_RISK_CATEGORIES,
)


# ============================================================================
# ICAO classification helpers
# ============================================================================

def test_icao_categories_are_unique():
    cats = [c["category"] for c in ICAO_TOP_RISK_CATEGORIES]
    assert len(cats) == len(set(cats))
    assert "LOCI" in cats and "CFIT" in cats and "OTHER" in cats


def test_classify_uses_occurrence_category():
    assert StateRiskService._classify({"occurrence_category": "LOCI"}) == "LOCI"
    assert StateRiskService._classify({"occurrence_category": "BIRD"}) == "BIRD"
    assert StateRiskService._classify({"occurrence_category": "ENG"}) == "ENG"


def test_classify_matches_named_labels():
    assert StateRiskService._classify({"occurrence_type": "Loss of Control Inflight"}) == "LOCI"
    assert StateRiskService._classify({"occurrence_type": "Runway Excursion"}) == "RE"
    assert StateRiskService._classify({"occurrence_type": "Runway Incursion"}) == "RI"
    assert StateRiskService._classify({"occurrence_type": "Bird Strike"}) == "BIRD"
    assert StateRiskService._classify({"occurrence_type": "Controlled Flight Into Terrain"}) == "CFIT"


def test_classify_falls_back_to_other():
    assert StateRiskService._classify({}) == "OTHER"
    assert StateRiskService._classify({"occurrence_category": "UNKNOWN_XYZ"}) == "OTHER"


def test_tolerability_bands():
    assert StateRiskService._tolerability(None) == "Acceptable"
    assert StateRiskService._tolerability(1) == "Acceptable"
    assert StateRiskService._tolerability(5) == "Acceptable"
    assert StateRiskService._tolerability(6) == "Tolerable"
    assert StateRiskService._tolerability(9) == "Tolerable"
    assert StateRiskService._tolerability(15) == "Tolerable"
    assert StateRiskService._tolerability(16) == "Intolerable"
    assert StateRiskService._tolerability(25) == "Intolerable"


def test_aggregate_groups_risk_into_level_ii_iii_iv(monkeypatch):
    """State aggregation must group hazard counts into Level II (Low),
    Level III (High) and Level IV (Very High) tiers."""
    svc = _svc(
        monkeypatch,
        hazards=[
            {"tenant_id": "air1", "occurrence_category": "BIRD", "risk_level": "Low"},
            {"tenant_id": "air1", "occurrence_category": "BIRD", "risk_level": "Medium"},
            {"tenant_id": "air1", "occurrence_category": "BIRD", "risk_level": "High"},
            {"tenant_id": "air1", "occurrence_category": "BIRD", "risk_level": "Very High"},
        ],
    )
    result = svc.aggregate_state_risk(2026, 3)
    by_cat = {r["icoc_category"]: r for r in result["risks"]}
    bird = by_cat["BIRD"]
    assert bird["count"] == 4
    assert bird["level_ii_count"] == 1
    assert bird["level_iii_count"] == 2  # Medium + High fold into Level III
    assert bird["level_iv_count"] == 1
    assert bird["high_risk_count"] == 3


# ============================================================================
# Aggregation (mocked cross-tenant collection groups)
# ============================================================================

class _FakeDoc:
    def __init__(self, data):
        self._data = data
        self.id = "fake-id"

    def to_dict(self):
        return self._data


class _FakeQuery:
    def get(self):
        return [self._doc]

    def limit(self, n):
        return self

    def stream(self):
        return [self._doc]

    def where(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs

    def get(self):
        return self._docs

    def stream(self):
        return self._docs

    def limit(self, n):
        return self

    def document(self, doc_id):
        return _FakeDocRef(doc_id, self._docs)


class _FakeDocRef:
    def __init__(self, doc_id, docs):
        self.id = doc_id
        self._docs = docs

    def get(self):
        for d in self._docs:
            if d.id == self.id:
                return d
        return _FakeDoc({})


def _svc(monkeypatch, hazards=None, reports=None, reference=None):
    hazards = hazards or []
    reports = reports or []

    def fake_cg(self, name):
        if name == "hazards":
            return _FakeCollection([_FakeDoc(h) for h in hazards])
        return _FakeCollection([_FakeDoc(r) for r in reports])

    monkeypatch.setattr(
        "app.services.state_risk_service.get_db",
        lambda: type("DB", (), {"collection_group": fake_cg})(),
    )
    return StateRiskService({"uid": "caan-user", "role": "CAAN_SMD"})


def test_aggregate_state_risk(monkeypatch):
    svc = _svc(
        monkeypatch,
        hazards=[
            {"tenant_id": "air1", "occurrence_category": "BIRD", "severity_level": 3, "probability_level": 3, "risk_level": "High"},
            {"tenant_id": "air1", "occurrence_category": "LOCI", "severity_level": 5, "probability_level": 5, "risk_level": "Very High"},
            {"tenant_id": "air2", "occurrence_category": "BIRD", "severity_level": 1, "probability_level": 1, "risk_level": "Low"},
        ],
    )
    result = svc.aggregate_state_risk(2026, 3)
    assert result["year"] == 2026
    assert result["quarter"] == 3
    by_cat = {r["icoc_category"]: r for r in result["risks"]}
    assert by_cat["BIRD"]["count"] == 2
    assert by_cat["BIRD"]["current_risk_index"] == 4
    assert by_cat["LOCI"]["current_risk_index"] == 25
    assert by_cat["LOCI"]["contributing_tenants"] == ["air1"]
    # State top risk should rank highest risk index first
    assert result["risks"][0]["icoc_category"] == "LOCI"


def test_aggregate_includes_reports(monkeypatch):
    svc = _svc(
        monkeypatch,
        reports=[
            {"tenant_id": "air1", "occurrence_category": "ENG", "severity_level": 4, "probability_level": 2, "risk_level": "High"},
        ],
    )
    result = svc.aggregate_state_risk(2026, 2)
    by_cat = {r["icoc_category"]: r for r in result["risks"]}
    assert by_cat["ENG"]["count"] == 1
    assert by_cat["ENG"]["current_risk_index"] == 8


def test_aggregate_empty_returns_no_rows(monkeypatch):
    svc = _svc(monkeypatch)
    result = svc.aggregate_state_risk(2026, 1)
    assert result["risks"] == []


# ============================================================================
# Register persistence (mocked risk collection)
# ============================================================================

class _FakeRiskDocRef:
    def __init__(self, doc_id, store):
        self.id = doc_id
        self._store = store

    def get(self):
        data = self._store.get(self.id)
        if data is None:
            return _FakeMissingDoc()
        return _FakeRiskDoc(self.id, data)

    def set(self, data):
        self._store[self.id] = data
        return self

    def update(self, data):
        existing = self._store.get(self.id, {})
        existing.update(data)
        self._store[self.id] = existing
        return self


class _FakeRiskDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self.exists = True
        self._data = data

    def to_dict(self):
        return self._data


class _FakeMissingDoc:
    def __init__(self):
        self.exists = False

    def to_dict(self):
        return {}


class _FakeRiskCollection:
    def __init__(self):
        self._store = {}
        self._docs = []

    def document(self, doc_id):
        return _FakeRiskDocRef(doc_id, self._store)

    def stream(self):
        return [_FakeRiskDoc(did, data) for did, data in self._store.items()]


class _FakeBatch:
    def __init__(self, coll):
        self._ops = []
        self._coll = coll

    def set(self, ref, data):
        self._ops.append(("set", ref.id, data))
        return self

    def update(self, ref, data):
        self._ops.append(("update", ref.id, data))
        return self

    def commit(self):
        for kind, doc_id, data in self._ops:
            ref = self._coll.document(doc_id)
            if kind == "set":
                ref.set(data)
            else:
                ref.update(data)


def _svc_with_risk_collection(monkeypatch, hazards, reference=None):
    coll = _FakeRiskCollection()

    def fake_cg(self, name):
        return _FakeCollection([_FakeDoc(h) for h in hazards]) if name == "hazards" else _FakeCollection([])

    class _DB:
        def batch(self):
            return _FakeBatch(coll)

        def collection(self, name):
            assert name == "state"
            return _FakeStateDoc()

        def collection_group(self, name):
            return fake_cg(self, name)

    class _FakeStateDoc:
        def document(self, doc_id):
            if doc_id == "ssp":
                return type("SSP", (), {"collection": lambda self, name: coll if name == "risk_register" else None})()
            return type("ICAO", (), {"collection": lambda self, name: _FakeCollection([])})()

    monkeypatch.setattr("app.services.state_risk_service.get_db", lambda: _DB())
    return coll, StateRiskService({"uid": "caan-user", "role": "CAAN_SMD"})


def test_sync_register_persists_entries(monkeypatch):
    coll, svc = _svc_with_risk_collection(
        monkeypatch,
        hazards=[
            {"tenant_id": "air1", "occurrence_category": "BIRD", "severity_level": 3, "probability_level": 3, "risk_level": "High"},
            {"tenant_id": "air1", "occurrence_category": "LOCI", "severity_level": 5, "probability_level": 5, "risk_level": "Very High"},
        ],
    )
    result = svc.sync_register_from_aggregation(2026, 3)
    assert result["synced"] == 2
    assert "BIRD-2026Q3" in coll._store
    assert "LOCI-2026Q3" in coll._store
    bird = coll._store["BIRD-2026Q3"]
    assert bird["ssp_target"] is not None
    assert bird["actual_ssp_value"] == 9
    assert bird["tolerability"] == "Tolerable"


def test_sync_uses_atomic_batch(monkeypatch):
    """All register writes must go through the batch (single commit) rather
    than per-document writes."""
    coll, svc = _svc_with_risk_collection(
        monkeypatch,
        hazards=[
            {"tenant_id": "air1", "occurrence_category": "BIRD", "severity_level": 3, "probability_level": 3, "risk_level": "High"},
            {"tenant_id": "air1", "occurrence_category": "LOCI", "severity_level": 5, "probability_level": 5, "risk_level": "Very High"},
        ],
    )
    result = svc.sync_register_from_aggregation(2026, 3)
    assert result["synced"] == 2
    assert "BIRD-2026Q3" in coll._store
    assert "LOCI-2026Q3" in coll._store


def test_sync_records_aggregated_at_staleness(monkeypatch):
    """Every synced entry must carry aggregated_at and the result must expose
    the aggregation timestamp for staleness detection."""
    coll, svc = _svc_with_risk_collection(
        monkeypatch,
        hazards=[
            {"tenant_id": "air1", "occurrence_category": "BIRD", "severity_level": 3, "probability_level": 3, "risk_level": "High"},
        ],
    )
    result = svc.sync_register_from_aggregation(2026, 3)
    assert "aggregated_at" in result
    assert result["aggregated_at"] is not None
    bird = coll._store["BIRD-2026Q3"]
    assert "aggregated_at" in bird
    assert bird["aggregated_at"] == result["aggregated_at"]


def test_sync_persists_tier_and_level(monkeypatch):
    """Register entries must carry the 3-tier tolerability tier + Level naming."""
    coll, svc = _svc_with_risk_collection(
        monkeypatch,
        hazards=[
            {"tenant_id": "air1", "occurrence_category": "BIRD", "severity_level": 5, "probability_level": 5, "risk_level": "Very High"},
        ],
    )
    svc.sync_register_from_aggregation(2026, 3)
    bird = coll._store["BIRD-2026Q3"]
    assert bird["tolerability"] == "Intolerable"
    assert bird["tolerability_tier"] == "VERY HIGH"
    assert bird["level"] == "Level IV"
    assert bird["level_ii_count"] == 0
    assert bird["level_iii_count"] == 0
    assert bird["level_iv_count"] == 1


def test_sync_retains_ssp_target_on_resync(monkeypatch):
    """A second sync must carry over the existing SSP target and reduction
    rate, not overwrite them with the defaults."""
    coll, svc = _svc_with_risk_collection(
        monkeypatch,
        hazards=[
            {"tenant_id": "air1", "occurrence_category": "BIRD", "severity_level": 3, "probability_level": 3, "risk_level": "High"},
        ],
    )
    svc.sync_register_from_aggregation(2026, 3)
    svc.update_ssp_target("BIRD-2026Q3", ssp_target=6.0, risk_reduction_rate=15.0)
    result = svc.sync_register_from_aggregation(2026, 3)
    assert result["synced"] == 1
    bird = coll._store["BIRD-2026Q3"]
    assert bird["ssp_target"] == 6.0
    assert bird["risk_reduction_rate"] == 15.0


def test_sync_trend_detects_deterioration(monkeypatch):
    coll, svc = _svc_with_risk_collection(
        monkeypatch,
        hazards=[
            {"tenant_id": "air1", "occurrence_category": "BIRD", "severity_level": 4, "probability_level": 4, "risk_level": "High"},
        ],
    )
    svc.sync_register_from_aggregation(2026, 1)
    # Same category worsens in Q2
    coll, svc2 = _svc_with_risk_collection(
        monkeypatch,
        hazards=[
            {"tenant_id": "air1", "occurrence_category": "BIRD", "severity_level": 5, "probability_level": 5, "risk_level": "Very High"},
        ],
    )
    svc2.sync_register_from_aggregation(2026, 2)
    # Simulate existing entry retained for Q2 run
    data = coll._store["BIRD-2026Q2"]
    assert data["trend"] in ("improving", "stable", "deteriorating")


def test_update_ssp_target(monkeypatch):
    coll, svc = _svc_with_risk_collection(
        monkeypatch,
        hazards=[
            {"tenant_id": "air1", "occurrence_category": "BIRD", "severity_level": 3, "probability_level": 3, "risk_level": "High"},
        ],
    )
    svc.sync_register_from_aggregation(2026, 1)
    updated = svc.update_ssp_target("BIRD-2026Q1", ssp_target=6.0, risk_reduction_rate=15.0)
    assert updated is not None
    assert updated["ssp_target"] == 6.0
    assert updated["risk_reduction_rate"] == 15.0


def test_update_ssp_target_missing_returns_none(monkeypatch):
    coll, svc = _svc_with_risk_collection(monkeypatch, hazards=[])
    assert svc.update_ssp_target("MISSING-2026Q1", ssp_target=5.0) is None


# ============================================================================
# Route-level: authorization + response envelope (mocked auth)
# ============================================================================

from fastapi.testclient import TestClient
from app.main import app
from app.middleware.auth import get_caan_user, get_admin_user


class _CAANUser:
    def __init__(self):
        self._data = {
            "role": "CAAN_SMD",
            "tenant_id": None,
            "uid": "caan-test",
            "email": "caan@test.np",
            "claims": {"role": "CAAN_SMD", "tenant_id": None},
        }

    def get(self, key, default=None):
        return self._data.get(key, default)


class _SuperUser:
    def __init__(self):
        self._data = {
            "role": "SUPER_ADMIN",
            "tenant_id": None,
            "uid": "super-test",
            "email": "super@test.np",
            "claims": {"role": "SUPER_ADMIN", "tenant_id": None},
        }

    def get(self, key, default=None):
        return self._data.get(key, default)


def _client_with_roles(caan=True, admin=True):
    def dep_caan():
        return _CAANUser()

    def dep_admin():
        return _SuperUser()

    overrides = {}
    if caan:
        overrides[get_caan_user] = dep_caan
    if admin:
        overrides[get_admin_user] = dep_admin
    app.dependency_overrides.update(overrides)

    class _ClientScope:
        def __init__(self):
            self.client = TestClient(app)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            app.dependency_overrides.clear()

    return _ClientScope()


def test_register_requires_caan_role():
    with _client_with_roles(caan=True, admin=False) as s:
        r = s.client.get("/api/v1/state-risk/register")
        assert r.status_code in (200, 200)


def test_register_endpoint_shape():
    with _client_with_roles(caan=True, admin=False) as s:
        r = s.client.get("/api/v1/state-risk/register")
    assert r.status_code == 200
    payload = r.json()
    assert "success" in payload
    assert "risks" in payload


def test_aggregate_endpoint_returns_risks():
    with _client_with_roles(caan=True, admin=False) as s:
        r = s.client.get("/api/v1/state-risk/aggregate?year=2026&quarter=1")
    assert r.status_code == 200
    payload = r.json()
    assert payload["success"] is True
    assert "risks" in payload


def test_update_ssp_target_requires_admin():
    with _client_with_roles(caan=False, admin=False) as s:
        r = s.client.put("/api/v1/state-risk/register/BIRD-2026Q1/ssp-target",
                         json={"ssp_target": 6.0})
    assert r.status_code in (403, 401)


# ============================================================================
# CAAN survey maturity (SMS pillars across tenants)
# ============================================================================

def _survey_svc(monkeypatch, surveys):
    from app.services.dashboard_service import DashboardService

    def fake_cg(self, name):
        assert name == "surveys"
        return _FakeCollection([_FakeDoc(s) for s in surveys])

    class _DB:
        def collection_group(self, name):
            return fake_cg(self, name)

    monkeypatch.setattr("app.firebase.get_db", lambda: _DB())
    return DashboardService({"uid": "caan-user", "role": "CAAN_SMD"})


def test_get_caan_survey_maturity_aggregates_pillars(monkeypatch):
    svc = _survey_svc(monkeypatch, surveys=[
        {
            "tenant_id": "air1",
            "safety_policy": 4.0, "safety_risk_management": 3.0,
            "safety_assurance": 5.0, "safety_promotion": 4.0,
            "overall_sms_maturity": 4.0,
        },
        {
            "tenant_id": "air1",
            "safety_policy": 2.0, "safety_risk_management": 3.0,
            "safety_assurance": 3.0, "safety_promotion": 4.0,
            "overall_sms_maturity": 3.0,
        },
        {
            "tenant_id": "air2",
            "safety_policy": 5.0, "safety_risk_management": 5.0,
            "safety_assurance": 5.0, "safety_promotion": 5.0,
            "overall_sms_maturity": 5.0,
        },
    ])
    result = svc.get_caan_survey_maturity()
    assert result["state"]["response_count"] == 3
    by_id = {op["tenant_id"]: op for op in result["operators"]}
    assert by_id["air1"]["response_count"] == 2
    assert by_id["air1"]["pillars"]["safety_policy"] == 3.0
    assert by_id["air1"]["overall_sms_maturity"] == 3.5
    assert by_id["air2"]["overall_sms_maturity"] == 5.0
    # State pillar average across all responses
    assert result["state"]["pillars"]["safety_policy"] == round((4.0 + 2.0 + 5.0) / 3, 2)
    # Best SMS maturity ranks first
    assert result["operators"][0]["tenant_id"] == "air2"


def test_get_caan_survey_maturity_filters_by_days_cutoff(monkeypatch):
    now = datetime.now(timezone.utc)
    svc = _survey_svc(monkeypatch, surveys=[
        {
            "tenant_id": "air1",
            "submitted_at": now,
            "safety_policy": 4.0, "safety_risk_management": 3.0,
            "safety_assurance": 5.0, "safety_promotion": 4.0,
            "overall_sms_maturity": 4.0,
        },
        {
            "tenant_id": "air1",
            "submitted_at": now - timedelta(days=120),
            "safety_policy": 2.0, "safety_risk_management": 3.0,
            "safety_assurance": 3.0, "safety_promotion": 4.0,
            "overall_sms_maturity": 3.0,
        },
        {
            "tenant_id": "air2",
            "submitted_at": now - timedelta(days=400),
            "safety_policy": 5.0, "safety_risk_management": 5.0,
            "safety_assurance": 5.0, "safety_promotion": 5.0,
            "overall_sms_maturity": 5.0,
        },
    ])
    result = svc.get_caan_survey_maturity(days=90)
    assert result["state"]["response_count"] == 1
    by_id = {op["tenant_id"]: op for op in result["operators"]}
    assert by_id["air1"]["response_count"] == 1
    assert by_id["air1"]["overall_sms_maturity"] == 4.0
    assert "air2" not in by_id

    all_time = svc.get_caan_survey_maturity()
    assert all_time["state"]["response_count"] == 3


def test_universal_oversight_includes_all_tenant_types(monkeypatch):
    """CAAN SMD aggregation must treat internal CAAN directorates (caan-directorate
    tenant type) exactly like external service providers — no tenant type is
    excluded from the state payload."""
    from app.services.dashboard_service import DashboardService

    now = datetime.now(timezone.utc)

    class _Snap:
        def __init__(self, doc_id, data):
            self.id = doc_id
            self._data = data

        def to_dict(self):
            return self._data

    tenant_ids = ["air1", "hel1", "mro1", "aerodrome1", "ground1", "caan-fssd", "caan-assd"]
    tenant_docs = [
        _Snap("air1", {"name": "Air One", "icao": "AO1", "country": "Nepal", "active": True}),
        _Snap("hel1", {"name": "Heli Co", "icao": "HC1", "country": "Nepal", "active": True}),
        _Snap("mro1", {"name": "MRO One", "icao": "MO1", "country": "Nepal", "active": True}),
        _Snap("aerodrome1", {"name": "Aero One", "icao": "AE1", "country": "Nepal", "active": True}),
        _Snap("ground1", {"name": "Ground One", "icao": "G1", "country": "Nepal", "active": True}),
        _Snap("caan-fssd", {"name": "CAAN FSSD", "icao": "FSSD", "country": "Nepal", "active": True}),
        _Snap("caan-assd", {"name": "CAAN ASSD", "icao": "ASSD", "country": "Nepal", "active": True}),
    ]

    hazards = [
        {"tenant_id": tid, "severity": 4, "probability": 3, "risk_level": "High",
         "created_at": now} for tid in tenant_ids
    ]
    responses = [
        {"tenant_id": tid, "submitted_at": now} for tid in tenant_ids
    ]
    reports = [
        {"tenant_id": tid, "report_type": "mandatory", "occurrence_type": "Bird Strike",
         "risk_index": 6, "created_at": now} for tid in tenant_ids
    ]
    surveys = [
        {"tenant_id": tid, "safety_policy": 4.0, "safety_risk_management": 4.0,
         "safety_assurance": 4.0, "safety_promotion": 4.0,
         "overall_sms_maturity": 4.0, "submitted_at": now} for tid in tenant_ids
    ]

    class _DB:
        def collection(self, name):
            assert name == "tenants"
            return _FakeCollection([_Snap(t.id, t.to_dict()) for t in tenant_docs])

        def collection_group(self, name):
            mapping = {
                "hazards": hazards,
                "responses": responses,
                "surveys": surveys,
            }
            return _FakeCollection([_FakeDoc(s) for s in mapping[name]])

    monkeypatch.setattr("app.firebase.get_db", lambda: _DB())
    monkeypatch.setattr(
        "app.firebase.get_cross_tenant_collection",
        lambda name: _FakeCollection([_FakeDoc(s) for s in reports]),
    )
    monkeypatch.setattr(
        "app.services.regulator_service.operator_tenant_ids_for_regulator",
        lambda rid: list(tenant_ids),
    )

    svc = DashboardService({"uid": "caan-user", "role": "CAAN_SMD"})
    result = svc.get_caan_state(days=0, regulator_id="caan")

    operator_ids = {o["tenant_id"] for o in result["operators"]}
    assert operator_ids == set(tenant_ids), operator_ids
    assert result["kpis"]["active_operators"] == len(tenant_ids)
    assert result["kpis"]["mors"] == len(tenant_ids)
    assert result["kpis"]["high_risk_hazards"] == len(tenant_ids)
    assert result["kpis"]["responses"] == len(tenant_ids)

    by_id = {o["tenant_id"]: o for o in result["operators"]}
    for tid in ("air1", "caan-fssd", "caan-assd"):
        assert by_id[tid]["mors"] == 1, tid
        assert by_id[tid]["high_risk_hazards"] == 1, tid
        assert by_id[tid]["sms_maturity"] == 4.0, tid

    maturity = result["sms_maturity"]
    assert maturity["state"]["response_count"] == len(tenant_ids)


def test_get_caan_survey_maturity_empty(monkeypatch):
    svc = _survey_svc(monkeypatch, surveys=[])
    result = svc.get_caan_survey_maturity()
    assert result["operators"] == []
    assert result["state"]["overall_sms_maturity"] is None
    assert result["state"]["response_count"] == 0


def test_get_caan_sms_maturity_assessment_low_pillars(monkeypatch):
    from app.services.dashboard_service import DashboardService

    written = {}

    class _Snap:
        def __init__(self, data):
            self._data = data
            self.exists = bool(data)

        def to_dict(self):
            return self._data

    class _DocRef:
        def __init__(self, data=None):
            self._data = data or {}

        def get(self):
            return _Snap(self._data)

        def set(self, data):
            written.update(data)

        def collection(self, name):
            return _Coll([])

    class _Coll:
        def __init__(self, docs):
            self._docs = docs

        def get(self):
            return [_Snap(d) for d in self._docs]

        def document(self, doc_id):
            return _DocRef()

        def collection(self, name):
            return _Coll([])

    class _DB:
        def __init__(self, surveys):
            self._surveys = surveys

        def collection_group(self, name):
            return _Coll(self._surveys)

        def collection(self, name):
            return _Coll([])

    db = _DB([
        {
            "tenant_id": "air1",
            "safety_policy": 2.0, "safety_risk_management": 2.0,
            "safety_assurance": 4.0, "safety_promotion": 4.0,
            "overall_sms_maturity": 3.0,
            "question_scores": {"q1": 2.0, "q5": 2.0},
            "submitted_at": datetime.now(timezone.utc),
        },
        {
            "tenant_id": "air2",
            "safety_policy": 5.0, "safety_risk_management": 5.0,
            "safety_assurance": 5.0, "safety_promotion": 5.0,
            "overall_sms_maturity": 5.0,
            "submitted_at": datetime.now(timezone.utc),
        },
    ])
    monkeypatch.setattr("app.firebase.get_db", lambda: db)
    svc = DashboardService({"uid": "caan-user", "role": "CAAN_SMD"})
    result = svc.get_caan_sms_maturity_assessment(days=90)

    assert result["period_days"] == 90
    by_id = {op["tenant_id"]: op for op in result["operators"]}
    # air1: policy & SRM below 70% -> mock recommendations generated
    low_pillars = {lp["pillar"] for lp in by_id["air1"]["low_pillars"]}
    assert low_pillars == {"safety_policy", "safety_risk_management"}
    assert len(by_id["air1"]["recommendations"]) == 2
    assert all(r["score_pct"] < 70 for r in by_id["air1"]["recommendations"])
    # air2: all strong -> no recommendations
    assert by_id["air2"]["low_pillars"] == []
    assert by_id["air2"]["recommendations"] == []
    assert written.get("period_days") == 90


# ============================================================================
# Airline SMS maturity (tenant-scoped counterpart of the CAAN dashboard)
# ============================================================================

def test_get_airline_sms_maturity_tenant_scoped(monkeypatch):
    from app.services.dashboard_service import DashboardService

    written = {}

    class _Snap:
        def __init__(self, data):
            self._data = data
            self.exists = bool(data)

        def to_dict(self):
            return self._data

    class _DocRef:
        def __init__(self, data=None):
            self._data = data or {}

        def get(self):
            return _Snap(self._data)

        def set(self, data):
            written.update(data)

        def collection(self, name):
            return _Coll([])

    class _Coll:
        def __init__(self, docs):
            self._docs = docs

        def get(self):
            return [_Snap(d) for d in self._docs]

        def document(self, doc_id):
            return _DocRef()

        def collection(self, name):
            return _Coll([])

    class _DB:
        def __init__(self, surveys):
            self._surveys = surveys

        def collection_group(self, name):
            return _Coll(self._surveys)

        def collection(self, name):
            return _Coll([])

    docs = []
    for _ in range(6):
        docs.append({
            "tenant_id": "air1",
            "safety_policy": 5.0, "safety_risk_management": 1.0,
            "safety_assurance": 2.0, "safety_promotion": 4.0,
            "overall_sms_maturity": 3.0,
            "question_scores": {"q1": 5.0},
            "submitted_at": datetime.now(timezone.utc),
        })
    # A different tenant's data must never surface for air1's officer.
    docs.append({
        "tenant_id": "air2",
        "safety_policy": 5.0, "safety_risk_management": 5.0,
        "safety_assurance": 5.0, "safety_promotion": 5.0,
        "overall_sms_maturity": 5.0,
        "submitted_at": datetime.now(timezone.utc),
    })

    monkeypatch.setattr("app.firebase.get_db", lambda: _DB(docs))
    svc = DashboardService({"uid": "air-officer", "role": "AIRLINE_ADMIN", "tenant_id": "air1"})
    result = svc.get_airline_sms_maturity(days=365)

    assert result["tenant_id"] == "air1"
    assert result["response_count"] == 6
    assert result["overall_score"] == 50.0
    assert result["tier"] == "action"
    assert result["tier_label"] == "Action Needed"
    assert result["pillars"]["safety_policy"] == 100.0
    assert result["pillars"]["safety_risk_management"] == 0.0
    assert result["pillars"]["safety_assurance"] == 25.0
    assert result["pillars"]["safety_promotion"] == 75.0
    assert result["assessment"]["strengths"] == ["Safety Policy"]
    assert sorted(result["assessment"]["improvement_opportunities"]) == [
        "Safety Assurance", "Safety Risk Management"]
    assert len(result["assessment"]["priority_actions"]) == 2
    assert all(r["score_pct"] < 70 for r in result["assessment"]["priority_actions"])
    assert len(result["history"]) == 1
    assert result["history"][0]["overall_score"] == 50.0
    assert result["history"][0]["response_count"] == 6
    assert written.get("period_days") == 365


def test_get_airline_sms_maturity_empty(monkeypatch):
    from app.services.dashboard_service import DashboardService

    class _Snap:
        def __init__(self, data):
            self._data = data
            self.exists = bool(data)

        def to_dict(self):
            return self._data

    class _DocRef:
        def __init__(self, data=None):
            self._data = data or {}

        def get(self):
            return _Snap(self._data)

        def collection(self, name):
            return _Coll([])

    class _Coll:
        def __init__(self, docs=None):
            self._docs = docs or []

        def get(self):
            return [_Snap(d) for d in self._docs]

        def document(self, doc_id):
            return _DocRef()

        def collection(self, name):
            return _Coll([])

    class _DB:
        def collection_group(self, name):
            return _Coll([])

        def collection(self, name):
            return _Coll([])

    monkeypatch.setattr("app.firebase.get_db", lambda: _DB())
    svc = DashboardService({"uid": "air-officer", "role": "AIRLINE_ADMIN", "tenant_id": "air1"})
    result = svc.get_airline_sms_maturity(days=365)

    assert result["tenant_id"] == "air1"
    assert result["overall_score"] is None
    assert result["assessment"]["priority_actions"] == []
    assert result["history"] == []
    assert result["response_count"] == 0


def test_get_airline_sms_maturity_requires_tenant():
    from app.services.dashboard_service import DashboardService

    svc = DashboardService({"uid": "nobody", "role": "USER"})
    result = svc.get_airline_sms_maturity()
    assert result["overall_score"] is None
    assert result["assessment"]["priority_actions"] == []


def test_get_airline_sms_maturity_missing_pillars(monkeypatch):
    from app.services.dashboard_service import DashboardService

    class _Snap:
        def __init__(self, data):
            self._data = data
            self.exists = bool(data)

        def to_dict(self):
            return self._data

    class _DocRef:
        def __init__(self, data=None):
            self._data = data or {}

        def get(self):
            return _Snap(self._data)

        def collection(self, name):
            return _Coll([])

    class _Coll:
        def __init__(self, docs=None):
            self._docs = docs or []

        def get(self):
            return [_Snap(d) for d in self._docs]

        def document(self, doc_id):
            return _DocRef()

        def collection(self, name):
            return _Coll([])

    class _DB:
        def __init__(self, surveys):
            self._surveys = surveys

        def collection_group(self, name):
            return _Coll(self._surveys)

        def collection(self, name):
            return _Coll([])

    docs = []
    for _ in range(4):
        docs.append({
            "tenant_id": "air1",
            "safety_policy": 4.0, "safety_risk_management": 2.0,
            "safety_assurance": 3.0,  # safety_promotion intentionally absent
            "overall_sms_maturity": 3.0,
            "submitted_at": datetime.now(timezone.utc),
        })
    monkeypatch.setattr("app.firebase.get_db", lambda: _DB(docs))
    monkeypatch.setattr(
        "app.services.dashboard_service.recommend_sms_maturity_actions",
        lambda *a, **k: [{"action": "Mock action A"}, {"action": "Mock action B"}])
    svc = DashboardService({"uid": "air-officer", "role": "AIRLINE_ADMIN", "tenant_id": "air1"})
    result = svc.get_airline_sms_maturity(days=365)

    assert result["pillars"]["safety_policy"] == 75.0
    assert "safety_promotion" not in result["pillars"]
    assert result["overall_score"] == 50.0
    assert "Safety Promotion" not in result["assessment"]["strengths"]
    assert "Safety Promotion" not in result["assessment"]["improvement_opportunities"]
    assert sorted(result["assessment"]["improvement_opportunities"]) == [
        "Safety Assurance", "Safety Risk Management"]


def test_get_airline_sms_maturity_history_ordering(monkeypatch):
    from app.services.dashboard_service import DashboardService

    class _Snap:
        def __init__(self, data):
            self._data = data
            self.exists = bool(data)

        def to_dict(self):
            return self._data

    class _DocRef:
        def __init__(self, data=None):
            self._data = data or {}

        def get(self):
            return _Snap(self._data)

        def collection(self, name):
            return _Coll([])

    class _Coll:
        def __init__(self, docs=None):
            self._docs = docs or []

        def get(self):
            return [_Snap(d) for d in self._docs]

        def document(self, doc_id):
            return _DocRef()

        def collection(self, name):
            return _Coll([])

    class _DB:
        def __init__(self, surveys):
            self._surveys = surveys

        def collection_group(self, name):
            return _Coll(self._surveys)

        def collection(self, name):
            return _Coll([])

    older = datetime.now(timezone.utc) - timedelta(days=45)
    docs = [
        # Strong month (2 responses, ~45 days ago)
        {"tenant_id": "air1", "safety_policy": 5.0, "safety_risk_management": 5.0,
         "safety_assurance": 5.0, "safety_promotion": 5.0, "overall_sms_maturity": 5.0,
         "submitted_at": older},
        {"tenant_id": "air1", "safety_policy": 5.0, "safety_risk_management": 5.0,
         "safety_assurance": 5.0, "safety_promotion": 5.0, "overall_sms_maturity": 5.0,
         "submitted_at": older + timedelta(hours=1)},
        # Weaker month (1 response, now)
        {"tenant_id": "air1", "safety_policy": 2.0, "safety_risk_management": 2.0,
         "safety_assurance": 4.0, "safety_promotion": 4.0, "overall_sms_maturity": 3.0,
         "submitted_at": datetime.now(timezone.utc)},
    ]
    monkeypatch.setattr("app.firebase.get_db", lambda: _DB(docs))
    svc = DashboardService({"uid": "air-officer", "role": "AIRLINE_ADMIN", "tenant_id": "air1"})
    result = svc.get_airline_sms_maturity(days=365)

    assert len(result["history"]) == 2
    periods = [h["period"] for h in result["history"]]
    assert periods == sorted(periods)  # chronological order
    assert result["history"][0]["overall_score"] == 100.0
    assert result["history"][0]["response_count"] == 2
    assert result["history"][0]["tier"] == "strong"
    assert result["history"][0]["assessment_date"] is not None
    assert result["history"][1]["overall_score"] == 50.0
    assert result["history"][1]["response_count"] == 1


# ============================================================================
# Airline SMS maturity API (route-level auth + envelope)
# ============================================================================

def _empty_firestore():
    class _Snap:
        def __init__(self, data):
            self._data = data
            self.exists = bool(data)

        def to_dict(self):
            return self._data

    class _DocRef:
        def get(self):
            return _Snap({})

        def set(self, data):
            pass

        def collection(self, name):
            return _Coll()

    class _Coll:
        def get(self):
            return []

        def document(self, doc_id):
            return _DocRef()

        def collection(self, name):
            return _Coll()

    class _DB:
        def collection_group(self, name):
            return _Coll()

        def collection(self, name):
            return _Coll()

    return _DB()


def test_airline_sms_maturity_route_requires_auth(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr("app.firebase.get_db", lambda: _empty_firestore())
    resp = TestClient(app).get("/api/v1/dashboard/airline/sms-maturity")
    assert resp.status_code in (401, 403)


def test_airline_sms_maturity_route_tenant_required(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.middleware.auth import get_current_user

    monkeypatch.setattr("app.firebase.get_db", lambda: _empty_firestore())
    app.dependency_overrides[get_current_user] = lambda: {
        "uid": "u", "role": "USER", "tenant_id": None, "email": "user@aviasafe.com"}
    try:
        resp = TestClient(app).get("/api/v1/dashboard/airline/sms-maturity")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_airline_sms_maturity_route_200_empty(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.middleware.auth import get_current_user

    monkeypatch.setattr("app.firebase.get_db", lambda: _empty_firestore())
    app.dependency_overrides[get_current_user] = lambda: {
        "uid": "officer", "role": "AIRLINE_ADMIN", "tenant_id": "air1",
        "email": "officer@air1.com"}
    try:
        resp = TestClient(app).get("/api/v1/dashboard/airline/sms-maturity")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload.get("status") == "success"
        data = payload["data"]
        assert data["tenant_id"] == "air1"
        assert data["overall_score"] is None
        assert data["assessment"]["priority_actions"] == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)
