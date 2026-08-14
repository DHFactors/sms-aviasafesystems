#!/usr/bin/env python3
"""Read-only audit of tenant survey campaign status in the configured database.

Outputs a plain-text table of every tenant's survey status based on the exact
same window logic the frontend survey page (public/survey/app.js
`enforceSurveyWindow`) and backend tenant_service apply:

    state = open (default)
    if is_survey_active is explicitly False  -> closed
    else if open_date in the future          -> scheduled
    else if close_date in the past           -> closed
    else                                     -> open

"Redirect Expected" = Yes when the survey is OPEN (the survey form is live and
employees hitting /survey/?tenant=... are expected to be able to complete it).
"""

import os
import sys
from datetime import date, datetime

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from app.firebase import initialize_firebase, get_db


def _norm_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        text = str(value).strip()
        if "T" in text:
            text = text.split("T")[0]
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _survey_state(survey_config, config):
    cfg = survey_config or {}
    tenant_config = config or {}

    open_date = _norm_date(
        cfg.get("openDate") or cfg.get("open_date") or tenant_config.get("survey_open_date")
    )
    close_date = _norm_date(
        cfg.get("closeDate") or cfg.get("close_date") or tenant_config.get("survey_close_date")
    )

    active = cfg.get("isActive")
    if not isinstance(active, bool):
        active = cfg.get("is_active")
    if not isinstance(active, bool):
        active = tenant_config.get("is_survey_active")

    today = date.today()
    if active is False:
        return "CLOSED", open_date, close_date
    if open_date and today < open_date:
        return "SCHEDULED", open_date, close_date
    if close_date and today > close_date:
        return "CLOSED", open_date, close_date
    return "OPEN", open_date, close_date


def main():
    initialize_firebase()
    db = get_db()
    docs = sorted(db.collection("tenants").get(), key=lambda d: d.id)

    header = f"{'Tenant ID':<26} | {'Status':<10} | {'Config':<13} | {'Window Start':<12} | {'Window End':<12} | {'Redirect Expected'}"
    print(header)
    print("-" * len(header))
    for d in docs:
        x = d.to_dict() or {}
        survey_config = x.get("surveyConfig") or {}
        config = x.get("config") or {}
        state, open_date, close_date = _survey_state(survey_config, config)
        configured = bool(survey_config or config.get("survey_open_date") or config.get("is_survey_active") is not None)
        redirect = "Yes" if state == "OPEN" else "No"
        config_label = "configured" if configured else "none"
        print(
            f"{d.id:<26} | {state:<10} | {config_label:<13} | {str(open_date or '-'):<12} | {str(close_date or '-'):<12} | {redirect}"
        )
    print()
    print("Note: 'none' = no surveyConfig map and no survey_* config fields in the tenant doc.")
    print("      Per frontend enforceSurveyWindow, an unconfigured tenant defaults to OPEN (form live).")


if __name__ == "__main__":
    main()