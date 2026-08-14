"""Backfill: create a hazard for every report that has no linked hazard.

Each unlinked report gets an auto-created hazard (same logic as the live
POST /api/reports flow, _auto_create_hazard_from_report) with source_id set
to the report's id so the 1:1 report <-> hazard linkage is restored.

Usage:
  python backend/scripts/backfill_hazards.py [--database sms-db-beta]
      [--tenant tara-air --tenant sita-air] [--all] [--dry-run]

  --all        run for every operator tenant (default when no --tenant given)
  --dry-run    print what would be created without writing anything
"""
import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from dotenv import load_dotenv
load_dotenv(override=False)

from firebase_admin import credentials, firestore
import firebase_admin

DEFAULT_DB = "sms-db-beta"
OPERATORS = [
    "sita-air", "yeti-airlines", "summit-air", "simrik-air",
    "buddha-air", "air-dynasty", "tara-air",
]


def parse_args(argv):
    out = {"database": DEFAULT_DB, "tenants": [], "all": False, "dry_run": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--database" and i + 1 < len(argv):
            out["database"] = argv[i + 1]
            i += 2
        elif a == "--tenant" and i + 1 < len(argv):
            out["tenants"].append(argv[i + 1])
            i += 2
        elif a == "--all":
            out["all"] = True
            i += 1
        elif a == "--dry-run":
            out["dry_run"] = True
            i += 1
        else:
            i += 1
    return out


def main():
    args = parse_args(sys.argv[1:])
    db_id = args["database"]
    os.environ["FIREBASE_DATABASE_ID"] = db_id

    tenants = args["tenants"] if args["tenants"] else (OPERATORS if args["all"] else OPERATORS)
    if not tenants:
        print("No tenants selected.")
        return

    creds = credentials.Certificate({
        "type": "service_account",
        "project_id": os.environ.get("FIREBASE_PROJECT_ID"),
        "private_key": os.environ.get("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n"),
        "client_email": os.environ.get("FIREBASE_CLIENT_EMAIL"),
        "token_uri": os.environ.get("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
    })
    if not firebase_admin._apps:
        firebase_admin.initialize_app(creds)
    app = firebase_admin.get_app()
    db = firestore.client(app=app, database_id=db_id)

    import app.firebase as fb
    fb._db = db
    fb._firebase_app = app

    from app.routes.reports import _auto_create_hazard_from_report

    print(f"database={db_id} dry_run={args['dry_run']} tenants={tenants}\n")

    for tid in tenants:
        ten = db.collection("tenants").document(tid)
        reports = list(ten.collection("reports").stream())
        hazards = list(ten.collection("hazards").stream())
        linked = {h.to_dict().get("source_id") for h in hazards}
        linked.discard(None)

        pending = [r for r in reports if r.id not in linked]
        print(f"{tid}: reports={len(reports)} | hazards={len(hazards)} | "
              f"already_linked={len(reports) - len(pending)} | to_create={len(pending)}")

        if args["dry_run"]:
            continue

        created = errors = 0
        for rep in pending:
            d = rep.to_dict()
            stored = {
                "id": rep.id,
                "tenant_id": tid,
                "report_type": d.get("report_type"),
                "narrative": d.get("narrative", ""),
                "severity_level": d.get("severity_level"),
                "probability_level": d.get("probability_level"),
                "occurrence_category": d.get("occurrence_category"),
                "occurrence_type": d.get("occurrence_type"),
            }
            user = {"uid": d.get("created_by") or f"safety-{tid}-001"}
            try:
                _auto_create_hazard_from_report(stored, user)
                created += 1
                occ = d.get("occurrence_date")
                if occ:
                    refs = list(ten.collection("hazards").where("source_id", "==", rep.id).limit(1).get())
                    if refs:
                        refs[0].reference.update({"created_at": occ, "updated_at": occ})
            except Exception as e:
                errors += 1
                print(f"ERROR for {rep.id}: {e}")

        after = sum(1 for _ in ten.collection("hazards").stream())
        print(f"  created={created} | errors={errors} | total hazards now={after}")

    print("\nBackfill complete.")


if __name__ == "__main__":
    main()
