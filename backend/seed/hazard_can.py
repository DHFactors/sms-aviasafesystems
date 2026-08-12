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

from seed.config import OPERATOR_PROFILES, SEED_VERSION
from seed.generator import SeededRandom, generate_timestamp, _make_id
from app.services.risk_matrix import compute_risk_index, get_risk_level
from app.services.hazard_service import generate_hazard_id

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
    """Deterministic seeded custodian (email/uid/department) for a seeded doc."""
    profile = None
    for op in OPERATOR_PROFILES:
        if op["id"] == tenant_id:
            profile = op
            break
    domain = profile["email_domain"] if profile else "aviasafesystems.com"
    roles = [
        ("ups", f"ops@{tenant_id}.com", f"ops-{tenant_id}-001", "Flight Operations"),
        ("safety", f"safety.{tenant_id}@{domain}", f"sm-{tenant_id}-001", ""),
        ("manager", f"manager.{tenant_id}@{domain}", f"mgr-{tenant_id}-001", ""),
    ]
    token, email, uid, department = roles[pick % len(roles)]
    return {"assigned_to": email, "assigned_to_uid": uid, "department": department, "role": token}


def _hazard_doc(rng: SeededRandom, profile: dict, index: int) -> dict:
    tenant_id = profile["id"]
    created_at = generate_timestamp(rng, days_back_min=0, days_back_max=365)
    year = created_at.year
    category = rng.choice(ICAO_CATEGORIES)
    taxonomy = TAXONOMY_POOL[category]
    severity = rng.randint(2, 5)
    probability = rng.randint(1, 4)
    risk_index = compute_risk_index(severity, probability)
    risk_level = get_risk_level(risk_index)
    priority = "H" if risk_index >= 12 else "M" if risk_index >= 6 else "L"
    status = rng.choice(HAZARD_STATUSES)
    custodian = _custodian(tenant_id, index)

    hazard_id = generate_hazard_id(tenant_id, taxonomy, year, index + 1)

    doc = {
        "tenant_id": tenant_id,
        "hazard_id": hazard_id,
        "title": rng.choice(HAZARD_TITLES),
        "description": rng.choice(HAZARD_DESCRIPTIONS),
        "source": rng.choice(SOURCES),
        "occurrence_type": category,
        "taxonomy": taxonomy,
        "consequence": rng.choice(["Minor", "Major", "Hazardous", "Catastrophic"]),
        "severity": severity,
        "probability": probability,
        "risk_index": risk_index,
        "risk_level": risk_level,
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
    custodian = _custodian(tenant_id, index + 1)
    return {
        "can_reference": f"CAN-{index + 1:03d}",
        "hazard_id": hazard_id,
        "hazard_doc_id": hazard_doc_id,
        "title": f"Corrective action notice {index + 1}",
        "description": f"Seeded corrective action requirement {index + 1} for {profile['name']}.",
        "required_action": rng.choice(REQUIRED_ACTIONS),
        "target_completion_date": (issued_at + timedelta(days=rng.randint(14, 60))).date().isoformat(),
        "assigned_to": custodian["assigned_to"],
        "assigned_to_uid": custodian["assigned_to_uid"],
        "department": custodian["department"],
        "priority": rng.choice(["High", "Medium", "Low"]),
        "status": rng.choice(CAN_STATUSES),
        "issued_by": "seed.runner",
        "issued_by_uid": "seed-runner-001",
        "issued_at": issued_at,
        "tenant_id": tenant_id,
        "created_by": "seed.runner",
        "created_at": issued_at,
        "updated_at": issued_at,
        "seed_version": SEED_VERSION,
        "seed_creator": "seed.runner",
    }


def _cap_doc(rng: SeededRandom, can_reference: str, can_doc_id: str, index: int, department: str) -> dict:
    submitted_at = generate_timestamp(rng, days_back_min=0, days_back_max=60)
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
        "submitted_by": "seed.runner",
        "submitted_by_uid": "seed-runner-001",
        "submitted_at": submitted_at,
        "created_at": submitted_at,
        "updated_at": submitted_at,
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
                cap_doc = _cap_doc(
                    rng,
                    can_doc["can_reference"],
                    can_doc_id,
                    k,
                    can_doc["department"],
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