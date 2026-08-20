"""PSOE Audit & Surveillance (Phase 3 Step 2A) — template + scoring + RBAC tests.

Covers:
  * Template loading from backend/app/data/psoe_appendix10.json — the four
    CAAN SMS Procedure Manual Appendix 10 components with weights 10/40/30/20
    and the CAAN/ICAO 0-3 implementation scale.
  * Scoring — N/A answers are excluded from the denominator; the overall score
    is the weight combination of component percentages.
  * RBAC — the template is public; listing requires authentication; creating
    requires TENANT_ADMIN / AIRLINE_ADMIN / CAAN_SMD (STAFF / SAFETY_OFFICER
    get 403); tenant-bound users are locked to their own tenant.
"""

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user
from app.models.psoe import PSOEAnswer
from app.services.psoe_service import (
    TEMPLATE_VERSION,
    compute_component_scores,
    compute_overall,
    load_template,
    reset_template_cache,
)


# ============================================================================
# Fake Firebase storage + auth
# ============================================================================

class _Doc:
    def __init__(self, data, exists=True, id=None):
        self._data = data or {}
        self.exists = exists
        self.id = id

    def to_dict(self):
        return self._data


class _CollQuery:
    def __init__(self, db, name):
        self._db = db
        self._name = name
        self._filters = []

    def where(self, field, op, value):
        self._filters.append((field, op, value))
        return self

    def limit(self, n):
        return self

    def get(self):
        return self._run()

    def stream(self):
        return self._run()

    def _run(self):
        store = self._db._store(self._name)
        rows = []
        for key, data in store.items():
            doc = dict(data or {})
            doc.setdefault("id", key)
            ok = True
            for field, op, value in self._filters:
                if op == "==" and doc.get(field) != value:
                    ok = False
            if ok:
                rows.append(_Doc(doc, exists=True, id=doc["id"]))
        return rows


class _CollRef:
    def __init__(self, db, name, key):
        self._db = db
        self._name = name
        self._key = key

    def get(self):
        store = self._db._store(self._name)
        data = store.get(self._key)
        if data is None:
            return _Doc(None, exists=False, id=self._key)
        return _Doc(dict(data), exists=True, id=self._key)

    def set(self, data, merge=False):
        store = self._db._store(self._name)
        if merge and self._key in store:
            merged = dict(store[self._key])
            merged.update(dict(data))
            data = merged
        store[self._key] = dict(data)

    def update(self, data):
        store = self._db._store(self._name)
        merged = dict(store.get(self._key) or {})
        merged.update(dict(data))
        store[self._key] = merged


class _Coll:
    def __init__(self, db, name):
        self._db = db
        self._name = name

    def document(self, key):
        return _CollRef(self._db, self._name, key)

    def where(self, field, op, value):
        return _CollQuery(self._db, self._name).where(field, op, value)

    def add(self, entry):
        store = self._db._store(self._name)
        doc_id = f"{self._name}-{len(store) + 1}"
        store[doc_id] = dict(entry)
        return type("Ref", (), {"id": doc_id})()

    def get(self):
        store = self._db._store(self._name)
        return [_Doc(dict(d), exists=True, id=k) for k, d in store.items()]


class _FakeDB:
    def __init__(self):
        self.tenants = {}
        self.psoe_assessments = {}
        self.audit_logs = {}

    def _store(self, name):
        return {
            "tenants": self.tenants,
            "psoe_assessments": self.psoe_assessments,
            "audit_logs": self.audit_logs,
        }[name]

    def collection(self, name):
        if name not in ("tenants", "psoe_assessments", "audit_logs"):
            raise AssertionError(f"unexpected collection {name}")
        return _Coll(self, name)


def _patch(monkeypatch, db):
    monkeypatch.setattr("app.firebase.get_db", lambda: db)
    monkeypatch.setattr("app.routes.psoe.get_db", lambda: db)
    monkeypatch.setattr("app.services.audit_service.get_db", lambda: db)


def _as_role(role, tid="airline1", department=None):
    return {
        "uid": f"uid-{role.lower()}",
        "email": f"{role.lower()}@example.com",
        "role": role,
        "tenant_id": tid,
        "department": department,
        "claims": {"role": role, "tenant_id": tid, "department": department},
    }


def _override_user(user):
    app.dependency_overrides[get_current_user] = lambda: user


def _override_unauth():
    def _deny():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = _deny


def _clear_override():
    app.dependency_overrides.pop(get_current_user, None)


def _template_ids():
    t = load_template()
    return {c.id: [q.id for q in c.questions] for c in t.components}


# ============================================================================
# Template loading
# ============================================================================

def test_template_loads_four_components_with_weights():
    reset_template_cache()
    t = load_template()
    assert len(t.components) == 4
    assert [c.weight for c in t.components] == [10, 40, 30, 20]
    assert t.total_weight == 100
    names = [c.name for c in t.components]
    assert names == [
        "Safety Policy & Objectives",
        "Safety Risk Management",
        "Safety Assurance",
        "Safety Promotion",
    ]
    ids = [q.id for c in t.components for q in c.questions]
    assert len(ids) == len(set(ids)), "question ids must be unique"
    for c in t.components:
        assert c.questions, c.id
        for q in c.questions:
            assert q.max_score == 3
            assert q.component == c.id
    assert t.scoring_scale["0"] == "Not Implemented / Non-Compliant"
    assert t.scoring_scale["3"] == "Fully Effective & Continuous Improvement"


def test_template_endpoint_is_public():
    reset_template_cache()
    resp = TestClient(app).get("/api/v1/psoe/template")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["version"] == TEMPLATE_VERSION
    assert body["total_weight"] == 100
    assert len(body["components"]) == 4
    weights = {c["name"]: c["weight"] for c in body["components"]}
    assert weights == {
        "Safety Policy & Objectives": 10,
        "Safety Risk Management": 40,
        "Safety Assurance": 30,
        "Safety Promotion": 20,
    }


def test_legacy_psoe_template_alias_works():
    reset_template_cache()
    resp = TestClient(app).get("/api/psoe/template")
    assert resp.status_code == 200, resp.text


# ============================================================================
# Scoring
# ============================================================================

def test_scoring_excludes_na_from_denominator():
    reset_template_cache()
    t = load_template()
    sp = [q.id for q in t.components[0].questions]
    responses = [
        PSOEAnswer(question_id=sp[0], score=3),
        PSOEAnswer(question_id=sp[1], score=2),
        PSOEAnswer(question_id=sp[2], score=3),
        PSOEAnswer(question_id=sp[3], is_na=True),
        PSOEAnswer(question_id=sp[4], score=1),
        PSOEAnswer(question_id=sp[5], score=3),
    ]
    cs = compute_component_scores(responses, t)
    c1 = cs["component_1"]
    assert c1["applicable_questions"] == 5
    assert c1["na_questions"] == 1
    assert c1["score"] == 12
    assert c1["max_score"] == 15
    assert c1["score_pct"] == 80.0
    assert c1["weighted_pct"] == 8.0  # 80% of weight 10


def test_na_only_component_scores_zero():
    reset_template_cache()
    t = load_template()
    sp = [q.id for q in t.components[0].questions]
    responses = [PSOEAnswer(question_id=qid, is_na=True) for qid in sp]
    cs = compute_component_scores(responses, t)
    assert cs["component_1"]["applicable_questions"] == 0
    assert cs["component_1"]["score_pct"] == 0.0


def test_overall_is_weighted_combination():
    reset_template_cache()
    t = load_template()
    responses = []
    for comp in t.components:
        for q in comp.questions:
            score = 0 if q.id.startswith("SRM-") else 3
            responses.append(PSOEAnswer(question_id=q.id, score=score))
    cs = compute_component_scores(responses, t)
    overall = compute_overall(cs)
    # Components 1,3,4 at 100%, Component 2 (weight 40) at 0% -> 60%.
    assert overall["overall_score_pct"] == 60.0
    assert overall["overall_level"] == "Partially Implemented (Documented only)"


# ============================================================================
# RBAC
# ============================================================================

def test_list_assessments_requires_auth(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db)
    _override_unauth()
    try:
        resp = TestClient(app).get("/api/v1/psoe/assessments")
    finally:
        _clear_override()
    assert resp.status_code == 401


def test_create_assessment_requires_admin_role(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db)
    _override_user(_as_role("STAFF", tid="airline1"))
    try:
        resp = TestClient(app).post("/api/v1/psoe/assessments",
                                    json={"title": "Annual SMS surveillance"})
    finally:
        _clear_override()
    assert resp.status_code == 403
    assert not db.psoe_assessments


def test_safety_officer_cannot_create_assessment(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db)
    _override_user(_as_role("SAFETY_OFFICER", tid="airline1"))
    try:
        resp = TestClient(app).post("/api/v1/psoe/assessments",
                                    json={"title": "Annual SMS surveillance"})
    finally:
        _clear_override()
    assert resp.status_code == 403


def test_tenant_admin_can_create_assessment(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db)
    _override_user(_as_role("TENANT_ADMIN", tid="airline1"))
    try:
        resp = TestClient(app).post("/api/v1/psoe/assessments", json={
            "title": "Annual SMS surveillance",
            "responses": [
                {"question_id": "SP-01", "score": 3},
                {"question_id": "SP-02", "score": 2},
                {"question_id": "SRM-01", "is_na": True},
            ],
        })
    finally:
        _clear_override()
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["tenant_id"] == "airline1"
    assert body["status"] == "draft"
    assert body["overall_score_pct"] is not None
    assert body["component_scores"]["component_1"]["score"] == 5
    stored = list(db.psoe_assessments.values())[0]
    assert stored["tenant_id"] == "airline1"
    assert stored["created_by"] == "tenant_admin@example.com"


def test_legacy_airline_admin_can_create_assessment(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db)
    _override_user(_as_role("AIRLINE_ADMIN", tid="airline1"))
    try:
        resp = TestClient(app).post("/api/v1/psoe/assessments",
                                    json={"title": "Annual SMS surveillance"})
    finally:
        _clear_override()
    assert resp.status_code == 201, resp.text
    assert resp.json()["tenant_id"] == "airline1"


def test_caan_smd_can_create_assessment_with_target_tenant(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db)
    _override_user(_as_role("CAAN_SMD", tid=None))
    try:
        resp = TestClient(app).post("/api/v1/psoe/assessments", json={
            "title": "CAAN surveillance - airline1",
            "tenant_id": "airline1",
        })
    finally:
        _clear_override()
    assert resp.status_code == 201, resp.text
    assert resp.json()["tenant_id"] == "airline1"


def test_caan_smd_must_specify_target_tenant(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db)
    _override_user(_as_role("CAAN_SMD", tid=None))
    try:
        resp = TestClient(app).post("/api/v1/psoe/assessments",
                                    json={"title": "Missing tenant"})
    finally:
        _clear_override()
    assert resp.status_code == 422


def test_tenant_admin_cannot_create_for_another_tenant(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db)
    _override_user(_as_role("TENANT_ADMIN", tid="airline1"))
    try:
        resp = TestClient(app).post("/api/v1/psoe/assessments", json={
            "title": "Sneaky",
            "tenant_id": "airline2",
        })
    finally:
        _clear_override()
    assert resp.status_code == 403
    assert not db.psoe_assessments


def test_list_is_scoped_to_own_tenant(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db)
    db.psoe_assessments["a1"] = {
        "id": "a1", "tenant_id": "airline1", "title": "Airline 1 audit",
        "status": "draft", "template_version": "1.0.0",
        "created_at": "2026-08-20T00:00:00Z",
    }
    db.psoe_assessments["a2"] = {
        "id": "a2", "tenant_id": "airline2", "title": "Airline 2 audit",
        "status": "draft", "template_version": "1.0.0",
        "created_at": "2026-08-20T00:00:00Z",
    }
    _override_user(_as_role("TENANT_ADMIN", tid="airline1"))
    try:
        resp = TestClient(app).get("/api/v1/psoe/assessments")
    finally:
        _clear_override()
    assert resp.status_code == 200, resp.text
    titles = [a["title"] for a in resp.json()]
    assert titles == ["Airline 1 audit"]


def test_caan_smd_lists_all_or_scopes_by_tenant(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db)
    db.psoe_assessments["a1"] = {
        "id": "a1", "tenant_id": "airline1", "title": "Airline 1 audit",
        "status": "draft", "template_version": "1.0.0",
        "created_at": "2026-08-20T00:00:00Z",
    }
    db.psoe_assessments["a2"] = {
        "id": "a2", "tenant_id": "airline2", "title": "Airline 2 audit",
        "status": "draft", "template_version": "1.0.0",
        "created_at": "2026-08-20T00:00:00Z",
    }
    _override_user(_as_role("CAAN_SMD", tid=None))
    try:
        resp = TestClient(app).get("/api/v1/psoe/assessments")
    finally:
        _clear_override()
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    _override_user(_as_role("CAAN_SMD", tid=None))
    try:
        resp = TestClient(app).get("/api/v1/psoe/assessments?tenant_id=airline2")
    finally:
        _clear_override()
    assert resp.status_code == 200
    assert [a["tenant_id"] for a in resp.json()] == ["airline2"]


def test_get_assessment_scoped_to_own_tenant(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db)
    db.psoe_assessments["a1"] = {
        "id": "a1", "tenant_id": "airline1", "title": "Airline 1 audit",
        "status": "draft", "template_version": "1.0.0",
        "responses": [{"question_id": "SP-01", "score": 3}],
        "overall_score_pct": 50.0, "created_at": "2026-08-20T00:00:00Z",
    }
    _override_user(_as_role("TENANT_ADMIN", tid="airline1"))
    try:
        resp = TestClient(app).get("/api/v1/psoe/assessments/a1")
    finally:
        _clear_override()
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == "a1"
    assert body["tenant_id"] == "airline1"
    assert body["responses"][0]["question_id"] == "SP-01"


def test_get_assessment_forbidden_for_other_tenant(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db)
    db.psoe_assessments["a2"] = {
        "id": "a2", "tenant_id": "airline2", "title": "Airline 2 audit",
        "status": "draft", "created_at": "2026-08-20T00:00:00Z",
    }
    _override_user(_as_role("TENANT_ADMIN", tid="airline1"))
    try:
        resp = TestClient(app).get("/api/v1/psoe/assessments/a2")
    finally:
        _clear_override()
    assert resp.status_code == 403


def test_get_assessment_not_found(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db)
    _override_user(_as_role("TENANT_ADMIN", tid="airline1"))
    try:
        resp = TestClient(app).get("/api/v1/psoe/assessments/missing")
    finally:
        _clear_override()
    assert resp.status_code == 404


# ============================================================================
# Model validation
# ============================================================================

def test_answer_rejects_out_of_range_score():
    import pytest
    from app.models.psoe import PSOEAnswer
    with pytest.raises(Exception):
        PSOEAnswer(question_id="SP-01", score=5)


def test_answer_rejects_score_with_na():
    import pytest
    from app.models.psoe import PSOEAnswer
    with pytest.raises(Exception):
        PSOEAnswer(question_id="SP-01", score=2, is_na=True)