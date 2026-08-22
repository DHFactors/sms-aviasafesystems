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
    python -m seed.runner --tenants-only     # Only seed 3-tenant demo (Phase 3 Step 5)

Idempotent: records the seed version in Firestore. Will not duplicate data
on repeated runs unless --force is used.
"""

import sys
import argparse
from datetime import datetime, timedelta, timezone
from typing import Optional
from loguru import logger

from seed.config import SEED_VERSION, SEED_DOC_PATH, OPERATOR_PROFILES

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
    tenants_only: bool = False,
    with_regulator: bool = False,
    archetype_ids: Optional[list] = None,
) -> dict:
    """Seed demo data.

    ``archetype_ids`` activates Virtual Tenant Mirroring: only the master
    archetype datasets (demo-fixed-wing / demo-rotary-wing) are seeded with
    neutral FW-/RW- references plus the CAAN regulator aggregate view — no
    individual operator data is written.

    `tenant_ids` restricts every step to the given operator tenants (users,
    tenant docs, surveys, reports, hazards/CANs, and the post-seed purge).
    When scoped, the CAAN state-regulator tenant and the global state-risk
    reference are left untouched. When None, the full 12-tenant beta model is
    seeded (11 providers + CAAN).

    `tenants_only` seeds only the 3-tenant demo setup (Buddha Air, Yeti Airlines,
    Sita Air) with users and PSAOE assessments (Phase 3 Step 5).
    """
    if archetype_ids:
        from seed.archetype_config import archetype_seed_profiles

        profiles = archetype_seed_profiles(archetype_ids)
        tenant_ids = [p["id"] for p in profiles]
        logger.info(f"Archetype mode: seeding virtual tenants {tenant_ids} "
                    "(neutral FW-/RW- references; surveys/reports skipped)")
    else:
        profiles = None

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

    all_doing_all = not surveys_only and not reports_only and not users_only and not tenants_only
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
    else:
        tenant_ids = []

    if dry_run:
        from seed.hazard_can import estimate_counts
        from seed.config import OPERATOR_PROFILES as _OP_PROFILES

        if archetype_ids:
            hc = estimate_counts(profiles=profiles)
            counts["hazards"] = hc["hazards"]
            counts["cans"] = hc["cans"]
            counts["caps"] = hc["caps"]
            counts["tenants"] = len(tenant_ids)
            scope = f"archetype virtual tenants {tenant_ids}"
            logger.info(f"DRY RUN ({scope}): Would seed {counts['tenants']} tenants, "
                        f"{counts['hazards']} hazards, {counts['cans']} CANs, "
                        f"{counts['caps']} CAPs (surveys/reports skipped)")
            return counts

        hc = estimate_counts(tenant_ids)
        counts["hazards"] = hc["hazards"]
        counts["cans"] = hc["cans"]
        counts["caps"] = hc["caps"]

        if tenants_only:
            step5_ids = ["buddha-air", "yeti-airlines", "sita-air"]
            profiles = [_p for _p in _OP_PROFILES if _p["id"] in step5_ids]
            counts["tenants"] = len(step5_ids)
        else:
            profiles = [_p for _p in _OP_PROFILES if not tenant_ids or _p["id"] in tenant_ids]
            counts["tenants"] = len(profiles)

        for p in profiles:
            counts["surveys"] += p["survey_count"]
            counts["vsr_reports"] += p["vsr_count"]
            counts["mor_reports"] += p["mor_count"]

        scope = "scoped" if (tenants_only or tenant_ids) else "11-tenant beta"
        logger.info(f"DRY RUN ({scope}): Would seed {counts['tenants']} tenants, "
                     f"{counts['surveys']} surveys, "
                     f"{counts['vsr_reports']} VSR, "
                     f"{counts['mor_reports']} MOR, "
                     f"{counts['hazards']} hazards, "
                     f"{counts['cans']} CANs, "
                     f"{counts['caps']} CAPs, "
                     f"{counts['state_risk_categories']} state risk categories")
        return counts

    if all_doing_all or users_only or tenants_only:
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
        tenant_ids_created = create_all_tenants(db, tenant_ids, profiles=profiles)
        # Full seeds (and presets/archetypes) always include the CAAN
        # state-regulator tenant + oversight scoping; scoped regulator creation
        # covers only the seeded operator ids.
        if not tenant_ids:
            create_caan_tenant(db)
            create_regulator_scoping(db)
        elif with_regulator or archetype_ids:
            create_caan_tenant(db)
            create_regulator_scoping(db, operator_ids=tenant_ids_created)
        counts["tenants"] = len(tenant_ids_created)

    if (all_doing_all or surveys_only) and not archetype_ids:
        logger.info("=== Seeding survey responses ===")
        from seed.surveys import create_all_surveys
        total_surveys = create_all_surveys(db, tenant_ids)
        counts["surveys"] = total_surveys

    if (all_doing_all or reports_only) and not archetype_ids:
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
        hc = create_all_hazard_can_data(db, tenant_ids, profiles=profiles)
        counts["hazards"] = hc["hazards"]
        counts["cans"] = hc["cans"]
        counts["caps"] = hc["caps"]

    if archetype_ids:
        # Virtual archetypes ship with baseline PSOE assessments (one
        # COMPLETED ≥75% "Suitable & Operating" + one DRAFT each) so the AE
        # dashboard maturity panel has data on first load.
        logger.info("=== Seeding archetype PSOE baselines ===")
        counts["psoe"] = _seed_archetype_psoe(db, sorted(archetype_ids))

    if all_doing_all and not tenant_ids:
        logger.info("=== Seeding state risk register reference ===")
        from seed.state_risk import create_all_state_risk_reference
        counts["state_risk_categories"] = create_all_state_risk_reference(db)

    if tenants_only:
        logger.info("=== Seeding 3-tenant demo setup (Phase 3 Step 5) ===")
        from seed.config import OPERATOR_PROFILES as _OP_PROFILES

        # Three demo tenants for Phase 3 Step 5
        step5_tenant_ids = ["buddha-air", "yeti-airlines", "sita-air"]

        from seed.config import CREDENTIAL_TENANT_CODES
        step5_tenant_ids = ["buddha-air", "yeti-airlines", "sita-air"]

        # Count tenants
        counts["tenants"] = len(step5_tenant_ids)

        # === Seed users for the 3 tenants ===
        logger.info("=== Seeding users ===")
        from seed.users import create_user

        # AE, Safety Manager, and Pilot/Reporter per tenant
        ae_email_base = ["ae@buddha.test", "ae@yeti.test", "ae@sita.test"]
        sm_email_base = ["safety@buddha.test", "safety@yeti.test", "safety@sita.test"]
        pilot_email_base = ["pilot@buddha.test", "pilot@yeti.test", "pilot@sita.test"]

        for idx, tid in enumerate(step5_tenant_ids):
            profile = next(p for p in OPERATOR_PROFILES if p["id"] == tid)
            tenant_name = profile["name"]

            # Tenant code for password generation
            code = CREDENTIAL_TENANT_CODES[tid]

            # AE account
            ae_uid = f"ae-{tid}-001"
            ae_pwd = f"{code}-AE-2026"
            create_user(auth, {
                "uid": ae_uid,
                "email": ae_email_base[idx],
                "full_name": f"Accountable Executive ({tenant_name})",
                "organization": tenant_name,
                "role": "AIRLINE_ADMIN",
                "tenant_id": tid,
                "password": ae_pwd,
            })

            # Safety Manager account
            sm_uid = f"sm-{tid}-001"
            sm_pwd = f"{code}-Safety-2026"
            create_user(auth, {
                "uid": sm_uid,
                "email": sm_email_base[idx],
                "full_name": f"Safety Manager ({tenant_name})",
                "organization": tenant_name,
                "role": "TENANT_ADMIN",
                "tenant_id": tid,
                "department": "Safety",
                "password": sm_pwd,
            })

            # Pilot / Reporter account
            pilot_uid = f"pilot-{tid}-001"
            pilot_pwd = f"{code}-Pilot-2026"
            create_user(auth, {
                "uid": pilot_uid,
                "email": pilot_email_base[idx],
                "full_name": f"Pilot/Reporter ({tenant_name})",
                "organization": tenant_name,
                "role": "USER",
                "tenant_id": tid,
                "password": pilot_pwd,
            })

        counts["users"] = 9  # 3 tenants × 3 roles each

        # === Seed PSAOE assessments for the 3 tenants ===
        logger.info("=== Seeding PSAOE assessments ===")
        from app.firebase import get_db
        from app.services.psoe_service import load_template

        db_firestore = get_db()
        template = load_template()

        # PSAOE question data (simplified reflecting Appendix 10)
        psoe_templates = {
            "buddha-air": {
                "title": "Annual SMS Surveillance Audit — Buddha Air",
                "assessment_date": "2026-08-15",
                "auditor_name": "Capt. Rajesh Sharma",
                "status": "completed",
                "responses": [
                    {"question_id": "Q1", "score": 3, "is_na": False, "comment": "Safety policy fully documented and communicated", "evidence": "Policy manual v2.1"},
                    {"question_id": "Q2", "score": 2, "is_na": False, "comment": "Risk assessments conducted quarterly", "evidence": "Risk register Q2 2026"},
                    {"question_id": "Q3", "score": 1, "is_na": False, "comment": "Some mitigations aging", "evidence": "Mitigation plan in progress"},
                    {"question_id": "Q4", "score": 3, "is_na": False, "comment": "Strong safety reporting culture", "evidence": "SMS reports database"},
                    {"question_id": "Q5", "score": 2, "is_na": False, "comment": "SOP reviews up to date", "evidence": "SOP revision log"},
                    {"question_id": "Q6", "score": 2, "is_na": False, "comment": "Safety performance monitoring active", "evidence": "KPI dashboard"},
                    {"question_id": "Q7", "score": 1, "is_na": False, "comment": "One finding overdue", "evidence": "Corrective action pending"},
                    {"question_id": "Q8", "score": 3, "is_na": False, "comment": "Extensive training program", "evidence": "Training records 2026"},
                    {"question_id": "Q9", "score": 2, "is_na": False, "comment": "Safety communication improved", "evidence": "Newsletter Q3"},
                ]
            },
            "yeti-airlines": {
                "title": "Annual SMS Surveillance Audit — Yeti Airlines",
                "assessment_date": "2026-08-15",
                "auditor_name": "F/O Ramesh Thapa",
                "status": "draft",
                "responses": [
                    {"question_id": "Q1", "score": 2, "is_na": False, "comment": "Policy documented, partial implementation", "evidence": "Policy draft v0.9"},
                    {"question_id": "Q2", "score": 3, "is_na": False, "comment": "Robust risk assessment process", "evidence": "Risk register current"},
                    {"question_id": "Q3", "score": 3, "is_na": False, "comment": "All mitigations current", "evidence": "Mitigation complete"},
                    {"question_id": "Q4", "score": 2, "is_na": False, "comment": "Safety reporting average", "evidence": "Reports database"},
                    {"question_id": "Q5", "score": 1, "is_na": False, "comment": "Some SOPs outdated", "evidence": "SOP revision needed"},
                    {"question_id": "Q6", "score": 2, "is_na": False, "comment": "Assurance activities ongoing", "evidence": "Audit schedule"},
                    {"question_id": "Q7", "score": 3, "is_na": False, "comment": "Strong safety culture", "evidence": "Climate survey"},
                    {"question_id": "Q8", "score": 1, "is_na": False, "comment": "Limited promotion activities", "evidence": "Draft plan"},
                    {"question_id": "Q9", "score": 2, "is_na": False, "comment": "Communication improving", "evidence": "Briefing records"},
                ]
            },
            "sita-air": {
                "title": "Annual SMS Surveillance Audit — Sita Air",
                "assessment_date": "2026-08-15",
                "auditor_name": "Sita Kumari Gurung",
                "status": "completed",
                "responses": [
                    {"question_id": "Q1", "score": 3, "is_na": False, "comment": "Safety policy fully effective", "evidence": "Policy manual approved"},
                    {"question_id": "Q2", "score": 3, "is_na": False, "comment": "Excellent risk management", "evidence": "Risk register gold"},
                    {"question_id": "Q3", "score": 2, "is_na": False, "comment": "Most mitigations effective", "evidence": "Action plan complete"},
                    {"question_id": "Q4", "score": 3, "is_na": False, "comment": "Strong reporting culture", "evidence": "SMS database"},
                    {"question_id": "Q5", "score": 3, "is_na": False, "comment": "All SOPs current", "evidence": "Revision log"},
                    {"question_id": "Q6", "score": 3, "is_na": False, "comment": "Assurance excellent", "evidence": "Performance dashboard"},
                    {"question_id": "Q7", "score": 2, "is_na": False, "comment": "One area for improvement", "evidence": "Corrective action"},
                    {"question_id": "Q8", "score": 3, "is_na": False, "comment": "Promotion very active", "evidence": "Training records"},
                    {"question_id": "Q9", "score": 3, "is_na": False, "comment": "Communication excellent", "evidence": "Newsletters"},
                ]
            },
        }

        for idx, tid in enumerate(step5_tenant_ids):
            psoe_t = psoe_templates[tid]

            from app.models.psoe import PSOEAnswer, PSOEAssessmentCreate

            # Create response objects
            responses = []
            for r in psoe_t["responses"]:
                responses.append(PSOEAnswer(
                    question_id=r["question_id"],
                    score=r["score"] if not r["is_na"] else None,
                    is_na=r["is_na"],
                    comment=r.get("comment"),
                    evidence=r.get("evidence"),
                ))

            from app.services.psoe_service import score_assessment
            scores = score_assessment(responses)

            now = datetime.now(timezone.utc)

            assessment_create = PSOEAssessmentCreate(
                title=psoe_t["title"],
                tenant_id=tid,
                department="Safety",
                scope="Annual SMS surveillance",
                auditor_name=psoe_t["auditor_name"],
                assessor_email=f"ae@{tid}.test",
                assessment_date=psoe_t["assessment_date"],
                template_version="1.0.0",
                responses=responses,
                notes="Seeded PSAOE assessment for Phase 3 Step 5 demo",
            )

            doc_data = {
                "tenant_id": assessment_create.tenant_id,
                "title": assessment_create.title,
                "status": psoe_t["status"],
                "department": assessment_create.department,
                "scope": assessment_create.scope,
                "auditor_name": assessment_create.auditor_name,
                "assessor_email": assessment_create.assessor_email,
                "assessment_date": assessment_create.assessment_date,
                "template_version": assessment_create.template_version,
                "responses": [r.model_dump() for r in assessment_create.responses],
                "component_scores": scores["component_scores"],
                "overall_score_pct": scores["overall_score_pct"],
                "overall_level": scores["overall_level"],
                "created_by": "seed.runner",
                "created_at": now,
                "updated_at": now,
                "notes": assessment_create.notes,
            }

            doc_ref = db_firestore.collection("psoe_assessments").document(tid)
            doc_ref.set(doc_data)

        logger.info(f"Seeded PSAOE assessments for {counts['tenants']} tenants: "
                     f"1 COMPLETED + 1 DRAFT per tenant")

    # Purge / stamp after all steps
    if not dry_run:
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


def _seed_archetype_psoe(db, tenant_ids: list) -> int:
    """Write baseline PSOE assessments for virtual archetype tenants.

    One COMPLETED (overall ~80% → Level 2 'Suitable & Operating') and one
    DRAFT per tenant, written to the top-level `psoe_assessments` collection.
    Idempotent via deterministic document ids."""
    from app.models.psoe import PSOEAnswer
    from app.services.psoe_service import load_template, score_assessment

    template = load_template()
    coll = db.collection("psoe_assessments")
    now = datetime.now(timezone.utc)

    completed_scores = {
        "component_1": [3, 3, 3, 2, 3, 1],   # Policy ~83%
        "component_2": [3, 3, 2, 3, 2, 1],   # SRM ~78%
        "component_3": [3, 3, 2, 3, 1],      # Assurance ~80%
        "component_4": [3, 3, 3, 1],         # Promotion ~83%
    }
    draft_scores = {
        "component_1": [2, 2, 2, 3, 2, 1],
        "component_2": [2, 2, 1, 2, 2, 1],
        "component_3": [2, 2, 1, 2, 0],
        "component_4": [2, 2, 1, None],
    }

    def _responses(template, plan):
        out = []
        for comp in template.components:
            for q, score in zip(comp.questions, plan[comp.id]):
                if score is None:
                    out.append(PSOEAnswer(question_id=q.id, score=None, is_na=True))
                else:
                    out.append(PSOEAnswer(
                        question_id=q.id, score=score, is_na=False,
                        comment=f"Seasonal baseline evidence ({q.id}).",
                        evidence="Archetype demo dataset",
                    ))
        return out

    written = 0
    for tid in tenant_ids:
        for suffix, status, plan, date_off in (
            ("baseline-completed", "completed", completed_scores, 1),
            ("baseline-draft", "draft", draft_scores, 3),
        ):
            responses = _responses(template, plan)
            scores = score_assessment(responses)
            doc = {
                "tenant_id": tid,
                "title": f"{tid} — CAAN Appendix 10 {'Surveillance' if status == 'completed' else 'Self-Assessment (Draft)'}",
                "status": status,
                "department": "Safety",
                "scope": "CAAN Appendix 10 SMS surveillance" if status == "completed" else "PSOE self-assessment",
                "assessment_date": (now - timedelta(days=date_off)).date().isoformat(),
                "template_version": template.version,
                "responses": [r.model_dump() for r in responses],
                "component_scores": scores["component_scores"],
                "overall_score_pct": scores["overall_score_pct"],
                "overall_level": scores["overall_level"],
                "created_by": "seed.runner",
                "created_at": now,
                "updated_at": now,
                "seed_version": SEED_VERSION,
            }
            coll.document(f"{tid}-{suffix}").set(doc)
            written += 1

    logger.info(f"Seeded {written} baseline PSOE assessments for archetypes")
    return written


def main():
    parser = argparse.ArgumentParser(description="AviaSAFE Demo Data Seeder")
    parser.add_argument("--force", action="store_true", help="Re-seed (overwrite + purge stale)")
    parser.add_argument("--dry-run", action="store_true", help="Show counts without writing")
    parser.add_argument("--surveys-only", action="store_true", help="Only seed survey data")
    parser.add_argument("--reports-only", action="store_true", help="Only seed VSR + MOR data")
    parser.add_argument("--users-only", action="store_true", help="Only seed auth users")
    parser.add_argument("--tenants-only", action="store_true", help="Seed 3-tenant demo setup (Phase 3 Step 5)")
    parser.add_argument("--preset", choices=["full", "lean", "dev"], default="full",
                        help=(
                            "Seeding preset: "
                            "full = 365-day seasonal window across all 11 operators + CAAN "
                            "(default / beta / prod staging); "
                            "lean = 365-day window restricted to buddha-air + fishtail-air + CAAN; "
                            "dev = 90-day lightweight window (2 operators) for fast local testing."
                        ))
    parser.add_argument("--archetypes", default=None,
                        help=(
                            "Virtual Tenant Mirroring: comma-separated virtual tenants to seed, "
                            "e.g. 'demo-fixed-wing,demo-rotary-wing,caanepal'. Seeds the master "
                            "archetype datasets with neutral FW-/RW- references (365-day seasonal) "
                            "plus the CAAN regulator aggregate view. Mutually exclusive with --preset."
                        ))

    args = parser.parse_args()

    import seed.config as _cfg
    from seed.archetype_config import (
        ARCHETYPE_DATASETS,
        REGULATOR_TIER_ID,
        archetype_seed_profiles,
    )

    archetype_ids = None
    if args.archetypes:
        requested = [a.strip() for a in args.archetypes.split(",") if a.strip()]
        unknown = [a for a in requested
                   if a != REGULATOR_TIER_ID and a not in ARCHETYPE_DATASETS]
        if unknown:
            parser.error(f"Unknown archetype(s): {unknown}. "
                         f"Known: {list(ARCHETYPE_DATASETS)} + {REGULATOR_TIER_ID}")
        archetype_ids = [a for a in requested if a != REGULATOR_TIER_ID]
        _cfg.SEED_WINDOW_DAYS = 365

    # Preset strategy: window length + operator scope. The window is read
    # dynamically by the generators, so mutate it before run().
    if not archetype_ids:
        if args.preset == "lean":
            preset_tenant_ids = ["buddha-air", "fishtail-air"]
            _cfg.SEED_WINDOW_DAYS = 365
        elif args.preset == "dev":
            preset_tenant_ids = ["buddha-air", "fishtail-air"]
            _cfg.SEED_WINDOW_DAYS = 90
        else:
            preset_tenant_ids = None  # full: all OPERATOR_PROFILES
            _cfg.SEED_WINDOW_DAYS = 365
    else:
        preset_tenant_ids = None

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
        tenants_only=args.tenants_only,
        tenant_ids=preset_tenant_ids,
        with_regulator=True,  # presets always include the CAAN state-regulator tier
        archetype_ids=archetype_ids,
    )
    return result


if __name__ == "__main__":
    main()