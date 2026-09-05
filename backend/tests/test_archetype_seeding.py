"""Virtual Tenant Mirroring — archetype seeding (Chunk 2).

Locks the neutral-reference contract and seasonal envelopes for the master
archetype datasets consumed by `--archetypes`:

  * demo-fixed-wing : FW-HZ/FW-CAN/FW-CAP-{seq}-{YY}, 8-20 hazards/month
  * demo-rotary-wing: RW-HZ/RW-CAN/RW-CAP-{seq}-{YY}, 10-22 hazards/month
  * identical lifecycle machinery as real operators (365-day seasonal plan)
"""

from datetime import datetime, timezone

import pytest

from seed.archetype_config import (
    ARCHETYPE_DATASETS,
    REGULATOR_TIER_ID,
    archetype_seed_profiles,
    neutral_can_ref,
    neutral_cap_ref,
    season_rules_for,
    validate_archetype_config,
)
import re
from seed.generator import SeededRandom
from seed.hazard_can import (
    _annual_hazard_count,
    _can_doc,
    _cap_doc,
    _fishbone_doc,
    _hazard_doc,
    _seasonal_plan,
)


def _now():
    return datetime.now(timezone.utc)


_CAAN_REF_RE = re.compile(r"^[A-Z]{3}/\d{3}/[HML]/\d{4}$")


def test_archetype_config_is_valid():
    assert validate_archetype_config() == []
    assert set(all_ids := ARCHETYPE_DATASETS) == {"demo-fixed-wing", "demo-rotary-wing"}
    assert REGULATOR_TIER_ID == "caanepal"
    assert all_ids  # sanity


def test_neutral_reference_formats_with_year():
    # CAN/CAP neutral references keep their FW-/RW- branding (out of the CAAN
    # hazard-reference scope); hazard references now use the CAAN function format.
    assert neutral_can_ref("demo-fixed-wing", 12, 2026) == "FW-CAN-0012-26"
    assert neutral_cap_ref("demo-fixed-wing", 40, 2026) == "FW-CAP-0040-26"


def test_archetype_seed_profiles_inherit_mirror_shape():
    profiles = archetype_seed_profiles(["demo-fixed-wing", "demo-rotary-wing"])
    by_id = {p["id"]: p for p in profiles}
    assert by_id["demo-fixed-wing"]["is_archetype"] is True
    assert by_id["demo-fixed-wing"]["archetype_kind"] == "fixed-wing"
    # Rotary mirrors a helicopter operator; fixed-wing mirrors an airline.
    assert by_id["demo-rotary-wing"]["tenant_type"] == "helicopter-operator"
    assert by_id["demo-fixed-wing"]["tenant_type"] == "airline"
    with pytest.raises(ValueError):
        archetype_seed_profiles(["unknown-archetype"])


@pytest.mark.parametrize("aid,lo,hi", [
    ("demo-fixed-wing", 8, 20),
    ("demo-rotary-wing", 10, 22),
])
def test_seasonal_plan_stays_inside_archetype_envelope(aid, lo, hi):
    profile = archetype_seed_profiles([aid])[0]
    rng = SeededRandom(seed=123)
    plan = _seasonal_plan(profile, _now(), rng, rules=season_rules_for(aid))
    assert len(plan) >= 11  # rolling 12-month window (current month partial)
    for entry in plan:
        assert lo <= entry["hazard_count"] <= hi, entry
    # Monsoon uplift preserved: Jun-Aug average above the annual monthly mean.
    monsoon = [p["hazard_count"] for p in plan if p["season"] == "MONSOON"]
    overall = sum(p["hazard_count"] for p in plan) / len(plan)
    assert sum(monsoon) / len(monsoon) > overall


def test_annual_volume_meets_demonstration_minimum():
    for aid in ("demo-fixed-wing", "demo-rotary-wing"):
        profile = archetype_seed_profiles([aid])[0]
        assert _annual_hazard_count(profile) >= 52


def test_archetype_documents_carry_icao_references():
    profile = archetype_seed_profiles(["demo-fixed-wing"])[0]
    created = datetime(2026, 7, 14, tzinfo=timezone.utc)  # monsoon month

    # Hazards are referenced with the CAAN function format (no tenant code).
    hazard = _hazard_doc(SeededRandom(seed=1), profile, 6, created_at=created)
    assert _CAAN_REF_RE.match(hazard["hazard_id"])
    assert hazard["hazard_id"].count("-") == 0

    can = _can_doc(SeededRandom(seed=2), profile, 6, "haz-doc", hazard["hazard_id"],
                   issued_at=created, can_reference=neutral_can_ref("demo-fixed-wing", 7, 2026))
    assert can["can_reference"] == "FW-CAN-0007-26"

    fishbone = _fishbone_doc(SeededRandom(seed=3), seed=9500, can_index=6,
                             submitted_by=can["assigned_to"])
    cap = _cap_doc(SeededRandom(seed=4), can["can_reference"], "can-doc", 0,
                   can["department"],
                   submitted_by={"postholder": can["assigned_to"], "uid": can["assigned_to_uid"]},
                   fishbone=fishbone, initial_risk_index=can["initial_risk_index"],
                   parent_issued_at=created,
                   cap_reference=neutral_cap_ref("demo-fixed-wing", 40, 2026))
    assert cap["cap_reference"] == "FW-CAP-0040-26"
