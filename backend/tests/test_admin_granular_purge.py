# ============================================================================
# Tests for Granular Demo Purges — Category C Steps 6 & 7
#   POST /api/v1/admin/psoe/purge        (purge_psoe_demo_data)
#   POST /api/v1/admin/state-risk/purge   (purge_state_risk_demo_data)
# ============================================================================

import asyncio
from types import SimpleNamespace

import pytest

from app.services.admin_data_service import (
    purge_psoe_demo_data,
    purge_state_risk_demo_data,
)


class _FakeDoc:
    def __init__(self, doc_id, data=None):
        self.id = doc_id
        self._data = data or {}

    @property
    def reference(self):
        return self

    def to_dict(self):
        return dict(self._data)

    def delete(self):
        self.deleted = True


class _FakeSubCollection:
    def __init__(self, db, name):
        self._db = db
        self.name = name

    def get(self):
        return list(self._db.docs.get(self.name, []))

    def stream(self):
        return iter(list(self._db.docs.get(self.name, [])))

    def document(self, doc_id):
        docs = self._db.docs.setdefault(self.name, [])
        for d in docs:
            if getattr(d, "id", None) == doc_id:
                return d
        doc = _FakeDoc(doc_id)
        docs.append(doc)
        return doc


class _FakeFirestore:
    def __init__(self):
        self.docs = {}

    def collection(self, name):
        return _FakeSubCollection(self, name)

    def seed(self, name, docs):
        self.docs.setdefault(name, []).extend(docs)


class _FakeResult:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class _FakeSession:
    def __init__(self, rowcount=2, raise_on=False):
        self.rowcount = rowcount
        self.raise_on = raise_on
        self.executed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        if self.raise_on:
            raise RuntimeError("pg exploded")
        return _FakeResult(self.rowcount)


class _FakeScope:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


ACTOR = {"uid": "u1", "email": "admin@aviasafe.test"}


@pytest.fixture
def patch(monkeypatch):
    fs = _FakeFirestore()
    auditor = []
    sessions = []
    config = {"rowcount": 2, "raise_on": False}

    def fake_get_db():
        return fs

    def fake_audit(action, actor, target, detail, result="success"):
        auditor.append((action, target, detail, result))

    def fake_session_scope():
        session = _FakeSession(rowcount=config["rowcount"], raise_on=config["raise_on"])
        sessions.append(session)
        return _FakeScope(session)

    monkeypatch.setattr("app.services.admin_data_service.get_db", fake_get_db)
    monkeypatch.setattr("app.services.admin_data_service._audit", fake_audit)
    monkeypatch.setattr("app.services.admin_data_service.session_scope", fake_session_scope)
    return SimpleNamespace(fs=fs, auditor=auditor, sessions=sessions, config=config)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# PSOE purge
# ---------------------------------------------------------------------------


def test_purge_psoe_demo_deletes_demo_pg_rows(patch):
    patch.config["rowcount"] = 2
    result = _run(purge_psoe_demo_data(ACTOR))

    assert result["success"] is True
    assert result["deleted_count"] == 4  # psoe_findings(2) + psoe_assessments(2)
    assert set(result["details"].keys()) == {"psoe_findings", "psoe_assessments"}
    assert result["firestore_deleted"] == 0
    actions = [a[0] for a in patch.auditor]
    assert "PSOE_DEMO_PURGED" in actions


def test_purge_psoe_demo_removes_only_seeder_firestore_baselines(patch):
    patch.fs.seed("psoe_assessments", [
        _FakeDoc("sita-air-baseline-completed",
                 {"created_by": "production-setup", "seed_version": "production-setup-1"}),
        _FakeDoc("sita-air-baseline-draft",
                 {"seed_version": "production-setup-2"}),
        _FakeDoc("real-assessment-1",
                 {"created_by": "alice@airline.com", "seed_version": None}),
    ])

    result = _run(purge_psoe_demo_data(ACTOR))

    assert result["firestore_deleted"] == 2
    docs = patch.fs.docs["psoe_assessments"]
    assert docs[0].deleted is True
    assert docs[1].deleted is True
    assert getattr(docs[2], "deleted", False) is False


def test_purge_psoe_demo_isolates_pg_error(patch):
    patch.config["raise_on"] = True

    result = _run(purge_psoe_demo_data(ACTOR))

    assert result["success"] is False
    assert str(result["details"]["psoe_findings"]).startswith("Error")


# ---------------------------------------------------------------------------
# State Risk purge
# ---------------------------------------------------------------------------


def test_purge_state_risk_demo_deletes_demo_rows(patch):
    patch.config["rowcount"] = 3

    result = _run(purge_state_risk_demo_data(ACTOR))

    assert result["success"] is True
    assert result["deleted_count"] == 3
    assert result["details"]["state_risk_register"] == 3
    assert [a[0] for a in patch.auditor] == ["STATE_RISK_DEMO_PURGED"]


def test_purge_state_risk_demo_surfaces_error(patch):
    patch.config["raise_on"] = True

    result = _run(purge_state_risk_demo_data(ACTOR))

    assert result["success"] is False
    assert str(result["details"]["state_risk_register"]).startswith("Error")
    assert patch.auditor[-1][0] == "STATE_RISK_DEMO_PURGED"
    assert patch.auditor[-1][3] == "error"


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_granular_purge_endpoints_registered():
    from app.routes.admin import router

    paths = [getattr(r, "path", None) for r in router.routes]
    assert "/psoe/purge" in paths
    assert "/state-risk/purge" in paths