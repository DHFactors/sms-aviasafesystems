"""Phase 2: view-only authorized users list.

Covers the Auth->Firestore user mirroring (user_doc_from_auth_record), the
tenant-scoped query (list_tenant_users), and GET /api/v1/tenants/{id}/users
(authz: AIRLINE_ADMIN of that tenant or SUPER_ADMIN).
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.services import users
from pg_bridge import patch_pg_through


# ============================================================================
# Auth record -> user doc mapping
# ============================================================================

class _FakeMeta:
    def __init__(self, ts, last_sign_in=None):
        self.creation_timestamp = ts
        self.last_sign_in_timestamp = last_sign_in


class _FakeRecord:
    def __init__(self, uid="u1", email="officer@taraair.com", claims=None, meta_ts="2026-08-06T10:00:00Z", last_login=1750000000000):
        self.uid = uid
        self.email = email
        self.display_name = "Tara Safety"
        self.custom_claims = claims or {"role": "AIRLINE_ADMIN", "tenant_id": "tara-air"}
        self.user_metadata = _FakeMeta(meta_ts, last_sign_in=last_login)


def test_user_doc_from_auth_record_full():
    doc = users.user_doc_from_auth_record(_FakeRecord())
    assert doc["uid"] == "u1"
    assert doc["email"] == "officer@taraair.com"
    assert doc["role"] == "AIRLINE_ADMIN"
    assert doc["tenant_id"] == "tara-air"
    assert doc["created_at"] is not None
    assert doc["last_login"] is not None
    assert doc["updated_at"] is not None


def test_user_doc_defaults_when_no_claims():
    rec = _FakeRecord(claims=None)
    rec.custom_claims = None
    rec.user_metadata.last_sign_in_timestamp = None
    doc = users.user_doc_from_auth_record(rec)
    assert doc["role"] == "USER"
    assert doc["tenant_id"] is None
    assert doc["last_login"] is None


def test_user_doc_parses_ms_epoch_last_login():
    rec = _FakeRecord(last_login=1750000000000)
    assert users._parse_ms_timestamp(1750000000000) is not None
    assert users._parse_ms_timestamp("1750000000000") is not None
    assert users._parse_ms_timestamp(None) is None
    assert users._parse_ms_timestamp("not-a-date") is None


# ============================================================================
# list_tenant_users
# ============================================================================

class _UsersDB:
    def __init__(self):
        self._users = {
            "u2": {"uid": "u2", "email": "b@taraair.com", "role": "AIRLINE_ADMIN",
                   "tenant_id": "tara-air", "created_at": _dt(2), "last_login": None},
            "u1": {"uid": "u1", "email": "a@taraair.com", "role": "USER",
                   "tenant_id": "tara-air", "created_at": _dt(1), "last_login": _dt(3)},
            "u3": {"uid": "u3", "email": "x@buddhaair.com", "role": "AIRLINE_ADMIN",
                   "tenant_id": "buddha-air", "created_at": _dt(1), "last_login": None},
        }

    def collection(self, name):
        class _UsersColl:
            def __init__(self, db):
                self._db = db

            def where(self, field, op, value):
                return _UsersQuery(self._db, value)
        if name == "users":
            return _UsersColl(self)
        raise AssertionError(f"unexpected collection {name}")


class _UsersQuery:
    def __init__(self, db, tenant_id):
        self._db = db
        self._tid = tenant_id

    def get(self):
        snaps = []
        for uid, data in self._db._users.items():
            if data.get("tenant_id") == self._tid:
                snaps.append(_UserSnap(uid, data))
        return snaps


class _UserSnap:
    def __init__(self, id, data):
        self.id = id
        self._data = data

    def to_dict(self):
        return self._data


def _dt(day):
    return datetime(2026, 8, day, tzinfo=timezone.utc)


def test_list_tenant_users_filters_and_sorts(monkeypatch):
    patch_pg_through(monkeypatch, lambda: _UsersDB())
    rows = users.list_tenant_users("tara-air")
    assert len(rows) == 2
    # sorted by createdAt then email
    assert rows[0]["uid"] == "u1"
    assert rows[1]["uid"] == "u2"
    assert rows[0]["email"] == "a@taraair.com"
    assert rows[0]["createdAt"].startswith("2026-08-01")
    assert rows[1]["lastLogin"] is None


# ============================================================================
# GET /api/v1/tenants/{tenantId}/users
# ============================================================================

class _FakeUsersColl:
    def __init__(self, db):
        self._db = db

    def where(self, field, op, value):
        return _FakeUsersQuery(self._db, value)


class _FakeUsersQuery:
    def __init__(self, db, tid):
        self._db = db
        self._tid = tid

    def get(self):
        snaps = []
        for uid, data in self._db._users.items():
            if data.get("tenant_id") == self._tid:
                snaps.append(_UserSnap(uid, data))
        return snaps


class _FakeDB:
    def __init__(self):
        self._users = {}

    def collection(self, name):
        if name == "users":
            return _FakeUsersColl(self)
        raise AssertionError(f"unexpected collection {name}")


def _patch_db(monkeypatch, db):
    patch_pg_through(monkeypatch, lambda: db)


def _patch_user(monkeypatch, user):
    def _fake_verify_firebase_token(token):
        return {
            "uid": user["uid"],
            "email": user["email"],
            "role": user["role"],
            "tenant_id": user["tenant_id"],
        }
    monkeypatch.setattr("app.middleware.auth.verify_firebase_token", _fake_verify_firebase_token)


def _user(role="AIRLINE_ADMIN", tid="tara-air", uid="u-admin", email="admin@taraair.com"):
    return {"uid": uid, "email": email, "role": role, "tenant_id": tid,
            "claims": {"role": role, "tenant_id": tid}}


def _get(tid, headers=None):
    req_headers = {"Authorization": "Bearer faketoken"}
    if headers:
        req_headers.update(headers)
    return TestClient(app).get(f"/api/v1/tenants/{tid}/users", headers=req_headers)


def test_get_users_airline_admin_own_tenant(monkeypatch):
    db = _FakeDB()
    db._users["u1"] = {"uid": "u1", "email": "officer@taraair.com", "role": "AIRLINE_ADMIN",
                       "tenant_id": "tara-air", "created_at": _dt(1), "last_login": None}
    _patch_db(monkeypatch, db)
    _patch_user(monkeypatch, _user())

    resp = _get("tara-air")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["tenant_id"] == "tara-air"
    assert len(body["data"]["users"]) == 1
    assert body["data"]["users"][0]["email"] == "officer@taraair.com"
    assert body["data"]["users"][0]["role"] == "AIRLINE_ADMIN"
    assert body["data"]["users"][0]["createdAt"] is not None


def test_get_users_cross_tenant_denied(monkeypatch):
    _patch_db(monkeypatch, _FakeDB())
    _patch_user(monkeypatch, _user(tid="tara-air"))

    resp = _get("buddha-air")
    assert resp.status_code == 403


def test_get_users_super_admin_any_tenant(monkeypatch):
    db = _FakeDB()
    db._users["s1"] = {"uid": "s1", "email": "smd@caan.gov.np", "role": "SUPER_ADMIN",
                       "tenant_id": "buddha-air", "created_at": _dt(1), "last_login": None}
    _patch_db(monkeypatch, db)
    _patch_user(monkeypatch, _user(role="SUPER_ADMIN", tid=None, uid="s-admin", email="smd@caan.gov.np"))

    resp = _get("buddha-air")
    assert resp.status_code == 200
    assert len(resp.json()["data"]["users"]) == 1


def test_get_users_plain_user_denied(monkeypatch):
    _patch_db(monkeypatch, _FakeDB())
    _patch_user(monkeypatch, _user(role="USER", tid="tara-air", email="emp@taraair.com"))

    resp = _get("tara-air")
    assert resp.status_code == 403
