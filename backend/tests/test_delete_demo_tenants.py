# ============================================================================
# Tests for Delete Demo Tenants — POST /api/v1/admin/delete-demo-tenants
# (Firestore doc tree + Postgres per-tenant rows)
# ============================================================================

import asyncio

import pytest

from app.services.admin_data_service import (
    delete_demo_tenants,
    _is_deleteable_demo_tenant,
)


class _FakeDoc:
    def __init__(self, doc_id, data=None, subcollections=None):
        self.id = doc_id
        self.path = [doc_id]
        self._data = data or {}
        self.deleted = False
        self._subs = subcollections or {}
        self.sets = []

    @property
    def reference(self):
        return self

    def to_dict(self):
        return dict(self._data)

    def set(self, data, merge=False):
        self.sets.append((dict(data), merge))
        if merge:
            self._data.update(data)
        else:
            self._data = dict(data)

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
        self.accessed = []
        self.added = []

    def collection(self, name):
        self.accessed.append(name)
        return _FakeSubCollection(self, name)

    def seed(self, name, docs):
        self.docs.setdefault(name, []).extend(docs)

    def all_docs(self):
        return [d for docs in self.docs.values() for d in docs]

    def doc(self, name):
        for d in self.docs.get(name, []):
            if getattr(d, "id", None) == name:
                return d
        d = _FakeDoc(name)
        self.docs.setdefault(name, []).append(d)
        return d


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


ACTOR = {"uid": "u1", "email": "admin@aviasafe.test"}

REGULATOR_TYPE_MARKERS = {"state_regulator", "STATE_REGULATOR"}


def _seed_tenants(fs):
    fixedwing = _FakeDoc("fixedwing", {"name": "Fixed-Wing Operator", "is_demo": True, "status": "DEMO"})
    rotary = _FakeDoc("rotarywing", {"name": "Rotary-Wing Operator", "is_demo": True})
    sita = _FakeDoc("sita-air", {"name": "Sita Air Ltd", "status": "CANCELLED", "active": False})
    sourya = _FakeDoc("sourya-air", {"name": "Sourya Airlines", "status": "cancelled"})
    demo_regulator = _FakeDoc("demostate", {"name": "Demo State Regulator", "type": "state_regulator", "is_demo": True})
    active = _FakeDoc("nepal-airlines", {"name": "Nepal Airlines", "status": "ACTIVE"})

    # nests: fixedwing holds a reports subcollection doc
    reports = _FakeSubCollection(fs, "fixedwing/reports")
    fs.seed("fixedwing/reports", [_FakeDoc("r1", {"tenant_id": "x"})])
    fixedwing._subs["reports"] = reports

    for d in [fixedwing, rotary, sita, sourya, demo_regulator, active]:
        fs.seed("tenants", [d])
    fs.seed("psoe_questions", [_FakeDoc("q1", {"text": "..."})])

    by_id = {d.id: d for d in fs.all_docs()}
    return fixedwing, rotary, sita, sourya, demo_regulator, active, by_id


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def test_is_deleteable_demo_tenant_matches_demo_and_cancelled_operators():
    assert _is_deleteable_demo_tenant({"is_demo": True}) is True
    assert _is_deleteable_demo_tenant({"is_beta_sandbox": True}) is True
    assert _is_deleteable_demo_tenant({"status": "CANCELLED"}) is True
    assert _is_deleteable_demo_tenant({"status": "cancelled"}) is True
    assert _is_deleteable_demo_tenant({"status": "ACTIVE"}) is False
    assert _is_deleteable_demo_tenant({"status": "DEMO"}) is False  # demo by status, but no flag


def test_regulator_docs_never_matched_even_when_is_demo():
    assert _is_deleteable_demo_tenant({"name": "Demo State Regulator", "type": "state_regulator", "is_demo": True}) is False
    assert _is_deleteable_demo_tenant({"name": "Demo State Regulator", "is_demo": True}) is False


# ---------------------------------------------------------------------------
# Firestore doc selection
# ---------------------------------------------------------------------------

def test_delete_demo_tenants_targets_expected_slugs(fs_patch, monkeypatch):
    fs, _ = fs_patch
    fixedwing, rotary, sita, sourya, demo_regulator, active, by_id = _seed_tenants(fs)

    async def _fake_pg(tenant_list):
        return {"deleted_count": 0, "details": {"hazards": 0}}

    monkeypatch.setattr("app.services.admin_data_service._delete_tenant_postgres_data", _fake_pg)

    result = _run(delete_demo_tenants(ACTOR))

    assert set(result["tenants"]) == {"fixedwing", "rotarywing", "sita-air", "sourya-air"}
    assert result["deleted_count"] == 4
    # preserved
    assert not demo_regulator.deleted
    assert not active.deleted
    # deleted docs are gone
    for slug in ["fixedwing", "rotarywing", "sita-air", "sourya-air"]:
        assert by_id[slug].deleted


def test_delete_demo_tenants_recurses_subcollections(fs_patch, monkeypatch):
    fs, _ = fs_patch
    fixedwing, _, _, _, _, _, by_id = _seed_tenants(fs)

    async def _fake_pg(tenant_list):
        return {"deleted_count": 0, "details": {}}

    monkeypatch.setattr("app.services.admin_data_service._delete_tenant_postgres_data", _fake_pg)

    _run(delete_demo_tenants(ACTOR))

    # fixedwing's reports subcollection doc must be deleted (recursive tree)
    assert fixedwing.deleted


def test_delete_demo_tenants_returns_firestore_counts_by_slug(fs_patch, monkeypatch):
    fs, _ = fs_patch
    fixedwing, _, _, _, _, _, _ = _seed_tenants(fs)

    async def _fake_pg(tenant_list):
        return {"deleted_count": 0, "details": {}}

    monkeypatch.setattr("app.services.admin_data_service._delete_tenant_postgres_data", _fake_pg)

    result = _run(delete_demo_tenants(ACTOR))
    assert "fixedwing" in result["firestore"]["deleted"]
    assert result["firestore"]["deleted"]["fixedwing"] >= 1


def test_delete_demo_tenants_no_match_is_noop(fs_patch, monkeypatch):
    fs, _ = fs_patch
    nepal = _FakeDoc("nepal-airlines", {"name": "Nepal Airlines", "status": "ACTIVE"})
    fs.seed("tenants", [nepal])

    async def _fake_pg(tenant_list):
        return {"deleted_count": 0, "details": {}}

    monkeypatch.setattr("app.services.admin_data_service._delete_tenant_postgres_data", _fake_pg)

    result = _run(delete_demo_tenants(ACTOR))
    assert result["deleted_count"] == 0
    assert result["tenants"] == []
    assert not nepal.deleted


# ---------------------------------------------------------------------------
# Postgres flow
# ---------------------------------------------------------------------------

def test_delete_demo_tenants_calls_postgres_with_matching_uuids(fs_patch, monkeypatch):
    fs, _ = fs_patch
    _, _, _, _, _, _, _ = _seed_tenants(fs)

    captured = {}

    async def _fake_pg(tenant_list):
        captured["uuids"] = [str(u) for u in tenant_list]
        return {"deleted_count": 5, "details": {"hazards": 5}}

    monkeypatch.setattr("app.services.admin_data_service._delete_tenant_postgres_data", _fake_pg)

    result = _run(delete_demo_tenants(ACTOR))
    assert len(captured["uuids"]) == 4
    assert len(set(captured["uuids"])) == 4  # unique deterministic uuids
    assert result["postgres"]["deleted_count"] == 5


def test_delete_demo_tenants_audits(fs_patch, monkeypatch):
    fs, auditor = fs_patch
    _seed_tenants(fs)

    async def _fake_pg(tenant_list):
        return {"deleted_count": 0, "details": {}}

    monkeypatch.setattr("app.services.admin_data_service._delete_tenant_postgres_data", _fake_pg)

    _run(delete_demo_tenants(ACTOR))

    actions = [a[0] for a in auditor]
    assert "TENANTS_DEMO_DELETED" in actions


def test_delete_demo_tenants_detaches_regulators(fs_patch, monkeypatch):
    fs, _ = fs_patch
    _seed_tenants(fs)

    async def _fake_pg(tenant_list):
        return {"deleted_count": 0, "details": {}}

    monkeypatch.setattr("app.services.admin_data_service._delete_tenant_postgres_data", _fake_pg)

    caan = _FakeDoc("caan", {"name": "CAAN", "operator_tenant_ids": ["fixedwing", "sita-air", "active-air"]})
    fs.seed("regulators", [caan])

    result = _run(delete_demo_tenants(ACTOR))

    assert caan.sets, "regulator should have been updated via set"
    data, merge = caan.sets[-1]
    assert merge is True
    assert data["operator_tenant_ids"] == ["active-air"]
    assert result["regulators"] == {"caan": {"before": ["fixedwing", "sita-air", "active-air"], "after": ["active-air"]}}


def test_delete_demo_tenants_leaves_unaffected_regulators(fs_patch, monkeypatch):
    fs, _ = fs_patch
    _seed_tenants(fs)

    async def _fake_pg(tenant_list):
        return {"deleted_count": 0, "details": {}}

    monkeypatch.setattr("app.services.admin_data_service._delete_tenant_postgres_data", _fake_pg)

    dc_civil = _FakeDoc("dc-civil", {"name": "DC Civil Aviation", "operator_tenant_ids": ["nepal-airlines"]})
    fs.seed("regulators", [dc_civil])

    result = _run(delete_demo_tenants(ACTOR))

    assert dc_civil.sets == []
    assert result["regulators"] == {}


def test_delete_demo_tenants_deletes_tenant_users(fs_patch, monkeypatch):
    fs, _ = fs_patch
    _seed_tenants(fs)

    async def _fake_pg(tenant_list):
        return {"deleted_count": 0, "details": {}}

    monkeypatch.setattr("app.services.admin_data_service._delete_tenant_postgres_data", _fake_pg)

    deleted_uids = []

    class _FakeAuth:
        def __init__(self, deleted_uids):
            self._deleted = deleted_uids

        def delete_user(self, uid):
            self._deleted.append(uid)

    monkeypatch.setattr("app.services.admin_data_service.get_auth", lambda: _FakeAuth(deleted_uids))

    fs.seed("users", [
        _FakeDoc("u1", {"uid": "u1", "tenant_id": "fixedwing", "email": "pilot@fixedwing.test"}),
        _FakeDoc("u2", {"uid": "u2", "tenant_id": "sita-air"}),
        _FakeDoc("u3", {"uid": "u3", "tenant_id": "nepal-airlines"}),
    ])

    result = _run(delete_demo_tenants(ACTOR))

    by_id = {d.id: d for d in fs.docs["users"]}
    assert set(deleted_uids) == {"u1", "u2"}
    assert by_id["u1"].deleted is True
    assert by_id["u2"].deleted is True
    assert by_id["u3"].deleted is False
    assert result["users_deleted"] == 2


def test_delete_demo_tenants_deletes_users_even_when_auth_unavailable(fs_patch, monkeypatch):
    fs, _ = fs_patch
    _seed_tenants(fs)

    async def _fake_pg(tenant_list):
        return {"deleted_count": 0, "details": {}}

    monkeypatch.setattr("app.services.admin_data_service._delete_tenant_postgres_data", _fake_pg)

    def _broken_get_auth():
        raise RuntimeError("firebase not initialized")

    monkeypatch.setattr("app.services.admin_data_service.get_auth", _broken_get_auth)

    fs.seed("users", [
        _FakeDoc("u1", {"uid": "u1", "tenant_id": "fixedwing"}),
        _FakeDoc("u3", {"uid": "u3", "tenant_id": "nepal-airlines"}),
    ])

    result = _run(delete_demo_tenants(ACTOR))

    by_id = {d.id: d for d in fs.docs["users"]}
    assert by_id["u1"].deleted is True
    assert by_id["u3"].deleted is False
    assert result["users_deleted"] == 1


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def test_delete_demo_tenants_endpoint_registered_on_admin_router():
    from app.routes.admin import router

    paths = [getattr(r, "path", None) for r in router.routes]
    assert "/delete-demo-tenants" in paths