"""Reproduce the GET /api/v1/hazards and /api/v1/reports 500 by running the
exact backend service list logic + Pydantic response models against sms-db."""
import os
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore

# load backend/.env
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
app = firebase_admin.initialize_app(cred, name="repro")
db = firestore.client(app, database_id="sms-db")


def serialize(data):
    for key in ("created_at", "updated_at", "occurrence_date", "processed_at", "reviewed_at"):
        if key in data and hasattr(data[key], "isoformat"):
            data[key] = data[key].isoformat()
    return data


def list_hazards(tenant_id):
    docs = db.collection("tenants").document(tenant_id).collection("hazards").get()
    results = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        serialize(data)
        results.append(data)
    results.sort(key=lambda r: r.get("created_at", datetime.min), reverse=True)
    return results


def get_reports(tenant_id):
    docs = db.collection("tenants").document(tenant_id).collection("reports").get()
    results = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        serialize(data)
        results.append(data)
    results.sort(key=lambda r: r.get("created_at", datetime.min), reverse=True)
    return results


def check(name, items, fn):
    try:
        out = []
        for d in items:
            raw_item = fn(d)
            # infer model class by name
            model = HazardListItem if "hazard" in name else ReportListItem
            out.append(model(**raw_item))
        print(f"[OK]   {name}: {len(out)} items validated")
        return True
    except Exception as e:
        print(f"[FAIL] {name}: {type(e).__name__}: {e}")
        return False


from app.models.hazard import HazardListItem
from app.models.report import ReportListItem


def to_hazard_item(data):
    return {
        "id": data.get("id", ""),
        "hazard_id": data.get("hazard_id", ""),
        "title": data.get("title", ""),
        "source": data.get("source", ""),
        "taxonomy": data.get("taxonomy", ""),
        "priority": data.get("priority", ""),
        "risk_level": data.get("risk_level"),
        "status": data.get("status", "Open"),
        "assigned_to": data.get("assigned_to"),
        "department": data.get("department"),
        "created_at": data.get("created_at"),
        "severity": data.get("severity"),
        "probability": data.get("probability"),
        "risk_index": data.get("risk_index"),
    }


def to_report_item(data):
    return {
        "id": data.get("id", ""),
        "tenant_id": data.get("tenant_id", ""),
        "report_type": data.get("report_type", "voluntary"),
        "status": data.get("status", "NEW"),
        "ai_status": data.get("ai_status", "PENDING"),
        "location": data.get("location", ""),
        "occurrence_date": data.get("occurrence_date"),
        "created_by": data.get("created_by", ""),
        "created_at": data.get("created_at"),
        "is_anonymous": data.get("is_anonymous", False),
        "occurrence_type": data.get("occurrence_type"),
        "severity": data.get("severity"),
        "risk_score": data.get("risk_score"),
        "risk_level": data.get("risk_level"),
        "severity_level": data.get("severity_level"),
        "probability_level": data.get("probability_level"),
        "occurrence_category": data.get("occurrence_category"),
        "aircraft_make": data.get("aircraft_make"),
        "aircraft_model": data.get("aircraft_model"),
        "operator": data.get("operator"),
        "flight_phase": data.get("flight_phase"),
    }


for tid in ("buddha-air", "sita-air"):
    hazards = list_hazards(tid)
    reports = get_reports(tid)
    print(f"\n=== {tid} ===  hazards={len(hazards)} reports={len(reports)}")
    check(f"hazards list [{tid}]", hazards, to_hazard_item)
    check(f"reports list [{tid}]", reports, to_report_item)

    # Show raw distinct values of enum fields to spot bad values
    for d in hazards[:5]:
        print("  hazard raw:", {k: d.get(k) for k in ("id", "source", "taxonomy", "priority", "status", "hazard_id")})
    for d in reports[:5]:
        print("  report raw:", {k: d.get(k) for k in ("id", "report_type", "status", "ai_status", "location", "occurrence_date", "created_at")})

firebase_admin.delete_app(app)
