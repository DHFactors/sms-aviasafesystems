"""Lightweight 6-Tenant Beta seed model (2026-08-12).

Locks the invariants of the seed configuration:

  * OPERATOR_PROFILES holds exactly ONE provider per service-provider type
    (airline, helicopter-operator, mro, aerodrome, ground-handling), so a seed
    produces exactly 5 operator tenants + the CAAN state-regulator tenant.
  * Legacy seed operators are archived in LEGACY_OPERATOR_PROFILES and are
    never part of the active seeding set or the credential scheme.
  * Each provider seeds 10 records per domain (VSR/MOR/hazard/CAN), and
    flight diversions only for flight operators (airline + helicopter).
"""

from seed.config import (
    OPERATOR_PROFILES,
    LEGACY_OPERATOR_PROFILES,
    BETA_SERVICE_PROVIDER_TYPES,
    FLIGHT_OPERATOR_TYPES,
    CREDENTIAL_EMAIL_DOMAINS,
    CREDENTIAL_TENANT_CODES,
    build_simplified_role_plan,
    SIMPLIFIED_ROLE_ACCOUNTS,
)


def test_exactly_one_provider_per_tenant_type():
    types = {p["tenant_type"] for p in OPERATOR_PROFILES}
    assert types == BETA_SERVICE_PROVIDER_TYPES
    assert len(OPERATOR_PROFILES) == len(BETA_SERVICE_PROVIDER_TYPES) == 5
    ids = [p["id"] for p in OPERATOR_PROFILES]
    assert len(ids) == len(set(ids))


def test_legacy_operators_archived_and_excluded():
    active_ids = {p["id"] for p in OPERATOR_PROFILES}
    legacy_ids = {p["id"] for p in LEGACY_OPERATOR_PROFILES}
    assert len(LEGACY_OPERATOR_PROFILES) == 5
    assert not (active_ids & legacy_ids)
    assert all(p.get("archived") for p in LEGACY_OPERATOR_PROFILES)


def test_every_provider_has_ten_record_counts():
    for p in OPERATOR_PROFILES:
        assert p["vsr_count"] == 10
        assert p["mor_count"] == 10
        assert p["hazard_count"] == 10
        assert p["can_count"] == 10


def test_flight_diversions_only_for_flight_operators():
    for p in OPERATOR_PROFILES:
        expected = 10 if p["tenant_type"] in FLIGHT_OPERATOR_TYPES else 0
        assert p["flight_diversion_count"] == expected, p["id"]


def test_credential_scheme_covers_active_providers_only():
    active_ids = {p["id"] for p in OPERATOR_PROFILES}
    assert set(CREDENTIAL_EMAIL_DOMAINS) == active_ids
    assert set(CREDENTIAL_TENANT_CODES) == active_ids
    plan = build_simplified_role_plan()
    assert len(plan) == 5 * len(SIMPLIFIED_ROLE_ACCOUNTS) == 20
    assert {entry["op_id"] for entry in plan} == active_ids
