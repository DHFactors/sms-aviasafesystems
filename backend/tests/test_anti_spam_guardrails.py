"""Anti-spam and credential-stuffing guardrails on auth and intake routes (2026-08).

Covers:
  * POST /api/v1/auth/register-tenant   - disposable-email rejection (400) and
    strict sliding-window registration limit (5/hour/IP, 429 + Retry-After)
  * POST /api/v1/auth/join-team         - disposable-email rejection (400)
  * POST /api/v1/auth/register (legacy) - disposable-email rejection (400)
  * GET  /api/v1/auth/verify-invite     - sliding-window limit (10/hour/IP)
  * POST /api/v1/auth/login             - per-IP failed-attempt sliding-window
    lockout (5 failures / 15 min; the 6th attempt is 429 + Retry-After) and
    the success path (custom-token mint).

Honeypot rejections are frontend-only and are covered by
frontend-tests/input-guard.test.js (public/js/input_guard.js).

The sliding-window Redis log is exercised through a lightweight in-memory
FakeRedis implementing exactly the sorted-set subset the limiter uses
(zadd / zcard / zremrangebyscore / zrange / expire / delete).
"""

from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.services.tenant_registration import (
    DISPOSABLE_EMAIL_MESSAGE,
    email_domain,
    is_disposable_email,
)


# ============================================================================
# Fake Redis - sorted-set subset used by the sliding-window limiter
# ============================================================================

class _FakeRedis:
    def __init__(self):
        self.zsets = {}
        self.counters = {}
        self.expiries = {}

    async def zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update(dict(mapping))
        return len(mapping)

    async def zcard(self, key):
        return len(self.zsets.get(key, {}))

    async def zremrangebyscore(self, key, min_score, max_score):
        zs = self.zsets.setdefault(key, {})
        for member, score in list(zs.items()):
            if min_score <= score <= max_score:
                del zs[member]
        return 0

    async def zrange(self, key, start, end, withscores=False):
        items = sorted(self.zsets.get(key, {}).items(), key=lambda kv: kv[1])
        rows = items[start:] if end == -1 else items[start:end + 1]
        if withscores:
            return list(rows)
        return [m for m, _ in rows]

    async def expire(self, key, seconds):
        self.expiries[key] = seconds
        return True

    async def delete(self, key):
        self.zsets.pop(key, None)
        return 1

    async def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def ttl(self, key):
        return self.expiries.get(key, -1)


def _enable_rate_limit(monkeypatch) -> _FakeRedis:
    """Turn the Redis-backed limiter on and point it at an in-memory fake."""
    fake = _FakeRedis()

    async def _get_redis():
        return fake

    monkeypatch.setattr("app.middleware.rate_limit.redis_enabled", True)
    monkeypatch.setattr("app.middleware.rate_limit.get_redis", _get_redis)
    return fake


# ============================================================================
# Fake Firebase storage + auth for the endpoint tests
# ============================================================================

class _Doc:
    def __init__(self, data, exists=True, id=None):
        self._data = data or {}
        self.exists = exists
        self.id = id

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
            ok = all(doc.get(f) == v for f, _, v in self._filters)
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

    def set(self, data):
        self._db.tenants[self._tid] = dict(data)

    def update(self, data):
        if self._tid not in self._db.tenants:
            self._db.tenants[self._tid] = {}
        self._db.tenants[self._tid].update(dict(data))

    def collection(self, name):
        assert name == "profile"
        return _ProfileColl(self._db, self._tid)


class _ProfileColl:
    def __init__(self, db, tid):
        self._db = db
        self._tid = tid

    def document(self, name):
        return _ProfileRef(self._db, self._tid, name)


class _ProfileRef:
    def __init__(self, db, tid, name):
        self._db = db
        self._tid = tid
        self._name = name

    def set(self, data):
        self._db.profiles.setdefault(self._tid, {})[self._name] = dict(data)

    def get(self):
        profile = self._db.profiles.get(self._tid, {}).get(self._name)
        if profile is None:
            return _Doc(None, exists=False)
        return _Doc(dict(profile), exists=True)


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
        self.profiles = {}
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


def _register_body(email="safety@summitair.com", **overrides):
    body = {
        "organization_name": "Summit Air",
        "classification": "AIRLINE_FIXED_WING",
        "admin_full_name": "Anil Shrestha",
        "admin_title": "Safety Manager",
        "email": email,
        "password": "Summit-Safety-2026",
        "confirm_password": "Summit-Safety-2026",
        "beta_access_key": settings.BETA_ACCESS_KEY,
    }
    body.update(overrides)
    return body


def _join_body(email="ops@yetiairlines.com", tid="yeti-airlines",
               invite_code="ABC123", **overrides):
    body = {
        "invite_code": invite_code,
        "tenant_id": tid,
        "full_name": "Rajesh Thapa",
        "email": email,
        "password": "Ops-2026-Password",
        "confirm_password": "Ops-2026-Password",
        "department": "flight_ops",
    }
    body.update(overrides)
    return body


def _seed_tenant(db, tid="yeti-airlines", invite_code="ABC123", active=True):
    db.tenants[tid] = {
        "tenant_id": tid,
        "name": "Yeti Airlines",
        "tenant_type": "AIRLINE_FIXED_WING",
        "classification": "AIRLINE_FIXED_WING",
        "applicable_departments": ["safety", "flight_ops", "camo", "qa"],
        "team_invite_code": invite_code,
        "active": active,
    }


# ============================================================================
# Disposable-email domain helpers
# ============================================================================

def test_email_domain_helper():
    assert email_domain("Ops@YetiAirlines.com") == "yetiairlines.com"
    assert email_domain("  safety@caanepal.gov.np  ") == "caanepal.gov.np"
    assert email_domain("no-at-sign") == "no-at-sign"


def test_is_disposable_email_blocks_known_providers():
    for addr in (
        "boss@mailinator.com",
        "x@sub.guerrillamail.com",
        "temp@yopmail.fr",
        "anon@10minutemail.net",
        "throw@throwaway.email",
        "alias@getnada.com",
    ):
        assert is_disposable_email(addr), addr


def test_is_disposable_email_case_insensitive():
    assert is_disposable_email("Boss@Mailinator.COM")
    assert is_disposable_email("x@YoPMail.com")


def test_is_disposable_email_allows_corporate_domains():
    for addr in (
        "safety@summitair.com",
        "smd@caanepal.gov.np",
        "ops@yetiairlines.com",
        "info@aviasafesystems.com",
    ):
        assert not is_disposable_email(addr), addr


# ============================================================================
# POST /api/v1/auth/register-tenant - disposable email (400)
# ============================================================================

def test_register_tenant_disposable_email_rejected(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)

    resp = TestClient(app).post(
        "/api/v1/auth/register-tenant",
        json=_register_body(email="boss@mailinator.com"),
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == DISPOSABLE_EMAIL_MESSAGE
    assert not db.tenants
    assert not db.profiles
    assert not db.users
    assert not auth.claims


def test_register_tenant_subdomain_disposable_email_rejected(monkeypatch):
    """A subdomain of a blocked provider must also be rejected."""
    _patch(monkeypatch, _FakeDB(), _FakeAuth())
    resp = TestClient(app).post(
        "/api/v1/auth/register-tenant",
        json=_register_body(email="boss@alias.mailinator.com"),
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == DISPOSABLE_EMAIL_MESSAGE


def test_register_tenant_corporate_email_still_accepted(monkeypatch):
    """The blocklist must never reject a genuine corporate mailbox."""
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    resp = TestClient(app).post(
        "/api/v1/auth/register-tenant",
        json=_register_body(email="safety@summitair.com"),
    )
    assert resp.status_code == 200, resp.text


# ============================================================================
# POST /api/v1/auth/join-team - disposable email (400)
# ============================================================================

def test_join_team_disposable_email_rejected(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)
    _seed_tenant(db)

    resp = TestClient(app).post(
        "/api/v1/auth/join-team",
        json=_join_body(email="ops@10minutemail.com"),
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == DISPOSABLE_EMAIL_MESSAGE
    assert not auth.claims


def test_join_team_corporate_email_still_accepted(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db)
    resp = TestClient(app).post(
        "/api/v1/auth/join-team",
        json=_join_body(email="ops@yetiairlines.com"),
    )
    assert resp.status_code == 200, resp.text


# ============================================================================
# POST /api/v1/auth/register (legacy) - disposable email (400)
# ============================================================================

def test_legacy_register_disposable_email_rejected(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)
    resp = TestClient(app).post(
        "/api/v1/auth/register",
        json={
            "email": "spam@yopmail.com",
            "password": "Legacy-Pass-2026",
            "full_name": "Spam Bot",
            "organization": "Spam Co",
            "role": settings.ROLE_DEFAULT_REGISTRATION,
        },
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == DISPOSABLE_EMAIL_MESSAGE
    assert not db.users


# ============================================================================
# POST /api/v1/auth/login - per-IP failed-attempt sliding window
# ============================================================================

async def _bad_credentials(email, password):
    return None


async def _good_credentials(email, password):
    return {"uid": "u-1", "email": email, "display_name": "Test User"}


class _TokenAuth:
    def __init__(self):
        self.token = "custom-token-123"

    def create_custom_token(self, uid):
        return self.token.encode("utf-8")


def test_login_success_returns_custom_token(monkeypatch):
    _enable_rate_limit(monkeypatch)
    monkeypatch.setattr("app.services.login_service.verify_credentials", _good_credentials)
    monkeypatch.setattr("app.services.login_service.get_auth", lambda: _TokenAuth())
    monkeypatch.setattr("app.services.audit_service.log_audit", lambda *a, **k: None)

    resp = TestClient(app).post(
        "/api/v1/auth/login",
        json={"email": "safety@summitair.com", "password": "Good-Pass-2026"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["custom_token"] == "custom-token-123"
    assert body["uid"] == "u-1"


def test_login_bad_credentials_returns_401(monkeypatch):
    _enable_rate_limit(monkeypatch)
    monkeypatch.setattr("app.services.login_service.verify_credentials", _bad_credentials)
    monkeypatch.setattr("app.services.audit_service.log_audit", lambda *a, **k: None)

    resp = TestClient(app).post(
        "/api/v1/auth/login",
        json={"email": "safety@summitair.com", "password": "wrong-pass"},
    )
    assert resp.status_code == 401
    assert "Invalid email or password" in resp.json()["detail"]


def test_login_sixth_failure_returns_429_with_retry_after(monkeypatch):
    _enable_rate_limit(monkeypatch)
    monkeypatch.setattr("app.services.login_service.verify_credentials", _bad_credentials)
    monkeypatch.setattr("app.services.audit_service.log_audit", lambda *a, **k: None)

    client = TestClient(app)
    for i in range(5):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": f"user{i}@corp.com", "password": "wrong-pass"},
        )
        assert resp.status_code == 401, resp.text

    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "user6@corp.com", "password": "wrong-pass"},
    )
    assert resp.status_code == 429, resp.text
    retry_after = resp.headers.get("Retry-After")
    assert retry_after is not None
    assert int(retry_after) >= 1
    assert "Try again" in resp.json()["error"]["message"]
    assert resp.json()["detail"] == resp.json()["error"]["message"]


def test_login_success_clears_failure_window(monkeypatch):
    fake = _enable_rate_limit(monkeypatch)
    monkeypatch.setattr("app.services.login_service.verify_credentials", _bad_credentials)
    monkeypatch.setattr("app.services.audit_service.log_audit", lambda *a, **k: None)

    client = TestClient(app)
    # 4 failures (window capacity is 5): the next attempt may still be a login.
    for i in range(4):
        assert client.post(
            "/api/v1/auth/login",
            json={"email": f"u{i}@corp.com", "password": "bad"},
        ).status_code == 401

    # A successful login clears the window...
    monkeypatch.setattr("app.services.login_service.verify_credentials", _good_credentials)
    monkeypatch.setattr("app.services.login_service.get_auth", lambda: _TokenAuth())
    ok = client.post(
        "/api/v1/auth/login",
        json={"email": "safety@summitair.com", "password": "Good-Pass-2026"},
    )
    assert ok.status_code == 200, ok.text
    assert fake.zsets == {}

    # ...so a follow-up failure is a plain 401, not a lockout 429.
    monkeypatch.setattr("app.services.login_service.verify_credentials", _bad_credentials)
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "other@corp.com", "password": "bad"},
    )
    assert resp.status_code == 401, resp.text


# ============================================================================
# POST /api/v1/auth/register-tenant - sliding-window rate limit
# ============================================================================

def test_register_tenant_rate_limit_429_with_retry_after(monkeypatch):
    _enable_rate_limit(monkeypatch)
    _patch(monkeypatch, _FakeDB(), _FakeAuth())

    client = TestClient(app)
    for i in range(5):
        resp = client.post(
            "/api/v1/auth/register-tenant",
            json=_register_body(email=f"org{i}@corp.com"),
        )
        assert resp.status_code == 200, resp.text

    resp = client.post(
        "/api/v1/auth/register-tenant",
        json=_register_body(email="org6@corp.com"),
    )
    assert resp.status_code == 429, resp.text
    assert resp.headers.get("Retry-After") is not None
    assert int(resp.headers["Retry-After"]) >= 1


# ============================================================================
# GET /api/v1/auth/verify-invite - sliding-window rate limit
# ============================================================================

def test_verify_invite_rate_limit_429_with_retry_after(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db, invite_code="ABC123")
    _enable_rate_limit(monkeypatch)

    client = TestClient(app)
    for i in range(10):
        resp = client.get("/api/v1/auth/verify-invite?code=ABC123")
        assert resp.status_code == 200, resp.text

    resp = client.get("/api/v1/auth/verify-invite?code=ABC123")
    assert resp.status_code == 429, resp.text
    assert resp.headers.get("Retry-After") is not None
    assert int(resp.headers["Retry-After"]) >= 1