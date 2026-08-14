"""Super-Admin tenant credentials management tests.

Covers the tenant_credentials service (tenant+user creation, email
availability, credential reads, password reset, welcome email) and the
/api/v1/admin/tenants/* credential routes (SUPER_ADMIN authz + setup-key gate).
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_admin_user, get_current_user


# ============================================================================
# Fake Firestore (same minimal shape as test_admin_seed)
# ============================================================================

class _FakeRef:
    def __init__(self, db, name, doc_id):
        self._db = db
        self._name = name
        self.id = doc_id

    def get(self):
        store = self._db._store_for(self._name)
        if self.id in store:
            return _Snap(dict(store[self.id]), exists=True)
        return _Snap({}, exists=False)

    def set(self, data, merge=False):
        store = self._db._store_for(self._name)
        if merge and self.id in store:
            merged = dict(store[self.id])
            merged.update(data)
            store[self.id] = merged
        else:
            store[self.id] = dict(data)
        return self


class _Snap:
    def __init__(self, data, exists=True):
        self._data = data or {}
        self.exists = exists
        self.id = self._data.get("id") or "doc"

    def to_dict(self):
        return self._data


class _QueryResult:
    def __init__(self, items):
        self._items = items

    def get(self):
        return self._items


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
        return [_Snap(dict(d)) for d in store.values()]

    def order_by(self, field, direction="ASCENDING"):
        items = [_Snap(dict(d)) for d in self._db._store_for(self._name).values()]
        items.sort(key=lambda s: (s.to_dict().get(field) or ""), reverse=(direction == "DESCENDING"))
        return _QueryResult(items)


class _FakeDB:
    def __init__(self):
        self._stores = {"regulators": {}, "tenants": {}, "audit_logs": {}, "users": {}}

    def _store_for(self, name):
        if name not in self._stores:
            self._stores[name] = {}
        return self._stores[name]

    def collection(self, name):
        return _FakeColl(self, name)


# ============================================================================
# Fake Firebase Auth
# ============================================================================

class _FakeMeta:
    def __init__(self):
        self.creation_timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        self.last_sign_in_at = None
        self.last_sign_in_timestamp = None


class _FakeUserRecord:
    def __init__(self, email, uid, display_name=None):
        self.email = email
        self.uid = uid
        self.display_name = display_name
        self.custom_claims = None
        self.user_metadata = _FakeMeta()


class _FakeAuth:
    def __init__(self):
        self.by_email = {}
        self._seq = 0

    def create_user(self, email=None, password=None, email_verified=False, display_name=None):
        if email in self.by_email:
            from firebase_admin import auth as fb_auth
            raise fb_auth.EmailAlreadyExistsError(
                f"user with email {email} already exists", None, None
            )
        self._seq += 1
        uid = f"uid-{self._seq}"
        rec = _FakeUserRecord(email, uid, display_name)
        rec.password = password
        self.by_email[email] = rec
        return rec

    def get_user_by_email(self, email):
        if email in self.by_email:
            return self.by_email[email]
        from firebase_admin import auth as fb_auth
        raise fb_auth.UserNotFoundError("No user found for email")

    def get_user(self, uid):
        for rec in self.by_email.values():
            if rec.uid == uid:
                return rec
        raise ValueError(f"no user with uid {uid}")

    def update_user(self, uid, custom_claims=None, password=None):
        for rec in self.by_email.values():
            if rec.uid == uid:
                if custom_claims is not None:
                    rec.custom_claims = dict(custom_claims)
                if password:
                    rec.password = password
                return rec
        raise ValueError(f"no user with uid {uid}")


# ============================================================================
# Helpers
# ============================================================================

def _patch_all(monkeypatch, db=None, auth=None, email_provider="none"):
    db = db or _FakeDB()
    auth = auth or _FakeAuth()
    monkeypatch.setattr("app.services.production_seed.get_db", lambda: db)
    monkeypatch.setattr("app.services.tenant_credentials.get_db", lambda: db)
    monkeypatch.setattr("app.services.tenant_credentials.get_auth", lambda: auth)
    monkeypatch.setattr("app.services.users.get_db", lambda: db)
    monkeypatch.setattr("app.services.email_service.settings.EMAIL_PROVIDER", email_provider)
    from app.core.config import settings
    monkeypatch.setattr(settings, "SETUP_SECRET", "test-setup-key", raising=False)
    return db, auth


def _admin_user(role="SUPER_ADMIN"):
    return {"uid": "super-1", "email": "super-admin@aviasafesystems.test", "role": role, "tenant_id": None}


def _client(user=None):
    app.dependency_overrides[get_admin_user] = lambda: user or _admin_user()
    return TestClient(app)


def _clear_overrides():
    app.dependency_overrides.pop(get_admin_user, None)
    app.dependency_overrides.pop(get_current_user, None)


def _sample_tenant():
    return {
        "tenant_id": "new-air",
        "name": "New Air",
        "icao": "NWA",
        "country": "Nepal",
        "regulator_id": "caan",
        "contact": {"name": "Ram Sharma", "title": "Safety Manager",
                    "email": "ram.sharma@newair.com", "phone": "+977-1-1111111"},
        "contract": {"date": "2026-08-01", "reference": "AVIA-NEW-2026-001",
                     "expiry": "2027-07-31", "type": "standard",
                     "signedBy": "Ram Sharma", "signedDate": "2026-08-01"},
        "users": [{"email": "admin@newair.com", "role": "AIRLINE_ADMIN", "full_name": "New Air Admin"}],
    }


# ============================================================================
# Service-level
# ============================================================================

def test_generate_password_length_and_classes():
    from app.services.tenant_credentials import generate_password
    for _ in range(20):
        pw = generate_password()
        assert len(pw) >= 12
        assert any(c.isupper() for c in pw)
        assert any(c.islower() for c in pw)
        assert any(c.isdigit() for c in pw)
        assert any(c in "!@#$%&*_-" for c in pw)


def test_check_email_available(monkeypatch):
    _, auth = _patch_all(monkeypatch)
    from app.services.tenant_credentials import check_email_available
    assert check_email_available("taken@x.com")["available"] is True
    auth.create_user(email="taken@x.com", password="secret12345")
    assert check_email_available("taken@x.com")["available"] is False


def test_create_tenant_with_credentials(monkeypatch):
    db, auth = _patch_all(monkeypatch)
    from app.services.tenant_credentials import create_tenant_with_credentials
    result = create_tenant_with_credentials(_sample_tenant(), _admin_user())

    assert result["users"][0]["status"] == "ok"
    assert result["users"][0]["email"] == "admin@newair.com"
    # Password is returned exactly once and never stored
    assert result["users"][0]["password"]
    stored = db._stores["tenants"]["new-air"]
    assert "password" not in str(stored)
    assert stored["contact"]["name"] == "Ram Sharma"
    assert stored["contract"]["reference"] == "AVIA-NEW-2026-001"
    assert stored["users"][0]["email"] == "admin@newair.com"
    assert stored["safety_manager"]["email"] == "admin@newair.com"
    assert stored["audit"]["created_by"] == "super-admin@aviasafesystems.test"
    assert any(l["action"] == "TENANT_CREDENTIALS_CREATED" for l in db._stores["audit_logs"].values())
    # Auth user created with claims
    rec = auth.by_email["admin@newair.com"]
    assert rec.custom_claims == {"role": "AIRLINE_ADMIN", "tenant_id": "new-air"}


def test_create_tenant_with_credentials_duplicate_email(monkeypatch):
    db, auth = _patch_all(monkeypatch)
    from app.services.tenant_credentials import create_tenant_with_credentials
    auth.create_user(email="admin@newair.com", password="secret12345")
    result = create_tenant_with_credentials(_sample_tenant(), _admin_user())
    assert result["users"][0]["status"] == "error"
    assert "already exists" in result["users"][0]["detail"]
    # tenant doc still created with no stored users
    stored = db._stores["tenants"]["new-air"]
    assert "users" not in stored


def test_get_tenant_credentials(monkeypatch):
    db, _ = _patch_all(monkeypatch)
    db._stores["tenants"]["new-air"] = {
        "tenant_id": "new-air", "name": "New Air", "contact": {"name": "Ram Sharma"},
        "users": [{"email": "admin@newair.com", "role": "AIRLINE_ADMIN"}],
    }
    from app.services.tenant_credentials import get_tenant_credentials
    creds = get_tenant_credentials("new-air")
    assert creds["name"] == "New Air"
    assert creds["users"][0]["email"] == "admin@newair.com"


def test_get_tenant_credentials_missing(monkeypatch):
    _patch_all(monkeypatch)
    from app.services.tenant_credentials import get_tenant_credentials
    try:
        get_tenant_credentials("nope")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "not found" in str(e)


def test_reset_admin_password(monkeypatch):
    db, auth = _patch_all(monkeypatch)
    db._stores["tenants"]["new-air"] = {
        "tenant_id": "new-air", "users": [{"email": "admin@newair.com", "role": "AIRLINE_ADMIN"}],
    }
    auth.create_user(email="admin@newair.com", password="old-password-123")
    from app.services.tenant_credentials import reset_admin_password
    result = reset_admin_password("new-air", _admin_user())
    assert result["email"] == "admin@newair.com"
    assert result["password"] and len(result["password"]) >= 12
    assert auth.by_email["admin@newair.com"].password == result["password"]
    assert any(l["action"] == "TENANT_PASSWORD_RESET" for l in db._stores["audit_logs"].values())


def test_send_welcome_email_log_provider(monkeypatch):
    db, auth = _patch_all(monkeypatch, email_provider="none")
    db._stores["tenants"]["new-air"] = {
        "tenant_id": "new-air", "name": "New Air",
        "contact": {"name": "Ram Sharma"},
        "users": [{"email": "admin@newair.com", "role": "AIRLINE_ADMIN"}],
    }
    auth.create_user(email="admin@newair.com", password="old-password-123")
    from app.services.tenant_credentials import send_welcome_email_for_tenant
    result = send_welcome_email_for_tenant("new-air", _admin_user())
    assert result["admin_email"] == "admin@newair.com"
    assert result["password"]
    assert result["delivery"]["provider"] == "none"
    assert "Welcome to AviaSAFE SMS" in result["delivery"]["preview"]
    assert auth.by_email["admin@newair.com"].password == result["password"]
    assert any(l["action"] == "TENANT_WELCOME_EMAIL" for l in db._stores["audit_logs"].values())


# ============================================================================
# Route-level
# ============================================================================

def test_credentials_routes_require_token():
    try:
        resp = TestClient(app).get("/api/v1/admin/tenants/new-air/credentials?setup_key=x")
        assert resp.status_code in (401, 403)
    finally:
        _clear_overrides()


def test_credentials_routes_403_non_super(monkeypatch):
    _patch_all(monkeypatch)
    app.dependency_overrides[get_current_user] = lambda: _admin_user(role="AIRLINE_ADMIN")
    try:
        resp = TestClient(app).get("/api/v1/admin/tenants/new-air/credentials?setup_key=test-setup-key")
        assert resp.status_code == 403
    finally:
        _clear_overrides()


def test_check_email_route(monkeypatch):
    _, auth = _patch_all(monkeypatch)
    auth.create_user(email="taken@x.com", password="secret12345")
    try:
        resp = _client().post("/api/v1/admin/tenants/check-email",
                              json={"setup_key": "test-setup-key", "email": "taken@x.com"})
        assert resp.status_code == 200
        assert resp.json()["available"] is False
        resp = _client().post("/api/v1/admin/tenants/check-email",
                              json={"setup_key": "test-setup-key", "email": "fresh@x.com"})
        assert resp.json()["available"] is True
    finally:
        _clear_overrides()


def test_check_email_route_wrong_key(monkeypatch):
    _patch_all(monkeypatch)
    try:
        resp = _client().post("/api/v1/admin/tenants/check-email",
                              json={"setup_key": "wrong", "email": "a@b.com"})
        assert resp.status_code == 403
    finally:
        _clear_overrides()


def test_get_credentials_route(monkeypatch):
    db, _ = _patch_all(monkeypatch)
    db._stores["tenants"]["new-air"] = {
        "tenant_id": "new-air", "name": "New Air",
        "contact": {"name": "Ram Sharma"}, "users": [{"email": "admin@newair.com", "role": "AIRLINE_ADMIN"}],
    }
    try:
        resp = _client().get("/api/v1/admin/tenants/new-air/credentials?setup_key=test-setup-key")
        assert resp.status_code == 200
        assert resp.json()["credentials"]["name"] == "New Air"
        resp = _client().get("/api/v1/admin/tenants/missing/credentials?setup_key=test-setup-key")
        assert resp.status_code == 404
    finally:
        _clear_overrides()


def test_reset_password_route(monkeypatch):
    db, auth = _patch_all(monkeypatch)
    db._stores["tenants"]["new-air"] = {
        "tenant_id": "new-air", "users": [{"email": "admin@newair.com", "role": "AIRLINE_ADMIN"}],
    }
    auth.create_user(email="admin@newair.com", password="old-password-123")
    try:
        resp = _client().post("/api/v1/admin/tenants/new-air/reset-password",
                              json={"setup_key": "test-setup-key"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["password"] and len(body["password"]) >= 12
    finally:
        _clear_overrides()


def test_send_welcome_route(monkeypatch):
    db, auth = _patch_all(monkeypatch, email_provider="none")
    db._stores["tenants"]["new-air"] = {
        "tenant_id": "new-air", "name": "New Air",
        "contact": {"name": "Ram Sharma"},
        "users": [{"email": "admin@newair.com", "role": "AIRLINE_ADMIN"}],
    }
    auth.create_user(email="admin@newair.com", password="old-password-123")
    try:
        resp = _client().post("/api/v1/admin/tenants/new-air/send-welcome",
                              json={"setup_key": "test-setup-key"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["delivery"]["provider"] == "none"
        assert body["password"]
    finally:
        _clear_overrides()


def test_create_tenant_route_with_users(monkeypatch):
    db, auth = _patch_all(monkeypatch)
    try:
        resp = _client().post("/api/v1/admin/tenants", json={
            "setup_key": "test-setup-key", "tenant": _sample_tenant(),
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["users"][0]["status"] == "ok"
        assert body["users"][0]["password"]
        assert db._stores["tenants"]["new-air"]["contact"]["name"] == "Ram Sharma"
    finally:
        _clear_overrides()


def test_create_tenant_route_without_users_still_works(monkeypatch):
    db, _ = _patch_all(monkeypatch)
    try:
        resp = _client().post("/api/v1/admin/tenants", json={
            "setup_key": "test-setup-key",
            "tenant": {"tenant_id": "plain-air", "name": "Plain Air", "regulator_id": "caan"},
        })
        assert resp.status_code == 200
        assert resp.json()["tenant"]["tenant_id"] == "plain-air"
    finally:
        _clear_overrides()
