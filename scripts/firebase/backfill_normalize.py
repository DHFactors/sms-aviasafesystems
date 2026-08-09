"""Backfill sms-db-beta hazard/report documents so they conform to the
Pydantic response models that currently return 500.

Root cause (verified via repro-500.py): seed scripts stored
  - hazard taxonomy as ICAO occurrence codes ('BIRD', 'CFIT', 'MAC', ...)
  - hazard source as 'Manual' (not in HazardSource enum)
  - hazard priority as '' / missing (required H|M|L)
  - report severity as int (model expects Optional[str])

This script normalizes existing documents in place.
"""
import os
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore

env = {}
for line in Path(Path(__file__).resolve().parents[2] / "backend" / ".env").read_text(encoding="utf-8").splitlines():
    m = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.*)$", line)
    if m and not line.strip().startswith("#"):
        v = m.group(2)
        if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
            v = v[1:-1]
        env[m[1]] = v

cred = credentials.Certificate({
    "type": "service_account",
    "project_id": env["FIREBASE_PROJECT_ID"],
    "private_key": env["FIREBASE_PRIVATE_KEY"].replace("\\n", "\n"),
    "client_email": env["FIREBASE_CLIENT_EMAIL"],
    "token_uri": env.get("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
})
app = firebase_admin.initialize_app(cred, name="backfill_norm")
db = firestore.client(app, database_id="sms-db-beta")

VALID_SOURCES = {
    "VSR", "MOR", "Quality Audit", "Safety Inspection", "Flight Diversion",
    "CAAN Audit", "Internal Audit", "Safety Survey", "IOR", "MOC",
    "SRM Request", "Incident",
}
VALID_TAXONOMIES = {
    "Organizational-Facilities",
    "Organizational-Documentation, Processes and Procedures",
    "Technical", "Wildlife", "Human Factors", "Environmental", "Other",
}

# Mirrors app/routes/reports.py:_determine_hazard_taxonomy
ICAO_TO_TAXONOMY = {
    "BIRD": "Wildlife",
    "FIRE": "Technical",
    "ENG": "Technical",
    "SYS": "Technical",
    "MAC": "Technical",
    "CFIT": "Organizational-Facilities",
    "GCOL": "Organizational-Facilities",
    "RI": "Organizational-Facilities",
    "RE": "Organizational-Facilities",
    "LOCI": "Organizational-Facilities",
    "CABIN": "Human Factors",
    "PRO": "Organizational-Documentation, Processes and Procedures",
    "ARC": "Organizational-Documentation, Processes and Procedures",
    "WX": "Environmental",
}
FALLBACK_SOURCE = "Internal Audit"
FALLBACK_PRIORITY = "M"


def normalize_taxonomy(value, occurrence_category=None):
    if value in VALID_TAXONOMIES:
        return value, False
    candidate = occurrence_category or value
    mapped = ICAO_TO_TAXONOMY.get((candidate or "").upper())
    if mapped:
        return mapped, True
    return "Other", True


def normalize_source(value):
    if not value:
        return FALLBACK_SOURCE, True
    if value in VALID_SOURCES:
        return value, False
    return FALLBACK_SOURCE, True


def normalize_priority(value):
    if value in ("H", "M", "L"):
        return value, False
    return FALLBACK_PRIORITY, True


def fix_hazards(tenant_id):
    col = db.collection("tenants").document(tenant_id).collection("hazards")
    fixed = 0
    for doc in col.stream():
        data = doc.to_dict()
        updates = {}
        tax, tax_changed = normalize_taxonomy(data.get("taxonomy"), data.get("occurrence_category"))
        if tax_changed:
            updates["taxonomy"] = tax
        src, src_changed = normalize_source(data.get("source"))
        if src_changed:
            updates["source"] = src
        pri, pri_changed = normalize_priority(data.get("priority"))
        if pri_changed:
            updates["priority"] = pri
        if updates:
            doc.reference.update(updates)
            fixed += 1
            print(f"  [hazard] {doc.id}: {updates}")
    return fixed


def fix_reports(tenant_id):
    col = db.collection("tenants").document(tenant_id).collection("reports")
    fixed = 0
    for doc in col.stream():
        data = doc.to_dict()
        sev = data.get("severity")
        if isinstance(sev, int):
            doc.reference.update({"severity": str(sev)})
            fixed += 1
            print(f"  [report] {doc.id}: severity {sev} -> '{sev}'")
    return fixed


tenant_ids = [t.id for t in db.collection("tenants").stream()]
for tenant_id in tenant_ids:
    print(f"=== {tenant_id} ===")
    try:
        h = fix_hazards(tenant_id)
        r = fix_reports(tenant_id)
        print(f"  fixed hazards={h} reports={r}")
    except Exception as e:
        print(f"  ERROR: {e}")

firebase_admin.delete_app(app)
print("\nDone.")
