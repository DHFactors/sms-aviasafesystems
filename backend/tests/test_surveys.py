"""Survey submission + scoring tests.

Covers the shared scoring service (pure functions) and the POST /api/v1/surveys
endpoint (validation, persistence to both surveys + responses, auth handling).
"""

from datetime import datetime

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.db_models import Survey, SurveyResponse
from app.db.ids import register_tenant
from app.db.session import session_scope
from app.main import app
from app.services import survey_scoring as sc


# ============================================================================
# Scoring service (pure functions, no Firestore)
# ============================================================================

VALID_ANSWERS = {
    "q1_aware": True,
    "q2": 5, "q3": 4, "q4": 4, "q5_spi": 4,
    "q6": 5, "q7": 5, "q8": 4, "q9": 4, "q10": 5, "q11": 4,
    "q12_risk_assess": 4, "q13_action_inform": 3,
    "q14": 4, "q15": 4, "q16": 3, "q19_invest_outcome": 4, "q20_corrective": 4,
    "q17": 5, "q18": 4, "q21": 4, "q22": 5, "q23_peer": 4,
}


def test_master_contract_counts():
    # 23 scored questions across the four ICAO pillars
    assert len(sc.QUESTION_PILLARS) == 23
    assert len(sc.PILLARS) == 4
    assert set(sc.PILLARS) == {
        "safety_policy", "safety_risk_management", "safety_assurance", "safety_promotion"
    }


def test_binary_normalization():
    assert sc.normalize_answer("q1_aware", True) == 5.0
    assert sc.normalize_answer("q1_aware", False) == 1.0
    assert sc.normalize_answer("q1_aware", 5) == 5.0
    assert sc.normalize_answer("q1_aware", 1) == 1.0
    assert sc.normalize_answer("q1_aware", 3) is None
    assert sc.normalize_answer("q1_aware", "true") is None


def test_likert_normalization():
    assert sc.normalize_answer("q2", 5) == 5.0
    assert sc.normalize_answer("q2", 1) == 1.0
    assert sc.normalize_answer("q2", 6) is None
    assert sc.normalize_answer("q2", 0) is None
    assert sc.normalize_answer("q2", True) is None


def test_validate_answers_accepts_valid():
    assert sc.validate_answers(VALID_ANSWERS) == {}


def test_validate_answers_rejects_missing():
    missing = dict(VALID_ANSWERS)
    del missing["q6"]
    errors = sc.validate_answers(missing)
    assert errors["q6"] == "required"


def test_validate_answers_rejects_out_of_range():
    bad = dict(VALID_ANSWERS)
    bad["q10"] = 99
    errors = sc.validate_answers(bad)
    assert errors["q10"].startswith("must be")


def test_validate_answers_ignores_optional_text():
    answers = dict(VALID_ANSWERS)
    answers["q24_comments"] = "some feedback"
    assert sc.validate_answers(answers) == {}


def test_pillar_scores_grouping():
    scores = sc.compute_pillar_scores(VALID_ANSWERS)
    # q1_aware(5) + q2(5) + q3(4) + q4(4) + q5_spi(4) = 22 / 5 = 4.4
    assert scores["safety_policy"] == 4.4
    # q6(5)+q7(5)+q8(4)+q9(4)+q10(5)+q11(4)+q12(4)+q13(3) = 34 / 8 = 4.25
    assert scores["safety_risk_management"] == 4.25
    # q14(4)+q15(4)+q16(3)+q19(4)+q20(4) = 19 / 5 = 3.8
    assert scores["safety_assurance"] == 3.8
    # q17(5)+q18(4)+q21(4)+q22(5)+q23(4) = 22 / 5 = 4.4
    assert scores["safety_promotion"] == 4.4


def test_overall_and_percentage():
    scores = sc.compute_pillar_scores(VALID_ANSWERS)
    overall = sc.compute_overall_maturity(scores)
    assert overall == round((4.4 + 4.25 + 3.8 + 4.4) / 4, 2)
    assert sc.compute_percentage_score(5.0) == 100.0
    assert sc.compute_percentage_score(3.0) == 50.0
    assert sc.compute_percentage_score(1.0) == 0.0
    assert sc.compute_percentage_score(None) is None


def test_question_scores_shape():
    qs = sc.compute_question_scores(VALID_ANSWERS)
    assert set(qs.keys()) == set(sc.QUESTION_PILLARS)
    assert qs["q1_aware"] == 5.0


# ============================================================================
# Fake Firestore for route-level tests
# ============================================================================

class _FakeDoc:
    def __init__(self, data=None):
        self._data = data or {}
        self.exists = bool(data)

    def to_dict(self):
        return self._data


class _FakeColl:
    def __init__(self):
        self.docs = []
        self._next_id = 1

    def document(self, doc_id=None):
        return _FakeTenantRef()

    def add(self, data):
        did = f"auto-{self._next_id}"
        self._next_id += 1
        self.docs.append((did, dict(data)))
        ref = type("Ref", (), {"id": did})()
        return (None, ref)

    def get(self):
        return []


class _FakeTenantRef:
    def collection(self, name):
        return _FakeColl()


class _FakeDB:
    def __init__(self, tenant_known=True):
        self.tenant_known = tenant_known
        self.surveys = _FakeColl()
        self.responses = _FakeColl()
        self.audit = _FakeColl()
        self._meta = {"tenant": {"name": "Tara Air"} if tenant_known else None}

    def collection(self, name):
        if name == "tenants":
            class _Tenants:
                def __init__(self, db):
                    self._db = db

                def document(self, tid):
                    return _FakeTenantProxy(self._db)
            return _Tenants(self)
        if name == "audit_logs":
            return self.audit
        return _FakeColl()

    def collection_group(self, name):
        return _FakeColl()


class _FakeTenantProxy:
    def __init__(self, db):
        self._db = db

    def get(self):
        return _FakeDoc(self._db._meta["tenant"])

    def collection(self, name):
        if name == "surveys":
            return self._db.surveys
        if name == "responses":
            return self._db.responses
        return _FakeColl()


def _patch_db(monkeypatch, db):
    monkeypatch.setattr("app.routes.surveys.get_db", lambda: db)
    monkeypatch.setattr("app.services.audit_service.get_db", lambda: db)


def _patch_user(monkeypatch, user):
    async def _fake_get_current_user(credentials=None):
        return user
    monkeypatch.setattr("app.routes.surveys.get_current_user", _fake_get_current_user)


def _post(payload, headers=None):
    return TestClient(app).post("/api/v1/surveys/", json=payload, headers=headers or {})


def _fetch_survey_rows(tenant):
    tid = register_tenant(tenant)

    async def _get():
        async with session_scope() as s:
            surveys = (
                await s.scalars(select(Survey).where(Survey.tenant_id == tid))
            ).all()
            responses = (
                await s.scalars(select(SurveyResponse).where(SurveyResponse.tenant_id == tid))
            ).all()
            return {"surveys": surveys, "responses": responses}

    return asyncio.run(_get())


@pytest.fixture(autouse=True)
def _cleanup_survey_rows():
    yield
    tid = register_tenant("tara-air")

    async def _wipe():
        async with session_scope() as s:
            await s.execute(delete(SurveyResponse).where(SurveyResponse.tenant_id == tid))
            await s.execute(delete(Survey).where(Survey.tenant_id == tid))

    asyncio.run(_wipe())


def test_survey_route_anonymous_success(monkeypatch):
    db = _FakeDB(tenant_known=True)
    _patch_db(monkeypatch, db)

    resp = _post({"tenantId": "tara-air", "respondentId": "emp@taraair.com", "answers": VALID_ANSWERS})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["tenant_id"] == "tara-air"
    assert body["data"]["overall_sms_maturity"] is not None

    # Scored doc persisted to surveys, raw doc to responses.
    rows = _fetch_survey_rows("tara-air")
    assert len(rows["surveys"]) == 1
    survey = rows["surveys"][0]
    assert str(survey.tenant_id) == register_tenant("tara-air")
    assert survey.overall_sms_maturity == 4
    assert survey.safety_policy == 4
    assert survey.overall_score_pct is not None
    assert survey.survey_version == sc.SURVEY_VERSION
    assert isinstance(survey.submitted_at, datetime)
    assert survey.submitted_at.tzinfo is not None
    assert len(rows["responses"]) == 1
    raw = rows["responses"][0]
    assert raw.answers["q1_aware"] is True
    assert raw.submitted_at.tzinfo is not None
    # Audit entry written
    assert len(db.audit.docs) == 1
    assert db.audit.docs[0][1]["action"] == "SURVEY_SUBMITTED"


def test_survey_route_unknown_tenant(monkeypatch):
    _patch_db(monkeypatch, _FakeDB(tenant_known=False))
    resp = _post({"tenantId": "ghost-air", "answers": VALID_ANSWERS})
    assert resp.status_code == 400


def test_survey_route_validation_error(monkeypatch):
    _patch_db(monkeypatch, _FakeDB(tenant_known=True))
    bad = dict(VALID_ANSWERS)
    del bad["q18"]
    resp = _post({"tenantId": "tara-air", "answers": bad})
    assert resp.status_code == 422
    body = resp.json()
    assert "q18" in body["errors"]
    assert body["success"] is False


def test_survey_route_missing_tenant(monkeypatch):
    _patch_db(monkeypatch, _FakeDB(tenant_known=True))
    resp = _post({"answers": VALID_ANSWERS})
    assert resp.status_code == 422


def test_survey_route_authenticated_tenant_mismatch(monkeypatch):
    _patch_db(monkeypatch, _FakeDB(tenant_known=True))
    user = {
        "uid": "u1", "email": "officer@taraair.com",
        "role": "AIRLINE_ADMIN", "tenant_id": "tara-air",
        "claims": {"role": "AIRLINE_ADMIN", "tenant_id": "tara-air"},
    }
    _patch_user(monkeypatch, user)
    # User belongs to tara-air but posts to another tenant -> 403
    resp = _post({"tenantId": "other-air", "answers": VALID_ANSWERS},
                 headers={"Authorization": "Bearer faketoken"})
    assert resp.status_code == 403


def test_survey_route_authenticated_own_tenant(monkeypatch):
    db = _FakeDB(tenant_known=True)
    _patch_db(monkeypatch, db)
    user = {
        "uid": "u1", "email": "officer@taraair.com",
        "role": "AIRLINE_ADMIN", "tenant_id": "tara-air",
        "claims": {"role": "AIRLINE_ADMIN", "tenant_id": "tara-air"},
    }
    _patch_user(monkeypatch, user)
    resp = _post({"tenantId": "tara-air", "answers": VALID_ANSWERS},
                 headers={"Authorization": "Bearer faketoken"})
    assert resp.status_code == 201
    rows = _fetch_survey_rows("tara-air")
    assert len(rows["surveys"]) == 1
    assert len(rows["responses"]) == 1
