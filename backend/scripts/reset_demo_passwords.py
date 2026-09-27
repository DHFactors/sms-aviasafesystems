# ============================================================================
# FILE: reset_demo_passwords.py
# PATH: backend/scripts/reset_demo_passwords.py
# PURPOSE: Set ONE standard demo password on every demo-tenant Firebase Auth
#          account. Demo emails are unreachable (fake domains), so email-based
#          reset is useless; this script rotates them programmatically.
#
# RUN (from repo root):
#     python backend/scripts/reset_demo_passwords.py [--dry-run]
# RUN (from backend/):
#     python scripts/reset_demo_passwords.py [--dry-run]
# NOTE: `python -m scripts.reset_demo_passwords` does NOT work —
#       backend/scripts/ is intentionally not a package (no __init__.py).
#
# IDEMPOTENT: setting the same password twice is harmless; re-runnable.
# NEVER touches PROTECTED_EMAILS (SUPER_ADMIN / developer accounts).
# ============================================================================

import argparse
import os
import sys

# Make `app.*` importable regardless of cwd (repo root or backend/).
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# ----------------------------------------------------------------------------
# Single source of truth — change here if the operator requests a new password.
# ----------------------------------------------------------------------------
STANDARD_DEMO_PASSWORD = "AviaSafeDemo2026!"

# Accounts that MUST NEVER be reset (mirrors SUPER_ADMIN_PROTECTED_EMAILS
# in backend/app/routes/admin.py — keep the two lists in sync).
PROTECTED_EMAILS = frozenset({
    "ezondiza.dhf@gmail.com",
    "ghanshyamacharya@outlook.com",
})


def _canonical_demo_emails():
    """Hardcoded pilot-tenant emails — the canonical demo set."""
    from app.db.isolation import PERMANENT_PILOT_EMAILS
    return set(PERMANENT_PILOT_EMAILS)


def _pg_demo_emails():
    """Best-effort union source: emails of users rows in pilot tenants.

    The users table has no is_demo column; pilot tenants carry
    is_demo=FALSE by policy, so membership is resolved via the tenants
    slug list. Returns (emails, is_developer_emails). Raises on DB error
    so the caller can degrade to the hardcoded list.
    """
    from app.db import pg as pg_bridge
    from app.db.db_models import Tenant, UserProfile
    from app.db.isolation import PERMANENT_TENANT_SLUGS

    tenants = pg_bridge.fetch_all(Tenant)
    pilot_ids = {
        str(t.get("id"))
        for t in tenants
        if str(t.get("slug") or "").strip().lower() in PERMANENT_TENANT_SLUGS
    }
    emails, developers = set(), set()
    for u in pg_bridge.fetch_all(UserProfile):
        if str(u.get("tenant_id") or "") in pilot_ids and u.get("email"):
            emails.add(str(u["email"]).strip().lower())
            if u.get("is_developer"):
                developers.add(str(u["email"]).strip().lower())
    return emails, developers


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Reset all demo-tenant Firebase Auth passwords "
                    "to the standard demo password.")
    ap.add_argument("--dry-run", action="store_true",
                    help="List what WOULD be reset without changing anything.")
    args = ap.parse_args()

    targets = _canonical_demo_emails()
    pg_developers = set()
    try:
        pg_emails, pg_developers = _pg_demo_emails()
        targets |= pg_emails
        print(f"[info] Postgres union source added {len(pg_emails)} email(s).")
    except Exception as e:
        print(f"[warn] Postgres union source unavailable ({e}); "
              f"using hardcoded demo list only.")

    # Belt and suspenders: is_developer rows are never touched even if they
    # somehow land in a pilot tenant.
    protected = {e.lower() for e in PROTECTED_EMAILS} | pg_developers

    attempted = succeeded = skipped = errored = 0
    if args.dry_run:
        print("[dry-run] No passwords will be changed.")
    else:
        from app.firebase import get_auth
        auth = get_auth()

    for email in sorted(targets):
        attempted += 1
        if email.lower() in protected:
            print(f"[SKIP] {email} — protected account, never touched")
            skipped += 1
            continue
        if args.dry_run:
            print(f"[WOULD-RESET] {email}")
            continue
        try:
            user = auth.get_user_by_email(email)
        except Exception as e:
            if "UserNotFound" in type(e).__name__ or "not found" in str(e).lower():
                print(f"[SKIP] {email} — no such Firebase user")
                skipped += 1
            else:
                print(f"[ERR] {email} — lookup failed: {e}")
                errored += 1
            continue
        try:
            auth.update_user(user.uid, password=STANDARD_DEMO_PASSWORD)
            print(f"[OK] {email} — password reset")
            succeeded += 1
        except Exception as e:
            print(f"[ERR] {email} — {e}")
            errored += 1

    print("---- summary ----")
    print(f"attempted={attempted} succeeded={succeeded} "
          f"skipped={skipped} errored={errored}")
    return 0 if errored == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
