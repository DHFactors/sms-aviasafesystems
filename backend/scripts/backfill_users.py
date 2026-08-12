# ============================================================================
# FILE: backfill_users.py
# PATH: backend/scripts/backfill_users.py
# PURPOSE: Backfill the Firestore `users` collection from Firebase Auth so the
#          tenant-scoped "Authorized Users" list works for existing accounts.
#
# Usage:
#   python scripts/backfill_users.py            # beta (sms-db-beta)
#   python scripts/backfill_users.py sms-db     # production
#   BACKFILL_DB=sms-db python scripts/backfill_users.py
#
# Run with the same backend/.env (service account) as the target environment.
# ============================================================================

import os
import sys

DB_ID = os.environ.get("BACKFILL_DB", sys.argv[1] if len(sys.argv) > 1 else "sms-db-beta")
os.environ["FIREBASE_DATABASE_ID"] = DB_ID

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from dotenv import load_dotenv
load_dotenv(override=False)

from firebase_admin import credentials, firestore
import firebase_admin

creds = credentials.Certificate({
    "type": "service_account",
    "project_id": os.environ.get("FIREBASE_PROJECT_ID"),
    "private_key": os.environ.get("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n"),
    "client_email": os.environ.get("FIREBASE_CLIENT_EMAIL"),
    "token_uri": os.environ.get("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
})

if not firebase_admin._apps:
    app = firebase_admin.initialize_app(creds)
else:
    app = firebase_admin.get_app()
db = firestore.client(app=app, database_id=DB_ID)

import app.firebase as fb
fb._db = db
fb._firebase_app = app

from app.services.users import backfill_users_from_auth, list_tenant_users

count = backfill_users_from_auth()
print(f"\nusers synced: {count} (database={DB_ID})")

for tid in ["buddha-air", "air-dynasty", "ktm-mro", "pokhara-aerodrome", "himalaya-ground-services"]:
    users = list_tenant_users(tid)
    print(f"\n[{tid}] {len(users)} authorized users:")
    for u in users:
        print(f"  - {u['email']} ({u['role']}) created={u['createdAt']}")
