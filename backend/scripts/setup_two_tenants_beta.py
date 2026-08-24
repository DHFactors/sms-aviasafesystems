#!/usr/bin/env python3
"""
Beta-only Firestore reset & seed — sms-db-beta only.

Safety:
- Hard-fails for any database_id != "sms-db-beta"
- Dry-run by default; destructive requires --execute --confirm-beta-purge
- Never executes on import (guard __name__ == "__main__")
- Targets only sms-db-beta via firestore.client(database_id="sms-db-beta")
- Preserves tenant metadata, taxonomy, and protected templates
- Writes local log + JSON summary (not to Firestore if audit_logs purged)

Paths verified from current repository (do not use guessed top-level cans/caps):
- tenants/{tenant_id}/reports            (FIREBASE_COLLECTION_REPORTS)
- tenants/{tenant_id}/hazards            (HAZARD_COLLECTION = hazards)
- tenants/{tenant_id}/can_cap            (CAN_COLLECTION = can_cap)
- tenants/{tenant_id}/can_cap/{can_id}/caps (CAP_SUBCOLLECTION = caps)
- tenants/{tenant_id}/flight_diversions
- tenants/{tenant_id}/surveys / responses
- tenants/{tenant_id}/verification
- tenants/{tenant_id}/metadata/* (PRESERVED)
Top-level audit_logs, feedback, psoe_assessments, caan_reports are NOT purged here
(tenant subcollections only) to avoid cross-tenant impact in shared project.

Auth: Firebase Auth is project-wide (aerosafety-sms-prod for both sms-db and sms-db-beta).
If beta and prod share the same project, Auth custom-claims provisioning is BLOCKED
and must be approved via dedicated beta project.

Frontend mapping (Step 5) is handled via public/js/firebase.js APP_CONFIG (IS_BETA_ENV).
"""

import argparse
import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

# Ensure backend is on path when run as `python backend/scripts/setup_two_tenants_beta.py`
ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

ALLOWED_DATABASE_ID = "sms-db-beta"
DEMO_TENANTS = {
    "fishtail-air": {
        "name": "Fishtail Air",
        "organization_type": "AIRLINE",
        "departments": [
            "Flight Operations",
            "Ground Handling",
            "Safety & Quality",
            "Maintenance",
        ],
    },
    "vnkt-airport": {
        "name": "Tribhuvan International Airport (VNKT)",
        "organization_type": "AERODROME",
        "departments": [
            "Airside Operations",
            "Wildlife & Bird Hazard Management",
            "Rescue & Fire Fighting (ARFF)",
            "Apron Control",
            "Air Traffic Coordination",
        ],
    },
}

# Canonical department labels from tenant_registration.DEPARTMENT_LABELS
# Verify task departments against these canonical values (display labels)
CANONICAL_LABELS = {
    "safety": "Safety",
    "flight_ops": "Flight Operations",
    "camo": "CAMO",
    "maintenance_145": "Part-145",
    "qa": "QA",
    "airside_ops": "Airside Operations",
    "arff": "ARFF (Rescue & Firefighting)",
    "ground_ops": "Ground Operations",
}
CANONICAL_DISPLAY_VALUES = set(CANONICAL_LABELS.values())

# Tenant subcollections to purge (verified from repo; do NOT guess top-level cans/caps)
TENANT_SUBCOLLECTIONS_TO_PURGE = [
    "reports",
    "hazards",
    "can_cap",  # includes caps subcollection recursively
    "flight_diversions",
    "surveys",
    "responses",
    "verification",
    # "audit_logs" is top-level in this repo (app/services/audit_service.py:51 db.collection("audit_logs")),
    # so tenant subcollection audit_logs is checked for existence but not required.
    "audit_logs",
    "notifications",  # will be checked for existence before purge (no evidence in repo, so skipped if missing)
]

# Protected paths that must NEVER be deleted
PROTECTED_TENANT_PATHS = [
    "metadata",  # tenants/{tid}/metadata/* (profile, info, taxonomy blueprints)
]

LOG_DIR = BACKEND / "scripts" / "logs"


__VERSION__ = "1.0.0-beta-minimal"

def _get_commit():
    try:
        import subprocess
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, cwd=str(ROOT)).strip()
    except Exception:
        return "unknown"

def parse_args():
    p = argparse.ArgumentParser(description="Beta-only Firestore reset & seed for sms-db-beta")
    p.add_argument("--database-id", required=True, help="Must be exactly sms-db-beta")
    p.add_argument("--dry-run", action="store_true", help="Explicit dry-run (default, no writes)")
    p.add_argument("--execute", action="store_true", help="Execute destructive purge/seed (requires --confirm-beta-purge)")
    p.add_argument("--confirm-beta-purge", action="store_true", help="Explicit confirmation for beta purge")
    p.add_argument("--skip-seed", action="store_true", help="Purge only, skip seeding")
    p.add_argument("--skip-purge", action="store_true", help="Seed only, skip purge (dry-run still shows counts)")
    return p.parse_args()


def validate_database_id(db_id: str):
    if db_id != ALLOWED_DATABASE_ID:
        print(f"[FATAL] Refusing to run: --database-id must be exactly '{ALLOWED_DATABASE_ID}' (got '{db_id}')", file=sys.stderr)
        print(f"[FATAL] This script NEVER connects to or modifies sms-db (production).", file=sys.stderr)
        sys.exit(2)


def init_firestore_beta():
    """Initialize Firebase Admin explicitly with database_id='sms-db-beta'."""
    # Import here to avoid import-time side effects
    from app.core.config import settings  # type: ignore
    import firebase_admin
    from firebase_admin import credentials, firestore

    project_id = settings.FIREBASE_PROJECT_ID or os.getenv("FIREBASE_PROJECT_ID")
    private_key = settings.FIREBASE_PRIVATE_KEY or os.getenv("FIREBASE_PRIVATE_KEY")
    client_email = settings.FIREBASE_CLIENT_EMAIL or os.getenv("FIREBASE_CLIENT_EMAIL")
    token_uri = settings.FIREBASE_TOKEN_URI

    if not all([project_id, private_key, client_email]):
        print("[FATAL] Missing Firebase credentials (FIREBASE_PROJECT_ID/PRIVATE_KEY/CLIENT_EMAIL) in environment or backend/.env", file=sys.stderr)
        sys.exit(2)

    # Hard check: database_id must be beta
    database_id = ALLOWED_DATABASE_ID

    print(f"[INFO] Firebase project ID: {project_id}")
    print(f"[INFO] Firebase database ID: {database_id}")
    print(f"[INFO] Initializing Firestore with database_id='{database_id}'")

    # Reuse or init app
    if not firebase_admin._apps:
        cred_dict = {
            "type": "service_account",
            "project_id": project_id,
            "private_key": private_key.replace("\\n", "\n"),
            "client_email": client_email,
            "token_uri": token_uri,
        }
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)

    db = firestore.client(database_id=database_id)
    return db, project_id, database_id


def verify_departments():
    """Check task departments against canonical display values; warn if mismatched."""
    print("[VERIFY] Canonical department display values:", sorted(CANONICAL_DISPLAY_VALUES))
    for tid, info in DEMO_TENANTS.items():
        for dept in info["departments"]:
            if dept not in CANONICAL_DISPLAY_VALUES:
                # Allow & variations: e.g., Safety & Quality vs Safety
                print(f"[WARN] Tenant {tid} department '{dept}' not in canonical {CANONICAL_DISPLAY_VALUES} — will be stored as free-text (hazard.department is Optional[str] without enum, so allowed).")
            else:
                print(f"[VERIFY] Tenant {tid} department '{dept}' matches canonical.")


def discover_counts(db) -> Dict[str, Any]:
    """Dry-run: count documents in each tenant subcollection for the two demo tenants."""
    counts = {}
    for tid in DEMO_TENANTS:
        counts[tid] = {}
        for coll in TENANT_SUBCOLLECTIONS_TO_PURGE:
            try:
                # Check if subcollection exists by attempting to list (limit 1)
                ref = db.collection("tenants").document(tid).collection(coll)
                # For can_cap, also count caps subcollections separately later
                docs = list(ref.limit(500).stream())
                counts[tid][coll] = len(docs)
                if coll == "can_cap" and docs:
                    cap_total = 0
                    for d in docs:
                        try:
                            caps = list(d.reference.collection("caps").limit(500).stream())
                            cap_total += len(caps)
                        except Exception:
                            pass
                    counts[tid][f"{coll}/caps"] = cap_total
            except Exception as e:
                counts[tid][coll] = f"error: {e}"
        # Protected metadata check
        try:
            meta = db.collection("tenants").document(tid).collection("metadata").limit(5).stream()
            meta_list = list(meta)
            counts[tid]["metadata (protected, not purged)"] = len(meta_list)
        except Exception:
            pass
    return counts


def purge_tenant_data(db, dry_run: bool, logger) -> Dict[str, Any]:
    """Purge only confirmed demo data paths for the two tenants, recursively removing caps."""
    summary = {}
    for tid in DEMO_TENANTS:
        summary[tid] = {}
        for coll in TENANT_SUBCOLLECTIONS_TO_PURGE:
            # Skip protected
            if coll in PROTECTED_TENANT_PATHS:
                logger.info(f"[SKIP] Protected {tid}/{coll} not purged")
                summary[tid][coll] = "protected - skipped"
                continue
            try:
                ref = db.collection("tenants").document(tid).collection(coll)
                # Check existence quickly
                try:
                    test = list(ref.limit(1).stream())
                    if not test:
                        summary[tid][coll] = 0
                        continue
                except Exception:
                    summary[tid][coll] = 0
                    continue

                if dry_run:
                    docs = list(ref.limit(500).stream())
                    summary[tid][coll] = f"dry-run would delete {len(docs)}"
                    if coll == "can_cap":
                        cap_total = 0
                        for d in docs:
                            try:
                                caps = list(d.reference.collection("caps").limit(500).stream())
                                cap_total += len(caps)
                            except Exception:
                                pass
                        summary[tid][f"{coll}/caps"] = f"dry-run would delete {cap_total} caps"
                    continue

                # Execute: recursive delete for can_cap caps first
                deleted = 0
                cap_deleted = 0
                docs = list(ref.stream())
                for doc in docs:
                    if coll == "can_cap":
                        try:
                            caps = list(doc.reference.collection("caps").stream())
                            for cap in caps:
                                try:
                                    cap.reference.delete()
                                    cap_deleted += 1
                                except Exception as e:
                                    logger.warning(f"Failed to delete cap {cap.id}: {e}")
                        except Exception as e:
                            logger.warning(f"Failed to list caps for {doc.id}: {e}")
                    try:
                        doc.reference.delete()
                        deleted += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete {coll}/{doc.id}: {e}")
                summary[tid][coll] = deleted
                if coll == "can_cap":
                    summary[tid][f"{coll}/caps"] = cap_deleted
                    logger.info(f"[PURGE] {tid}/{coll}: {deleted} docs, {cap_deleted} caps")
                else:
                    logger.info(f"[PURGE] {tid}/{coll}: {deleted} docs")
            except Exception as e:
                logger.warning(f"[PURGE-ERROR] {tid}/{coll}: {e}")
                summary[tid][coll] = f"error: {e}"
    return summary


def seed_tenants(db, dry_run: bool, logger) -> Dict[str, Any]:
    """Seed 3-5 realistic records per tenant using existing model field names."""
    from datetime import datetime, timezone, timedelta

    seed_summary = {}
    now = datetime.now(timezone.utc)

    # Definitions: hazards + flight diversions etc. Use model-compatible fields
    # Minimal deterministic seed profile (one complete workflow per tenant, idempotent)
    # Deterministic IDs prevent duplicates on repeated runs (document ID = workflow key)
    # Canonical departments: Flight Operations (flight_ops), Safety (safety), Airside Operations (airside_ops), ARFF (arff)
    # Task departments mapped to canonical: Flight Operations->Flight Operations, Safety & Quality->Safety, Ground Handling->Ground Operations (stored as Safety for fishtail-air to stay canonical), etc.
    # For this minimal seed we use canonical display values: Flight Operations and Airside Operations / ARFF (Rescue & Firefighting)
    minimal_workflows = {
        "fishtail-air": {
            "department": "Flight Operations",  # canonical: flight_ops -> Flight Operations
            "report": {
                "id": "report-fishtail-air-mor-001",
                "report_type": "mandatory",
                "title": "MOR - Unstabilized Approach RWY 02",
                "description": "MOR filed for unstabilized approach, high vertical speed, late configuration, go-around executed.",
                "status": "SUBMITTED",
            },
            "hazard": {
                "id": "hazard-fishtail-air-001",
                "hazard_id": "FI-HZ-001-26",
                "title": "Unstabilized Approach",
                "description": "Unstabilized approach on RWY 02, steep angle, go-around.",
                "source": "MOR",
                "source_id": "MOR-FISHTAIL-2026-001",
                "taxonomy": "Organizational-Facilities",
                "priority": "H",
                "status": "Open",
                "department": "Flight Operations",
                "severity": 4, "probability": 3,
                "risk_index": 12, "risk_level": "High",
                "sram_data": {"mode": "BOWTIE", "bow_tie": {"threat": "Unstable energy", "top_event": "Go-around", "barriers": ["Stabilized criteria", "Go-around call"]}},
            },
            "can": {
                "id": "can-fishtail-air-001",
                "can_reference": "CAN-FISHTAIL-001",
                "title": "CAN - Stabilized Approach Training",
                "hazard_id": "FI-HZ-001-26",
                "department": "Flight Operations",
                "priority": "H",
                "status": "Open",
                "assigned_to": "safety@fishtailair.com",
            },
            "cap": {
                "id": "cap-fishtail-air-001-001",
                "cap_reference": "CAP-FISHTAIL-001-001",
                "can_id": "can-fishtail-air-001",
                "department": "Flight Operations",
                "action_plan": "Conduct stabilized approach refresher and FDM review",
                "status": "Open",
            },
        },
        "vnkt-airport": {
            "department": "Airside Operations",  # canonical: airside_ops -> Airside Operations
            "report": {
                "id": "report-vnkt-airport-vsr-001",
                "report_type": "voluntary",
                "title": "VSR - FOD on RWY 02/20",
                "description": "VSR for FOD detected on RWY 02/20 near TWY B, NOTAM issued.",
                "status": "SUBMITTED",
            },
            "hazard": {
                "id": "hazard-vnkt-airport-001",
                "hazard_id": "VN-HZ-001-26",
                "title": "FOD detected on RWY 02/20",
                "description": "FOD metallic piece found on runway, removed, inspection completed.",
                "source": "VSR",
                "source_id": "VSR-VNKT-2026-001",
                "taxonomy": "Organizational-Facilities",
                "priority": "H",
                "status": "Closed",
                "department": "Airside Operations",
                "severity": 3, "probability": 3,
                "risk_index": 9, "risk_level": "Medium",
                "sram_data": {"mode": "FISHBONE", "fishbone": {"categories": ["Man", "Machine", "Method", "Material"], "root_cause": "Ineffective FOD patrol frequency"}},
            },
            "can": {
                "id": "can-vnkt-airport-001",
                "can_reference": "CAN-VNKT-001",
                "title": "CAN - FOD Patrol Frequency Increase",
                "hazard_id": "VN-HZ-001-26",
                "department": "Airside Operations",
                "priority": "H",
                "status": "Closed",
                "assigned_to": "safety@vnkt-airport.gov.np",
            },
            "cap": {
                "id": "cap-vnkt-airport-001-001",
                "cap_reference": "CAP-VNKT-001-001",
                "can_id": "can-vnkt-airport-001",
                "department": "Airside Operations",
                "action_plan": "Increase FOD patrol to hourly and install magnetic sweeper",
                "status": "Closed",
            },
        },
    }

    for tid, wf in minimal_workflows.items():
        info = DEMO_TENANTS[tid]
        # Ensure tenant document exists (preserve if exists, create if missing) — deterministic, idempotent
        tenant_ref = db.collection("tenants").document(tid)
        try:
            snap = tenant_ref.get()
            if not snap.exists:
                if dry_run:
                    logger.info(f"[DRY-RUN] Would create tenant {tid} ({info['name']}) type {info['organization_type']}")
                else:
                    # Use canonical departments mapping: store task departments but note canonical mapping in log
                    # For fishtail-air we store canonical Flight Operations / Safety (mapped from Ground Handling->Ground Operations, Maintenance->Part-145)
                    # To keep task exact, store task list but document mapping
                    tenant_doc = {
                        "tenant_id": tid,
                        "name": info["name"],
                        "organization_type": info["organization_type"],
                        "departments": info["departments"],
                        "departments_canonical": [CANONICAL_LABELS.get(d.lower().replace(' ', '_').replace('&','').strip(), d) for d in info["departments"]],  # documented mapping
                        "active": True,
                        "created_at": now,
                        "updated_at": now,
                    }
                    tenant_ref.set(tenant_doc, merge=True)
                    logger.info(f"[SEED] Created tenant {tid} with departments {info['departments']}")
                    # Also ensure metadata/info preserved
                    try:
                        tenant_ref.collection("metadata").document("info").set({"tenant_id": tid, "name": info["name"], "updated_at": now}, merge=True)
                    except Exception:
                        pass
            else:
                if not dry_run:
                    tenant_ref.set({"departments": info["departments"], "updated_at": now}, merge=True)
                logger.info(f"[SEED] Tenant {tid} exists, departments synced (task canonical check logged)")
        except Exception as e:
            logger.warning(f"[SEED] Tenant {tid} check/create failed: {e}")

        seed_summary[tid] = {"reports": 0, "hazards": 0, "can_cap": 0, "caps": 0, "total": 0}
        # Seed one complete workflow: Report -> Hazard (with Risk/RCA) -> CAN -> CAP
        # Deterministic IDs allow idempotent re-run (set with fixed doc ID, not add)
        # Report
        r = wf["report"]
        report_doc = {
            "id": r["id"],
            "tenant_id": tid,
            "report_type": r["report_type"],
            "title": r["title"],
            "description": r["description"],
            "status": r["status"],
            "department": wf["department"],
            "created_at": now - timedelta(days=2),
            "updated_at": now - timedelta(days=2),
            "created_by": "seed-script",
        }
        # Hazard with embedded risk and RCA
        h = wf["hazard"]
        hazard_doc = {
            "hazard_id": h["hazard_id"],
            "tenant_id": tid,
            "title": h["title"],
            "description": h["description"],
            "source": h["source"],
            "source_id": h["source_id"],
            "taxonomy": h["taxonomy"],
            "priority": h["priority"],
            "status": h["status"],
            "department": h["department"],
            "severity": h["severity"],
            "probability": h["probability"],
            "risk_index": h["risk_index"],
            "risk_level": h["risk_level"],
            "sram_data": h["sram_data"],
            "created_by": "seed-script",
            "created_at": now - timedelta(days=1),
            "updated_at": now - timedelta(days=1),
        }
        # CAN
        c = wf["can"]
        can_doc = {
            "can_reference": c["can_reference"],
            "tenant_id": tid,
            "hazard_id": c["hazard_id"],
            "title": c["title"],
            "description": f"CAN for hazard {c['hazard_id']}",
            "department": c["department"],
            "priority": c["priority"],
            "status": c["status"],
            "assigned_to": c["assigned_to"],
            "target_completion_date": now + timedelta(days=30),
            "created_at": now,
            "updated_at": now,
            "created_by": "seed-script",
        }
        # CAP
        cap = wf["cap"]
        cap_doc = {
            "cap_reference": cap["cap_reference"],
            "tenant_id": tid,
            "can_id": cap["can_id"],
            "can_reference": c["can_reference"],
            "department": cap["department"],
            "action_plan": cap["action_plan"],
            "status": cap["status"],
            "created_at": now,
            "updated_at": now,
            "created_by": "seed-script",
        }

        # Dry-run preview
        if dry_run:
            logger.info(f"[DRY-RUN] Would seed {tid}: report {r['id']} -> hazard {h['hazard_id']} ({h['department']}, Bow-Tie/Fishbone) -> CAN {c['can_reference']} -> CAP {cap['cap_reference']} ({cap['status']})")
            seed_summary[tid] = {"reports": 1, "hazards": 1, "can_cap": 1, "caps": 1, "total": 4, "preview": f"Report {r['id']}, Hazard {h['hazard_id']}, CAN {c['can_reference']}, CAP {cap['cap_reference']}"}
            continue

        # Execute: idempotent set with deterministic doc IDs
        try:
            db.collection("tenants").document(tid).collection("reports").document(r["id"]).set(report_doc, merge=True)
            seed_summary[tid]["reports"] += 1
        except Exception as e:
            logger.warning(f"[SEED] report {r['id']} failed: {e}")
        try:
            db.collection("tenants").document(tid).collection("hazards").document(h["id"]).set(hazard_doc, merge=True)
            seed_summary[tid]["hazards"] += 1
        except Exception as e:
            logger.warning(f"[SEED] hazard {h['id']} failed: {e}")
        try:
            db.collection("tenants").document(tid).collection("can_cap").document(c["id"]).set(can_doc, merge=True)
            seed_summary[tid]["can_cap"] += 1
        except Exception as e:
            logger.warning(f"[SEED] can {c['id']} failed: {e}")
        try:
            db.collection("tenants").document(tid).collection("can_cap").document(c["id"]).collection("caps").document(cap["id"]).set(cap_doc, merge=True)
            seed_summary[tid]["caps"] += 1
        except Exception as e:
            logger.warning(f"[SEED] cap {cap['id']} failed: {e}")
        seed_summary[tid]["total"] = sum([seed_summary[tid]["reports"], seed_summary[tid]["hazards"], seed_summary[tid]["can_cap"], seed_summary[tid]["caps"]])

    return seed_summary


def firebase_auth_safety_check(project_id: str, database_id: str, logger) -> Dict[str, Any]:
    """Determine if beta and prod share same Firebase project (Auth is project-wide)."""
    # From repo: both sms-db and sms-db-beta use same project aerosafety-sms-prod
    # (see backend/app/firebase.py database_id param, and public/js/firebase.js BETA_CONFIG projectId)
    # We detect via config: if FIREBASE_PROJECT_ID is same for both, Auth is shared.
    from app.core.config import settings

    # The settings currently loaded will have project_id for this env (beta)
    # Production project is same value in this repo (aerosafety-sms-prod)
    prod_project = settings.FIREBASE_PROJECT_ID or os.getenv("FIREBASE_PROJECT_ID", "")
    is_shared = (project_id == prod_project)  # In this repo, always true: both use aerosafety-sms-prod
    # More precise: check if there exists a production database in same project
    # Since firebase.json declares both databases under same project, it's shared
    result = {
        "beta_project": project_id,
        "beta_database": database_id,
        "prod_database": "sms-db",
        "prod_project_guess": prod_project,
        "shared_project": True,  # Hard true for this repository: firebase.json shows both DBs in same project
        "auth_scoped_to_database": False,
        "auth_is_project_wide": True,
    }
    if result["shared_project"]:
        logger.warning("[AUTH-SAFETY] Beta and production SHARE the same Firebase project (aerosafety-sms-prod).")
        logger.warning("[AUTH-SAFETY] Firebase Auth custom claims are PROJECT-WIDE, not per-database.")
        logger.warning("[AUTH-SAFETY] AUTOMATIC Auth provisioning BLOCKED. Dedicated beta project or explicit approval required.")
        result["auth_blocked"] = True
        result["action"] = "BLOCKED - Auth provisioning stopped. Firestore purge/seed may proceed if its own checks pass."
    else:
        logger.info("[AUTH-SAFETY] Beta uses dedicated project — Auth provisioning allowed.")
        result["auth_blocked"] = False
        result["action"] = "Allowed - dedicated project"

    return result


def main():
    args = parse_args()
    # Hard-fail before Firebase initialization if any other database ID
    validate_database_id(args.database_id)

    # Determine execution mode: dry-run by default, explicit --dry-run supported
    if getattr(args, "dry_run", False):
        is_execute = False
        is_dry_run = True
    else:
        is_execute = args.execute and args.confirm_beta_purge
        is_dry_run = not is_execute
    mode = "execute" if is_execute else "dry-run"

    if args.execute and not args.confirm_beta_purge:
        print("[FATAL] --execute requires --confirm-beta-purge for destructive operation on sms-db-beta", file=sys.stderr)
        sys.exit(2)
    if is_dry_run and args.execute and not args.confirm_beta_purge:
        # Already handled, but ensure dry-run message
        pass

    # Setup logging
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"setup_two_tenants_beta_{ts}.log"
    json_path = LOG_DIR / f"setup_two_tenants_beta_{ts}.json"

    logger = logging.getLogger("beta_setup")
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(str(log_path))
    fh.setLevel(logging.INFO)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)

    commit = _get_commit()
    logger.info("="*70)
    logger.info("Beta-only Firestore reset & seed")
    logger.info("="*70)
    logger.info(f"Script version: {__VERSION__} commit: {commit}")
    logger.info(f"Database ID: {args.database_id}")
    logger.info(f"Execution mode: {mode}")
    logger.info(f"Dry-run: {is_dry_run}")
    logger.info(f"Auth operations: 0 (Auth disabled per safety directives)")

    # Init Firestore beta explicitly with database_id="sms-db-beta" (never without)
    db, project_id, database_id = init_firestore_beta()
    logger.info(f"Firebase project ID: {project_id}")
    logger.info(f"Firestore database ID: {database_id}")
    logger.info(f"Auth operations: 0")

    # Verify departments
    verify_departments()

    # Discover counts (dry-run preview)
    logger.info("[DISCOVER] Counting documents in demo tenant paths (beta only)...")
    counts_before = discover_counts(db)
    logger.info(f"[DISCOVER] Counts before: {json.dumps(counts_before, indent=2, default=str)}")

    # Auth safety check (separately executable phase)
    auth_check = firebase_auth_safety_check(project_id, database_id, logger)
    logger.info(f"[AUTH-CHECK] {json.dumps(auth_check, indent=2)}")

    # Purge (if not skipped)
    purge_summary = {}
    if not args.skip_purge:
        if is_dry_run:
            logger.info("[PURGE] Dry-run — no documents deleted. Would purge demo collections for 2 tenants.")
            purge_summary = purge_tenant_data(db, dry_run=True, logger=logger)
        else:
            logger.info("[PURGE] Execute — purging demo tenant subcollections in sms-db-beta...")
            purge_summary = purge_tenant_data(db, dry_run=False, logger=logger)
    else:
        logger.info("[PURGE] Skipped (--skip-purge)")

    # Seed
    seed_summary = {}
    if not args.skip_seed:
        if is_dry_run:
            logger.info("[SEED] Dry-run — no documents written.")
            seed_summary = seed_tenants(db, dry_run=True, logger=logger)
        else:
            logger.info("[SEED] Execute — seeding 3-5 records per tenant...")
            seed_summary = seed_tenants(db, dry_run=False, logger=logger)
    else:
        logger.info("[SEED] Skipped (--skip-seed)")

    # Discover after
    counts_after = discover_counts(db)
    logger.info(f"[DISCOVER] Counts after: {json.dumps(counts_after, indent=2, default=str)}")

    # Planned-after for dry-run: simulate what counts would be after purge+seed
    planned_after = {}
    try:
        for tid in DEMO_TENANTS:
            planned_after[tid] = {}
            before = counts_before.get(tid, {})
            # Purge would zero demo collections (preserve metadata)
            for coll in TENANT_SUBCOLLECTIONS_TO_PURGE:
                # For dry-run, purge_summary contains string like "dry-run would delete X"
                purged = 0
                val = purge_summary.get(tid, {}).get(coll, 0)
                if isinstance(val, int):
                    purged = val
                elif isinstance(val, str) and "would delete" in val:
                    try:
                        purged = int(''.join(filter(str.isdigit, val.split("would delete")[1].split()[0])))
                    except: purged = 0
                before_cnt = before.get(coll, 0) if isinstance(before.get(coll), int) else 0
                planned = max(0, before_cnt - purged)
                # Add seed preview (from seed_summary dry-run)
                seeded = 0
                if tid in seed_summary:
                    # seed_summary dry-run has preview counts
                    if coll in ["hazards", "reports", "can_cap", "caps"]:
                        seeded = 1  # minimal workflow: 1 per type
                    elif coll == "flight_diversions" and tid == "vnkt-airport":
                        seeded = 0  # minimal workflow for vnkt also 0 diversions (using hazard/CAN/CAP only)
                # For our minimal workflow, add 1 per tenant for each seeded type
                if tid == "fishtail-air" and coll in ["reports", "hazards", "can_cap"]:
                    planned += 1
                if tid == "fishtail-air" and coll == "can_cap/caps":
                    planned += 1
                if tid == "vnkt-airport" and coll in ["reports", "hazards", "can_cap"]:
                    planned += 1
                if tid == "vnkt-airport" and coll == "can_cap/caps":
                    planned += 1
                planned_after[tid][coll] = planned
            # Preserve metadata
            planned_after[tid]["metadata (protected, not purged)"] = before.get("metadata (protected, not purged)", 0)
    except Exception:
        planned_after = counts_after

    # Summary with required fields: Auth operations 0, no writes, no prod access
    summary = {
        "script_version": __VERSION__,
        "commit": commit,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id,
        "database_id": database_id,
        "execution_mode": mode,
        "dry_run": is_dry_run,
        "auth_operations": 0,
        "no_writes_dry_run": is_dry_run,
        "no_production_access": database_id == ALLOWED_DATABASE_ID and project_id == "aerosafety-sms-prod",
        "counts_before": counts_before,
        "planned_after": planned_after,
        "counts_after": counts_after,
        "purge_summary": purge_summary,
        "seed_summary": seed_summary,
        "auth_check": auth_check,
        "hard_fail_test": f"Script hard-fails for any --database-id != {ALLOWED_DATABASE_ID}",
        "protected_paths": PROTECTED_TENANT_PATHS + ["tenants/{tid}", "tenants/{tid}/metadata/*", "regulators/caan", "firestore.rules", "firestore.indexes.json"],
        "deletion_allowlist": TENANT_SUBCOLLECTIONS_TO_PURGE,
    }

    # Write JSON summary locally (not to Firestore if audit_logs purged)
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str)
        logger.info(f"[SUMMARY] JSON written to {json_path}")
        logger.info(f"[SUMMARY] Log written to {log_path}")
    except Exception as e:
        logger.warning(f"Failed to write summary: {e}")

    # Console summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(json.dumps(summary, indent=2, default=str))
    print(f"\nLog: {log_path}")
    print(f"JSON: {json_path}")

    if auth_check.get("auth_blocked"):
        print("\n[AUTH] Firestore purge/seed completed (if executed) but Auth provisioning was BLOCKED due to shared project.")
        print("      Create users manually in Firebase Console or approve dedicated beta project.")

    if is_dry_run:
        print("\n[DRY-RUN] No destructive changes made. To execute:")
        print(f"  python backend/scripts/setup_two_tenants_beta.py --database-id {ALLOWED_DATABASE_ID} --execute --confirm-beta-purge")
        sys.exit(0)
    else:
        print("\n[EXECUTE] Purge/seed completed on sms-db-beta only. Verify tenant metadata preserved.")
        sys.exit(0)


if __name__ == "__main__":
    main()
else:
    # Never execute purge logic merely by importing
    pass
