#!/usr/bin/env python3
"""
Fix Summit Air login failure for the local Docker demo (sms-db).

Context
-------
The demo frontend runs on http://localhost:5005 (firebase serve) against the
beta Firebase project `aerosafety-sms-prod` and the named Firestore database
`sms-db`. The user `safety@summitair.com` / `SUMMIT-Safety-2026` is the
canonical Summit Air Safety Manager account from the simplified credential
scheme (`seed/config.py` — CODE=SUMMIT, role=safety). If the beta database
was never seeded or Firebase Auth was wiped, Firebase returns
"Invalid email or password".

This script idempotently creates or updates that user in
`sms-db` (project `aerosafety-sms-prod`) and verifies the password via
the Identity Toolkit REST API — the same path the web app uses.

Usage (from repository root or backend/)
-----------------------------------------
  # With backend/.env.demo populated (recommended — same secrets as the demo)
  python backend/scripts/fix_summit_air_user.py

  # Or with an explicit service-account JSON
  GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json python backend/scripts/fix_summit_air_user.py

  # Dry-run (prints what would happen, no writes)
  python backend/scripts/fix_summit_air_user.py --dry-run

  # Also seed the Summit Air tenant doc if missing
  python backend/scripts/fix_summit_air_user.py --ensure-tenant

Requires:  backend/.env.demo  (FIREBASE_* + FIREBASE_DATABASE_ID=sms-db)

Alternative: Firebase CLI
--------------------------
  firebase auth:import users.json --project aerosafety-sms-prod
  # where users.json contains the exported user (see Firebase docs).

Alternative: one-shot Admin SDK snippet
----------------------------------------
  import firebase_admin
  from firebase_admin import credentials, auth
  cred = credentials.Certificate("path/to/sa.json")
  firebase_admin.initialize_app(cred)
  try:
      u = auth.get_user_by_email("safety@summitair.com")
      auth.update_user(u.uid, password="SUMMIT-Safety-2026")
  except auth.UserNotFoundError:
      auth.create_user(uid="safety-summit-air-001",
                       email="safety@summitair.com",
                       password="SUMMIT-Safety-2026",
                       display_name="Safety Manager (Summit Air)",
                       email_verified=True)
      auth.set_custom_user_claims("safety-summit-air-001",
                                   {"role": "AIRLINE_ADMIN", "tenant_id": "summit-air"})
"""

import argparse
import os
import sys
from pathlib import Path

# Resolve repo + backend paths before importing app.*
REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
for p in (str(BACKEND), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Load backend/.env.demo explicitly when present so FIREBASE_DATABASE_ID
# resolves to sms-db even if backend/.env points at sms-db.
ENV_DEMO = BACKEND / ".env.demo"
if ENV_DEMO.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_DEMO, override=False)
    except Exception:
        pass

# Force beta database for this fix unless caller already set a value.
os.environ.setdefault("FIREBASE_DATABASE_ID", "sms-db")

TARGET_EMAIL = "safety@summitair.com"
TARGET_PASSWORD = "SUMMIT-Safety-2026"
TARGET_UID = "safety-summit-air-001"
TARGET_ROLE = "AIRLINE_ADMIN"
TARGET_TENANT = "summit-air"
TARGET_DISPLAY = "Safety Manager (Summit Air)"
FIREBASE_WEB_API_KEY = os.environ.get("FIREBASE_WEB_API_KEY") or "AIzaSyCdCtUuyOcUIoCBEaiWGbhp6_XwZKHsicc"


def ensure_tenant(db) -> None:
    """Create/update the summit-air tenant doc if absent (idempotent)."""
    from seed.config import OPERATOR_PROFILES  # lazy import after path setup
    from seed.operators import create_tenant

    profile = next((p for p in OPERATOR_PROFILES if p["id"] == TARGET_TENANT), None)
    if not profile:
        print(f"[WARN] No OPERATOR_PROFILES entry for {TARGET_TENANT}; skipping tenant ensure.")
        return
    create_tenant(db, profile)
    print(f"[OK] Tenant '{TARGET_TENANT}' ensured in Firestore (database=sms-db).")


def fix_user(dry_run: bool = False, ensure_tenant_flag: bool = False) -> int:
    from app.firebase import initialize_firebase, get_auth, get_db
    from app.core.config import settings

    print(f"Target project : {settings.FIREBASE_PROJECT_ID or '(from env)'}")
    print(f"Target database: {settings.FIREBASE_DATABASE_ID}")
    print(f"Target user    : {TARGET_EMAIL} ({TARGET_UID}) / {TARGET_ROLE} @ {TARGET_TENANT}")

    if dry_run:
        print("\n[DRY RUN] Would create/update the user above and set custom claims.")
        print(f"[DRY RUN] Password would be set to: {TARGET_PASSWORD}")
        return 0

    initialize_firebase()
    auth = get_auth()
    db = get_db()

    # --- Auth: create or update ---
    try:
        existing = auth.get_user_by_email(TARGET_EMAIL)
        uid = existing.uid
        # Email exists but maybe on a different UID than the canonical one.
        # Always normalize to TARGET_UID's claims and reset password.
        if uid != TARGET_UID:
            print(f"[INFO] User exists with uid={uid} (expected {TARGET_UID}); updating that record.")
        auth.update_user(uid, password=TARGET_PASSWORD, email_verified=True, display_name=TARGET_DISPLAY)
        print(f"[OK] Updated password for {TARGET_EMAIL} (uid={uid})")
    except Exception as e:
        # firebase_admin.auth.UserNotFoundError is the common case
        msg = str(e).lower()
        if "not found" in msg or "no user" in msg or "usernotfound" in type(e).__name__.lower():
            print(f"[INFO] User {TARGET_EMAIL} not found — creating.")
            try:
                user = auth.create_user(
                    uid=TARGET_UID,
                    email=TARGET_EMAIL,
                    password=TARGET_PASSWORD,
                    display_name=TARGET_DISPLAY,
                    email_verified=True,
                )
                uid = user.uid
                print(f"[OK] Created user {TARGET_EMAIL} (uid={uid})")
            except Exception as ce:
                # UID collision but email free, or vice versa — try email lookup again
                print(f"[WARN] create_user failed: {ce}; trying update by email.")
                existing = auth.get_user_by_email(TARGET_EMAIL)
                uid = existing.uid
                auth.update_user(uid, password=TARGET_PASSWORD, email_verified=True)
                print(f"[OK] Updated password for {TARGET_EMAIL} (uid={uid}) via fallback")
        else:
            print(f"[ERROR] get_user_by_email failed: {e}")
            return 2

    # --- Custom claims ---
    try:
        auth.set_custom_user_claims(uid, {"role": TARGET_ROLE, "tenant_id": TARGET_TENANT})
        print(f"[OK] Custom claims set: role={TARGET_ROLE}, tenant_id={TARGET_TENANT}")
    except Exception as e:
        print(f"[ERROR] set_custom_user_claims failed: {e}")
        return 2

    # --- Tenant doc (optional) ---
    if ensure_tenant_flag:
        try:
            ensure_tenant(db)
        except Exception as e:
            print(f"[WARN] ensure_tenant failed: {e}")

    # --- Verify via Identity Toolkit REST (same as web login) ---
    try:
        import requests
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_WEB_API_KEY}"
        resp = requests.post(url, json={"email": TARGET_EMAIL, "password": TARGET_PASSWORD, "returnSecureToken": True}, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            print(f"[OK] REST login verified for {TARGET_EMAIL} (idToken issued, uid={data.get('localId','?')})")
        else:
            print(f"[FAIL] REST login for {TARGET_EMAIL} returned {resp.status_code}: {resp.text[:400]}")
            return 1
    except Exception as e:
        print(f"[WARN] REST verification skipped (no network/requests): {e}")

    print("\nDone. Try logging in at http://localhost:5005/login.html with:")
    print(f"  Email:    {TARGET_EMAIL}")
    print(f"  Password: {TARGET_PASSWORD}")
    print("If you use the local Docker backend, set once in the browser console:")
    print("  localStorage.setItem('aviasafe:localApiBaseUrl','http://localhost:8000')")
    return 0


def fix_all_users(dry_run: bool = False) -> int:
    """Idempotently create/update ALL operator demo accounts (48 + CAAN) via seed."""
    from app.firebase import initialize_firebase, get_auth
    from app.core.config import settings
    from seed.config import build_simplified_role_plan
    from seed.users import create_user

    print(f"Target project : {settings.FIREBASE_PROJECT_ID or '(from env)'}")
    print(f"Target database: {settings.FIREBASE_DATABASE_ID}")
    if dry_run:
        plan = build_simplified_role_plan()
        print(f"[DRY RUN] Would create/update {len(plan)} operator accounts + CAAN/DEV")
        for p in plan:
            print(f"  [DRY RUN] {p['email']:35} {p['password']:20} {p['uid']}")
        return 0

    initialize_firebase()
    auth = get_auth()
    # Delegate to the canonical seeder (users-only) — it handles DEMO_USERS + OPERATOR_PROFILES
    from seed.users import create_all_users
    created = create_all_users(auth)
    print(f"[OK] Ensured {len(created)} Auth users (roles + custom claims)")

    # Verify summit as representative
    try:
        import requests
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_WEB_API_KEY}"
        resp = requests.post(url, json={"email": TARGET_EMAIL, "password": TARGET_PASSWORD, "returnSecureToken": True}, timeout=15)
        if resp.status_code == 200:
            print(f"[OK] REST login verified for {TARGET_EMAIL}")
        else:
            print(f"[WARN] REST login for {TARGET_EMAIL} returned {resp.status_code}: {resp.text[:300]}")
    except Exception as e:
        print(f"[WARN] REST verification skipped: {e}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fix Summit Air demo user(s) in sms-db")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    parser.add_argument("--ensure-tenant", action="store_true", help="Also ensure the summit-air tenant doc exists")
    parser.add_argument("--all", dest="all_users", action="store_true", help="Fix ALL demo accounts (48 operators + CAAN), not just Summit Air")
    args = parser.parse_args(argv)
    if args.all_users:
        return fix_all_users(dry_run=args.dry_run)
    return fix_user(dry_run=args.dry_run, ensure_tenant_flag=args.ensure_tenant)


if __name__ == "__main__":
    sys.exit(main())
