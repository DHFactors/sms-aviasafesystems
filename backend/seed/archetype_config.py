# ============================================================================
# FILE: backend/seed/archetype_config.py
# PURPOSE: Virtual Tenant Mirroring — master archetype configuration.
#
#          Prospect AE demonstrations are served from TWO master archetype
#          datasets ("virtual tenants") instead of duplicating data for each
#          of the 20 prospect operators:
#
#            * demo-fixed-wing  — fixed-wing operations master dataset
#            * demo-rotary-wing — rotary-wing operations master dataset
#
#          Each archetype is seeded ONCE with the full 365-day seasonal
#          pipeline (seed/hazard_can.py) under its own virtual tenant id.
#          At login, prospect AE accounts receive an ``archetypeId`` custom
#          claim; the client formats every neutral reference (FW-HZ-…,
#          RW-CAN-…) into the prospect's own branding. No per-operator
#          database records exist — mirroring is purely presentational.
#
# CHUNK STATUS (Phase: Virtual Tenant Mirroring):
#   Chunk 1 (this file) — archetype registry scaffold + neutral reference
#                         code generation helpers.
#   Chunk 2             — seeder wiring in seed/hazard_can.py using the
#                         neutral FW-/RW- prefixes defined here.
#   Chunk 3             — the 20-tenant PROSPECT_REGISTRY (demo-prospects.js /
#                         backend registry) consumed by
#                         resolve_archetype_for_email().
#
# Nothing in this module writes to Firestore; it is pure configuration.
# ============================================================================

from seed.config import OPERATOR_PROFILES

# Custom-claim key stamped onto prospect AE accounts at login.
CLAIM_KEY = "archetypeId"

# Archetypes live as virtual tenants in the same `tenants` collection.
VIRTUAL_TENANT_MODE = True

# Every archetype seeds the full seasonal window (runner --preset semantics).
DEFAULT_WINDOW_DAYS = 365


# ── Master archetype datasets ───────────────────────────────────────────────
# ``mirror_profile`` names the OPERATOR_PROFILES entry whose operational shape
# (fleet mix, routes, hazard domains, departments) the archetype mirrors. The
# archetype NEVER references the real operator's identity client-side.
#
# ``hazard_month_ranges`` narrows the generic seasonal engine (SEASON_RULES in
# seed/hazard_can.py) to the archetype's operating envelope while preserving
# the ~50% monsoon uplift:
#   fixed-wing : 8–20 hazards/month  (ATR / turboprop / STOL scenarios)
#   rotary-wing: 10–22 hazards/month (mountain / HEMS scenarios)

ARCHETYPE_DATASETS = {
    "demo-fixed-wing": {
        "id": "demo-fixed-wing",
        "label": "Fixed-Wing Operations (Demo)",
        "kind": "fixed-wing",
        # Neutral reference prefixes — formatted client-side per prospect.
        "neutral_prefix": "FW",
        "ref_prefixes": {
            "hazard": "FW-HZ",
            "can": "FW-CAN",
            "cap": "FW-CAP",
        },
        "mirror_profile": "buddha-air",
        "window_days": DEFAULT_WINDOW_DAYS,
        "seasonal": True,
        "hazard_month_ranges": {
            "PRE_MONSOON": (8, 12),
            "MONSOON": (15, 20),
            "FESTIVE": (12, 16),
            "WINTER": (8, 11),
        },
    },
    "demo-rotary-wing": {
        "id": "demo-rotary-wing",
        "label": "Rotary-Wing Operations (Demo)",
        "kind": "rotary-wing",
        "neutral_prefix": "RW",
        "ref_prefixes": {
            "hazard": "RW-HZ",
            "can": "RW-CAN",
            "cap": "RW-CAP",
        },
        "mirror_profile": "fishtail-air",
        "window_days": DEFAULT_WINDOW_DAYS,
        "seasonal": True,
        "hazard_month_ranges": {
            "PRE_MONSOON": (10, 14),
            "MONSOON": (17, 22),
            "FESTIVE": (13, 17),
            "WINTER": (10, 12),
        },
    },
}

DEFAULT_ARCHETYPE_ID = "demo-fixed-wing"

# Regulator virtual tier name accepted by --archetypes (aggregate oversight
# view over the selected archetypes; no operator data of its own).
REGULATOR_TIER_ID = "caanepal"


def season_rules_for(archetype_id: str):
    """Season → (min, max) hazards/month for an archetype, falling back to the
    generic SEASON_RULES shape consumed by seed/hazard_can.py."""
    cfg = get_archetype(archetype_id)
    if not cfg:
        return None
    return dict(cfg.get("hazard_month_ranges") or {})


# ── Accessors ───────────────────────────────────────────────────────────────

def get_archetype(archetype_id: str):
    """Return the archetype config dict, or None when the id is unknown."""
    return ARCHETYPE_DATASETS.get(archetype_id)


def all_archetype_ids():
    """All master archetype dataset ids (stable order)."""
    return list(ARCHETYPE_DATASETS.keys())


def resolve_archetype_for_email(email: str):
    """Resolve the archetype id for a prospect AE email via the 20-tenant
    PROSPECT_REGISTRY (introduced in Chunk 3).

    Returns None while the registry is absent or the email is not a registered
    prospect — callers fall back to DEFAULT_ARCHETYPE_ID only where a demo
    context explicitly allows it.
    """
    if not email:
        return None
    try:
        from seed.prospect_registry import PROSPECT_REGISTRY  # Chunk 3 artifact
    except ImportError:
        return None
    entry = (PROSPECT_REGISTRY.get(str(email).lower()) or {}) if isinstance(PROSPECT_REGISTRY, dict) else {}
    archetype_id = entry.get("archetypeId")
    return archetype_id if archetype_id in ARCHETYPE_DATASETS else None


# ── Neutral reference code generation ───────────────────────────────────────
# Canonical format: {PREFIX}-{KIND}-{seq:04d}-{YY}  e.g. FW-HZ-0007-26
# (YY = two-digit year of the event, matching the seasonal window).

def neutral_hazard_ref(archetype_id: str, sequence: int, year: int = None) -> str:
    """e.g. ('demo-fixed-wing', 7, 2026) -> 'FW-HZ-0007-26'."""
    archetype = get_archetype(archetype_id)
    ref = f"{archetype['ref_prefixes']['hazard']}-{sequence:04d}"
    return f"{ref}-{year % 100:02d}" if year is not None else ref


def neutral_can_ref(archetype_id: str, sequence: int, year: int = None) -> str:
    """e.g. ('demo-rotary-wing', 3, 2026) -> 'RW-CAN-0003-26'."""
    archetype = get_archetype(archetype_id)
    ref = f"{archetype['ref_prefixes']['can']}-{sequence:04d}"
    return f"{ref}-{year % 100:02d}" if year is not None else ref


def neutral_cap_ref(archetype_id: str, sequence: int, year: int = None) -> str:
    """CAP references carry their own global sequence,
    e.g. ('demo-rotary-wing', 12, 2026) -> 'RW-CAP-0012-26'."""
    archetype = get_archetype(archetype_id)
    ref = f"{archetype['ref_prefixes']['cap']}-{sequence:04d}"
    return f"{ref}-{year % 100:02d}" if year is not None else ref


# ── Synthetic operator profiles for the seeder ──────────────────────────────

def archetype_seed_profiles(archetype_ids):
    """Build OPERATOR_PROFILES-shaped dicts for the requested archetypes so
    the existing 365-day seasonal pipeline (seed/hazard_can.py) can run
    against them unchanged. The synthetic profile inherits the mirror
    profile's operational shape (fleet mix, routes, hazard domains,
    departments) but carries the neutral demo identity."""
    profiles = []
    for aid in archetype_ids:
        cfg = get_archetype(aid)
        if not cfg:
            raise ValueError(f"Unknown archetype id: {aid}")
        base = next((p for p in OPERATOR_PROFILES if p["id"] == cfg["mirror_profile"]), None)
        if base is None:
            raise ValueError(f"Archetype '{aid}' mirrors unknown profile '{cfg['mirror_profile']}'")
        profile = dict(base)
        profile["id"] = aid
        profile["name"] = cfg["label"]
        profile["email_domain"] = f"{aid}.demo.aviasafesystems.com"
        profile["is_archetype"] = True
        profile["archetype_kind"] = cfg["kind"]
        profiles.append(profile)
    return profiles


# ── Integrity checks (consumed by tests / the seeder pre-flight) ────────────

def validate_archetype_config():
    """Return a list of configuration problems (empty list = valid)."""
    issues = []
    seen_prefixes = set()

    if DEFAULT_ARCHETYPE_ID not in ARCHETYPE_DATASETS:
        issues.append(f"DEFAULT_ARCHETYPE_ID '{DEFAULT_ARCHETYPE_ID}' is not a known archetype")

    profile_ids = {p["id"] for p in OPERATOR_PROFILES}
    for archetype_id, cfg in ARCHETYPE_DATASETS.items():
        if cfg["id"] != archetype_id:
            issues.append(f"{archetype_id}: inner id mismatch ({cfg['id']})")
        if "-" not in archetype_id or archetype_id != archetype_id.lower():
            issues.append(f"{archetype_id}: virtual tenant ids must be lowercase hyphenated")

        prefix = cfg.get("neutral_prefix")
        if not prefix or not str(prefix).isupper():
            issues.append(f"{archetype_id}: neutral_prefix must be an uppercase token")
        if prefix in seen_prefixes:
            issues.append(f"{archetype_id}: duplicate neutral_prefix '{prefix}'")
        seen_prefixes.add(prefix)

        expected = {
            "hazard": f"{prefix}-HZ",
            "can": f"{prefix}-CAN",
            "cap": f"{prefix}-CAP",
        }
        if cfg.get("ref_prefixes") != expected:
            issues.append(f"{archetype_id}: ref_prefixes must match {expected}")

        if cfg.get("mirror_profile") not in profile_ids:
            issues.append(f"{archetype_id}: mirror_profile '{cfg.get('mirror_profile')}' "
                          "is not an OPERATOR_PROFILES entry")

        if not cfg.get("seasonal") or cfg.get("window_days") != DEFAULT_WINDOW_DAYS:
            issues.append(f"{archetype_id}: archetypes must seed the full "
                          f"{DEFAULT_WINDOW_DAYS}-day seasonal window")

    return issues
