"""All-tenant READ-ONLY inventory for sms-db-beta.

Exact document counts per tenant for every seed-owned collection plus the
protected top-level surfaces, with PURGE / PRESERVE / EMPTY / PENDING marks.

Safety:
- Hard-fails for any database_id != "sms-db-beta"
- Never writes to Firestore or Auth (inventory only)
- Exact counts: Firestore aggregation count() self-tested against full
  enumeration on every query; enumeration fallback is exact by construction.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

ALLOWED_DATABASE_ID = "sms-db-beta"
ROOT = BACKEND.parent
LOG_DIR = BACKEND / "scripts" / "logs"

__VERSION__ = "1.0.0-beta-inventory"

MINIMAL_TENANTS = ["fishtail-air", "vnkt-airport"]

TENANT_OPERATIONAL_COLLECTIONS = [
    "reports",
    "hazards",
    "can_cap",
    "surveys",
    "responses",
    "verification",
    "flight_diversions",
    "notifications",
]

TOP_LEVEL_PRESERVE_COLLECTIONS = [
    "psoe_assessments",
    "audit_logs",
    "feedback",
    "regulators",
    "surveyResponses",
    "public_responses",
    "demo_sessions",
    "caan_oversight",
]

STATE_RISK_REGISTER_PATH = "state/ssp/risk_register"


def _aggregation_count(coll_ref) -> int:
    results = coll_ref.count().get()
    return int(results[0][0].value)


def _enumeration_count(coll_ref, page_size: int = 1000) -> int:
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


def exact_collection_count(coll_ref) -> Dict[str, Any]:
    try:
        agg = _aggregation_count(coll_ref)
    except Exception as e:
        enum = _enumeration_count(coll_ref)
        return {"count": enum, "method": f"enumeration_fallback(aggregation_error:{type(e).__name__})", "mark_ok": True}
    try:
        enum = _enumeration_count(coll_ref)
    except Exception as e:
        return {"count": agg, "method": f"aggregation(enum_error:{type(e).__name__})", "mark_ok": False}
    if agg == enum:
        return {"count": agg, "method": "aggregation_verified", "mark_ok": True}
    return {"count": enum, "method": f"enumeration_mismatch(agg={agg})", "mark_ok": True}


def count_nested_caps(db, tid: str) -> Dict[str, Any]:
    cans = list(db.collection("tenants").document(tid).collection("can_cap").stream())
    total_caps = 0
    cap_ids: List[str] = []
    for can in cans:
        caps = list(can.reference.collection("caps").stream())
        total_caps += len(caps)
        cap_ids.extend(c.id for c in caps)
    return {"count": total_caps, "ids": cap_ids, "cans": len(cans)}


def probe_subcollection_exists(coll_ref) -> bool:
    return len(list(coll_ref.limit(1).stream())) > 0


def mark_for(tenant_id: str, collection: str, count: int, pending: bool) -> str:
    if pending:
        return "PENDING"
    if collection == "metadata":
        return "PRESERVE"
    if count == 0:
        return "EMPTY"
    if tenant_id in MINIMAL_TENANTS:
        return "PRESERVE"
    return "PURGE"


def inventory_tenant(db, tid: str) -> Dict[str, Any]:
    entry: Dict[str, Any] = {}
    tdoc = db.collection("tenants").document(tid).get()
    entry["tenant_doc"] = {"exists": bool(tdoc.exists), "mark": "PRESERVE"}
    meta = list(db.collection("tenants").document(tid).collection("metadata").stream())
    entry["metadata"] = {
        "count": len(meta),
        "ids": [m.id for m in meta],
        "mark": "PRESERVE",
    }
    ops: Dict[str, Any] = {}
    for coll in TENANT_OPERATIONAL_COLLECTIONS:
        ref = db.collection("tenants").document(tid).collection(coll)
        if not probe_subcollection_exists(ref):
            ops[coll] = {"count": 0, "mark": "EMPTY", "method": "probe_empty"}
            continue
        res = exact_collection_count(ref)
        ops[coll] = {
            "count": res["count"],
            "method": res["method"],
            "mark": mark_for(tid, coll, res["count"], pending=not res["mark_ok"]),
        }
    caps_res = count_nested_caps(db, tid)
    ops["can_cap/caps (nested)"] = {
        "count": caps_res["count"],
        "ids": caps_res["ids"],
        "method": "per_can_enumeration",
        "mark": mark_for(tid, "caps", caps_res["count"], pending=False),
    }
    entry["operational"] = ops
    return entry


def inventory_top_level(db) -> Dict[str, Any]:
    top: Dict[str, Any] = {}
    for coll in TOP_LEVEL_PRESERVE_COLLECTIONS:
        ref = db.collection(coll)
        if not probe_subcollection_exists(ref):
            top[coll] = {"count": 0, "mark": "EMPTY", "method": "probe_empty"}
            continue
        res = exact_collection_count(ref)
        top[coll] = {
            "count": res["count"],
            "method": res["method"],
            "mark": "PRESERVE" if res["count"] else "EMPTY",
        }
    risk_ref = db.collection(STATE_RISK_REGISTER_PATH)
    res = exact_collection_count(risk_ref)
    top[STATE_RISK_REGISTER_PATH] = {
        "count": res["count"],
        "method": res["method"],
        "mark": "PRESERVE",
    }
    regs = list(db.collection("regulators").stream())
    top["regulators"]["docs"] = [
        {"id": r.id, "operator_tenant_ids": (r.to_dict() or {}).get("operator_tenant_ids")}
        for r in regs
    ]
    return top


def run_inventory(db, logger=None) -> Dict[str, Any]:
    def log(msg: str):
        if logger:
            logger.info(msg)
        else:
            print(msg)

    log("[SELF-TEST] validating exact-count helper...")
    test_refs = [
        ("fishtail-air/reports", db.collection("tenants").document("fishtail-air").collection("reports")),
        ("buddha-air/hazards", db.collection("tenants").document("buddha-air").collection("hazards")),
    ]
    for label, ref in test_refs:
        res = exact_collection_count(ref)
        log(f"[SELF-TEST] {label} -> {res['count']} via {res['method']} verified={res['mark_ok']}")
        assert res["mark_ok"], f"count helper failed verification for {label}"
    log("[SELF-TEST] PASS")

    tenant_ids = sorted(d.id for d in db.collection("tenants").stream())
    log(f"[INVENTORY] tenants discovered: {len(tenant_ids)}")

    tenants_report = {}
    for tid in tenant_ids:
        log(f"[INVENTORY] {tid} ...")
        tenants_report[tid] = inventory_tenant(db, tid)

    top_level = inventory_top_level(db)

    purge_targets = []
    for tid, entry in tenants_report.items():
        for coll, info in entry["operational"].items():
            if info["mark"] == "PURGE":
                purge_targets.append({"tenant": tid, "collection": coll, "count": info["count"]})

    report = {
        "script_version": __VERSION__,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database_id": ALLOWED_DATABASE_ID,
        "mode": "READ_ONLY_DRY_RUN",
        "writes": 0,
        "auth_operations": 0,
        "no_production_access": True,
        "minimal_tenants": MINIMAL_TENANTS,
        "counts_by_method_note": "aggregation counts are self-tested against full enumeration on every collection; mismatches resolved by exact enumeration",
        "top_level": top_level,
        "tenants": tenants_report,
        "purge_plan_preview": {
            "targets": purge_targets,
            "total_docs_to_purge": sum(t["count"] for t in purge_targets),
            "preserve": ["tenants/{tid}", "tenants/{tid}/metadata/*", "fishtail-air operational docs", "vnkt-airport operational docs"]
            + TOP_LEVEL_PRESERVE_COLLECTIONS
            + [STATE_RISK_REGISTER_PATH],
            "post_purge_steps": [
                "re-verify counts: legacy operational collections == 0",
                "update regulators/caan.operator_tenant_ids -> ['fishtail-air','vnkt-airport']",
                "re-run master-register live pagination tests",
            ],
        },
    }
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only all-tenant inventory for sms-db-beta")
    parser.add_argument("--database-id", required=True, help="Must be exactly sms-db-beta")
    args = parser.parse_args(argv)

    if args.database_id != ALLOWED_DATABASE_ID:
        print(f"[FATAL] Refusing: --database-id must be '{ALLOWED_DATABASE_ID}' (got '{args.database_id}')", file=sys.stderr)
        return 2

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

    report = run_inventory(db)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = LOG_DIR / f"all_tenants_dryrun_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(json.dumps(report["purge_plan_preview"], indent=2, default=str))
    print(f"\n[OK] Read-only inventory complete. No writes. Auth operations: 0.")
    print(f"[OK] Manifest written: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
