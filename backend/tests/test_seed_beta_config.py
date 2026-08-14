"""10-Tenant Beta seed model (2026-08-14).

Locks the invariants of the seed configuration:

  * OPERATOR_PROFILES holds 10 active providers covering every service-provider
    type (airline, helicopter-operator, mro, aerodrome, ground-handling), so a
    seed produces exactly 10 operator tenants + the CAAN state-regulator tenant.
  * All tenant ids are lowercase, hyphenated (e.g. yeti-airlines).
  * Each provider seeds randomized realistic volumes: 25-40 total reports with
    ~70% VSR / 30% MOR, ~25-35% anonymous VSRs, 15-25 surveys, and flight
    diversions only for flight operators (airline + helicopter).
  * LEGACY_OPERATOR_PROFILES is empty (all legacy operators re-activated).
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


def test_all_providers_cover_tenant_types():
    types = {p["tenant_type"] for p in OPERATOR_PROFILES}
    assert types == BETA_SERVICE_PROVIDER_TYPES
    assert len(OPERATOR_PROFILES) == 10
    ids = [p["id"] for p in OPERATOR_PROFILES]
    assert len(ids) == len(set(ids))


def test_all_tenant_ids_are_hyphenated_lowercase():
    for p in OPERATOR_PROFILES:
        tid = p["id"]
        assert tid == tid.lower()
        assert "-" in tid, f"{tid} must use hyphens (not underscores)"


def test_legacy_operators_are_reactivated():
    active_ids = {p["id"] for p in OPERATOR_PROFILES}
    assert LEGACY_OPERATOR_PROFILES == []
    assert active_ids >= {"yeti-airlines", "summit-air", "sita-air", "simrik-air", "tara-air"}


def test_every_provider_has_realistic_volumes():
    for p in OPERATOR_PROFILES:
        total = p["vsr_count"] + p["mor_count"]
        assert 25 <= total <= 40, p["id"]
        vsr_share = p["vsr_count"] / total
        assert 0.68 <= vsr_share <= 0.72, p["id"]
        assert 0.25 <= p["anonymous_rate"] <= 0.35, p["id"]
        assert 15 <= p["survey_count"] <= 25, p["id"]
        assert p["hazard_count"] >= 12, p["id"]
        assert p["can_count"] >= 8, p["id"]


def test_flight_diversions_only_for_flight_operators():
    for p in OPERATOR_PROFILES:
        expected = 10 if p["tenant_type"] in FLIGHT_OPERATOR_TYPES else 0
        assert p["flight_diversion_count"] == expected, p["id"]


def test_credential_scheme_covers_active_providers_only():
    active_ids = {p["id"] for p in OPERATOR_PROFILES}
    assert set(CREDENTIAL_EMAIL_DOMAINS) == active_ids
    assert set(CREDENTIAL_TENANT_CODES) == active_ids
    plan = build_simplified_role_plan()
    assert len(plan) == 10 * len(SIMPLIFIED_ROLE_ACCOUNTS) == 40
    assert {entry["op_id"] for entry in plan} == active_ids
