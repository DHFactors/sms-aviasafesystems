# ============================================================================
# FILE: purge_auth_pool.py
# PATH: backend/scripts/purge_auth_pool.py
# PURPOSE: One-time utility to purge a Firebase Auth user pool so a project can
#          be re-provisioned cleanly from the seed spec. Used to clear the
#          gap-analysis-ssp beta project of legacy / old-schema accounts before
#          re-running `python -m seed.deploy_seed --users-only`.
#
# Usage (from backend/):
#   python scripts/purge_auth_pool.py --dry-run
#   python scripts/purge_auth_pool.py --yes
# ============================================================================

import argparse
import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from app.firebase import initialize_firebase, get_auth


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Purge the Firebase Auth user pool.")
    parser.add_argument("--dry-run", action="store_true",
                        help="List users that would be deleted without deleting.")
    parser.add_argument("--yes", action="store_true",
                        help="Skip the interactive confirmation.")
    args = parser.parse_args(argv)

    if not args.yes and not args.dry_run:
        print("Refusing to delete users without --yes (or use --dry-run first).")
        return 2

    initialize_firebase()
    auth = get_auth()

    users = list(auth.list_users().iterate_all())
    print(f"Pool size: {len(users)}")

    if args.dry_run:
        for u in sorted(users, key=lambda r: (r.email or "").lower()):
            print(f"  would delete  {u.uid}  {u.email}")
        print(f"\nDry-run: {len(users)} user(s) would be deleted.")
        return 0

    deleted = 0
    for u in users:
        try:
            auth.delete_user(u.uid)
            deleted += 1
            print(f"  deleted  {u.uid}  {u.email}")
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED  {u.uid}  {u.email}: {e}")
    print(f"\nDeleted {deleted} user(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())