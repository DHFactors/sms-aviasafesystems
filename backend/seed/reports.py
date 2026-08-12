from loguru import logger

from seed.config import (
    OPERATOR_PROFILES,
    VSR_OCCURRENCE_TYPES,
    GENERIC_MOR_OCCURRENCE_TYPES,
    VSR_NARRATIVE_TEMPLATES,
    VSR_NARRATIVE_KEYWORDS,
    MOR_NARRATIVE_TEMPLATES,
    MOR_NARRATIVE_KEYWORDS,
    INVESTIGATION_STATUSES,
    NEPAL_AIRPORTS,
    AIRCRAFT_REGISTRATIONS,
    SEED_VERSION,
)
from seed.generator import (
    SeededRandom,
    generate_narrative,
    generate_timestamp,
    generate_risk_score,
    generate_ai_analysis,
    generate_icao_severity,
    generate_icao_probability,
    severity_from_risk,
    SEVERITY_STR_TO_LEVEL,
    LEVEL_TO_SEVERITY_STR,
    LEVEL_TO_PROBABILITY_STR,
    _make_id,
)
from app.services.risk_matrix import compute_risk_index, get_risk_level


def _generate_airport(rng: SeededRandom, profile: dict) -> str:
    if rng.random() < 0.6:
        routes = profile.get("routes", [])
        if routes:
            parts = routes[rng.randint(0, len(routes) - 1)].split("-")
            if len(parts) >= 2:
                return rng.choice([f"{parts[0]} ({p})" for p in parts])
    return rng.choice(NEPAL_AIRPORTS)


def _generate_icao_risk_fields(
    rng: SeededRandom,
    risk_mean: float,
    risk_std: float,
    severity_str: str,
) -> dict:
    severity_level = SEVERITY_STR_TO_LEVEL.get(severity_str, 3)
    probability_level = generate_icao_probability(rng, risk_mean, risk_std)
    risk_index = compute_risk_index(severity_level, probability_level)
    risk_level = get_risk_level(risk_index)
    return {
        "severity_level": severity_level,
        "probability_level": probability_level,
        "risk_index": risk_index,
        "risk_level": risk_level,
    }


def _generate_vsr_document(
    rng: SeededRandom,
    profile: dict,
    index: int,
    base_seed: int,
) -> dict:
    rng.seed(base_seed + index)

    tenant_id = profile["id"]
    occurrence_type = rng.choice(VSR_OCCURRENCE_TYPES)
    narrative = generate_narrative(rng, VSR_NARRATIVE_TEMPLATES, VSR_NARRATIVE_KEYWORDS)
    risk_score = generate_risk_score(rng, profile["vsr_risk_mean"], profile["vsr_risk_std"])
    severity = severity_from_risk(risk_score)
    location = _generate_airport(rng, profile)
    timestamp = generate_timestamp(rng, days_back_min=1, days_back_max=365)
    is_anonymous = rng.random() < profile["anonymous_rate"]
    reg_choices = AIRCRAFT_REGISTRATIONS.get(tenant_id, ["9N-XXX"])
    aircraft_reg = rng.choice(reg_choices)

    flight_prefixes = profile.get("flight_number_prefixes", [])
    flight_prefix = rng.choice(flight_prefixes) if flight_prefixes else ""
    flight_number = f"{flight_prefix}{rng.randint(101, 999)}"

    statuses = ["SUBMITTED", "COMPLETED", "COMPLETED", "COMPLETED", "ARCHIVED"]
    if risk_score > 0.6:
        statuses.extend(["PROCESSING", "COMPLETED"])

    status = rng.choice(statuses)
    ai_status = "COMPLETED" if status in ("COMPLETED", "ARCHIVED") else "PENDING"

    icao_risk = _generate_icao_risk_fields(rng, profile["vsr_risk_mean"], profile["vsr_risk_std"], severity)
    ai_analysis = None

    if ai_status == "COMPLETED":
        rng.seed(base_seed + index + 10000)
        ai_analysis = generate_ai_analysis(rng, occurrence_type, narrative, is_mandatory=False)

    sms_categories = ["Safety", "Operations", "Maintenance", "Ground", "Flight Operations"]
    likelihoods = ["Remote", "Improbable", "Remote", "Probable", "Frequent", "Remote", "Improbable"]

    doc_id = _make_id("vsr", tenant_id, index)

    doc = {
        "tenant_id": tenant_id,
        "report_type": "voluntary",
        "status": status,
        "ai_status": ai_status,
        "narrative": narrative,
        "location": location,
        "occurrence_date": timestamp,
        "created_by": f"user_{rng.randint(100, 999)}",
        "created_at": timestamp,
        "updated_at": timestamp,
        "is_anonymous": is_anonymous,
        "flight_number": flight_number,
        "aircraft_registration": aircraft_reg,
        "occurrence_type": occurrence_type,
        "severity": severity,
        "risk_score": risk_score,
        "likelihood": rng.choice(likelihoods),
        "consequence": rng.choice(["Minor", "Major", "Hazardous", "Catastrophic"]),
        "sms_category": rng.choice(sms_categories),
        **icao_risk,
        "seed_version": SEED_VERSION,
    }

    if ai_analysis:
        doc["ai_analysis"] = ai_analysis

    return doc_id, doc


def _generate_mor_document(
    rng: SeededRandom,
    profile: dict,
    index: int,
    base_seed: int,
) -> dict:
    rng.seed(base_seed + index)

    tenant_id = profile["id"]
    occurrence_type = rng.choice(GENERIC_MOR_OCCURRENCE_TYPES)
    narrative = generate_narrative(rng, MOR_NARRATIVE_TEMPLATES, MOR_NARRATIVE_KEYWORDS)
    risk_score = generate_risk_score(rng, profile["mor_risk_mean"], profile["mor_risk_std"])
    severity = severity_from_risk(risk_score)
    location = _generate_airport(rng, profile)
    timestamp = generate_timestamp(rng, days_back_min=1, days_back_max=365)
    is_anonymous = False
    reg_choices = AIRCRAFT_REGISTRATIONS.get(tenant_id, ["9N-XXX"])
    aircraft_reg = rng.choice(reg_choices)

    flight_prefixes = profile.get("flight_number_prefixes", [])
    flight_prefix = rng.choice(flight_prefixes) if flight_prefixes else ""
    flight_number = f"{flight_prefix}{rng.randint(101, 999)}"

    status_candidates = ["NEW", "PROCESSING", "SUBMITTED", "COMPLETED", "COMPLETED", "ARCHIVED"]
    status = rng.choice(status_candidates)
    ai_status = "COMPLETED" if status in ("COMPLETED", "ARCHIVED") else "PENDING"

    icao_risk = _generate_icao_risk_fields(rng, profile["mor_risk_mean"], profile["mor_risk_std"], severity)
    ai_analysis = None
    investigation_status = "NOT_INVESTIGATED"

    if ai_status == "COMPLETED":
        rng.seed(base_seed + index + 20000)
        ai_analysis = generate_ai_analysis(rng, occurrence_type, narrative, is_mandatory=True)

        inv_weights = [0.05, 0.20, 0.45, 0.30]
        investigation_status = rng.choices(
            INVESTIGATION_STATUSES, weights=inv_weights, k=1
        )[0]

    doc_id = _make_id("mor", tenant_id, index)

    doc = {
        "tenant_id": tenant_id,
        "report_type": "mandatory",
        "status": status,
        "ai_status": ai_status,
        "narrative": narrative,
        "location": location,
        "occurrence_date": timestamp,
        "created_by": f"user_{rng.randint(100, 999)}",
        "created_at": timestamp,
        "updated_at": timestamp,
        "is_anonymous": False,
        "flight_number": flight_number,
        "aircraft_registration": aircraft_reg,
        "occurrence_type": occurrence_type,
        "severity": severity,
        "risk_score": risk_score,
        "likelihood": rng.choice(["Probable", "Frequent", "Remote"]),
        "consequence": rng.choice(["Major", "Hazardous", "Catastrophic"]),
        "sms_category": "Safety",
        "investigation_status": investigation_status,
        **icao_risk,
        "seed_version": SEED_VERSION,
    }

    if ai_analysis:
        doc["ai_analysis"] = ai_analysis

    return doc_id, doc


def write_report(db, doc_id: str, doc: dict):
    from app.core.config import settings

    tenant_id = doc["tenant_id"]
    doc_ref = (
        db.collection(settings.FIREBASE_COLLECTION_TENANTS)
        .document(tenant_id)
        .collection(settings.FIREBASE_COLLECTION_REPORTS)
        .document(doc_id)
    )
    doc_ref.set(doc)


def create_all_vsr_reports(db, tenant_ids=None) -> int:
    total = 0
    for profile in OPERATOR_PROFILES:
        if tenant_ids and profile["id"] not in tenant_ids:
            continue
        tenant_id = profile["id"]
        base_seed = 20000 + hash(tenant_id) % 10000
        rng = SeededRandom(seed=base_seed)
        count = profile["vsr_count"]

        for i in range(count):
            doc_id, doc = _generate_vsr_document(rng, profile, i, base_seed)
            write_report(db, doc_id, doc)
            total += 1

        logger.info(f"Seeded {count} VSR reports for {profile['name']}")

    logger.info(f"Seeded {total} VSR reports total")
    return total


def create_all_mor_reports(db, tenant_ids=None) -> int:
    total = 0
    for profile in OPERATOR_PROFILES:
        if tenant_ids and profile["id"] not in tenant_ids:
            continue
        tenant_id = profile["id"]
        base_seed = 30000 + hash(tenant_id) % 10000
        rng = SeededRandom(seed=base_seed)
        count = profile["mor_count"]

        for i in range(count):
            doc_id, doc = _generate_mor_document(rng, profile, i, base_seed)
            write_report(db, doc_id, doc)
            total += 1

        logger.info(f"Seeded {count} MOR reports for {profile['name']}")

    logger.info(f"Seeded {total} MOR reports total")
    return total
