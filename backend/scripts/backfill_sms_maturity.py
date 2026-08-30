# ============================================================================
# FILE: backfill_sms_maturity.py
# PATH: backend/scripts/backfill_sms_maturity.py
# PURPOSE: Migrate stored survey docs from the legacy "SMS Health" field names
#          to the "SMS Maturity" field names after the full product rename.
#          - tenants/{id}/surveys: adds overall_sms_maturity / overallSMSMaturity
#            when only the legacy overall_sms_health / overallSMSHealth exist.
#            Legacy fields are kept (additive) so old consumers keep working.
#          - tenants/{id}/sms_health cache: deleted (disposable; regenerated
#            under the new sms_maturity collection on the next dashboard request).
#          Production sms-db is never touched unless SEED_DB=...
#
# Usage:
#   python scripts/backfill_sms_maturity.py            # beta (sms-db)
#   python scripts/backfill_sms_maturity.py sms-db
#   SEED_DB=sms-db python scripts/backfill_sms_maturity.py
# ============================================================================

import os
import sys

DB_ID = os.environ.get("SEED_DB", sys.argv[1] if len(sys.argv) > 1 else "sms-db")
os.environ["FIREBASE_DATABASE_ID"] = DB_ID

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND, ".env"), override=False)

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
    firebase_admin.initialize_app(creds)
db = firestore.client(app=firebase_admin.get_app(), database_id=DB_ID)

TENANTS = db.collection("tenants")


def backfill_tenant(tid: str) -> dict:
    tenant_ref = TENANTS.document(tid)
    updated_surveys = 0
    legacy_surveys = 0

    surveys = tenant_ref.collection("surveys").stream()
    for snap in surveys:
        data = snap.to_dict()
        old = data.get("overall_sms_health")
        old_camel = data.get("overallSMSHealth")
        new = data.get("overall_sms_maturity")
        new_camel = data.get("overallSMSMaturity")
        patch = {}
        if old is not None and new is None:
            patch["overall_sms_maturity"] = old
            legacy_surveys += 1
        if old_camel is not None and new_camel is None:
            patch["overallSMSMaturity"] = old_camel
        if patch:
            snap.reference.update(patch)
            updated_surveys += 1

    # Delete the legacy SMS-health assessment cache (disposable; regenerates
    # under the sms_maturity collection on the next dashboard request).
    deleted_cache = 0
    cache = tenant_ref.collection("sms_health").stream()
    for snap in cache:
        snap.reference.delete()
        deleted_cache += 1

    return {
        "tenant": tid,
        "surveys_updated": updated_surveys,
        "surveys_with_legacy": legacy_surveys,
        "legacy_cache_deleted": deleted_cache,
    }


def main():
    print(f"Backfilling SMS Maturity field names -> database={DB_ID}\n")
    total_surveys = 0
    total_cache = 0
    tenant_ids = [t.id for t in TENANTS.list_documents()]
    for tid in tenant_ids:
        r = backfill_tenant(tid)
        total_surveys += r["surveys_updated"]
        total_cache += r["legacy_cache_deleted"]
        print(f"  {r['tenant']}: surveys_updated={r['surveys_updated']} "
              f"(legacy={r['surveys_with_legacy']}) cache_deleted={r['legacy_cache_deleted']}")
    print(f"\nDone. {total_surveys} survey docs updated, {total_cache} legacy cache docs deleted "
          f"across {len(tenant_ids)} tenants.")


if __name__ == "__main__":
    main()
