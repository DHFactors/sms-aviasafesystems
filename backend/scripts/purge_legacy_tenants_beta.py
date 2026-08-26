"""Beta-only legacy tenant purge for sms-db-beta.

Purges seed-owned operational data for an explicit 12-tenant allowlist and
updates regulators/caan.operator_tenant_ids to the minimal two-tenant set.

Safety:
- Hard-fails for any database_id != "sms-db-beta"
- Requires --execute AND --confirm-beta-purge for any write
- Pre-flight exact recount against the inventory manifest; aborts on drift
- Never touches tenants/{tid} docs, metadata/*, fishtail-air, vnkt-airport,
  or any top-level collection other than regulators/caan.operator_tenant_ids
- Auth operations: 0
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

ALLOWED_DATABASE_ID = "sms-db-beta"
LOG_DIR = BACKEND / "scripts" / "logs"
ROOT = BACKEND.parent

__VERSION__ = "1.0.0-beta-legacy-purge"

MINIMAL_TENANTS = ["fishtail-air", "vnkt-airport"]
REGULATOR_DOC = ("regulators", "caan")
NEW_OPERATOR_TENANT_IDS = ["fishtail-air", "vnkt-airport"]

COLLECTIONS_TO_PURGE = [
    "reports",
    "hazards",
    "can_cap",
    "surveys",
    "responses",
    "verification",
    "flight_diversions",
    "notifications",
]

LEGACY_ALLOWLIST: Dict[str, Dict[str, int]] = {
    "air-dynasty": {"reports": 32, "hazards": 118, "can_cap": 19, "caps": 40},
    "buddha-air": {"reports": 34, "hazards": 164, "can_cap": 31, "caps": 62},
    "demo-fixed-wing": {"reports": 0, "hazards": 168, "can_cap": 32, "caps": 67},
    "demo-rotary-wing": {"reports": 0, "hazards": 167, "can_cap": 30, "caps": 58},
    "himalaya-ground-services": {"reports": 26, "hazards": 108, "can_cap": 17, "caps": 32},
    "ktm-mro": {"reports": 33, "hazards": 113, "can_cap": 20, "caps": 35},
    "pokhara-aerodrome": {"reports": 26, "hazards": 99, "can_cap": 18, "caps": 35},
    "simrik-air": {"reports": 30, "hazards": 110, "can_cap": 19, "caps": 39},
    "sita-air": {"reports": 34, "hazards": 119, "can_cap": 21, "caps": 36},
    "summit-air": {"reports": 32, "hazards": 125, "can_cap": 20, "caps": 43},
    "tara-air": {"reports": 33, "hazards": 115, "can_cap": 20, "caps": 40},
    "yeti-airlines": {"reports": 37, "hazards": 151, "can_cap": 28, "caps": 59},
}


def log(msg: str):
    print(f"{datetime.now(timezone.utc).isoformat()} {msg}", flush=True)


def aggregation_count(coll_ref) -> int:
    return int(coll_ref.count().get()[0][0].value)


def enumeration_count(coll_ref, page_size: int = 1000) -> int:
    total = 0
    last = None
    while True:
        q = coll_ref.order_by("__name__").limit(page_size)
        if last is not None:
            q = q.start_after(last)
        docs = list(q.stream())
        if not docs:
            break
        total += len(docs)
        last = docs[-1]
    return total


def exact_count(coll_ref) -> int:
    try:
        agg = aggregation_count(coll_ref)
        enum = enumeration_count(coll_ref)
        return enum if agg != enum else agg
    except Exception:
        return enumeration_count(coll_ref)


def preflight(db) -> Dict[str, Any]:
    actual: Dict[str, Dict[str, int]] = {}
    drift: List[str] = []
    expected_total = 0
    actual_total = 0
    for tid, exp in LEGACY_ALLOWLIST.items():
        actual[tid] = {}
        for coll in COLLECTIONS_TO_PURGE:
            ref = db.collection("tenants").document(tid).collection(coll)
            n = exact_count(ref) if list(ref.limit(1).stream()) else 0
            actual[tid][coll] = n
        caps = 0
        for can in db.collection("tenants").document(tid).collection("can_cap").stream():
            caps += enumeration_count(can.reference.collection("caps"))
        actual[tid]["caps"] = caps
        for key in ["reports", "hazards", "can_cap", "caps"]:
            expected_total += exp[key]
            actual_total += actual[tid][key]
            if actual[tid][key] != exp[key]:
                drift.append(f"{tid}/{coll_key_name(key)}: expected {exp[key]}, found {actual[tid][key]}")
    minimal_state = {}
    for tid in MINIMAL_TENANTS:
        base_ref = db.collection("tenants").document(tid)
        entry = {
            coll: (
                exact_count(base_ref.collection(coll))
                if list(base_ref.collection(coll).limit(1).stream())
                else 0
            )
            for coll in ["reports", "hazards", "can_cap"]
        }
        entry["metadata"] = enumeration_count(base_ref.collection("metadata"))
        minimal_state[tid] = entry
    reg_doc = db.collection(REGULATOR_DOC[0]).document(REGULATOR_DOC[1]).get()
    regulator_current = None
    if reg_doc.exists:
        regulator_current = (reg_doc.to_dict() or {}).get("operator_tenant_ids")
    return {
        "actual": actual,
        "drift": drift,
        "expected_total": expected_total,
        "actual_total": actual_total,
        "minimal_before": minimal_state,
        "regulator_current": regulator_current,
    }


def coll_key_name(key: str) -> str:
    return key


def delete_collection_streaming(db, coll_ref, batch_size: int = 400) -> int:
    deleted = 0
    while True:
        docs = list(coll_ref.limit(batch_size).stream())
        if not docs:
            break
        batch = db.batch()
        for d in docs:
            batch.delete(d.reference)
        batch.commit()
        deleted += len(docs)
    return deleted


def purge_tenant(db, tid: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    base = db.collection("tenants").document(tid)
    caps_deleted = 0
    cans = list(base.collection("can_cap").stream())
    cap_batches: List[List[Any]] = []
    buf: List[Any] = []
    for can in cans:
        for cap in can.reference.collection("caps").stream():
            buf.append(cap.reference)
            if len(buf) >= 400:
                cap_batches.append(buf)
                buf = []
    if buf:
        cap_batches.append(buf)
    for chunk in cap_batches:
        b = db.batch()
        for ref in chunk:
            b.delete(ref)
        b.commit()
        caps_deleted += len(chunk)
    counts["caps"] = caps_deleted
    for coll in ["can_cap"] + [c for c in COLLECTIONS_TO_PURGE if c != "can_cap"]:
        counts[coll] = delete_collection_streaming(db, base.collection(coll))
    return counts


def update_regulator(db) -> Dict[str, Any]:
    ref = db.collection(REGULATOR_DOC[0]).document(REGULATOR_DOC[1])
    doc = ref.get()
    before = (doc.to_dict() or {}).get("operator_tenant_ids") if doc.exists else None
    ref.set({"operator_tenant_ids": NEW_OPERATOR_TENANT_IDS}, merge=True)
    after = (ref.get().to_dict() or {}).get("operator_tenant_ids")
    return {"before": before, "after": after}


def postverify(db, preflight_meta_count: Dict[str, int]) -> Dict[str, Any]:
    residual = {}
    for tid in LEGACY_ALLOWLIST:
        entry = {}
        for coll in COLLECTIONS_TO_PURGE:
            ref = db.collection("tenants").document(tid).collection(coll)
            n = exact_count(ref) if list(ref.limit(1).stream()) else 0
            if n:
                entry[coll] = n
        if entry:
            residual[tid] = entry
    minimal_after = {}
    for tid in MINIMAL_TENANTS:
        minimal_after[tid] = {
            coll: (
                exact_count(db.collection("tenants").document(tid).collection(coll))
                if list(db.collection("tenants").document(tid).collection(coll).limit(1).stream())
                else 0
            )
            for coll in ["reports", "hazards", "can_cap"]
        }
        meta_now = enumeration_count(db.collection("tenants").document(tid).collection("metadata"))
        minimal_after[tid]["metadata"] = meta_now
    reg = (db.collection(REGULATOR_DOC[0]).document(REGULATOR_DOC[1]).get().to_dict() or {})
    return {
        "residual_legacy": residual,
        "minimal_after": minimal_after,
        "regulator_operator_tenant_ids": reg.get("operator_tenant_ids"),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Purge legacy tenants from sms-db-beta (allowlisted)")
    parser.add_argument("--database-id", required=True, help="Must be exactly sms-db-beta")
    parser.add_argument("--dry-run", action="store_true", help="Pre-flight recount only, no writes")
    parser.add_argument("--execute", action="store_true", help="Execute destructive purge (requires --confirm-beta-purge)")
    parser.add_argument("--confirm-beta-purge", action="store_true", help="Explicit confirmation")
    args = parser.parse_args(argv)

    if args.database_id != ALLOWED_DATABASE_ID:
        log(f"[FATAL] Refusing: --database-id must be '{ALLOWED_DATABASE_ID}' (got '{args.database_id}')")
        return 2
    if args.execute and not args.dry_run and not args.confirm_beta_purge:
        log("[FATAL] --execute requires --confirm-beta-purge")
        return 2
    if not args.execute and not args.dry_run:
        args.dry_run = True

    from app.core.config import settings  # type: ignore
    import firebase_admin
    from firebase_admin import credentials, firestore

    project_id = settings.FIREBASE_PROJECT_ID
    cred_dict = {
        "type": "service_account",
        "project_id": project_id,
        "private_key": settings.FIREBASE_PRIVATE_KEY.replace("\\n", "\n"),
        "client_email": settings.FIREBASE_CLIENT_EMAIL,
        "token_uri": settings.FIREBASE_TOKEN_URI,
    }
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred_dict))
    db = firestore.client(database_id=ALLOWED_DATABASE_ID)

    log(f"[INFO] version={__VERSION__} project={project_id} database={ALLOWED_DATABASE_ID} execute={args.execute}")
    log(f"[INFO] allowlist_tenants={len(LEGACY_ALLOWLIST)} auth_operations=0")

    log("[PRE-FLIGHT] exact recount vs manifest...")
    pf = preflight(db)
    log(f"[PRE-FLIGHT] expected_total={pf['expected_total']} actual_total={pf['actual_total']} drift_items={len(pf['drift'])}")
    for d in pf["drift"]:
        log(f"[DRIFT] {d}")
    log(f"[PRE-FLIGHT] minimal_before={json.dumps(pf['minimal_before'])}")
    log(f"[PRE-FLIGHT] regulator.operator_tenant_ids current={pf['regulator_current']}")

    meta_counts_before = {t: pf["minimal_before"][t].get("metadata") for t in MINIMAL_TENANTS}

    summary: Dict[str, Any] = {
        "script_version": __VERSION__,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "database_id": ALLOWED_DATABASE_ID,
        "mode": "execute" if args.execute else "dry-run",
        "auth_operations": 0,
        "preflight": pf,
    }

    if pf["drift"]:
        summary["aborted_reason"] = "inventory drift detected"
        _write_summary(summary)
        log("[ABORT] Drift between manifest and live data. Re-run all-tenant dry-run and refresh allowlist.")
        return 3

    if not args.execute:
        summary["would_purge_docs"] = pf["actual_total"]
        summary["would_set_operator_tenant_ids"] = NEW_OPERATOR_TENANT_IDS
        _write_summary(summary)
        log(f"[DRY-RUN] No writes. Would purge ~{pf['actual_total']} docs across {len(LEGACY_ALLOWLIST)} tenants.")
        return 0

    log("[PURGE] Executing...")
    purged: Dict[str, Dict[str, int]] = {}
    total_deleted = 0
    t_start = time.perf_counter()
    for tid in LEGACY_ALLOWLIST:
        t0 = time.perf_counter()
        purged[tid] = purge_tenant(db, tid)
        n = sum(purged[tid].values())
        total_deleted += n
        log(f"[PURGE] {tid}: {n} docs in {time.perf_counter()-t0:.1f}s ({json.dumps(purged[tid])})")
    purge_seconds = time.perf_counter() - t_start

    log("[REGULATOR] updating operators/caan.operator_tenant_ids ...")
    regulator_result = update_regulator(db)

    log("[POST-VERIFY] recounting...")
    pv = postverify(db, meta_counts_before)
    log(f"[POST-VERIFY] residual_legacy={json.dumps(pv['residual_legacy'])}")
    log(f"[POST-VERIFY] minimal_after={json.dumps(pv['minimal_after'])}")
    log(f"[POST-VERIFY] regulator.operator_tenant_ids={pv['regulator_operator_tenant_ids']}")

    ok = (
        not pv["residual_legacy"]
        and pv["regulator_operator_tenant_ids"] == NEW_OPERATOR_TENANT_IDS
        and all(
            pv["minimal_after"][t][c] == pf["minimal_before"][t][c]
            for t in MINIMAL_TENANTS
            for c in ["reports", "hazards", "can_cap"]
        )
        and all(pv["minimal_after"][t]["metadata"] == pf["minimal_before"][t].get("metadata") for t in MINIMAL_TENANTS)
    )

    summary.update(
        {
            "purged_per_tenant": purged,
            "total_deleted_reported": total_deleted,
            "purge_seconds": round(purge_seconds, 2),
            "regulator_update": regulator_result,
            "postverify": pv,
            "success": ok,
        }
    )
    _write_summary(summary)
    log(f"[DONE] success={ok} total_deleted_reported={total_deleted}")
    return 0 if ok else 4


def _write_summary(summary: Dict[str, Any]):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"legacy_purge_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    log(f"[SUMMARY] written to {path}")


if __name__ == "__main__":
    sys.exit(main())
