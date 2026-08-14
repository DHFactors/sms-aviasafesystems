#!/usr/bin/env python3
"""Activate survey campaign windows for yeti-airlines and tara-air in sms-db-beta.

Read-only otherwise: only writes the tenant config map + derived surveyConfig
mirror, exactly matching what the /api/v1/tenants/{id}/config PUT endpoint
persists. Uses build_config_update so snake_case config and camelCase
surveyConfig stay in sync with the frontend reader contract.
"""

import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from app.firebase import initialize_firebase, get_db
from app.services.tenant_service import build_config_update

TITLE = "Annual SMS Safety Culture Survey 2026"
OPEN_DATE = "2026-08-13"
CLOSE_DATE = "2026-09-13"
TENANTS = ("yeti-airlines", "tara-air")


def main():
    initialize_firebase()
    db = get_db()

    for tid in TENANTS:
        doc = db.collection("tenants").document(tid).get()
        if not doc.exists:
            print(f"{tid}: DOCUMENT NOT FOUND — skipping")
            continue

        existing_config = (doc.to_dict() or {}).get("config") or {}
        existing_survey_config = (doc.to_dict() or {}).get("surveyConfig") or {}

        updated, survey_config = build_config_update(
            {
                "is_survey_active": True,
                "survey_open_date": OPEN_DATE,
                "survey_close_date": CLOSE_DATE,
            },
            existing_config,
            existing_survey_config,
        )
        # Add the campaign title to the surveyConfig map (frontend-visible metadata).
        survey_config["title"] = TITLE

        db.collection("tenants").document(tid).update(
            {"config": updated, "surveyConfig": survey_config}
        )
        print(
            f"{tid}: is_survey_active={updated['is_survey_active']} "
            f"open={updated.get('survey_open_date')} close={updated.get('survey_close_date')} "
            f"title={survey_config.get('title')}"
        )


if __name__ == "__main__":
    main()