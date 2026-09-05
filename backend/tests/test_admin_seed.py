"""Super-Admin web seeding panel tests.

Covers the production_seed service (regulator/tenant creation, bulk import,
audit logs), tenant lifecycle status, and the /api/v1/admin/* routes
(SUPER_ADMIN authz + setup-key gate).

Operational dummy-data seeding now runs against PostgreSQL via the Step-5
tool (is_demo=true); the old Firestore-subcollection writer tests were
dropped, so this module focuses on the Firestore-backed identity/status logic.
"""

from datetime import datetime, timezone

import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_admin_user, get_current_user


# ============================================================================
# Fake Firestore (top-level collections + tenant subcollections)
# ============================================================================

class _SubRef:
    def __init__(self, db, tid, sub, doc):
        self._db = db
        self._tid = tid
        self._sub = sub
        self._doc = doc
        self.id = doc.get("id") or "sub-doc"

    def delete(self):
        items = self._db._subs.get((self._tid, self._sub), [])
        if self._doc in items:
            items.remove(self._doc)

    def collection(self, sub):
        return _FakeSubColl(self._db, self.id, sub)


class _SubSnap:
    def __init__(self, db, tid, sub, doc):
        self._db = db
        self._tid = tid
        self._sub = sub
        self._doc = doc
        self.id = doc.get("id") or "sub-doc"
        self.exists = True
        self.reference = _SubRef(db, tid, sub, doc)

    def to_dict(self):
        return self._doc


class _FakeRef:
    def __init__(self, db, name, doc_id):
        self._db = db
        self._name = name
        self.id = doc_id

    def get(self):
        store = self._db._store_for(self._name)
        if self.id in store:
            return _Snap(dict(store[self.id]), self._db, self._name, self.id, exists=True, ref=self)
        return _Snap({}, self._db, self._name, self.id, exists=False, ref=self)

    def set(self, data, merge=False):
        store = self._db._store_for(self._name)
        if merge and self.id in store:
            merged = dict(store[self.id])
            merged.update(data)
            store[self.id] = merged
        else:
            store[self.id] = dict(data)
        return self

    def delete(self):
        self._db._store_for(self._name).pop(self.id, None)

    def collection(self, sub):
        return _FakeSubColl(self._db, self.id, sub)


class _Snap:
    def __init__(self, data, db, name, doc_id, exists=True, ref=None):
        self._data = data or {}
        self._db = db
        self._name = name
        self.id = self._data.get("id") or doc_id
        self.exists = exists
        self.reference = ref or _FakeRef(db, name, doc_id)

    def to_dict(self):
        return self._data


class _QueryResult:
    def __init__(self, items):
        self._items = items

    def get(self):
        return self._items

    def limit(self, n):
        self._items = self._items[:n]
        return self


class _FakeSubColl:
    def __init__(self, db, tid, sub):
        self._db = db
        self._tid = tid
        self._sub = sub

    def add(self, doc):
        self._db._subs.setdefault((self._tid, self._sub), []).append(dict(doc))
        ref = _FakeRef(self._db, f"sub:{self._tid}/{self._sub}", len(self._db._subs[(self._tid, self._sub)]) - 1)
        return (None, ref)

    def get(self):
        return [_SubSnap(self._db, self._tid, self._sub, d)
                for d in self._db._subs.get((self._tid, self._sub), [])]

    def where(self, field, op, value):
        items = [_SubSnap(self._db, self._tid, self._sub, d)
                 for d in self._db._subs.get((self._tid, self._sub), [])
                 if d.get(field) == value]
        return _QueryResult(items)

    def limit(self, n):
        return _QueryResult([_SubSnap(self._db, self._tid, self._sub, d)
                             for d in self._db._subs.get((self._tid, self._sub), [])][:n])

    def document(self, doc_id):
        store = self._db._subs.get((self._tid, self._sub))
        if not isinstance(store, dict):
            store = {}
            self._db._subs[(self._tid, self._sub)] = store
        return _SubDocRef(store, doc_id)

    def get_docs(self):
        store = self._db._subs.get((self._tid, self._sub))
        return store if isinstance(store, dict) else {}


class _SubDocRef:
    def __init__(self, store, doc_id):
        self._store = store
        self._id = doc_id

    def set(self, data):
        self._store[self._id] = dict(data)
        return self

    def limit(self, n):
        return _QueryResult([_SubSnap(self._db, self._tid, self._sub, d)
                             for d in self._db._subs.get((self._tid, self._sub), [])][:n])


class _FakeColl:
    def __init__(self, db, name):
        self._db = db
        self._name = name

    def document(self, doc_id):
        return _FakeRef(self._db, self._name, doc_id)

    def add(self, doc):
        ref = _FakeRef(self._db, self._name, f"{self._name}-{len(self._db._store_for(self._name))}")
        ref.set(doc)
        return ref

    def get(self):
        store = self._db._store_for(self._name)
        return [_Snap(dict(d), self._db, self._name, k, ref=_FakeRef(self._db, self._name, k))
                for k, d in store.items()]

    def where(self, field, op, value):
        store = self._db._store_for(self._name)
        return _QueryResult([_Snap(dict(d), self._db, self._name, k, ref=_FakeRef(self._db, self._name, k))
                             for k, d in store.items() if d.get(field) == value])

    def order_by(self, field, direction="ASCENDING"):
        items = []
        for k, d in self._db._store_for(self._name).items():
            snap = _Snap(dict(d), self._db, self._name, k, ref=_FakeRef(self._db, self._name, k))
            items.append(snap)
        items.sort(key=lambda s: (s.to_dict().get(field) or ""), reverse=(direction == "DESCENDING"))
        return _QueryResult(items)


class _FakeDB:
    def __init__(self):
        self._stores = {"regulators": {}, "tenants": {}, "audit_logs": {}}
        self._subs = {}

    def _store_for(self, name):
        if name not in self._stores:
            self._stores[name] = {}
        return self._stores[name]

    def collection(self, name):
        return _FakeColl(self, name)

    def collection_group(self, name):
        items = []
        for (tid, sub), docs in self._subs.items():
            if sub == name:
                for d in docs:
                    items.append(_SubSnap(self, tid, sub, d))
        return _QueryResult(items)


def _patch_db(monkeypatch, db=None):
    db = db or _FakeDB()
    monkeypatch.setattr("app.services.production_seed.get_db", lambda: db)
    monkeypatch.setattr("app.services.admin_data_service.get_db", lambda: db)
    monkeypatch.setattr("app.services.seed_surfaces.get_db", lambda: db)
    return db


def _patch_secret(monkeypatch, value="test-setup-key"):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SETUP_SECRET", value, raising=False)


def _admin_user(role="SUPER_ADMIN"):
    return {"uid": "super-1", "email": "super-admin@aviasafesystems.com", "role": role, "tenant_id": None}


# ============================================================================
# Service-level
# ============================================================================

def test_create_regulator_success(monkeypatch):
    db = _patch_db(monkeypatch)
    from app.services.production_seed import create_regulator
    doc = create_regulator({
        "id": "dgca", "name": "Directorate General of Civil Aviation",
        "country": "IN", "country_name": "India", "operator_tenant_ids": ["ind-air1"],
    }, _admin_user())
    assert doc["id"] == "dgca"
    assert doc["short_name"] == "DGCA"
    stored = db._stores["regulators"]["dgca"]
    assert stored["name"] == "Directorate General of Civil Aviation"
    assert stored["operator_tenant_ids"] == ["ind-air1"]
    logs = db._stores["audit_logs"]
    assert any(l["action"] == "REGULATOR_CREATED" for l in logs.values())


def test_create_regulator_duplicate(monkeypatch):
    db = _patch_db(monkeypatch)
    db._stores["regulators"]["caan"] = {"id": "caan", "name": "CAAN"}
    from app.services.production_seed import create_regulator
    try:
        create_regulator({"id": "caan", "name": "Civil Aviation Authority of Nepal"}, _admin_user())
        assert False, "expected ValueError"
    except ValueError as e:
        assert "already exists" in str(e)


def test_create_regulator_invalid_id(monkeypatch):
    _patch_db(monkeypatch)
    from app.services.production_seed import create_regulator
    try:
        create_regulator({"id": "Bad ID", "name": "X"}, _admin_user())
        assert False, "expected ValueError"
    except ValueError as e:
        assert "must be lowercase" in str(e)


def test_create_tenant_success(monkeypatch):
    db = _patch_db(monkeypatch)
    from app.services.production_seed import create_tenant
    doc = create_tenant({
        "tenant_id": "ind-air1", "name": "IndiAir", "icao": "INA",
        "regulator_id": "dgca", "country": "India",
    }, _admin_user())
    stored = db._stores["tenants"]["ind-air1"]
    assert stored["regulator_id"] == "dgca"
    assert stored["name"] == "IndiAir"
    assert any(l["action"] == "TENANT_CREATED" for l in db._stores["audit_logs"].values())


def test_create_tenant_duplicate(monkeypatch):
    db = _patch_db(monkeypatch)
    db._stores["tenants"]["sita-air"] = {"tenant_id": "sita-air", "name": "Sita Air"}
    from app.services.production_seed import create_tenant
    try:
        create_tenant({"tenant_id": "sita-air", "name": "Sita Air"}, _admin_user())
        assert False, "expected ValueError"
    except ValueError as e:
        assert "already exists" in str(e)


def test_bulk_create_tenants_json(monkeypatch):
    db = _patch_db(monkeypatch)
    from app.services.production_seed import bulk_create_tenants
    result = bulk_create_tenants([
        {"tenant_id": "a-air", "name": "A Air"},
        {"tenant_id": "b-air", "name": "B Air"},
        {"tenant_id": "a-air", "name": "Dup"},  # duplicate -> error
    ], _admin_user())
    assert result["ok"] == 2
    assert result["total"] == 3
    assert db._stores["tenants"].keys() >= {"a-air", "b-air"}


def test_list_audit_logs(monkeypatch):
    db = _patch_db(monkeypatch)
    from app.services.production_seed import _audit, list_audit_logs
    for i in range(3):
        _audit("SEED_PREVIEW", _admin_user(), "caan", f"entry {i}")
    logs = list_audit_logs(limit=10)
    assert len(logs) == 3
    assert logs[0]["action"] == "SEED_PREVIEW"


def test_list_tenants_admin_counts(monkeypatch):
    db = _patch_db(monkeypatch)
    db._stores["tenants"]["tara-air"] = {"tenant_id": "tara-air", "name": "Tara Air"}
    db._subs[("tara-air", "surveys")] = [{"x": 1}, {"x": 2}]
    from app.services.production_seed import list_tenants_admin
    rows = list_tenants_admin()
    assert rows[0]["counts"]["surveys"] == 2


# ============================================================================
# Route-level
# ============================================================================

def _client(user=None):
    app.dependency_overrides[get_admin_user] = lambda: user or _admin_user()
    return TestClient(app)


def test_admin_routes_require_token():
    # No override -> real get_current_user -> 401/403
    resp = TestClient(app).get("/api/v1/admin/seed/logs")
    assert resp.status_code in (401, 403)


def test_admin_routes_403_non_super(monkeypatch):
    _patch_db(monkeypatch)
    # Override the *underlying* get_current_user so get_admin_user's real check
    # runs and rejects a non-SUPER_ADMIN role.
    app.dependency_overrides[get_current_user] = lambda: _admin_user(role="AIRLINE_ADMIN")
    try:
        resp = TestClient(app).get("/api/v1/admin/seed/logs")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert resp.status_code == 403


def test_admin_create_regulator_route(monkeypatch):
    _patch_db(monkeypatch)
    _patch_secret(monkeypatch)
    resp = _client().post("/api/v1/admin/regulators", json={
        "setup_key": "test-setup-key",
        "regulator": {"id": "caan", "name": "Civil Aviation Authority of Nepal",
                      "country": "NP", "country_name": "Nepal"},
    })
    assert resp.status_code == 200
    assert resp.json()["regulator"]["id"] == "caan"


def test_admin_create_regulator_wrong_key(monkeypatch):
    _patch_db(monkeypatch)
    _patch_secret(monkeypatch)
    resp = _client().post("/api/v1/admin/regulators", json={
        "setup_key": "wrong", "regulator": {"id": "caan", "name": "CAAN"},
    })
    assert resp.status_code == 403


def test_admin_seed_logs_route(monkeypatch):
    db = _patch_db(monkeypatch)
    from app.services.production_seed import _audit
    _audit("SEED_PREVIEW", _admin_user(), "caan", "hello")
    resp = _client().get("/api/v1/admin/seed/logs?limit=5")
    assert resp.status_code == 200
    assert len(resp.json()["logs"]) == 1


def test_admin_bulk_tenants_csv_route(monkeypatch):
    db = _patch_db(monkeypatch)
    _patch_secret(monkeypatch)
    csv_text = "tenant_id,name,icao,country,regulator_id\nx-air,X Air,XA,Nepal,caan\ny-air,Y Air,YA,Nepal,caan\n"
    resp = _client().post("/api/v1/admin/tenants/bulk", json={"setup_key": "test-setup-key", "csv": csv_text})
    assert resp.status_code == 200
    assert resp.json()["ok"] == 2
    assert "x-air" in db._stores["tenants"]


def test_admin_list_tenants_route(monkeypatch):
    db = _patch_db(monkeypatch)
    db._stores["tenants"]["tara-air"] = {"tenant_id": "tara-air", "name": "Tara Air"}
    resp = _client().get("/api/v1/admin/tenants")
    assert resp.status_code == 200
    assert resp.json()["tenants"][0]["id"] == "tara-air"


# ============================================================================
# Tenant lifecycle status (admin_data_service)
# ============================================================================

def _seed_tenant(db, tid="tara-air", **extra):
    doc = {"tenant_id": tid, "name": "Tara Air", "active": True}
    doc.update(extra)
    db._stores["tenants"][tid] = doc
    return doc


def test_derive_tenant_status_explicit():
    from app.services.admin_data_service import derive_tenant_status
    assert derive_tenant_status({}, None, explicit="Trial") == "TRIAL"
    assert derive_tenant_status({}, None, explicit="Inactive") == "INACTIVE"
    assert derive_tenant_status({}, None, explicit="demo") == "DEMO"


def test_derive_tenant_status_unpaid_is_inactive():
    from app.services.admin_data_service import derive_tenant_status
    assert derive_tenant_status({}, "Unpaid") == "INACTIVE"


def test_derive_tenant_status_expired_contract():
    from datetime import date, timedelta
    from app.services.admin_data_service import derive_tenant_status
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert derive_tenant_status({"end_date": yesterday}, "paid") == "INACTIVE"


def test_derive_tenant_status_future_contract_is_trial():
    from datetime import date, timedelta
    from app.services.admin_data_service import derive_tenant_status
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert derive_tenant_status({"start_date": tomorrow}, "Paid") == "TRIAL"


def test_update_tenant_status_explicit(monkeypatch):
    db = _patch_db(monkeypatch)
    _seed_tenant(db)
    from app.services.admin_data_service import update_tenant_status
    doc = update_tenant_status("tara-air", _admin_user(), status="Trial")
    stored = db._stores["tenants"]["tara-air"]
    assert stored["status"] == "TRIAL"
    assert stored["active"] is False
    assert any(l["action"] == "TENANT_STATUS_UPDATED" for l in db._stores["audit_logs"].values())
    assert doc["status"] == "TRIAL"


def test_update_tenant_status_derived_from_contract(monkeypatch):
    from datetime import date, timedelta
    db = _patch_db(monkeypatch)
    _seed_tenant(db)
    from app.services.admin_data_service import update_tenant_status
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    next_year = (date.today() + timedelta(days=366)).isoformat()
    update_tenant_status("tara-air", _admin_user(),
                         contract_start_date=tomorrow, contract_end_date=next_year)
    stored = db._stores["tenants"]["tara-air"]
    # Contract starts in the future -> Trial
    assert stored["status"] == "TRIAL"
    assert stored["contract"]["start_date"] == tomorrow
    assert stored["contract"]["end_date"] == next_year


def test_update_tenant_status_demo_with_trial_end(monkeypatch):
    db = _patch_db(monkeypatch)
    _seed_tenant(db)
    from app.services.admin_data_service import update_tenant_status
    doc = update_tenant_status("tara-air", _admin_user(), status="demo",
                               payment_status="Not Applicable", trial_end_date="2026-09-30")
    stored = db._stores["tenants"]["tara-air"]
    assert stored["status"] == "DEMO"
    assert stored["active"] is False
    assert stored["payment_status"] == "not_applicable"
    assert stored["contract"]["trial_end_date"] == "2026-09-30"
    assert doc["status"] == "DEMO"


def test_update_tenant_status_unpaid(monkeypatch):
    db = _patch_db(monkeypatch)
    _seed_tenant(db)
    from app.services.admin_data_service import update_tenant_status
    update_tenant_status("tara-air", _admin_user(), payment_status="Unpaid")
    assert db._stores["tenants"]["tara-air"]["status"] == "INACTIVE"
    assert db._stores["tenants"]["tara-air"]["payment_status"] == "unpaid"


def test_update_tenant_status_missing_tenant(monkeypatch):
    _patch_db(monkeypatch)
    from app.services.admin_data_service import update_tenant_status
    try:
        update_tenant_status("nope", _admin_user(), status="Active")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "not found" in str(e)


def test_admin_tenant_status_route(monkeypatch):
    db = _patch_db(monkeypatch)
    _patch_secret(monkeypatch)
    _seed_tenant(db)
    resp = _client().post("/api/v1/admin/tenants/tara-air/status", json={
        "setup_key": "test-setup-key",
        "status": "Inactive",
        "contract_start_date": "2026-01-01",
        "contract_end_date": "2026-12-31",
        "payment_status": "Paid",
    })
    assert resp.status_code == 200
    assert resp.json()["tenant"]["status"] == "INACTIVE"
    assert db._stores["tenants"]["tara-air"]["active"] is False


def test_admin_tenant_status_route_bad_key(monkeypatch):
    db = _patch_db(monkeypatch)
    _patch_secret(monkeypatch)
    _seed_tenant(db)
    resp = _client().post("/api/v1/admin/tenants/tara-air/status", json={
        "setup_key": "wrong", "status": "Active",
    })
    assert resp.status_code == 403


def test_update_tenant_modules_service(monkeypatch):
    db = _patch_db(monkeypatch)
    _seed_tenant(db)
    from app.services.admin_data_service import update_tenant_modules
    doc = update_tenant_modules("tara-air", _admin_user(), {
        "module1": True, "module2": "yes", "module3": 0, "module4": False, "junk": True,
    })
    stored = db._stores["tenants"]["tara-air"]
    assert stored["modules"] == {"module1": True, "module2": True, "module3": False, "module4": False}
    assert any(l["action"] == "TENANT_MODULES_UPDATED" for l in db._stores["audit_logs"].values())
    assert doc["modules"]["module1"] is True


def test_update_tenant_modules_missing_tenant(monkeypatch):
    _patch_db(monkeypatch)
    from app.services.admin_data_service import update_tenant_modules
    try:
        update_tenant_modules("nope", _admin_user(), {"module1": True})
        assert False, "expected ValueError"
    except ValueError as e:
        assert "not found" in str(e)


def test_admin_tenant_modules_route(monkeypatch):
    db = _patch_db(monkeypatch)
    _patch_secret(monkeypatch)
    _seed_tenant(db)
    resp = _client().post("/api/v1/admin/tenants/tara-air/modules", json={
        "setup_key": "test-setup-key",
        "modules": {"module1": True, "module2": False, "module3": True, "module4": True},
    })
    assert resp.status_code == 200
    assert resp.json()["tenant"]["modules"]["module3"] is True
    assert db._stores["tenants"]["tara-air"]["modules"]["module2"] is False
    assert any(l["action"] == "TENANT_MODULES_UPDATED" for l in db._stores["audit_logs"].values())


def test_admin_tenant_modules_route_bad_key(monkeypatch):
    db = _patch_db(monkeypatch)
    _patch_secret(monkeypatch)
    _seed_tenant(db)
    resp = _client().post("/api/v1/admin/tenants/tara-air/modules", json={
        "setup_key": "wrong",
        "modules": {"module1": True},
    })
    assert resp.status_code == 403


def test_admin_tenant_modules_route_missing_tenant(monkeypatch):
    _patch_db(monkeypatch)
    _patch_secret(monkeypatch)
    resp = _client().post("/api/v1/admin/tenants/nope/modules", json={
        "setup_key": "test-setup-key",
        "modules": {"module1": True},
    })
    assert resp.status_code == 404


def test_seed_psoe_tenant_writes_baselines(monkeypatch):
    db = _patch_db(monkeypatch)
    _seed_tenant(db)
    from app.services.seed_surfaces import seed_psoe_tenant
    result = asyncio.run(seed_psoe_tenant("tara-air", _admin_user(), force=False))
    assert "assessments" in result
    ids = [a["id"] for a in result["assessments"]]
    assert "tara-air-baseline-completed" in ids
    assert "tara-air-baseline-draft" in ids
    docs = db._stores["psoe_assessments"]
    assert len(docs) == 2
    with_tenant = [v for v in docs.values() if v.get("tenant_id") == "tara-air"]
    assert len(with_tenant) == 2
    statuses = [v.get("status") for v in with_tenant]
    assert "completed" in statuses and "draft" in statuses


def test_seed_psoe_requires_existing_tenant(monkeypatch):
    _patch_db(monkeypatch)
    from app.services.seed_surfaces import seed_psoe_tenant
    try:
        asyncio.run(seed_psoe_tenant("missing-air", _admin_user(), force=False))
        assert False, "expected ValueError"
    except ValueError as e:
        assert "not found" in str(e)


def test_seed_state_risk_reference(monkeypatch):
    db = _patch_db(monkeypatch)
    from app.services.seed_surfaces import ICAO_TOP_RISK_CATEGORIES, seed_state_risk_reference
    result = asyncio.run(seed_state_risk_reference(_admin_user()))
    assert result["categories"] == len(ICAO_TOP_RISK_CATEGORIES)
    store = db._subs.get(("icao_top_risks", "categories"))
    assert isinstance(store, dict) and len(store) == len(ICAO_TOP_RISK_CATEGORIES)


def test_admin_psoe_route_seeds(monkeypatch):
    db = _patch_db(monkeypatch)
    _patch_secret(monkeypatch)
    _seed_tenant(db)
    resp = _client().post("/api/v1/admin/psoe", json={
        "setup_key": "test-setup-key", "all": True, "force": False,
    })
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["tenant_id"] == "tara-air"
    assert len(results[0]["assessments"]) == 2


def test_admin_psoe_route_single_tenant(monkeypatch):
    db = _patch_db(monkeypatch)
    _patch_secret(monkeypatch)
    _seed_tenant(db)
    resp = _client().post("/api/v1/admin/psoe", json={
        "setup_key": "test-setup-key", "all": False, "tenant_ids": ["tara-air"],
    })
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 1


def test_admin_psoe_route_no_tenants(monkeypatch):
    _patch_db(monkeypatch)
    _patch_secret(monkeypatch)
    resp = _client().post("/api/v1/admin/psoe", json={
        "setup_key": "test-setup-key", "all": True,
    })
    assert resp.status_code == 400


def test_admin_psoe_route_bad_key(monkeypatch):
    db = _patch_db(monkeypatch)
    _patch_secret(monkeypatch)
    _seed_tenant(db)
    resp = _client().post("/api/v1/admin/psoe", json={
        "setup_key": "wrong", "all": True,
    })
    assert resp.status_code == 403


def test_admin_state_risk_route(monkeypatch):
    db = _patch_db(monkeypatch)
    _patch_secret(monkeypatch)
    resp = _client().post("/api/v1/admin/state-risk", json={"setup_key": "test-setup-key"})
    assert resp.status_code == 200
    from app.services.seed_surfaces import ICAO_TOP_RISK_CATEGORIES
    assert resp.json()["categories"] == len(ICAO_TOP_RISK_CATEGORIES)


def test_admin_state_risk_route_bad_key(monkeypatch):
    _patch_db(monkeypatch)
    _patch_secret(monkeypatch)
    resp = _client().post("/api/v1/admin/state-risk", json={"setup_key": "wrong"})
    assert resp.status_code == 403

