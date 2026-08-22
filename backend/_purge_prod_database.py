"""One-time purge: wipe sms-db to a 100% virgin state.

DO NOT RUN THIS AGAINST sms-db-beta — this targets ONLY the Production database.
"""
import sys
from google.cloud import firestore

def purge_sms_db():
    confirm = input(
        "Are you ABSOLUTELY sure you want to wipe 'sms-db' to a virgin state? (type 'PURGE_SMS_DB'): "
    )
    if confirm != "PURGE_SMS_DB":
        print("Aborted.")
        sys.exit(0)

    db = firestore.Client(database="sms-db")
    collections = [
        "audit_logs",
        "psoe_assessments",
        "regulators",
        "seed_metadata",
        "tenants",
        "users",
    ]

    for coll_name in collections:
        coll_ref = db.collection(coll_name)
        docs = list(coll_ref.limit(500).stream())
        batch_count = 0
        while docs:
            batch = db.batch()
            for doc in docs:
                # Delete nested subcollections recursively if any
                for subcoll in doc.reference.collections():
                    for subdoc in subcoll.stream():
                        batch.delete(subdoc.reference)
                batch.delete(doc.reference)
                batch_count += 1
            try:
                batch.commit()
            except Exception as e:
                print(f"Error committing batch: {e}")
                sys.exit(1)
            print(f"  Purged batch of {batch_count} docs from {coll_name}...")
            docs = list(coll_ref.limit(500).stream())
        print(f"  Collection '{coll_name}' in sms-db is now empty. "
              f"Total docs removed: {batch_count}")
        batch_count = 0

    # Verify: list all collections and docs
    print("\n=== VERIFICATION ===")
    for coll_name in collections:
        docs = list(db.collection(coll_name).list_documents())
        print(f"  {coll_name}: {len(docs)} documents")
    print("\n✅ sms-db is now in a virgin state.")
    print("⚠️  sms-db-beta was NOT touched by this script.")

if __name__ == "__main__":
    purge_sms_db()