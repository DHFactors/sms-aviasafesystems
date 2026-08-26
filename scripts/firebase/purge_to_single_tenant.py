"""Reduce sms-db-beta to a single airline tenant: fishtail-air.

Safety:
- Hard-fails for any database_id != "sms-db-beta"
- Requires --execute AND --confirm-purge for any write
- Auth operations: 0
- Never touches regulators/caan beyond operator_tenant_ids

Actions:
1. Delete all tenant documents and subcollections except fishtail-air
2. Clean /users mirror records for non-fishtail tenants
3. Set regulators/caan.operator_tenant_ids to ["fishtail-air"]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

ALLOWED_DATABASE_ID = "sms-db-beta"
KEEP_TENANT = "fishtail-air"

SUBCOLLECTIONS = [
    "hazards", "reports", "can_cap", "surveys", "responses",
    "verification", "flight_diversions", "notifications", "metadata",
    "audit_logs",
]


def log(msg: str):
    print(f"{datetime.now(timezone.utc).isoformat()} {msg}", flush=True)


def delete_subcollections(db, tenant_ref) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for coll_name in SUBCOLLECTIONS:
        coll_ref = tenant_ref.collection(coll_name)
        deleted = 0
        while True:
            docs = list(coll_ref.limit(400).stream())
            if not docs:
                break
            batch = db.batch()
            for d in docs:
                batch.delete(d.reference)
            batch.commit()
            deleted += len(docs)
        if deleted:
            counts[coll_name] = deleted

    can_ref = tenant_ref.collection("can_cap")
    for can_doc in can_ref.stream():
        caps_ref = can_doc.reference.collection("caps")
        cap_deleted = 0
        while True:
            caps = list(caps_ref.limit(400).stream())
            if not caps:
                break
            batch = db.batch()
            for c in caps:
                batch.delete(c.reference)
            batch.commit()
            cap_deleted += len(caps)
        if cap_deleted:
            counts[f"can_cap/{can_doc.id}/caps"] = cap_deleted

    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Reduce sms-db-beta to fishtail-air only")
    parser.add_argument("--database-id", required=True, help="Must be exactly sms-db-beta")
    parser.add_argument("--dry-run", action="store_true", help="List tenants only, no writes")
    parser.add_argument("--execute", action="store_true", help="Execute destructive purge")
    parser.add_argument("--confirm-purge", action="store_true", help="Explicit confirmation")
    args = parser.parse_args(argv)

    if args.database_id != ALLOWED_DATABASE_ID:
        log(f"[FATAL] Refusing: --database-id must be '{ALLOWED_DATABASE_ID}' (got '{args.database_id}')")
        return 2
    if args.execute and not args.confirm_purge:
        log("[FATAL] --execute requires --confirm-purge")
        return 2
    if not args.execute:
        args.dry_run = True

    from app.core.config import settings
    import firebase_admin
    from firebase_admin import credentials, firestore

    cred_dict = {
        "type": "service_account",
        "project_id": settings.FIREBASE_PROJECT_ID,
        "private_key": settings.FIREBASE_PRIVATE_KEY.replace("\\n", "\n"),
        "client_email": settings.FIREBASE_CLIENT_EMAIL,
        "token_uri": settings.FIREBASE_TOKEN_URI,
    }
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred_dict))
    db = firestore.client(database_id=ALLOWED_DATABASE_ID)

    log(f"[INFO] database={ALLOWED_DATABASE_ID} execute={args.execute}")

    tenants_snap = list(db.collection("tenants").stream())
    tenant_ids = [t.id for t in tenants_snap]
    log(f"[PRE-FLIGHT] tenants found ({len(tenant_ids)}): {tenant_ids}")

    to_delete = [tid for tid in tenant_ids if tid != KEEP_TENANT]
    log(f"[PRE-FLIGHT] to_delete ({len(to_delete)}): {to_delete}")

    if KEEP_TENANT not in tenant_ids:
        log(f"[FATAL] keeper tenant '{KEEP_TENANT}' not found in tenants collection!")
        return 3

    reg_doc = db.collection("regulators").document("caan").get()
    reg_before = (reg_doc.to_dict() or {}).get("operator_tenant_ids") if reg_doc.exists else None
    log(f"[PRE-FLIGHT] regulators/caan.operator_tenant_ids = {reg_before}")

    if not args.execute:
        log(f"[DRY-RUN] Would delete {len(to_delete)} tenant docs + subcollections.")
        log(f"[DRY-RUN] Would set regulators/caan.operator_tenant_ids = [\"{KEEP_TENANT}\"]")
        return 0

    total_deleted = 0
    t_start = time.perf_counter()
    for tid in to_delete:
        t0 = time.perf_counter()
        tenant_ref = db.collection("tenants").document(tid)
        sub_counts = delete_subcollections(db, tenant_ref)
        sub_total = sum(sub_counts.values())
        tenant_ref.delete()
        total_deleted += sub_total + 1
        log(f"[DELETE] {tid}: doc + {sub_total} subcol docs in {time.perf_counter()-t0:.1f}s {sub_counts}")

    log("[USERS] cleaning /users mirror records for non-fishtail tenants...")
    users_deleted = 0
    for u in db.collection("users").stream():
        d = u.to_dict()
        if d.get("tenant_id") and d["tenant_id"] != KEEP_TENANT:
            u.reference.delete()
            users_deleted += 1
    log(f"[USERS] deleted {users_deleted} user mirror records")

    log("[REGULATOR] setting regulators/caan.operator_tenant_ids ...")
    db.collection("regulators").document("caan").set(
        {"operator_tenant_ids": [KEEP_TENANT]}, merge=True
    )
    reg_after = (db.collection("regulators").document("caan").get().to_dict() or {}).get("operator_tenant_ids")
    log(f"[REGULATOR] after: {reg_after}")

    remaining = [t.id for t in db.collection("tenants").stream()]
    log(f"[POST-VERIFY] tenants ({len(remaining)}): {remaining}")

    elapsed = time.perf_counter() - t_start
    ok = remaining == [KEEP_TENANT] and reg_after == [KEEP_TENANT]
    log(f"[DONE] success={ok} total_deleted={total_deleted + users_deleted} elapsed={elapsed:.1f}s")

    summary = {
        "database_id": ALLOWED_DATABASE_ID,
        "deleted_tenants": to_delete,
        "remaining_tenants": remaining,
        "users_deleted": users_deleted,
        "regulator_before": reg_before,
        "regulator_after": reg_after,
        "success": ok,
        "elapsed_seconds": round(elapsed, 2),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    log_dir = BACKEND / "scripts" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_path = log_dir / f"purge_single_tenant_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    log(f"[SUMMARY] {summary_path}")

    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
