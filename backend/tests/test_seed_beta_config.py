"""12-Tenant Beta seed model (2026-08-17).

Locks the invariants of the seed configuration:

  * OPERATOR_PROFILES holds 12 active providers covering every service-provider
    type (airline, helicopter-operator, mro, aerodrome, ground-handling,
    caan-directorate), so a seed produces exactly 12 operator tenants + the
    CAAN state-regulator tenant. Internal CAAN directorates (caan-fssd,
    caan-assd) are treated like any external provider for oversight scoping.
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
    VSR_ORIGINATOR_PERSONAS,
    FISHBONE_CATEGORIES,
)


def test_all_providers_cover_tenant_types():
    types = {p["tenant_type"] for p in OPERATOR_PROFILES}
    assert types == BETA_SERVICE_PROVIDER_TYPES
    assert len(OPERATOR_PROFILES) == 12
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
    assert len(plan) == 12 * len(SIMPLIFIED_ROLE_ACCOUNTS) == 48
    assert {entry["op_id"] for entry in plan} == active_ids


def test_vsr_originator_90_10_anonymity_ratio():
    from seed.reports import generate_vsr_originator
    from seed.generator import SeededRandom

    rng = SeededRandom(seed=1234)
    anon = named = 0
    for _ in range(10_000):
        o = generate_vsr_originator(rng, "buddha-air")
        if o["is_anonymous"]:
            anon += 1
            assert o["originator_name"] == "Anonymous (Confidential VSR)"
            assert o["contact_details"] is None
        else:
            named += 1
            assert o["originator_name"] in {p["name"] for p in VSR_ORIGINATOR_PERSONAS}
    ratio = anon / (anon + named)
    assert 0.87 <= ratio <= 0.93, f"expected ~0.90, got {ratio:.3f}"


def test_mor_originators_are_compliance_authorities_only():
    from seed.config import MOR_ORIGINATOR_AUTHORITIES
    from seed.reports import _generate_mor_document
    from seed.generator import SeededRandom

    for profile in OPERATOR_PROFILES:
        rng = SeededRandom(seed=99)
        for i in range(profile["mor_count"]):
            _, doc = _generate_mor_document(rng, profile, i, 30000)
            assert doc["report_type"] == "mandatory"
            assert doc["originator_name"] in MOR_ORIGINATOR_AUTHORITIES
            assert doc["is_anonymous"] is False


def test_can_uses_corporate_safety_issuer_and_postholder_rotation():
    from seed.config import CAN_ISSUED_BY, CAN_ASSIGNED_POSTHOLDERS
    from seed.hazard_can import _can_doc
    from seed.generator import SeededRandom

    profile = next(p for p in OPERATOR_PROFILES if p["id"] == "buddha-air")
    rng = SeededRandom(seed=7)
    postholders = set()
    for i in range(profile["can_count"]):
        rng.seed(40000 + sum(ord(c) for c in profile["id"]) + 5000 + i)
        can = _can_doc(rng, profile, i, f"haz-doc-{i}", f"hazard-{i}")
        assert can["issued_by"] == CAN_ISSUED_BY
        assert can["assigned_to"] == can["addressed_function"]
        postholders.add(can["assigned_to"])
        assert can["initial_sra"]["severity_letter"] in {"B", "C", "D"}
        assert can["initial_sra"]["risk_index"] == (
            can["initial_sra"]["severity"] * can["initial_sra"]["probability"]
        )
    assert postholders == {label for label, _ in CAN_ASSIGNED_POSTHOLDERS}


def test_cap_has_six_branch_fishbone_primary_and_1to1_actions():
    from seed.hazard_can import _fishbone_doc, _cap_doc
    from seed.generator import SeededRandom

    rng = SeededRandom(seed=11)
    submitted_by = {"postholder": "Head of Flight Operations", "uid": "ops-buddha-air-001"}
    fishbone = _fishbone_doc(rng, seed=9500, can_index=0, submitted_by=submitted_by["postholder"])

    assert len(fishbone["root_causes"]) == 6
    assert sum(1 for rc in fishbone["root_causes"] if rc["is_primary"]) == 1
    assert {rc["category"] for rc in fishbone["root_causes"]} == set(FISHBONE_CATEGORIES)
    assert len(fishbone["action_items"]) == 6
    rc_ids = {rc["id"] for rc in fishbone["root_causes"]}
    assert {ai["root_cause_id"] for ai in fishbone["action_items"]} == rc_ids

    cap = _cap_doc(
        rng,
        can_reference="CAN-001",
        can_doc_id="can-1",
        index=0,
        department="Flight Operations",
        submitted_by=submitted_by,
        fishbone=fishbone,
    )
    assert cap["submitted_by"] == "Head of Flight Operations"
    assert cap["residual_sra"]["risk_level"] in {"Low", "Medium"}
    assert cap["residual_sra"]["risk_index"] <= 9
    assert all(ai["target_date"] for ai in cap["action_items"])
    assert cap["process_owner"] == "Head of Flight Operations"


def test_operational_profiles_cover_all_active_tenants():
    from seed.tenant_profiles import (
        TENANT_OPERATIONAL_PROFILES,
        CATEGORY_FIXED_WING,
        CATEGORY_ROTOR_WING,
        CATEGORY_AMO,
        CATEGORY_AERODROME,
        CATEGORY_GROUND_HANDLING,
    )

    active_ids = {p["id"] for p in OPERATOR_PROFILES}
    assert set(TENANT_OPERATIONAL_PROFILES) == active_ids
    for tid, profile in TENANT_OPERATIONAL_PROFILES.items():
        assert profile.tenant_id == tid
        assert profile.fleet, tid
        assert profile.base_hub, tid
        assert len(profile.authorized_destinations) >= 1, tid
        assert len(profile.hazard_domains) >= 1, tid


def test_operational_profile_categories_match_tenant_types():
    from seed.tenant_profiles import (
        TENANT_OPERATIONAL_PROFILES,
        CATEGORY_FIXED_WING,
        CATEGORY_ROTOR_WING,
        CATEGORY_AMO,
        CATEGORY_AERODROME,
        CATEGORY_GROUND_HANDLING,
        CATEGORY_CAAN,
    )

    type_to_category = {
        "airline": CATEGORY_FIXED_WING,
        "helicopter-operator": CATEGORY_ROTOR_WING,
        "mro": CATEGORY_AMO,
        "aerodrome": CATEGORY_AERODROME,
        "ground-handling": CATEGORY_GROUND_HANDLING,
        "caan-directorate": CATEGORY_CAAN,
    }
    for p in OPERATOR_PROFILES:
        profile = TENANT_OPERATIONAL_PROFILES[p["id"]]
        assert profile.category == type_to_category[p["tenant_type"]], p["id"]


def test_rotor_wing_profiles_never_list_fixed_wing_aircraft():
    from seed.tenant_profiles import TENANT_OPERATIONAL_PROFILES, CATEGORY_ROTOR_WING

    fixed_wing_markers = ["ATR", "Twin Otter", "Beechcraft", "Dornier", "L-410", "A3", "A3", "319", "320"]
    for tid, profile in TENANT_OPERATIONAL_PROFILES.items():
        if profile.category != CATEGORY_ROTOR_WING:
            continue
        for ac in profile.fleet:
            assert not any(m in ac for m in fixed_wing_markers), f"{tid} rotor-wing fleet has {ac}"


def test_vsr_occurrence_types_respect_tenant_hazard_domains():
    from seed.reports import _generate_vsr_document
    from seed.generator import SeededRandom
    from seed.tenant_profiles import (
        get_authorized_destinations,
        vsr_occurrence_types_for_tenant,
        DOMAIN_TO_VSR_OCCURRENCE_TYPES,
    )

    profile = next(p for p in OPERATOR_PROFILES if p["id"] == "buddha-air")
    rng = SeededRandom(seed=21)
    locations = set()
    occurrence_types = set()
    for i in range(profile["vsr_count"]):
        _, doc = _generate_vsr_document(rng, profile, i, 20000)
        locations.add(doc["location"])
        occurrence_types.add(doc["occurrence_type"])

    authorized = set(get_authorized_destinations(profile["id"]))
    assert locations <= authorized, locations - authorized

    allowed_types = set(vsr_occurrence_types_for_tenant(profile["id"], []))
    assert occurrence_types <= allowed_types, occurrence_types - allowed_types


def test_mor_occurrence_types_respect_tenant_hazard_domains():
    from seed.reports import _generate_mor_document
    from seed.generator import SeededRandom
    from seed.tenant_profiles import (
        get_authorized_destinations,
        mor_occurrence_types_for_tenant,
    )

    profile = next(p for p in OPERATOR_PROFILES if p["id"] == "air-dynasty")
    rng = SeededRandom(seed=22)
    locations = set()
    occurrence_types = set()
    for i in range(profile["mor_count"]):
        _, doc = _generate_mor_document(rng, profile, i, 30000)
        locations.add(doc["location"])
        occurrence_types.add(doc["occurrence_type"])

    authorized = set(get_authorized_destinations(profile["id"]))
    assert locations <= authorized, locations - authorized

    allowed_types = set(mor_occurrence_types_for_tenant(profile["id"], []))
    assert occurrence_types <= allowed_types, occurrence_types - allowed_types


def test_hazard_titles_respect_tenant_hazard_domains():
    from seed.hazard_can import _hazard_doc
    from seed.generator import SeededRandom
    from seed.tenant_profiles import (
        hazard_titles_for_tenant,
        DOMAIN_TO_HAZARD_TITLES,
    )

    profile = next(p for p in OPERATOR_PROFILES if p["id"] == "ktm-mro")
    rng = SeededRandom(seed=23)
    titles = set()
    for i in range(profile["hazard_count"]):
        rng.seed(40000 + sum(ord(c) for c in profile["id"]) + i)
        doc = _hazard_doc(rng, profile, i)
        titles.add(doc["title"])

    allowed = set(hazard_titles_for_tenant(profile["id"], []))
    assert titles <= allowed, titles - allowed


def test_report_aircraft_matches_tenant_fleet():
    from seed.reports import _generate_vsr_document
    from seed.generator import SeededRandom
    from seed.tenant_profiles import get_aircraft_fleet

    profile = next(p for p in OPERATOR_PROFILES if p["id"] == "yeti-airlines")
    rng = SeededRandom(seed=24)
    types = set()
    for i in range(profile["vsr_count"]):
        _, doc = _generate_vsr_document(rng, profile, i, 20000)
        assert doc["aircraft_type"] is not None
        types.add(doc["aircraft_type"])

    fleet = set(get_aircraft_fleet(profile["id"]))
    assert types <= fleet, types - fleet


def test_non_flying_providers_have_no_aircraft_type():
    from seed.reports import _generate_vsr_document
    from seed.generator import SeededRandom

    for p in OPERATOR_PROFILES:
        if p["tenant_type"] in ("airline", "helicopter-operator"):
            continue
        rng = SeededRandom(seed=25)
        _, doc = _generate_vsr_document(rng, p, 0, 20000)
        assert doc["aircraft_type"] is None, p["id"]


def test_tenants_with_stol_routes_never_get_trunk_jet_fleet():
    from seed.tenant_profiles import TENANT_OPERATIONAL_PROFILES, CATEGORY_ROTOR_WING

    stol_tenants = {"summit-air", "tara-air", "simrik-air"}
    trunk_markers = ["A319", "A320", "ATR 72"]
    for tid in stol_tenants:
        profile = TENANT_OPERATIONAL_PROFILES[tid]
        for ac in profile.fleet:
            assert not any(m in ac for m in trunk_markers), f"{tid} STOL fleet has {ac}"
        assert "Lukla (VNLK)" in profile.authorized_destinations or "Kangel Danda (VNDG)" in profile.authorized_destinations
