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
from app.firebase import get_auth, get_db
from app.models.hazard import revalue_taxonomy
from app.services.hazard_service import generate_hazard_id, resolve_function_code
from app.db.ids import register_tenant, tenant_uuid
from app.db import pg
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
    Tenant,
    Verification,
)
from app.services.risk_matrix import compute_risk_index, get_risk_level
from app.services.production_seed import _audit, _is_regulator_doc, _validate_id
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

# Severity string vocabulary expected by dashboard metrics (Low/Medium/High/
# Critical) derived from the ICAO 1-5 severity scale the seeder samples.
_SEVERITY_STRING_BY_LEVEL = {1: "Low", 2: "Low", 3: "Medium", 4: "High", 5: "Critical"}

# Realistic, human-readable occurrence types so the hazard-frequency chart and
# top-hazards view show distinct hazard categories instead of a generic
# "Report" bar.
_OCCURRENCE_TYPE_LABELS = [
    "Runway Excursion", "Runway Incursion", "Bird Strike",
    "System/Component Failure", "Powerplant Failure", "Weather Encounter",
    "Cabin Safety Event", "Procedural Deviation", "ATC Operational Incident",
    "Abnormal Runway Contact", "Ground Collision", "Airborne Conflict",
]

DEFAULT_SEED_COUNTS = {"vsr": 5, "mor": 3, "can": 3, "cap": 3, "survey": 12}

# ---------------------------------------------------------------------------
# Trailing/windowed 12-month demo dataset
# ---------------------------------------------------------------------------
# Realistic monthly volumes so dashboard trends, KPIs and regulatory reports
# have live-looking content (~80 VSR / ~19 MOR / ~16 CAN / ~12 CAP).
_MONTHLY_VSR = [5, 6, 5, 7, 6, 7, 6, 7, 8, 7, 8, 8]
_MONTHLY_MOR = [2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 2]
_MONTHLY_CAN = [1, 1, 2, 1, 1, 2, 1, 1, 2, 1, 1, 2]
_MONTHLY_CAP = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
# SMS-maturity surveys — ≈17/month so each tenant has 200+ responses for the
# survey analysis / maturity dashboards.
_MONTHLY_SURVEYS = [16, 17, 18, 17, 16, 18, 17, 17, 18, 17, 16, 17]

# ICAO category distribution — bird-strike / powerplant / runway-excursion
# heavy, as in a typical airline operation.
_ICAO_CATEGORY_DISTRIBUTION = [
    ("BIRD", 15), ("ENG", 12), ("RE", 12), ("WX", 10), ("SYS", 10),
    ("PRO", 10), ("CABIN", 8), ("GCOL", 8), ("LOCI", 5), ("CFIT", 5),
    ("OTHER", 5),
]
# Severity distribution: Critical 10% / High 30% / Medium 40% / Low 20%.
_SEVERITY_DISTRIBUTION = [(5, 10), (4, 30), (3, 40), (2, 20)]

# Human-readable occurrence label per ICAO category so hazard-frequency
# grouping stays coherent with the category shown in tables/filters.
_OCCURRENCE_TYPE_FOR_ICAO = {
    "BIRD": "Bird Strike",
    "ENG": "Powerplant Failure",
    "RE": "Runway Excursion",
    "RI": "Runway Incursion",
    "WX": "Weather Encounter",
    "SYS": "System/Component Failure",
    "PRO": "Procedural Deviation",
    "CABIN": "Cabin Safety Event",
    "GCOL": "Ground Collision",
    "LOCI": "Airborne Conflict",
    "CFIT": "Abnormal Runway Contact",
    "ARC": "ATC Operational Incident",
    "MAC": "Airborne Conflict",
    "FIRE": "System/Component Failure",
    "OTHER": "ATC Operational Incident",
}

# Rotor-wing flavour so Annapurna Helicopter gets helicopter-specific occurrence
# types / hazards instead of generic fixed-wing content.
_HELICOPTER_OCCURRENCE_LABELS = {
    "BIRD": "Bird Strike",
    "ENG": "Powerplant / Engine Failure",
    "RE": "Forced Landing",
    "RI": "Loss of Tail Rotor Effectiveness",
    "WX": "Mountain Valley Clouding",
    "SYS": "Main Rotor / Transmission Failure",
    "PRO": "SOP Deviation (Mountain Ops)",
    "CABIN": "Passenger Handling Event",
    "GCOL": "Ground / Skid Contact",
    "LOCI": "Airborne Conflict",
    "CFIT": "Terrain Proximity / Hard Landing",
    "ARC": "Uncoordinated Mountain Approach",
    "MAC": "Mountain Ridge Encounter",
    "FIRE": "Electrical / Battery Fire Risk",
    "OTHER": "Density Altitude Encounter",
}

# Fixed-wing flavour for Sita Air (no helicopter content).
_FIXED_WING_OCCURRENCE_LABELS = {
    "BIRD": "Bird Strike",
    "ENG": "Powerplant Failure",
    "RE": "Runway Excursion",
    "RI": "Runway Incursion",
    "WX": "Weather Encounter",
    "SYS": "System/Component Failure",
    "PRO": "Procedural Deviation",
    "CABIN": "Cabin Safety Event",
    "GCOL": "Ground Collision",
    "LOCI": "Airborne Conflict",
    "CFIT": "Abnormal Runway Contact",
    "ARC": "ATC Operational Incident",
    "MAC": "Airborne Conflict",
    "FIRE": "System/Component Failure",
    "OTHER": "ATC Operational Incident",
}

_DEFAULT_LOCATIONS = ["KTM", "Pokhara", "Bhairahawa", "In-flight", "Kathmandu Valley"]

# Per-tenant operational profiles driving realistic 12-month demo content:
# Sita Air is fixed-wing only (DHC-6 Twin Otter / Dornier Do 228), Annapurna
# Helicopter is rotor-wing only (AS350B3e / H125 / Bell 407) with mountain
# helipad routes. Unknown tenants fall back to generic content with no
# aircraft detail.
_DEMO_TENANT_PROFILES = {
    "sita-air": {
        "category": "Aeroplane",
        "fleet": ["de Havilland DHC-6 Twin Otter", "Dornier Do 228"],
        "registrations": ["9N-AMK", "9N-AML", "9N-AMM", "9N-AMN", "9N-AMP", "9N-AMQ"],
        "locations": [
            "Kathmandu (VNKT)", "Pokhara (VNPK)", "Simikot (VNSK)", "Dolpa (VNDP)",
            "Lukla (VNLK)", "Taplejung (VNTJ)", "Janakpur (VNJP)", "Bharatpur (VNBG)",
            "In-flight (mountain sector)",
        ],
        "occurrence_labels": _FIXED_WING_OCCURRENCE_LABELS,
    },
    "annapurna-heli": {
        "category": "Helicopter",
        "fleet": ["Eurocopter AS350B3e", "Airbus H125", "Bell 407GXi"],
        "registrations": ["9N-AHN", "9N-AHO", "9N-AHP", "9N-AHR", "9N-AHT"],
        "locations": [
            "Kathmandu (VNKT) Helipad", "Lukla (VNLK)", "Jomsom (VNJS)", "Manang LZ",
            "Everest Base Camp LZ", "Kangel Danda (VNDG)", "Simikot (VNSK)",
            "Annapurna Base Camp LZ", "Langtang (VNLT)",
            "In-flight (high mountain sector)", "In-flight (autorotation sector)",
        ],
        "occurrence_labels": _HELICOPTER_OCCURRENCE_LABELS,
    },
}


def _get_tenant(tenant_id: str) -> Dict[str, Any]:
    doc = pg.fetch_by(Tenant, "slug", tenant_id)
    if doc is None:
        raise ValueError(f"tenant not found: {tenant_id}")
    return doc


def _set_tenant(tenant_id: str, updates: Dict[str, Any]) -> None:
    pg.update(Tenant, "slug", tenant_id, dict(updates))
    try:
        get_db().collection(settings.FIREBASE_COLLECTION_TENANTS).document(
            tenant_id
        ).set(dict(updates), merge=True)
    except Exception as e:
        logger.warning(f"Tenant mirror update failed ({tenant_id}): {e}")


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

    _set_tenant(tid, updates)

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
    _set_tenant(tid, updates)

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


async def _resolve_tenant_uuid(session, slug: str) -> str:
    """Canonical uuid5('tenant:'+slug) id for a tenant, verified against the
    tenants row so dummy data is never written under an id with no record.

    Raises ValueError when the tenant is missing or its stored id drifted from
    the canonical value (repair with scripts/migrate_tenant_ids.py).
    """
    expected = tenant_uuid(slug)
    register_tenant(slug)
    row_id = (await session.execute(
        select(Tenant.id).where(Tenant.slug == slug)
    )).scalar_one_or_none()
    if row_id is None:
        raise ValueError(f"tenant not found: {slug}")
    if str(row_id) != expected:
        raise ValueError(
            f"tenant '{slug}' id drift: stored {row_id} != canonical {expected}; "
            "run scripts/migrate_tenant_ids.py"
        )
    return expected


def _risk(sev, prob):
    idx = compute_risk_index(sev, prob)
    return sev, prob, idx, get_risk_level(idx)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _weighted_pick(pairs: List[Tuple[Any, int]]) -> Any:
    """Return one element from ``pairs`` randomly weighted by each weight."""
    total = sum(int(w) for _, w in pairs)
    r = random.uniform(0, total)
    upto = 0.0
    for val, w in pairs:
        upto += int(w)
        if r <= upto:
            return val
    return pairs[-1][0]


async def _seed_reports(session, tid: str, report_type: str, count: int, base: datetime,
                        category_picker=None, severity_picker=None,
                        locations=None, label_map=None, aircraft=None) -> int:
    for i in range(count):
        sev = severity_picker() if severity_picker else random.randint(2, 5)
        sev, prob, idx, lvl = _risk(sev, random.randint(1, 4))
        created = base - timedelta(days=i)
        occ_cat = category_picker() if category_picker else random.choice(_ICAO_CATEGORIES)
        loc = random.choice(locations) if locations else random.choice(_DEFAULT_LOCATIONS)
        registration = None
        aircraft_make = None
        aircraft_model = None
        aircraft_category = None
        if aircraft:
            aircraft_model = random.choice(aircraft["fleet"])
            aircraft_make = aircraft_model.split(" ", 1)[0]
            aircraft_category = aircraft["category"]
            registration = random.choice(aircraft["registrations"])
        session.add(Report(
            tenant_id=uuid.UUID(tid),
            report_type=report_type,
            status="NEW",
            ai_status="PENDING",
            narrative=(
                f"Dummy {'voluntary' if report_type == 'voluntary' else 'mandatory'} safety "
                f"report {i + 1} for demonstration"
                + (f" ({registration} {aircraft_model})." if registration else ".")
            ),
            location=loc,
            occurrence_date=created,
            aircraft_registration=registration,
            aircraft_make=aircraft_make,
            aircraft_model=aircraft_model,
            aircraft_category=aircraft_category,
            # Vary the occurrence type across realistic ICAO hazards so the
            # hazard-frequency chart / top-hazards dashboard show real
            # categories rather than a single generic "Report" bar.
            occurrence_type=(label_map or _OCCURRENCE_TYPE_FOR_ICAO).get(occ_cat) or random.choice(_OCCURRENCE_TYPE_LABELS),
            occurrence_category=occ_cat,
            # The severity string drives the risk distribution + high/critical
            # KPI buckets; derive it from the numeric level that is also stored.
            severity=_SEVERITY_STRING_BY_LEVEL[sev],
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


async def _seed_surveys(session, tid: str, count: int, base: datetime,
                        progress: Optional[float] = None) -> int:
    for i in range(count):
        # Optional maturity progression (0 → 1): later surveys score higher so
        # the monthly SMS-maturity history shows a believable improvement trend.
        lo_p = lo_s = lo_a = lo_m = 3
        if progress is not None:
            lo = min(5, 3 + round(2 * max(0.0, min(progress, 1.0))))
            lo_p = lo_s = lo_a = lo_m = lo
        policy = random.randint(lo_p, 5)
        srm = random.randint(lo_s, 5)
        assurance = random.randint(lo_a, 5)
        promotion = random.randint(lo_m, 5)
        overall = round((policy + srm + assurance + promotion) / 4)
        scored = overall >= 3
        submitted_at = base - timedelta(days=i)
        session.add(Survey(
            tenant_id=uuid.UUID(tid),
            submitted_at=submitted_at,
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
                submitted_at=submitted_at,
                survey_version="sms-maturity-v1",
                is_demo=True,
            ))
    return count


async def _seed_hazards_cans_caps(session, tuuid: str, n_can: int, n_cap: int,
                                  base: datetime, start_seq: int = 0,
                                  label_map=None) -> Tuple[int, int]:
    """Seed ``n_can`` hazard+CAN pairs and ``n_cap`` CAPs attached to the first
    CANs. Returns ``(seeded_can, seeded_cap)``.

    ``start_seq`` offsets the generated CAN/hazard sequence numbers so ids stay
    unique across repeated calls (e.g. one call per month in the 12-month
    dataset) — ``generate_hazard_id`` scopes its sequence per function+year.
    """
    can_ids = []
    for i in range(n_can):
        sev, prob, idx, lvl = _risk(random.randint(2, 4), random.randint(2, 4))
        cat = random.choice(_ICAO_CATEGORIES)
        created = base - timedelta(days=i)
        # Use ICAO category as occurrence_type/adrep for realistic hazard frequency chart
        occ_type = (label_map or _OCCURRENCE_TYPE_FOR_ICAO).get(cat) or cat
        dept = random.choice(_DEPARTMENTS)
        priority = "H" if idx >= 12 else "M" if idx >= 6 else "L"
        function = resolve_function_code(dept, None)
        taxonomy = revalue_taxonomy(_ICAO_TO_TAXONOMY.get(cat, ""))
        seq = start_seq + i + 1
        hazard = Hazard(
            tenant_id=uuid.UUID(tuuid),
            hazard_id=generate_hazard_id(function, priority, created.year, seq),
            function=function,
            title=f"Dummy hazard {seq} for demonstration",
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
            can_reference=f"CAN-DEMO-{seq:03d}",
            title=f"Dummy corrective action {seq}",
            description=f"Dummy corrective action notice {seq}.",
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

    seeded_cap = 0
    for j in range(min(n_cap, len(can_ids))):
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
        seeded_cap += 1
    return len(can_ids), seeded_cap


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

    async with session_scope() as session:
        # Canonical (and tenants-row-verified) UUID string for this slug.
        tuuid = await _resolve_tenant_uuid(session, tid)
        if "vsr" in kinds:
            counts_total["vsr"] = await _seed_reports(session, tuuid, "voluntary", seed_counts.get("vsr", 0), base)
        if "mor" in kinds:
            counts_total["mor"] = await _seed_reports(session, tuuid, "mandatory", seed_counts.get("mor", 0), base)
        if "survey" in kinds:
            counts_total["survey"] = await _seed_surveys(session, tuuid, seed_counts.get("survey", 0), base)

        if "can" in kinds or "cap" in kinds:
            n_cap = seed_counts["cap"] if "cap" in kinds else 0
            n_can_seeded, n_cap_seeded = await _seed_hazards_cans_caps(
                session, tuuid, n_can, n_cap, base)
            if "can" in kinds:
                counts_total["can"] = n_can_seeded
            if "cap" in kinds:
                counts_total["cap"] = n_cap_seeded

    _audit("DEMO_DATA_SEED", actor, tid,
           f"Seeded {', '.join(f'{k}={counts_total[k]}' for k in kinds)} for tenant {tid}")
    logger.info(f"Demo data seeded for {tid}: {counts_total}")
    return {"tenant_id": tid, "seeded": counts_total}


async def generate_12_month_data(tenant_id: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    """Replace a tenant's demo dataset with a realistic 12-month demo set.

    Unseeds existing demo VSR/MOR/CAN/CAP/Survey rows, then seeds ~100 reports
    (≈80 VSR / ~20 MOR), ≈16 CANs, ~12 CAPs and ~204 SMS-maturity surveys
    (≈17/month, maturity improving across the window) spread across a randomly
    chosen 12-month window inside Jan 2026 – Sep 2027. ICAO categories and
    severities are sampled from realistic weighted distributions so dashboard
    trends, KPIs and regulatory reports have live-looking content.
    """
    tid = _validate_id(tenant_id, "tenant id")
    tenant_doc = _get_tenant(tid)

    removed = await unseed_tenant_demo_data(
        tid, ["vsr", "mor", "can", "cap", "survey"], actor)

    # Per-tenant operational realism: Sita Air (fixed-wing) vs Annapurna
    # Helicopter (rotor-wing). Unknown tenants fall back to generic content.
    profile = _DEMO_TENANT_PROFILES.get(
        tenant_doc.get("slug") or tenant_doc.get("tenant_id") or tid, {})
    locations = profile.get("locations")
    label_map = profile.get("occurrence_labels")
    aircraft = profile or None

    # Random 12-month window: start anywhere from Jan 2026 (offset 0) up to
    # Oct 2026 (offset 9) so the last month never exceeds Sep 2027.
    start_y, start_m = (2026, 1 + random.randint(0, 9))

    seeded = {"vsr": 0, "mor": 0, "can": 0, "cap": 0, "survey": 0}
    seq = 0

    async with session_scope() as session:
        tuuid = await _resolve_tenant_uuid(session, tid)
        for idx in range(12):
            m = start_m + idx
            y = start_y
            if m > 12:
                m -= 12
                y += 1
            # Cluster reports mid-month so an entire month's batch stays inside
            # the month boundary (max backdate is 7 days).
            base = datetime(y, m, 1, tzinfo=timezone.utc) + timedelta(days=random.randint(10, 18))

            seeded["vsr"] += await _seed_reports(
                session, tuuid, "voluntary", _MONTHLY_VSR[idx], base,
                category_picker=lambda: _weighted_pick(_ICAO_CATEGORY_DISTRIBUTION),
                severity_picker=lambda: _weighted_pick(_SEVERITY_DISTRIBUTION),
                locations=locations, label_map=label_map, aircraft=aircraft,
            )
            seeded["mor"] += await _seed_reports(
                session, tuuid, "mandatory", _MONTHLY_MOR[idx], base,
                category_picker=lambda: _weighted_pick(_ICAO_CATEGORY_DISTRIBUTION),
                severity_picker=lambda: _weighted_pick(_SEVERITY_DISTRIBUTION),
                locations=locations, label_map=label_map, aircraft=aircraft,
            )
            n_can_seeded, n_cap_seeded = await _seed_hazards_cans_caps(
                session, tuuid, _MONTHLY_CAN[idx], _MONTHLY_CAP[idx], base, start_seq=seq,
                label_map=label_map)
            seq += _MONTHLY_CAN[idx]
            seeded["can"] += n_can_seeded
            seeded["cap"] += n_cap_seeded
            # ~17 SMS-maturity surveys per month (scored 3→5, improving across
            # the window). Base near month-end so even the last backdated
            # response stays inside the month → clean monthly history buckets.
            survey_base = datetime(y, m, 1, tzinfo=timezone.utc) + timedelta(days=random.randint(18, 24))
            seeded["survey"] += await _seed_surveys(
                session, tuuid, _MONTHLY_SURVEYS[idx], survey_base, progress=idx / 11.0)

    total_reports = seeded["vsr"] + seeded["mor"]
    removed_total = sum(removed.get("removed", {}).values())
    _audit("DEMO_DATA_SEED_12M", actor, tid,
           f"Seeded 12-month demo set {start_y:04d}-{start_m:02d}→{y:04d}-{m:02d}: "
           f"{total_reports} reports, {seeded['can']} CANs, {seeded['cap']} CAPs, "
           f"{seeded['survey']} surveys (replaced {removed_total} demo rows)")
    logger.info(f"12-month demo data seeded for {tid}: {seeded}")
    return {
        "tenant_id": tid,
        "seeded": seeded,
        "removed": removed.get("removed", {}),
        "total_reports": total_reports,
        "window": f"{start_y:04d}-{start_m:02d} to {y:04d}-{m:02d}",
    }


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

    async with session_scope() as session:
        tuuid = await _resolve_tenant_uuid(session, tid)
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
            return [
                d.get("slug") or d.get("tenant_id") or d.get("id")
                for d in pg.fetch_all(Tenant)
            ]
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


async def _build_purge_steps(tenant_uuids: Optional[List[uuid.UUID]] = None):
    """Return an ordered list of (table_name, delete_statement) pairs.

    Order is child → parent so FK constraints are satisfied. Subqueries scope
    child deletes to the demo parents' id sets / demo tenants only.

    When `tenant_uuids` is provided every row for those tenants is deleted
    (regardless of is_demo) so a demo tenant can be fully removed; otherwise
    only `is_demo = true` rows are targeted (the cluster-wide purge).
    """
    if tenant_uuids is not None:
        targets = tuple(tenant_uuids)
        demo_tenant_ids: Any = targets
        is_demo_scope = False
        demo_hazards = select(Hazard.id).where(Hazard.tenant_id.in_(targets)).scalar_subquery()
        demo_cans = select(Can.id).where(Can.tenant_id.in_(targets)).scalar_subquery()
        demo_caps = select(Cap.id).where(Cap.tenant_id.in_(targets)).scalar_subquery()
        demo_reports = select(Report.id).where(Report.tenant_id.in_(targets)).scalar_subquery()
        demo_assessments = select(PsoeAssessment.id).where(PsoeAssessment.tenant_id.in_(targets)).scalar_subquery()
        demo_bowties = select(BowTieAnalysis.id).where(BowTieAnalysis.tenant_id.in_(targets)).scalar_subquery()
    else:
        demo_tenant_ids = union_all(
            select(Hazard.tenant_id).where(Hazard.is_demo == True),
            select(Report.tenant_id).where(Report.is_demo == True),
            select(Survey.tenant_id).where(Survey.is_demo == True),
            select(Can.tenant_id).where(Can.is_demo == True),
            select(Cap.tenant_id).where(Cap.is_demo == True),
        ).scalar_subquery()
        is_demo_scope = True
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

    def parent_scope(model):
        return model.is_demo == True if is_demo_scope else model.tenant_id.in_(demo_tenant_ids)

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
        ("psoe_assessments", delete(PsoeAssessment).where(parent_scope(PsoeAssessment))),
        # Survey subtree
        ("survey_responses", delete(SurveyResponse).where(parent_scope(SurveyResponse))),
        ("surveys", delete(Survey).where(parent_scope(Survey))),
        # CAN/CAP subtree
        ("caps", delete(Cap).where(parent_scope(Cap))),
        ("cans", delete(Can).where(parent_scope(Can))),
        ("reports", delete(Report).where(parent_scope(Report))),
        ("hazards", delete(Hazard).where(parent_scope(Hazard))),
        # Bow-tie subtree (children first; FKs are CASCADE but delete explicitly
        # so per-table counts are reported)
        ("bow_tie_controls", delete(BowTieControl).where(BowTieControl.bowtie_id.in_(demo_bowties))),
        ("bow_tie_consequences", delete(BowTieConsequence).where(BowTieConsequence.bowtie_id.in_(demo_bowties))),
        ("bow_tie_threats", delete(BowTieThreat).where(BowTieThreat.bowtie_id.in_(demo_bowties))),
        ("bow_tie_analyses", delete(BowTieAnalysis).where(parent_scope(BowTieAnalysis))),
        # Registers (risk_register FK to bow_tie is SET NULL; barrier_register
        # FKs to bow_tie/controls are SET NULL — already handled above)
        ("risk_register", delete(RiskRegisterEntry).where(parent_scope(RiskRegisterEntry))),
        ("barrier_register", delete(BarrierRegisterEntry).where(parent_scope(BarrierRegisterEntry))),
        ("state_risk_register", delete(StateRiskRegisterEntry).where(parent_scope(StateRiskRegisterEntry))),
        ("regulatory_reports", delete(RegulatoryReport).where(parent_scope(RegulatoryReport))),
        # Master tenant registry (demo only; regulators/users reference slugs, not rows)
        ("tenants", delete(Tenant).where(Tenant.is_demo.is_(True))),
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


# ============================================================================
# Delete demo tenants (Supabase rows + Firestore docs)
# ============================================================================

DELETABLE_TENANT_TERMINAL_STATUSES = {"CANCELLED"}


def _is_deleteable_demo_tenant(data: Dict[str, Any]) -> bool:
    """True when a tenants-collection doc is an OPERATOR to fully delete.

    Demo operators are flagged with `is_demo` (or legacy `is_beta_sandbox`)
    or are in the terminal `CANCELLED` state. Authority docs (state
    regulators) that also carry is_demo are never matched here.
    """
    if _is_regulator_doc(data):
        return False
    if data.get("is_demo") or data.get("is_beta_sandbox"):
        return True
    status = str(data.get("status") or "").strip().upper()
    return status in DELETABLE_TENANT_TERMINAL_STATUSES


async def _delete_tenant_postgres_data(tenant_uuids: List[uuid.UUID]) -> Dict[str, Any]:
    """Delete every Postgres row belonging to the given tenant uuids.

    Runs in the child→parent order from _build_purge_steps so FK constraints
    are satisfied. Each table runs in its own transaction so one failing table
    does not abort the rest. Returns per-table counts (or an error string).
    """
    if not tenant_uuids:
        return {"deleted_count": 0, "details": {}}
    steps = await _build_purge_steps(tenant_uuids=tenant_uuids)
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
            logger.error(f"Delete tenant data failed for {table}: {e}")
            details[table] = f"Error: {e}"
    return {"deleted_count": total, "details": details}


async def delete_demo_tenants(actor: Dict[str, Any]) -> Dict[str, Any]:
    """Permanently delete demo operators from BOTH stores.

    Removes every Postgres row for the tenant (all child tables) and the
    tenant's Firestore doc including all subcollections (reports, CAN/CAP,
    surveys, PSOE assessments, bow-tie, flight diversions, …). Also detaches
    the deleted tenant slugs from every regulator's `operator_tenant_ids` and
    deletes the tenant's users (Firebase Auth + Firestore `users` docs). The
    global `psoe_questions` reference bank is preserved.
    """
    db = get_db()
    candidates: List[Tuple[str, Dict[str, Any]]] = []
    for snap in db.collection(settings.FIREBASE_COLLECTION_TENANTS).stream():
        data = snap.to_dict() or {}
        if _is_deleteable_demo_tenant(data):
            candidates.append((snap.id, data))

    if not candidates:
        _audit("TENANTS_DEMO_DELETED", actor, "none",
               "No demo / CANCELLED tenants found to delete")
        return {
            "success": True,
            "deleted_count": 0,
            "tenants": [],
            "postgres": {"deleted_count": 0, "details": {}},
            "firestore": {"deleted": {}},
            "users_deleted": 0,
            "regulators": {},
        }

    postgres_result = await _delete_tenant_postgres_data(
        [tenant_uuid(slug) for slug, _ in candidates]
    )

    firestore_deleted: Dict[str, int] = {}
    for slug, _ in candidates:
        counter = [0]
        _delete_firestore_doc_tree(
            db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(slug),
            _count=counter,
        )
        firestore_deleted[slug] = counter[0]

    names = {slug: (data.get("name") or slug) for slug, data in candidates}
    tenant_list = [slug for slug, _ in candidates]
    fs_total = sum(firestore_deleted.values()) or 0
    regulator_updates = _detach_deleted_tenants_from_regulators(tenant_list, db)
    users_deleted = _delete_users_for_deleted_tenants(tenant_list, db)
    _audit(
        "TENANTS_DEMO_DELETED",
        actor,
        ",".join(tenant_list) or "-",
        f"Deleted demo tenants: {', '.join(f'{s} ({names[s]})' for s in tenant_list)} — "
        f"Firestore docs removed: {fs_total}, Postgres rows removed: {postgres_result.get('deleted_count', 0)}, "
        f"users deleted: {users_deleted}, regulators updated: {len(regulator_updates)}",
    )
    logger.info(f"Demo tenants deleted: {tenant_list} ({fs_total} Firestore docs)")
    return {
        "success": True,
        "deleted_count": len(tenant_list),
        "tenants": tenant_list,
        "postgres": postgres_result,
        "firestore": {"deleted": firestore_deleted},
        "users_deleted": users_deleted,
        "regulators": regulator_updates,
    }


def _detach_deleted_tenants_from_regulators(
    deleted_tenant_ids: List[str], db: Any
) -> Dict[str, Dict[str, Any]]:
    """Remove deleted tenant slugs from every regulator's `operator_tenant_ids`.

    Regulators live in the Firestore `regulators` collection and reference
    their operator tenants by slug. When a tenant is deleted its slug must be
    stripped from each regulator so no dangling operator reference remains
    (and the panel's Existing Regulators list shows accurate counts).

    Returns ``{regulator_id: {"before": [...], "after": [...]}}`` for every
    regulator whose list actually changed.
    """
    if not deleted_tenant_ids:
        return {}
    removed = set(deleted_tenant_ids)
    updated: Dict[str, Dict[str, Any]] = {}
    try:
        for snap in db.collection(settings.FIREBASE_COLLECTION_REGULATORS).stream():
            ops = list((snap.to_dict() or {}).get("operator_tenant_ids") or [])
            kept = [tid for tid in ops if tid not in removed]
            if kept == ops:
                continue
            snap.reference.set({"operator_tenant_ids": kept}, merge=True)
            updated[snap.id] = {"before": ops, "after": kept}
    except Exception as e:
        logger.warning(f"Failed to detach deleted tenants from regulators: {e}")
    return updated


def _delete_users_for_deleted_tenants(tenant_ids: List[str], db: Any) -> int:
    """Delete Firestore `users/{uid}` docs + Firebase Auth records for tenants.

    Mirrors the panel's per-user delete: the Firestore user doc (keyed by uid)
    and the matching Auth record are both removed. Auth failures for
    already-gone users are tolerated and logged.

    Returns the number of user records deleted.
    """
    if not tenant_ids:
        return 0
    removed = set(tenant_ids)
    try:
        snaps = [
            snap for snap in db.collection(settings.FIREBASE_COLLECTION_USERS).stream()
            if (snap.to_dict() or {}).get("tenant_id") in removed
        ]
    except Exception as e:
        logger.warning(f"Failed to list tenant users for deletion: {e}")
        return 0
    if not snaps:
        return 0

    try:
        auth = get_auth()
    except Exception as e:
        logger.warning(f"Firebase Auth unavailable — deleting user docs only: {e}")
        auth = None

    deleted = 0
    for snap in snaps:
        data = snap.to_dict() or {}
        uid = data.get("uid") or snap.id
        if auth is not None:
            try:
                auth.delete_user(uid)
            except Exception as e:
                logger.warning(f"Auth delete failed for {uid}: {e}")
        try:
            snap.reference.delete()
        except Exception as e:
            logger.warning(f"Firestore user doc delete failed for {uid}: {e}")
            continue
        deleted += 1
    return deleted


# ============================================================================
# Granular demo purges — Category C (Steps 6 & 7): PSOE + State Risk
# ============================================================================

PSOE_SEED_CREATOR = "production-setup"
PSOE_SEED_VERSION_PREFIX = "production-setup-"


async def purge_psoe_demo_data(actor: Dict[str, Any]) -> Dict[str, Any]:
    """Purge ALL PSOE demo data (is_demo = true).

    Removes Postgres `psoe_assessments` demo rows (+ their `psoe_findings`
    children) and the Firestore production-setup baseline assessments
    (created_by = "production-setup" / seed_version "production-setup-*").
    Real PSOE assessments and the global `psoe_questions` reference bank are
    never touched.
    """
    pg_details: Dict[str, Any] = {}
    pg_total = 0
    demo_assessment_ids = (
        select(PsoeAssessment.id)
        .where(PsoeAssessment.is_demo == True)
        .scalar_subquery()
    )
    steps = [
        ("psoe_findings", delete(PsoeFinding).where(PsoeFinding.assessment_id.in_(demo_assessment_ids))),
        ("psoe_assessments", delete(PsoeAssessment).where(PsoeAssessment.is_demo == True)),
    ]
    for table, stmt in steps:
        try:
            async with session_scope() as session:
                result = await session.execute(stmt)
                count = result.rowcount or 0
            pg_details[table] = count
            pg_total += count
        except Exception as e:
            logger.error(f"PSOE purge failed for {table}: {e}")
            pg_details[table] = f"Error: {e}"

    fs_deleted = 0
    try:
        coll = get_db().collection("psoe_assessments")
        for snap in coll.stream():
            data = snap.to_dict() or {}
            if (
                data.get("created_by") == PSOE_SEED_CREATOR
                or str(data.get("seed_version") or "").startswith(PSOE_SEED_VERSION_PREFIX)
            ):
                snap.reference.delete()
                fs_deleted += 1
    except Exception as e:
        logger.error(f"PSOE Firestore purge failed: {e}")

    ok = not any(str(v).startswith("Error") for v in pg_details.values())
    _audit(
        "PSOE_DEMO_PURGED",
        actor,
        "all",
        f"Purged {pg_total} Postgres PSOE demo rows, removed {fs_deleted} Firestore baselines",
        result="success" if ok else "partial",
    )
    logger.info(f"PSOE demo data purged: {pg_total} rows, {fs_deleted} Firestore docs")
    return {
        "success": ok,
        "deleted_count": pg_total,
        "details": pg_details,
        "firestore_deleted": fs_deleted,
    }


async def purge_state_risk_demo_data(actor: Dict[str, Any]) -> Dict[str, Any]:
    """Purge ALL State Risk demo data (is_demo = true).

    Removes Postgres `state_risk_register` demo rows. The Firestore ICAO
    reference taxonomy is global reference data (not per-tenant demo data) and
    is preserved.
    """
    pg_deleted = 0
    error = ""
    try:
        async with session_scope() as session:
            result = await session.execute(
                delete(StateRiskRegisterEntry).where(StateRiskRegisterEntry.is_demo == True)
            )
            pg_deleted = result.rowcount or 0
    except Exception as e:
        error = str(e)
        logger.error(f"State risk purge failed: {e}")

    _audit(
        "STATE_RISK_DEMO_PURGED",
        actor,
        "all",
        f"Purged {pg_deleted} State Risk demo rows",
        result="error" if error else "success",
    )
    logger.info(f"State risk demo data purged: {pg_deleted} rows")
    return {
        "success": not error,
        "deleted_count": pg_deleted,
        "details": {
            "state_risk_register": pg_deleted if not error else f"Error: {error}"
        },
    }
