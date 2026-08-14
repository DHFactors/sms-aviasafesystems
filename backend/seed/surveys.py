from datetime import datetime, timezone
from loguru import logger

from app.services.survey_scoring import SURVEY_VERSION

from seed.config import (
    OPERATOR_PROFILES,
    SURVEY_COLLECTION,
    ICAO_SMS_PILLARS,
    ICAO_SMS_ELEMENTS,
    ALL_ICAO_ELEMENTS,
    SURVEY_DEPARTMENTS,
    NEPALI_NAMES,
    SEED_VERSION,
)
from seed.generator import (
    SeededRandom,
    generate_timestamp,
    generate_survey_response,
    _make_id,
)


def _compute_pillar_scores(element_scores: dict) -> dict:
    pillar_scores = {}
    for pillar, elements in ICAO_SMS_ELEMENTS.items():
        vals = [element_scores[e] for e in elements]
        pillar_scores[pillar] = round(sum(vals) / len(vals), 1)
    return pillar_scores


def generate_survey_batch(
    rng: SeededRandom,
    profile: dict,
    base_seed: int,
) -> list:
    tenant_id = profile["id"]
    count = profile["survey_count"]
    element_targets = profile["element_scores"]
    variance = profile["culture_variance"]
    dep_count = len(SURVEY_DEPARTMENTS)

    surveys = []
    for i in range(count):
        rng.seed(base_seed + i)
        elements = generate_survey_response(rng, element_targets, variance)

        overall = round(sum(elements.values()) / len(elements), 1)
        pillar_scores = _compute_pillar_scores(elements)

        dept = SURVEY_DEPARTMENTS[i % dep_count]
        year_exp = rng.choice(["<1", "1-3", "3-5", "5-10", "10+"])
        timestamp = generate_timestamp(rng, days_back_min=1, days_back_max=180)
        doc_id = _make_id("svy", tenant_id, i)

        surveys.append({
            "id": doc_id,
            "tenant_id": tenant_id,
            **elements,
            **pillar_scores,
            "overall_sms_maturity": overall,
            "status": "completed",
            "department": dept,
            "years_of_experience": year_exp,
            "respondent_name": rng.choice(NEPALI_NAMES) if rng.random() > 0.3 else None,
            "submitted_at": timestamp,
            "seed_index": i,
            "seed_version": SEED_VERSION,
        })

    return surveys


def _response_doc(survey: dict) -> dict:
    """Mirror of the production_seed `responses` subcollection shape, so the
    CAAN dashboard's cross-tenant `responses` KPI counts survey participation."""
    tenant_id = survey["tenant_id"]
    elements = {k: survey[k] for k in ALL_ICAO_ELEMENTS if k in survey}
    return {
        "tenant_id": tenant_id,
        "tenantId": tenant_id,
        "respondent_id": f"seed-{tenant_id}-{survey['seed_index']}",
        "respondentId": f"seed-{tenant_id}-{survey['seed_index']}",
        "answers": elements,
        "department": survey["department"],
        "submitted_at": survey["submitted_at"],
        "submittedAt": survey["submitted_at"],
        "survey_version": SURVEY_VERSION,
        "seed_version": SEED_VERSION,
    }


def write_surveys(db, surveys: list):
    from app.core.config import settings

    written = 0
    for s in surveys:
        doc_id = s["id"]
        tenant_id = s["tenant_id"]
        data = {k: v for k, v in s.items() if k != "id"}
        doc_ref = (
            db.collection(settings.FIREBASE_COLLECTION_TENANTS)
            .document(tenant_id)
            .collection(SURVEY_COLLECTION)
            .document(doc_id)
        )
        doc_ref.set(data)
        db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id).collection(
            "responses"
        ).document(doc_id).set(_response_doc(s))
        written += 1
    return written


def create_all_surveys(db, tenant_ids=None) -> int:
    base_seed = 10000
    total = 0

    for profile in OPERATOR_PROFILES:
        if tenant_ids and profile["id"] not in tenant_ids:
            continue
        tenant_id = profile["id"]
        rng = SeededRandom(seed=base_seed + hash(tenant_id) % 10000)

        surveys = generate_survey_batch(rng, profile, base_seed)
        count = write_surveys(db, surveys)
        total += count
        logger.info(f"Seeded {count} survey responses for {profile['name']}")

    logger.info(f"Seeded {total} survey responses total")
    return total
