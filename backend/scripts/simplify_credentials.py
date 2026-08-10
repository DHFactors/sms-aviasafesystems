#!/usr/bin/env python3
"""
Simplify user credentials to the 2026-08 scheme.

Email:    {role}@{tenant}.com            e.g. safety@buddha-air.com
Password: {TENANT_CODE}-{ROLE}-2026      e.g. BHA-Safety-2026

What this does per operator tenant (Buddha Air, Tara Air, Sita Air, Yeti
Airlines, Summit Air, Simrik Air, Air Dynasty):
  * Creates the four functional role accounts (safety, camo, 145, ops) using
    the simplified email + password format, as AIRLINE_ADMIN bound to the
    tenant. Accounts that already exist are updated in place (email, password,
    claims) rather than duplicated.
  * Leaves the legacy Safety Manager / Accountable Executive / Department
    Manager accounts untouched.
  * Removes the CAAN super-admin account (`super-admin-001`) from Auth and the
    mirrored Firestore `users` collection.

Firebase Auth is shared between the beta and production environments (same
project, `aerosafety-sms-prod`), so Auth changes apply once. The mirrored
Firestore `users` collection is refreshed per database — run once with
`sms-db-beta` and once with `sms-db`.

Usage:
    python scripts/simplify_credentials.py                 # dry-run (default)
    python scripts/simplify_credentials.py --apply         # make Auth changes
    python scripts/simplify_credentials.py --apply --db sms-db   # + backfill prod

The Firestore backfill targets the database in `--db` (default `sms-db-beta`)
and requires the same service-account `.env` as the target environment.
"""

import argparse
import os
import sys
from datetime import datetime, timezone

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from dotenv import load_dotenv
load_dotenv(override=False)

from firebase_admin import credentials as fb_credentials
import firebase_admin

from loguru import logger

logger.remove()
logger.add(sys.stdout, format="{time:HH:mm:ss} | {level:<7} | {message}", level="INFO")

from seed.config import (
    OPERATOR_PROFILES,
    SIMPLIFIED_ROLE_ACCOUNTS,
    simplified_email,
    simplified_password,
    CREDENTIAL_TENANT_CODES,
)

SUPER_ADMIN_UID = "super-admin-001"


def _bootstrap_firebase(db_id: str):
    from firebase_admin import auth, firestore

    if not firebase_admin._apps:
        app = firebase_admin.initialize_app(fb_credentials.Certificate({
            "type": "service_account",
            "project_id": os.environ.get("FIREBASE_PROJECT_ID"),
            "private_key": os.environ.get("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n"),
            "client_email": os.environ.get("FIREBASE_CLIENT_EMAIL"),
            "token_uri": os.environ.get("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
        }))
    else:
        app = firebase_admin.get_app()
    db = firestore.client(app=app, database_id=db_id)

    import app.firebase as fb
    fb._db = db
    fb._firebase_app = app
    return app, db


def _email_exists(auth, email: str) -> bool:
    try:
        auth.get_user_by_email(email)
        return True
    except Exception:
        return False


def build_plan():
    """Return the list of (op_id, role_spec) accounts the scheme defines."""
    plan = []
    for profile in OPERATOR_PROFILES:
        op_id = profile["id"]
        for role in SIMPLIFIED_ROLE_ACCOUNTS:
            plan.append({
                "op_id": op_id,
                "op_name": profile["name"],
                "token": role["token"],
                "email": simplified_email(role["token"], op_id),
                "password": simplified_password(role["token"], op_id),
                "app_role": role["app_role"],
                "full_name": f"{role['full_name']} ({profile['name']})",
                "uid": f"{role['token']}-{op_id}-001",
            })
    return plan


def dry_run(auth):
    print("=" * 78)
    print("DRY-RUN — no changes will be made")
    print("=" * 78)
    plan = build_plan()
    print(f"\nSimplified scheme accounts to ensure ({len(plan)}):\n")
    print(f"{'Tenant':<22}{'Role':<8}{'Email':<32}{'Password':<20}{'Status'}")
    print("-" * 100)
    for acc in plan:
        exists = _email_exists(auth, acc["email"])
        status = "EXISTS (will update)" if exists else "CREATE"
        print(f"{acc['op_name']:<22}{acc['token']:<8}{acc['email']:<32}{acc['password']:<20}{status}")

    # Super admin removal
    try:
        sa = auth.get_user(SUPER_ADMIN_UID)
        print(f"\nCAAN super-admin to remove: {SUPER_ADMIN_UID} "
              f"({sa.email}, role=SUPER_ADMIN)")
    except Exception:
        print(f"\nCAAN super-admin {SUPER_ADMIN_UID}: not present — nothing to remove")

    print("\nUnchanged: legacy Safety Manager / Accountable Executive / Dept Manager"
          " and CAAN SMD accounts.")
    print("WARNING: removing super-admin-001 disables SUPER_ADMIN access; verify a")
    print("replacement (e.g. a CAAN_SMD provisioned as SUPER_ADMIN) before apply.\n")
    return len(plan)


def apply_auth(auth):
    plan = build_plan()
    created = updated = 0
    print(f"Ensuring {len(plan)} simplified accounts...")
    for acc in plan:
        try:
            existing = auth.get_user(acc["uid"])
        except Exception:
            existing = None
        try:
            if existing is None:
                auth.create_user(
                    uid=acc["uid"],
                    email=acc["email"],
                    password=acc["password"],
                    display_name=acc["full_name"],
                    email_verified=True,
                )
                created += 1
                action = "created"
            else:
                auth.update_user(acc["uid"], email=acc["email"],
                                 password=acc["password"],
                                 display_name=acc["full_name"],
                                 email_verified=True)
                updated += 1
                action = "updated"
            auth.update_user(acc["uid"], custom_claims={
                "role": acc["app_role"], "tenant_id": acc["op_id"]})
            print(f"  [{action}] {acc['email']}  {acc['password']}")
        except Exception as e:
            logger.error(f"Failed {acc['email']}: {e}")

    # Remove CAAN super-admin
    try:
        sa = auth.get_user(SUPER_ADMIN_UID)
        auth.delete_user(SUPER_ADMIN_UID)
        print(f"\nRemoved CAAN super-admin: {SUPER_ADMIN_UID} ({sa.email})")
        removed = True
    except Exception:
        print(f"\nCAAN super-admin {SUPER_ADMIN_UID}: not present — nothing to remove")
        removed = False

    print(f"\nAuth done: {created} created, {updated} updated, super-admin removed={removed}")
    return {"created": created, "updated": updated, "super_admin_removed": removed}


def backfill_users(db):
    from app.services.users import backfill_users_from_auth
    from app.firebase import get_db, get_auth

    get_db()
    count = backfill_users_from_auth()
    print(f"\nFirestore `users` collection synced: {count} docs")
    return count


def main():
    parser = argparse.ArgumentParser(description="Simplify user credentials (2026-08 scheme)")
    parser.add_argument("--apply", action="store_true",
                        help="Make Auth changes (default is dry-run)")
    parser.add_argument("--db", default=os.environ.get("BACKFILL_DB", "sms-db-beta"),
                        help="Firestore database id for the users backfill (default sms-db-beta)")
    args = parser.parse_args()

    if not args.apply:
        from firebase_admin import auth as fb_auth

        # Dry-run still needs Auth to report existence, so bootstrap without
        # writing anything.
        _bootstrap_firebase(args.db)
        dry_run(fb_auth)
        sys.exit(0)

    app, db = _bootstrap_firebase(args.db)
    from firebase_admin import auth as fb_auth

    summary = apply_auth(fb_auth)
    backfill_users(db)

    print("\nNext: run with `--db sms-db` (production Firestore backfill) if this run "
          "targeted beta.")
    print(f"Done at {datetime.now(timezone.utc).isoformat()}: {summary}")


if __name__ == "__main__":
    main()
