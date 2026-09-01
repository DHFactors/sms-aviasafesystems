# ============================================================================
# FILE: wipe_tenant_data.py
# PATH: backend/scripts/wipe_tenant_data.py
# PURPOSE: Wipe ALL tenant-related data from Firestore and Firebase Auth while
#          preserving the Super Admin account.
#
# Deletes:
#   Firestore:
#     * every document in the `tenants` collection, including all
#       subcollections under each tenant (responses, hazards, reports, cans,
#       caps, surveys, spis, flight_diversions, sms_maturity, metadata, ...)
#     * every document in the `regulators` collection
#     * demo seed markers (seed_metadata/seed, admin_seed, ...)
#   Firebase Auth:
#     * every user EXCEPT the Super Admin (ezondiza.dhf@gmail.com)
#     * the users/{uid} mirrors for deleted users
#
# Safety:
#   * explicit confirmation + environment confirmation required
#   * aborts (without deleting anything) if the Super Admin cannot be found
#   * logs every deletion to a timestamped audit file under backend/scripts/logs
#   * safe to run repeatedly (skips non-existent docs / users)
#
# Usage (from backend/):
#   python scripts/wipe_tenant_data.py
#   python scripts/wipe_tenant_data.py --yes
# ============================================================================

import argparse
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"), override=False)

SUPER_ADMIN_EMAIL = "ezondiza.dhf@gmail.com"

# Only the Super Admin is preserved. Every other account is deleted.
PROTECTED_EMAILS = {SUPER_ADMIN_EMAIL}
PROTECTED_UIDS = set()
PROTECTED_ROLES = set()

# Seed / marker document paths that are NOT under a tenant. Deleted as part of
# the Firestore wipe.
TOP_LEVEL_MARKER_PATHS = [
    ("seed_metadata", "seed"),
    ("admin_seed", None),
]

LOG_DIR = os.path.join(ROOT, "scripts", "logs")


def _confirm(prompt: str, yes: bool) -> bool:
    if yes:
        return True
    try:
        reply = input(f"{prompt} (yes/no) ")
    except EOFError:
        print("No interactive terminal; re-run with --yes to skip confirmation.")
        return False
    return reply.strip().lower() in {"yes", "y"}


def _is_protected(uid=None, email=None, role=None) -> bool:
    return (
        (uid and uid in PROTECTED_UIDS)
        or (email and email in PROTECTED_EMAILS)
        or (role and role in PROTECTED_ROLES)
    )


def _ensure_log_file() -> str:
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(LOG_DIR, f"wipe_tenant_data_{ts}.log")
    open(path, "a", encoding="utf-8").close()
    return path


class AuditLogger:
    def __init__(self, path: str):
        self.path = path
        self.lines = []
        self._header()

    def _header(self):
        self.write(f"=== aviaSDCPS tenant data wipe ===")
        self.write(f"timestamp : {datetime.now(timezone.utc).isoformat()}")
        self.write(f"project   : {os.environ.get('FIREBASE_PROJECT_ID', '?')}")
        self.write(f"database  : {os.environ.get('FIREBASE_DATABASE_ID', 'sms-db')}")

    def write(self, line: str):
        self.lines.append(line)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def close(self):
        self.write("=== end audit log ===")


def _delete_collection(collection_ref, audit: AuditLogger, path_label: str) -> int:
    """Delete every doc in a top-level-ish collection, recursing into
    subcollections of each doc so nested data is removed first."""
    count = 0
    try:
        snapshots = list(collection_ref.stream())
    except Exception as e:
        audit.write(f"  ! failed to scan {path_label}: {e}")
        print(f"  ! failed to scan {path_label}: {e}")
        return 0
    for snap in snapshots:
        for sub in snap.reference.collections():
            child_label = f"{path_label}/{snap.id}"
            count += _delete_collection(sub, audit, f"{child_label}/{sub.id}")
        try:
            snap.reference.delete()
            count += 1
            audit.write(f"  deleted {path_label}/{snap.id}")
            print(f"  deleted {path_label}/{snap.id}")
        except Exception as e:
            audit.write(f"  ! failed to delete {path_label}/{snap.id}: {e}")
            print(f"  ! failed to delete {path_label}/{snap.id}: {e}")
    return count


def _wipe_tenants(db, audit: AuditLogger) -> dict:
    print("\n── Listing tenants ──")
    collection = db.collection("tenants")
    try:
        snapshots = list(collection.stream())
    except Exception as e:
        audit.write(f"! failed to list tenants: {e}")
        print(f"! failed to list tenants: {e}")
        return {"tenants": 0, "docs": 0}

    print(f"  found {len(snapshots)} tenant document(s)")
    for snap in snapshots:
        print(f"    - {snap.id}")

    tenants = 0
    docs = 0
    for snap in snapshots:
        print(f"\n  wiping tenant {snap.id} ...")
        tenant_docs = 0
        for sub in snap.reference.collections():
            tenant_docs += _delete_collection(
                sub, audit, f"tenants/{snap.id}/{sub.id}"
            )
        tenants += 1
        docs += tenant_docs
        try:
            snap.reference.delete()
            audit.write(f"  deleted tenants/{snap.id} (document)")
            print(f"  deleted tenant document tenants/{snap.id}")
        except Exception as e:
            audit.write(f"  ! failed to delete tenants/{snap.id}: {e}")
            print(f"  ! failed to delete tenants/{snap.id}: {e}")
    return {"tenants": tenants, "docs": docs}


def _wipe_regulators(db, audit: AuditLogger) -> int:
    print("\n── Listing regulators ──")
    collection = db.collection("regulators")
    try:
        snapshots = list(collection.stream())
    except Exception as e:
        audit.write(f"! failed to list regulators: {e}")
        print(f"! failed to list regulators: {e}")
        return 0
    print(f"  found {len(snapshots)} regulator document(s)")
    for snap in snapshots:
        print(f"    - {snap.id}")
        _delete_collection(
            snap.reference, audit, f"regulators/{snap.id}"
        )
        try:
            snap.reference.delete()
            audit.write(f"  deleted regulators/{snap.id}")
            print(f"  deleted regulators/{snap.id}")
        except Exception as e:
            audit.write(f"  ! failed to delete regulators/{snap.id}: {e}")
            print(f"  ! failed to delete regulators/{snap.id}: {e}")
    return len(snapshots)


def _wipe_markers(db, audit: AuditLogger) -> int:
    print("\n── Cleaning demo seed markers ──")
    count = 0
    for coll, doc_id in TOP_LEVEL_MARKER_PATHS:
        ref = db.collection(coll)
        try:
            if doc_id is None:
                snapshots = list(ref.stream())
                for snap in snapshots:
                    _delete_collection(
                        snap.reference, audit, f"{coll}/{snap.id}"
                    )
                    try:
                        snap.reference.delete()
                        audit.write(f"  deleted {coll}/{snap.id}")
                        print(f"  deleted {coll}/{snap.id}")
                        count += 1
                    except Exception as e:
                        audit.write(f"  ! failed to delete {coll}/{snap.id}: {e}")
            else:
                doc = ref.document(doc_id)
                if doc.get().exists:
                    _delete_collection(doc, audit, f"{coll}/{doc_id}")
                    doc.delete()
                    audit.write(f"  deleted {coll}/{doc_id}")
                    print(f"  deleted {coll}/{doc_id}")
                    count += 1
        except Exception as e:
            audit.write(f"  ! failed to clean marker {coll}/{doc_id or '<collection>'}: {e}")
            print(f"  ! failed to clean marker {coll}/{doc_id}: {e}")
    return count


def _find_super_admin(auth):
    """Return (auth record, custom_claims) for the Super Admin, else None."""
    try:
        user = auth.get_user_by_email(SUPER_ADMIN_EMAIL)
        return user, (user.custom_claims or {})
    except Exception:
        return None, None


def _wipe_auth_users(auth, db, audit: AuditLogger) -> dict:
    print("\n── Listing Firebase Auth users ──")
    users = []
    page_token = None
    while True:
        try:
            page = auth.list_users(max_results=1000, page_token=page_token)
        except Exception as e:
            audit.write(f"! failed to list auth users: {e}")
            print(f"! failed to list auth users: {e}")
            break
        users.extend(page.users)
        page_token = page.next_page_token
        if not page_token:
            break

    print(f"  found {len(users)} user(s)")
    for u in users:
        claims = u.custom_claims or {}
        print(f"    - {u.email} (uid={u.uid}, role={claims.get('role')})")

    deleted = 0
    protected = 0
    for u in users:
        claims = u.custom_claims or {}
        if _is_protected(uid=u.uid, email=u.email, role=claims.get("role")):
            print(f"  SKIPPED protected account: {u.email} (uid={u.uid}, role={claims.get('role')})")
            audit.write(f"  SKIPPED protected account {u.email} (uid={u.uid})")
            protected += 1
            continue
        try:
            db.collection("users").document(u.uid).delete()
        except Exception:
            pass
        try:
            auth.delete_user(u.uid)
            audit.write(f"  deleted auth user {u.email} (uid={u.uid}, claims={claims})")
            print(f"  deleted auth user {u.email} (uid={u.uid})")
            deleted += 1
        except Exception as e:
            audit.write(f"  ! failed to delete auth user {u.email} (uid={u.uid}): {e}")
            print(f"  ! failed to delete auth user {u.email} (uid={u.uid}): {e}")
    return {"users": deleted, "protected": protected}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Wipe ALL tenant data from Firestore + Firebase Auth, "
                    "preserving the Super Admin account.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--yes", action="store_true",
                        help="Skip interactive confirmations.")
    args = parser.parse_args(argv)

    from app.core.config import settings
    from app.firebase import initialize_firebase

    environment = settings.ENVIRONMENT
    project = settings.FIREBASE_PROJECT_ID or "?"
    database = settings.FIREBASE_DATABASE_ID

    print("=" * 70)
    print("  aviaSDCPS Tenant Data Wipe")
    print("=" * 70)
    print(f"  Environment : {environment}")
    print(f"  Project     : {project}")
    print(f"  Database    : {database}")
    print(f"  Preserve    : {SUPER_ADMIN_EMAIL} (SUPER_ADMIN)")
    print("=" * 70)

    if not _confirm(f"This is running on: {environment}. Continue?", args.yes):
        print("Aborted by user.")
        return 1

    initialize_firebase()

    from app.firebase import get_auth, get_db
    db = get_db()
    auth = get_auth()

    # ── Pre-flight safety check: Super Admin MUST exist ─────────────────────
    super_user, super_claims = _find_super_admin(auth)
    if super_user is None:
        print(f"\nABORT: Super Admin '{SUPER_ADMIN_EMAIL}' not found in Firebase "
              f"Auth. Refusing to wipe to prevent accidental lockout.")
        return 3
    super_role = (super_claims or {}).get("role")
    print(f"\n  Super Admin found: {SUPER_ADMIN_EMAIL} (uid={super_user.uid}, "
          f"role={super_role})")

    if not _confirm(f"Are you sure you want to wipe ALL tenant data? "
                    f"(found {super_user.uid} as Super Admin)", args.yes):
        print("Aborted by user.")
        return 1

    log_path = _ensure_log_file()
    audit = AuditLogger(log_path)

    try:
        tenants = _wipe_tenants(db, audit)
        regulator_count = _wipe_regulators(db, audit)
        marker_count = _wipe_markers(db, audit)
        users = _wipe_auth_users(auth, db, audit)
    finally:
        audit.close()

    print("\n" + "=" * 70)
    print("  Wipe complete. Summary:")
    print(f"    Tenants deleted   : {tenants['tenants']} (docs: {tenants['docs']})")
    print(f"    Regulators deleted: {regulator_count}")
    print(f"    Markers deleted   : {marker_count}")
    print(f"    Auth users deleted: {users['users']} (protected skipped: {users['protected']})")
    print(f"    Super Admin kept  : {SUPER_ADMIN_EMAIL} (role={super_role})")
    print(f"    Audit log         : {log_path}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
