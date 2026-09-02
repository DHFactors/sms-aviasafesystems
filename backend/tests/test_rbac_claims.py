"""RBAC claims for the simplified credential scheme (2026-08).

Verifies the security-domain rules applied by seed config + provisioning:

  safety@{tenant}.com  -> AIRLINE_ADMIN  (full tenant dashboard)
  camo@{tenant}.com    -> USER  / CAMO
  145@{tenant}.com     -> USER  / Part-145
  ops@{tenant}.com     -> USER  / Flight Operations

Extended six-role scheme (2026-08-21) for fishtail-air / summit-air:
  ae@{domain}          -> AIRLINE_ADMIN (Accountable Executive)
  pilot@{domain}       -> USER  / Line Crew

and the resulting frontend routing contract (getRoleDestination in
public/js/firebase.js): USER accounts with a department claim route to the
responsible-manager dashboard, everything else to the full dashboard.
"""

import pytest

from seed.config import (
    OPERATOR_PROFILES,
    SIMPLIFIED_ROLE_ACCOUNTS,
    EXTENDED_ROLE_TENANT_IDS,
    CREDENTIAL_EMAIL_DOMAINS,
    simplified_email,
    roles_for_tenant,
    build_simplified_role_plan,
)

EXPECTED_ROLE_RULES = {
    "safety": ("AIRLINE_ADMIN", ""),
    "camo": ("USER", "CAMO"),
    "145": ("USER", "Part-145"),
    "ops": ("USER", "Flight Operations"),
}


def _rule(token):
    return next(r for r in SIMPLIFIED_ROLE_ACCOUNTS if r["token"] == token)


# ============================================================================
# Security-domain config
# ============================================================================

def test_simplified_role_accounts_match_security_domain():
    tokens = {r["token"] for r in SIMPLIFIED_ROLE_ACCOUNTS}
    assert tokens == set(EXPECTED_ROLE_RULES)
    for token, (role, dept) in EXPECTED_ROLE_RULES.items():
        r = _rule(token)
        assert r["app_role"] == role, token
        assert r.get("department") == dept, token


def test_every_operator_has_all_role_accounts():
    assert set(CREDENTIAL_EMAIL_DOMAINS) == {op["id"] for op in OPERATOR_PROFILES}
    assert len(OPERATOR_PROFILES) == 11
    plan = build_simplified_role_plan()
    expected_accounts = sum(len(roles_for_tenant(op["id"])) for op in OPERATOR_PROFILES)
    assert len(plan) == expected_accounts
    for op in OPERATOR_PROFILES:
        for token in EXPECTED_ROLE_RULES:
            email = simplified_email(token, op["id"])
            assert email == f"{token}@{CREDENTIAL_EMAIL_DOMAINS[op['id']]}"


def test_extended_operators_provision_ae_and_pilot_accounts():
    """fishtail-air / summit-air carry the six-role scheme (AE + Line Pilot)."""
    plan = build_simplified_role_plan()
    for tid in EXTENDED_ROLE_TENANT_IDS:
        entries = {e["token"]: e for e in plan if e["op_id"] == tid}
        assert {"ae", "pilot"} <= set(entries), tid

        ae = entries["ae"]
        assert ae["app_role"] == "AIRLINE_ADMIN"
        assert ae["department"] == ""
        pilot = entries["pilot"]
        assert pilot["app_role"] == "USER"
        assert pilot["department"] == "Line Crew"

    # Non-extended operators never receive AE / Pilot accounts.
    for op in OPERATOR_PROFILES:
        if op["id"] in EXTENDED_ROLE_TENANT_IDS:
            continue
        tokens = {e["token"] for e in plan if e["op_id"] == op["id"]}
        assert tokens == set(EXPECTED_ROLE_RULES), op["id"]


def test_example_accounts_from_scheme_doc():
    assert simplified_email("safety", "buddha-air") == "safety@buddha-air.com"
    assert simplified_email("camo", "ktm-mro") == "camo@ktm-mro.com"
    assert simplified_email("145", "ktm-mro") == "145@ktm-mro.com"
    assert simplified_email("ops", "air-dynasty") == "ops@air-dynasty.com"


# ============================================================================
# Frontend routing contract (mirror of public/js/firebase.js getRoleDestination)
# ============================================================================

def _route(user):
    role = user.get("role") or "USER"
    if role == "SUPER_ADMIN":
        return "/admin/dashboard.html"
    if role == "CAAN_SMD":
        return "/caan.html"
    if role == "USER":
        department = user.get("department") or ""
        if department:
            return "/dashboard/responsible-manager.html"
        return "/safety.html"
    return "/safety.html"


def test_safety_routes_to_full_dashboard():
    r = _rule("safety")
    assert r["app_role"] == "AIRLINE_ADMIN"
    assert r.get("department") == ""
    assert _route({"role": "AIRLINE_ADMIN", "department": ""}) == "/safety.html"


@pytest.mark.parametrize("token,op_id,expected_email", [
    ("camo", "ktm-mro", "camo@ktm-mro.com"),
    ("145", "ktm-mro", "145@ktm-mro.com"),
    ("ops", "air-dynasty", "ops@air-dynasty.com"),
])
def test_department_roles_route_to_responsible_manager(token, op_id, expected_email):
    r = _rule(token)
    assert r["app_role"] == "USER"
    assert r.get("department")
    assert _route({"role": "USER", "department": r["department"]}) \
        == "/dashboard/responsible-manager.html"
    assert simplified_email(token, op_id) == expected_email


# ============================================================================
# Claim assignment in the Auth-provisioning layer (seed.users.create_user)
# ============================================================================

class _FakeAuth:
    def __init__(self):
        self.records = {}
        self.claims = {}
        self.updates = {}

    def get_user(self, uid):
        if uid not in self.records:
            raise ValueError(f"no user {uid}")
        return type("U", (), {"uid": uid, "email": self.records[uid]["email"]})()

    def create_user(self, **kw):
        self.records[kw["uid"]] = kw
        return type("U", (), {"uid": kw["uid"], "email": kw["email"]})()

    def update_user(self, uid, password=None, **kw):
        self.updates[uid] = kw
        if password is not None:
            self.records[uid]["password"] = password

    def set_custom_user_claims(self, uid, claims):
        self.claims[uid] = dict(claims)


def test_create_user_sets_department_claim():
    from seed.users import create_user

    auth = _FakeAuth()
    spec = {
        "uid": "ops-tara-air-001",
        "email": "ops@tara-air.com",
        "password": "TARA-Ops-2026",
        "full_name": "Operations Manager (Tara Air)",
        "role": "USER",
        "tenant_id": "tara-air",
        "department": "Flight Operations",
    }
    out = create_user(auth, spec)
    assert auth.claims["ops-tara-air-001"] == {
        "role": "USER", "tenant_id": "tara-air", "department": "Flight Operations",
    }
    assert out["department"] == "Flight Operations"


def test_create_user_omits_claim_when_no_department():
    from seed.users import create_user

    auth = _FakeAuth()
    spec = {
        "uid": "safety-tara-air-001",
        "email": "safety@tara-air.com",
        "password": "TARA-Safety-2026",
        "full_name": "Safety Manager (Tara Air)",
        "role": "AIRLINE_ADMIN",
        "tenant_id": "tara-air",
        "department": "",
    }
    create_user(auth, spec)
    assert auth.claims["safety-tara-air-001"] == {"role": "AIRLINE_ADMIN", "tenant_id": "tara-air"}


def test_create_user_sets_is_developer_claim():
    from seed.users import create_user

    auth = _FakeAuth()
    spec = {
        "uid": "dev-001",
        "email": "ezondiza.dhf@gmail.com",
        "password": "DEV-Aviasafe-2026",
        "full_name": "Developer",
        "role": "SUPER_ADMIN",
        "is_developer": True,
    }
    out = create_user(auth, spec)
    assert auth.claims["dev-001"] == {"role": "SUPER_ADMIN", "is_developer": True}
    assert out["is_developer"] is True


def test_create_user_resyncs_password_for_existing_user():
    from seed.users import create_user

    auth = _FakeAuth()
    spec = {
        "uid": "dev-001",
        "email": "ezondiza.dhf@gmail.com",
        "password": "DEV-Aviasafe-2026",
        "full_name": "Developer",
        "role": "SUPER_ADMIN",
        "is_developer": True,
        "sync_password": True,
    }
    # Pre-existing user with an outdated password (no create happens).
    auth.records["dev-001"] = {"email": "ezondiza.dhf@gmail.com", "password": "old-pass"}
    create_user(auth, spec)
    assert auth.updates.get("dev-001") is not None
    assert auth.records["dev-001"]["password"] == "DEV-Aviasafe-2026"
    assert auth.claims["dev-001"]["role"] == "SUPER_ADMIN"


def test_create_all_users_provisions_developer_account():
    from seed.users import create_all_users

    auth = _FakeAuth()
    created = create_all_users(auth)
    dev = [u for u in created if u["email"] == "ezondiza.dhf@gmail.com"]
    assert len(dev) == 1
    assert dev[0]["role"] == "SUPER_ADMIN"
    assert dev[0]["is_developer"] is True
    assert auth.claims["kwxmjFjhVEVi9UuxtxrYO0lNQLE2"] == {
        "role": "SUPER_ADMIN",
        "is_developer": True,
    }
