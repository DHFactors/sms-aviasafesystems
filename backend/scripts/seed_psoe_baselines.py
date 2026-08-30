#!/usr/bin/env python3
"""
Seed baseline PSOE assessments for key demo tenants into Firestore.

For each target tenant this script writes two assessments in the top-level
``psoe_assessments`` collection:

  * ``{tenant_id}-baseline-completed`` — a COMPLETED CAAN Appendix 10
    surveillance audit scoring ~80% overall (Level 2 "Suitable / Operating")
    with realistic 4-pillar spread (Policy ~83%, SRM ~78%, Assurance ~80%,
    Promotion ~83%) and four gap findings (scores of 0/1).
  * ``{tenant_id}-baseline-draft`` — an in-progress DRAFT self-assessment
    (~54%) showing lower maturity and an unmitigated finding.

Component scores are computed by app.services.psoe_service.score_assessment,
so the stored component_scores / overall_score_pct / overall_level match what
the live API and /audits/psoe.html render.

Usage:
    python backend/scripts/seed_psoe_baselines.py                 # sms-db
    python backend/scripts/seed_psoe_baselines.py --database sms-db
"""

import argparse
import os
import sys
from datetime import datetime, timezone

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from app.core.config import settings
from app.firebase import initialize_firebase, get_db
from app.models.psoe import PSOEAnswer
from app.services.psoe_service import load_template, score_assessment

TARGET_TENANTS = ["buddha-air", "summit-air", "fishtail-air"]

TENANT_NAMES = {
    "buddha-air": "Buddha Air",
    "summit-air": "Summit Air",
    "fishtail-air": "Fishtail Air",
}

TENANT_SAFETY_EMAILS = {
    "buddha-air": "safety@buddha-air.com",
    "summit-air": "safety@summitair.com",
    "fishtail-air": "safety@fishtailair.com",
}

# Question-id -> (comment, evidence). {tenant} is replaced with the tenant name.
COMMENTS = {
    "SP-01": ("SMS implementation policy signed and published by the Accountable Executive", "SMS Manual rev 6, signed Jan 2026"),
    "SP-02": ("Safety responsibilities documented across all postholder roles", "Org chart + responsibility matrix v4"),
    "SP-03": ("Board-level safety review held quarterly", "Minutes: Q1-Q3 2026 safety committee"),
    "SP-04": ("SMS documentation library current and version-controlled", "Doc control register export"),
    "SP-05": ("Senior management review panel meets monthly", "Review agenda pack Aug 2026"),
    "SP-06": ("ERP documented but not exercised within the last 12 months", "ERP rev 3; no drill records on file"),
    "SRM-01": ("Hazard identification process embedded across departments", "Hazard log extract, 2026 YTD"),
    "SRM-02": ("Risk assessment methodology applied to operational changes", "MOC records: 2 runway works packages"),
    "SRM-03": ("SRM training completed by all safety-action group members", "Training matrix v2"),
    "SRM-04": ("Bow-tie analyses maintained for top hazards", "SRAM workspace exports (top 5 hazards)"),
    "SRM-05": ("Residual-risk reviews follow CAN/CAP closure", "CAP closure sample audit"),
    "SRM-06": ("Risk register updates lag behind seasonal operations tempo", "Register last reviewed May 2026"),
    "SA-01": ("Safety performance indicators monitored monthly", "SPI dashboard export Jul 2026"),
    "SA-02": ("Internal audit programme executed to plan", "Audit schedule completion 92%"),
    "SA-03": ("Management of change process applied to fleet changes", "MOC-2026-011 record"),
    "SA-04": ("Occurrence investigation loop closed within target days", "Investigation tracker Q2-Q3"),
    "SA-05": ("SPI trends not analysed against targets each quarter", "No Q2 trend analysis on file"),
    "SPROM-01": ("Recurrent safety training delivered to all operational staff", "Training records 95% complete"),
    "SPROM-02": ("Safety bulletins issued after significant events", "Bulletin archive 2026"),
    "SPROM-03": ("Just culture policy communicated across the workforce", "Staff survey results 2026"),
    "SPROM-04": ("Safety communication limited to annual refresher briefing", "Briefing log — frequency below plan"),
}

# Tenant-specific flavour for a handful of questions (esp. rotor-wing context).
TENANT_OVERRIDES = {
    "fishtail-air": {
        "SRM-02": ("Mountain LZ missions risk-assessed per charter; density-altitude limits applied", "AS350 B3e mission risk cards, Jul-Aug 2026"),
        "SRM-06": ("Monsoon-season LZ hazard reviews not kept current for remote sites", "LZ survey file gaps: Dolpa, Simikot"),
        "SA-01": ("LZ debris / FOD reports tracked but SPI thresholds undefined", "VSR extract: LZ debris reports Jun-Aug"),
        "SPROM-01": ("Mountain-flying recurrent training delivered to line pilots", "Bell 206 / AS350 ground school records"),
    },
    "summit-air": {
        "SRM-02": ("STOL performance assessments completed for Lukla and Bhojpur sectors", "L-410 UVP-E20 sector risk sheets"),
        "SA-01": ("Hard-landing SPI monitored against fleet threshold", "SPI dashboard Jul 2026"),
    },
}

# Score plans (question order per component as defined in psoe_appendix10.json).
COMPLETED_SCORES = {
    "component_1": [3, 3, 3, 2, 3, 1],   # Policy ~83%
    "component_2": [3, 3, 2, 3, 2, 1],   # SRM ~78%
    "component_3": [3, 3, 2, 3, 1],      # Assurance ~80%
    "component_4": [3, 3, 3, 1],         # Promotion ~83%
}

DRAFT_SCORES = {
    "component_1": [2, 2, 2, 3, 2, 1],
    "component_2": [2, 2, 1, 2, 2, 1],
    "component_3": [2, 2, 1, 2, 0],
    "component_4": [2, 2, 1, None],      # None -> N/A
}


def build_responses(template, score_plan, tenant_id):
    responses = []
    for comp in template.components:
        scores = score_plan[comp.id]
        for q, score in zip(comp.questions, scores):
            comment, evidence = TENANT_OVERRIDES.get(tenant_id, {}).get(
                q.id, COMMENTS[q.id]
            )
            if score is None:
                responses.append(PSOEAnswer(question_id=q.id, score=None, is_na=True))
            else:
                responses.append(PSOEAnswer(
                    question_id=q.id,
                    score=score,
                    is_na=False,
                    comment=comment.format(tenant=TENANT_NAMES[tenant_id]),
                    evidence=evidence,
                ))
    return responses


def doc_payload(tenant_id, status, assessment_date, title, notes):
    template = load_template()
    responses = build_responses(
        template,
        COMPLETED_SCORES if status == "completed" else DRAFT_SCORES,
        tenant_id,
    )
    scores = score_assessment(responses)
    now = datetime.now(timezone.utc)
    return {
        "tenant_id": tenant_id,
        "title": title,
        "status": status,
        "department": "Safety",
        "scope": "CAAN Appendix 10 SMS surveillance" if status == "completed" else "PSOE self-assessment (in progress)",
        "auditor_name": "Capt. Rajesh Sharma (CAAN SMD)" if status == "completed" else f"Safety Manager ({TENANT_NAMES[tenant_id]})",
        "assessor_email": TENANT_SAFETY_EMAILS[tenant_id],
        "assessment_date": assessment_date,
        "template_version": template.version,
        "responses": [r.model_dump() for r in responses],
        "component_scores": scores["component_scores"],
        "overall_score_pct": scores["overall_score_pct"],
        "overall_level": scores["overall_level"],
        "created_by": "scripts.seed_psoe_baselines",
        "created_at": now,
        "updated_at": now,
        "notes": notes,
    }


def main():
    parser = argparse.ArgumentParser(description="Seed baseline PSOE assessments.")
    # NOTE: default is hard-coded (not read from the environment) because
    # importing app.core.config loads backend/.env into the process env,
    # which would otherwise override the intended beta target.
    parser.add_argument("--database", default="sms-db")
    args = parser.parse_args()

    settings.FIREBASE_DATABASE_ID = args.database
    initialize_firebase()
    db = get_db()
    coll = db.collection("psoe_assessments")

    written = []
    for tid in TARGET_TENANTS:
        name = TENANT_NAMES[tid]

        completed = doc_payload(
            tid, "completed", datetime(2026, 8, 20, tzinfo=timezone.utc),
            f"CAAN Appendix 10 Surveillance Audit — {name} (2026)",
            "Baseline surveillance audit seeded for beta demo (gap findings included).",
        )
        coll.document(f"{tid}-baseline-completed").set(completed)
        written.append((f"{tid}-baseline-completed", completed["overall_score_pct"], completed["overall_level"]))

        draft = doc_payload(
            tid, "draft", datetime(2026, 8, 18, tzinfo=timezone.utc),
            f"{name} PSOE Self-Assessment (Draft)",
            "In-progress self-assessment seeded for beta demo.",
        )
        coll.document(f"{tid}-baseline-draft").set(draft)
        written.append((f"{tid}-baseline-draft", draft["overall_score_pct"], draft["overall_level"]))

    print(f"Wrote {len(written)} PSOE assessments to {args.database}:")
    for doc_id, pct, level in written:
        print(f"  {doc_id:<40} overall={pct}%  level={level}")


if __name__ == "__main__":
    main()
