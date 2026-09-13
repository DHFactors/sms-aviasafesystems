"""Regression: the password returned by POST /api/v1/admin/users must be the
exact password Firebase Auth stores.

The rest of the admin/credentials suite fakes Auth with `_FakeAuth`, which
stores whatever password was handed to `create_user` and therefore cannot
catch a divergence between the returned password and what real Auth keeps.
This test deliberately skips that fake: it creates a real Firebase Auth user
through the production route, signs in against the LIVE Identity Toolkit
REST endpoint (the same call the browser SDK makes), and verifies the uid.

The tenant/Postgres/user-doc writes are faked so the test leaves no data
behind except a transient real Auth account, which is deleted in teardown.

Requires live Firebase credentials in the environment (FIREBASE_SERVICE or
the ADC file plus FIREBASE_WEB_API_KEY), the same way the deployed backend
and the existing live-signin reproduction do.
"""

import asyncio
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_admin_user
from app.services.login_service import verify_credentials
from app.services import tenant_credentials as tc
from app.firebase import get_auth
from app.db import pg as pg_mod
from pg_bridge import patch_pg_through


# ============================================================================
# Minimal fake Firestore (tenant mirror write only; pg is faked via the bridge)
# ============================================================================

class _Snap:
    def __init__(self, data, doc_id=None):
        self._data = data or {}
        self.id = doc_id or self._data.get("id") or "doc"
        self.exists = bool(self._data)

    def to_dict(self):
        return self._data


class _FakeRef:
    def __init__(self, db, name, doc_id):
        self._db = db
        self._name = name
        self.id = doc_id

    def get(self):
        store = self._db._store_for(self._name)
        if self.id in store:
            data = dict(store[self.id])
            data.setdefault("id", self.id)
            return _Snap(data, self.id)
        return _Snap(None, self.id)

    def set(self, data, merge=False):
        store = self._db._store_for(self._name)
        if merge and self.id in store:
            merged = dict(store[self.id])
            merged.update(data)
            store[self.id] = merged
        else:
            store[self.id] = dict(data)
        return self


class _FakeColl:
    def __init__(self, db, name):
        self._db = db
        self._name = name

    def document(self, doc_id):
        return _FakeRef(self._db, self._name, doc_id)


class _FakeDB:
    def __init__(self):
        self._stores = {"tenants": {}, "users": {}, "audit_logs": {}, "user_profiles": {}}

    def _store_for(self, name):
        if name not in self._stores:
            self._stores[name] = {}
        return self._stores[name]

    def collection(self, name):
        return _FakeColl(self, name)


def _admin_user():
    return {"uid": "super-1", "email": "super-admin@aviasafesystems.com", "role": "SUPER_ADMIN", "tenant_id": None}


def _setup(monkeypatch):
    db = _FakeDB()
    db._stores["tenants"]["pwtest-air"] = {
        "slug": "pwtest-air",
        "name": "Password Regression Air",
        "regulator_id": "caan",
        "users": [
            {"email": "admin@pwtestair.com", "role": "AIRLINE_ADMIN",
             "full_name": "Admin", "status": "active"},
        ],
    }
    patch_pg_through(monkeypatch, lambda: db)
    # Best-effort Firestore mirror of the tenant patch — herd it into the fake
    # instead of the (removed) real Firestore.
    monkeypatch.setattr("app.services.tenant_credentials.get_db", lambda: db)
    monkeypatch.setattr("app.core.config.settings.EMAIL_PROVIDER", "none")
    monkeypatch.setattr("app.core.config.settings.SETUP_SECRET", "test-setup-key")
    app.dependency_overrides[get_admin_user] = _admin_user
    return db


def _teardown():
    app.dependency_overrides.pop(get_admin_user, None)


def _delete_auth_user(email, uid):
    auth = get_auth()
    try:
        auth.delete_user(uid)
        return
    except Exception:  # noqa: BLE001 - try the email backup next
        pass
    try:
        auth.delete_user(auth.get_user_by_email(email).uid)
    except Exception:  # noqa: BLE001 - best-effort cleanup
        pass


def _new_test_email() -> str:
    return f"pwsc-{uuid.uuid4().hex[:10]}@aviasafesystems.com"


def test_returned_password_signs_in_via_identity_toolkit(monkeypatch):
    """The server-generated password must authenticate against real Auth.

    Regression for the reported "returned password fails to sign in" incident
    (classified as a transcription error, not a code bug). If a future change
    ever applies a different password to Auth than the one it returns, this
    test fails at the Identity Toolkit RPC itself.
    """
    db = _setup(monkeypatch)
    email = _new_test_email()
    uid = None
    try:
        resp = TestClient(app).post("/api/v1/admin/users", json={
            "setup_key": "test-setup-key",
            "tenant_id": "pwtest-air",
            "email": email,
            "role": "STAFF",
            "name": "Password Check User",
            "department": "Safety",
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["password"], "no password returned by create"
        password = body["password"]
        uid = body["uid"]

        # The real Auth record exists and is the one we created.
        auth = get_auth()
        rec = auth.get_user_by_email(email)
        assert rec.uid == uid

        # The exact returned password authenticates against the live Identity
        # Toolkit (same RPC as login_service.verify_credentials in prod).
        verified = asyncio.run(verify_credentials(email, password))
        assert verified is not None, "returned password was rejected by Identity Toolkit"
        assert verified["uid"] == uid

        # The password was never persisted anywhere in the tenant document.
        assert "password" not in str(db._stores["tenants"]["pwtest-air"])
        assert any(u["email"] == email for u in db._stores["tenants"]["pwtest-air"]["users"])
    finally:
        if uid:
            _delete_auth_user(email, uid)
        _teardown()


def test_returned_password_signs_in_wrong_password_rejected(monkeypatch):
    """A scrambled copy of the password must NOT sign in — this is what the
    user experienced when hand-transcribing the 14-char password. It confirms
    the rejection comes from Auth, not from the client."""
    db = _setup(monkeypatch)
    email = _new_test_email()
    uid = None
    try:
        resp = TestClient(app).post("/api/v1/admin/users", json={
            "setup_key": "test-setup-key",
            "tenant_id": "pwtest-air",
            "email": email,
            "role": "STAFF",
        })
        assert resp.status_code == 200
        password = resp.json()["password"]
        uid = resp.json()["uid"]

        scrambled = "".join(sorted(password))  # guaranteed different
        assert scrambled != password
        verified = asyncio.run(verify_credentials(email, scrambled))
        assert verified is None, "scrambled password must be rejected"
    finally:
        if uid:
            _delete_auth_user(email, uid)
        _teardown()