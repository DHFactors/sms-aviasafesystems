"""Phase 1: per-tenant survey rate-limit control.

Covers the Redis key shape (`rl:survey:{tenantId}:{date}`), per-tenant limit
resolution with global fallback, and the PUT /api/v1/tenants/{id}/config
endpoint (authz + validation + persistence).
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.middleware import rate_limit as rl


# ============================================================================
# Redis key shape + per-tenant limit resolution
# ============================================================================

def test_survey_redis_key_shape():
    key = rl._build_redis_key("survey_submit", "tara-air", "1.2.3.4", 86400)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert key == f"rl:survey:tara-air:{today}"


def test_survey_redis_key_anonymous_ip():
    key = rl._build_redis_key("survey_submit", None, "1.2.3.4", 86400)
    assert key.startswith("rl:survey:ip:1.2.3.4:")


def test_non_survey_redis_key_unchanged():
    key = rl._build_redis_key("mor_submit", "tara-air", "1.2.3.4", 86400)
    assert key.startswith("rl:mor_submit:tenant:tara-air:")


class _RateLimitDB:
    def __init__(self):
        self._tenants = {}

    def collection(self, name):
        class _Tenants:
            def __init__(self, db):
                self._db = db

            def document(self, tid):
                return _TenantRef(self._db, tid)
        if name == "tenants":
            return _Tenants(self)
        raise AssertionError(f"unexpected collection {name}")


class _TenantRef:
    def __init__(self, db, tid):
        self._db = db
        self._tid = tid

    def get(self):
        data = self._db._tenants.get(self._tid)
        if data is None:
            return _Doc(None, exists=False)
        return _Doc(data)


class _Doc:
    """Mimics the real Firestore DocumentSnapshot: get() raises KeyError when
    the field is missing, to_dict() returns the full data map."""

    def __init__(self, data, exists=True):
        self._data = data or {}
        self.exists = exists

    def get(self, field, default=None):
        if field is None:
            return self._data
        if field not in self._data:
            raise KeyError(f"'{field}' is not contained in the data")
        return self._data[field]

    def to_dict(self):
        return self._data


def test_resolve_limit_per_tenant_override(monkeypatch):
    db = _RateLimitDB()
    db._tenants["tara-air"] = {"config": {"survey_rate_limit": 25}}
    monkeypatch.setattr("app.middleware.rate_limit.get_db", lambda: db)
    count, window = rl._resolve_limit("survey_submit", "tara-air")
    assert (count, window) == (25, 86400)


def test_resolve_limit_falls_back_to_global(monkeypatch):
    db = _RateLimitDB()
    db._tenants["tara-air"] = {"config": {}}
    monkeypatch.setattr("app.middleware.rate_limit.get_db", lambda: db)
    count, _ = rl._resolve_limit("survey_submit", "tara-air")
    assert count == settings.SURVEY_RATE_LIMIT


def test_resolve_limit_missing_config_field(monkeypatch):
    db = _RateLimitDB()
    db._tenants["tara-air"] = {"tenant_id": "tara-air", "name": "Tara Air"}
    monkeypatch.setattr("app.middleware.rate_limit.get_db", lambda: db)
    count, _ = rl._resolve_limit("survey_submit", "tara-air")
    assert count == settings.SURVEY_RATE_LIMIT


def test_resolve_limit_unknown_tenant_falls_back(monkeypatch):
    db = _RateLimitDB()
    monkeypatch.setattr("app.middleware.rate_limit.get_db", lambda: db)
    count, _ = rl._resolve_limit("survey_submit", "ghost-air")
    assert count == settings.SURVEY_RATE_LIMIT


def test_resolve_limit_non_survey_unaffected(monkeypatch):
    db = _RateLimitDB()
    db._tenants["tara-air"] = {"config": {"survey_rate_limit": 25}}
    monkeypatch.setattr("app.middleware.rate_limit.get_db", lambda: db)
    count, window = rl._resolve_limit("mor_submit", "tara-air")
    assert (count, window) == (20, 86400)


# ============================================================================
# PUT /api/v1/tenants/{tenantId}/config
# ============================================================================

class _FakeAuditColl:
    def __init__(self, db):
        self._db = db

    def add(self, entry):
        self._db.audit_docs.append(dict(entry))
        return type("Ref", (), {"id": f"audit-{len(self._db.audit_docs)}"})()


class _FakeDB:
    def __init__(self):
        self._tenants = {}
        self.audit_docs = []

    def collection(self, name):
        if name == "tenants":
            return _TenantsColl(self)
        if name == "audit_logs":
            return _FakeAuditColl(self)
        raise AssertionError(f"unexpected collection {name}")


class _TenantsColl:
    def __init__(self, db):
        self._db = db

    def document(self, tid):
        return _TenantRef(self._db, tid)


class _TenantRef:
    def __init__(self, db, tid):
        self._db = db
        self._tid = tid

    def get(self):
        data = self._db._tenants.get(self._tid)
        if data is None:
            return _Doc(None, exists=False)
        return _Doc(data)

    def update(self, data):
        if self._tid not in self._db._tenants:
            self._db._tenants[self._tid] = {}
        self._db._tenants[self._tid].update(data)


def _patch_db(monkeypatch, db):
    monkeypatch.setattr("app.routes.tenants.get_db", lambda: db)
    monkeypatch.setattr("app.services.audit_service.get_db", lambda: db)
    monkeypatch.setattr("app.services.tenant_service.get_db", lambda: db)


def _patch_user(monkeypatch, user):
    """Make the real get_current_user dependency resolve from a fake token."""
    def _fake_verify_firebase_token(token):
        return {
            "uid": user["uid"],
            "email": user["email"],
            "role": user["role"],
            "tenant_id": user["tenant_id"],
        }
    monkeypatch.setattr("app.middleware.auth.verify_firebase_token", _fake_verify_firebase_token)


def _admin(tid="tara-air"):
    return {
        "uid": "u1", "email": "officer@taraair.com",
        "role": "AIRLINE_ADMIN", "tenant_id": tid,
        "claims": {"role": "AIRLINE_ADMIN", "tenant_id": tid},
    }


def _put(tid, body, headers=None):
    req_headers = {"Authorization": "Bearer faketoken"}
    if headers:
        req_headers.update(headers)
    return TestClient(app).put(f"/api/v1/tenants/{tid}/config", json=body, headers=req_headers)


def test_put_config_success(monkeypatch):
    db = _FakeDB()
    db._tenants["tara-air"] = {"tenant_id": "tara-air", "config": {"survey_rate_limit": 5}}
    _patch_db(monkeypatch, db)
    _patch_user(monkeypatch, _admin())

    resp = _put("tara-air", {"survey_rate_limit": 25})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["tenant_id"] == "tara-air"
    assert body["data"]["config"]["survey_rate_limit"] == 25
    assert db._tenants["tara-air"]["config"]["survey_rate_limit"] == 25
    assert db.audit_docs and db.audit_docs[0]["action"] == "TENANT_CONFIG_UPDATED"


def test_put_config_preserves_existing_keys(monkeypatch):
    db = _FakeDB()
    db._tenants["tara-air"] = {"config": {"survey_rate_limit": 5, "survey_instructions": "Please answer honestly"}}
    _patch_db(monkeypatch, db)
    _patch_user(monkeypatch, _admin())

    resp = _put("tara-air", {"survey_rate_limit": 50})
    assert resp.status_code == 200
    assert db._tenants["tara-air"]["config"]["survey_instructions"] == "Please answer honestly"
    assert db._tenants["tara-air"]["config"]["survey_rate_limit"] == 50


def test_put_config_creates_config_when_missing(monkeypatch):
    db = _FakeDB()
    db._tenants["tara-air"] = {"tenant_id": "tara-air", "name": "Tara Air"}
    _patch_db(monkeypatch, db)
    _patch_user(monkeypatch, _admin())

    resp = _put("tara-air", {"survey_rate_limit": 10})
    assert resp.status_code == 200
    assert db._tenants["tara-air"]["config"]["survey_rate_limit"] == 10


def test_put_config_wrong_tenant_denied(monkeypatch):
    db = _FakeDB()
    db._tenants["tara-air"] = {"config": {}}
    db._tenants["other-air"] = {"config": {}}
    _patch_db(monkeypatch, db)
    _patch_user(monkeypatch, _admin("tara-air"))

    resp = _put("other-air", {"survey_rate_limit": 10})
    assert resp.status_code == 403


def test_put_config_cross_role_denied(monkeypatch):
    db = _FakeDB()
    db._tenants["tara-air"] = {"config": {}}
    _patch_db(monkeypatch, db)
    super_admin = {
        "uid": "s1", "email": "smd@caan.gov.np",
        "role": "SUPER_ADMIN", "tenant_id": None,
        "claims": {"role": "SUPER_ADMIN"},
    }
    _patch_user(monkeypatch, super_admin)

    resp = _put("tara-air", {"survey_rate_limit": 10})
    assert resp.status_code == 403


def test_put_config_invalid_value(monkeypatch):
    _patch_db(monkeypatch, _FakeDB())
    _patch_user(monkeypatch, _admin())

    resp = _put("tara-air", {"survey_rate_limit": 7})
    assert resp.status_code == 422


def test_put_config_unknown_tenant(monkeypatch):
    _patch_db(monkeypatch, _FakeDB())
    _patch_user(monkeypatch, _admin("ghost-air"))

    resp = _put("ghost-air", {"survey_rate_limit": 10})
    assert resp.status_code == 404


def test_put_config_full_survey_management(monkeypatch):
    """PUT persists rate limit, instructions, dates and the active override,
    and keeps the camelCase surveyConfig mirror in sync."""
    db = _FakeDB()
    db._tenants["tara-air"] = {"tenant_id": "tara-air", "config": {"survey_rate_limit": 5}}
    _patch_db(monkeypatch, db)
    _patch_user(monkeypatch, _admin())

    body = {
        "survey_rate_limit": 50,
        "survey_instructions": "Please answer honestly",
        "survey_open_date": "2026-09-01",
        "survey_close_date": "2026-09-30",
        "is_survey_active": True,
    }
    resp = _put("tara-air", body)
    assert resp.status_code == 200
    config = resp.json()["data"]["config"]
    assert config["survey_rate_limit"] == 50
    assert config["survey_instructions"] == "Please answer honestly"
    assert config["survey_open_date"] == "2026-09-01"
    assert config["survey_close_date"] == "2026-09-30"
    assert config["is_survey_active"] is True

    stored = db._tenants["tara-air"]
    assert stored["config"]["survey_open_date"] == "2026-09-01"
    assert stored["config"]["survey_close_date"] == "2026-09-30"
    assert stored["config"]["is_survey_active"] is True
    assert stored["surveyConfig"]["openDate"] == "2026-09-01"
    assert stored["surveyConfig"]["closeDate"] == "2026-09-30"
    assert stored["surveyConfig"]["isActive"] is True


def test_put_config_safety_role_allowed(monkeypatch):
    """The 'safety' role is a valid Safety Manager role for the tenant."""
    db = _FakeDB()
    db._tenants["tara-air"] = {"tenant_id": "tara-air", "config": {}}
    _patch_db(monkeypatch, db)
    _patch_user(monkeypatch, {
        "uid": "u9", "email": "safety@taraair.com",
        "role": "safety", "tenant_id": "tara-air",
        "claims": {"role": "safety", "tenant_id": "tara-air"},
    })

    resp = _put("tara-air", {"survey_rate_limit": 10, "is_survey_active": True})
    assert resp.status_code == 200
    assert db._tenants["tara-air"]["config"]["is_survey_active"] is True


def test_put_config_close_before_open_rejected(monkeypatch):
    db = _FakeDB()
    db._tenants["tara-air"] = {"tenant_id": "tara-air", "config": {}}
    _patch_db(monkeypatch, db)
    _patch_user(monkeypatch, _admin())

    resp = _put("tara-air", {
        "survey_rate_limit": 10,
        "survey_open_date": "2026-09-30",
        "survey_close_date": "2026-09-01",
    })
    assert resp.status_code == 422


def test_put_config_invalid_date_rejected(monkeypatch):
    db = _FakeDB()
    db._tenants["tara-air"] = {"tenant_id": "tara-air", "config": {}}
    _patch_db(monkeypatch, db)
    _patch_user(monkeypatch, _admin())

    resp = _put("tara-air", {
        "survey_rate_limit": 10,
        "survey_open_date": "not-a-date",
        "survey_close_date": "2026-09-30",
    })
    assert resp.status_code == 422


def test_put_config_clears_dates_and_closes(monkeypatch):
    """Explicit empty dates remove the survey window and close the survey."""
    db = _FakeDB()
    db._tenants["tara-air"] = {
        "config": {
            "survey_rate_limit": 10,
            "survey_open_date": "2026-08-01",
            "survey_close_date": "2026-08-31",
            "is_survey_active": True,
        },
        "surveyConfig": {"openDate": "2026-08-01", "closeDate": "2026-08-31", "isActive": True},
    }
    _patch_db(monkeypatch, db)
    _patch_user(monkeypatch, _admin())

    resp = _put("tara-air", {
        "survey_rate_limit": 10,
        "survey_open_date": "",
        "survey_close_date": "",
        "is_survey_active": False,
    })
    assert resp.status_code == 200
    config = db._tenants["tara-air"]["config"]
    assert "survey_open_date" not in config
    assert "survey_close_date" not in config
    assert config["is_survey_active"] is False

    survey_config = db._tenants["tara-air"]["surveyConfig"]
    assert "openDate" not in survey_config
    assert "closeDate" not in survey_config
    assert survey_config["isActive"] is False


def test_put_config_preserves_legacy_survey_window(monkeypatch):
    """A PUT that only touches the rate limit leaves the legacy surveyConfig
    window (openDate/closeDate) intact."""
    db = _FakeDB()
    db._tenants["tara-air"] = {
        "config": {"survey_rate_limit": 5},
        "surveyConfig": {"openDate": "2026-08-01T00:00:00Z", "closeDate": "2026-08-31T23:59:59Z"},
    }
    _patch_db(monkeypatch, db)
    _patch_user(monkeypatch, _admin())

    resp = _put("tara-air", {"survey_rate_limit": 25})
    assert resp.status_code == 200
    survey_config = db._tenants["tara-air"]["surveyConfig"]
    assert survey_config["openDate"] == "2026-08-01T00:00:00Z"
    assert survey_config["closeDate"] == "2026-08-31T23:59:59Z"


def test_put_config_buddha_air_manager_tenant_isolation(monkeypatch):
    """A buddha-air Safety Manager can open/close their own survey but must not
    affect other tenants (verification scenario)."""
    db = _FakeDB()
    db._tenants["buddha-air"] = {"tenant_id": "buddha-air", "config": {"survey_rate_limit": 5}}
    db._tenants["tara-air"] = {"tenant_id": "tara-air", "config": {"survey_rate_limit": 5}}
    _patch_db(monkeypatch, db)
    _patch_user(monkeypatch, {
        "uid": "u-buddha", "email": "safety@buddha-air.com",
        "role": "AIRLINE_ADMIN", "tenant_id": "buddha-air",
        "claims": {"role": "AIRLINE_ADMIN", "tenant_id": "buddha-air"},
    })

    # Opens their own survey.
    resp = _put("buddha-air", {
        "survey_rate_limit": 25,
        "survey_open_date": "2026-09-01",
        "survey_close_date": "2026-09-30",
        "is_survey_active": True,
    })
    assert resp.status_code == 200
    buddha = db._tenants["buddha-air"]
    assert buddha["config"]["is_survey_active"] is True
    assert buddha["surveyConfig"]["openDate"] == "2026-09-01"

    # Cannot touch another tenant.
    resp = _put("tara-air", {"survey_rate_limit": 25})
    assert resp.status_code == 403
    assert db._tenants["tara-air"]["config"]["survey_rate_limit"] == 5


# ============================================================================
# GET /api/v1/tenants/{tenantId}/config (Phase 3, auth optional)
# ============================================================================

def _get(tid, headers=None):
    return TestClient(app).get(f"/api/v1/tenants/{tid}/config", headers=headers)


def test_get_config_authenticated(monkeypatch):
    db = _FakeDB()
    db._tenants["tara-air"] = {
        "name": "Tara Air",
        "config": {"survey_rate_limit": 25, "survey_instructions": "Please answer honestly"},
        "surveyConfig": {"openDate": "2026-08-01T00:00:00Z", "closeDate": "2026-08-31T23:59:59Z"},
    }
    _patch_db(monkeypatch, db)
    _patch_user(monkeypatch, _admin())

    resp = _get("tara-air", headers={"Authorization": "Bearer faketoken"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["tenant_id"] == "tara-air"
    assert body["data"]["name"] == "Tara Air"
    assert body["data"]["config"]["survey_rate_limit"] == 25
    assert body["data"]["config"]["survey_instructions"] == "Please answer honestly"
    assert body["data"]["surveyConfig"]["openDate"] == "2026-08-01T00:00:00Z"
    assert body["data"]["surveyConfig"]["closeDate"] == "2026-08-31T23:59:59Z"


def test_get_config_no_auth_allowed(monkeypatch):
    """The public survey page reads instructions without a login."""
    db = _FakeDB()
    db._tenants["tara-air"] = {"config": {"survey_instructions": "Read the manual first"}}
    _patch_db(monkeypatch, db)

    resp = _get("tara-air")
    assert resp.status_code == 200
    assert resp.json()["data"]["config"]["survey_instructions"] == "Read the manual first"


def test_get_config_missing_config_map(monkeypatch):
    """Tenant doc without a config field returns an empty config map."""
    db = _FakeDB()
    db._tenants["tara-air"] = {"tenant_id": "tara-air", "name": "Tara Air"}
    _patch_db(monkeypatch, db)

    resp = _get("tara-air")
    assert resp.status_code == 200
    assert resp.json()["data"]["config"] == {}


def test_get_config_unknown_tenant(monkeypatch):
    _patch_db(monkeypatch, _FakeDB())

    resp = _get("ghost-air")
    assert resp.status_code == 404
