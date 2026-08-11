#!/usr/bin/env python3
"""
AviaSAFE Demo Data Seeder

Seeds a production-quality demonstration dataset into Firestore for the
AviaSAFE Safety Management System (SMS) Platform.

Usage:
    python -m seed.runner                    # Seed if not already seeded
    python -m seed.runner --force            # Re-seed (delete and recreate)
    python -m seed.runner --dry-run          # Print counts without writing
    python -m seed.runner --surveys-only     # Only seed survey data
    python -m seed.runner --reports-only     # Only seed VSR + MOR data
    python -m seed.runner --users-only       # Only seed auth users

Idempotent: records the seed version in Firestore. Will not duplicate data
on repeated runs unless --force is used.
"""

import sys
import argparse
from datetime import datetime, timezone
from loguru import logger

from seed.config import (
    SEED_VERSION,
    SEED_DOC_PATH,
    OPERATOR_PROFILES,
)

logger.remove()
logger.add(sys.stdout, format="{time:HH:mm:ss} | {level:<7} | {message}", level="INFO")


def get_seed_status(db) -> dict:
    doc_ref = db.document(SEED_DOC_PATH)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    return None


def set_seed_status(db, status: dict):
    doc_ref = db.document(SEED_DOC_PATH)
    doc_ref.set(status)


def clear_seed_data(db, tenant_ids: list):
    from app.core.config import settings

    for tenant_id in tenant_ids:
        tenant_ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id)

        reports = tenant_ref.collection(settings.FIREBASE_COLLECTION_REPORTS).stream()
        for r in reports:
            r.reference.delete()

        surveys = tenant_ref.collection("surveys").stream()
        for s in surveys:
            s.reference.delete()

        metadata = tenant_ref.collection(settings.FIREBASE_COLLECTION_METADATA).stream()
        for m in metadata:
            m.reference.delete()

        tenant_ref.delete()

    logger.info(f"Cleared existing seed data for {len(tenant_ids)} tenants")

    seed_doc = db.document(SEED_DOC_PATH)
    if seed_doc.get().exists:
        seed_doc.delete()

    logger.info("Cleared seed metadata")


def run(
    db=None,
    auth=None,
    force: bool = False,
    dry_run: bool = False,
    surveys_only: bool = False,
    reports_only: bool = False,
    users_only: bool = False,
) -> dict:
    if not dry_run:
        if db is None:
            from app.firebase import get_db
            db = get_db()
        if auth is None:
            from app.firebase import get_auth
            auth = get_auth()

    status = None if dry_run else get_seed_status(db)

    if status and status.get("version") == SEED_VERSION and not force and not dry_run:
        logger.info(f"Seed version {SEED_VERSION} already applied at {status.get('seeded_at')}")
        logger.info("Use --force to re-seed")
        return {"status": "skipped", "version": SEED_VERSION, "seeded_at": status.get("seeded_at")}

    if force and not dry_run:
        tenant_ids = [p["id"] for p in OPERATOR_PROFILES]
        clear_seed_data(db, tenant_ids)

    all_doing_all = not surveys_only and not reports_only and not users_only
    counts = {
        "version": SEED_VERSION,
        "tenants": 0,
        "users": 0,
        "surveys": 0,
        "vsr_reports": 0,
        "mor_reports": 0,
        "state_risk_categories": 0,
    }

    if dry_run:
        for p in OPERATOR_PROFILES:
            counts["tenants"] += 1
            counts["surveys"] += p["survey_count"]
            counts["vsr_reports"] += p["vsr_count"]
            counts["mor_reports"] += p["mor_count"]
        logger.info(f"DRY RUN: Would seed {counts['tenants']} tenants, "
                     f"{counts['surveys']} surveys, "
                     f"{counts['vsr_reports']} VSR, "
                     f"{counts['mor_reports']} MOR, "
                     f"{counts['state_risk_categories']} state risk categories")
        return counts

    if all_doing_all or users_only:
        logger.info("=== Seeding users ===")
        from seed.users import create_all_users
        created = create_all_users(auth)
        counts["users"] = len(created)

    if all_doing_all or (not users_only and not reports_only):
        logger.info("=== Seeding tenants ===")
        from seed.operators import create_all_tenants, create_caan_tenant
        tenant_ids = create_all_tenants(db)
        create_caan_tenant(db)
        counts["tenants"] = len(tenant_ids)

    if all_doing_all or surveys_only:
        logger.info("=== Seeding survey responses ===")
        from seed.surveys import create_all_surveys
        total_surveys = create_all_surveys(db)
        counts["surveys"] = total_surveys

    if all_doing_all or reports_only:
        logger.info("=== Seeding VSR reports ===")
        from seed.reports import create_all_vsr_reports
        total_vsr = create_all_vsr_reports(db)
        counts["vsr_reports"] = total_vsr

        logger.info("=== Seeding MOR reports ===")
        from seed.reports import create_all_mor_reports
        total_mor = create_all_mor_reports(db)
        counts["mor_reports"] = total_mor

    if all_doing_all:
        logger.info("=== Seeding state risk register reference ===")
        from seed.state_risk import create_all_state_risk_reference
        counts["state_risk_categories"] = create_all_state_risk_reference(db)

    if not dry_run:
        counts["seeded_at"] = datetime.now(timezone.utc).isoformat()
        set_seed_status(db, counts)
        logger.info(f"Seed complete: {counts['surveys']} surveys, "
                     f"{counts['vsr_reports']} VSR, {counts['mor_reports']} MOR "
                     f"across {counts['tenants']} tenants with {counts['users']} users")

    return counts


def main():
    parser = argparse.ArgumentParser(description="AviaSAFE Demo Data Seeder")
    parser.add_argument("--force", action="store_true", help="Re-seed (delete and recreate)")
    parser.add_argument("--dry-run", action="store_true", help="Show counts without writing")
    parser.add_argument("--surveys-only", action="store_true", help="Only seed survey data")
    parser.add_argument("--reports-only", action="store_true", help="Only seed VSR + MOR data")
    parser.add_argument("--users-only", action="store_true", help="Only seed auth users")
    args = parser.parse_args()

    from app.core.config import settings
    from app.firebase import initialize_firebase, get_db, get_auth

    initialize_firebase()
    db = get_db()
    auth = get_auth()

    result = run(
        db=db,
        auth=auth,
        force=args.force,
        dry_run=args.dry_run,
        surveys_only=args.surveys_only,
        reports_only=args.reports_only,
        users_only=args.users_only,
    )
    return result


if __name__ == "__main__":
    main()
