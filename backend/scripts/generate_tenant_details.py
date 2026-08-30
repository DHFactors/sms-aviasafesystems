#!/usr/bin/env python3
"""
Generate the Tenant Details Audit document (docs/tenant_details.txt).

Combines three configuration sources with live Firestore metrics:

  1. backend/seed/config.py      — OPERATOR_PROFILES + simplified role plan
                                   (email / {CODE}-{ROLE}-2026 password per account)
  2. beta-testing-credentials.csv — credential reference rows (covers tenants that
                                   are documented but not seeded, e.g. Saurya Airlines)
  3. Firestore (sms-db)     — tenant docs, hazard / CAN / CAP counts and
                                   PSOE assessment statuses per tenant

Output: a plain-text audit document grouped by tenant with
  * Tenant ID & operator type
  * User accounts table (Role | Email | Password)
  * Operational metrics (Hazards | CANs | CAPs | PSOE completed/draft)

Usage (from repo root or backend/):
    python backend/scripts/generate_tenant_details.py
    python backend/scripts/generate_tenant_details.py --database sms-db
"""

import argparse
import csv
import os
import sys
from collections import OrderedDict
from datetime import datetime, timezone

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from app.core.config import settings
from app.firebase import initialize_firebase, get_db
from seed.config import (
    OPERATOR_PROFILES,
    CAAN_TENANT,
    DEMO_USERS,
    DEVELOPER_ACCOUNT,
    build_simplified_role_plan,
    CREDENTIAL_EMAIL_DOMAINS,
)

CSV_PATH = os.path.join(REPO_ROOT, "beta-testing-credentials.csv")
DEFAULT_OUTPUT = os.path.join(REPO_ROOT, "docs", "tenant_details.txt")

PSOE_COLLECTION = "psoe_assessments"
CAPS_SUBCOLLECTION = "caps"

# Friendly labels for the simplified role tokens.
ROLE_LABELS = {
    "ae": "Accountable Executive",
    "safety": "Safety Manager",
    "camo": "CAMO Manager",
    "145": "Part-145 Maintenance",
    "ops": "Operations Manager",
    "pilot": "Line Pilot",
}

# Documented-but-not-seeded tenants carried by the CSV (display name -> tenant id).
CSV_EXTRA_TENANT_IDS = {
    "Saurya Airlines": "saurya-airlines",
}


# ---------------------------------------------------------------------------
# Account gathering
# ---------------------------------------------------------------------------

def build_seed_accounts():
    """Return {tenant_id: [(role_label, email, password), ...]} from seed config."""
    accounts = {}
    for entry in build_simplified_role_plan():
        label = ROLE_LABELS.get(entry["token"], entry["full_name"])
        role = f"{label} [{entry['app_role']}]"
        accounts.setdefault(entry["op_id"], []).append(
            (role, entry["email"], entry["password"])
        )
    return accounts


def load_csv_rows():
    """Return raw CSV rows keyed by tenant display name (preserves order)."""
    grouped = OrderedDict()
    if not os.path.exists(CSV_PATH):
        print(f"WARNING: {CSV_PATH} not found — skipping CSV source")
        return grouped
    with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            grouped.setdefault((row.get("tenant") or "").strip(), []).append(row)
    return grouped


# ---------------------------------------------------------------------------
# Firestore metrics
# ---------------------------------------------------------------------------

def count_docs(coll_ref) -> int:
    return sum(1 for _ in coll_ref.stream())


def tenant_metrics(db, tenant_id: str) -> dict:
    """Live operational counts for one tenant."""
    metrics = {
        "tenant_doc": False,
        "hazards": 0,
        "cans": 0,
        "caps": 0,
        "psoe_completed": 0,
        "psoe_draft": 0,
        "psoe_other": 0,
    }

    tenant_doc = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id).get()
    metrics["tenant_doc"] = tenant_doc.exists
    if tenant_doc.exists:
        data = tenant_doc.to_dict() or {}
        metrics["firestore_type"] = data.get("type", "")

    tenant_ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id)
    metrics["hazards"] = count_docs(tenant_ref.collection("hazards"))

    can_docs = list(tenant_ref.collection("can_cap").stream())
    metrics["cans"] = len(can_docs)
    caps = 0
    for can in can_docs:
        caps += count_docs(can.reference.collection(CAPS_SUBCOLLECTION))
    metrics["caps"] = caps

    psoe_snaps = list(
        db.collection(PSOE_COLLECTION).where("tenant_id", "==", tenant_id).stream()
    )
    for snap in psoe_snaps:
        status = str((snap.to_dict() or {}).get("status", "")).lower()
        if status == "completed":
            metrics["psoe_completed"] += 1
        elif status == "draft":
            metrics["psoe_draft"] += 1
        else:
            metrics["psoe_other"] += 1

    return metrics


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

LINE = "=" * 100
THIN = "-" * 100


def render_tenant_block(index, display_name, tenant_id, op_type, accounts, m):
    lines = []
    lines.append(f"{index}. {display_name}  ({tenant_id})")
    lines.append(f"   Operator Type : {op_type}")
    lines.append(f"   Firestore Doc : {'present' if m['tenant_doc'] else 'NOT FOUND in database'}")
    lines.append("")
    lines.append("   User Accounts:")
    lines.append(f"     {'Role':<38} | {'Email':<38} | Password")
    lines.append(f"     {'-' * 38}-+-{'-' * 38}-{'-' * 22}")
    if accounts:
        for role, email, password in accounts:
            lines.append(f"     {role:<38} | {email:<38} | {password}")
    else:
        lines.append(f"     {'(no provisioned accounts)':<38} | {'-':<38} | -")
    lines.append("")
    lines.append("   Operational Metrics:")
    lines.append(
        f"     Hazards: {m['hazards']:<4} | CANs: {m['cans']:<4} | CAPs: {m['caps']:<4}"
        f" | PSOE: {m['psoe_completed']} completed, {m['psoe_draft']} draft"
        + (f", {m['psoe_other']} other" if m["psoe_other"] else "")
    )
    lines.append("")
    return lines


def main():
    parser = argparse.ArgumentParser(description="Generate the tenant details audit document.")
    parser.add_argument("--database", default="sms-db",
                        help="Firestore database id (default: sms-db)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help=f"Output path (default: {DEFAULT_OUTPUT})")
    args = parser.parse_args()

    # Target the requested Firestore database before the SDK initialises.
    settings.FIREBASE_DATABASE_ID = args.database
    initialize_firebase()
    db = get_db()

    seed_accounts = build_seed_accounts()
    csv_grouped = load_csv_rows()

    # Map CSV rows onto known tenants by email domain (display names in the CSV
    # drift from OPERATOR_PROFILES names, e.g. "Pokhara Airport (Aerodrome)").
    domain_to_tid = {d: tid for tid, d in CREDENTIAL_EMAIL_DOMAINS.items()}
    csv_extras = OrderedDict()
    for name, rows in csv_grouped.items():
        if not name or name == "CAAN":
            continue
        first_email = (rows[0].get("email") or "").lower()
        domain = first_email.split("@")[-1] if "@" in first_email else ""
        if domain not in domain_to_tid:
            csv_extras[name] = rows

    out = []
    out.append(LINE)
    out.append("AVIASAFE SMS — TENANT DETAILS AUDIT")
    out.append(LINE)
    out.append(f"Generated : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    out.append(f"Database  : {args.database}")
    out.append(f"Project   : {settings.FIREBASE_PROJECT_ID}")
    out.append("Sources   : backend/seed/config.py · docs/CREDENTIALS.md · beta-testing-credentials.csv")
    out.append("Password convention : {TENANT_CODE}-{ROLE}-2026")
    out.append("")

    index = 0

    # --- Operator tenants (seed config order) -----------------------------
    for profile in OPERATOR_PROFILES:
        index += 1
        tid = profile["id"]
        m = tenant_metrics(db, tid)
        op_type = m.get("firestore_type") or profile.get("tenant_type", profile.get("type", ""))
        out.extend(render_tenant_block(
            index, profile["name"], tid, op_type,
            seed_accounts.get(tid, []), m,
        ))

    # --- CSV-only documented tenants (e.g. Saurya Airlines) ---------------
    for name, rows in csv_extras.items():
        index += 1
        tid = CSV_EXTRA_TENANT_IDS.get(name, name.lower().replace(" ", "-"))
        m = tenant_metrics(db, tid)
        accounts = [
            (f"{r.get('role_label', '')} [{r.get('role', '')}]".strip(),
             r.get("email", ""), r.get("password", ""))
            for r in rows
        ]
        out.extend(render_tenant_block(
            index, f"{name} (documented — not in current seed set)", tid,
            "airline (credential reference only)", accounts, m,
        ))

    # --- CAAN state regulator --------------------------------------------
    index += 1
    caan_m = tenant_metrics(db, CAAN_TENANT["id"])
    caan_accounts = []
    for u in DEMO_USERS:
        caan_accounts.append((f"{u['role']} [CAAN_SMD]", u["email"], "CAAN-Safety-2026"))
    out.extend(render_tenant_block(
        index, CAAN_TENANT["name"], CAAN_TENANT["id"],
        caan_m.get("firestore_type") or CAAN_TENANT["type"],
        caan_accounts, caan_m,
    ))

    # --- Platform / developer account -------------------------------------
    dev = DEVELOPER_ACCOUNT
    out.append(THIN)
    out.append("Platform / Super-Admin (cross-tenant)")
    out.append(f"   {dev['role']:<38} | {dev['email']:<38} | (managed in Firebase Console; see CSV backup)")
    out.append("")

    # --- Summary -----------------------------------------------------------
    total_accounts = sum(len(v) for v in seed_accounts.values()) + len(caan_accounts)
    out.append(LINE)
    out.append("SUMMARY")
    out.append(LINE)
    out.append(f"Operator tenants (seeded)   : {len(OPERATOR_PROFILES)}")
    out.append(f"Documented extra tenants    : {len(csv_extras)}")
    out.append(f"State regulator tenants     : 1 (caan)")
    out.append(f"Role accounts               : {total_accounts} total "
               f"({total_accounts - len(caan_accounts)} operator + {len(caan_accounts)} CAAN SMD, + super-admin)")
    out.append(f"Output file                 : {args.output}")
    out.append(LINE)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip() + "\n")

    print(f"Wrote {args.output}")
    print(f"Tenants rendered: {index} (+ platform admin)")


if __name__ == "__main__":
    main()
