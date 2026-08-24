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


def parse_args():
    p = argparse.ArgumentParser(description="Beta-only Firestore reset & seed for sms-db-beta")
    p.add_argument("--database-id", required=True, help="Must be exactly sms-db-beta")
    p.add_argument("--execute", action="store_true", help="Execute destructive purge/seed (default dry-run)")
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
    airline_hazards = [
        {
            "title": "Unstabilized Approach - RWY 02",
            "description": "Aircraft on final approach to VNKT RWY 02 reported high vertical speed and late configuration, executed go-around. Flight data shows approach angle 4.2 degrees excess.",
            "source": "VSR",
            "source_id": "VSR-FSH-2026-001",
            "taxonomy": "Organizational-Facilities",
            "priority": "H",
            "status": "Open",
            "department": "Flight Operations",
            "severity": 4, "probability": 3,
        },
        {
            "title": "Hydraulic Leak - A319",
            "description": "Post-flight inspection revealed hydraulic fluid leak at left MLG actuator, quantity low, system pressure fluctuation 2800-3000 psi.",
            "source": "Internal Audit",
            "source_id": "AUD-FSH-2026-002",
            "taxonomy": "Technical",
            "priority": "H",
            "status": "Open",
            "department": "Maintenance",
            "severity": 3, "probability": 3,
        },
        {
            "title": "Tail Rotor Chip Indication",
            "description": "Chip detector warning for tail rotor gearbox on AS350, magnetic plug inspection showed fine metallic particles, component quarantined.",
            "source": "MOR",
            "source_id": "MOR-FSH-2026-003",
            "taxonomy": "Technical",
            "priority": "M",
            "status": "Under Review",
            "department": "Maintenance",
            "severity": 4, "probability": 2,
        },
        {
            "title": "Cabin Safety Briefing Deviation",
            "description": "Cabin crew omitted brace position demonstration on sector VNKT-PKR, safety audit finding via spot check.",
            "source": "Quality Audit",
            "source_id": "QA-FSH-2026-004",
            "taxonomy": "Human Factors",
            "priority": "M",
            "status": "Open",
            "department": "Safety & Quality",
            "severity": 2, "probability": 3,
        },
    ]

    aerodrome_hazards = [
        {
            "title": "FOD detected on RWY 02/20 - Taxiway B",
            "description": "Runway inspection found metallic FOD near TWY B intersection, size approx 15cm, removed, NOTAM issued 02/20 closed 15 min.",
            "source": "Safety Inspection",
            "source_id": "INSP-VNKT-2026-001",
            "taxonomy": "Organizational-Facilities",
            "priority": "H",
            "status": "Open",
            "department": "Airside Operations",
            "severity": 3, "probability": 4,
        },
        {
            "title": "Bird flock incursion near threshold 20",
            "description": "ATC reported flock of 30+ birds at 50ft AGL near THR 20 during arrival of RA-401, bird dispersal unit deployed, wildlife log updated.",
            "source": "VSR",
            "source_id": "VSR-VNKT-2026-002",
            "taxonomy": "Wildlife",
            "priority": "H",
            "status": "Open",
            "department": "Wildlife & Bird Hazard Management",
            "severity": 3, "probability": 4,
        },
        {
            "title": "Apron service vehicle speed violation - Bay 5",
            "description": "Ground handling baggage tug recorded 42 km/h in apron (limit 25), safety camera review, driver re-training scheduled.",
            "source": "Internal Audit",
            "source_id": "AUD-VNKT-2026-003",
            "taxonomy": "Human Factors",
            "priority": "M",
            "status": "Under Review",
            "department": "Apron Control",
            "severity": 2, "probability": 4,
        },
        {
            "title": "ARFF vehicle bay door malfunction",
            "description": "ARFF Crash Tender 2 bay door failed to open during weekly drill, delay 45 sec, maintenance ticket raised, backup vehicle positioned.",
            "source": "Safety Inspection",
            "source_id": "INSP-VNKT-2026-004",
            "taxonomy": "Technical",
            "priority": "H",
            "status": "Open",
            "department": "Rescue & Fire Fighting (ARFF)",
            "severity": 4, "probability": 2,
        },
        {
            "title": "ATC coordination - missed handover VHF 118.1",
            "description": "Approach and tower frequency handover delayed 2 min during peak, coordination SOP briefing conducted for ATCO team.",
            "source": "Internal Audit",
            "source_id": "AUD-VNKT-2026-005",
            "taxonomy": "Organizational-Documentation, Processes and Procedures",
            "priority": "M",
            "status": "Open",
            "department": "Air Traffic Coordination",
            "severity": 2, "probability": 3,
        },
    ]

    for tid, info in DEMO_TENANTS.items():
        # Ensure tenant document exists (preserve if exists, create if missing)
        tenant_ref = db.collection("tenants").document(tid)
        try:
            snap = tenant_ref.get()
            if not snap.exists:
                if dry_run:
                    logger.info(f"[DRY-RUN] Would create tenant {tid} ({info['name']})")
                else:
                    tenant_doc = {
                        "tenant_id": tid,
                        "name": info["name"],
                        "organization_type": info["organization_type"],
                        "departments": info["departments"],
                        "active": True,
                        "created_at": now,
                        "updated_at": now,
                    }
                    # Store canonical departments derived from scope if possible
                    tenant_ref.set(tenant_doc)
                    logger.info(f"[SEED] Created tenant {tid}")
            else:
                # Update departments to match task spec (preserve other metadata)
                if not dry_run:
                    tenant_ref.update({"departments": info["departments"], "updated_at": now})
                logger.info(f"[SEED] Tenant {tid} exists, departments synced")
        except Exception as e:
            logger.warning(f"[SEED] Tenant {tid} check/create failed: {e}")

        # Seed hazards
        hazards = airline_hazards if tid == "fishtail-air" else aerodrome_hazards
        # Take 3-5: use 4 for fishtail, 5 for vnkt
        hazards_to_seed = hazards[:4] if tid == "fishtail-air" else hazards[:5]
        seed_summary[tid] = {"hazards": 0, "flight_diversions": 0, "can_cap": 0}
        for idx, h in enumerate(hazards_to_seed, start=1):
            doc = {
                "hazard_id": f"{tid[:2].upper()}-HZ-{idx:03d}-26",
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
                "created_by": "seed-script",
                "created_at": now - timedelta(days=idx),
                "updated_at": now - timedelta(days=idx),
            }
            if dry_run:
                logger.info(f"[DRY-RUN] Would seed hazard {doc['hazard_id']} for {tid} dept {h['department']}")
            else:
                try:
                    db.collection("tenants").document(tid).collection("hazards").add(doc)
                    seed_summary[tid]["hazards"] += 1
                except Exception as e:
                    logger.warning(f"[SEED] hazard {h['title']} failed: {e}")

        # Seed flight diversions (aerodrome) or additional hazards as CAN demo for airline
        if tid == "vnkt-airport":
            diversions = [
                {"reason": "Weather", "description": "Diversion to VNPK due to CB over VNKT", "department": "Airside Operations"},
                {"reason": "Technical", "description": "Diversion for hydraulic indication, landed VNPK", "department": "Airside Operations"},
            ]
            for idx, d in enumerate(diversions, start=1):
                doc = {
                    "diversion_id": f"{tid}-DIV-{idx:03d}",
                    "tenant_id": tid,
                    "reason": d["reason"],
                    "description": d["description"],
                    "department": d["department"],
                    "status": "Open",
                    "created_at": now - timedelta(days=idx),
                    "updated_at": now,
                    "created_by": "seed-script",
                }
                if dry_run:
                    logger.info(f"[DRY-RUN] Would seed diversion {doc['diversion_id']}")
                else:
                    try:
                        db.collection("tenants").document(tid).collection("flight_diversions").add(doc)
                        seed_summary[tid]["flight_diversions"] += 1
                    except Exception as e:
                        logger.warning(f"[SEED] diversion failed: {e}")
        else:
            # For airline, seed 2 CANs as demo
            for idx in range(2):
                can_doc = {
                    "can_reference": f"CAN-{idx+1:03d}",
                    "tenant_id": tid,
                    "hazard_id": f"{tid[:2].upper()}-HZ-{idx+1:03d}-26",
                    "title": f"CAN for {hazards_to_seed[idx]['title']}",
                    "description": "Corrective action required per safety review",
                    "department": hazards_to_seed[idx]["department"],
                    "priority": hazards_to_seed[idx]["priority"],
                    "status": "Open",
                    "assigned_to": "safety@fishtailair.com",
                    "assigned_to_uid": "",
                    "target_completion_date": now + timedelta(days=30),
                    "created_at": now - timedelta(days=idx),
                    "updated_at": now,
                    "created_by": "seed-script",
                }
                if dry_run:
                    logger.info(f"[DRY-RUN] Would seed CAN {can_doc['can_reference']}")
                else:
                    try:
                        db.collection("tenants").document(tid).collection("can_cap").add(can_doc)
                        seed_summary[tid]["can_cap"] += 1
                    except Exception as e:
                        logger.warning(f"[SEED] CAN failed: {e}")

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
    validate_database_id(args.database_id)

    # Determine execution mode
    is_execute = args.execute and args.confirm_beta_purge
    is_dry_run = not is_execute
    mode = "execute" if is_execute else "dry-run"

    if args.execute and not args.confirm_beta_purge:
        print("[FATAL] --execute requires --confirm-beta-purge for destructive operation on sms-db-beta", file=sys.stderr)
        sys.exit(2)

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

    logger.info("="*70)
    logger.info("Beta-only Firestore reset & seed")
    logger.info("="*70)
    logger.info(f"Database ID: {args.database_id}")
    logger.info(f"Execution mode: {mode}")
    logger.info(f"Dry-run: {is_dry_run}")

    # Init Firestore beta explicitly
    db, project_id, database_id = init_firestore_beta()
    logger.info(f"Firebase project ID: {project_id}")
    logger.info(f"Firebase database ID: {database_id}")

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

    # Summary
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id,
        "database_id": database_id,
        "execution_mode": mode,
        "dry_run": is_dry_run,
        "counts_before": counts_before,
        "purge_summary": purge_summary,
        "seed_summary": seed_summary,
        "counts_after": counts_after,
        "auth_check": auth_check,
        "hard_fail_test": f"Script hard-fails for any --database-id != {ALLOWED_DATABASE_ID}",
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
