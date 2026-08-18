"""Self-service onboarding safeguards: real-time invite verification and
duplicate-account protection (2026-08).

Covers:
  * GET  /api/v1/auth/verify-invite  (valid / invalid / inactive / blank code,
    case-insensitive resolution, public payload shape)
  * POST /api/v1/auth/join-team      (duplicate email -> 409, least-privilege
    USER claims, operational_role capture, strong-password rules)

Invite verification deliberately reveals nothing when a code is unknown or
inactive: it returns {valid: false, error} with 404 / 400.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings


# ============================================================================
# Fake Firebase storage + auth for the endpoint tests
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


class _TenantQuery:
    def __init__(self, db):
        self._db = db
        self._filters = []

    def where(self, field, op, value):
        self._filters.append((field, op, value))
        return self

    def limit(self, n):
        return self

    def get(self):
        rows = []
        for tid, data in self._db.tenants.items():
            doc = dict(data or {})
            doc.setdefault("tenant_id", tid)
            ok = True
            for field, op, value in self._filters:
                if op == "==" and doc.get(field) != value:
                    ok = False
            if ok:
                rows.append(_Doc(doc, exists=True, id=tid))
        return rows


class _TenantRef:
    def __init__(self, db, tid):
        self._db = db
        self._tid = tid

    def get(self):
        if self._tid not in self._db.tenants:
            return _Doc(None, exists=False, id=self._tid)
        return _Doc(dict(self._db.tenants[self._tid]), exists=True, id=self._tid)


class _TenantsColl:
    def __init__(self, db):
        self._db = db

    def document(self, tid):
        return _TenantRef(self._db, tid)

    def where(self, field, op, value):
        return _TenantQuery(self._db).where(field, op, value)


class _UserRef:
    def __init__(self, db, uid):
        self._db = db
        self._uid = uid

    def set(self, data, merge=False):
        if merge and self._uid in self._db.users:
            merged = dict(self._db.users[self._uid])
            merged.update(dict(data))
            data = merged
        self._db.users[self._uid] = dict(data)

    def get(self):
        if self._uid not in self._db.users:
            return _Doc(None, exists=False)
        return _Doc(dict(self._db.users[self._uid]), exists=True)


class _UsersColl:
    def __init__(self, db):
        self._db = db

    def document(self, uid):
        return _UserRef(self._db, uid)


class _AuditColl:
    def __init__(self, db):
        self._db = db

    def add(self, entry):
        self._db.audit.append(dict(entry))
        return type("Ref", (), {"id": f"audit-{len(self._db.audit)}"})()


class _FakeDB:
    def __init__(self):
        self.tenants = {}
        self.users = {}
        self.audit = []

    def collection(self, name):
        if name == "tenants":
            return _TenantsColl(self)
        if name == "users":
            return _UsersColl(self)
        if name == "audit_logs":
            return _AuditColl(self)
        raise AssertionError(f"unexpected collection {name}")


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
    if auth is not None:
        monkeypatch.setattr("app.firebase.get_auth", lambda: auth)
        monkeypatch.setattr("app.services.tenant_registration.get_auth", lambda: auth)


def _seed_tenant(db, tid="yeti-airlines", name="Yeti Airlines",
                 classification="AIRLINE_FIXED_WING",
                 departments=None, invite_code="ABC123", active=True, status=None):
    db.tenants[tid] = {
        "tenant_id": tid,
        "name": name,
        "tenant_type": classification,
        "classification": classification,
        "applicable_departments": departments or ["safety", "flight_ops", "camo", "qa"],
        "team_invite_code": invite_code,
        "active": active,
    }
    if status is not None:
        db.tenants[tid]["status"] = status
    return db.tenants[tid]


def _join_body(tid="yeti-airlines", department="flight_ops", invite_code="ABC123",
               operational_role="safety_officer", **overrides):
    body = {
        "invite_code": invite_code,
        "full_name": "Rajesh Thapa",
        "email": "ops@yetiairlines.com",
        "password": "Ops-2026-Password",
        "confirm_password": "Ops-2026-Password",
        "department": department,
        "operational_role": operational_role,
    }
    body.update(overrides)
    if tid:
        body["tenant_id"] = tid
    return body


# ============================================================================
# GET /api/v1/auth/verify-invite
# ============================================================================

def test_verify_invite_valid_code(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db, invite_code="ABC123")

    resp = TestClient(app).get("/api/v1/auth/verify-invite?code=ABC123")
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["organization_name"] == "Yeti Airlines"
    assert body["tenant_id"] == "yeti-airlines"
    assert body["category"] == "AIRLINE_FIXED_WING"


def test_verify_invite_is_case_insensitive(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db, invite_code="ABC123")

    resp = TestClient(app).get("/api/v1/auth/verify-invite?code=abc123")
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


def test_verify_invite_invalid_code(monkeypatch):
    _patch(monkeypatch, _FakeDB(), _FakeAuth())
    resp = TestClient(app).get("/api/v1/auth/verify-invite?code=ZZZZZZ")
    assert resp.status_code == 404
    body = resp.json()
    assert body["valid"] is False
    assert body["error"] == "Invalid or expired invite code"


def test_verify_invite_blank_code(monkeypatch):
    _patch(monkeypatch, _FakeDB(), _FakeAuth())
    resp = TestClient(app).get("/api/v1/auth/verify-invite")
    assert resp.status_code == 400
    assert resp.json()["valid"] is False


def test_verify_invite_inactive_tenant_rejected(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db, invite_code="OFF000", active=False)

    resp = TestClient(app).get("/api/v1/auth/verify-invite?code=OFF000")
    assert resp.status_code == 404
    body = resp.json()
    assert body["valid"] is False
    assert body["error"] == "Invalid or expired invite code"


def test_verify_invite_suspended_status_rejected(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db, invite_code="SUS000", status="inactive")

    resp = TestClient(app).get("/api/v1/auth/verify-invite?code=SUS000")
    assert resp.status_code == 404
    assert resp.json()["valid"] is False


# ============================================================================
# POST /api/v1/auth/join-team — duplicate accounts & least privilege
# ============================================================================

def test_join_team_duplicate_email_returns_409(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)
    _seed_tenant(db)

    def _fail_duplicate(**kw):
        if kw.get("email") == "ops@yetiairlines.com":
            raise ValueError("The email address is already in use by another account.")
        return type("U", (), {"uid": "u-x", "email": kw.get("email")})()

    monkeypatch.setattr(auth, "create_user", _fail_duplicate)

    resp = TestClient(app).post("/api/v1/auth/join-team", json=_join_body())
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]
    assert not auth.claims


def test_join_team_duplicate_email_never_creates_user_doc(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)
    _seed_tenant(db)

    def _fail_duplicate(**kw):
        raise ValueError("Email already in use")

    monkeypatch.setattr(auth, "create_user", _fail_duplicate)

    resp = TestClient(app).post("/api/v1/auth/join-team", json=_join_body())
    assert resp.status_code == 409
    assert not db.users


def test_join_team_stores_operational_role(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)
    _seed_tenant(db)

    resp = TestClient(app).post(
        "/api/v1/auth/join-team",
        json=_join_body(operational_role="Licensed Aircraft Engineer (AME)", email="145@yetiairlines.com"),
    )
    assert resp.status_code == 200, resp.text
    uid = list(auth.claims)[0]
    assert auth.claims[uid] == {
        "role": "USER",
        "tenant_id": "yeti-airlines",
        "department": "Flight Operations",
    }
    user_doc = list(db.users.values())[0]
    assert user_doc["operational_role"] == "Licensed Aircraft Engineer (AME)"
    assert user_doc["role"] == "USER"


def test_join_team_weak_password_rejected(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)
    _seed_tenant(db)

    for weak in ("alllowercase123", "NOUPPERCASE", "Short1x"):
        resp = TestClient(app).post(
            "/api/v1/auth/join-team",
            json=_join_body(password=weak, confirm_password=weak, email=f"{weak}@yetiairlines.com"),
        )
        assert resp.status_code == 422, weak
        detail = resp.json()["detail"]
        assert "uppercase" in detail or "digit" in detail or "at least" in detail, weak
    assert not auth.claims


def test_join_team_password_with_uppercase_and_digit_accepted(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)
    _seed_tenant(db)

    resp = TestClient(app).post(
        "/api/v1/auth/join-team",
        json=_join_body(password="SafeOps2026x", confirm_password="SafeOps2026x"),
    )
    assert resp.status_code == 200, resp.text