# ============================================================================
# FILE: seed_caan_demo_data.py
# PATH: backend/scripts/seed_caan_demo_data.py
# PURPOSE: Seed beta so the CAAN (State Regulator) dashboard can be effectively
#          checked as state oversight. Writes, for ALL operator tenants:
#            * a `regulators/caan` State Regulator document (Nepal)
#            * `country` + `regulator_id` tags on each operator tenant
#            * survey responses in tenants/{id}/surveys (+ raw responses),
#              scored with the same survey_scoring math as live submissions
#            * hazards + reports in tenants/{id}/hazards and tenants/{id}/reports
#              so the State Risk Register / Cross-Tenant Aggregation populate
#          Idempotent: previously seeded docs (marked with seed_version) are
#          removed before re-seeding. Production sms-db is never touched.
#
# Usage:
#   python scripts/seed_caan_demo_data.py            # beta (sms-db-beta)
#   python scripts/seed_caan_demo_data.py sms-db-beta
#   SEED_DB=sms-db-beta python scripts/seed_caan_demo_data.py
# ============================================================================

import os
import random
import sys
from datetime import datetime, timedelta, timezone

DB_ID = os.environ.get("SEED_DB", sys.argv[1] if len(sys.argv) > 1 else "sms-db-beta")
os.environ["FIREBASE_DATABASE_ID"] = DB_ID

SEED_VERSION = "caan-demo-1"
REGULATOR_ID = "caan"
COUNTRY = "NP"
COUNTRY_NAME = "Nepal"

# The operators overseen by the CAAN State Regulator. Matches the 5 active beta
# provider tenants (seed/config.py OPERATOR_PROFILES). Legacy operators were
# archived and are no longer overseen. Base maturity (1-5) drives the seeded
# SMS culture so the CAAN dashboard shows a realistic spread of maturity.
OPERATORS = [
    {"id": "buddha-air", "name": "Buddha Air", "maturity": 4.1},
    {"id": "air-dynasty", "name": "Air Dynasty Heli Services", "maturity": 3.0},
    {"id": "ktm-mro", "name": "KTM MRO Services", "maturity": 3.5},
    {"id": "pokhara-aerodrome", "name": "Pokhara Aerodrome", "maturity": 2.8},
    {"id": "himalaya-ground-services", "name": "Himalaya Ground Handling", "maturity": 3.3},
]

ICAO_CATEGORIES = [
    "LOCI", "CFIT", "RE", "RI", "MAC", "WX", "ENG", "SYS",
    "FIRE", "BIRD", "GCOL", "CABIN", "ARC", "OTHER",
]

DEPARTMENTS = ["Flight Operations", "Maintenance & Engineering", "Ground Handling",
               "Cabin Crew", "Administration"]
YEARS_EXP = ["0-2", "2-7", "7-15", "15+"]

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND, ".env"), override=False)

from firebase_admin import credentials, firestore
import firebase_admin

from app.services.survey_scoring import (
    BINARY_QUESTIONS,
    QUESTION_PILLARS,
    SURVEY_VERSION,
    compute_overall_maturity,
    compute_percentage_score,
    compute_pillar_scores,
    compute_question_scores,
)
from app.services.risk_matrix import compute_risk_index, get_risk_level

creds = credentials.Certificate({
    "type": "service_account",
    "project_id": os.environ.get("FIREBASE_PROJECT_ID"),
    "private_key": os.environ.get("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n"),
    "client_email": os.environ.get("FIREBASE_CLIENT_EMAIL"),
    "token_uri": os.environ.get("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
})

if not firebase_admin._apps:
    firebase_admin.initialize_app(creds)
app = firebase_admin.get_app()
db = firestore.client(app=app, database_id=DB_ID)

import app.firebase as fb
fb._db = db
fb._firebase_app = app


# ============================================================================
# Helpers
# ============================================================================

def clamp(v, lo=1, hi=5):
    return max(lo, min(hi, int(round(v))))


def random_answers(maturity: float) -> dict:
    """Generate one plausible set of answers for the master question contract.
    Per-question scores sit around a pillar mean drawn from the tenant's
    maturity, with independent noise and the occasional weak response."""
    pillar_means = {
        "safety_policy": clamp(maturity + random.uniform(-0.3, 0.5)),
        "safety_risk_management": clamp(maturity + random.uniform(-0.5, 0.4)),
        "safety_assurance": clamp(maturity + random.uniform(-0.4, 0.3)),
        "safety_promotion": clamp(maturity + random.uniform(-0.5, 0.6)),
    }
    answers = {}
    for qid, pillar in QUESTION_PILLARS.items():
        if qid in BINARY_QUESTIONS:
            aware_prob = clamp(maturity) / 5.0
            answers[qid] = random.random() < aware_prob
            continue
        mean = pillar_means[pillar]
        answers[qid] = clamp(random.gauss(mean, 0.8))
    return answers


def survey_doc(tid: str, answers: dict, submitted_at: datetime, idx: int) -> dict:
    pillar_scores = compute_pillar_scores(answers)
    overall = compute_overall_maturity(pillar_scores)
    question_scores = compute_question_scores(answers)
    return {
        "tenant_id": tid,
        "tenantId": tid,
        "submitted_at": submitted_at,
        "submittedAt": submitted_at,
        "respondent_id": f"seed-{tid}-{idx}",
        "respondentId": f"seed-{tid}-{idx}",
        "department": random.choice(DEPARTMENTS),
        "employee_category": random.choice(["Flight Crew", "Cabin Crew", "Engineer", "Ground Staff", "Admin"]),
        "years_experience": random.choice(YEARS_EXP),
        "language_used": random.choice(["en", "en", "en", "ne"]),
        "survey_version": SURVEY_VERSION,
        "seed_version": SEED_VERSION,
        "answers": answers,
        "question_scores": question_scores,
        "questionScores": question_scores,
        "safety_policy": pillar_scores["safety_policy"],
        "safety_risk_management": pillar_scores["safety_risk_management"],
        "safety_assurance": pillar_scores["safety_assurance"],
        "safety_promotion": pillar_scores["safety_promotion"],
        "overall_sms_maturity": overall,
        "overallSMSMaturity": overall,
        "pillarScores": pillar_scores,
        "overall_score_pct": compute_percentage_score(overall),
    }


# Mirrors app/routes/reports.py:_determine_hazard_taxonomy so seeded hazards
# carry a taxonomy value accepted by the HazardTaxonomy enum (API contract).
ICAO_TO_TAXONOMY = {
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
    "PRO": "Organizational-Documentation, Processes and Procedures",
    "WX": "Environmental",
    "OTHER": "Other",
}


def hazard_doc(tid: str, cat: str, created_at: datetime, idx: int) -> dict:
    severity = random.randint(2, 4)
    probability = random.randint(2, 4)
    risk_index = compute_risk_index(severity, probability)
    return {
        "tenant_id": tid,
        "hazard_id": f"{tid}-HZ-{created_at.year}-{idx:03d}",
        "title": f"Demo hazard {cat} at {tid}",
        "description": f"Seeded demonstration hazard classified as {cat}.",
        "source": random.choice(["VSR", "MOR", "Safety Inspection"]),
        "occurrence_category": cat,
        "taxonomy": ICAO_TO_TAXONOMY.get(cat, "Other"),
        "severity": severity,
        "probability": probability,
        "risk_index": risk_index,
        "risk_level": get_risk_level(risk_index),
        "priority": "H" if risk_index >= 12 else "M" if risk_index >= 6 else "L",
        "status": random.choice(["Open", "Open", "Under Review", "Closed"]),
        "created_by": "seed-caan-demo",
        "created_at": created_at,
        "updated_at": created_at,
        "seed_version": SEED_VERSION,
    }


def report_doc(tid: str, cat: str, created_at: datetime, idx: int) -> dict:
    severity = random.randint(2, 5)
    probability = random.randint(1, 4)
    risk_index = compute_risk_index(severity, probability)
    return {
        "tenant_id": tid,
        "tenantId": tid,
        "report_type": random.choice(["voluntary", "voluntary", "mandatory"]),
        "status": "NEW",
        "ai_status": "PENDING",
        "narrative": f"Seeded demonstration report ({cat}) from {tid}.",
        "location": random.choice(["KTM", "Pokhara", "Bhairahawa", "In-flight", "Kathmandu Valley"]),
        "occurrence_type": "Report",
        "occurrence_category": cat,
        "severity": str(severity),
        "severity_level": severity,
        "probability": probability,
        "probability_level": probability,
        "risk_index": risk_index,
        "risk_level": get_risk_level(risk_index),
        "is_anonymous": random.random() < 0.5,
        "occurrence_date": created_at.isoformat(),
        "created_by": "seed-caan-demo",
        "created_at": created_at,
        "updated_at": created_at,
        "seed_version": SEED_VERSION,
    }


def clear_seeded(tid: str):
    """Remove previously seeded demo docs for a tenant."""
    ref = db.collection("tenants").document(tid)
    for sub in ("surveys", "responses", "hazards", "reports"):
        snaps = ref.collection(sub).where("seed_version", "==", SEED_VERSION).get()
        for snap in snaps:
            snap.reference.delete()


def count_docs(tid: str, sub: str) -> int:
    return len(ref_count := list(db.collection("tenants").document(tid).collection(sub).limit(2000).get()))


# ============================================================================
# 1. State Regulator document + operator tenant tags
# ============================================================================

def seed_regulator():
    regulator_ref = db.collection("regulators").document(REGULATOR_ID)
    regulator_ref.set({
        "id": REGULATOR_ID,
        "type": "state_regulator",
        "name": f"Civil Aviation Authority of {COUNTRY_NAME}",
        "short_name": "CAAN",
        "country": COUNTRY,
        "country_name": COUNTRY_NAME,
        "domain": "ssp.caanepal.gov.np",
        "operator_tenant_ids": [o["id"] for o in OPERATORS],
        "active": True,
        "updated_at": datetime.now(timezone.utc),
    }, merge=True)
    print(f"[1] State Regulator '{REGULATOR_ID}' ({COUNTRY_NAME}) ensured.")

    for op in OPERATORS:
        db.collection("tenants").document(op["id"]).set({
            "regulator_id": REGULATOR_ID,
            "country": COUNTRY,
            "active": True,
        }, merge=True)
    print(f"[1] {len(OPERATORS)} operator tenants tagged regulator_id={REGULATOR_ID}, country={COUNTRY}.")


# ============================================================================
# 2. Survey responses (SMS maturity)
# ============================================================================

def seed_surveys(force: bool = False):
    now = datetime.now(timezone.utc)
    total = 0
    for op in OPERATORS:
        tid = op["id"]
        if not force and count_docs(tid, "surveys") > 0:
            print(f"[2] {tid}: surveys exist, skipping (use --force to reseed).")
            continue
        clear_seeded(tid)
        ref = db.collection("tenants").document(tid)
        n = random.randint(20, 34)
        for i in range(n):
            answers = random_answers(op["maturity"])
            submitted_at = now - timedelta(days=random.uniform(0, 130))
            doc = survey_doc(tid, answers, submitted_at, i)
            ref.collection("surveys").add(doc)
            ref.collection("responses").add({
                "tenant_id": tid,
                "tenantId": tid,
                "respondent_id": doc["respondent_id"],
                "respondentId": doc["respondent_id"],
                "answers": answers,
                "department": doc["department"],
                "submitted_at": submitted_at,
                "submittedAt": submitted_at,
                "survey_version": SURVEY_VERSION,
                "seed_version": SEED_VERSION,
            })
        total += n
        print(f"[2] {tid}: seeded {n} survey responses (maturity ~{op['maturity']}).")
    print(f"[2] surveys seeded: {total} total.")


# ============================================================================
# 3. Hazards + reports (State Risk Register / Cross-Tenant Aggregation)
# ============================================================================

def seed_hazards_and_reports(force: bool = False):
    now = datetime.now(timezone.utc)
    h_total = r_total = 0
    for op in OPERATORS:
        tid = op["id"]
        clear_seeded(tid)
        ref = db.collection("tenants").document(tid)
        cats = random.sample(ICAO_CATEGORIES, k=random.randint(4, 7))
        for idx, cat in enumerate(cats):
            created_at = now - timedelta(days=random.uniform(0, 200))
            ref.collection("hazards").add(hazard_doc(tid, cat, created_at, idx))
            h_total += 1
        n_reports = random.randint(3, 6)
        for idx in range(n_reports):
            created_at = now - timedelta(days=random.uniform(0, 200))
            cat = random.choice(ICAO_CATEGORIES)
            ref.collection("reports").add(report_doc(tid, cat, created_at, idx))
            r_total += 1
        print(f"[3] {tid}: seeded hazards + {n_reports} reports.")
    print(f"[3] hazards seeded: {h_total}, reports seeded: {r_total}.")


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    force = "--force" in sys.argv
    print(f"Seeding CAAN demo data -> database={DB_ID} (force={force})\n")
    seed_regulator()
    seed_surveys(force=force)
    seed_hazards_and_reports(force=force)
    print(f"\nDone. CAAN State Regulator dashboard can now be checked for {len(OPERATORS)} operators.")
