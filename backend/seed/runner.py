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
from typing import Optional
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


# Collections + deterministic document-id prefixes that this runner owns.
# Only docs matching a prefix are candidates for purging; anything else (live
# submissions, admin/CAAN demo seeders) is left untouched.
RUNNER_COLLECTION_PREFIXES = {
    "surveys": ("svy_",),
    "responses": ("svy_",),
    "reports": ("vsr_", "mor_"),
    "hazards": ("haz_",),
    "can_cap": ("can_",),
}


def _is_stale(doc_id: str, doc_data: dict, prefixes: tuple) -> bool:
    """Runner-created docs that a successful seed would have (re)tagged with the
    current SEED_VERSION. Anything with a runner prefix but a different/missing
    version is leftover from an older seed and safe to remove."""
    if not any(doc_id.startswith(p) for p in prefixes):
        return False
    stored_version = (doc_data or {}).get("seed_version")
    return stored_version != SEED_VERSION


def purge_stale_seed(db, tenant_ids=None) -> dict:
    """Remove runner-owned docs left over from earlier seed versions.

    Runs only AFTER the whole seed has succeeded, so a failed re-seed can never
    wipe existing data (previously the clear ran first and left the database
    empty on mid-run failures). Scoped to `tenant_ids` when provided.
    """
    from app.core.config import settings

    removed = {"surveys": 0, "responses": 0, "reports": 0, "hazards": 0, "can_cap": 0, "caps": 0}
    profiles = [p for p in OPERATOR_PROFILES if not tenant_ids or p["id"] in tenant_ids]
    for tenant_id in [p["id"] for p in profiles]:
        tenant_ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id)

        for sub, prefixes in RUNNER_COLLECTION_PREFIXES.items():
            try:
                snaps = tenant_ref.collection(sub).stream()
            except Exception as e:
                logger.warning(f"Purge scan failed for {tenant_id}/{sub}: {e}")
                continue
            for s in snaps:
                if _is_stale(s.id, s.to_dict(), prefixes):
                    s.reference.delete()
                    removed[sub] += 1

        try:
            cans = tenant_ref.collection("can_cap").stream()
        except Exception:
            cans = []
        for can in cans:
            try:
                caps = can.reference.collection("caps").stream()
            except Exception:
                caps = []
            for cap in caps:
                if _is_stale(cap.id, cap.to_dict(), ("cap_",)):
                    cap.reference.delete()
                    removed["caps"] += 1

    logger.info(f"Purged stale seed docs: {removed}")
    return removed


def run(
    db=None,
    auth=None,
    force: bool = False,
    dry_run: bool = False,
    surveys_only: bool = False,
    reports_only: bool = False,
    users_only: bool = False,
    tenant_ids: Optional[list] = None,
) -> dict:
    """Seed demo data.

    `tenant_ids` restricts every step to the given operator tenants (users,
    tenant docs, surveys, reports, hazards/CANs, and the post-seed purge).
    When scoped, the CAAN state-regulator tenant and the global state-risk
    reference are left untouched. When None, the full 11-tenant beta model is
    seeded (10 providers + CAAN).
    """
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

    all_doing_all = not surveys_only and not reports_only and not users_only
    counts = {
        "version": SEED_VERSION,
        "tenants": 0,
        "users": 0,
        "surveys": 0,
        "vsr_reports": 0,
        "mor_reports": 0,
        "hazards": 0,
        "cans": 0,
        "caps": 0,
        "state_risk_categories": 0,
    }
    if tenant_ids:
        counts["tenant_ids"] = sorted(set(tenant_ids))

    if dry_run:
        from seed.hazard_can import estimate_counts
        hc = estimate_counts(tenant_ids)
        counts["hazards"] = hc["hazards"]
        counts["cans"] = hc["cans"]
        counts["caps"] = hc["caps"]
        profiles = [p for p in OPERATOR_PROFILES if not tenant_ids or p["id"] in tenant_ids]
        for p in profiles:
            counts["tenants"] += 1
            counts["surveys"] += p["survey_count"]
            counts["vsr_reports"] += p["vsr_count"]
            counts["mor_reports"] += p["mor_count"]
        scope = "scoped" if tenant_ids else "10-tenant beta"
        logger.info(f"DRY RUN ({scope}): Would seed {counts['tenants']} tenants, "
                     f"{counts['surveys']} surveys, "
                     f"{counts['vsr_reports']} VSR, "
                     f"{counts['mor_reports']} MOR, "
                     f"{counts['hazards']} hazards, "
                     f"{counts['cans']} CANs, "
                     f"{counts['caps']} CAPs, "
                     f"{counts['state_risk_categories']} state risk categories")
        return counts

    if all_doing_all or users_only:
        logger.info("=== Seeding users ===")
        from seed.users import create_all_users
        created = create_all_users(auth, tenant_ids)
        counts["users"] = len(created)

    if all_doing_all or (not users_only and not reports_only):
        logger.info("=== Seeding tenants ===")
        from seed.operators import (
            create_all_tenants,
            create_caan_tenant,
            create_regulator_scoping,
        )
        tenant_ids_created = create_all_tenants(db, tenant_ids)
        if not tenant_ids:
            create_caan_tenant(db)
            create_regulator_scoping(db)
        counts["tenants"] = len(tenant_ids_created)

    if all_doing_all or surveys_only:
        logger.info("=== Seeding survey responses ===")
        from seed.surveys import create_all_surveys
        total_surveys = create_all_surveys(db, tenant_ids)
        counts["surveys"] = total_surveys

    if all_doing_all or reports_only:
        logger.info("=== Seeding VSR reports ===")
        from seed.reports import create_all_vsr_reports
        total_vsr = create_all_vsr_reports(db, tenant_ids)
        counts["vsr_reports"] = total_vsr

        logger.info("=== Seeding MOR reports ===")
        from seed.reports import create_all_mor_reports
        total_mor = create_all_mor_reports(db, tenant_ids)
        counts["mor_reports"] = total_mor

    if all_doing_all or reports_only:
        logger.info("=== Seeding hazards + CAN/CAP ===")
        from seed.hazard_can import create_all_hazard_can_data
        hc = create_all_hazard_can_data(db, tenant_ids)
        counts["hazards"] = hc["hazards"]
        counts["cans"] = hc["cans"]
        counts["caps"] = hc["caps"]

    if all_doing_all and not tenant_ids:
        logger.info("=== Seeding state risk register reference ===")
        from seed.state_risk import create_all_state_risk_reference
        counts["state_risk_categories"] = create_all_state_risk_reference(db)

    if not dry_run:
        # Purge runner-owned leftovers only after the whole seed succeeded, so a
        # failed re-seed can no longer wipe existing data (non-destructive-until-success).
        if all_doing_all:
            purge_stale_seed(db, tenant_ids)
        counts["seeded_at"] = datetime.now(timezone.utc).isoformat()
        set_seed_status(db, counts)
        logger.info(f"Seed complete: {counts['surveys']} surveys, "
                     f"{counts['vsr_reports']} VSR, {counts['mor_reports']} MOR, "
                     f"{counts['hazards']} hazards, {counts['cans']} CANs, "
                     f"{counts['caps']} CAPs "
                     f"across {counts['tenants']} tenants with {counts['users']} users")

    return counts


def main():
    parser = argparse.ArgumentParser(description="AviaSAFE Demo Data Seeder")
    parser.add_argument("--force", action="store_true", help="Re-seed (overwrite + purge stale)")
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
