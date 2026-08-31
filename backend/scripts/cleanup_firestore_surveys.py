# ============================================================================
# FILE: cleanup_firestore_surveys.py
# PATH: backend/scripts/cleanup_firestore_surveys.py
# PURPOSE: One-time purge of the legacy Firestore survey collections so
#          Supabase PostgreSQL is the exclusive source of truth for survey
#          data. After the dashboard analytics migrated to the `surveys` and
#          `survey_responses` Postgres tables (Path A), the old Firestore
#          `tenants/{id}/surveys` and `tenants/{id}/responses` collections /
#          collection groups are no longer consumed by any dashboard or the
#          live API — this script removes any remaining historical docs.
#
# Usage (from backend/):
#   python scripts/cleanup_firestore_surveys.py --dry-run
#   python scripts/cleanup_firestore_surveys.py --yes
#
# Defaults to the configured production database (FIREBASE_DATABASE_ID from
# backend/.env). Override if needed:
#   FIREBASE_DATABASE_ID=sms-db python scripts/cleanup_firestore_surveys.py --yes
# ============================================================================

import argparse
import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BACKEND, ".env"), override=False)

from app.firebase import initialize_firebase, get_db  # noqa: E402

CHUNK_SIZE = 400  # Firestore batch() caps at 500 writes per commit


def _delete_group(db, collection_name: str, dry_run: bool) -> int:
    """Delete every doc under the `collection_name` collection group.

    Streams all matched docs (any tenant's `{collection_name}` subcollection),
    deletes by document path in bounded batches, and returns the count.
    """
    total = 0
    docs = list(db.collection_group(collection_name).stream())
    if not docs:
        print(f"  {collection_name}: no docs found")
        return 0

    print(f"  {collection_name}: {len(docs)} doc(s) matched")
    if dry_run:
        for d in docs[:20]:
            print(f"    would delete  {d.reference.path}")
        if len(docs) > 20:
            print(f"    ... and {len(docs) - 20} more")
        return len(docs)

    for start in range(0, len(docs), CHUNK_SIZE):
        chunk = docs[start : start + CHUNK_SIZE]
        batch = db.batch()
        for d in chunk:
            batch.delete(d.reference)
        try:
            batch.commit()
            total += len(chunk)
            print(f"    deleted {start + len(chunk)}/{len(docs)}")
        except Exception as e:  # noqa: BLE001
            print(f"    FAILED to commit chunk {start}: {e}")
    return total


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Purge the legacy Firestore surveys / responses collections.",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="List docs that would be deleted without deleting.")
    parser.add_argument("--yes", action="store_true",
                        help="Skip the interactive confirmation.")
    args = parser.parse_args(argv)

    if not args.yes and not args.dry_run:
        print("Refusing to delete survey collections without --yes "
              "(or use --dry-run first).")
        return 2

    initialize_firebase()
    db = get_db()
    print(f"Targeting database: {db._database_id if hasattr(db, '_database_id') else 'unknown'}")
    print("Purge scope: collection groups 'surveys' and 'responses'")

    for collection_name in ("surveys", "responses"):
        _delete_group(db, collection_name, args.dry_run)

    if args.dry_run:
        print("\nDry-run complete — no documents were deleted.")
    else:
        print("\nCleanup complete. Supabase PostgreSQL is the source of truth "
              "for survey data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())