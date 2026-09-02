# ============================================================================
# FILE: production_seed.py
# PATH: backend/app/services/production_seed.py
# PURPOSE: Super-Admin web seeding panel backend. Creates State Regulator and
#          operator tenant documents, supports individual + bulk tenant import,
#          previews the CAAN demo seed plan, deploys it (surveys + hazards +
#          reports, same shapes as scripts/seed_caan_demo_data.py), and records
#          every action to the `audit_logs` collection.
#
#          Target database is whatever the backend is configured for — the
#          single consolidated `sms-db` named database — so the panel always
#          operates against the live platform data.
# ============================================================================

import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.config import settings
from app.db.ids import tenant_uuid
from app.firebase import get_db
from app.services.risk_matrix import compute_risk_index, get_risk_level
from app.services.survey_scoring import (
    BINARY_QUESTIONS,
    QUESTION_PILLARS,
    SURVEY_VERSION,
    compute_overall_maturity,
    compute_percentage_score,
    compute_pillar_scores,
    compute_question_scores,
)

SEED_VERSION = "caan-demo-1"

# The operators overseen by the default CAAN State Regulator seed plan. Base
# maturity (1-5) drives the seeded SMS culture so the dashboard shows a
# realistic spread of maturity across operators. Matches the 11 active beta
# provider tenants (seed/config.py OPERATOR_PROFILES).
SEED_OPERATORS = [
    {"id": "buddha-air", "name": "Buddha Air", "maturity": 4.1},
    {"id": "air-dynasty", "name": "Air Dynasty Heli Services", "maturity": 3.0},
    {"id": "ktm-mro", "name": "KTM MRO Services", "maturity": 3.5},
    {"id": "pokhara-aerodrome", "name": "Pokhara Aerodrome", "maturity": 2.8},
    {"id": "himalaya-ground-services", "name": "Himalaya Ground Handling", "maturity": 3.3},
    {"id": "yeti-airlines", "name": "Yeti Airlines", "maturity": 3.9},
    {"id": "summit-air", "name": "Summit Air", "maturity": 3.1},
    {"id": "sita-air", "name": "Sita Air", "maturity": 3.6},
    {"id": "simrik-air", "name": "Simrik Air", "maturity": 3.5},
    {"id": "tara-air", "name": "Tara Air", "maturity": 3.6},
    {"id": "fishtail-air", "name": "Fishtail Air", "maturity": 3.4},
]

ICAO_CATEGORIES = [
    "LOCI", "CFIT", "RE", "RI", "MAC", "WX", "ENG", "SYS",
    "FIRE", "BIRD", "GCOL", "CABIN", "ARC", "OTHER",
]

# Maps ICAO occurrence categories to the SMS taxonomy values accepted by the
# HazardTaxonomy enum (see app/routes/reports.py:_determine_hazard_taxonomy).
_ICAO_TO_TAXONOMY = {
    "LOCI": "Organizational-Facilities",
    "CFIT": "Organizational-Facilities",
    "RE": "Organizational-Facilities",
    "RI": "Organizational-Facilities",
    "GCOL": "Organizational-Facilities",
    "MAC": "Technical",
    "ENG": "Technical",
    "SYS": "Technical",
    "FIRE": "Technical",
    "BIRD": "Wildlife",
    "CABIN": "Human Factors",
    "ARC": "Organizational-Documentation, Processes and Procedures",
    "PRO": "Organizational-Documentation, Processes and Procedures",
    "WX": "Environmental",
    "OTHER": "Other",
}

DEPARTMENTS = ["Flight Operations", "Maintenance & Engineering", "Ground Handling",
               "Cabin Crew", "Administration"]
YEARS_EXP = ["0-2", "2-7", "7-15", "15+"]

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


# ============================================================================
# Audit logging
# ============================================================================

def _audit(action: str, actor: Dict[str, Any], target: str, detail: str,
           result: str = "success") -> None:
    """Persist one audit entry under the top-level `audit_logs` collection."""
    try:
        now = datetime.now(timezone.utc)
        db = get_db()
        db.collection(settings.FIREBASE_COLLECTION_AUDIT_LOGS).add({
            "action": action,
            "actor": {
                "uid": actor.get("uid"),
                "email": actor.get("email"),
            },
            "target": target,
            "detail": detail,
            "result": result,
            "timestamp": now.isoformat(),
            "created_at": now,
        })
    except Exception as e:
        logger.error(f"Audit log write failed ({action}): {e}")


def list_audit_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """Most recent seeding/admin audit entries (newest first)."""
    limit = max(1, min(int(limit or 50), 200))
    try:
        docs = (
            get_db().collection(settings.FIREBASE_COLLECTION_AUDIT_LOGS)
            .order_by("timestamp", direction="DESCENDING").limit(limit).get()
        )
        rows = []
        for d in docs:
            data = d.to_dict() or {}
            data["id"] = d.id
            rows.append(data)
        return rows
    except Exception as e:
        logger.warning(f"Failed to list audit logs: {e}")
        return []


# ============================================================================
# Validation + creation
# ============================================================================

def _validate_id(value: str, label: str = "id") -> str:
    value = (value or "").strip()
    if not value or not ID_RE.match(value):
        raise ValueError(f"{label} must be lowercase letters/numbers/hyphens (e.g. sita-air)")
    return value


def create_regulator(data: Dict[str, Any], actor: Dict[str, Any]) -> Dict[str, Any]:
    """Create a State Regulator document. 409 when the id already exists."""
    rid = _validate_id(data.get("id"), "regulator id")
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("regulator name is required")

    db = get_db()
    if db.collection(settings.FIREBASE_COLLECTION_REGULATORS).document(rid).get().exists:
        raise ValueError(f"regulator already exists: {rid}")

    now = datetime.now(timezone.utc)
    doc = {
        "id": rid,
        "type": "state_regulator",
        "name": name,
        "short_name": (data.get("short_name") or "").strip() or rid.upper(),
        "country": (data.get("country") or "").strip(),
        "country_name": (data.get("country_name") or "").strip(),
        "domain": (data.get("domain") or "").strip() or None,
        "operator_tenant_ids": list(data.get("operator_tenant_ids") or []),
        "active": bool(data.get("active", True)),
        "created_at": now,
        "updated_at": now,
    }
    db.collection(settings.FIREBASE_COLLECTION_REGULATORS).document(rid).set(doc)

    _audit("REGULATOR_CREATED", actor, rid,
           f"Created State Regulator '{name}' ({data.get('country_name') or data.get('country') or ''})")
    logger.info(f"Regulator {rid} created by {actor.get('uid')}")
    return doc


def create_tenant(data: Dict[str, Any], actor: Dict[str, Any]) -> Dict[str, Any]:
    """Create an operator tenant document. 409 when the id already exists."""
    tid = _validate_id(data.get("tenant_id") or data.get("id"), "tenant id")
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("tenant name is required")

    db = get_db()
    if db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tid).get().exists:
        raise ValueError(f"tenant already exists: {tid}")

    regulator_id = (data.get("regulator_id") or "").strip() or None
    if regulator_id:
        _validate_id(regulator_id, "regulator id")

    now = datetime.now(timezone.utc)
    doc = {
        "tenant_id": tid,
        "name": name,
        "icao": (data.get("icao") or "").strip(),
        "country": (data.get("country") or "Nepal").strip(),
        "category": (data.get("category") or "CONTRACTED").upper(),
        "status": (data.get("status") or "ACTIVE").upper(),
        "trial_expires_at": data.get("trial_expires_at"),
        "active": bool(data.get("active", True)),
        "created_at": now,
        "updated_at": now,
    }
    if regulator_id:
        doc["regulator_id"] = regulator_id
    sm = data.get("safety_manager")
    if isinstance(sm, dict) and sm:
        doc["safety_manager"] = sm
    survey_config = data.get("survey_config")
    if isinstance(survey_config, dict) and survey_config:
        doc["survey_config"] = survey_config

    db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tid).set(doc)

    _audit("TENANT_CREATED", actor, tid,
           f"Created operator tenant '{name}' (regulator={regulator_id or 'none'})")
    logger.info(f"Tenant {tid} created by {actor.get('uid')}")
    return doc


def bulk_create_tenants(records: List[Dict[str, Any]], actor: Dict[str, Any]) -> Dict[str, Any]:
    """Create many tenants from a parsed list; returns per-record results."""
    results = []
    for rec in records:
        try:
            doc = create_tenant(rec, actor)
            results.append({"tenant_id": doc["tenant_id"], "status": "ok"})
        except ValueError as e:
            results.append({"tenant_id": rec.get("tenant_id") or rec.get("id"), "status": "error", "detail": str(e)})
        except Exception as e:
            results.append({"tenant_id": rec.get("tenant_id") or rec.get("id"), "status": "error", "detail": str(e)})

    ok = sum(1 for r in results if r["status"] == "ok")
    _audit("TENANTS_BULK_IMPORT", actor, f"{ok}/{len(results)}",
           f"Bulk import created {ok} of {len(results)} tenants")
    return {"total": len(results), "ok": ok, "results": results}


# ============================================================================
# Admin lists
# ============================================================================

def list_regulators_admin() -> List[Dict[str, Any]]:
    try:
        docs = get_db().collection(settings.FIREBASE_COLLECTION_REGULATORS).get()
        return [dict(d.to_dict() or {}, id=d.id) for d in docs]
    except Exception as e:
        logger.warning(f"Failed to list regulators (admin): {e}")
        return []


def list_tenants_admin() -> List[Dict[str, Any]]:
    try:
        db = get_db()
        tenants = db.collection(settings.FIREBASE_COLLECTION_TENANTS).get()
        rows = []
        for t in tenants:
            td = dict(t.to_dict() or {})
            td["id"] = t.id
            td["counts"] = {}
            for sub in ("surveys", "hazards", "reports", "can_cap"):
                try:
                    td["counts"][sub if sub != "can_cap" else "cans"] = len(list(t.reference.collection(sub).limit(500).get()))
                except Exception:
                    td["counts"]["cans" if sub == "can_cap" else sub] = 0
            rows.append(td)
        rows.sort(key=lambda r: (r.get("name") or r.get("id") or "").lower())
        return rows
    except Exception as e:
        logger.warning(f"Failed to list tenants (admin): {e}")
        return []


async def _postgres_tenant_counts(slugs: List[str]) -> Dict[str, Dict[str, int]]:
    """Per-tenant operational counts from PostgreSQL by slug.

    Tenant documents live in Firestore (by slug) while hazards/reports/cans/
    caps/surveys rows live in Supabase keyed by a deterministic
    ``uuid5('tenant', slug)``. Returns ``{slug: {surveys, hazards, reports,
    cans, caps}}``. Falls back to empty counts when DATABASE_URL is unset or
    the read fails (keep the Firestore-only path working).
    """
    slugs = [s for s in (slugs or []) if s]
    if not slugs:
        return {}
    try:
        from sqlalchemy import text
        from app.db.session import get_engine
        engine = get_engine()
    except Exception as e:
        logger.warning(f"PostgreSQL unavailable for tenant counts: {e}")
        return {}

    by_uuid = {tenant_uuid(s): s for s in slugs}
    counts = {s: {"surveys": 0, "hazards": 0, "reports": 0, "cans": 0, "caps": 0} for s in slugs}
    try:
        async with engine.connect() as conn:
            for label in ("hazards", "reports", "cans", "caps", "surveys"):
                result = await conn.execute(
                    text(
                        f"SELECT tenant_id, count(*) AS c FROM {label} "
                        "WHERE tenant_id = ANY(:ids) GROUP BY tenant_id"
                    ),
                    {"ids": list(by_uuid.keys())},
                )
                for row in result:
                    slug = by_uuid.get(str(row.tenant_id))
                    if slug:
                        counts[slug][label] = row.c
        return counts
    except Exception as e:
        logger.warning(f"Failed to read PostgreSQL tenant counts: {e}")
        return {}


async def list_tenants_admin_pg() -> List[Dict[str, Any]]:
    """List operator tenants enriched for the Super Admin dashboard.

    Merges Firestore tenant metadata (country, regulator_id, status, contract,
    payment) with PostgreSQL operational counts and resolves regulator name +
    country from the `regulators` collection. Falls back to Firestore
    subcollection counts when PostgreSQL is not configured.
    """
    rows = list_tenants_admin()
    pg_counts = await _postgres_tenant_counts([r.get("id") for r in rows])

    regs = {}
    try:
        db = get_db()
        for snap in db.collection(settings.FIREBASE_COLLECTION_REGULATORS).stream():
            regs[snap.id] = snap.to_dict() or {}
    except Exception as e:
        logger.warning(f"Failed to list regulators for tenant enrichment: {e}")

    for r in rows:
        slug = r.get("id")
        if slug and slug in pg_counts:
            r["counts"] = pg_counts[slug]
        rid = r.get("regulator_id")
        reg = regs.get(rid) if rid else None
        r["regulator_name"] = (reg or {}).get("name") if reg else None
        r["regulator_country"] = (
            (reg or {}).get("country_name") or (reg or {}).get("country")
        ) if reg else None
        r["is_demo"] = bool(r.get("is_demo") or r.get("is_beta_sandbox"))
    rows.sort(key=lambda r: (r.get("name") or r.get("id") or "").lower())
    return rows


# ============================================================================
# Seed plan + deploy
# ============================================================================

def _count_docs(db, tid: str, sub: str) -> int:
    try:
        return len(list(db.collection("tenants").document(tid).collection(sub).limit(2000).get()))
    except Exception:
        return 0


def _clear_seeded(db, tid: str) -> None:
    ref = db.collection("tenants").document(tid)
    for sub in ("surveys", "responses", "hazards", "reports"):
        try:
            snaps = ref.collection(sub).where("seed_version", "==", SEED_VERSION).get()
        except Exception:
            snaps = []
        for snap in snaps:
            snap.reference.delete()


def seed_plan() -> Dict[str, Any]:
    """Current state vs desired state for the CAAN demo seed plan."""
    db = get_db()
    regulator_id = "caan"
    try:
        reg_exists = db.collection("regulators").document(regulator_id).get().exists
    except Exception:
        reg_exists = False

    operators = []
    for op in SEED_OPERATORS:
        tid = op["id"]
        td = None
        try:
            snap = db.collection("tenants").document(tid).get()
            if snap.exists:
                td = snap.to_dict() or {}
        except Exception:
            pass
        operators.append({
            "id": tid,
            "name": op["name"],
            "maturity": op["maturity"],
            "exists": td is not None,
            "tagged": bool(td and td.get("regulator_id") == regulator_id),
            "surveys_existing": _count_docs(db, tid, "surveys"),
            "surveys_target": "20-34",
            "hazards_existing": _count_docs(db, tid, "hazards"),
            "reports_existing": _count_docs(db, tid, "reports"),
        })

    return {
        "regulator": {"id": regulator_id, "exists": reg_exists,
                      "operator_tenant_ids": [o["id"] for o in SEED_OPERATORS]},
        "operators": operators,
        "totals": {
            "operators": len(SEED_OPERATORS),
            "surveys_to_seed": sum(1 for o in operators if o["surveys_existing"] == 0),
            "operators_to_tag": sum(1 for o in operators if not o["tagged"]),
        },
    }


def preview_seed(actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    plan = seed_plan()
    plan["previewed_at"] = datetime.now(timezone.utc).isoformat()
    if actor:
        _audit("SEED_PREVIEW", actor, "caan",
               f"Previewed seed plan: {plan['totals']['operators']} operators")
    return plan


def _clamp(v, lo=1, hi=5):
    return max(lo, min(hi, int(round(v))))


def _random_answers(maturity: float) -> dict:
    pillar_means = {
        "safety_policy": _clamp(maturity + random.uniform(-0.3, 0.5)),
        "safety_risk_management": _clamp(maturity + random.uniform(-0.5, 0.4)),
        "safety_assurance": _clamp(maturity + random.uniform(-0.4, 0.3)),
        "safety_promotion": _clamp(maturity + random.uniform(-0.5, 0.6)),
    }
    answers = {}
    for qid, pillar in QUESTION_PILLARS.items():
        if qid in BINARY_QUESTIONS:
            aware_prob = _clamp(maturity) / 5.0
            answers[qid] = random.random() < aware_prob
            continue
        mean = pillar_means[pillar]
        answers[qid] = _clamp(random.gauss(mean, 0.8))
    return answers


def _survey_doc(tid: str, answers: dict, submitted_at: datetime, idx: int) -> dict:
    pillar_scores = compute_pillar_scores(answers)
    overall = compute_overall_maturity(pillar_scores)
    question_scores = compute_question_scores(answers)
    return {
        "tenant_id": tid,
        "tenantId": tid,
        "submitted_at": submitted_at,
        "submittedAt": submitted_at,
        "respondent_id": f"seed-{tid}-{idx}",
        "respondentId": f"seed-{tid}-{idx}",
        "department": random.choice(DEPARTMENTS),
        "employee_category": random.choice(["Flight Crew", "Cabin Crew", "Engineer", "Ground Staff", "Admin"]),
        "years_experience": random.choice(YEARS_EXP),
        "language_used": random.choice(["en", "en", "en", "ne"]),
        "survey_version": SURVEY_VERSION,
        "seed_version": SEED_VERSION,
        "answers": answers,
        "question_scores": question_scores,
        "questionScores": question_scores,
        "safety_policy": pillar_scores["safety_policy"],
        "safety_risk_management": pillar_scores["safety_risk_management"],
        "safety_assurance": pillar_scores["safety_assurance"],
        "safety_promotion": pillar_scores["safety_promotion"],
        "overall_sms_maturity": overall,
        "overallSMSMaturity": overall,
        "pillarScores": pillar_scores,
        "overall_score_pct": compute_percentage_score(overall),
    }


def _hazard_doc(tid: str, cat: str, created_at: datetime, idx: int) -> dict:
    severity = random.randint(2, 4)
    probability = random.randint(2, 4)
    risk_index = compute_risk_index(severity, probability)
    return {
        "tenant_id": tid,
        "hazard_id": f"{tid}-HZ-{created_at.year}-{idx:03d}",
        "title": f"Demo hazard {cat} at {tid}",
        "description": f"Seeded demonstration hazard classified as {cat}.",
        "source": random.choice(["VSR", "MOR", "Safety Inspection"]),
        "occurrence_category": cat,
        "taxonomy": _ICAO_TO_TAXONOMY.get(cat, "Other"),
        "severity": severity,
        "probability": probability,
        "risk_index": risk_index,
        "risk_level": get_risk_level(risk_index),
        "priority": "H" if risk_index >= 12 else "M" if risk_index >= 6 else "L",
        "status": random.choice(["Open", "Open", "Under Review", "Closed"]),
        "created_by": "seed-caan-demo",
        "created_at": created_at,
        "updated_at": created_at,
        "seed_version": SEED_VERSION,
    }


def _report_doc(tid: str, cat: str, created_at: datetime, idx: int) -> dict:
    severity = random.randint(2, 5)
    probability = random.randint(1, 4)
    risk_index = compute_risk_index(severity, probability)
    return {
        "tenant_id": tid,
        "tenantId": tid,
        "report_type": random.choice(["voluntary", "voluntary", "mandatory"]),
        "status": "NEW",
        "ai_status": "PENDING",
        "narrative": f"Seeded demonstration report ({cat}) from {tid}.",
        "location": random.choice(["KTM", "Pokhara", "Bhairahawa", "In-flight", "Kathmandu Valley"]),
        "occurrence_type": "Report",
        "occurrence_category": cat,
        "severity": str(severity),
        "severity_level": severity,
        "probability": probability,
        "probability_level": probability,
        "risk_index": risk_index,
        "risk_level": get_risk_level(risk_index),
        "is_anonymous": random.random() < 0.5,
        "occurrence_date": created_at.isoformat(),
        "created_by": "seed-caan-demo",
        "created_at": created_at,
        "updated_at": created_at,
        "seed_version": SEED_VERSION,
    }


def deploy_seed(force: bool, actor: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the CAAN demo seed plan against the configured database."""
    db = get_db()
    regulator_id = "caan"
    now = datetime.now(timezone.utc)

    # 1. Regulator document + operator tenant tags
    db.collection("regulators").document(regulator_id).set({
        "id": regulator_id,
        "type": "state_regulator",
        "name": "Civil Aviation Authority of Nepal",
        "short_name": "CAAN",
        "country": "NP",
        "country_name": "Nepal",
        "domain": "ssp.caanepal.gov.np",
        "operator_tenant_ids": [o["id"] for o in SEED_OPERATORS],
        "active": True,
        "updated_at": now,
    }, merge=True)

    for op in SEED_OPERATORS:
        db.collection("tenants").document(op["id"]).set({
            "regulator_id": regulator_id,
            "country": "NP",
            "active": True,
        }, merge=True)

    # 2. Surveys + hazards + reports per operator
    survey_total = hazard_total = report_total = 0
    details = []
    for op in SEED_OPERATORS:
        tid = op["id"]
        ref = db.collection("tenants").document(tid)
        existing_surveys = _count_docs(db, tid, "surveys")

        if not force and existing_surveys > 0:
            details.append(f"{tid}: surveys exist, skipped")
        else:
            _clear_seeded(db, tid)
            n = random.randint(20, 34)
            for i in range(n):
                answers = _random_answers(op["maturity"])
                submitted_at = now - timedelta(days=random.uniform(0, 130))
                doc = _survey_doc(tid, answers, submitted_at, i)
                ref.collection("surveys").add(doc)
                ref.collection("responses").add({
                    "tenant_id": tid,
                    "tenantId": tid,
                    "respondent_id": doc["respondent_id"],
                    "respondentId": doc["respondent_id"],
                    "answers": answers,
                    "department": doc["department"],
                    "submitted_at": submitted_at,
                    "submittedAt": submitted_at,
                    "survey_version": SURVEY_VERSION,
                    "seed_version": SEED_VERSION,
                })
            survey_total += n
            details.append(f"{tid}: seeded {n} surveys")

        cats = random.sample(ICAO_CATEGORIES, k=random.randint(4, 7))
        for idx, cat in enumerate(cats):
            ref.collection("hazards").add(_hazard_doc(tid, cat, now - timedelta(days=random.uniform(0, 200)), idx))
            hazard_total += 1
        n_reports = random.randint(3, 6)
        for idx in range(n_reports):
            ref.collection("reports").add(_report_doc(tid, random.choice(ICAO_CATEGORIES),
                                                      now - timedelta(days=random.uniform(0, 200)), idx))
            report_total += 1

    result = {
        "regulator_id": regulator_id,
        "operators": len(SEED_OPERATORS),
        "surveys_seeded": survey_total,
        "hazards_seeded": hazard_total,
        "reports_seeded": report_total,
        "details": details,
        "seeded_at": now.isoformat(),
        "force": bool(force),
    }
    _audit("SEED_DEPLOY", actor, regulator_id,
           f"Seeded {len(SEED_OPERATORS)} operators: {survey_total} surveys, "
           f"{hazard_total} hazards, {report_total} reports (force={bool(force)})")
    logger.info(f"Seed deploy by {actor.get('uid')}: {result}")
    return result
