# ============================================================================
# FILE: deploy_seed.py
# PATH: backend/seed/deploy_seed.py
# PURPOSE: Safe wrapper around seed.runner.run() with an explicit database
#          override and confirmation gates. The default target is the beta
#          database (sms-db-beta); the production database (sms-db) is refused
#          unless --allow-production is passed explicitly.
#
# Usage (from backend/):
#   python -m seed.deploy_seed                          # full beta seed
#   python -m seed.deploy_seed --force
#   python -m seed.deploy_seed --dry-run
#   python -m seed.deploy_seed --tenant-id buddha-air --tenant-id air-dynasty
#   python -m seed.deploy_seed --tenant-id ktm-mro --force --dry-run
#   python -m seed.deploy_seed --surveys-only --tenant-id buddha-air
#   python -m seed.deploy_seed --db sms-db --allow-production   # do not do this
# ============================================================================

import argparse
import os
import sys
from getpass import getpass

BETA_DB_ID = "sms-db-beta"
PROD_DB_ID = "sms-db"


def _confirm(prompt: str, yes: bool) -> bool:
    if yes:
        return True
    try:
        reply = input(f"{prompt} [y/N] ")
    except EOFError:
        print("No interactive terminal; re-run with --yes to skip confirmation.")
        return False
    return reply.strip().lower() in {"y", "yes"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed the beta SMS database (or an explicit override).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--db", default=BETA_DB_ID,
                        help="Firestore database id to seed (default: beta).")
    parser.add_argument("--allow-production", action="store_true",
                        help="Permit targeting the production database (dangerous).")
    parser.add_argument("--tenant-id", action="append", default=None,
                        help="Restrict seeding to these operator tenants (repeatable). "
                             "When given, the CAAN regulator and state-risk reference "
                             "are left untouched.")
    parser.add_argument("--force", action="store_true",
                        help="Re-seed even if the current SEED_VERSION was already applied.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be seeded without writing anything.")
    parser.add_argument("--surveys-only", action="store_true",
                        help="Only (re)write survey responses.")
    parser.add_argument("--reports-only", action="store_true",
                        help="Only (re)write VSR/MOR reports and hazard/CAN/CAP data.")
    parser.add_argument("--users-only", action="store_true",
                        help="Only create/update Firebase Auth users.")
    parser.add_argument("--yes", action="store_true",
                        help="Skip interactive confirmations.")
    args = parser.parse_args(argv)

    if args.db == PROD_DB_ID and not args.allow_production:
        print("Refusing to seed the production database (sms-db).")
        print("If you really mean this, pass --allow-production.")
        return 2

    os.environ["FIREBASE_DATABASE_ID"] = args.db

    from app.core.config import settings
    from app.firebase import initialize_firebase
    from seed.config import SEED_VERSION

    if settings.FIREBASE_DATABASE_ID != args.db:
        print(f"ERROR: settings resolved to '{settings.FIREBASE_DATABASE_ID}' "
              f"but requested '{args.db}'.")
        return 2

    print(f"Target database : {args.db}")
    print(f"Project         : {settings.FIREBASE_PROJECT_ID}")
    print(f"Seed version    : {SEED_VERSION}")
    if args.tenant_id:
        print(f"Tenant scope    : {', '.join(sorted(set(args.tenant_id)))}")
    else:
        print("Tenant scope    : ALL (12 providers + CAAN state regulator)")
    if args.dry_run:
        print("Mode            : DRY RUN (no writes)")

    if not args.tenant_id and not args.dry_run:
        if not _confirm(
            "This will seed/write test data across ALL operator tenants in this "
            "database. Continue?", args.yes
        ):
            print("Aborted.")
            return 1

    if args.dry_run:
        from seed.runner import run
        counts = run(dry_run=True, tenant_ids=args.tenant_id)
        print("\nDry-run summary (what a real run would write):")
        for key, value in counts.items():
            print(f"  {key}: {value}")
        return 0

    initialize_firebase()

    from seed.runner import run
    counts = run(
        force=args.force,
        surveys_only=args.surveys_only,
        reports_only=args.reports_only,
        users_only=args.users_only,
        tenant_ids=args.tenant_id,
    )
    status = counts.get("status", "completed")
    print(f"\nSeed finished: {status}")
    if status != "skipped":
        for key, value in counts.items():
            if key in ("tenant_ids",):
                continue
            print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
