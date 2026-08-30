# ============================================================================
# FILE: seed_flight_diversions.py
# PATH: backend/scripts/seed_flight_diversions.py
# PURPOSE: Seed demo flight diversion reports for every operator tenant so the
#          Flight Diversion register can be checked. Mirrors the exact doc
#          shape produced by FlightDiversionService.create_diversion, and also
#          creates the linked "Flight Diversion" hazard for each record (same
#          behaviour as the live POST /api/flight-diversions flow).
#          Idempotent: previously seeded docs (marked with seed_version) are
#          removed before re-seeding. Production sms-db is never touched.
#
# Usage:
#   python scripts/seed_flight_diversions.py            # beta (sms-db)
#   python scripts/seed_flight_diversions.py sms-db
#   python -m scripts.seed_flight_diversions --tenants buddha-air,air-dynasty
#   SEED_DB=sms-db python scripts/seed_flight_diversions.py
# ============================================================================

import argparse
import os
import random
import sys
from datetime import datetime, timedelta, timezone

DB_ID = os.environ.get("SEED_DB", "sms-db")
os.environ["FIREBASE_DATABASE_ID"] = DB_ID

SEED_VERSION = "flight-diversion-demo-2"
SEED_CREATOR = "seed-flight-diversions"
HAZARD_SEQ_BASE = 8000

from seed.config import OPERATOR_PROFILES, FLIGHT_OPERATOR_TYPES


def _operator_code(iata: str, tenant_id: str) -> str:
    """Fall back to a readable code when the profile has no IATA (non-airline)."""
    if iata and iata.isalnum():
        return iata.upper()
    return "".join(part[0] for part in tenant_id.split("-") if part)[:2].upper()


OPERATORS = [
    {
        "id": p["id"],
        "iata": _operator_code(p.get("iata", ""), p["id"]),
        "kind": "Scheduled" if p["tenant_type"] == "airline" else "Helicopter",
        "count": p["flight_diversion_count"],
    }
    for p in OPERATOR_PROFILES
    if p["tenant_type"] in FLIGHT_OPERATOR_TYPES and p["flight_diversion_count"]
]

AIRPORTS = {
    "KTM": "Kathmandu",
    "PKR": "Pokhara",
    "BHR": "Bhairahawa",
    "BIR": "Biratnagar",
    "SIF": "Simikot",
    "JKR": "Jumla",
    "LUA": "Lukla",
    "DOP": "Dolpa",
    "JMO": "Jomsom",
    "SKH": "Surkhet",
}

REASONS = [
    ("Weather", ["Severe weather on approach", "Line squall with wind shear", "Heavy rain, visibility below minima", "Crosswind above operating limits"]),
    ("Technical", ["Engine parameter exceedance", "Cabin pressurization fault", "Wheel brake temperature high", "Hydraulic pressure fluctuation"]),
    ("Medical", ["Passenger medical emergency", "Crew incapacitation", "Passenger suspected cardiac event"]),
    ("Fuel", ["Low fuel during extended holding", "Fuel imbalance indication", "Long holding increased fuel burn"]),
    ("Security", ["Security threat reported on board", "Bomb threat received", "Unruly passenger incident"]),
    ("Operational", ["Destination runway closed", "Weight and balance issue", "Bird strike on departure"]),
    ("Airport Closure", ["Destination airport closed by NOTAM", "Runway lighting unserviceable", "Airport closure due to accident response"]),
    ("Air Traffic Control", ["ATC restriction at destination", "En-route slot shortage", "Holding due to ATC congestion"]),
]

REASON_TAXONOMY = {
    "Weather": "Environmental",
    "Technical": "Technical",
    "Medical": "Human Factors",
    "Fuel": "Technical",
    "Security": "Other",
    "Operational": "Other",
    "Airport Closure": "Other",
    "Air Traffic Control": "Other",
    "Other": "Other",
}

NAMES = ["Rajesh Shrestha", "Binay Gurung", "Anil Thapa", "Dipesh Karki", "Suman Rai", "Prakash Adhikari"]
REMARKS = ["Crew informed operations.", "Diversion decision documented in FDM review.",
           "Passengers deplaned at alternate.", "Follow-up maintenance action raised.", None]

random.seed(20240810)


# ============================================================================
# Doc builders
# ============================================================================

def make_diversion_doc(tid: str, op: dict, seq: int, year: int, when: datetime) -> dict:
    reason, detail_opts = random.choice(REASONS)
    details = random.choice(detail_opts)
    airports = random.sample(list(AIRPORTS.keys()), 3)
    sector_from, sector_to, diverted_to = airports[0], airports[1], airports[2]
    flight_number = f"{op['iata']} {random.randint(101, 999)}"
    reg = f"9N-{''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ', k=3))}"
    diversion_id = f"DIV-{year}-{seq:03d}"

    doc = {
        "tenant_id": tid,
        "diversion_id": diversion_id,
        "date": when,
        "flight_number": flight_number,
        "aircraft_registration": reg,
        "sector_from": sector_from,
        "sector_to": sector_to,
        "diverted_to": diverted_to,
        "reason": reason,
        "reason_details": details,
        "captain": f"Capt. {random.choice(NAMES)}",
        "description": (
            f"Aircraft {reg} operating {flight_number} from {AIRPORTS[sector_from]} "
            f"({sector_from}) to {AIRPORTS[sector_to]} ({sector_to}) was diverted to "
            f"{AIRPORTS[diverted_to]} ({diverted_to}) due to {reason}. {details}."
        ),
        "additional_fuel_cost": round(random.uniform(300, 4500), 2),
        "passenger_impact": random.randint(0, 12) if op["kind"] != "Helicopter" else random.randint(0, 5),
        "delay_minutes": random.choice([0, 0, 20, 35, 55, 90, 120, 180, 240]),
        "remarks": random.choice(REMARKS),
        "status": random.choices(["Pending", "Pending", "Reviewed", "Investigating", "Closed"], weights=[4, 3, 2, 2, 1])[0],
        "hazard_id": f"{tid}-HZ-{year}-{HAZARD_SEQ_BASE + seq:03d}",
        "created_by": SEED_CREATOR,
        "created_at": when,
        "updated_at": when,
        "seed_version": SEED_VERSION,
    }
    if op["kind"] != "Helicopter":
        doc["first_officer"] = f"FO {random.choice(NAMES)}"
        doc["air_hostess"] = f"AH {random.choice(NAMES)}"
    return {k: v for k, v in doc.items() if v is not None}


def make_hazard_doc(tid: str, op: dict, seq: int, year: int, when: datetime,
                    diversion_doc_id: str, diversion_doc: dict) -> dict:
    reason = diversion_doc["reason"]
    return {
        "hazard_id": diversion_doc["hazard_id"],
        "tenant_id": tid,
        "title": (
            f"Flight Diversion {diversion_doc['diversion_id']} - {diversion_doc['flight_number']} "
            f"{diversion_doc['sector_from']}-{diversion_doc['sector_to']} diverted to {diversion_doc['diverted_to']}"
        ),
        "description": diversion_doc["description"],
        "source": "Flight Diversion",
        "source_id": diversion_doc["diversion_id"],
        "source_url": f"/flight_diversions/detail.html?id={diversion_doc_id}",
        "occurrence_type": f"Flight Diversion - {reason}",
        "taxonomy": REASON_TAXONOMY.get(reason, "Other"),
        "priority": "M",
        "status": "Open",
        "created_by": SEED_CREATOR,
        "created_at": when,
        "updated_at": when,
        "seed_version": SEED_VERSION,
    }


# ============================================================================
# Firestore helpers
# ============================================================================

def clear_seeded(tid: str):
    ref = db.collection("tenants").document(tid)
    for sub in ("flight_diversions", "hazards"):
        snaps = ref.collection(sub).where("seed_version", "==", SEED_VERSION).get()
        for snap in snaps:
            snap.reference.delete()


def count_docs(tid: str, sub: str) -> int:
    return len(list(db.collection("tenants").document(tid).collection(sub).limit(5000).get()))


# ============================================================================
# Seed
# ============================================================================

def seed_diversions(tenant_ids=None) -> tuple:
    now = datetime.now(timezone.utc)
    d_total = h_total = 0
    ops = [o for o in OPERATORS if not tenant_ids or o["id"] in tenant_ids]
    for op in ops:
        tid = op["id"]
        clear_seeded(tid)
        ref = db.collection("tenants").document(tid)
        diversions = ref.collection("flight_diversions")
        hazards = ref.collection("hazards")

        times = sorted(
            now - timedelta(days=random.uniform(0, 180)) for _ in range(op["count"])
        )
        for seq, when in enumerate(times, start=1):
            year = when.year
            diversion_doc = make_diversion_doc(tid, op, seq, year, when)
            _, dref = diversions.add(diversion_doc)
            hazard_doc = make_hazard_doc(tid, op, seq, year, when, dref.id, diversion_doc)
            _, href = hazards.add(hazard_doc)
            dref.update({"hazard_link_url": f"/hazards/detail.html?id={href.id}"})
            d_total += 1
            h_total += 1

        print(f"  {tid}: seeded {count_docs(tid, 'flight_diversions')} diversions + "
              f"{sum(1 for h in hazards.where('source', '==', 'Flight Diversion').stream())} linked hazards.")
    return d_total, h_total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed demo flight diversions into operator tenants (beta by default).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("db", nargs="?", default=DB_ID,
                        help="Firestore database id (default: sms-db).")
    parser.add_argument("--tenants", default=None,
                        help="Comma-separated operator tenant ids to restrict seeding to "
                             "(default: all flight operators).")
    args = parser.parse_args()
    DB_ID = args.db
    os.environ["FIREBASE_DATABASE_ID"] = DB_ID

    random.seed(20240810)
    BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, BACKEND)
    os.chdir(BACKEND)

    from dotenv import load_dotenv
    load_dotenv(os.path.join(BACKEND, ".env"), override=False)

    from firebase_admin import credentials, firestore
    import firebase_admin

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

    tenant_filter = None
    if args.tenants:
        tenant_filter = [t.strip() for t in args.tenants.split(",") if t.strip()]
        unknown = [t for t in tenant_filter if t not in {o["id"] for o in OPERATORS}]
        if unknown:
            print(f"WARNING: requested tenants are not flight operators (skipped): {unknown}")

    print(f"Seeding flight diversions -> database={DB_ID}\n")
    d_total, h_total = seed_diversions(tenant_filter)
    print(f"\nDone. Seeded {d_total} flight diversions and {h_total} linked hazards across "
          f"{len(tenant_filter) if tenant_filter else len(OPERATORS)} operators.")
