"""Developer / SuperAdmin tenant governance tests.

Covers GET /api/v1/admin/tenants/governance (SUPER_ADMIN or developer-email
gated, normalized tenant summary), PATCH /api/v1/admin/tenants/{id}/status
(status validation + Firestore reflection), and the middleware lockout: a user
belonging to a SUSPENDED tenant is rejected by get_current_user with HTTP 403.
"""

import asyncio

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user, SUSPENDED_TENANT_DETAIL


class _Snap:
    def __init__(self, data, doc_id, exists=True):
        self._data = data or {}
        self.id = doc_id
        self.exists = exists

    def to_dict(self):
        return self._data


class _DocRef:
    def __init__(self, db, coll, doc_id):
        self._db = db
        self._coll = coll
        self._id = doc_id

    def get(self):
        data = self._db._stores.get(self._coll, {}).get(self._id)
        if data is None:
            return _Snap({}, self._id, exists=False)
        return _Snap(dict(data), self._id, exists=True)

    def update(self, fields):
        store = self._db._stores.setdefault(self._coll, {})
        if self._id not in store:
            store[self._id] = {}
        store[self._id].update(fields)


class _Coll:
    def __init__(self, db, name):
        self._db = db
        self._name = name

    def get(self):
        return [
            _Snap(dict(data), doc_id)
            for doc_id, data in self._db._stores.get(self._name, {}).items()
        ]

    def document(self, doc_id):
        return _DocRef(self._db, self._name, doc_id)


class _FakeDB:
    def __init__(self, tenants=None):
        self._stores = {"tenants": dict(tenants or {})}

    def collection(self, name):
        return _Coll(self, name)


def _seed_tenants():
    return {
        "acme-air": {
            "tenant_id": "acme-air",
            "name": "Acme Air",
            "classification": "Fixed-Wing Airline",
            "safety_manager": {"email": "safety@acmeair.com", "name": "A. Manager"},
            "status": "Active",
            "created_at": "2026-08-01T00:00:00+00:00",
            "is_beta_sandbox": True,
        },
        "sky-heli": {
            "tenant_id": "sky-heli",
            "name": "Sky Heli",
            "tenant_type": "Helicopter/Rotary Operator",
            "safety_manager": {"email": "safety@skyheli.com", "name": "S. Manager"},
            "created_at": "2026-08-02T00:00:00+00:00",
        },
    }


def _patch_admin_db(monkeypatch, db):
    import app.routes.admin as admin_mod
    monkeypatch.setattr(admin_mod.get_db, "__wrapped__", None, raising=False)
    monkeypatch.setattr("app.routes.admin.get_db", lambda: db)


def _user(role="SUPER_ADMIN", email="super-admin@aviasafesystems.com", tenant_id=None):
    return {"uid": "dev-1", "email": email, "role": role, "tenant_id": tenant_id}


def _client(user=None):
    app.dependency_overrides[get_current_user] = lambda: user or _user()
    return TestClient(app)


def _clear():
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# GET /api/v1/admin/tenants/governance
# ---------------------------------------------------------------------------

def test_governance_list_super_admin_200(monkeypatch):
    _patch_admin_db(monkeypatch, _FakeDB(_seed_tenants()))
    try:
        resp = _client(_user("SUPER_ADMIN")).get("/api/v1/admin/tenants/governance")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        by_id = {t["tenant_id"]: t for t in body["tenants"]}

        acme = by_id["acme-air"]
        assert acme["name"] == "Acme Air"
        assert acme["classification"] == "Fixed-Wing Airline"
        assert acme["admin_email"] == "safety@acmeair.com"
        assert acme["status"] == "ACTIVE"  # normalized from "Active"
        assert acme["is_beta_sandbox"] is True
        assert acme["created_at"] == "2026-08-01T00:00:00+00:00"

        heli = by_id["sky-heli"]
        assert heli["classification"] == "Helicopter/Rotary Operator"  # tenant_type fallback
        assert heli["status"] == "ACTIVE"  # default when status missing
        assert heli["is_beta_sandbox"] is False
    finally:
        _clear()


def test_governance_list_developer_email_200(monkeypatch):
    """The developer allowlist must work via email even when the role is USER,
    and the email match is case-insensitive."""
    _patch_admin_db(monkeypatch, _FakeDB(_seed_tenants()))
    try:
        resp = _client(_user("USER", "GhanshyamAcharya@Outlook.COM")).get(
            "/api/v1/admin/tenants/governance"
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 2
    finally:
        _clear()


def test_governance_list_denied_for_tenant_admin(monkeypatch):
    _patch_admin_db(monkeypatch, _FakeDB(_seed_tenants()))
    try:
        resp = _client(_user("AIRLINE_ADMIN", "safety@acmeair.com", "acme-air")).get(
            "/api/v1/admin/tenants/governance"
        )
        assert resp.status_code == 403
    finally:
        _clear()


# ---------------------------------------------------------------------------
# PATCH /api/v1/admin/tenants/{tenant_id}/status
# ---------------------------------------------------------------------------

def test_patch_status_updates_tenant(monkeypatch):
    db = _FakeDB(_seed_tenants())
    _patch_admin_db(monkeypatch, db)
    try:
        resp = _client(_user("SUPER_ADMIN")).patch(
            "/api/v1/admin/tenants/acme-air/status", json={"status": "SUSPENDED"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["tenant"]["tenant_id"] == "acme-air"
        assert body["tenant"]["status"] == "SUSPENDED"

        stored = db._stores["tenants"]["acme-air"]
        assert stored["status"] == "SUSPENDED"
        assert stored["active"] is False
        assert stored["status_updated_by"] == "dev-1"
    finally:
        _clear()


def test_patch_status_activate_after_suspend(monkeypatch):
    db = _FakeDB(_seed_tenants())
    db._stores["tenants"]["acme-air"]["status"] = "SUSPENDED"
    db._stores["tenants"]["acme-air"]["active"] = False
    _patch_admin_db(monkeypatch, db)
    try:
        resp = _client(_user("SUPER_ADMIN")).patch(
            "/api/v1/admin/tenants/acme-air/status", json={"status": "ACTIVE"}
        )
        assert resp.status_code == 200
        assert resp.json()["tenant"]["status"] == "ACTIVE"
        assert db._stores["tenants"]["acme-air"]["active"] is True
    finally:
        _clear()


def test_patch_status_invalid_rejected(monkeypatch):
    _patch_admin_db(monkeypatch, _FakeDB(_seed_tenants()))
    try:
        resp = _client(_user("SUPER_ADMIN")).patch(
            "/api/v1/admin/tenants/acme-air/status", json={"status": "BOGUS"}
        )
        assert resp.status_code == 422
    finally:
        _clear()


def test_patch_status_not_found(monkeypatch):
    _patch_admin_db(monkeypatch, _FakeDB(_seed_tenants()))
    try:
        resp = _client(_user("SUPER_ADMIN")).patch(
            "/api/v1/admin/tenants/does-not-exist/status", json={"status": "SUSPENDED"}
        )
        assert resp.status_code == 404
    finally:
        _clear()


def test_patch_status_denied_for_tenant_admin(monkeypatch):
    _patch_admin_db(monkeypatch, _FakeDB(_seed_tenants()))
    try:
        resp = _client(_user("AIRLINE_ADMIN", "safety@acmeair.com", "acme-air")).patch(
            "/api/v1/admin/tenants/acme-air/status", json={"status": "SUSPENDED"}
        )
        assert resp.status_code == 403
    finally:
        _clear()


# ---------------------------------------------------------------------------
# Middleware lockout — SUSPENDED tenant's users get HTTP 403
# ---------------------------------------------------------------------------

class _Creds:
    def __init__(self, token):
        self.credentials = token
        self.scheme = "Bearer"


def _patch_auth(monkeypatch, db, *, role="AIRLINE_ADMIN", tenant_id="acme-air"):
    monkeypatch.setattr(
        "app.middleware.auth.verify_firebase_token",
        lambda token: {
            "uid": "u-1",
            "email": "safety@acmeair.com",
            "role": role,
            "tenant_id": tenant_id,
            "department": "safety",
        },
    )
    monkeypatch.setattr("app.middleware.auth.get_db", lambda: db)


def test_suspended_tenant_user_locked_out(monkeypatch):
    db = _FakeDB(_seed_tenants())
    db._stores["tenants"]["acme-air"]["status"] = "SUSPENDED"
    _patch_auth(monkeypatch, db)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_current_user(_Creds("token")))
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == SUSPENDED_TENANT_DETAIL


def test_active_tenant_user_allowed(monkeypatch):
    db = _FakeDB(_seed_tenants())
    _patch_auth(monkeypatch, db)

    user = asyncio.run(get_current_user(_Creds("token")))
    assert user["email"] == "safety@acmeair.com"
    assert user["tenant_id"] == "acme-air"


def test_suspended_check_skipped_for_cross_tenant_roles(monkeypatch):
    db = _FakeDB(_seed_tenants())
    db._stores["tenants"]["acme-air"]["status"] = "SUSPENDED"
    _patch_auth(monkeypatch, db, role="CAAN_SMD", tenant_id=None)

    user = asyncio.run(get_current_user(_Creds("token")))
    assert user["role"] == "CAAN_SMD"


def test_suspended_check_fail_open_on_db_error(monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("database down")

    monkeypatch.setattr(
        "app.middleware.auth.verify_firebase_token",
        lambda token: {"uid": "u-1", "email": "safety@acmeair.com",
                       "role": "AIRLINE_ADMIN", "tenant_id": "acme-air"},
    )
    monkeypatch.setattr("app.middleware.auth.get_db", _boom)

    user = asyncio.run(get_current_user(_Creds("token")))
    assert user["tenant_id"] == "acme-air"  # deny-open: user not locked out