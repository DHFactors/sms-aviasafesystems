"""Departmental Admin (HOD) delegation — invite RBAC + department-scoped join.

Covers (2026-08):
  * POST /api/v1/auth/invite  — TENANT_ADMIN may invite DEPT_ADMIN/SAFETY_OFFICER/
    STAFF into any applicable department; DEPT_ADMIN may only invite STAFF into
    their own department (cross-department and escalation -> 403).
  * POST /api/v1/auth/join (alias of /join-team) — a department-scoped invite
    binds the invitee's department AND role directly from the invite document.
  * GET  /api/v1/tenants/{tenantId}/users — DEPT_ADMIN sees only their own
    department's members; TENANT_ADMIN sees everyone.
  * GET  /api/v1/auth/verify-invite — returns department + role for scoped invites.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user


# ============================================================================
# Fake Firebase storage + auth
# ============================================================================

class _Doc:
    def __init__(self, data, exists=True, id=None):
        self._data = data or {}
        self.exists = exists
        self.id = id

    def get(self, field, default=None):
        if field is None:
            return self._data
        return self._data.get(field, default)

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
        if isinstance(store, list):
            rows = []
            for i, data in enumerate(store):
                doc = dict(data or {})
                doc.setdefault("id", str(i))
                ok = True
                for field, op, value in self._filters:
                    if op == "==" and doc.get(field) != value:
                        ok = False
                if ok:
                    rows.append(_Doc(doc, exists=True, id=doc["id"]))
            return rows
        rows = []
        for key, data in store.items():
            doc = dict(data or {})
            doc.setdefault("id", key)
            ok = True
            for field, op, value in self._filters:
                if op == "==" and doc.get(field) != value:
                    ok = False
            if ok:
                rows.append(_Doc(doc, exists=True, id=key))
        return rows


class _CollRef:
    def __init__(self, db, name, key):
        self._db = db
        self._name = name
        self._key = key

    def get(self):
        store = self._db._store(self._name)
        data = store.get(self._key) if isinstance(store, dict) else None
        if data is None:
            return _Doc(None, exists=False, id=self._key)
        return _Doc(dict(data), exists=True, id=self._key)

    def set(self, data, merge=False):
        store = self._db._store(self._name)
        if not isinstance(store, dict):
            raise AssertionError(f"cannot set document in non-dict collection {self._name}")
        if merge and self._key in store:
            merged = dict(store[self._key])
            merged.update(dict(data))
            data = merged
        store[self._key] = dict(data)

    def update(self, data):
        store = self._db._store(self._name)
        merged = dict(store.get(self._key) or {}) if isinstance(store, dict) else {}
        merged.update(dict(data))
        if isinstance(store, dict):
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
        self._db._store(self._name).append(dict(entry))
        return type("Ref", (), {"id": f"{self._name}-{len(self._db._store(self._name))}"})()


class _FakeDB:
    def __init__(self):
        self.tenants = {}
        self.users = {}
        self.invites = {}
        self.audit = []

    def _store(self, name):
        return {
            "tenants": self.tenants,
            "users": self.users,
            "invites": self.invites,
            "audit_logs": self.audit,
        }[name]

    def collection(self, name):
        if name not in ("tenants", "users", "invites", "audit_logs"):
            raise AssertionError(f"unexpected collection {name}")
        return _Coll(self, name)


class _FakeAuth:
    def __init__(self):
        self.records = {}
        self.claims = {}

    def create_user(self, **kw):
        uid = f"uid-{len(self.records) + 1}"
        self.records[uid] = dict(kw)
        return type("U", (), {"uid": uid, "email": kw.get("email")})()

    def set_custom_user_claims(self, uid, claims):
        self.claims[uid] = dict(claims)


def _patch(monkeypatch, db, auth=None):
    monkeypatch.setattr("app.firebase.get_db", lambda: db)
    monkeypatch.setattr("app.routes.auth.get_db", lambda: db)
    monkeypatch.setattr("app.services.tenant_registration.get_db", lambda: db)
    monkeypatch.setattr("app.services.users.get_db", lambda: db)
    monkeypatch.setattr("app.services.audit_service.get_db", lambda: db)
    monkeypatch.setattr("app.services.invites.get_db", lambda: db)
    if auth is not None:
        monkeypatch.setattr("app.firebase.get_auth", lambda: auth)
        monkeypatch.setattr("app.services.tenant_registration.get_auth", lambda: auth)


def _seed_tenant(db, tid="yeti-airlines", name="Yeti Airlines",
                 departments=None, invite_code="ABC123", active=True):
    db.tenants[tid] = {
        "tenant_id": tid,
        "name": name,
        "tenant_type": "AIRLINE_FIXED_WING",
        "classification": "AIRLINE_FIXED_WING",
        "applicable_departments": departments or ["safety", "flight_ops", "camo", "qa"],
        "team_invite_code": invite_code,
        "active": active,
    }


def _seed_scoped_invite(db, code="HOD123", tid="yeti-airlines",
                        department="flight_ops", role="STAFF", status="ACTIVE"):
    db.invites[code] = {
        "code": code,
        "tenant_id": tid,
        "department": department,
        "department_label": "Flight Operations" if department == "flight_ops" else department,
        "role": role,
        "created_by": "sm@yeti-airlines.com",
        "created_at": "2026-08-01T00:00:00Z",
        "status": status,
    }


def _as_role(role, tid="yeti-airlines", department=None):
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


def _clear_override():
    app.dependency_overrides.pop(get_current_user, None)


# ============================================================================
# Invite RBAC
# ============================================================================

def test_tenant_admin_invites_dept_admin_any_department(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db)
    _override_user(_as_role("TENANT_ADMIN", department="safety"))
    try:
        resp = TestClient(app).post("/api/v1/auth/invite",
                                    json={"department": "camo", "role": "DEPT_ADMIN"})
    finally:
        _clear_override()
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["role"] == "DEPT_ADMIN"
    assert body["department"] == "camo"
    code = body["code"]
    assert len(code) == 6
    stored = db.invites[code]
    assert stored["tenant_id"] == "yeti-airlines"
    assert stored["department"] == "camo"
    assert stored["role"] == "DEPT_ADMIN"
    assert stored["status"] == "ACTIVE"
    assert stored["created_by"] == "uid-tenant_admin"


def test_tenant_admin_invites_staff_any_department(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db)
    _override_user(_as_role("TENANT_ADMIN", department="safety"))
    try:
        resp = TestClient(app).post("/api/v1/auth/invite",
                                    json={"department": "qa", "role": "STAFF"})
    finally:
        _clear_override()
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "STAFF"


def test_legacy_airline_admin_can_invite_safety_officer(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db)
    _override_user(_as_role("AIRLINE_ADMIN", department="safety"))
    try:
        resp = TestClient(app).post("/api/v1/auth/invite",
                                    json={"department": "flight_ops", "role": "SAFETY_OFFICER"})
    finally:
        _clear_override()
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "SAFETY_OFFICER"


def test_legacy_auth_invite_alias_works(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db)
    _override_user(_as_role("TENANT_ADMIN", department="safety"))
    try:
        resp = TestClient(app).post("/api/auth/invite",
                                    json={"department": "camo", "role": "STAFF"})
    finally:
        _clear_override()
    assert resp.status_code == 200, resp.text


def test_dept_admin_invites_staff_own_department(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db)
    _override_user(_as_role("DEPT_ADMIN", department="Flight Operations"))
    try:
        resp = TestClient(app).post("/api/v1/auth/invite",
                                    json={"department": "flight_ops", "role": "STAFF"})
    finally:
        _clear_override()
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "STAFF"
    assert body["department"] == "flight_ops"


def test_dept_admin_cross_department_invite_returns_403(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db)
    _override_user(_as_role("DEPT_ADMIN", department="Flight Operations"))
    try:
        resp = TestClient(app).post("/api/v1/auth/invite",
                                    json={"department": "camo", "role": "STAFF"})
    finally:
        _clear_override()
    assert resp.status_code == 403
    assert "own department" in resp.json()["detail"]
    assert not db.invites


def test_dept_admin_cannot_assign_dept_admin_role(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db)
    _override_user(_as_role("DEPT_ADMIN", department="Flight Operations"))
    try:
        resp = TestClient(app).post("/api/v1/auth/invite",
                                    json={"department": "flight_ops", "role": "DEPT_ADMIN"})
    finally:
        _clear_override()
    assert resp.status_code == 403
    assert "Department Admin" in resp.json()["detail"]
    assert not db.invites


def test_dept_admin_cannot_assign_tenant_admin_role(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db)
    _override_user(_as_role("DEPT_ADMIN", department="Flight Operations"))
    try:
        resp = TestClient(app).post("/api/v1/auth/invite",
                                    json={"department": "flight_ops", "role": "TENANT_ADMIN"})
    finally:
        _clear_override()
    assert resp.status_code == 403
    assert not db.invites


def test_staff_cannot_invite(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db)
    _override_user(_as_role("STAFF", department="Flight Operations"))
    try:
        resp = TestClient(app).post("/api/v1/auth/invite",
                                    json={"department": "flight_ops", "role": "STAFF"})
    finally:
        _clear_override()
    assert resp.status_code == 403
    assert not db.invites


def test_tenant_admin_cannot_invite_to_inapplicable_department(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db, departments=["safety", "flight_ops"])
    _override_user(_as_role("TENANT_ADMIN", department="safety"))
    try:
        resp = TestClient(app).post("/api/v1/auth/invite",
                                    json={"department": "arff", "role": "STAFF"})
    finally:
        _clear_override()
    assert resp.status_code == 422
    assert not db.invites


# ============================================================================
# Join binds department + role from the scoped invite
# ============================================================================

def _join_body(invite_code="HOD123", department="flight_ops", **overrides):
    body = {
        "invite_code": invite_code,
        "full_name": "Ramesh Gurung",
        "email": "ramesh@yetiairlines.com",
        "password": "Join-2026-Pass",
        "confirm_password": "Join-2026-Pass",
        "department": department,
    }
    body.update(overrides)
    return body


def test_join_with_scoped_invite_binds_department_and_staff_role(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)
    _seed_tenant(db)
    _seed_scoped_invite(db, code="HOD123", department="camo", role="STAFF")

    resp = TestClient(app).post(
        "/api/v1/auth/join-team",
        json=_join_body(invite_code="HOD123", department="flight_ops"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["department"] == "camo"
    assert body["department_label"] == "CAMO"
    assert body["role"] == "STAFF"

    uid = list(auth.claims)[0]
    assert auth.claims[uid] == {
        "role": "STAFF",
        "tenant_id": "yeti-airlines",
        "department": "CAMO",
    }
    user_doc = list(db.users.values())[0]
    assert user_doc["role"] == "STAFF"
    assert user_doc["department"] == "CAMO"
    assert user_doc["status"] == "ACTIVE"


def test_join_alias_endpoint_binds_dept_admin_role(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)
    _seed_tenant(db)
    _seed_scoped_invite(db, code="HOD456", department="qa", role="DEPT_ADMIN")

    resp = TestClient(app).post(
        "/api/v1/auth/join",
        json=_join_body(invite_code="HOD456", department="flight_ops",
                        email="hodqa@yetiairlines.com"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["department"] == "qa"
    assert body["role"] == "DEPT_ADMIN"
    uid = list(auth.claims)[0]
    assert auth.claims[uid]["role"] == "DEPT_ADMIN"
    assert auth.claims[uid]["department"] == "QA"


def test_join_inactive_scoped_invite_rejected(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)
    _seed_tenant(db)
    _seed_scoped_invite(db, code="DEAD00", department="camo", role="STAFF", status="USED")

    resp = TestClient(app).post(
        "/api/v1/auth/join-team",
        json=_join_body(invite_code="DEAD00"),
    )
    assert resp.status_code == 404
    assert not auth.claims
    assert not db.users


def test_join_legacy_tenant_code_still_defaults_to_least_privilege(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)
    _seed_tenant(db, invite_code="ABC123")

    resp = TestClient(app).post(
        "/api/v1/auth/join-team",
        json=_join_body(invite_code="ABC123", department="flight_ops"),
    )
    assert resp.status_code == 200, resp.text
    uid = list(auth.claims)[0]
    assert auth.claims[uid]["role"] == "USER"
    assert auth.claims[uid]["department"] == "Flight Operations"


def test_verify_invite_returns_scoped_department_and_role(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db)
    _seed_scoped_invite(db, code="HOD999", department="flight_ops", role="SAFETY_OFFICER")

    resp = TestClient(app).get("/api/v1/auth/verify-invite?code=HOD999")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid"] is True
    assert body["tenant_id"] == "yeti-airlines"
    assert body["department"] == "flight_ops"
    assert body["department_label"] == "Flight Operations"
    assert body["role"] == "SAFETY_OFFICER"


# ============================================================================
# Department-scoped team listing
# ============================================================================

def _seed_users(db):
    db.users["u-sm"] = {
        "uid": "u-sm", "email": "sm@yeti.com", "role": "AIRLINE_ADMIN",
        "tenant_id": "yeti-airlines", "department": "Safety",
    }
    db.users["u-hod"] = {
        "uid": "u-hod", "email": "hodops@yeti.com", "role": "DEPT_ADMIN",
        "tenant_id": "yeti-airlines", "department": "Flight Operations",
    }
    db.users["u-eng"] = {
        "uid": "u-eng", "email": "eng@yeti.com", "role": "STAFF",
        "tenant_id": "yeti-airlines", "department": "Flight Operations",
    }
    db.users["u-camo"] = {
        "uid": "u-camo", "email": "camo@yeti.com", "role": "STAFF",
        "tenant_id": "yeti-airlines", "department": "CAMO",
    }


def test_dept_admin_users_list_is_scoped_to_own_department(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db)
    _seed_users(db)
    _override_user(_as_role("DEPT_ADMIN", department="Flight Operations"))
    try:
        resp = TestClient(app).get("/api/v1/tenants/yeti-airlines/users")
    finally:
        _clear_override()
    assert resp.status_code == 200, resp.text
    users = resp.json()["data"]["users"]
    emails = [u["email"] for u in users]
    assert "hodops@yeti.com" in emails
    assert "eng@yeti.com" in emails
    assert "camo@yeti.com" not in emails
    assert "sm@yeti.com" not in emails


def test_tenant_admin_users_list_shows_all_departments(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db)
    _seed_users(db)
    _override_user(_as_role("TENANT_ADMIN", department="safety"))
    try:
        resp = TestClient(app).get("/api/v1/tenants/yeti-airlines/users")
    finally:
        _clear_override()
    assert resp.status_code == 200, resp.text
    users = resp.json()["data"]["users"]
    assert len(users) == 4
