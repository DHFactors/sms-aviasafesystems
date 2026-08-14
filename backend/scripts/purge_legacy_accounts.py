#!/usr/bin/env python3
"""
Purge legacy operator user accounts (safety.*, ae.*, manager.*) from
sms-db-beta Firebase Auth + Firestore /users.

Since 2026-08-14 the seed provisions ONLY the four simplified role accounts per
tenant (safety@, 145@, camo@, ops@). This removes the old sm-/ae-/mgr- accounts
that the earlier seed created.

Targets (never touches CAAN SMD, SUPER_ADMIN, or simplified role accounts):
  - Auth records whose UID matches ^(sm|ae|mgr)-<tenant>-001$
  - Auth records whose email matches ^(safety|ae|manager)\.
  - Firestore /users documents whose id matches ^(sm|ae|mgr)-

Usage:
    $env:FIREBASE_DATABASE_ID='sms-db-beta'
    python backend/scripts/purge_legacy_accounts.py --dry-run
    python backend/scripts/purge_legacy_accounts.py
"""

import argparse
import os
import re
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

AUTH_UID_RE = re.compile(r"^(sm|ae|mgr)-[a-z-]+-001$")
AUTH_EMAIL_RE = re.compile(r"^(safety|ae|manager)\.")
FS_DOC_RE = re.compile(r"^(sm|ae|mgr)-")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from app.firebase import initialize_firebase, get_auth, get_db

    initialize_firebase()
    auth = get_auth()
    db = get_db()

    auth_records = list(auth.list_users().iterate_all())
    auth_targets = [
        u for u in auth_records
        if (u.email and AUTH_EMAIL_RE.match(u.email))
        or (u.uid and AUTH_UID_RE.match(u.uid))
    ]
    auth_targets.sort(key=lambda u: u.uid)

    fs_docs = list(db.collection("users").stream())
    fs_targets = [d for d in fs_docs if FS_DOC_RE.match(d.id)]
    fs_targets.sort(key=lambda d: d.id)

    print(f"Auth records: {len(auth_records)}")
    print(f"  legacy to purge: {len(auth_targets)}")
    for u in auth_targets:
        print(f"    auth  {u.uid}  {u.email}")
    print(f"Firestore /users docs: {len(fs_docs)}")
    print(f"  legacy to purge: {len(fs_targets)}")
    for d in fs_targets:
        data = d.to_dict() or {}
        print(f"    fs    {d.id}  {data.get('email')}")

    if args.dry_run:
        print("\nDRY RUN — nothing deleted")
        return

    for u in auth_targets:
        try:
            auth.delete_user(u.uid)
            print(f"deleted auth {u.uid} {u.email}")
        except Exception as e:
            print(f"FAILED auth {u.uid}: {e}")

    for d in fs_targets:
        try:
            d.reference.delete()
            print(f"deleted fs {d.id}")
        except Exception as e:
            print(f"FAILED fs {d.id}: {e}")

    print(f"\nPurged {len(auth_targets)} auth + {len(fs_targets)} firestore legacy accounts")


if __name__ == "__main__":
    main()