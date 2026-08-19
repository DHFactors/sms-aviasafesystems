"""Self-service tenant registration + team-member onboarding (2026-08).

Covers:
  * POST /api/v1/auth/register-tenant  (slugification, claims assignment,
    operational-profile initialisation, invite-code issuance, beta access key)
  * POST /api/v1/auth/join-team        (invite-code / tenant-id resolution,
    department applicability, claim assignment)
  * GET  /api/v1/auth/tenant-lookup    (dynamic department dropdown data)

The classification -> department rules are asserted against the codified
OperationalScope model (app/models/tenant_profile.py): an AMO registers with
Part-145 + QA (no flight ops / CAMO); an aerodrome with airside + ARFF.
"""

import re

from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.services.tenant_registration import (
    DEPARTMENT_LABELS,
    slugify_organization,
    MIN_PASSWORD_LENGTH,
)


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

    def set(self, data):
        self._db.tenants[self._tid] = dict(data)

    def update(self, data):
        if self._tid not in self._db.tenants:
            self._db.tenants[self._tid] = {}
        self._db.tenants[self._tid].update(dict(data))

    def collection(self, name):
        assert name == "profile", f"unexpected subcollection {name}"
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

    def get_user(self, uid):
        if uid not in self.records:
            raise ValueError(f"no user {uid}")
        return type("U", (), {"uid": uid, "email": self.records[uid].get("email")})()


def _patch(monkeypatch, db, auth=None):
    monkeypatch.setattr("app.firebase.get_db", lambda: db)
    monkeypatch.setattr("app.routes.auth.get_db", lambda: db)
    monkeypatch.setattr("app.services.tenant_registration.get_db", lambda: db)
    monkeypatch.setattr("app.services.users.get_db", lambda: db)
    monkeypatch.setattr("app.services.audit_service.get_db", lambda: db)
    if auth is not None:
        monkeypatch.setattr("app.firebase.get_auth", lambda: auth)
        monkeypatch.setattr("app.services.tenant_registration.get_auth", lambda: auth)


def _register_body(org="Summit Air", classification="AIRLINE_FIXED_WING", **overrides):
    body = {
        "organization_name": org,
        "classification": classification,
        "admin_full_name": "Anil Shrestha",
        "admin_title": "Safety Manager",
        "email": "safety@summitair.com",
        "password": "Summit-Safety-2026",
        "confirm_password": "Summit-Safety-2026",
        "beta_access_key": settings.BETA_ACCESS_KEY,
    }
    body.update(overrides)
    return body


def _seed_tenant(db, tid="yeti-airlines", name="Yeti Airlines",
                 classification="AIRLINE_FIXED_WING",
                 departments=None, invite_code="ABC123"):
    db.tenants[tid] = {
        "tenant_id": tid,
        "name": name,
        "tenant_type": classification,
        "classification": classification,
        "applicable_departments": departments or ["safety", "flight_ops", "camo", "qa"],
        "team_invite_code": invite_code,
        "operates_flights": classification in ("AIRLINE_FIXED_WING", "AIRLINE_ROTARY"),
    }
    return db.tenants[tid]


# ============================================================================
# Slugification
# ============================================================================

def test_slugify_organization():
    assert slugify_organization("Summit Air") == "summit-air"
    assert slugify_organization("Yeti Airlines") == "yeti-airlines"
    assert slugify_organization("Simrik Heli  LTD.") == "simrik-heli-ltd"
    assert slugify_organization("  ") == "organization"


# ============================================================================
# POST /api/v1/auth/register-tenant
# ============================================================================

def test_register_tenant_fixed_wing(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)

    resp = TestClient(app).post("/api/v1/auth/register-tenant", json=_register_body())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["tenant_id"] == "summit-air"
    assert body["classification"] == "AIRLINE_FIXED_WING"
    assert body["operates_flights"] is True
    assert body["applicable_departments"] == ["safety", "flight_ops", "camo", "qa"]
    assert body["admin_email"] == "safety@summitair.com"

    uid = list(auth.claims)[0]
    assert auth.claims[uid] == {
        "role": "AIRLINE_ADMIN",
        "tenant_id": "summit-air",
        "department": "safety",
    }

    tenant = db.tenants["summit-air"]
    assert tenant["name"] == "Summit Air"
    assert tenant["safety_manager"]["email"] == "safety@summitair.com"
    assert tenant["safety_manager"]["title"] == "Safety Manager"

    profile = db.profiles["summit-air"]["operational"]
    assert profile["scope"] == "AIRLINE_FIXED_WING"
    assert profile["tenant_type"] == "AIRLINE_FIXED_WING"
    assert profile["operates_flights"] is True
    assert profile["applicable_departments"] == ["safety", "flight_ops", "camo", "qa"]

    user_doc = list(db.users.values())[0]
    assert user_doc["role"] == "AIRLINE_ADMIN"
    assert user_doc["tenant_id"] == "summit-air"
    assert user_doc["department"] == "safety"

    assert db.audit and db.audit[0]["action"] == "TENANT_REGISTERED"


def test_register_tenant_issues_6char_invite_code(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())

    resp = TestClient(app).post("/api/v1/auth/register-tenant", json=_register_body())
    assert resp.status_code == 200, resp.text
    code = resp.json()["team_invite_code"]
    assert re.fullmatch(r"[A-Z0-9]{6}", code), code
    assert db.tenants["summit-air"]["team_invite_code"] == code


def test_register_tenant_amo_profile(monkeypatch):
    """An AMO registers with only non-flight taxonomy + Part-145/QA departments."""
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())

    resp = TestClient(app).post(
        "/api/v1/auth/register-tenant",
        json=_register_body(org="Kathmandu MRO", classification="AMO",
                            email="info@ktm-mro.com"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tenant_id"] == "kathmandu-mro"
    assert body["operates_flights"] is False
    depts = body["applicable_departments"]
    assert depts == ["safety", "maintenance_145", "qa"]
    assert "flight_ops" not in depts
    assert "camo" not in depts
    assert "maintenance_145" in depts
    assert "qa" in depts

    profile = db.profiles["kathmandu-mro"]["operational"]
    assert profile["operates_flights"] is False
    assert profile["applicable_departments"] == ["safety", "maintenance_145", "qa"]
    assert db.tenants["kathmandu-mro"]["operates_flights"] is False


def test_register_tenant_aerodrome_profile(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())

    resp = TestClient(app).post(
        "/api/v1/auth/register-tenant",
        json=_register_body(org="Pokhara Aerodrome", classification="AERODROME",
                            email="ops@pokhara-aero.com"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["operates_flights"] is False
    assert body["applicable_departments"] == ["safety", "airside_ops", "arff"]


def test_register_tenant_invalid_classification(monkeypatch):
    _patch(monkeypatch, _FakeDB(), _FakeAuth())
    resp = TestClient(app).post(
        "/api/v1/auth/register-tenant",
        json=_register_body(classification="REGULATOR"),
    )
    assert resp.status_code == 422


def test_register_tenant_wrong_beta_access_key(monkeypatch):
    _patch(monkeypatch, _FakeDB(), _FakeAuth())
    resp = TestClient(app).post(
        "/api/v1/auth/register-tenant",
        json=_register_body(beta_access_key="NOT-THE-KEY"),
    )
    assert resp.status_code == 403
    assert "beta access key" in resp.json()["detail"].lower()


def test_register_tenant_blank_access_key_uses_default(monkeypatch):
    # Beta sandbox: the access key is optional (blank falls back to default).
    monkeypatch.setattr(settings, "ENVIRONMENT", "beta")
    _patch(monkeypatch, _FakeDB(), _FakeAuth())
    resp = TestClient(app).post(
        "/api/v1/auth/register-tenant",
        json=_register_body(beta_access_key=""),
    )
    assert resp.status_code == 200, resp.text


def test_register_tenant_production_requires_access_key(monkeypatch):
    # Production gate: self-service registration is by invitation only — a valid
    # enterprise access code is mandatory, blank is rejected.
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    _patch(monkeypatch, _FakeDB(), _FakeAuth())
    resp = TestClient(app).post(
        "/api/v1/auth/register-tenant",
        json=_register_body(beta_access_key=""),
    )
    assert resp.status_code == 403
    assert "beta access key" in resp.json()["detail"].lower()

    resp = TestClient(app).post(
        "/api/v1/auth/register-tenant",
        json=_register_body(beta_access_key="NOT-THE-KEY"),
    )
    assert resp.status_code == 403

    resp = TestClient(app).post(
        "/api/v1/auth/register-tenant",
        json=_register_body(beta_access_key=settings.BETA_ACCESS_KEY),
    )
    assert resp.status_code == 200, resp.text


def test_register_tenant_beta_tags_sandbox(monkeypatch):
    """Beta self-service tenants are tagged for sandbox cleanup."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "beta")
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    resp = TestClient(app).post("/api/v1/auth/register-tenant", json=_register_body())
    assert resp.status_code == 200, resp.text
    tenant = db.tenants["summit-air"]
    assert tenant["is_beta_sandbox"] is True
    assert tenant["auto_expire_days"] == 30


def test_register_tenant_production_not_sandbox_tagged(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    resp = TestClient(app).post(
        "/api/v1/auth/register-tenant", json=_register_body()
    )
    assert resp.status_code == 200, resp.text
    tenant = db.tenants["summit-air"]
    assert "is_beta_sandbox" not in tenant
    assert "auto_expire_days" not in tenant


def test_register_tenant_password_mismatch(monkeypatch):
    _patch(monkeypatch, _FakeDB(), _FakeAuth())
    resp = TestClient(app).post(
        "/api/v1/auth/register-tenant",
        json=_register_body(confirm_password="different-pass"),
    )
    assert resp.status_code == 422


def test_register_tenant_short_password_rejected(monkeypatch):
    _patch(monkeypatch, _FakeDB(), _FakeAuth())
    resp = TestClient(app).post(
        "/api/v1/auth/register-tenant",
        json=_register_body(password="short", confirm_password="short"),
    )
    assert resp.status_code == 422
    assert f"at least {MIN_PASSWORD_LENGTH}" in resp.json()["detail"]


def test_register_tenant_duplicate_slug_gets_suffix(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    db.tenants["summit-air"] = {"tenant_id": "summit-air", "name": "Existing Summit Air"}

    resp = TestClient(app).post("/api/v1/auth/register-tenant", json=_register_body())
    assert resp.status_code == 200, resp.text
    assert resp.json()["tenant_id"] == "summit-air-2"


def test_register_tenant_duplicate_email_rejected(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)

    # Pre-existing account with the same email causes create_user to fail.
    def _fail_duplicate(**kw):
        if kw.get("email") == "safety@summitair.com":
            raise ValueError("The email address is already in use by another account.")
        return type("U", (), {"uid": "u-x", "email": kw.get("email")})()

    monkeypatch.setattr(auth, "create_user", _fail_duplicate)

    resp = TestClient(app).post("/api/v1/auth/register-tenant", json=_register_body())
    assert resp.status_code == 422
    assert "already exists" in resp.json()["detail"]


# ============================================================================
# POST /api/v1/auth/join-team
# ============================================================================

def _join_body(tid="yeti-airlines", department="flight_ops", invite_code="ABC123", **overrides):
    body = {
        "invite_code": invite_code,
        "full_name": "Rajesh Thapa",
        "email": "ops@yetiairlines.com",
        "password": "Ops-2026-Password",
        "confirm_password": "Ops-2026-Password",
        "department": department,
    }
    body.update(overrides)
    if tid:
        body["tenant_id"] = tid
    return body


def test_join_team_by_invite_code(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)
    _seed_tenant(db)

    resp = TestClient(app).post("/api/v1/auth/join-team", json=_join_body())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["tenant_id"] == "yeti-airlines"
    assert body["tenant_name"] == "Yeti Airlines"
    assert body["department"] == "flight_ops"
    assert body["department_label"] == "Flight Operations"

    uid = list(auth.claims)[0]
    assert auth.claims[uid] == {
        "role": "USER",
        "tenant_id": "yeti-airlines",
        "department": "Flight Operations",
    }
    user_doc = list(db.users.values())[0]
    assert user_doc["role"] == "USER"
    assert user_doc["department"] == "Flight Operations"
    assert db.audit and db.audit[0]["action"] == "TEAM_MEMBER_JOINED"


def test_join_team_camo_department_label(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)
    _seed_tenant(db)

    resp = TestClient(app).post(
        "/api/v1/auth/join-team",
        json=_join_body(department="camo", email="camo@yetiairlines.com"),
    )
    assert resp.status_code == 200, resp.text
    uid = list(auth.claims)[0]
    assert auth.claims[uid]["department"] == "CAMO"


def test_join_team_part145_department_label(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)
    _seed_tenant(db, tid="ktm-mro", name="KTM MRO",
                classification="AMO",
                departments=["safety", "maintenance_145", "qa"],
                invite_code="MRO000")

    resp = TestClient(app).post(
        "/api/v1/auth/join-team",
        json=_join_body(tid="ktm-mro", invite_code="MRO000",
                        department="maintenance_145", email="145@ktm-mro.com"),
    )
    assert resp.status_code == 200, resp.text
    uid = list(auth.claims)[0]
    assert auth.claims[uid]["department"] == "Part-145"


def test_join_team_by_tenant_id_without_code(monkeypatch):
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)
    _seed_tenant(db)

    resp = TestClient(app).post(
        "/api/v1/auth/join-team",
        json=_join_body(invite_code=None),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["tenant_id"] == "yeti-airlines"


def test_join_team_amo_rejects_flight_departments(monkeypatch):
    """An AMO must not be able to join as Flight Ops / CAMO."""
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)
    _seed_tenant(db, tid="ktm-mro", name="KTM MRO",
                classification="AMO",
                departments=["safety", "maintenance_145", "qa"],
                invite_code="MRO000")

    for dept in ("flight_ops", "camo"):
        resp = TestClient(app).post(
            "/api/v1/auth/join-team",
            json=_join_body(tid="ktm-mro", invite_code="MRO000", department=dept),
        )
        assert resp.status_code == 422, dept
    assert not auth.claims

    resp = TestClient(app).post(
        "/api/v1/auth/join-team",
        json=_join_body(tid="ktm-mro", invite_code="MRO000", department="maintenance_145"),
    )
    assert resp.status_code == 200, resp.text


def test_join_team_unknown_invite_code(monkeypatch):
    _patch(monkeypatch, _FakeDB(), _FakeAuth())
    resp = TestClient(app).post("/api/v1/auth/join-team", json=_join_body(invite_code="ZZZZZZ"))
    assert resp.status_code == 404


def test_join_team_unknown_tenant_id(monkeypatch):
    _patch(monkeypatch, _FakeDB(), _FakeAuth())
    resp = TestClient(app).post("/api/v1/auth/join-team", json=_join_body(tid="ghost-air"))
    assert resp.status_code == 404


def test_join_team_password_mismatch(monkeypatch):
    _patch(monkeypatch, _FakeDB(), _FakeAuth())
    resp = TestClient(app).post(
        "/api/v1/auth/join-team",
        json=_join_body(confirm_password="different-pass"),
    )
    assert resp.status_code == 422


def test_join_team_missing_locator(monkeypatch):
    _patch(monkeypatch, _FakeDB(), _FakeAuth())
    resp = TestClient(app).post(
        "/api/v1/auth/join-team",
        json=_join_body(tid=None, invite_code=None),
    )
    assert resp.status_code == 422


def test_join_team_mismatched_invite_code_rejected(monkeypatch):
    """A tenant_id with a non-matching invite code must not join."""
    db = _FakeDB()
    auth = _FakeAuth()
    _patch(monkeypatch, db, auth)
    _seed_tenant(db, invite_code="ABC123")

    resp = TestClient(app).post(
        "/api/v1/auth/join-team",
        json=_join_body(tid="yeti-airlines", invite_code="ZZZ999"),
    )
    assert resp.status_code == 404
    assert not auth.claims


# ============================================================================
# GET /api/v1/auth/tenant-lookup
# ============================================================================

def test_tenant_lookup_by_invite_code(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db, invite_code="ABC123")

    resp = TestClient(app).get("/api/v1/auth/tenant-lookup?code=abc123")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_id"] == "yeti-airlines"
    assert body["tenant_name"] == "Yeti Airlines"
    assert body["classification"] == "AIRLINE_FIXED_WING"
    codes = [d["code"] for d in body["applicable_departments"]]
    assert codes == ["safety", "flight_ops", "camo", "qa"]
    labels = {d["code"]: d["label"] for d in body["applicable_departments"]}
    assert labels["flight_ops"] == "Flight Operations"
    assert labels["camo"] == "CAMO"
    assert labels["qa"] == "QA"


def test_tenant_lookup_by_tenant_id(monkeypatch):
    db = _FakeDB()
    _patch(monkeypatch, db, _FakeAuth())
    _seed_tenant(db, tid="pokhara-aerodrome", name="Pokhara Aerodrome",
                classification="AERODROME",
                departments=["safety", "airside_ops", "arff"], invite_code="AERO00")

    resp = TestClient(app).get("/api/v1/auth/tenant-lookup?tenant_id=pokhara-aerodrome")
    assert resp.status_code == 200
    body = resp.json()
    codes = [d["code"] for d in body["applicable_departments"]]
    assert codes == ["safety", "airside_ops", "arff"]
    assert body["operates_flights"] is False


def test_tenant_lookup_unknown_invite_code(monkeypatch):
    _patch(monkeypatch, _FakeDB(), _FakeAuth())
    resp = TestClient(app).get("/api/v1/auth/tenant-lookup?code=ZZZZZZ")
    assert resp.status_code == 404


def test_tenant_lookup_requires_locator(monkeypatch):
    _patch(monkeypatch, _FakeDB(), _FakeAuth())
    resp = TestClient(app).get("/api/v1/auth/tenant-lookup")
    assert resp.status_code == 422


# ============================================================================
# Department label conventions align with the frontend routing contract
# ============================================================================

def test_department_labels_align_with_seed_conventions():
    assert DEPARTMENT_LABELS["flight_ops"] == "Flight Operations"
    assert DEPARTMENT_LABELS["camo"] == "CAMO"
    assert DEPARTMENT_LABELS["maintenance_145"] == "Part-145"