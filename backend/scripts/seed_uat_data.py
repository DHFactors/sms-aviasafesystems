#!/usr/bin/env python3
"""
UAT Seed Data Utility — writes deterministic test fixtures into Firestore.

Targets ONLY the configured FIREBASE_DATABASE_ID (defaults to sms-db-beta).
Creates:
  - 2 tenants (fishtail-air, nepal-wings) with AOC, tier, safety manager
  - 5 hazards per tenant spanning matrix cells 5A, 4C, 3D, 2E, 1E
  - Voluntary + mandatory occurrences for operational reporting rates
  - Open / in-progress / overdue CAPA records for fishtail-air
  - Baseline SPIs with current values exceeding 1-Sigma thresholds
  - Regulator entity regulators/caan with distribution recipients

Idempotent: overwrites documents with same seed_version tag.
Usage:
  python scripts/seed_uat_data.py              # uses FIREBASE_DATABASE_ID env
  python scripts/seed_uat_data.py sms-db-beta  # explicit database ID
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"), override=False)

DB_ID = os.environ.get("FIREBASE_DATABASE_ID", sys.argv[1] if len(sys.argv) > 1 else "sms-db-beta")

# ── Firebase init ─────────────────────────────────────────────────────────────
import firebase_admin
from firebase_admin import credentials, firestore as fs

cred_dict = {
    "type": "service_account",
    "project_id": os.environ.get("FIREBASE_PROJECT_ID"),
    "private_key": os.environ.get("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n"),
    "client_email": os.environ.get("FIREBASE_CLIENT_EMAIL"),
    "token_uri": os.environ.get("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
}

if not firebase_admin._apps:
    creds = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(creds)

db = fs.client(app=firebase_admin.get_app(), database_id=DB_ID)

# Patch app.firebase so internal helpers can resolve db
import app.firebase as fb
fb._db = db
fb._firebase_app = firebase_admin.get_app()

SEED_VERSION = "uat-v1"
NOW = datetime.now(timezone.utc)

print(f"[seed_uat_data] Target database: {DB_ID}")
print(f"[seed_uat_data] Seed version:    {SEED_VERSION}")
print(f"[seed_uat_data] Timestamp:       {NOW.isoformat()}")


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1: Tenants
# ═══════════════════════════════════════════════════════════════════════════════

TENANTS: List[Dict[str, Any]] = [
    {
        "id": "fishtail-air",
        "data": {
            "tenant_id": "fishtail-air",
            "name": "Fishtail Air",
            "operator_name": "Fishtail Air",
            "organization_type": "AIRLINE",
            "aoc_number": "AOC-042-NEP",
            "sms_tier": "Enterprise",
            "status": "active",
            "country": "NP",
            "country_name": "Nepal",
            "regulator_id": "caan",
            "flight_hours": 8420.5,
            "total_flights": 2340,
            "departments": [
                "Flight Operations",
                "Maintenance & Engineering",
                "Ground Handling",
                "Safety & Quality",
                "Cabin Crew",
            ],
            "safety_manager": {
                "name": "Rajesh Gurung",
                "email": "safety@fishtail-air.com.np",
                "phone": "+977-1-4001001",
            },
            "sag_members": [
                {"name": "Sita Sharma", "email": "sita.sharma@fishtail-air.com.np", "role": "Safety Officer"},
                {"name": "Binod Thapa", "email": "binod.thapa@fishtail-air.com.np", "role": "Flight Ops Manager"},
            ],
            "created_at": NOW - timedelta(days=365),
            "updated_at": NOW,
            "seed_version": SEED_VERSION,
        },
    },
    {
        "id": "nepal-wings",
        "data": {
            "tenant_id": "nepal-wings",
            "name": "Nepal Wings Air Services",
            "operator_name": "Nepal Wings",
            "organization_type": "AIRLINE",
            "aoc_number": "AOC-088-NEP",
            "sms_tier": "Standard",
            "status": "active",
            "country": "NP",
            "country_name": "Nepal",
            "regulator_id": "caan",
            "flight_hours": 3150.0,
            "total_flights": 890,
            "departments": [
                "Flight Operations",
                "Maintenance",
                "Ground Handling",
            ],
            "safety_manager": {
                "name": "Anita Rai",
                "email": "safety@nepal-wings.com.np",
                "phone": "+977-1-4002002",
            },
            "sag_members": [
                {"name": "Deepak Magar", "email": "deepak@nepal-wings.com.np", "role": "Safety Officer"},
            ],
            "created_at": NOW - timedelta(days=200),
            "updated_at": NOW,
            "seed_version": SEED_VERSION,
        },
    },
]


def seed_tenants():
    print("\n── Seeding Tenants ──")
    for t in TENANTS:
        ref = db.collection("tenants").document(t["id"])
        ref.set(t["data"])
        print(f"  ✓ {t['id']}: AOC={t['data']['aoc_number']}, Tier={t['data']['sms_tier']}")


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2: Hazards (5x5 matrix cells: 5A, 4C, 3D, 2E, 1E)
# ═══════════════════════════════════════════════════════════════════════════════

HAZARD_TEMPLATES = [
    {"sev": 5, "prob": 5, "cell": "5A", "cat": "LOCI", "title": "Loss of control in icing conditions", "status": "Open", "risk_level": "Very High"},
    {"sev": 4, "prob": 3, "cell": "4C", "cat": "ENG", "title": "Uncontained engine failure during takeoff", "status": "Open", "risk_level": "High"},
    {"sev": 3, "prob": 2, "cell": "3D", "cat": "RE", "title": "Runway excursion on wet surface", "status": "Open", "risk_level": "Medium"},
    {"sev": 2, "prob": 1, "cell": "2E", "cat": "BIRD", "title": "Bird strike during approach", "status": "Closed", "risk_level": "Low"},
    {"sev": 1, "prob": 1, "cell": "1E", "cat": "OTHER", "minor": "Minor cabin service irregularity", "status": "Closed", "risk_level": "Low"},
]


def _hazard_doc(tenant_id: str, idx: int, t: Dict[str, Any]) -> Dict[str, Any]:
    created = NOW - timedelta(days=30 * (5 - idx))
    return {
        "tenant_id": tenant_id,
        "hazard_id": f"{tenant_id}-HZ-2026-{idx:03d}",
        "title": t["title"],
        "description": f"UAT seed hazard: {t['title']}",
        "source": "VSR",
        "occurrence_category": t["cat"],
        "severity": t["sev"],
        "probability": t["prob"],
        "risk_index": f"{t['sev']}{chr(64 + t['prob'])}",
        "risk_level": t["risk_level"],
        "status": t["status"],
        "created_by": "seed-uat",
        "created_at": created,
        "updated_at": created,
        "seed_version": SEED_VERSION,
    }


def seed_hazards():
    print("\n── Seeding Hazards ──")
    for tenant_id in ["fishtail-air", "nepal-wings"]:
        batch = db.batch()
        for i, t in enumerate(HAZARD_TEMPLATES, start=1):
            ref = db.collection("tenants").document(tenant_id).collection("hazards").document(f"hz-{i:03d}")
            batch.set(ref, _hazard_doc(tenant_id, i, t))
        batch.commit()
        print(f"  ✓ {tenant_id}: 5 hazards seeded (5A, 4C, 3D, 2E, 1E)")


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3: Occurrences (voluntary + mandatory)
# ═══════════════════════════════════════════════════════════════════════════════

REPORTS_DATA = [
    {"type": "voluntary", "status": "NEW",      "sev": "Low",    "cat": "OTHER", "title": "Near-miss on apron"},
    {"type": "mandatory", "status": "COMPLETED", "sev": "High",   "cat": "ENG",   "title": "In-flight engine shutdown"},
    {"type": "voluntary", "status": "NEW",      "sev": "Medium", "cat": "BIRD",  "title": "Bird strike during climb"},
    {"type": "mandatory", "status": "INVESTIGATING", "sev": "High", "cat": "LOCI", "title": "Wing stall event"},
    {"type": "voluntary", "status": "CLOSED",   "sev": "Low",    "cat": "CABIN", "title": "Turbulence injury — cabin"},
]


def _report_doc(tenant_id: str, idx: int, r: Dict[str, Any]) -> Dict[str, Any]:
    created = NOW - timedelta(days=14 * idx)
    return {
        "tenant_id": tenant_id,
        "report_id": f"{tenant_id}-RPT-2026-{idx:03d}",
        "report_type": r["type"],
        "status": r["status"],
        "ai_status": "COMPLETED",
        "narrative": r["title"],
        "severity": r["sev"],
        "occurrence_category": r["cat"],
        "occurrence_type": r["title"],
        "location": "KTM",
        "is_anonymous": r["type"] == "voluntary",
        "created_by": "seed-uat",
        "created_at": created,
        "updated_at": created,
        "seed_version": SEED_VERSION,
    }


def seed_reports():
    print("\n── Seeding Reports ──")
    for tenant_id in ["fishtail-air", "nepal-wings"]:
        batch = db.batch()
        for i, r in enumerate(REPORTS_DATA, start=1):
            ref = db.collection("tenants").document(tenant_id).collection("reports").document(f"rpt-{i:03d}")
            batch.set(ref, _report_doc(tenant_id, i, r))
        batch.commit()
        print(f"  ✓ {tenant_id}: 5 reports seeded (3 voluntary, 2 mandatory)")


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4: CAPAs (open / in-progress / overdue — fishtail-air only)
# ═══════════════════════════════════════════════════════════════════════════════

CAPAS_DATA = [
    {
        "can_number": "CAPA-2026-001",
        "description": "Replace worn main landing gear brake assemblies",
        "finding": "Brake wear exceeded limits on MSN-042",
        "responsible": "Head of Maintenance",
        "assigned_to": "Engineering Dept",
        "status": "OPEN",
        "priority": "HIGH",
        "due_date": "2026-09-30",
        "created_at": NOW - timedelta(days=45),
    },
    {
        "can_number": "CAPA-2026-002",
        "description": "Implement crew resource management refresher training",
        "finding": "CRM non-compliance flagged in Q2 audit",
        "responsible": "Accountable Manager",
        "assigned_to": "Flight Operations",
        "status": "IN_PROGRESS",
        "priority": "MEDIUM",
        "due_date": "2026-12-31",
        "created_at": NOW - timedelta(days=30),
    },
    {
        "can_number": "CAPA-2026-003",
        "description": "Update SMS manual Section 4.2 — Risk Assessment Procedures",
        "finding": "Manual revision overdue by 60 days",
        "responsible": "Safety Manager",
        "assigned_to": "Safety & Quality",
        "status": "OPEN",
        "priority": "CRITICAL",
        "due_date": "2026-06-30",  # Overdue
        "created_at": NOW - timedelta(days=90),
    },
    {
        "can_number": "CAPA-2026-004",
        "description": "Install cockpit voice recorder memory protector upgrade",
        "finding": "AD compliance required by CAAN directive CA-2026-012",
        "responsible": "Head of Maintenance",
        "assigned_to": "Engineering Dept",
        "status": "OPEN",
        "priority": "HIGH",
        "due_date": "2026-10-31",
        "created_at": NOW - timedelta(days=20),
    },
    {
        "can_number": "CAPA-2026-005",
        "description": "Revise emergency evacuation procedure SOP",
        "finding": "CRM finding: crew coordination during evacuation drill",
        "responsible": "Safety Manager",
        "assigned_to": "Safety & Quality",
        "status": "IN_PROGRESS",
        "priority": "MEDIUM",
        "due_date": "2026-11-15",
        "created_at": NOW - timedelta(days=25),
    },
]


def seed_capas():
    print("\n── Seeding CAPAs (fishtail-air) ──")
    batch = db.batch()
    for i, c in enumerate(CAPAS_DATA, start=1):
        ref = db.collection("tenants").document("fishtail-air").collection("cans").document(f"capa-{i:03d}")
        doc = dict(c)
        doc["updated_at"] = doc["created_at"]
        doc["seed_version"] = SEED_VERSION
        batch.set(ref, doc)
    batch.commit()
    print(f"  ✓ fishtail-air: {len(CAPAS_DATA)} CAPAs (2 open, 2 in-progress, 1 overdue)")


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5: SPIs (baseline operational indicators — fishtail-air)
# ═══════════════════════════════════════════════════════════════════════════════

SPI_DATA = [
    {
        "spi_id": "SPI-001",
        "name": "Flight Hours per Safety Report",
        "domain": "OPS",
        "description": "Average flight hours between submitted safety reports",
        "current_value": 350.0,
        "target_value": 200.0,
        "alert_threshold": 500.0,
        "warning_threshold": 400.0,
        "unit": "hrs/report",
        "measurement_period": "monthly",
        "is_on_target": True,
        "trend": "stable",
    },
    {
        "spi_id": "SPI-002",
        "name": "Aircraft Technical Dispatch Reliability",
        "domain": "MAINT",
        "description": "Percentage of flights departing within 15 min of schedule (tech reasons)",
        "current_value": 97.8,
        "target_value": 98.0,
        "alert_threshold": 95.0,
        "warning_threshold": 96.5,
        "unit": "%",
        "measurement_period": "monthly",
        "is_on_target": False,
        "trend": "declining",
    },
    {
        "spi_id": "SPI-003",
        "name": "Runway Excursion Risk Index",
        "domain": "OPS",
        "description": "Composite risk score for runway excursion per 1000 landings",
        "current_value": 0.42,
        "target_value": 0.50,
        "alert_threshold": 0.80,
        "warning_threshold": 0.60,
        "unit": "index",
        "measurement_period": "monthly",
        "is_on_target": True,
        "trend": "improving",
    },
    {
        "spi_id": "SPI-004",
        "name": "Safety Culture Survey Score",
        "domain": "SAFETY_PROMOTION",
        "description": "Composite safety culture index from anonymous employee surveys",
        "current_value": 3.8,
        "target_value": 4.0,
        "alert_threshold": 2.5,
        "warning_threshold": 3.0,
        "unit": "score/5",
        "measurement_period": "quarterly",
        "is_on_target": False,
        "trend": "stable",
    },
    {
        "spi_id": "SPI-005",
        "name": "Unstabilised Approach Rate",
        "domain": "FLIGHT_OPS",
        "description": "Percentage of approaches classified as unstabilised below 1000ft",
        "current_value": 2.1,
        "target_value": 1.5,
        "alert_threshold": 4.0,
        "warning_threshold": 3.0,
        "unit": "%",
        "measurement_period": "monthly",
        "is_on_target": False,
        "trend": "declining",
    },
]


def seed_spis():
    print("\n── Seeding SPIs (fishtail-air) ──")
    batch = db.batch()
    for i, s in enumerate(SPI_DATA, start=1):
        ref = db.collection("tenants").document("fishtail-air").collection("spis").document(f"spi-{i:03d}")
        doc = dict(s)
        doc["tenant_id"] = "fishtail-air"
        doc["created_at"] = NOW - timedelta(days=60)
        doc["updated_at"] = NOW
        doc["seed_version"] = SEED_VERSION
        batch.set(ref, doc)
    batch.commit()
    print(f"  ✓ fishtail-air: {len(SPI_DATA)} SPIs seeded (2 on-target, 3 off-target)")


# ═══════════════════════════════════════════════════════════════════════════════
# Section 6: Regulator Entity (regulators/caan)
# ═══════════════════════════════════════════════════════════════════════════════

REGULATOR_DATA = {
    "regulator_id": "caan",
    "name": "Civil Aviation Authority of Nepal",
    "abbreviation": "CAAN",
    "country": "NP",
    "country_name": "Nepal",
    "type": "STATE_AUTHORITY",
    "status": "active",
    "notification_emails": [
        "caan.ssp@caanepal.gov.np",
        "caan.safety@caanepal.gov.np",
    ],
    "oversight_tenants": ["fishtail-air", "nepal-wings", "buddha-air", "air-dynasty"],
    "ssp_targets": {
        "total_hazards_intolerable": 5,
        "max_unresolved_capas": 10,
        "min_safety_culture_index": 3.5,
    },
    "created_at": NOW - timedelta(days=730),
    "updated_at": NOW,
    "seed_version": SEED_VERSION,
}


def seed_regulator():
    print("\n── Seeding Regulator ──")
    db.collection("regulators").document("caan").set(REGULATOR_DATA)
    print("  ✓ regulators/caan: CAAN Nepal with 4 oversight tenants")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  aviaSDCPS UAT Seed Data Utility")
    print("=" * 70)
    seed_tenants()
    seed_hazards()
    seed_reports()
    seed_capas()
    seed_spis()
    seed_regulator()
    print("\n" + "=" * 70)
    print("  Seed complete. Summary:")
    print(f"    Tenants:   2 (fishtail-air, nepal-wings)")
    print(f"    Hazards:   10 (5 per tenant)")
    print(f"    Reports:   10 (5 per tenant)")
    print(f"    CAPAs:     5 (fishtail-air)")
    print(f"    SPIs:      5 (fishtail-air)")
    print(f"    Regulator: 1 (caan)")
    print("=" * 70)


if __name__ == "__main__":
    main()
