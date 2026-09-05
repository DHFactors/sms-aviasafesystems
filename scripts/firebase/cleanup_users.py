"""Inventory and clean up Firebase Auth users + Firestore user records.

Runs against the environment in backend/.env (production by default).

Modes:
  --inventory     (default) list every Auth user and every Firestore users doc. Read-only.
  --rename OLD NEW
                  rename the Auth user email from OLD to NEW (same uid, claims preserved).
  --dry-run       same as --apply but reports what WOULD be deleted without touching anything.
  --apply         delete every Auth user NOT in KEEP_EMAILS, and their Firestore users doc.

The Firestore `users` collection is keyed by UID (see wipe_tenant_data.py). For safety,
a users doc is matched for deletion by (a) doc id == uid, (b) doc field email == uid's email,
or (c) doc id == the user's email. Tenant data is never touched.

Usage:
  python scripts/firebase/cleanup_users.py --inventory
  python scripts/firebase/cleanup_users.py --rename regulator@demo.com safety@demostate.com
  python scripts/firebase/cleanup_users.py --dry-run
  python scripts/firebase/cleanup_users.py --apply
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import firebase_admin
from firebase_admin import credentials, auth, firestore

KEEP_EMAILS = {
    "ezondiza.dhf@gmail.com",
    "safety@demostate.com",
    "safety@demoairport.com",
    "safety@fixedwing.com",
    "safety@rotarywing.com",
}


def load_env():
    env = {}
    for line in (ROOT / "backend" / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
            v = v[1:-1]
        env[k.strip()] = v.strip()
    return env


def get_app(env):
    cred = credentials.Certificate({
        "type": "service_account",
        "project_id": env["FIREBASE_PROJECT_ID"],
        "private_key": env["FIREBASE_PRIVATE_KEY"].replace("\\n", "\n"),
        "client_email": env["FIREBASE_CLIENT_EMAIL"],
        "token_uri": env.get("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
    })
    return firebase_admin.initialize_app(cred)


def collect(env):
    app = get_app(env)
    db = firestore.client(app, database_id="sms-db")

    auth_users = []
    for u in auth.list_users().iterate_all():
        auth_users.append({
            "uid": u.uid,
            "email": u.email,
            "display_name": u.display_name,
            "disabled": u.disabled,
            "created_at": u.user_metadata.creation_timestamp,
            "claims": dict(u.custom_claims or {}),
            "providers": [p.provider_id for p in (u.provider_data or [])],
        })

    user_docs = []
    for doc in db.collection("users").stream():
        d = doc.to_dict() or {}
        user_docs.append({
            "doc_id": doc.id,
            "email": d.get("email") or d.get("Email") or d.get("username"),
            "role": d.get("role"),
            "tenant_id": d.get("tenant_id"),
            "display_name": d.get("display_name"),
        })

    tenants = {}
    for t in db.collection("tenants").stream():
        d = t.to_dict() or {}
        email_fields = {}
        for k, v in d.items():
            if "email" in k.lower():
                email_fields[k] = v
        tenants[t.id] = {
            "name": d.get("name") or d.get("display_name") or d.get("icao"),
            "emails": email_fields,
        }

    firebase_admin.delete_app(firebase_admin.get_app())
    return {"auth_users": auth_users, "user_docs": user_docs, "tenants": tenants}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--rename", nargs=2, metavar=("OLD", "NEW"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    env = load_env()
    if not all(k in env for k in ("FIREBASE_PROJECT_ID", "FIREBASE_PRIVATE_KEY", "FIREBASE_CLIENT_EMAIL")):
        sys.exit("Missing Firebase credentials in backend/.env")
    print(f"Project: {env['FIREBASE_PROJECT_ID']}  Database: sms-db")

    if args.rename:
        old_email, new_email = args.rename
        app = get_app(env)
        user = auth.get_user_by_email(old_email)
        print(f"Renaming {old_email} (uid {user.uid}) -> {new_email}")
        auth.update_user(user.uid, email=new_email)
        print(f"Renamed. Claims preserved on uid {user.uid}.")
        firebase_admin.delete_app(firebase_admin.get_app())
        return

    data = collect(env)
    auth_users = data["auth_users"]
    user_docs = data["user_docs"]
    tenants = data["tenants"]

    keep = [u for u in auth_users if (u["email"] or "").lower() in KEEP_EMAILS]
    remove = [u for u in auth_users if (u["email"] or "").lower() not in KEEP_EMAILS]

    def email_of(u):
        return (u["email"] or "").lower()

    remove_set = {email_of(u) for u in remove}
    doc_remove = [
        d for d in user_docs
        if (d["email"] or "").lower() in remove_set
        or d["doc_id"].lower() in remove_set
    ]
    doc_keep = [d for d in user_docs if not any(
        d["doc_id"] == u["uid"] or (d["email"] or "").lower() == email_of(u)
        for u in keep
    )]

    print("\n=== FIRESTORE TENANTS ===")
    for tid, t in sorted(tenants.items()):
        print(f"  {tid:14s} {t['name'] or '':20s} {t['emails']}")

    print("\n=== AUTH USERS TO KEEP ===")
    for u in sorted(keep, key=lambda x: (x["email"] or "")):
        print(f"  KEEP {u['uid']:32s} {u['email'] or '(no email)':32s} role={u['claims'].get('role')} tenant={u['claims'].get('tenant_id')} disabled={u['disabled']} created={u['created_at']}")

    print(f"\n=== AUTH USERS TO REMOVE ({len(remove)}) ===")
    for u in sorted(remove, key=lambda x: (x["email"] or "")):
        print(f"  DEL  {u['uid']:32s} {u['email'] or '(no email)':32s} role={u['claims'].get('role')} tenant={u['claims'].get('tenant_id')} disabled={u['disabled']} created={u['created_at']}")

    print(f"\n=== USERS COLLECTION (sms-db): total={len(user_docs)} ===")
    print(f"  matched to kept auth users: {len(user_docs) - len(doc_keep)}")
    print(f"  to be removed: {len(doc_remove)}")
    for d in sorted(doc_remove, key=lambda x: x["doc_id"]):
        print(f"    {d['doc_id']:32s} email={d['email'] or '':32s} role={d['role']} tenant={d['tenant_id']}")

    unmatched_docs = [d for d in doc_keep if not any(
        d["doc_id"] == u["uid"] or (d["email"] or "").lower() == email_of(u)
        for u in keep
    )]
    print(f"\n  users docs NOT tied to any auth user (not deleted, review): {len(unmatched_docs)}")
    for d in unmatched_docs:
        print(f"    {d['doc_id']:32s} email={d['email'] or '':32s} role={d['role']} tenant={d['tenant_id']}")

    if args.apply or args.dry_run:
        mode = "DRY RUN (no changes)" if args.dry_run else "APPLY"
        print(f"\n[{mode}] Deleting {len(remove)} auth users + matching users docs.")
        if args.dry_run:
            return
        app = get_app(env)
        db = firestore.client(app, database_id="sms-db")
        deleted = {"auth": [], "docs": [], "errors": []}
        for u in remove:
            try:
                auth.delete_user(u["uid"])
                deleted["auth"].append(u["uid"])
            except Exception as e:
                deleted["errors"].append(f"auth {u['uid']}: {e}")
            try:
                doc = db.collection("users").document(u["uid"]).get()
                if doc.exists:
                    db.collection("users").document(u["uid"]).delete()
                    deleted["docs"].append(u["uid"])
            except firestore.NotFoundError:
                pass
            except Exception as e:
                deleted["errors"].append(f"doc {u['uid']}: {e}")
        firebase_admin.delete_app(firebase_admin.get_app())
        print(f"Deletion summary: auth={len(deleted['auth'])} docs={len(deleted['docs'])} errors={len(deleted['errors'])}")
        for e in deleted["errors"]:
            print(f"  ERROR {e}")


if __name__ == "__main__":
    main()