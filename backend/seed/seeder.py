# ============================================================================
# FILE: seeder.py
# PATH: backend/seed/seeder.py
# PURPOSE: Selective seeders for workspace tenants + user credentials.
#
#   1. seed_tenants_and_users()  - tenants (Firestore) + users (Auth) only.
#   2. reset_and_seed_minimal()  - destructive reset of sms-db to EXACTLY:
#        * tenants: 2 DEMO airlines (yeti-airlines, buddha-air),
#                   1 STATE regulator (caan), 1 SYSTEM tenant
#        * Auth:     6 accounts (2 per airline + CAAN SMD + Super Admin)
#      Operational data (reports / hazards / surveys / risk / CAPAs) is never
#      written; the Supabase operational tables stay at 0 rows.
#
# Usage (from backend/):
#   python -m seed.seeder                            # tenants + users upsert
#   python -m seed.seeder --reset-minimal --dry-run  # preview the reset+seed
#   python -m seed.seeder --reset-minimal            # execute the reset+seed
# ============================================================================

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

logger.remove()
logger.add(sys.stdout, format="{time:HH:mm:ss} | {level:<7} | {message}", level="INFO")

from seed.config import SEED_VERSION, OPERATOR_PROFILES, DEMO_USERS, DEVELOPER_ACCOUNT

# The single retained Super Admin account (never deleted during reset).
SUPER_ADMIN_EMAIL = DEVELOPER_ACCOUNT["email"]

# Minimal 2-airline demo dataset (the ONLY operator tenants in the reset DB).
MINIMAL_TENANT_IDS = ["buddha-air", "yeti-airlines"]

MINIMAL_TENANT_USERS = [
    {
        "tenant_id": "yeti-airlines",
        "organization": "Yeti Airlines",
        "users": [
            {"prefix": "admin", "email": "admin@yetiairlines.com",
             "role": "AIRLINE_ADMIN", "full_name": "Yeti Airlines Admin",
             "department": "Safety"},
            {"prefix": "ops", "email": "ops@yetiairlines.com",
             "role": "USER", "full_name": "Yeti Airlines Ops",
             "department": "Flight Operations"},
        ],
    },
    {
        "tenant_id": "buddha-air",
        "organization": "Buddha Air",
        "users": [
            {"prefix": "admin", "email": "admin@buddhaair.com",
             "role": "AIRLINE_ADMIN", "full_name": "Buddha Air Admin",
             "department": "Safety"},
            {"prefix": "ops", "email": "ops@buddhaair.com",
             "role": "USER", "full_name": "Buddha Air Ops",
             "department": "Flight Operations"},
        ],
    },
]


def seed_tenants_and_users(
    db=None,
    auth=None,
    tenant_ids: Optional[list] = None,
    include_caan: bool = True,
    print_counts: bool = True,
) -> dict:
    """Seed tenant documents (Firestore) and user credentials (Firebase Auth).

    Writes only the `tenants` collection + tenant metadata/risk-matrix defaults
    and the Auth accounts with role/tenant claims. Reports, hazards, surveys,
    PSAOE assessments, state-risk reference, and CAPAs are never touched.
    Idempotent: tenant docs / Auth accounts are upserted by uid or id.
    """
    from app.firebase import get_db, get_auth

    if db is None:
        db = get_db()
    if auth is None:
        auth = get_auth()

    if tenant_ids:
        known = {p["id"] for p in OPERATOR_PROFILES}
        unknown = [t for t in tenant_ids if t not in known]
        if unknown:
            raise ValueError(f"Unknown tenant id(s): {sorted(unknown)}")

    from seed.operators import (
        create_all_tenants,
        create_caan_tenant,
        create_regulator_scoping,
    )

    tenant_ids_created = create_all_tenants(db, tenant_ids)

    if include_caan:
        create_caan_tenant(db)
        if tenant_ids:
            create_regulator_scoping(db, operator_ids=tenant_ids_created + ["caan"])
        else:
            create_regulator_scoping(db)

    from seed.users import create_all_users

    created_users = create_all_users(auth, tenant_ids)

    counts = {
        "seed_version": SEED_VERSION,
        "tenants": len(tenant_ids_created) + (1 if include_caan else 0),
        "users": len(created_users),
        "tenant_ids": sorted(tenant_ids_created),
    }
    if print_counts:
        logger.info(
            f"Tenants+users seed complete: {counts['tenants']} tenants "
            f"({', '.join(counts['tenant_ids'])}), {counts['users']} users "
            f"(op tables untouched)"
        )
    return counts


# ============================================================================
# Minimal dataset reset (purge + seed)
# ============================================================================

_COLLECTIONS_TO_PURGE = ["users", "tenants", "regulators", "audit_logs"]


def _delete_doc_tree(reference) -> int:
    removed = 0
    for coll in reference.collections():
        for sub in coll.stream():
            removed += _delete_doc_tree(sub.reference)
            sub.reference.delete()
            removed += 1
    return removed


def purge_database_for_minimal_seed(db, auth, dry_run: bool = False) -> dict:
    """Delete every Firestore doc in users/tenants/regulators/audit_logs and
    every Firebase Auth user EXCEPT the Super Admin account. No-op in dry-run."""
    from app.core.config import settings

    removed = {"tenants": 0, "users": 0, "regulators": 0, "audit_logs": 0, "subdocs": 0}

    for col in _COLLECTIONS_TO_PURGE:
        snapshot = db.collection(col).stream()
        for doc in snapshot:
            if dry_run:
                removed[col] += 1
                continue
            removed["subdocs"] += _delete_doc_tree(doc.reference)
            doc.reference.delete()
            removed[col] += 1

    auth_removed = 0
    auth_kept = 0
    for record in auth.list_users().iterate_all():
        email = (record.email or "").lower()
        uid = record.uid
        is_super_admin = email == SUPER_ADMIN_EMAIL.lower() or uid == DEVELOPER_ACCOUNT["uid"]
        if is_super_admin:
            auth_kept += 1
            continue
        if dry_run:
            auth_removed += 1
            continue
        auth.delete_user(uid)
        auth_removed += 1

    logger.info(
        f"Purge {'dry-run' if dry_run else 'complete'}: "
        f"tenants={removed['tenants']} users={removed['users']} "
        f"regulators={removed['regulators']} audit_logs={removed['audit_logs']} "
        f"subdocs={removed['subdocs']}; Auth removed={auth_removed}, kept={auth_kept}"
    )
    removed["auth_removed"] = auth_removed
    removed["auth_kept"] = auth_kept
    return removed


def _mirror_user_to_firestore(db, auth, uid: str) -> None:
    from app.services.users import user_doc_from_auth_record, upsert_user_doc

    record = auth.get_user(uid)
    upsert_user_doc(uid, user_doc_from_auth_record(record))


def _seed_minimal_tenants(db) -> list:
    from seed.operators import (
        create_tenant,
        create_caan_tenant,
        create_system_tenant,
        create_regulator_scoping,
    )

    profiles = {p["id"]: p for p in OPERATOR_PROFILES}
    tenant_ids_created = []
    for tid in MINIMAL_TENANT_IDS:
        profile = dict(profiles[tid])
        profile.setdefault("category", "DEMO")
        profile.setdefault("status", "ACTIVE")
        tenant_ids_created.append(create_tenant(db, profile))

    create_caan_tenant(db)
    create_system_tenant(db)
    create_regulator_scoping(db, operator_ids=list(MINIMAL_TENANT_IDS))

    logger.info(f"Minimal tenants seeded: {len(tenant_ids_created) + 2} "
                f"({tenant_ids_created} + caan + system)")
    return tenant_ids_created


def _seed_minimal_users(db, auth) -> list:
    from seed.config import DEMO_USER_PASSWORD
    from seed.users import create_user

    created = []

    for tenant_cfg in MINIMAL_TENANT_USERS:
        tid = tenant_cfg["tenant_id"]
        for spec in tenant_cfg["users"]:
            user_spec = {
                "uid": f"{spec['prefix']}-{tid}-001",
                "email": spec["email"],
                "password": DEMO_USER_PASSWORD,
                "full_name": spec["full_name"],
                "organization": tenant_cfg["organization"],
                "role": spec["role"],
                "tenant_id": tid,
                "department": spec.get("department", ""),
                "sync_password": True,
            }
            result = create_user(auth, user_spec)
            _mirror_user_to_firestore(db, auth, result["uid"])
            created.append(result["uid"])

    smd_result = create_user(auth, {**dict(DEMO_USERS[0]), "sync_password": True})
    _mirror_user_to_firestore(db, auth, smd_result["uid"])
    created.append(smd_result["uid"])

    super_admin_spec = {**dict(DEVELOPER_ACCOUNT), "tenant_id": "system"}
    dev_result = create_user(auth, super_admin_spec)
    _mirror_user_to_firestore(db, auth, dev_result["uid"])
    created.append(dev_result["uid"])

    logger.info(f"Minimal users seeded: {len(created)} ({', '.join(created)})")
    return created


def reset_and_seed_minimal(db=None, auth=None, dry_run: bool = False) -> dict:
    """Destructively reset sms-db to the minimal 2-airline demo dataset, then
    seed tenants + users only. Returns a summary dict."""
    from app.firebase import get_db, get_auth

    if db is None:
        db = get_db()
    if auth is None:
        auth = get_auth()

    purge = purge_database_for_minimal_seed(db, auth, dry_run=dry_run)
    if dry_run:
        return {"mode": "dry-run", "purge": purge, "seed": {"tenants": [], "users": 0}}

    tenants = _seed_minimal_tenants(db)
    users = _seed_minimal_users(db, auth)
    return {
        "mode": "executed",
        "purge": purge,
        "seed": {"tenants": tenants + ["caan", "system"], "users": len(users)},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Seed workspace tenants + user credentials only.")
    parser.add_argument("--tenant-id", action="append", default=None,
                        help="Restrict operator tenants (repeatable).")
    parser.add_argument("--no-caan", action="store_true",
                        help="Skip the CAAN state-regulator tenant.")
    parser.add_argument("--reset-minimal", action="store_true",
                        help="Destructive reset to the minimal 2-airline demo dataset.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the planned actions without writing anything.")
    args = parser.parse_args(argv)

    if args.reset_minimal:
        result = reset_and_seed_minimal(dry_run=args.dry_run)
        print(f"\nReset-minimal {'DRY RUN (no writes)' if args.dry_run else 'complete'}:")
        if args.dry_run:
            print(f"  would purge: {result['purge']}")
            print(f"  would seed : 4 tenants (2 DEMO airlines + caan + system), 6 accounts")
        else:
            print(f"  purged : {result['purge']}")
            print(f"  seeded : tenants={result['seed']['tenants']}, users={result['seed']['users']}")
            import datetime as _dt
            print(f"  at     : {_dt.datetime.now(timezone.utc).isoformat()}")
        return 0

    counts = seed_tenants_and_users(
        tenant_ids=args.tenant_id,
        include_caan=not args.no_caan,
    )
    for key, value in counts.items():
        if key == "tenant_ids" and value and len(value) > 4:
            print(f"  {key}: {len(value)} tenants")
        else:
            print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())