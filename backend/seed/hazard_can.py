"""Hazard + CAN/CAP seeding for the AviaSAFE demo data pipeline.

Writes deterministic, realistic hazard, corrective-action-notice (CAN) and
corrective-action-plan (CAP) documents into each operator tenant. Every
document is tagged with the current SEED_VERSION so the runner can later purge
stale seed docs (and only seed docs) without touching live or admin-seeded data.

Document shapes mirror what the services write (app/services/hazard_service.py
and app/services/can_cap_service.py) so the UIs and the unified Master Register
render the seeded rows natively.
"""

from datetime import datetime, timedelta, timezone
import calendar

from loguru import logger

from seed import config as _cfg
from seed.archetype_config import (
    season_rules_for,
    neutral_can_ref,
    neutral_cap_ref,
)
from seed.config import (
    OPERATOR_PROFILES,
    SEED_VERSION,
    CREDENTIAL_EMAIL_DOMAINS,
    CAN_ISSUED_BY,
    CAN_ASSIGNED_POSTHOLDERS,
    FISHBONE_CATEGORIES,
    FISHBONE_ROOT_CAUSE_POOL,
    FISHBONE_ACTION_TEMPLATES,
)
from seed.generator import SeededRandom, generate_timestamp, _make_id
from seed.tenant_profiles import hazard_titles_for_tenant
from app.models.hazard import revalue_taxonomy
from app.services.risk_matrix import compute_risk_index, get_risk_level, risk_outcome
from app.services.hazard_service import generate_hazard_id, resolve_function_code

SEVERITY_LETTERS = ["A", "B", "C", "D", "E"]

# Maps each authentic postholder to the simplified role token that owns the
# matching functional account (safety / ops / camo / 145). The department
# label comes from CAN_ASSIGNED_POSTHOLDERS.
POSTHOLDER_ROLE = {
    "Head of Flight Operations": "ops",
    "Head of Maintenance / CAMO": "camo",
    "Ground Operations Manager": "ops",
    "Cabin Safety Manager": "safety",
}

# Provisioned postholder accounts that receive seeded CAN/CAP assignments.
# Rotating across all six guarantees every account (ae@, safety@, 145@, camo@,
# ops@, pilot@) holds 1-2 CANs plus their linked CAPs per tenant, with the
# department claim matching the functional queue (Part-145 / CAMO / Flight Ops).
POSTHOLDER_ACCOUNTS = [
    {"token": "ops",    "label": "Head of Flight Operations",    "department": "Flight Operations"},
    {"token": "145",    "label": "Part-145 Maintenance Manager", "department": "Part-145"},
    {"token": "camo",   "label": "Head of Maintenance / CAMO",   "department": "CAMO"},
    {"token": "pilot",  "label": "Line Pilot",                   "department": "Flight Operations"},
    {"token": "safety", "label": "Safety Manager",               "department": ""},
    {"token": "ae",     "label": "Accountable Executive",        "department": ""},
]

HAZARD_STATUSES = [
    "Open", "Open", "Open", "Processing",
    "Under Review", "Pending Closure", "Closed",
]
CAN_STATUSES = ["Open", "Open", "Under Review"]
CAP_STATUSES = ["Draft", "In Progress", "In Progress", "Completed"]

TAXONOMY_POOL = {
    "LOCI": "Organizational",
    "CFIT": "Organizational",
    "RE": "Organizational",
    "RI": "Organizational",
    "GCOL": "Organizational",
    "MAC": "Technical",
    "ENG": "Technical",
    "SYS": "Technical",
    "FIRE": "Technical",
    "BIRD": "Environmental",
    "CABIN": "Human",
    "ARC": "Organizational",
    "WX": "Environmental",
    "OTHER": "Organizational",
}
ICAO_CATEGORIES = list(TAXONOMY_POOL.keys())

# ICAO ADREP categories that only an aircraft in flight (or on the runway for
# departure / arrival) can experience. Excluded from the pools of non-flying
# tenants (AMO, aerodrome, ground handling, CAAN directorates) so occurrence
# reporting and risk templates respect ``operates_flights``.
FLIGHT_ONLY_ICAO_CATEGORIES = {"LOCI", "CFIT", "MAC", "ARC", "WX"}

SOURCES = [
    "VSR", "MOR", "Internal Audit", "Quality Audit",
    "Safety Inspection", "Flight Diversion",
]

HAZARD_TITLES = [
    "Unsecured cargo restraint during turnaround",
    "Recurrent bird activity on runway approach",
    "Fatigue reported during night dispatch duties",
    "Communication breakdown between cockpit and cabin crew",
    "Inadequate FOD control on the apron",
    "Degraded hydraulic system indication",
    "Insufficient de-icing coverage during cold weather",
    "Runway incursion during taxiing",
    "Maintenance documentation gaps for airworthy release",
    "Obstacle clearance margin at mountain STOL strip",
    "Ground power unit positioned too close to wingtip",
    "Captain elevated workload on late-evening sector",
]

HAZARD_DESCRIPTIONS = [
    "Seeded hazard observed during routine operations; requires SRM assessment.",
    "Reported via voluntary occurrence; contributing factors under review.",
    "Demonstration hazard reflecting realistic operational exposure for this operator.",
    "Identified during hazard identification review; recommended action following.",
]

REQUIRED_ACTIONS = [
    "Implement the agreed corrective action and verify effectiveness.",
    "Issue a safety bulletin and re-brief affected crews.",
    "Amend the relevant SOP and schedule retraining.",
    "Conduct a focused risk assessment and monitor the risk register.",
]

ACTION_PLANS = [
    "Phase the corrective action, verify effectiveness, and close out with evidence.",
    "Assign an owner, set milestones, and report progress at the monthly safety meeting.",
    "Reinforce controls, re-train staff, and audit compliance after 30 days.",
]


def _base_seed(tenant_id: str) -> int:
    return 40000 + sum(ord(c) for c in tenant_id)


# ============================================================================
# 365-day seasonal distribution engine (2026 Nepal ops calendar)
# ============================================================================

SEASON_RULES = {
    # season: (hazards/month range, barrier-effective band %, severity bump)
    "PRE_MONSOON": {"hazards": (8, 12),  "effective": (75, 80), "sev_bump": 0},
    "MONSOON":     {"hazards": (15, 20), "effective": (45, 60), "sev_bump": 1},
    "FESTIVE":     {"hazards": (12, 16), "effective": (68, 73), "sev_bump": 0},
    "WINTER":      {"hazards": (6, 9),   "effective": (65, 75), "sev_bump": 0},
}

# Weighted assignment targets — safety@ owns ~35% of records, ae@ ~5%
# (escalated items only). Quotas are materialized exactly per tenant via a
# greedy largest-remainder sequence (see _assignee_sequence).
ASSIGN_SHARES = [
    ("safety", 0.35),
    ("ops", 0.20),
    ("145", 0.15),
    ("camo", 0.15),
    ("pilot", 0.10),
    ("ae", 0.05),
]


def _assignee_sequence(total: int) -> list:
    """Deterministic near-exact proportional allocation of `total` slots."""
    counts = {t: 0 for t, _ in ASSIGN_SHARES}
    seq = []
    for i in range(total):
        token, _ = max(ASSIGN_SHARES, key=lambda s: s[1] * (i + 1) - counts[s[0]])
        seq.append(token)
        counts[token] += 1
    return seq


def _robustness_for(rng: SeededRandom, effective_pct: int, restored: bool = False) -> dict:
    """Sample a barrier robustness band honouring the seasonal effective rate
    (closed/verified restorations are forced back into the Effective band)."""
    roll = 100 if restored else rng.randint(1, 100)
    if restored or roll <= effective_pct:
        band = rng.choice([b for b in BQV_BANDS if b[3] in ("Good", "Very Good", "Excellent")])
        bqv = rng.randint(band[0], band[1])
    else:
        # Monsoon degradation runs deep: Fair / Poor / Ineffective.
        band = rng.choice([b for b in BQV_BANDS if b[3] in ("Fair", "Poor", "Ineffective")])
        bqv = rng.randint(band[0], max(band[0], band[1]))
    robustness = band[3]
    return {"bqv": bqv, "bsv": band[2], "robustness": robustness}

# Mirror of public/js/srm.js BQV bands for consistent seeded barrier quality.
BQV_BANDS = [
    (42, 50, 5, "Excellent"),
    (34, 41, 4, "Very Good"),
    (26, 33, 3, "Good"),
    (18, 25, 2, "Fair"),
    (10, 17, 1, "Poor"),
    (0, 9, 0, "Ineffective"),
]


def _season_of(month: int) -> str:
    if month in (6, 7, 8):
        return "MONSOON"
    if month in (9, 10, 11):
        return "FESTIVE"
    if month == 12:
        return "WINTER"
    return "PRE_MONSOON"


def _size_factor(profile: dict) -> float:
    """Operator scale factor from workforce size (large operators trend to the
    upper end of every seasonal band; small operators to the lower end)."""
    employees = profile.get("employees") or 200
    return max(0.5, min(1.0, 0.5 + 0.5 * (employees / 1200.0) ** 0.5))


def _rolling_months(now: datetime, window_days: int = None) -> list:
    """[(year, month)] oldest → newest covering the rolling window."""
    window = window_days if window_days is not None else _cfg.SEED_WINDOW_DAYS
    months = []
    y, m = now.year, now.month
    total_months = max(1, int(window // 30) + (1 if window % 30 else 0))
    for _ in range(total_months):
        months.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months.reverse()
    return months


def _month_datetime(year: int, month: int, rng: SeededRandom, now: datetime) -> datetime:
    """Deterministic timestamp on a random day of the given month, clamped to now."""
    last_day = calendar.monthrange(year, month)[1]
    day = rng.randint(1, last_day)
    ts = datetime(year, month, day, rng.randint(0, 23), rng.randint(0, 59),
                  tzinfo=timezone.utc)
    if ts > now:
        ts = now - timedelta(hours=rng.randint(1, 72))
    return ts


def _seasonal_plan(profile: dict, now: datetime, rng: SeededRandom, rules: dict = None) -> list:
    """Monthly hazard/CAN volume plan across the rolling window.

    Each entry: {year, month, season, hazard_count, can_count}. Volumes follow
    the seasonal rules scaled by operator size; the annual total is floored at
    52 hazards so every operator clears the CAAN oversight minimum.
    ``rules`` optionally overrides the per-season (min, max) hazards/month
    bands — used by the virtual-tenant archetypes (demo-fixed-wing 8-20,
    demo-rotary-wing 10-22).
    """
    sf = _size_factor(profile)
    rule_set = rules or SEASON_RULES
    # Explicit rule overrides (virtual archetypes) are authoritative: monthly
    # counts clamp into the archetype envelope on BOTH sides.
    clamp_to_band = rules is not None
    plan = []
    for (y, m) in _rolling_months(now):
        season = _season_of(m)
        band = rule_set[season]
        lo, hi = band["hazards"] if isinstance(band, dict) else band
        count = int(round(((lo + hi) / 2) * sf)) + rng.choice((-1, 0, 0, 1))
        if (y, m) == (now.year, now.month):
            elapsed_ratio = now.day / calendar.monthrange(y, m)[1]
            count = max(1, int(round(count * elapsed_ratio)))
        if clamp_to_band:
            count = max(lo, min(count, hi))
        else:
            count = max(1, min(count, hi))
        can_count = max(1, int(round(count * 0.18)))
        plan.append({"year": y, "month": m, "season": season,
                     "hazard_count": count, "can_count": can_count})

    # Annual minimum — top up monsoon months first, then evenly.
    total = sum(p["hazard_count"] for p in plan)
    deficit = 52 - total
    if deficit > 0:
        order = sorted(plan, key=lambda p: p["hazard_count"])
        idx = 0
        while deficit > 0:
            entry = plan[idx % len(plan)]
            if entry["season"] == "MONSOON":
                entry["hazard_count"] += deficit
                deficit = 0
            else:
                entry["hazard_count"] += 1
                deficit -= 1
            idx += 2
    return plan


def _annual_hazard_count(profile: dict) -> int:
    now = datetime.now(timezone.utc)
    rng = SeededRandom(seed=_base_seed(profile["id"]) + 77)
    return sum(p["hazard_count"] for p in _seasonal_plan(profile, now, rng))


def _annual_can_count(profile: dict) -> int:
    now = datetime.now(timezone.utc)
    rng = SeededRandom(seed=_base_seed(profile["id"]) + 77)
    return sum(p["can_count"] for p in _seasonal_plan(profile, now, rng))


def _lifecycle_bucket(age_days: int) -> str:
    if age_days > 90:
        return "OLD"
    if age_days >= 30:
        return "MID"
    return "RECENT"


def _hazard_status_for(rng: SeededRandom, bucket: str) -> str:
    """Lifecycle simulation: old records mostly CLOSED, mid-range under review,
    recent records active / unmitigated."""
    if bucket == "OLD":
        return "Closed" if rng.random() < 0.80 else rng.choice(["Under Review", "Pending Closure"])
    if bucket == "MID":
        return rng.choice(["Processing", "Under Review", "Open", "Processing"])
    return rng.choice(["Open", "Open", "Open", "Processing"])


def _can_status_for(rng: SeededRandom, bucket: str) -> str:
    if bucket == "OLD":
        return "Under Review" if rng.random() < 0.85 else "Open"
    if bucket == "MID":
        return rng.choice(["Under Review", "Under Review", "Open"])
    return "Open"


def _cap_status_for(rng: SeededRandom, bucket: str) -> tuple:
    """(status, is_closed) per lifecycle bucket."""
    if bucket == "OLD":
        return ("Completed", True) if rng.random() < 0.85 else ("In Progress", False)
    if bucket == "MID":
        return rng.choice([("Under Review", False), ("In Progress", False)])
    return rng.choice([("In Progress", False), ("In Progress", False), ("Draft", False)])


def _seasonal_barrier(rng: SeededRandom, name: str, month: int, restored: bool) -> dict:
    season = _season_of(month)
    lo, hi = SEASON_RULES[season]["effective"]
    sample = _robustness_for(rng, rng.randint(lo, hi), restored=restored)
    return {
        "id": f"bar-{rng.randint(1000, 9999)}",
        "name": name,
        "quality": {
            "effectiveness": 3 if sample["robustness"] in ("Good", "Very Good", "Excellent") else 2,
            "cost_benefit": 3, "practicality": 3, "acceptability": 3,
            "enforceability": 3, "durability": 3, "disinclination": 3,
        },
        **sample,
    }


def _sram_block(rng: SeededRandom, month: int, restored: bool, severity_letter: str, top_event: str) -> dict:
    barriers = {
        "ecb": [_seasonal_barrier(rng, "Existing preventive control", month, restored)],
        "erb": [_seasonal_barrier(rng, "Existing recovery barrier", month, restored)],
        "ncb": [], "nrb": [],
    }
    return {
        "analysis_mode": "BOWTIE_SRAM",
        "severity": {"severity_letter": severity_letter, "descriptor": ""},
        "barriers": barriers,
        "bowtie": {"threats": [], "top_event": top_event, "consequences": []},
        "signoffs": None,
    }


def _hazard_count(profile: dict) -> int:
    return profile.get("hazard_count") or max(15, int(profile["vsr_count"] * 0.35))


def _can_count(profile: dict) -> int:
    return profile.get("can_count") or max(4, _hazard_count(profile) // 6)


def _caps_per_can(base_seed: int, can_index: int) -> int:
    """Deterministic CAP count for a given CAN (independent RNG stream so the
    dry-run estimate matches an actual run exactly)."""
    return SeededRandom(seed=base_seed + 8000 + can_index).randint(1, 3)


def _custodian(tenant_id: str, pick: int) -> dict:
    """Deterministic seeded custodian (email/uid/department) for a seeded doc.

    References only the four simplified role accounts (safety@, ops@, camo@,
    145@) — legacy safety.* / ae.* / manager.* accounts were removed 2026-08-14.
    """
    domain = CREDENTIAL_EMAIL_DOMAINS.get(tenant_id, f"{tenant_id}.com")
    roles = [
        ("safety", f"safety@{domain}", f"safety-{tenant_id}-001", "Safety"),
        ("ops", f"ops@{domain}", f"ops-{tenant_id}-001", "Flight Operations"),
        ("camo", f"camo@{domain}", f"camo-{tenant_id}-001", "CAMO"),
        ("maint145", f"145@{domain}", f"145-{tenant_id}-001", "Part-145"),
    ]
    token, email, uid, department = roles[pick % len(roles)]
    return {"assigned_to": email, "assigned_to_uid": uid, "department": department, "role": token}


def _postholder(tenant_id: str, pick: int) -> dict:
    """Deterministic provisioned postholder account for a CAN/CAP.

    Rotates across POSTHOLDER_ACCOUNTS so every functional role account
    (ops@ / 145@ / camo@ / pilot@ / safety@ / ae@) is assigned 1-2 CANs per
    tenant. ``assigned_to`` carries the account email and ``uid`` matches the
    provisioning scheme ({token}-{tenant_id}-001) so responsible-manager
    queries resolve on uid OR email OR department.
    """
    domain = CREDENTIAL_EMAIL_DOMAINS.get(tenant_id, f"{tenant_id}.com")
    acct = POSTHOLDER_ACCOUNTS[pick % len(POSTHOLDER_ACCOUNTS)]
    return {
        "postholder": acct["label"],
        "email": f"{acct['token']}@{domain}",
        "uid": f"{acct['token']}-{tenant_id}-001",
        "department": acct["department"],
        "role": acct["token"],
    }


def _sra_doc(severity: int, probability: int, assessed_by: str, assessed_at) -> dict:
    """Structured 5x5 Safety Risk Assessment block matching the server-side
    canonical shape (app/services/risk_matrix.py + CanCapService.classify_sra)."""
    index = compute_risk_index(severity, probability)
    return {
        "severity": severity,
        "severity_letter": SEVERITY_LETTERS[severity - 1],
        "probability": probability,
        "risk_index": index,
        "risk_level": get_risk_level(index),
        "risk_outcome": risk_outcome(severity, probability),
        "assessed_by": assessed_by,
        "assessed_at": assessed_at,
    }


def _fishbone_doc(rng: SeededRandom, seed: int, can_index: int, submitted_by: str) -> dict:
    """Structured Fishbone (Ishikawa 6M) RCA.

    One root cause per Fishbone branch (all 6 categories: Man, Machine,
    Medium, Mission, Management, Measurement), exactly one designated primary
    cause, and structured action items mapped 1:1 to each root cause via
    root_cause_id.
    """
    rng.seed(seed)
    available = list(FISHBONE_CATEGORIES)
    rng.shuffle(available)
    primary_category = available[0]

    root_causes = []
    action_items = []
    for i, category in enumerate(available):
        rc_id = f"rc-{can_index}-{i + 1}"
        root_causes.append({
            "id": rc_id,
            "category": category,
            "description": rng.choice(FISHBONE_ROOT_CAUSE_POOL[category]),
            "is_primary": category == primary_category,
        })
        action_items.append({
            "id": f"ai-{can_index}-{i + 1}",
            "description": rng.choice(FISHBONE_ACTION_TEMPLATES),
            "root_cause_id": rc_id,
            "owner": submitted_by,
            "target_date": None,
        })
    return {"root_causes": root_causes, "action_items": action_items}


def _icao_categories_for(tenant_id: str) -> list:
    """ICAO ADREP categories applicable to a tenant.

    Flight-only categories (LOCI, CFIT, MAC, ARC, WX) populate exclusively for
    AOC-holding airlines; AMO / aerodrome / ground-handling / regulator tenants
    draw only from non-flight categories (e.g. GCOL, BIRD, ENG, SYS, FIRE,
    PRO, RE, RI, CABIN, OTHER).
    """
    from seed.tenant_profiles import get_operates_flights

    if get_operates_flights(tenant_id):
        return list(ICAO_CATEGORIES)
    return [c for c in ICAO_CATEGORIES if c not in FLIGHT_ONLY_ICAO_CATEGORIES]


def _hazard_doc(rng: SeededRandom, profile: dict, index: int, created_at: datetime = None,
                hazard_id: str = None) -> dict:
    tenant_id = profile["id"]
    if created_at is None:
        created_at = generate_timestamp(rng, days_back_min=0, days_back_max=365)
    age_days = max(0, (datetime.now(timezone.utc) - created_at).days)
    bucket = _lifecycle_bucket(age_days)
    month = created_at.month
    sev_bump = SEASON_RULES[_season_of(month)]["sev_bump"]

    year = created_at.year
    category = rng.choice(_icao_categories_for(tenant_id))
    taxonomy = TAXONOMY_POOL[category]
    # Monsoon exposure raises occurrence severity (weather / CFIT / RE precursors).
    severity = min(5, rng.randint(2, 5) + (sev_bump if rng.random() < 0.5 else 0))
    probability = rng.randint(1, 4)
    risk_index = compute_risk_index(severity, probability)
    risk_level = get_risk_level(risk_index)
    priority = "H" if risk_index >= 12 else "M" if risk_index >= 6 else "L"
    status = _hazard_status_for(rng, bucket)
    custodian = _custodian(tenant_id, index)

    if hazard_id is None:
        function = resolve_function_code(profile.get("department") or custodian.get("department") or "")
        hazard_id = generate_hazard_id(function, priority, year, index + 1)
    title_pool = hazard_titles_for_tenant(tenant_id, HAZARD_TITLES)
    operation_context = "monsoon-exposed" if _season_of(month) == "MONSOON" else "routine"

    doc = {
        "tenant_id": tenant_id,
        "hazard_id": hazard_id,
        "function": hazard_id.split("/")[0] if "/" in hazard_id else "GEN",
        "title": rng.choice(title_pool),
        "description": rng.choice(HAZARD_DESCRIPTIONS),
        "source": rng.choice(SOURCES),
        "source_id": f"seed-{year}-{index + 1:03d}",
        "occurrence_type": category,
        "taxonomy": revalue_taxonomy(taxonomy),
        "taxonomy_specific": category,
        "threat": f"{category} precursor observed during {operation_context} operations",
        "consequence": rng.choice(["Minor", "Major", "Hazardous", "Catastrophic"]),
        "top_event": "Loss-of-control / collision with terrain" if category in ("LOCI", "CFIT", "MAC", "RE") else "Operational disruption with safety margin reduction",
        "severity": severity,
        "probability": probability,
        "risk_index": risk_index,
        "risk_level": risk_level,
        "risk_score": risk_index,
        "risk_tier": "Low" if risk_index <= 5 else ("Medium" if risk_index <= 15 else "High"),
        "priority": priority,
        "recommended_action": rng.choice(REQUIRED_ACTIONS),
        "corrective_action": "Pending CAN issuance",
        "corrective_action_flag": True,
        "srm_flag": True,
        "assigned_to": custodian["assigned_to"],
        "assigned_to_uid": custodian["assigned_to_uid"],
        "department": custodian["department"],
        "status": status,
        "priority_date": created_at,
        "status_date": created_at,
        "follow_up_date": created_at + timedelta(days=rng.randint(14, 60)),
        "created_by": "seed.runner",
        "created_at": created_at,
        "updated_at": created_at,
        "seed_version": SEED_VERSION,
        "seed_creator": "seed.runner",
    }
    follow_up = doc["follow_up_date"]
    if status == "Closed":
        # Logical progression: created_at <= closed_at, closure inside the window.
        closed_at = created_at + timedelta(days=min(rng.randint(20, 60), max(20, age_days)))
        if closed_at > datetime.now(timezone.utc):
            closed_at = datetime.now(timezone.utc)
        doc["closed_at"] = closed_at
        doc["closed_by"] = "seed.runner"
        doc["follow_up_date"] = min(follow_up, closed_at)
    return doc


def _can_doc(rng: SeededRandom, profile: dict, index: int, hazard_doc_id: str, hazard_id: str,
             issued_at: datetime = None, can_reference: str = None) -> dict:
    tenant_id = profile["id"]
    if issued_at is None:
        issued_at = generate_timestamp(rng, days_back_min=0, days_back_max=200)
    age_days = max(0, (datetime.now(timezone.utc) - issued_at).days)
    bucket = _lifecycle_bucket(age_days)
    month = issued_at.month
    assigned = _postholder(tenant_id, index)

    # Realistic unmitigated baseline 5x5 SRA — Medium or above (index >= 6).
    # Monsoon-season findings trend one severity step higher.
    season_bump = SEASON_RULES[_season_of(month)]["sev_bump"]
    severity = min(5, rng.randint(2, 4) + (season_bump if rng.random() < 0.5 else 0))
    probability = rng.randint(2, 5)
    while compute_risk_index(severity, probability) < 6 and probability < 5:
        probability += 1
    while compute_risk_index(severity, probability) < 6 and severity < 4:
        severity += 1
    initial_sra = _sra_doc(severity, probability, CAN_ISSUED_BY, issued_at)

    now = datetime.now(timezone.utc)
    target = issued_at + timedelta(days=rng.randint(14, 60))

    return {
        "can_reference": can_reference or f"CAN-{index + 1:03d}",
        "hazard_id": hazard_id,
        "hazard_doc_id": hazard_doc_id,
        "title": f"Corrective action notice {index + 1}",
        "description": f"Seeded corrective action requirement {index + 1} for {profile['name']}.",
        "required_action": rng.choice(REQUIRED_ACTIONS),
        "target_completion_date": target.date().isoformat(),
        "assigned_to": assigned["email"],
        "assigned_to_uid": assigned["uid"],
        "department": assigned["department"],
        "addressed_function": assigned["postholder"],
        "requested_function": "Safety Management (SMS)",
        "copies_to": f"safety@{CREDENTIAL_EMAIL_DOMAINS.get(tenant_id, tenant_id + '.com')}",
        "priority": rng.choice(["High", "Medium", "Low"]),
        "status": _can_status_for(rng, bucket),
        "issued_by": CAN_ISSUED_BY,
        "issued_by_uid": f"safety-{tenant_id}-001",
        "issued_at": issued_at,
        "tenant_id": tenant_id,
        "initial_severity": initial_sra["severity"],
        "initial_probability": initial_sra["probability"],
        "initial_risk_index": initial_sra["risk_index"],
        "initial_risk_level": initial_sra["risk_level"],
        "initial_risk_outcome": initial_sra["risk_outcome"],
        "initial_sra": initial_sra,
        "created_by": CAN_ISSUED_BY,
        "created_at": issued_at,
        "updated_at": issued_at,
        "seed_version": SEED_VERSION,
        "seed_creator": "seed.runner",
    }

def _cap_doc(rng: SeededRandom, can_reference: str, can_doc_id: str, index: int, department: str,
             submitted_by: dict, fishbone: dict, initial_risk_index: int = None,
             parent_issued_at: datetime = None, escalate: bool = False,
             cap_reference: str = None) -> dict:
    now = datetime.now(timezone.utc)

    # Submission follows the parent CAN issuance by 5-25 days.
    if parent_issued_at is not None:
        submitted_at = min(parent_issued_at + timedelta(days=rng.randint(5, 25)), now - timedelta(hours=1))
        submitted_at = max(submitted_at, parent_issued_at)
    else:
        submitted_at = generate_timestamp(rng, days_back_min=0, days_back_max=60)

    age_days = max(0, (now - submitted_at).days)
    bucket = _lifecycle_bucket(age_days)
    status, is_closed = _cap_status_for(rng, bucket)

    residual_severity = rng.randint(1, 3)
    residual_probability = rng.randint(1, 2)

    # Mitigated residual risk must sit strictly below the CAN's unmitigated
    # initial risk (e.g. 3x4 = 12 High at issuance -> 2x2 = 4 Low after the
    # CAP). Never seed identical Initial/Residual SRA pairs. Closed records
    # never carry a residual severity/probability above 3 (validated closure).
    if is_closed:
        residual_severity = min(residual_severity, 3)
    if initial_risk_index:
        while (
            compute_risk_index(residual_severity, residual_probability) >= initial_risk_index
            and residual_probability > 1
        ):
            residual_probability -= 1
        while (
            compute_risk_index(residual_severity, residual_probability) >= initial_risk_index
            and residual_severity > 1
        ):
            residual_severity -= 1
    residual_sra = _sra_doc(residual_severity, residual_probability, CAN_ISSUED_BY, submitted_at)

    # Timeline invariant: submitted_at <= target_completion_date <= closed_at.
    target = submitted_at + timedelta(days=rng.randint(30, 60))
    closed_at = None
    if is_closed:
        closed_at = max(target, submitted_at + timedelta(days=rng.randint(20, 45)))
        if closed_at > now:
            closed_at = now - timedelta(hours=rng.randint(1, 24))
        target = min(target, closed_at)

    # Realistic action-item milestones (staggered 14-90 days from submission),
    # keeping the 1:1 linkage to each Fishbone root cause.
    action_items = []
    for ai in fishbone["action_items"]:
        milestone = (submitted_at + timedelta(days=rng.randint(14, 90))).date().isoformat()
        action_items.append({**ai, "target_date": milestone})

    # Bow-Tie SRAM block on ~60% of CAPs — barrier quality honours the seasonal
    # band of the submission month; closures carry verified restorations.
    month = submitted_at.month
    include_sram = rng.random() < 0.60
    sram_data = None
    rca_method = "fishbone"
    idx0 = initial_risk_index or 6
    severity_letter = "A" if idx0 > 20 else "B" if idx0 > 15 else "C" if idx0 > 10 else "D"
    if include_sram:
        sram_data = _sram_block(
            rng, month, restored=is_closed, severity_letter=severity_letter,
            top_event=f"{can_reference} systemic exposure",
        )
        rca_method = "bow_tie"
        # Seasonal signature: every ACTIVE monsoon-season Bow-Tie carries at
        # least one weather-degraded barrier (monsoon exposure erodes ECMs).
        if month in (6, 7, 8) and not is_closed:
            ecb_list = sram_data["barriers"]["ecb"]
            if ecb_list:
                degraded = _robustness_for(rng, 0, restored=False)
                ecb_list[0].update(degraded)

    doc = {
        "cap_reference": cap_reference or f"{can_reference}-CAP-{index + 1:03d}",
        "can_id": can_doc_id,
        "department": department,
        "action_plan": rng.choice(ACTION_PLANS),
        "timeline": f"{rng.randint(30, 90)} days",
        "resources_required": "Manpower and materials per the plan",
        "implementation_plan": "Phase the work, verify effectiveness, and close out.",
        "target_completion_date": target.date().isoformat(),
        "status": status,
        "submitted_by": submitted_by["postholder"],
        "submitted_by_uid": submitted_by["uid"],
        "submitted_at": submitted_at,
        "created_at": submitted_at,
        "updated_at": closed_at or submitted_at,
        # Structured RCA (Fishbone / Ishikawa 6M) + selected methodology
        "root_causes": fishbone["root_causes"],
        "action_items": action_items,
        "rca_method": rca_method,
        "process_owner": submitted_by["postholder"],
        # Residual 5x5 SRA after mitigation
        "residual_severity": residual_sra["severity"],
        "residual_probability": residual_sra["probability"],
        "residual_risk_index": residual_sra["risk_index"],
        "residual_risk_level": residual_sra["risk_level"],
        "residual_risk_outcome": residual_sra["risk_outcome"],
        "residual_sra": residual_sra,
        # CAAN CAR-19 SRM (Bow-Tie) barrier snapshot
        "sram_data": sram_data,
        "seed_version": SEED_VERSION,
        "seed_creator": "seed.runner",
    }
    if closed_at:
        doc["closed_by"] = CAN_ISSUED_BY
        doc["closed_at"] = closed_at
        doc["closed_signature"] = CAN_ISSUED_BY

    # AE escalation — recent AE-assigned items only (pending executive decision).
    if escalate:
        doc["status"] = "Under Review"
        doc["escalated_to_ae"] = True
        doc["escalated_by"] = CAN_ISSUED_BY
        doc["escalated_at"] = min(submitted_at + timedelta(days=1), now)
        doc["escalation_reason"] = "Resource blockage / high residual exposure — pending AE authorization."

    return doc


def estimate_counts(tenant_ids=None, profiles=None) -> dict:
    """Counts for a dry run. Deterministic — matches an actual run."""
    now = datetime.now(timezone.utc)
    totals = {"hazards": 0, "cans": 0, "caps": 0}
    if profiles is None:
        profiles = [p for p in OPERATOR_PROFILES
                    if not tenant_ids or p["id"] in tenant_ids]
    for profile in profiles:
        base_seed = _base_seed(profile["id"])
        rng = SeededRandom(seed=base_seed + 77)
        rules = season_rules_for(profile["id"]) if profile.get("is_archetype") else None
        plan = _seasonal_plan(profile, now, rng, rules=rules)
        can_total = sum(p["can_count"] for p in plan)
        totals["hazards"] += sum(p["hazard_count"] for p in plan)
        totals["cans"] += can_total
        for i in range(can_total):
            totals["caps"] += _caps_per_can(base_seed, i)
    return totals


def create_all_hazard_can_data(db, tenant_ids=None, profiles=None) -> dict:
    """Seed hazards + CANs (+CAPs) across a 365-day seasonal window.

    ``profiles`` overrides the OPERATOR_PROFILES iteration — used by the
    virtual-tenant archetypes (demo-fixed-wing / demo-rotary-wing), which
    generate neutral FW-/RW- references formatted client-side.
    Every write goes through Firestore batches (flushed every 400 ops) so the
    ~2k-document full preset completes quickly. Deterministic ordering keeps
    ``estimate_counts`` parity with the dry-run totals.
    """
    from app.core.config import settings

    now = datetime.now(timezone.utc)
    totals = {"hazards": 0, "cans": 0, "caps": 0}

    if profiles is None:
        profiles = [p for p in OPERATOR_PROFILES
                    if not tenant_ids or p["id"] in tenant_ids]

    for profile in profiles:
        tenant_id = profile["id"]
        is_archetype = bool(profile.get("is_archetype"))
        rules = season_rules_for(tenant_id) if is_archetype else None
        base_seed = _base_seed(tenant_id)
        rng = SeededRandom(seed=base_seed + 77)

        plan = _seasonal_plan(profile, now, rng, rules=rules)
        tenant_ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id)

        batch = db.batch()
        ops = 0

        def _add():
            nonlocal ops
            ops += 1
            if ops >= 400:
                batch.commit()
                ops = 0
                return True
            return False

        # ── Hazards: distributed per the seasonal monthly plan ──────────────
        hazard_doc_ids = []
        hazard_ids_by_month = {}
        h_index = 0
        for entry in plan:
            for _ in range(entry["hazard_count"]):
                rng.seed(base_seed + h_index)
                created_at = _month_datetime(entry["year"], entry["month"], rng, now)
                doc = _hazard_doc(rng, profile, h_index, created_at=created_at)
                doc_id = _make_id("haz", tenant_id, h_index)
                ref = tenant_ref.collection("hazards").document(doc_id)
                batch.set(ref, doc)
                hazard_doc_ids.append(doc_id)
                hazard_ids_by_month.setdefault((entry["year"], entry["month"]), []).append(
                    (doc_id, doc["hazard_id"])
                )
                totals["hazards"] += 1
                h_index += 1
                _add()

        # ── CANs: seasonally weighted, assigned via exact proportional quotas ──
        can_index = 0
        cap_seq = 0
        all_hazards = [(doc_id, hid) for m in sorted(hazard_ids_by_month) for doc_id, hid in hazard_ids_by_month[m]]
        can_total = sum(p["can_count"] for p in plan)
        assignees = _assignee_sequence(can_total)
        for entry in plan:
            for c in range(entry["can_count"]):
                i = can_index
                rng.seed(base_seed + 5000 + i)

                # Link to a hazard from this month (fallback: global pool).
                pool = hazard_ids_by_month.get((entry["year"], entry["month"])) or all_hazards
                j = rng.randint(0, len(pool) - 1)
                hazard_doc_id, hazard_id = pool[j]

                issued_at = _month_datetime(entry["year"], entry["month"], rng, now)
                neutral_can = None
                if is_archetype:
                    neutral_can = neutral_can_ref(tenant_id, i + 1,
                                                  year=issued_at.year % 100 + 2000)
                can_doc = _can_doc(rng, profile, i, hazard_doc_id, hazard_id,
                                   issued_at=issued_at, can_reference=neutral_can)

                token = assignees[i]
                acct = next(a for a in POSTHOLDER_ACCOUNTS if a["token"] == token)
                domain = CREDENTIAL_EMAIL_DOMAINS.get(tenant_id, f"{tenant_id}.com")
                can_doc["assigned_to"] = f"{token}@{domain}"
                can_doc["assigned_to_uid"] = f"{token}-{tenant_id}-001"
                can_doc["department"] = acct["department"]
                can_doc["addressed_function"] = acct["label"]

                can_doc_id = _make_id("can", tenant_id, i)
                can_ref = tenant_ref.collection("can_cap").document(can_doc_id)
                batch.set(can_ref, can_doc)
                totals["cans"] += 1
                can_index += 1
                _add()

                age_days = max(0, (now - issued_at).days)
                bucket = _lifecycle_bucket(age_days)

                cap_count = _caps_per_can(base_seed, i)
                for k in range(cap_count):
                    rng.seed(base_seed + 9000 + i * 10 + k)
                    fishbone = _fishbone_doc(rng, seed=base_seed + 9500 + i * 10 + k,
                                             can_index=i, submitted_by=can_doc["assigned_to"])
                    escalate = (
                        token == "ae" and bucket == "RECENT" and k == 0
                    )
                    neutral_cap = None
                    if is_archetype:
                        cap_seq += 1
                        neutral_cap = neutral_cap_ref(tenant_id, cap_seq,
                                                      year=issued_at.year % 100 + 2000)
                    cap_doc = _cap_doc(
                        rng,
                        can_doc["can_reference"],
                        can_doc_id,
                        k,
                        can_doc["department"],
                        submitted_by={
                            "postholder": can_doc["assigned_to"],
                            "uid": can_doc["assigned_to_uid"],
                        },
                        fishbone=fishbone,
                        initial_risk_index=can_doc["initial_risk_index"],
                        parent_issued_at=issued_at,
                        escalate=escalate,
                        cap_reference=neutral_cap,
                    )
                    cap_doc_id = _make_id("cap", tenant_id, i * 10 + k)
                    cap_ref = can_ref.collection("caps").document(cap_doc_id)
                    batch.set(cap_ref, cap_doc)
                    totals["caps"] += 1
                    _add()

        if ops:
            batch.commit()

        logger.info(
            f"Seeded {totals['hazards']} hazards, {totals['cans']} CANs "
            f"(365-day seasonal) for {profile['name']}"
        )

    logger.info(
        f"Seeded {totals['hazards']} hazards, {totals['cans']} CANs, "
        f"{totals['caps']} CAPs total"
    )
    return totals