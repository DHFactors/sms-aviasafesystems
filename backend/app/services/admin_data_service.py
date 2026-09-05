# ============================================================================
# FILE: admin_data_service.py
# PATH: backend/app/services/admin_data_service.py
# PURPOSE: Super-Admin data-management helpers:
#            * Tenant lifecycle status (Demo / Trial / Active / Inactive) driven
#              by contract dates + payment status.
#            * Seed / unseed dummy operational data (VSR, MOR, CAN, CAP) for
#              one tenant or every tenant.
#          Every mutation is recorded in the `audit_logs` collection and any
#          doc written by the seeder carries the ADMIN_DEMO_SEED_VERSION marker
#          so an unseed only ever removes its own dummy data.
# AUTHOR: AviaSAFE Systems
# ============================================================================

import csv
import io
import json
import random
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import and_, delete, func, or_, select, union_all

from app.core.config import settings
from app.firebase import get_db
from app.models.hazard import revalue_taxonomy
from app.services.hazard_service import generate_hazard_id, resolve_function_code
from app.db.ids import register_tenant, tenant_uuid
from app.db.session import session_scope
from app.db.db_models import (
    BarrierRegisterEntry,
    BowTieAnalysis,
    BowTieConsequence,
    BowTieControl,
    BowTieThreat,
    Can,
    Cap,
    Closure,
    CorrectiveAction,
    FlightDiversion,
    Hazard,
    HazardAssessment,
    HazardCapa,
    HazardRcaEntry,
    HazardRcaFactor,
    PsoeAssessment,
    PsoeFinding,
    RegulatoryReport,
    Report,
    RiskRegisterEntry,
    SafetyDeficiency,
    StateRiskRegisterEntry,
    Survey,
    SurveyResponse,
    Verification,
)
from app.services.risk_matrix import compute_risk_index, get_risk_level
from app.services.production_seed import _audit, _validate_id
from app.services.state_risk_service import STATE_COLLECTION

TENANT_STATUSES = {"DEMO", "TRIAL", "ACTIVE", "SUSPENDED", "RETIRED", "CANCELLED", "INACTIVE"}
# Back-compat alias: retired/cancelled written as single string maps to RETIRED
TENANT_STATUS_ALIASES = {"RETIRED/CANCELLED": "RETIRED", "RETIRED_CANCELLED": "RETIRED", "CANCELED": "CANCELLED"}
PAYMENT_STATUSES = {"paid", "unpaid", "not_applicable"}
DEMO_KINDS = {"vsr", "mor", "can", "cap", "survey"}

ADMIN_DEMO_SEED_VERSION = "admin-demo-1"
ADMIN_DEMO_CREATOR = "admin-seed"

_DEPARTMENTS = ["Flight Operations", "Maintenance & Engineering",
                "Ground Handling", "Cabin Crew", "Administration"]
_ICAO_CATEGORIES = ["LOCI", "CFIT", "RE", "RI", "MAC", "WX", "ENG", "SYS",
                    "FIRE", "BIRD", "GCOL", "CABIN", "ARC", "OTHER"]
_ICAO_TO_TAXONOMY = {
    "LOCI": "Organizational", "CFIT": "Organizational",
    "RE": "Organizational", "RI": "Organizational",
    "GCOL": "Organizational", "MAC": "Technical", "ENG": "Technical",
    "SYS": "Technical", "FIRE": "Technical", "BIRD": "Environmental",
    "CABIN": "Human", "ARC": "Organizational",
    "PRO": "Organizational",
    "WX": "Environmental", "OTHER": "Organizational",
}

DEFAULT_SEED_COUNTS = {"vsr": 5, "mor": 3, "can": 3, "cap": 3, "survey": 12}


def _tenant_ref(tenant_id: str):
    return get_db().collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id)


def _get_tenant(tenant_id: str) -> Dict[str, Any]:
    snap = _tenant_ref(tenant_id).get()
    if not snap.exists:
        raise ValueError(f"tenant not found: {tenant_id}")
    return snap.to_dict() or {}


# ============================================================================
# Tenant lifecycle status
# ============================================================================

def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as e:
        raise ValueError(f"invalid date '{value}' (expected YYYY-MM-DD)") from e


def derive_tenant_status(contract: Optional[Dict[str, Any]],
                         payment_status: Optional[str] = None,
                         explicit: Optional[str] = None) -> str:
    """Compute the tenant lifecycle status (uppercase).

    Returns one of ``DEMO / TRIAL / ACTIVE / SUSPENDED / RETIRED / CANCELLED / INACTIVE``.

    Rules (an explicit `status` wins over everything):
      * payment_status == 'unpaid'             -> INACTIVE
      * today > contract.end_date              -> INACTIVE (contract expired)
      * today < contract.start_date            -> TRIAL (contract not yet started)
      * otherwise                              -> ACTIVE
    ``DEMO`` is only ever set explicitly (developer/sandbox tenants).
    ``RETIRED`` and ``CANCELLED`` are terminal commercial states.
    """
    if explicit:
        norm = str(explicit).strip().upper().replace("/", "_").replace("-", "_")
        # Handle retired/cancelled alias
        if norm in ("RETIRED_CANCELLED", "RETIRED/CANCELLED"):
            norm = "RETIRED"
        norm = TENANT_STATUS_ALIASES.get(norm, norm)
        if norm not in TENANT_STATUSES:
            raise ValueError(f"invalid status '{explicit}' (allowed: {sorted(TENANT_STATUSES)})")
        return norm

    if str(payment_status or "").strip().lower() == "unpaid":
        return "INACTIVE"

    today = date.today()
    contract = contract or {}
    try:
        start = _parse_date(contract.get("start_date"))
        end = _parse_date(contract.get("end_date"))
    except ValueError:
        start = end = None
    if end and today > end:
        return "INACTIVE"
    if start and today < start:
        return "TRIAL"
    return "ACTIVE"


def update_tenant_status(tenant_id: str, actor: Dict[str, Any],
                         status: Optional[str] = None,
                         contract_start_date: Optional[str] = None,
                         contract_end_date: Optional[str] = None,
                         payment_status: Optional[str] = None,
                         trial_end_date: Optional[str] = None,
                         from_date: Optional[str] = None,
                         to_date: Optional[str] = None) -> Dict[str, Any]:
    """Update a tenant's lifecycle status + contract/payment metadata.

    Status is normalized to ``DEMO / TRIAL / ACTIVE / SUSPENDED / RETIRED / CANCELLED / INACTIVE`` and payment to
    ``paid / unpaid / not_applicable``. `status` may be set explicitly or left
    None to derive it from the contract dates and payment status. `from_date`/`to_date`
    are aliases for `contract_start_date`/`contract_end_date` for commercial UI.
    Returns the updated tenant document.
    """
    tid = _validate_id(tenant_id, "tenant id")
    doc = _get_tenant(tid)

    # from_date/to_date are commercial aliases for contract dates
    if from_date and not contract_start_date:
        contract_start_date = from_date
    if to_date and not contract_end_date:
        contract_end_date = to_date

    if status is not None:
        norm = str(status).strip().upper().replace("/", "_").replace("-", "_")
        if norm in ("RETIRED_CANCELLED", "RETIRED/CANCELLED"):
            norm = "RETIRED"
        norm = TENANT_STATUS_ALIASES.get(norm, norm)
        if norm not in TENANT_STATUSES:
            raise ValueError(f"invalid status '{status}' (allowed: {sorted(TENANT_STATUSES)})")
        status = norm
    if payment_status is not None:
        payment_status = str(payment_status).strip().lower()
        if payment_status in {"not applicable", "n/a", "na"}:
            payment_status = "not_applicable"
        if payment_status not in PAYMENT_STATUSES:
            raise ValueError(f"invalid payment status '{payment_status}' (allowed: {sorted(PAYMENT_STATUSES)})")

    if contract_start_date:
        _parse_date(contract_start_date)
    if contract_end_date:
        _parse_date(contract_end_date)
    if trial_end_date:
        _parse_date(trial_end_date)
    if from_date:
        _parse_date(from_date)
    if to_date:
        _parse_date(to_date)

    contract = dict(doc.get("contract") or {})
    if contract_start_date:
        contract["start_date"] = contract_start_date.strip()
    if contract_end_date:
        contract["end_date"] = contract_end_date.strip()
    if from_date:
        contract["start_date"] = from_date.strip()
        contract["from_date"] = from_date.strip()
    if to_date:
        contract["end_date"] = to_date.strip()
        contract["to_date"] = to_date.strip()
    if trial_end_date:
        contract["trial_end_date"] = trial_end_date.strip()

    resolved = derive_tenant_status(contract, payment_status or doc.get("payment_status"), status)
    now = datetime.now(timezone.utc)

    updates = {
        "status": resolved,
        "active": resolved in ("ACTIVE", "TRIAL", "DEMO"),
        "contract": contract,
        "status_updated_at": now,
        "status_updated_by": actor.get("uid"),
        "updated_at": now,
    }
    if payment_status:
        updates["payment_status"] = payment_status
    # Store commercial date range at top-level for direct queries and UI display
    if from_date:
        updates["from_date"] = from_date.strip()
        updates["contract_from_date"] = from_date.strip()
    elif contract_start_date:
        updates["from_date"] = contract_start_date.strip()
    if to_date:
        updates["to_date"] = to_date.strip()
        updates["contract_to_date"] = to_date.strip()
    elif contract_end_date:
        updates["to_date"] = contract_end_date.strip()

    _tenant_ref(tid).set(updates, merge=True)

    merged = dict(doc)
    merged.update(updates)
    _audit("TENANT_STATUS_UPDATED", actor, tid,
           f"Status set to {resolved} (contract start={contract.get('start_date') or 'n/a'}, "
           f"end={contract.get('end_date') or 'n/a'}, trial_end={contract.get('trial_end_date') or 'n/a'}, "
           f"payment={updates.get('payment_status') or doc.get('payment_status') or 'n/a'})")
    logger.info(f"Tenant {tid} status -> {resolved} by {actor.get('uid')}")
    return merged


MODULE_KEYS = ("module1", "module2", "module3", "module4")


def update_tenant_modules(tenant_id: str, actor: Dict[str, Any],
                          modules: Dict[str, Any]) -> Dict[str, Any]:
    """Persist a tenant's subscribed-module toggles (M1 SMS maturity, M2 hazard
    & risk, M3 PSOE audit, M4 regulator dashboard).

    Values are coerced to booleans, unknown keys are dropped, and the result is
    merged into the tenant doc under ``modules``. Requires SUPER_ADMIN + setup
    key and is audit-logged.
    """
    tid = _validate_id(tenant_id, "tenant id")
    doc = _get_tenant(tid)

    clean = {}
    for key in MODULE_KEYS:
        clean[key] = bool(modules.get(key))

    now = datetime.now(timezone.utc)
    # Merge so undeclared keys (future modules) are preserved on the doc.
    merged_modules = dict(doc.get("modules") or {})
    merged_modules.update(clean)

    updates = {
        "modules": merged_modules,
        "modules_updated_at": now,
        "modules_updated_by": actor.get("uid"),
        "updated_at": now,
    }
    _tenant_ref(tid).set(updates, merge=True)

    merged = dict(doc)
    merged.update(updates)
    merged["modules"] = clean
    _audit(
        "TENANT_MODULES_UPDATED", actor, tid,
        "Modules set to " + ", ".join(f"{k}={v}" for k, v in clean.items()),
    )
    logger.info(f"Tenant {tid} modules -> {clean} by {actor.get('uid')}")
    return merged


# ============================================================================
# Dummy data — PostgreSQL writer
# ============================================================================
# All operational dummy data (VSR/MOR/CAN/CAP/Survey) is written to PostgreSQL
# with `is_demo=True` so the Super-Admin tenants table (which reads Postgres
# counts) reconciles and unseed can remove exactly what this seeder wrote, for
# one tenant or every tenant.     Firestore stays reserved for auth/RBAC/claims.


def _normalize_kinds(kinds: List[str]) -> List[str]:
    out = []
    for k in kinds or []:
        k = (k or "").strip().lower()
        if k not in DEMO_KINDS:
            raise ValueError(f"invalid demo-data kind '{k}' (allowed: {sorted(DEMO_KINDS)})")
        if k not in out:
            out.append(k)
    if not out:
        raise ValueError("at least one kind is required (vsr, mor, can, cap, survey)")
    return out


def _resolve_seed_counts(kinds: List[str], counts: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """Return the per-kind seed counts for the requested kinds.

    Uses the caller-supplied ``counts`` map (per kind) when present and > 0,
    otherwise falls back to ``DEFAULT_SEED_COUNTS``. Counts are clamped to a
    sane upper bound (1..500) to protect the demo database. CAPs are children
    of CANs (FK) so the CAP count cannot exceed the CAN count.
    """
    counts = counts or {}
    resolved: Dict[str, int] = {}
    for k in DEFAULT_SEED_COUNTS:
        val = counts.get(k, DEFAULT_SEED_COUNTS[k])
        try:
            val = max(1, min(int(val), 500))
        except (TypeError, ValueError):
            val = DEFAULT_SEED_COUNTS[k]
        resolved[k] = val
    resolved["cap"] = min(resolved["cap"], resolved["can"])
    return resolved


def _tid(slug: str) -> str:
    """Resolve a tenant slug to its deterministic Postgres uuid."""
    register_tenant(slug)
    return tenant_uuid(slug)


def _risk(sev, prob):
    idx = compute_risk_index(sev, prob)
    return sev, prob, idx, get_risk_level(idx)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _seed_reports(session, tid: str, report_type: str, count: int, base: datetime) -> int:
    for i in range(count):
        sev, prob, idx, lvl = _risk(random.randint(2, 5), random.randint(1, 4))
        created = base - timedelta(days=i)
        session.add(Report(
            tenant_id=uuid.UUID(tid),
            report_type=report_type,
            status="NEW",
            ai_status="PENDING",
            narrative=(
                f"Dummy {'voluntary' if report_type == 'voluntary' else 'mandatory'} safety "
                f"report {i + 1} for demonstration."
            ),
            location=random.choice(["KTM", "Pokhara", "Bhairahawa", "In-flight", "Kathmandu Valley"]),
            occurrence_date=created,
            occurrence_type="Report",
            occurrence_category=random.choice(_ICAO_CATEGORIES),
            severity_level=sev,
            probability_level=prob,
            risk_index=idx,
            risk_level=lvl,
            is_anonymous=random.random() < 0.5,
            is_demo=True,
            created_by=ADMIN_DEMO_CREATOR,
            created_at=created,
            updated_at=created,
        ))
    return count


async def _seed_surveys(session, tid: str, count: int, base: datetime) -> int:
    for i in range(count):
        policy = random.randint(3, 5)
        srm = random.randint(3, 5)
        assurance = random.randint(3, 5)
        promotion = random.randint(3, 5)
        overall = round((policy + srm + assurance + promotion) / 4)
        scored = overall >= 3
        session.add(Survey(
            tenant_id=uuid.UUID(tid),
            submitted_at=base - timedelta(days=i * 2),
            respondent_id=f"demo-respondent-{i + 1}",
            department=random.choice(_DEPARTMENTS),
            employee_category=random.choice(["Pilot", "Cabin Crew", "Engineer", "Ground", "Admin"]),
            years_experience=random.choice(["1-5", "6-10", "11-20", "20+"]),
            language_used="English",
            survey_version="sms-maturity-v1",
            answers={},
            question_scores={},
            element_scores={},
            safety_policy=policy,
            safety_risk_management=srm,
            safety_assurance=assurance,
            safety_promotion=promotion,
            overall_sms_maturity=overall,
            overall_score_pct=float(overall * 20),
            is_demo=True,
            seed_version=ADMIN_DEMO_SEED_VERSION,
        ))
        if scored:
            session.add(SurveyResponse(
                tenant_id=uuid.UUID(tid),
                respondent_id=f"demo-respondent-{i + 1}",
                answers={},
                department=random.choice(_DEPARTMENTS),
                employee_category="Pilot",
                years_experience="11-20",
                language_used="English",
                submitted_at=base - timedelta(days=i * 2),
                survey_version="sms-maturity-v1",
                is_demo=True,
            ))
    return count


async def seed_tenant_demo_data(tenant_id: str, kinds: List[str], actor: Dict[str, Any],
                                counts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Seed dummy VSR/MOR/CAN/CAP/Survey rows into PostgreSQL for one tenant."""
    tid = _validate_id(tenant_id, "tenant id")
    _get_tenant(tid)  # 404 if missing
    kinds = _normalize_kinds(kinds)
    seed_counts = _resolve_seed_counts(kinds, counts)
    n_can = seed_counts["can"] if ("can" in kinds or "cap" in kinds) else 0

    counts_total = {k: 0 for k in kinds}
    base = _now()
    # Canonical UUID string for this tenant slug (e.g. "fixedwing" -> uuid5)
    tuuid = _tid(tid)

    async with session_scope() as session:
        if "vsr" in kinds:
            counts_total["vsr"] = await _seed_reports(session, tuuid, "voluntary", seed_counts.get("vsr", 0), base)
        if "mor" in kinds:
            counts_total["mor"] = await _seed_reports(session, tuuid, "mandatory", seed_counts.get("mor", 0), base)
        if "survey" in kinds:
            counts_total["survey"] = await _seed_surveys(session, tuuid, seed_counts.get("survey", 0), base)

        if "can" in kinds or "cap" in kinds:
            can_ids = []
            for i in range(n_can):
                sev, prob, idx, lvl = _risk(random.randint(2, 4), random.randint(2, 4))
                cat = random.choice(_ICAO_CATEGORIES)
                created = base - timedelta(days=i)
                # Use ICAO category as occurrence_type/adrep for realistic hazard frequency chart
                occ_type = cat  # e.g., CFIT, RE, BIRD, etc. — matches seeded adrep for frequency grouping
                dept = random.choice(_DEPARTMENTS)
                priority = "H" if idx >= 12 else "M" if idx >= 6 else "L"
                function = resolve_function_code(dept, None)
                taxonomy = revalue_taxonomy(_ICAO_TO_TAXONOMY.get(cat, ""))
                hazard = Hazard(
                    tenant_id=uuid.UUID(tuuid),
                    hazard_id=generate_hazard_id(function, priority, created.year, i + 1),
                    function=function,
                    title=f"Dummy hazard {i + 1} for demonstration",
                    description="Dummy demonstration hazard created by the Super-Admin seed tool.",
                    source="Internal Audit",
                    source_id="",
                    occurrence_type=occ_type,
                    adrep_category=cat,
                    threat=f"Demonstration {cat} precursor (Super-Admin seed).",
                    top_event="Demonstration top event (seed data).",
                    taxonomy=taxonomy,
                    severity=sev,
                    probability=prob,
                    risk_index=idx,
                    risk_level=lvl,
                    priority=priority,
                    corrective_action_flag=True,
                    srm_flag=True,
                    status="Open",
                    priority_date=created,
                    status_date=created,
                    srm_conducted=True,
                    analysis_mode="FISHBONE_ONLY",
                    is_demo=True,
                    created_by=ADMIN_DEMO_CREATOR,
                    created_at=created,
                    updated_at=created,
                )
                session.add(hazard)
                await session.flush()
                can = Can(
                    tenant_id=uuid.UUID(tuuid),
                    hazard_id=hazard.id,
                    can_reference=f"CAN-DEMO-{i + 1:03d}",
                    title=f"Dummy corrective action {i + 1}",
                    description=f"Dummy corrective action notice {i + 1}.",
                    required_action="Implement the agreed corrective action and report back.",
                    target_completion_date=created + timedelta(days=random.randint(14, 60)),
                    assigned_to=ADMIN_DEMO_CREATOR,
                    assigned_to_uid=ADMIN_DEMO_CREATOR,
                    department=random.choice(_DEPARTMENTS),
                    priority=random.choice(["High", "Medium", "Low"]),
                    status="Open",
                    issued_by=ADMIN_DEMO_CREATOR,
                    issued_by_uid=ADMIN_DEMO_CREATOR,
                    issued_at=created,
                    is_demo=True,
                    created_by=ADMIN_DEMO_CREATOR,
                    created_at=created,
                    updated_at=created,
                )
                session.add(can)
                await session.flush()
                can_ids.append((can.id, can.can_reference, created))
            counts_total["can"] = len(can_ids)

            if "cap" in kinds:
                n_cap = min(seed_counts["cap"], len(can_ids))
                for j in range(n_cap):
                    can_id, can_ref, created = can_ids[j]
                    session.add(Cap(
                        tenant_id=uuid.UUID(tuuid),
                        can_id=can_id,
                        cap_reference=f"{can_ref}-CAP-{j + 1:03d}",
                        action_plan="Dummy corrective/preventive action plan describing the mitigation steps.",
                        timeline=f"{random.randint(30, 90)} days",
                        resources_required="Manpower and materials per the plan",
                        implementation_plan="Phase the work, verify effectiveness, and close out.",
                        target_completion_date=created + timedelta(days=random.randint(30, 90)),
                        status="In Progress",
                        submitted_by=ADMIN_DEMO_CREATOR,
                        submitted_by_uid=ADMIN_DEMO_CREATOR,
                        submitted_at=created,
                        is_demo=True,
                        created_at=created,
                        updated_at=created,
                    ))
                counts_total["cap"] = n_cap

    _audit("DEMO_DATA_SEED", actor, tid,
           f"Seeded {', '.join(f'{k}={counts_total[k]}' for k in kinds)} for tenant {tid}")
    logger.info(f"Demo data seeded for {tid}: {counts_total}")
    return {"tenant_id": tid, "seeded": counts_total}


async def unseed_tenant_demo_data(tenant_id: str, kinds: List[str], actor: Dict[str, Any]) -> Dict[str, Any]:
    """Remove only the Super-Admin-seeded dummy rows for one tenant.

    FK-safe deletion order (child → parent):
      1. CAPs  (FK cap.can_id → cans.id)
      2. CANs  (FK cans.hazard_id → hazards.id)
      3. Reports (VSR/MOR) + Surveys/SurveyResponses (no FK to hazards)
      4. Hazards (parent, deleted last)
    Within each step the operation is idempotent — zero rows is not an error.
    """
    tid = _validate_id(tenant_id, "tenant id")
    _get_tenant(tid)
    kinds = _normalize_kinds(kinds)

    counts = {k: 0 for k in kinds}
    tuuid = _tid(tid)

    async with session_scope() as session:
        # Step 1: CAPs — child of CANs
        if "can" in kinds or "cap" in kinds:
            r = await session.execute(delete(Cap).where(
                Cap.tenant_id == uuid.UUID(tuuid), Cap.is_demo == True))
            if "cap" in kinds:
                counts["cap"] = r.rowcount

        # Step 2: CANs — child of Hazards
        if "can" in kinds:
            r = await session.execute(delete(Can).where(
                Can.tenant_id == uuid.UUID(tuuid), Can.is_demo == True))
            counts["can"] = r.rowcount

        # Step 3: Reports (VSR/MOR) + Surveys
        if "vsr" in kinds:
            r = await session.execute(delete(Report).where(
                Report.tenant_id == uuid.UUID(tuuid), Report.is_demo == True,
                Report.report_type == "voluntary"))
            counts["vsr"] = r.rowcount
        if "mor" in kinds:
            r = await session.execute(delete(Report).where(
                Report.tenant_id == uuid.UUID(tuuid), Report.is_demo == True,
                Report.report_type == "mandatory"))
            counts["mor"] = r.rowcount
        if "survey" in kinds:
            # SurveyResponse has no FK to Survey in this schema, but delete
            # child responses before parent surveys for safety / future FKs.
            r = await session.execute(delete(SurveyResponse).where(
                SurveyResponse.tenant_id == uuid.UUID(tuuid), SurveyResponse.is_demo == True))
            # Keep the count on "survey" as the SurveyResponse count for backwards
            # compat (existing callers expect counts["survey"]), but also remove
            # parent Survey rows so no orphan survey headers remain.
            counts["survey"] = r.rowcount
            await session.execute(delete(Survey).where(
                Survey.tenant_id == uuid.UUID(tuuid), Survey.is_demo == True))

        # Step 4: Hazards — parent of CANs, deleted last
        if "can" in kinds:
            await session.execute(delete(Hazard).where(
                Hazard.tenant_id == uuid.UUID(tuuid), Hazard.is_demo == True))

    _audit("DEMO_DATA_UNSEED", actor, tid,
           f"Removed {', '.join(f'{k}={counts[k]}' for k in kinds)} dummy rows for tenant {tid}")
    logger.info(f"Demo data unseeded for {tid}: {counts}")
    return {"tenant_id": tid, "removed": counts}


def demo_data_scope(tenant_ids: Optional[List[str]] = None, all_tenants: bool = True) -> List[str]:
    """Resolve the target tenant ids for a seed/unseed action."""
    if tenant_ids:
        return [_validate_id(t, "tenant id") for t in tenant_ids]
    if all_tenants:
        try:
            return [d.id for d in get_db().collection(settings.FIREBASE_COLLECTION_TENANTS).get()]
        except Exception as e:
            logger.error(f"Failed to list tenants for demo-data scope: {e}")
            return []
    return []


# ============================================================================
# Purge ALL demo data (is_demo = true) — cluster wide
# ============================================================================
# Deleting demo data requires FK-safe ordering (child → parent) plus handling
# of child tables that carry no is_demo flag themselves (they only reference
# demo parents through their FKs). Child rows are matched against the id sets
# of demo parents, so real (is_demo=false) tenant data is never touched.
#
# Tables with an is_demo column: hazards, reports, cans, caps, surveys,
# survey_responses, psoe_assessments, state_risk_register, regulatory_reports,
# bow_tie_analyses, risk_register, barrier_register.
# psoe_questions is GLOBAL reference data with no is_demo flag — never purged.


async def _build_purge_steps():
    """Return an ordered list of (table_name, delete_statement) pairs.

    Order is child → parent so FK constraints are satisfied. Subqueries scope
    child deletes to the demo parents' id sets / demo tenants only.
    """
    demo_tenant_ids = union_all(
        select(Hazard.tenant_id).where(Hazard.is_demo == True),
        select(Report.tenant_id).where(Report.is_demo == True),
        select(Survey.tenant_id).where(Survey.is_demo == True),
        select(Can.tenant_id).where(Can.is_demo == True),
        select(Cap.tenant_id).where(Cap.is_demo == True),
    ).scalar_subquery()
    demo_hazards = select(Hazard.id).where(Hazard.is_demo == True).scalar_subquery()
    demo_cans = select(Can.id).where(Can.is_demo == True).scalar_subquery()
    demo_caps = select(Cap.id).where(Cap.is_demo == True).scalar_subquery()
    demo_reports = select(Report.id).where(Report.is_demo == True).scalar_subquery()
    demo_assessments = select(PsoeAssessment.id).where(PsoeAssessment.is_demo == True).scalar_subquery()
    demo_bowties = select(BowTieAnalysis.id).where(BowTieAnalysis.is_demo == True).scalar_subquery()
    demo_rca_entries = (
        select(HazardRcaEntry.id)
        .where(HazardRcaEntry.tenant_id.in_(demo_tenant_ids))
        .scalar_subquery()
    )

    steps: List[tuple] = [
        # RCA subtree (no tenant_id-level is_demo; scoped by demo tenant)
        ("hazard_rca_factors", delete(HazardRcaFactor).where(HazardRcaFactor.entry_id.in_(demo_rca_entries))),
        ("hazard_assessments", delete(HazardAssessment).where(HazardAssessment.entry_id.in_(demo_rca_entries))),
        ("hazard_capas", delete(HazardCapa).where(HazardCapa.entry_id.in_(demo_rca_entries))),
        ("hazard_rca_entries", delete(HazardRcaEntry).where(HazardRcaEntry.tenant_id.in_(demo_tenant_ids))),
        # Children of demo hazards / cans / caps (no is_demo flag)
        ("verifications", delete(Verification).where(
            or_(Verification.hazard_id.in_(demo_hazards), Verification.cap_id.in_(demo_caps)))),
        ("closures", delete(Closure).where(Closure.hazard_id.in_(demo_hazards))),
        ("corrective_actions", delete(CorrectiveAction).where(
            or_(CorrectiveAction.hazard_id.in_(demo_hazards), CorrectiveAction.can_id.in_(demo_cans)))),
        ("flight_diversions", delete(FlightDiversion).where(FlightDiversion.hazard_id.in_(demo_hazards))),
        ("safety_deficiencies", delete(SafetyDeficiency).where(and_(
            SafetyDeficiency.tenant_id.in_(demo_tenant_ids),
            or_(
                SafetyDeficiency.event_id.in_(demo_hazards),
                SafetyDeficiency.event_id.in_(demo_cans),
                SafetyDeficiency.event_id.in_(demo_reports),
            ),
        ))),
        # PSOE (findings first — child of assessments)
        ("psoe_findings", delete(PsoeFinding).where(PsoeFinding.assessment_id.in_(demo_assessments))),
        ("psoe_assessments", delete(PsoeAssessment).where(PsoeAssessment.is_demo == True)),
        # Survey subtree
        ("survey_responses", delete(SurveyResponse).where(SurveyResponse.is_demo == True)),
        ("surveys", delete(Survey).where(Survey.is_demo == True)),
        # CAN/CAP subtree
        ("caps", delete(Cap).where(Cap.is_demo == True)),
        ("cans", delete(Can).where(Can.is_demo == True)),
        ("reports", delete(Report).where(Report.is_demo == True)),
        ("hazards", delete(Hazard).where(Hazard.is_demo == True)),
        # Bow-tie subtree (children first; FKs are CASCADE but delete explicitly
        # so per-table counts are reported)
        ("bow_tie_controls", delete(BowTieControl).where(BowTieControl.bowtie_id.in_(demo_bowties))),
        ("bow_tie_consequences", delete(BowTieConsequence).where(BowTieConsequence.bowtie_id.in_(demo_bowties))),
        ("bow_tie_threats", delete(BowTieThreat).where(BowTieThreat.bowtie_id.in_(demo_bowties))),
        ("bow_tie_analyses", delete(BowTieAnalysis).where(BowTieAnalysis.is_demo == True)),
        # Registers (risk_register FK to bow_tie is SET NULL; barrier_register
        # FKs to bow_tie/controls are SET NULL — already handled above)
        ("risk_register", delete(RiskRegisterEntry).where(RiskRegisterEntry.is_demo == True)),
        ("barrier_register", delete(BarrierRegisterEntry).where(BarrierRegisterEntry.is_demo == True)),
        ("state_risk_register", delete(StateRiskRegisterEntry).where(StateRiskRegisterEntry.is_demo == True)),
        ("regulatory_reports", delete(RegulatoryReport).where(RegulatoryReport.is_demo == True)),
    ]
    return steps


async def purge_all_demo_data(actor: Dict[str, Any]) -> Dict[str, Any]:
    """Delete ALL demo data cluster-wide.

    Irreversible. Removes every row with `is_demo = true` across the Postgres
    tables plus FK-scoped child rows (verifications, closures, corrective
    actions, flight diversions, safety deficiencies, RCA subtree, PSOE
    findings, bow-tie children) of demo parents. Real tenant data
    (is_demo = false) and the global psoe_questions reference bank (no is_demo
    column) are never touched.

    Each table runs in its own transaction so one failing table does not abort
    the rest. Returns per-table deletion counts (or an error string).
    """
    steps = await _build_purge_steps()
    details: Dict[str, Any] = {}
    total = 0
    for table, stmt in steps:
        try:
            async with session_scope() as session:
                result = await session.execute(stmt)
                count = result.rowcount or 0
            details[table] = count
            total += count
        except Exception as e:  # per-table isolation
            logger.error(f"Purge demo data failed for {table}: {e}")
            details[table] = f"Error: {e}"

    _audit(
        "DEMO_DATA_PURGE",
        actor,
        "all",
        f"Purged {total} demo records across {len(details)} tables",
        result="success" if not any(str(v).startswith("Error") for v in details.values()) else "partial",
    )
    logger.info(f"Purged {total} demo records across {len(details)} tables")
    return {"success": True, "deleted_count": total, "details": details}


# ============================================================================
# Export helpers (SUPER_ADMIN) — read-only CSV dumps for setup / audit / purge
# backups. Multi-table dumps are one CSV file with a `# TABLE:<name>  rows=<n>`
# delimiter line before each table's own header + rows, so spreadsheet apps
# still open the file and the block structure survives a raw round-trip.
#
# VSR / MOR live in the same `reports` table discriminated by
# `report_type` = "voluntary" / "mandatory" — the same values the seed / unseed
# / delete logic use (see _seed_reports / unseed_tenant_demo_data).
# ============================================================================

DEMO_EXPORT_KINDS = {"all", "vsr", "mor", "can", "cap", "survey"}

# Tables carrying the is_demo flag — the dumpable demo scope (type=all),
# kept in sync with the purge table list (see _build_purge_steps).
DEMO_EXPORT_TABLES = [
    "hazards",
    "reports",
    "cans",
    "caps",
    "surveys",
    "survey_responses",
    "psoe_assessments",
    "state_risk_register",
    "regulatory_reports",
    "bow_tie_analyses",
    "risk_register",
    "barrier_register",
]


def _registered_models() -> List[Any]:
    """Every mapped ORM class keyed by its table name (single source of truth)."""
    from app.db import db_models

    return list({mapper.class_.__tablename__: mapper.class_
                 for mapper in db_models.Base.registry.mappers}.values())


def _model_for_table(table_name: str):
    target = str(table_name or "").strip().lower()
    for model in _registered_models():
        if getattr(model, "__tablename__", "") == target:
            return model
    return None


def _demo_export_models() -> List[tuple]:
    blocks = []
    for name in DEMO_EXPORT_TABLES:
        model = _model_for_table(name)
        if model is not None:
            blocks.append((name, model))
    return blocks


def _export_tenant_uuid(tenant_id: Optional[str]) -> Optional[uuid.UUID]:
    """Resolve a tenant slug (or raw uuid) to the Postgres tenant uuid."""
    if not tenant_id:
        return None
    t = tenant_id.strip()
    try:
        return uuid.UUID(t)
    except ValueError:
        return uuid.UUID(tenant_uuid(t))


def _csv_repr(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _dicts_to_csv(rows: List[Dict[str, Any]]) -> str:
    """Serialize a list of dicts (RowMapping-friendly) to a CSV string."""
    if not rows:
        return ""
    fieldnames = list(dict.fromkeys(k for r in rows for k in r.keys()))
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: _csv_repr(v) for k, v in r.items()})
    return buf.getvalue()


def _blocks_to_csv(blocks: List[tuple]) -> str:
    """Join per-table CSVs into one file with `# TABLE:<name>` delimiters."""
    parts = []
    for label, text in blocks:
        row_count = max(len(text.splitlines()) - 1, 0) if text else 0
        parts.append(f"# TABLE:{label}  rows={row_count}")
        if text:
            parts.append(text)
    return "\n".join(parts)


async def _export_rows(model, *, where=None, limit: int = 200_000) -> List[Dict[str, Any]]:
    stmt = select(model)
    if where is not None:
        stmt = stmt.where(where)
    stmt = stmt.limit(limit)
    async with session_scope() as session:
        rows = (await session.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]


async def export_demo_data_csv(kind: str = "all",
                               tenant_id: Optional[str] = None) -> Tuple[str, str, int]:
    """CSV dump of is_demo rows scoped by kind (all/vsr/mor/can/cap/survey).

    Returns (csv_text, filename, row_count).
    """
    kind = (kind or "all").strip().lower()
    if kind not in DEMO_EXPORT_KINDS:
        raise ValueError(f"invalid export type '{kind}' (allowed: {sorted(DEMO_EXPORT_KINDS)})")
    tid = _export_tenant_uuid(tenant_id)
    stamp = _now().strftime("%Y-%m-%d_%H-%M-%S")

    def _where(model, *extra):
        conds = []
        if tid is not None and hasattr(model, "tenant_id"):
            conds.append(model.tenant_id == tid)
        for e in extra:
            if e is not None:
                conds.append(e)
        return and_(*conds) if conds else None

    if kind == "vsr":
        rows = await _export_rows(
            Report,
            where=_where(Report, Report.is_demo == True, Report.report_type == "voluntary"),
        )
        return _dicts_to_csv(rows), f"dummy_data_vsr_{stamp}.csv", len(rows)

    if kind == "mor":
        rows = await _export_rows(
            Report,
            where=_where(Report, Report.is_demo == True, Report.report_type == "mandatory"),
        )
        return _dicts_to_csv(rows), f"dummy_data_mor_{stamp}.csv", len(rows)

    if kind == "can":
        rows = await _export_rows(Can, where=_where(Can, Can.is_demo == True))
        return _dicts_to_csv(rows), f"dummy_data_can_{stamp}.csv", len(rows)

    if kind == "cap":
        rows = await _export_rows(Cap, where=_where(Cap, Cap.is_demo == True))
        return _dicts_to_csv(rows), f"dummy_data_cap_{stamp}.csv", len(rows)

    if kind == "survey":
        # Surveys + their child responses — the same scope unseed removes
        # (see unseed_tenant_demo_data).
        blocks, total = [], 0
        for name, model in (("surveys", Survey), ("survey_responses", SurveyResponse)):
            rows = await _export_rows(model, where=_where(model, model.is_demo == True))
            blocks.append((name, _dicts_to_csv(rows)))
            total += len(rows)
        return _blocks_to_csv(blocks), f"dummy_data_survey_{stamp}.csv", total

    # "all" — every is_demo table, block-delimited into one CSV
    blocks, total = [], 0
    for name, model in _demo_export_models():
        rows = await _export_rows(model, where=_where(model, model.is_demo == True))
        blocks.append((name, _dicts_to_csv(rows)))
        total += len(rows)
    return _blocks_to_csv(blocks), f"dummy_data_all_{stamp}.csv", total


async def _purge_counts() -> List[Dict[str, Any]]:
    """Per-table rows purge_all_demo_data WOULD delete, mirroring its scoping.

    Deliberately mirrors the subquery scopes of _build_purge_steps so the
    summary always matches what the purge removes.
    """
    demo_tenant_ids = union_all(
        select(Hazard.tenant_id).where(Hazard.is_demo == True),
        select(Report.tenant_id).where(Report.is_demo == True),
        select(Survey.tenant_id).where(Survey.is_demo == True),
        select(Can.tenant_id).where(Can.is_demo == True),
        select(Cap.tenant_id).where(Cap.is_demo == True),
    ).scalar_subquery()
    demo_hazards = select(Hazard.id).where(Hazard.is_demo == True).scalar_subquery()
    demo_cans = select(Can.id).where(Can.is_demo == True).scalar_subquery()
    demo_caps = select(Cap.id).where(Cap.is_demo == True).scalar_subquery()
    demo_reports = select(Report.id).where(Report.is_demo == True).scalar_subquery()
    demo_assessments = select(PsoeAssessment.id).where(PsoeAssessment.is_demo == True).scalar_subquery()
    demo_bowties = select(BowTieAnalysis.id).where(BowTieAnalysis.is_demo == True).scalar_subquery()
    demo_rca_entries = (
        select(HazardRcaEntry.id)
        .where(HazardRcaEntry.tenant_id.in_(demo_tenant_ids))
        .scalar_subquery()
    )

    spec: List[tuple] = [
        ("hazard_rca_factors", select(func.count()).select_from(HazardRcaFactor).where(HazardRcaFactor.entry_id.in_(demo_rca_entries))),
        ("hazard_assessments", select(func.count()).select_from(HazardAssessment).where(HazardAssessment.entry_id.in_(demo_rca_entries))),
        ("hazard_capas", select(func.count()).select_from(HazardCapa).where(HazardCapa.entry_id.in_(demo_rca_entries))),
        ("hazard_rca_entries", select(func.count()).select_from(HazardRcaEntry).where(HazardRcaEntry.tenant_id.in_(demo_tenant_ids))),
        ("verifications", select(func.count()).select_from(Verification).where(
            or_(Verification.hazard_id.in_(demo_hazards), Verification.cap_id.in_(demo_caps)))),
        ("closures", select(func.count()).select_from(Closure).where(Closure.hazard_id.in_(demo_hazards))),
        ("corrective_actions", select(func.count()).select_from(CorrectiveAction).where(
            or_(CorrectiveAction.hazard_id.in_(demo_hazards), CorrectiveAction.can_id.in_(demo_cans)))),
        ("flight_diversions", select(func.count()).select_from(FlightDiversion).where(FlightDiversion.hazard_id.in_(demo_hazards))),
        ("safety_deficiencies", select(func.count()).select_from(SafetyDeficiency).where(and_(
            SafetyDeficiency.tenant_id.in_(demo_tenant_ids),
            or_(
                SafetyDeficiency.event_id.in_(demo_hazards),
                SafetyDeficiency.event_id.in_(demo_cans),
                SafetyDeficiency.event_id.in_(demo_reports),
            ),
        ))),
        ("psoe_findings", select(func.count()).select_from(PsoeFinding).where(PsoeFinding.assessment_id.in_(demo_assessments))),
        ("psoe_assessments", select(func.count()).select_from(PsoeAssessment).where(PsoeAssessment.is_demo == True)),
        ("survey_responses", select(func.count()).select_from(SurveyResponse).where(SurveyResponse.is_demo == True)),
        ("surveys", select(func.count()).select_from(Survey).where(Survey.is_demo == True)),
        ("caps", select(func.count()).select_from(Cap).where(Cap.is_demo == True)),
        ("cans", select(func.count()).select_from(Can).where(Can.is_demo == True)),
        ("reports", select(func.count()).select_from(Report).where(Report.is_demo == True)),
        ("hazards", select(func.count()).select_from(Hazard).where(Hazard.is_demo == True)),
        ("bow_tie_controls", select(func.count()).select_from(BowTieControl).where(BowTieControl.bowtie_id.in_(demo_bowties))),
        ("bow_tie_consequences", select(func.count()).select_from(BowTieConsequence).where(BowTieConsequence.bowtie_id.in_(demo_bowties))),
        ("bow_tie_threats", select(func.count()).select_from(BowTieThreat).where(BowTieThreat.bowtie_id.in_(demo_bowties))),
        ("bow_tie_analyses", select(func.count()).select_from(BowTieAnalysis).where(BowTieAnalysis.is_demo == True)),
        ("risk_register", select(func.count()).select_from(RiskRegisterEntry).where(RiskRegisterEntry.is_demo == True)),
        ("barrier_register", select(func.count()).select_from(BarrierRegisterEntry).where(BarrierRegisterEntry.is_demo == True)),
        ("state_risk_register", select(func.count()).select_from(StateRiskRegisterEntry).where(StateRiskRegisterEntry.is_demo == True)),
        ("regulatory_reports", select(func.count()).select_from(RegulatoryReport).where(RegulatoryReport.is_demo == True)),
    ]

    counts: List[Dict[str, Any]] = []
    async with session_scope() as session:
        for table, stmt in spec:
            n = (await session.execute(stmt)).scalar_one()
            counts.append({"table": table, "demo_rows": n})
    return counts


async def export_purge_summary_csv() -> Tuple[str, str, int]:
    """CSV of the per-table rows purge_all_demo_data would delete."""
    stamp = _now().strftime("%Y-%m-%d_%H-%M-%S")
    counts = await _purge_counts()
    total = sum(int(r["demo_rows"]) for r in counts)
    return _dicts_to_csv(counts), f"purge_summary_{stamp}.csv", total


async def export_all_tables_csv() -> Tuple[str, str, int]:
    """Full dump of every operational Postgres table (all rows, demo + real)."""
    stamp = _now().strftime("%Y-%m-%d_%H-%M-%S")
    blocks, total = [], 0
    for model in sorted(_registered_models(), key=lambda m: m.__tablename__):
        rows = await _export_rows(model)
        blocks.append((model.__tablename__, _dicts_to_csv(rows)))
        total += len(rows)
    return _blocks_to_csv(blocks), f"all_tables_{stamp}.csv", total


async def export_single_table_csv(table_name: str) -> Tuple[str, str, int]:
    """Full dump of one table (all rows, demo + real). Unknown table -> KeyError."""
    model = _model_for_table(table_name)
    if model is None:
        raise KeyError(f"unknown table '{table_name}'")
    stamp = _now().strftime("%Y-%m-%d_%H-%M-%S")
    rows = await _export_rows(model)
    return _dicts_to_csv(rows), f"{model.__tablename__}_{stamp}.csv", len(rows)


# ============================================================================
# Unified purge — is_demo rows in Postgres + Firestore setup surfaces
# ============================================================================
# Operational demo rows live in Postgres (is_demo=true) and are fully handled by
# purge_all_demo_data. Firestore holds the surfaces the Super-Admin panel wrote:
# the `audit_logs` history, the `psoe_assessments` baseline docs (created by
# "production-setup") and the `state` ICAO SSP reference tree. Tenants,
# regulators, users and the global `psoe_questions` reference bank are preserved.

FIRESTORE_PURGE_COLLECTIONS = ["audit_logs", "psoe_assessments", "state"]


def _delete_firestore_doc_tree(doc_ref, _visited=None, _count=None) -> None:
    """Delete a Firestore doc and every subcollection doc (recursive)."""
    if _visited is None:
        _visited = set()
    if _count is None:
        _count = [0]
    key = ":".join(getattr(doc_ref, "path", None) or [getattr(doc_ref, "id", str(id(doc_ref)))])
    if key in _visited:
        return
    _visited.add(key)
    for sub in doc_ref.collections():
        for snap in sub.get():
            _delete_firestore_doc_tree(snap.reference, _visited, _count)
    doc_ref.delete()
    _count[0] += 1


async def purge_firestore_demo_data(actor: Dict[str, Any]) -> Dict[str, Any]:
    """Delete Firestore demo/setup surfaces, preserving authority/identity data."""
    db = get_db()
    deleted: Dict[str, int] = {}
    total = 0

    # audit_logs — setup/action history; wiped in full.
    count = 0
    for snap in db.collection(settings.FIREBASE_COLLECTION_AUDIT_LOGS).get():
        snap.reference.delete()
        count += 1
    if count:
        deleted["audit_logs"] = count
    total += count

    # psoe_assessments — only the Production-Setup baselines (created_by marker).
    count = 0
    for snap in db.collection("psoe_assessments").get():
        data = snap.to_dict() or {}
        if (data.get("created_by") == "production-setup"
                or str(snap.id).endswith("-baseline-completed")
                or str(snap.id).endswith("-baseline-draft")):
            snap.reference.delete()
            count += 1
    if count:
        deleted["psoe_assessments"] = count
    total += count

    # state — the ICAO SSP reference tree (docs + subcollections).
    count = 0
    for snap in db.collection(STATE_COLLECTION).get():
        counter = [0]
        _delete_firestore_doc_tree(snap.reference, _count=counter)
        count += counter[0]
    if count:
        deleted["state"] = count
    total += count

    details = ", ".join(f"{k}={v}" for k, v in sorted(deleted.items())) or "none"
    _audit("DEMO_DATA_PURGE_FIRESTORE", actor, "all",
           f"Purged {total} Firestore docs ({details})")
    logger.info(f"Firestore demo surfaces purged: {deleted} ({total} total)")
    return {"deleted": deleted, "total": total}


async def purge_all_demo_data_unified(actor: Dict[str, Any]) -> Dict[str, Any]:
    """Purge demo data from BOTH Postgres (is_demo) AND Firestore surfaces.

    Firestore is purged first so the Postgres DEMO_DATA_PURGE audit entry
    (written by purge_all_demo_data) survives in the freshly-cleared
    audit_logs, alongside the DEMO_DATA_PURGE_FIRESTORE entry written above.
    """
    firestore_result = await purge_firestore_demo_data(actor)
    postgres_result = await purge_all_demo_data(actor)

    total = (
        int(postgres_result.get("deleted_count", 0) or 0)
        + int(firestore_result.get("total", 0) or 0)
    )
    return {
        "success": True,
        "postgres": postgres_result,
        "firestore": firestore_result,
        "deleted_count": total,
    }
