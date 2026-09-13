"""Regulator dashboard (AggregationService) Postgres rewire tests.

Covers the /api/v1/regulator aggregation endpoints end-to-end after the Phase F
rewire moved them off the FirestoreRepository stub onto Postgres reads
(app.db.pg -> hazards + surveys). The fake collection below applies `where`
filters so per-tenant aggregates are exact, matching how pg.fetch_all routes
BinaryExpression conditions through the test bridge.
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.db.isolation import demo_scope
from app.db.ids import tenant_uuid
from app.middleware.auth import get_current_user
from app.services.aggregation_service import AggregationService
from pg_bridge import patch_pg_through


# ============================================================================
# Filtering fake Firestore (applies where/limit exactly like the bridge)
# ============================================================================

class _FakeSnap:
    def __init__(self, data):
        self._data = data or {}
        self.id = self._data.get("id", "doc")

    def to_dict(self):
        return self._data


class _FakeQuery:
    def __init__(self, docs, conds=None):
        self._docs = docs
        self._conds = conds or []

    def where(self, field, op, value):
        return _FakeQuery(self._docs, self._conds + [(field, value)])

    def limit(self, _n):
        return self

    def stream(self):
        out = []
        for i, d in enumerate(self._docs):
            if all(d.get(f) == v for f, v in self._conds):
                out.append(_FakeSnap(dict(d)))
        return out

    def get(self):
        return self.stream()


class _FakeColl:
    def __init__(self, docs):
        self._docs = docs

    def where(self, field, op, value):
        return _FakeQuery(self._docs, [(field, value)])

    def stream(self):
        return [_FakeSnap(dict(d)) for d in self._docs]

    def get(self):
        return self.stream()

    def limit(self, _n):
        return self


class _DemoDB:
    def __init__(self, collections):
        self._cols = collections

    def collection(self, name):
        return _FakeColl(self._cols.get(name, []))


def _md_docs(overall, pillars=4):
    return {
        "overall_sms_maturity": overall,
        "safety_policy": pillars,
        "safety_risk_management": pillars,
        "safety_assurance": pillars,
        "safety_promotion": pillars,
    }


def _si64(slug):
    return str(tenant_uuid(slug))


def _sample_db():
    dm = demo_scope()
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)
    hazards = [
        {"id": "h-fw-1", "tenant_id": _si64("fixedwing"), "is_demo": dm,
         "adrep_category": "BIRD", "taxonomy": "Environmental",
         "risk_level": "High", "risk_index": 9, "title": "Bird strike RWY 10",
         "created_at": now},
        {"id": "h-rw-1", "tenant_id": _si64("rotarywing"), "is_demo": dm,
         "adrep_category": "BIRD", "taxonomy": "Environmental",
         "risk_level": "Low", "risk_index": 3, "title": "Bird activity apron",
         "created_at": now},
        {"id": "h-demo-1", "tenant_id": _si64("demoairport"), "is_demo": dm,
         "adrep_category": "WX", "taxonomy": "Weather",
         "risk_level": "Very High", "risk_index": 15, "title": "Severe windshear",
         "created_at": now},
        {"id": "h-demo-2", "tenant_id": _si64("demoairport"), "is_demo": dm,
         "adrep_category": "WX", "taxonomy": "Weather",
         "risk_level": "High", "risk_index": 9, "title": "Fog low visibility",
         "created_at": now},
    ]
    surveys = [
        {"id": "s-fw", "tenant_id": _si64("fixedwing"), "is_demo": dm,
         "submitted_at": now, **_md_docs(4)},
        {"id": "s-rw", "tenant_id": _si64("rotarywing"), "is_demo": dm,
         "submitted_at": now, **_md_docs(3)},
        {"id": "s-demo", "tenant_id": _si64("demoairport"), "is_demo": dm,
         "submitted_at": now, **_md_docs(5)},
    ]
    return _DemoDB({"hazards": hazards, "surveys": surveys, "tenants": []})


def _patch_reg_dashboard_db(monkeypatch):
    patch_pg_through(monkeypatch, lambda: _sample_db())
    return AggregationService()


_TIDS = ["fixedwing", "rotarywing", "demoairport"]


# ============================================================================
# Service-level (PG-backed reads)
# ============================================================================

def test_industry_averages_pg_backed(monkeypatch):
    svc = _patch_reg_dashboard_db(monkeypatch)
    result = _run(svc.calculate_industry_averages(_TIDS))
    assert "error" not in result
    assert result["tenant_count"] == 3
    assert result["average_overall"] == 4.0
    for comp in ["component_1", "component_2", "component_3", "component_4"]:
        assert result["average_components"][comp] == 4.0
    assert result["level_distribution"] == {
        "Level 1": 0, "Level 2": 0, "Level 3": 1, "Level 4": 1, "Level 5": 1,
    }
    assert [s["anonymized_id"] for s in result["anonymized_scores"]] == [
        "Operator-1", "Operator-2", "Operator-3",
    ]


def test_top_hazards_pg_backed(monkeypatch):
    svc = _patch_reg_dashboard_db(monkeypatch)
    result = _run(svc.get_top_hazards(_TIDS))
    assert "error" not in result
    by_cat = {c["category"]: c["count"] for c in result["top_categories"]}
    assert by_cat == {"WX": 2, "BIRD": 2}
    assert result["total_hazards"] == 4


def test_risk_trends_pg_backed(monkeypatch):
    svc = _patch_reg_dashboard_db(monkeypatch)
    result = _run(svc.get_risk_trends(_TIDS))
    assert "error" not in result
    assert result["total_points"] == 4
    assert result["by_risk_level"] == {"High": 2, "Low": 1, "Very High": 1}
    assert all(isinstance(t["date"], str) and len(t["date"]) == 10
               for t in result["trend_over_time"])


def test_risk_register_pg_backed(monkeypatch):
    svc = _patch_reg_dashboard_db(monkeypatch)
    result = _run(svc.get_state_risk_register(_TIDS))
    assert "error" not in result
    assert result["total_high_risks"] == 3
    values = [r["risk_value"] for r in result["top_risks"]]
    assert values == sorted(values, reverse=True) == [15, 9, 9]
    cats = {r["category"] for r in result["top_risks"]}
    assert cats == {"BIRD", "WX"}


def test_benchmarking_pg_backed(monkeypatch):
    svc = _patch_reg_dashboard_db(monkeypatch)
    result = _run(svc.get_benchmarking("fixedwing", _TIDS))
    assert "error" not in result
    assert result["operator_score"] == 4.0
    assert result["industry_average"] == 4.0
    assert result["difference"] == 0.0
    assert result["anonymized"] is True
    assert result["tenant_id"] == "fixedwing"


def test_insufficient_data_guard_preserved(monkeypatch):
    svc = _patch_reg_dashboard_db(monkeypatch)
    result = _run(svc.get_top_hazards(["fixedwing", "rotarywing"]))
    assert result == {"error": "Insufficient data", "count": 2}
    result = _run(svc.calculate_industry_averages(["fixedwing", "rotarywing"]))
    assert result == {"error": "Insufficient data: minimum 3 tenants required", "count": 2}


def test_maturity_missing_tenant_skipped(monkeypatch):
    svc = _patch_reg_dashboard_db(monkeypatch)
    result = _run(svc.calculate_industry_averages(["fixedwing", "rotarywing", "doesnotexist"]))
    assert result["tenant_count"] == 2
    assert result["average_overall"] == 3.5


# ============================================================================
# Route-level (auth + live wiring)
# ============================================================================

def _caan_user():
    return {"role": "CAAN_SMD", "tenant_id": None, "uid": "caan", "email": "caan@test.np"}


def test_regulator_dashboard_requires_auth():
    resp = TestClient(app).get("/api/v1/regulator/industry-averages")
    assert resp.status_code in (401, 403)


def test_industry_averages_route(monkeypatch):
    _patch_reg_dashboard_db(monkeypatch)
    app.dependency_overrides[get_current_user] = _caan_user
    try:
        resp = TestClient(app).get("/api/v1/regulator/industry-averages")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["tenant_count"] == 3
    assert payload["average_overall"] == 4.0


def test_risk_trends_route_query_param(monkeypatch):
    _patch_reg_dashboard_db(monkeypatch)
    app.dependency_overrides[get_current_user] = _caan_user
    try:
        resp = TestClient(app).get(
            "/api/v1/regulator/risk-trends?tenant_ids=fixedwing,rotarywing,demoairport"
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert resp.status_code == 200
    assert resp.json()["total_points"] == 4


def _run(coro):
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()