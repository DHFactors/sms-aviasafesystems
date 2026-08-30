# ============================================================================
# FILE: unseed.py
# PATH: backend/seed/unseed.py
# PURPOSE: Remove runner-seeded test data from one or more operator tenants.
#
# Deletes ONLY data scoped to the targeted tenant(s):
#   * tenants/{tid}/surveys, reports, hazards, can_cap (+ caps), flight_diversions,
#     sms_maturity, metadata
#   * the tenant document itself (seed-created test tenants)
# With --include-users, also removes the tenant's Firebase Auth accounts and the
# mirrored users/{uid} docs.
#
# Never touched:
#   * the CAAN tenant ("caan") unless explicitly passed as --tenant-id caan
#   * the protected admin accounts (smd@caanepal.gov.np, super-admin-001,
#     system, any SUPER_ADMIN) even with --include-users
#
# When no --tenant-id is given, the five beta provider tenants are targeted and
# explicit confirmation is required.
#
# Usage (from backend/):
#   python -m seed.unseed --tenant-id buddha-air
#   python -m seed.unseed --tenant-id yeti-airlines --tenant-id tara-air --include-users
#   python -m seed.unseed                      # all 5 provider tenants (confirm required)
#   python -m seed.unseed --include-users --yes
# ============================================================================

import argparse
import os
import sys

BETA_DB_ID = "sms-db"

TENANT_SUBCOLLECTIONS = [
    "metadata",
    "surveys",
    "reports",
    "hazards",
    "can_cap",
    "flight_diversions",
    "sms_maturity",
]


def _confirm(prompt: str, yes: bool) -> bool:
    if yes:
        return True
    try:
        reply = input(f"{prompt} [y/N] ")
    except EOFError:
        print("No interactive terminal; re-run with --yes to skip confirmation.")
        return False
    return reply.strip().lower() in {"y", "yes"}


def _delete_tenant_docs(db, tenant_ref) -> dict:
    from app.core.config import settings

    removed = {}
    for sub in TENANT_SUBCOLLECTIONS:
        n = 0
        try:
            snapshots = list(tenant_ref.collection(sub).stream())
        except Exception as e:
            print(f"  ! failed to scan {tenant_ref.id}/{sub}: {e}")
            continue
        for snap in snapshots:
            if sub == "can_cap":
                try:
                    for cap in list(snap.reference.collection("caps").stream()):
                        cap.reference.delete()
                        removed.setdefault("caps", 0)
                        removed["caps"] += 1
                except Exception:
                    pass
            snap.reference.delete()
            n += 1
        if n:
            removed[sub] = n
            print(f"  deleted {n} docs in {tenant_ref.id}/{sub}")
    return removed


def _delete_tenant_users(db, auth, tid: str) -> dict:
    """Delete Auth users + users/{uid} mirrors for a tenant, skipping protected."""
    from app.core.config import settings
    from seed.config import PROTECTED_ADMIN_ACCOUNTS

    protected_emails = PROTECTED_ADMIN_ACCOUNTS["emails"]
    protected_uids = PROTECTED_ADMIN_ACCOUNTS["uids"]
    protected_roles = PROTECTED_ADMIN_ACCOUNTS["roles"]

    def is_protected(uid=None, email=None, role=None) -> bool:
        return (
            (uid and uid in protected_uids)
            or (email and email in protected_emails)
            or (role and role in protected_roles)
        )

    candidates = []
    try:
        snapshots = (
            db.collection(settings.FIREBASE_COLLECTION_USERS)
            .where("tenant_id", "==", tid)
            .get()
        )
        candidates.extend((s.id, (s.to_dict() or {})) for s in snapshots)
    except Exception as e:
        print(f"  ! failed to query users for {tid}: {e}")

    page_token = None
    while True:
        try:
            page = auth.list_users(max_results=1000, page_token=page_token)
        except Exception as e:
            print(f"  ! failed to list auth users: {e}")
            break
        for record in page.users:
            claims = record.custom_claims or {}
            if claims.get("tenant_id") == tid:
                candidates.append(
                    (record.uid, {"email": record.email, "role": claims.get("role")})
                )
        page_token = page.next_page_token
        if not page_token:
            break

    seen = set()
    removed_users = 0
    protected_hit = 0
    for uid, data in candidates:
        if uid in seen:
            continue
        seen.add(uid)
        if is_protected(uid=uid, email=data.get("email"), role=data.get("role")):
            print(f"  skipped protected account {uid} ({data.get('email')})")
            protected_hit += 1
            continue
        try:
            auth.delete_user(uid)
        except Exception as e:
            print(f"  ! failed to delete auth user {uid}: {e}")
        try:
            db.collection(settings.FIREBASE_COLLECTION_USERS).document(uid).delete()
        except Exception as e:
            print(f"  ! failed to delete users/{uid}: {e}")
        removed_users += 1
    return {"users": removed_users, "protected_skipped": protected_hit}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Unseed runner-created test data from operator tenants.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--db", default=BETA_DB_ID,
                        help="Firestore database id to unseed (default: sms-db).")
    parser.add_argument("--tenant-id", action="append", default=None,
                        help="Tenant(s) to unseed (repeatable). Defaults to all 5 provider "
                             "tenants. 'caan' is never implied.")
    parser.add_argument("--include-users", action="store_true",
                        help="Also delete the tenant's Firebase Auth accounts + users/{uid} "
                             "mirrors (protected admin accounts are always kept).")
    parser.add_argument("--yes", action="store_true",
                        help="Skip interactive confirmations.")
    args = parser.parse_args(argv)

    os.environ["FIREBASE_DATABASE_ID"] = args.db

    from app.core.config import settings
    from app.firebase import initialize_firebase
    from seed.config import OPERATOR_PROFILES

    if settings.FIREBASE_DATABASE_ID != args.db:
        print(f"ERROR: settings resolved to '{settings.FIREBASE_DATABASE_ID}' "
              f"but requested '{args.db}'.")
        return 2

    if args.tenant_id:
        targets = sorted(set(args.tenant_id))
    else:
        targets = sorted(p["id"] for p in OPERATOR_PROFILES)

    print(f"Target database : {args.db}")
    print(f"Project         : {settings.FIREBASE_PROJECT_ID}")
    print(f"Tenant scope    : {', '.join(targets)}")
    print(f"Include users   : {args.include_users}")

    if args.include_users:
        print("Protected (kept): smd@caanepal.gov.np, super-admin-001, system, SUPER_ADMIN")
    if not args.tenant_id:
        if not _confirm(
            "This will wipe ALL seed-created test tenants in this database "
            f"({', '.join(targets)}). Continue?", args.yes
        ):
            print("Aborted.")
            return 1

    initialize_firebase()

    from app.firebase import get_auth, get_db
    db = get_db()
    auth = get_auth()

    totals = {"tenants": 0, "docs": 0, "caps": 0, "users": 0, "protected_skipped": 0}
    for tid in targets:
        tenant_ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tid)
        print(f"\n== Unseeding {tid} ==")
        removed = _delete_tenant_docs(db, tenant_ref)
        totals["docs"] += sum(removed.values()) - removed.get("caps", 0)
        totals["caps"] += removed.get("caps", 0)

        if tenant_ref.get().exists:
            tenant_ref.delete()
            print(f"  deleted tenant document {tid}")
        else:
            print(f"  tenant document {tid} already absent")
        totals["tenants"] += 1

        if args.include_users:
            users = _delete_tenant_users(db, auth, tid)
            totals["users"] += users["users"]
            totals["protected_skipped"] += users["protected_skipped"]

    print("\nUnseed complete:")
    print(f"  tenants wiped : {totals['tenants']}")
    print(f"  docs deleted  : {totals['docs']} (+ {totals['caps']} caps)")
    print(f"  users deleted : {totals['users']} (protected skipped: {totals['protected_skipped']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
