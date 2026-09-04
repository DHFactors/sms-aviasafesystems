"""Migrate existing Firebase .test users to .com emails (in-place)."""
import os, io, sys
if os.name == "nt":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.abspath("."))

from app.core.config import settings  # noqa
from app.firebase import initialize_firebase, get_auth  # noqa

initialize_firebase()
auth = get_auth()

# Build the same list of uids as list_generic_users.py generated
uids = []
for tid in ("fixedwing", "rotarywing", "demoairport"):
    for token in ("ae", "safety", "camo", "145", "ops", "staff", "smd"):
        uids.append(f"{token}-{tid}-001")

errors = 0
successes = 0

for uid in uids:
    # Get current user to find their current email
    try:
        user = auth.get_user(uid)
        current_email = user.email
    except Exception as e:
        code = getattr(e, "code", type(e).__name__)
        print(f"  SKIP {uid}: user not found ({code})")
        errors += 1
        continue

    # Only migrate .test emails
    if not current_email.endswith(".test"):
        print(f"  SKIP {uid}: already {current_email}")
        successes += 1
        continue

    new_email = current_email.replace(".test", ".com")
    old_email = current_email

    try:
        # Update user email in Firebase Auth
        auth.update_user(uid, email=new_email)
        print(f"  MIGRATED {uid:24s}  {old_email:30s} -> {new_email}")
        successes += 1
    except Exception as e:
        print(f"  FAILED {uid:24s}  {old_email:30s} -> {new_email}: {str(e)[:120]}")
        errors += 1

# Re-generate the seeder's .com spec and re-run create_user to sync claims
# (The create_user function will re-apply role/tenant_id/department claims
# to ensure they're fresh after the email rename.)
from seed.users import create_user
from seed.seeder import _generic_user_spec, _GENERIC_ROLE_META, GENERIC_TENANT_CONFIG, GENERIC_TENANT_USERS, OPERATOR_PROFILES
from seed.config import roles_for_tenant

auth = get_auth()  # fresh auth handle

for uid in uids:
    try:
        create_user(auth, {"uid": uid, "password": None})  # re-apply claims
        print(f"  RE-CLAIMS synced for {uid}")
    except Exception as e:
        print(f"  RE-CLAIMS FAILED {uid}: {str(e)[:80]}")

# Summary
print(f"\n{'='*60}")
print(f"Migration Summary")
print(f"{'='*60}")
print(f"  Successes: {successes}")
print(f"  Errors:    {errors}")
print(f"  Total:     {len(uids)}")
if errors == 0:
    print("  All users migrated successfully.")
else:
    print(f"  {errors} failures — check output above.")
print(f"{'='*60}")

sys.exit(0 if errors == 0 else 1)