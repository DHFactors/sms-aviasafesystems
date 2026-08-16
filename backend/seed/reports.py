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
    VSR_ANONYMOUS_RATIO,
    VSR_ANONYMOUS_LABEL,
    VSR_ORIGINATOR_PERSONAS,
    MOR_ORIGINATOR_AUTHORITIES,
    PERSONA_ORGANISATIONS,
)
from seed.tenant_profiles import (
    get_aircraft_fleet,
    get_authorized_destinations,
    vsr_occurrence_types_for_tenant,
    mor_occurrence_types_for_tenant,
)

# Mapped to each operator tenant in build_persona_org_map(); falls back to the
# operator name when a tenant has no explicit entry.
PERSONA_ORGANISATIONS_FALLBACK = "the operator"
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


def generate_vsr_originator(rng: SeededRandom, tenant_id: str) -> dict:
    """Strict 90:10 VSR anonymity split.

    90% of generated VSRs are tagged anonymous (originator_name
    "Anonymous (Confidential VSR)", is_anonymous True, contact_details None).
    The remaining 10% randomly pull from named operational personas with
    optional contact details.
    """
    if rng.random() < VSR_ANONYMOUS_RATIO:
        return {
            "originator_name": VSR_ANONYMOUS_LABEL,
            "is_anonymous": True,
            "contact_details": None,
            "department": None,
        }

    persona = rng.choice(VSR_ORIGINATOR_PERSONAS)
    org = PERSONA_ORGANISATIONS.get(tenant_id, PERSONA_ORGANISATIONS_FALLBACK)
    # Optional contact details: ~half of the named reporters leave contact info.
    contact_details = None
    if rng.random() < 0.5:
        contact_details = {
            "role": persona["department"],
            "organisation": org,
            "contact": f"reporter.{tenant_id.replace('-', '')}@email.com",
        }
    return {
        "originator_name": persona["name"],
        "is_anonymous": False,
        "contact_details": contact_details,
        "department": persona["department"],
    }


def _generate_airport(rng: SeededRandom, profile: dict) -> str:
    """Pick a seeded location from the tenant's authorized destinations.

    Falls back to route-derived airports, then to the national airport list,
    so unregistered tenants still seed cleanly.
    """
    destinations = get_authorized_destinations(profile["id"])
    if destinations:
        return rng.choice(destinations)
    if rng.random() < 0.6:
        routes = profile.get("routes", [])
        if routes:
            parts = routes[rng.randint(0, len(routes) - 1)].split("-")
            if len(parts) >= 2:
                return rng.choice([f"{parts[0]} ({p})" for p in parts])
    return rng.choice(NEPAL_AIRPORTS)


def _generate_aircraft(
    rng: SeededRandom,
    profile: dict,
) -> dict:
    """Fleet-matched aircraft identity for a report.

    Selects the aircraft TYPE from the tenant's registered fleet (airlines and
    rotor-wing operators) and pairs it with a real registration from that
    tenant. Non-flying providers (AMO / aerodrome / ground handling) fall back
    to a generic 9N-XXX tail with no type.
    """
    tenant_id = profile["id"]
    fleet = get_aircraft_fleet(tenant_id)
    aircraft_type = None
    reg_choices = AIRCRAFT_REGISTRATIONS.get(tenant_id, ["9N-XXX"])

    if fleet and tenant_id in AIRCRAFT_REGISTRATIONS:
        aircraft_type = rng.choice(fleet)
    aircraft_reg = rng.choice(reg_choices)
    return {"aircraft_registration": aircraft_reg, "aircraft_type": aircraft_type}


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
    occurrence_pool = vsr_occurrence_types_for_tenant(tenant_id, VSR_OCCURRENCE_TYPES)
    occurrence_type = rng.choice(occurrence_pool)
    narrative = generate_narrative(rng, VSR_NARRATIVE_TEMPLATES, VSR_NARRATIVE_KEYWORDS)
    risk_score = generate_risk_score(rng, profile["vsr_risk_mean"], profile["vsr_risk_std"])
    severity = severity_from_risk(risk_score)
    location = _generate_airport(rng, profile)
    timestamp = generate_timestamp(rng, days_back_min=1, days_back_max=365)
    originator = generate_vsr_originator(rng, tenant_id)
    is_anonymous = originator["is_anonymous"]
    aircraft = _generate_aircraft(rng, profile)

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
        "originator_name": originator["originator_name"],
        "is_anonymous": is_anonymous,
        "contact_details": originator["contact_details"],
        "created_by": originator["originator_name"],
        "reporter_name": None if is_anonymous else originator["originator_name"],
        "reporter_role": originator["department"],
        "reporter_organisation": PERSONA_ORGANISATIONS.get(tenant_id, PERSONA_ORGANISATIONS_FALLBACK),
        "reporter_email": None,
        "created_at": timestamp,
        "updated_at": timestamp,
        "flight_number": flight_number,
        "aircraft_registration": aircraft["aircraft_registration"],
        "aircraft_type": aircraft["aircraft_type"],
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
    occurrence_pool = mor_occurrence_types_for_tenant(tenant_id, GENERIC_MOR_OCCURRENCE_TYPES)
    occurrence_type = rng.choice(occurrence_pool)
    narrative = generate_narrative(rng, MOR_NARRATIVE_TEMPLATES, MOR_NARRATIVE_KEYWORDS)
    risk_score = generate_risk_score(rng, profile["mor_risk_mean"], profile["mor_risk_std"])
    severity = severity_from_risk(risk_score)
    location = _generate_airport(rng, profile)
    timestamp = generate_timestamp(rng, days_back_min=1, days_back_max=365)
    is_anonymous = False
    aircraft = _generate_aircraft(rng, profile)

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

    # MOR originators are routed exclusively through compliance authorities.
    created_by = rng.choice(MOR_ORIGINATOR_AUTHORITIES)
    reporter_role = (
        "Quality Assurance / Compliance"
        if created_by.startswith("Quality")
        else "Technical Services / Airworthiness"
    )

    doc = {
        "tenant_id": tenant_id,
        "report_type": "mandatory",
        "status": status,
        "ai_status": ai_status,
        "narrative": narrative,
        "location": location,
        "occurrence_date": timestamp,
        "originator_name": created_by,
        "is_anonymous": False,
        "contact_details": {
            "role": reporter_role,
            "organisation": PERSONA_ORGANISATIONS.get(tenant_id, PERSONA_ORGANISATIONS_FALLBACK),
            "contact": None,
        },
        "created_by": created_by,
        "reporter_name": created_by,
        "reporter_role": reporter_role,
        "reporter_organisation": PERSONA_ORGANISATIONS.get(tenant_id, PERSONA_ORGANISATIONS_FALLBACK),
        "reporter_email": None,
        "created_at": timestamp,
        "updated_at": timestamp,
        "flight_number": flight_number,
        "aircraft_registration": aircraft["aircraft_registration"],
        "aircraft_type": aircraft["aircraft_type"],
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
