"""Seed the ICAO top-risk reference data for the state-level SSP register.

Creates `state/icao_top_risks/categories/{category}` docs with the ICAO-aligned
top safety risk taxonomy and default SSP targets. Used as the baseline that the
aggregated state risk is measured against.

Usage (from backend/):
    python -m seed.state_risk
"""

from loguru import logger

from app.firebase import get_db
from app.services.state_risk_service import ICAO_TOP_RISK_CATEGORIES, STATE_COLLECTION, ICAO_REFERENCE_DOCUMENT


def create_all_state_risk_reference(db=None) -> int:
    db = db or get_db()
    coll = db.collection(STATE_COLLECTION).document(ICAO_REFERENCE_DOCUMENT).collection("categories")
    created = 0
    for cat_def in ICAO_TOP_RISK_CATEGORIES:
        coll.document(cat_def["category"]).set(cat_def)
        created += 1
        logger.info(f"Seeded ICAO reference category {cat_def['category']} ({cat_def['name']})")
    logger.info(f"Seeded {created} ICAO top-risk reference categories")
    return created


def main():
    from app.firebase import initialize_firebase
    initialize_firebase()
    create_all_state_risk_reference()


if __name__ == "__main__":
    main()
