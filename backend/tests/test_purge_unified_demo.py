# ============================================================================
# Tests for the Unified Purge — POST /api/v1/admin/purge-unified-demo
# (Postgres is_demo rows + Firestore setup surfaces)
# ============================================================================

import asyncio

import pytest

from app.services.admin_data_service import (
    purge_all_demo_data_unified,
    purge_firestore_demo_data,
)


class _FakeDoc:
    def __init__(self, doc_id, data=None, subcollections=None):
        self.id = doc_id
        self.path = [doc_id]
        self._data = data or {}
        self.deleted = False
        self._subs = subcollections or {}

    @property
    def reference(self):
        return self

    def to_dict(self):
        return dict(self._data)

    def delete(self):
        self.deleted = True

    def collections(self):
        return list(self._subs.values())


class _FakeSubCollection:
    def __init__(self, db, name):
        self._db = db
        self.name = name

    def get(self):
        return list(self._db.docs.get(self.name, []))

    def add(self, data):
        self._db.added.append(data)
        doc = _FakeDoc(f"auto-{len(self._db.added)}", data)
        self._db.seed(self.name, [doc])
        return doc


class _FakeFirestore:
    def __init__(self):
        self.docs = {}
        self.accessed = []
        self.added = []

    def collection(self, name):
        self.accessed.append(name)
        return _FakeSubCollection(self, name)

    def seed(self, name, docs):
        for d in docs:
            if isinstance(d, _FakeDoc):
                self.docs.setdefault(name, []).append(d)

    def all_docs(self):
        return [d for docs in self.docs.values() for d in docs]


@pytest.fixture
def fs_patch(monkeypatch):
    fs = _FakeFirestore()

    auditor = []

    def fake_audit(action, actor, target, detail, result="success"):
        auditor.append((action, target, detail, result))

    monkeypatch.setattr("app.services.admin_data_service.get_db", lambda: fs)
    monkeypatch.setattr("app.services.admin_data_service._audit", fake_audit)
    return fs, auditor


def _run(coro):
    return asyncio.run(coro)


def _seed_demo_surfaces(fs):
    fs.seed("audit_logs", [
        _FakeDoc("audit-1", {"action": "TENANT_CREATED"}),
        _FakeDoc("audit-2", {"action": "DEMO_DATA_SEEDED"}),
        _FakeDoc("audit-3", {"action": "PSOE_SEEDED"}),
    ])
    fs.seed("psoe_assessments", [
        _FakeDoc("fixedwing-baseline-completed", {"created_by": "production-setup", "status": "completed"}),
        _FakeDoc("fixedwing-baseline-draft", {"created_by": "production-setup", "status": "draft"}),
        _FakeDoc("sita-baseline-completed", {}),  # id marker only
        _FakeDoc("real-assessment-1", {"created_by": "smd@caan.gov.np", "status": "active"}),
    ])
    state_doc = _FakeDoc("icao_top_risks", {"reference": "icao"})
    cats = _FakeSubCollection(fs, "state/icao_top_risks/categories")
    fs.seed("state", [state_doc])
    fs.seed("state/icao_top_risks/categories", [
        _FakeDoc("LOCI", {"category": "LOCI"}),
        _FakeDoc("CFIT", {"category": "CFIT"}),
    ])
    state_doc._subs = {"categories": cats}
    fs.seed("tenants", [_FakeDoc("fixedwing", {"name": "Fixed Wing"})])
    fs.seed("regulators", [_FakeDoc("caan", {"name": "CAAN"})])
    fs.seed("users", [_FakeDoc("u1", {"email": "a@b.c"})])
    fs.seed("psoe_questions", [_FakeDoc("q1", {"text": "..."})])
    return state_doc


# ---------------------------------------------------------------------------
# Endpoint registration
# ---------------------------------------------------------------------------

def test_unified_purge_endpoint_registered_on_admin_router():
    from app.routes.admin import router

    paths = {getattr(r, "path", None) for r in router.routes}
    assert "/purge-unified-demo" in paths


# ---------------------------------------------------------------------------
# Firestore purge
# ---------------------------------------------------------------------------

def test_firestore_purge_wipes_expected_surfaces(fs_patch):
    fs, _ = fs_patch
    state_doc = _seed_demo_surfaces(fs)

    result = _run(purge_firestore_demo_data({"uid": "u1", "email": "admin@aviasafe.test"}))

    assert result["deleted"] == {"audit_logs": 3, "psoe_assessments": 3, "state": 3}
    assert result["total"] == 9

    by_id = {d.id: d for d in fs.all_docs()}
    for doc_id in ["audit-1", "audit-2", "audit-3",
                   "fixedwing-baseline-completed", "fixedwing-baseline-draft",
                   "sita-baseline-completed", "icao_top_risks", "LOCI", "CFIT"]:
        assert by_id[doc_id].deleted, f"{doc_id} should have been deleted"
    assert not by_id["real-assessment-1"].deleted


def test_firestore_purge_preserves_identity_and_reference_collections(fs_patch):
    fs, _ = fs_patch
    _seed_demo_surfaces(fs)

    _run(purge_firestore_demo_data({"uid": "u1", "email": "admin@aviasafe.test"}))

    for name in ["tenants", "regulators", "users", "psoe_questions"]:
        assert name not in fs.accessed, f"{name} must never be touched by the demo purge"
        for doc in fs.docs.get(name, []):
            assert not doc.deleted, f"{name}/{doc.id} must be preserved"


def test_firestore_purge_writes_audit_entry(fs_patch):
    fs, auditor = fs_patch
    _seed_demo_surfaces(fs)

    _run(purge_firestore_demo_data({"uid": "u1", "email": "admin@aviasafe.test"}))

    actions = [a[0] for a in auditor]
    assert "DEMO_DATA_PURGE_FIRESTORE" in actions


# ---------------------------------------------------------------------------
# Unified purge (Postgres + Firestore together)
# ---------------------------------------------------------------------------

def test_unified_purge_sums_both_databases(fs_patch, monkeypatch):
    fs, auditor = fs_patch
    _seed_demo_surfaces(fs)

    async def _fake_postgres(actor):
        return {
            "success": True,
            "deleted_count": 42,
            "details": {"hazards": 10, "reports": 32},
        }

    monkeypatch.setattr(
        "app.services.admin_data_service.purge_all_demo_data", _fake_postgres
    )

    result = _run(purge_all_demo_data_unified({"uid": "u1", "email": "admin@aviasafe.test"}))

    assert result["success"] is True
    assert result["postgres"]["deleted_count"] == 42
    assert result["postgres"]["details"] == {"hazards": 10, "reports": 32}
    assert result["firestore"]["total"] == 9
    assert result["deleted_count"] == 51
    assert [a[0] for a in auditor] == ["DEMO_DATA_PURGE_FIRESTORE"]


def test_unified_purge_runs_firestore_before_postgres(fs_patch, monkeypatch):
    fs, _ = fs_patch
    _seed_demo_surfaces(fs)

    order = []

    async def _fake_postgres(actor):
        order.append("postgres")
        return {"success": True, "deleted_count": 1, "details": {}}

    original_fs = purge_firestore_demo_data

    async def _trace_firestore(actor):
        order.append("firestore")
        return await original_fs(actor)

    monkeypatch.setattr("app.services.admin_data_service.purge_all_demo_data", _fake_postgres)
    monkeypatch.setattr("app.services.admin_data_service.purge_firestore_demo_data", _trace_firestore)

    _run(purge_all_demo_data_unified({"uid": "u1", "email": "admin@aviasafe.test"}))

    assert order == ["firestore", "postgres"]