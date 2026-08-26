#!/usr/bin/env python3
"""
============================================================================
FILE: backend/scripts/purge_and_seed_users.py
PURPOSE: Purges all legacy/mock user accounts from Firebase Auth and
         Firestore collections (users/, tenants/{id}/users/), then seeds
         only the single authorized developer account and designated
         tenant operational accounts with role-prefixed emails.

         All mutations target the named database "sms-db-beta" exclusively.
         A --clean-prod-db flag is provided to wipe any stray documents
         mistakenly written to the virgin production database "sms-db".

USAGE:
    python backend/scripts/purge_and_seed_users.py --dry-run
    python backend/scripts/purge_and_seed_users.py
    python backend/scripts/purge_and_seed_users.py --purge-only
    python backend/scripts/purge_and_seed_users.py --seed-only
    python backend/scripts/purge_and_seed_users.py --clean-prod-db
============================================================================
"""

import os
import sys
import argparse

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

# ── Named Database Routing ──────────────────────────────────────────────────

TARGET_DB = os.getenv("FIRESTORE_DATABASE_ID", "sms-db-beta")

# ── Authorized Access Matrix ─────────────────────────────────────────────────

DEVELOPER_ACCOUNT = {
    "email": "ezondiza.dhf@gmail.com",
    "password": "DevSecurePassword2026!",
    "display_name": "Ezondiza DHF (System Developer)",
    "role": "admin",
    "tenant_id": "system",
}

TENANT_CONFIGS = [
    {
        "tenant_id": "fishtail-air",
        "domain": "fishtailair.com.np",
        "name": "Fishtail Air Pvt. Ltd.",
    },
    {
        "tenant_id": "nepal-wings",
        "domain": "nepalwings.com.np",
        "name": "Nepal Wings Aviation",
    },
]

ROLE_PREFIXES = [
    {"prefix": "safety", "role": "safety_manager", "title": "Safety Manager"},
    {"prefix": "145",    "role": "maintenance_manager", "title": "Part-145 Maintenance Manager"},
    {"prefix": "camo",   "role": "camo_manager", "title": "CAMO Continuing Airworthiness"},
    {"prefix": "ops",    "role": "flight_ops", "title": "Flight Operations Post-Holder"},
    {"prefix": "gops",   "role": "ground_ops", "title": "Ground Operations Lead"},
]

DEFAULT_TENANT_PASSWORD = "AviationSafe2026!"

PROD_COLLECTIONS = ["users", "tenants", "audit_logs", "hazards", "occurrences",
                     "reports", "cans", "regulators", "responses", "surveys"]


# ── Firebase Bootstrap ───────────────────────────────────────────────────────

def init_firebase():
    """Initialize Firebase using the project's service account from env."""
    from app.firebase import initialize_firebase
    initialize_firebase()


# ── Clean Virgin Production Database ─────────────────────────────────────────

def clean_prod_db():
    """Purge stray accidental documents from the virgin production sms-db."""
    import firebase_admin
    from firebase_admin import firestore
    prod_db = firestore.client(app=firebase_admin.get_app(), database_id="sms-db")
    total = 0
    for col in PROD_COLLECTIONS:
        docs = list(prod_db.collection(col).stream())
        for doc in docs:
            doc.reference.delete()
            print(f"  [clean] sms-db: {col}/{doc.id}")
            total += 1
        # Also check tenants/{id}/{subcollection} leaks
        for tenant_doc in prod_db.collection("tenants").stream():
            for sub in tenant_doc.reference.collections():
                for sub_doc in sub.stream():
                    sub_doc.reference.delete()
                    print(f"  [clean] sms-db: tenants/{tenant_doc.id}/{sub.id}/{sub_doc.id}")
                    total += 1
            tenant_doc.reference.delete()
            print(f"  [clean] sms-db: tenants/{tenant_doc.id}")
            total += 1
    print(f"\n  -> {total} stray document(s) removed from sms-db.")
    print("  -> sms-db is now virgin and clean.")
    return total


# ── Purge (beta) ─────────────────────────────────────────────────────────────

def purge_auth_users():
    """Delete ALL Firebase Auth user records."""
    import firebase_admin
    deleted = 0
    page = firebase_admin.auth.list_users()
    while page:
        for user in page.users:
            firebase_admin.auth.delete_user(user.uid)
            print(f"  [purge] Auth: {user.email} ({user.uid[:12]}...)")
            deleted += 1
        page = page.get_next_page()
    return deleted


def purge_firestore_users(db):
    """Delete all documents in the top-level /users collection."""
    deleted = 0
    for doc in db.collection("users").stream():
        doc.reference.delete()
        print(f"  [purge] FS  users/{doc.id}")
        deleted += 1
    return deleted


def purge_tenant_user_subcollections(db):
    """Delete all documents under tenants/{id}/users/ for every tenant."""
    deleted = 0
    for tenant_doc in db.collection("tenants").stream():
        users_sub = tenant_doc.reference.collection("users")
        for user_doc in users_sub.stream():
            user_doc.reference.delete()
            print(f"  [purge] FS  tenants/{tenant_doc.id}/users/{user_doc.id}")
            deleted += 1
    return deleted


# ── Seed (beta) ──────────────────────────────────────────────────────────────

def seed_developer(db):
    """Provision the single authorized developer account."""
    import firebase_admin
    rec = DEVELOPER_ACCOUNT
    user = firebase_admin.auth.create_user(
        email=rec["email"],
        password=rec["password"],
        display_name=rec["display_name"],
    )
    firebase_admin.auth.set_custom_user_claims(user.uid, {
        "role": rec["role"],
        "tenant_id": rec["tenant_id"],
    })
    db.collection("users").document(user.uid).set({
        "email": rec["email"],
        "role": rec["role"],
        "tenant_id": rec["tenant_id"],
        "display_name": rec["display_name"],
    })
    print(f"  [seed] Developer: {rec['email']} (uid={user.uid[:12]}...)")
    return user


def seed_tenant_users(db):
    """Provision role-prefixed operational accounts for each designated tenant."""
    import firebase_admin
    created = 0
    for tenant in TENANT_CONFIGS:
        t_id = tenant["tenant_id"]
        domain = tenant["domain"]
        print(f"\n  --- {tenant['name']} ({t_id}) ---")
        for r in ROLE_PREFIXES:
            email = f"{r['prefix']}@{domain}"
            name = f"{tenant['name']} - {r['title']}"
            user = firebase_admin.auth.create_user(
                email=email,
                password=DEFAULT_TENANT_PASSWORD,
                display_name=name,
            )
            firebase_admin.auth.set_custom_user_claims(user.uid, {
                "role": r["role"],
                "tenant_id": t_id,
            })
            db.collection("users").document(user.uid).set({
                "email": email,
                "role": r["role"],
                "tenant_id": t_id,
                "display_name": name,
            })
            db.collection("tenants").document(t_id).collection("users").document(user.uid).set({
                "email": email,
                "role": r["role"],
                "tenant_id": t_id,
                "display_name": name,
            })
            print(f"  [seed] {r['prefix'].upper():>6}  {email}  role={r['role']}")
            created += 1
    return created


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Purge and seed Firebase Auth + Firestore users.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes.")
    parser.add_argument("--purge-only", action="store_true", help="Only purge, do not seed.")
    parser.add_argument("--seed-only", action="store_true", help="Only seed, do not purge.")
    parser.add_argument("--clean-prod-db", action="store_true",
                        help="Purge stray accidental documents from virgin sms-db and exit.")
    args = parser.parse_args()

    init_firebase()

    # ── Clean prod path (independent of beta workflow) ────────────────────
    if args.clean_prod_db:
        print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Purging accidental data from virgin 'sms-db'...")
        if not args.dry_run:
            clean_prod_db()
        else:
            import firebase_admin
            from firebase_admin import firestore
            prod_db = firestore.client(app=firebase_admin.get_app(), database_id="sms-db")
            count = sum(len(list(prod_db.collection(c).stream())) for c in PROD_COLLECTIONS)
            print(f"  [dry-run] Would delete ~{count} document(s) from sms-db.")
        print("\n[Complete] Done.")
        return

    # ── Safety gate: never seed against production ────────────────────────
    if TARGET_DB != "sms-db-beta":
        print(f"\nBLOCKED: Seeding script must target 'sms-db-beta', got '{TARGET_DB}'.")
        sys.exit(1)

    import firebase_admin
    from firebase_admin import firestore
    beta_db = firestore.client(app=firebase_admin.get_app(), database_id="sms-db-beta")
    print(f"\nConnected to Firestore -> [Database: {TARGET_DB}]")

    if args.dry_run:
        print("\n=== DRY RUN (no changes will be made) ===\n")

    # ── Purge phase ──────────────────────────────────────────────────────
    if not args.seed_only:
        print("[1/3] Purging Firebase Auth users...")
        if not args.dry_run:
            n = purge_auth_users()
        else:
            import firebase_admin
            n = sum(1 for _ in firebase_admin.auth.list_users().iterate_all())
        print(f"       -> {n} auth user(s) {'would be ' if args.dry_run else ''}deleted\n")

        print("[2/3] Purging Firestore /users + tenants/*/users ...")
        if not args.dry_run:
            n1 = purge_firestore_users(beta_db)
            n2 = purge_tenant_user_subcollections(beta_db)
        else:
            n1 = len(list(beta_db.collection("users").stream()))
            n2 = sum(
                len(list(t.reference.collection("users").stream()))
                for t in beta_db.collection("tenants").stream()
            )
        print(f"       -> {n1} /users doc(s), {n2} tenant subcollection doc(s) {'would be ' if args.dry_run else ''}deleted\n")

    # ── Seed phase ───────────────────────────────────────────────────────
    if not args.purge_only:
        print("[3/3] Seeding authorized accounts...")
        if not args.dry_run:
            seed_developer(beta_db)
            n = seed_tenant_users(beta_db)
        else:
            print(f"  [seed] Developer: {DEVELOPER_ACCOUNT['email']}")
            n = len(TENANT_CONFIGS) * len(ROLE_PREFIXES)
            for tenant in TENANT_CONFIGS:
                for r in ROLE_PREFIXES:
                    print(f"  [seed] {r['prefix'].upper():>6}  {r['prefix']}@{tenant['domain']}")
        print(f"\n       -> {n + 1} user(s) {'would be ' if args.dry_run else ''}created\n")

    print("[Complete] Done.")


if __name__ == "__main__":
    main()
