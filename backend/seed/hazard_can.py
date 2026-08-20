"""Hazard + CAN/CAP seeding for the AviaSAFE demo data pipeline.

Writes deterministic, realistic hazard, corrective-action-notice (CAN) and
corrective-action-plan (CAP) documents into each operator tenant. Every
document is tagged with the current SEED_VERSION so the runner can later purge
stale seed docs (and only seed docs) without touching live or admin-seeded data.

Document shapes mirror what the services write (app/services/hazard_service.py
and app/services/can_cap_service.py) so the UIs and the unified Master Register
render the seeded rows natively.
"""

from datetime import timedelta
from loguru import logger

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
from app.services.risk_matrix import compute_risk_index, get_risk_level, risk_outcome
from app.services.hazard_service import generate_hazard_id

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

HAZARD_STATUSES = [
    "Open", "Open", "Open", "Processing",
    "Under Review", "Pending Closure", "Closed",
]
CAN_STATUSES = ["Open", "Open", "Under Review"]
CAP_STATUSES = ["Draft", "In Progress", "In Progress", "Completed"]

TAXONOMY_POOL = {
    "LOCI": "Organizational-Facilities",
    "CFIT": "Organizational-Facilities",
    "RE": "Organizational-Facilities",
    "RI": "Organizational-Facilities",
    "GCOL": "Organizational-Facilities",
    "MAC": "Technical",
    "ENG": "Technical",
    "SYS": "Technical",
    "FIRE": "Technical",
    "BIRD": "Wildlife",
    "CABIN": "Human Factors",
    "ARC": "Organizational-Documentation, Processes and Procedures",
    "WX": "Environmental",
    "OTHER": "Other",
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
    """Deterministic authentic operational postholder for a CAN/CAP.

    Rotates across the four CAN_ASSIGNED_POSTHOLDERS (label, department)
    tuples so every postholder is represented. Returns the human postholder
    label (displayed across CAN/CAP views) plus the matching functional account
    identity (email/uid/department) so seeded documents resolve against the
    four simplified role accounts.
    """
    domain = CREDENTIAL_EMAIL_DOMAINS.get(tenant_id, f"{tenant_id}.com")
    label, department = CAN_ASSIGNED_POSTHOLDERS[pick % len(CAN_ASSIGNED_POSTHOLDERS)]
    token = POSTHOLDER_ROLE[label]
    uid = f"{token}-{tenant_id}-001"
    return {
        "postholder": label,
        "email": f"{token}@{domain}",
        "uid": uid,
        "department": department,
        "role": token,
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


def _hazard_doc(rng: SeededRandom, profile: dict, index: int) -> dict:
    tenant_id = profile["id"]
    created_at = generate_timestamp(rng, days_back_min=0, days_back_max=365)
    year = created_at.year
    category = rng.choice(_icao_categories_for(tenant_id))
    taxonomy = TAXONOMY_POOL[category]
    severity = rng.randint(2, 5)
    probability = rng.randint(1, 4)
    risk_index = compute_risk_index(severity, probability)
    risk_level = get_risk_level(risk_index)
    priority = "H" if risk_index >= 12 else "M" if risk_index >= 6 else "L"
    status = rng.choice(HAZARD_STATUSES)
    custodian = _custodian(tenant_id, index)

    hazard_id = generate_hazard_id(tenant_id, taxonomy, year, index + 1)
    title_pool = hazard_titles_for_tenant(tenant_id, HAZARD_TITLES)

    doc = {
        "tenant_id": tenant_id,
        "hazard_id": hazard_id,
        "title": rng.choice(title_pool),
        "description": rng.choice(HAZARD_DESCRIPTIONS),
        "source": rng.choice(SOURCES),
        "occurrence_type": category,
        "taxonomy": taxonomy,
        "consequence": rng.choice(["Minor", "Major", "Hazardous", "Catastrophic"]),
        "severity": severity,
        "probability": probability,
        "risk_index": risk_index,
        "risk_level": risk_level,
        "risk_score": risk_index,
        "risk_tier": "Low" if risk_index <= 5 else ("Medium" if risk_index <= 15 else "High"),
        "priority": priority,
        "recommended_action": rng.choice(REQUIRED_ACTIONS),
        "corrective_action": "Pending CAN issuance",
        "assigned_to": custodian["assigned_to"],
        "assigned_to_uid": custodian["assigned_to_uid"],
        "department": custodian["department"],
        "status": status,
        "follow_up_date": created_at + timedelta(days=rng.randint(14, 60)),
        "created_by": "seed.runner",
        "created_at": created_at,
        "updated_at": created_at,
        "seed_version": SEED_VERSION,
        "seed_creator": "seed.runner",
    }
    if status == "Closed":
        doc["closed_at"] = created_at + timedelta(days=rng.randint(20, 60))
        doc["closed_by"] = "seed.runner"
    return doc


def _can_doc(rng: SeededRandom, profile: dict, index: int, hazard_doc_id: str, hazard_id: str) -> dict:
    tenant_id = profile["id"]
    issued_at = generate_timestamp(rng, days_back_min=0, days_back_max=200)
    assigned = _postholder(tenant_id, index)

    # Realistic baseline 5x5 SRA: severity C/D (2-4), probability 2-5.
    severity = rng.randint(2, 4)
    probability = rng.randint(2, 5)
    initial_sra = _sra_doc(severity, probability, CAN_ISSUED_BY, issued_at)

    return {
        "can_reference": f"CAN-{index + 1:03d}",
        "hazard_id": hazard_id,
        "hazard_doc_id": hazard_doc_id,
        "title": f"Corrective action notice {index + 1}",
        "description": f"Seeded corrective action requirement {index + 1} for {profile['name']}.",
        "required_action": rng.choice(REQUIRED_ACTIONS),
        "target_completion_date": (issued_at + timedelta(days=rng.randint(14, 60))).date().isoformat(),
        "assigned_to": assigned["postholder"],
        "assigned_to_uid": assigned["uid"],
        "department": assigned["department"],
        "addressed_function": assigned["postholder"],
        "requested_function": "Safety Management (SMS)",
        "copies_to": f"safety@{CREDENTIAL_EMAIL_DOMAINS.get(tenant_id, tenant_id + '.com')}",
        "priority": rng.choice(["High", "Medium", "Low"]),
        "status": rng.choice(CAN_STATUSES),
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


def _cap_doc(rng: SeededRandom, can_reference: str, can_doc_id: str, index: int, department: str, submitted_by: dict, fishbone: dict) -> dict:
    submitted_at = generate_timestamp(rng, days_back_min=0, days_back_max=60)
    residual_severity = rng.randint(1, 3)
    residual_probability = rng.randint(1, 2)
    residual_sra = _sra_doc(residual_severity, residual_probability, CAN_ISSUED_BY, submitted_at)

    # Realistic action-item milestones (staggered 14-90 days from submission),
    # keeping the 1:1 linkage to each Fishbone root cause.
    action_items = []
    for ai in fishbone["action_items"]:
        milestone = (submitted_at + timedelta(days=rng.randint(14, 90))).date().isoformat()
        action_items.append({**ai, "target_date": milestone})

    return {
        "cap_reference": f"{can_reference}-CAP-{index + 1:03d}",
        "can_id": can_doc_id,
        "department": department,
        "action_plan": rng.choice(ACTION_PLANS),
        "timeline": f"{rng.randint(30, 90)} days",
        "resources_required": "Manpower and materials per the plan",
        "implementation_plan": "Phase the work, verify effectiveness, and close out.",
        "target_completion_date": (submitted_at + timedelta(days=rng.randint(30, 90))).date().isoformat(),
        "status": rng.choice(CAP_STATUSES),
        "submitted_by": submitted_by["postholder"],
        "submitted_by_uid": submitted_by["uid"],
        "submitted_at": submitted_at,
        "created_at": submitted_at,
        "updated_at": submitted_at,
        # Structured RCA (Fishbone / Ishikawa 5M + Management)
        "root_causes": fishbone["root_causes"],
        "action_items": action_items,
        "process_owner": submitted_by["postholder"],
        # Residual 5x5 SRA after mitigation
        "residual_severity": residual_sra["severity"],
        "residual_probability": residual_sra["probability"],
        "residual_risk_index": residual_sra["risk_index"],
        "residual_risk_level": residual_sra["risk_level"],
        "residual_risk_outcome": residual_sra["risk_outcome"],
        "residual_sra": residual_sra,
        "seed_version": SEED_VERSION,
        "seed_creator": "seed.runner",
    }


def estimate_counts(tenant_ids=None) -> dict:
    """Counts for a dry run. Deterministic — matches an actual run."""
    totals = {"hazards": 0, "cans": 0, "caps": 0}
    for profile in OPERATOR_PROFILES:
        if tenant_ids and profile["id"] not in tenant_ids:
            continue
        base_seed = _base_seed(profile["id"])
        totals["hazards"] += _hazard_count(profile)
        can_count = _can_count(profile)
        totals["cans"] += can_count
        for i in range(can_count):
            totals["caps"] += _caps_per_can(base_seed, i)
    return totals


def create_all_hazard_can_data(db, tenant_ids=None) -> dict:
    """Seed hazards + CANs (+CAPs) into every OPERATOR_PROFILES tenant."""
    from app.core.config import settings

    totals = {"hazards": 0, "cans": 0, "caps": 0}

    for profile in OPERATOR_PROFILES:
        if tenant_ids and profile["id"] not in tenant_ids:
            continue
        tenant_id = profile["id"]
        base_seed = _base_seed(tenant_id)
        seed = base_seed
        rng = SeededRandom(seed=seed)

        tenant_ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id)

        hazard_doc_ids = []
        hazard_ids = []
        for i in range(_hazard_count(profile)):
            rng.seed(seed + i)
            doc = _hazard_doc(rng, profile, i)
            doc_id = _make_id("haz", tenant_id, i)
            tenant_ref.collection("hazards").document(doc_id).set(doc)
            hazard_doc_ids.append(doc_id)
            hazard_ids.append(doc["hazard_id"])
            totals["hazards"] += 1

        can_count = _can_count(profile)
        for i in range(can_count):
            rng.seed(seed + 5000 + i)
            j = rng.randint(0, len(hazard_doc_ids) - 1)
            can_doc_id = _make_id("can", tenant_id, i)
            can_doc = _can_doc(rng, profile, i, hazard_doc_ids[j], hazard_ids[j])
            tenant_ref.collection("can_cap").document(can_doc_id).set(can_doc)
            totals["cans"] += 1

            cap_count = _caps_per_can(base_seed, i)
            for k in range(cap_count):
                rng.seed(seed + 9000 + i * 10 + k)
                fishbone = _fishbone_doc(rng, seed + 9500 + i * 10 + k, i, can_doc["assigned_to"])
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
                )
                cap_doc_id = _make_id("cap", tenant_id, i * 10 + k)
                tenant_ref.collection("can_cap").document(can_doc_id).collection("caps").document(cap_doc_id).set(cap_doc)
                totals["caps"] += 1

        logger.info(
            f"Seeded {_hazard_count(profile)} hazards, {can_count} CANs, "
            f"{totals['caps']} CAPs for {profile['name']}"
        )

    logger.info(
        f"Seeded {totals['hazards']} hazards, {totals['cans']} CANs, "
        f"{totals['caps']} CAPs total"
    )
    return totals