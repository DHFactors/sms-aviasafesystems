# ============================================================================
# FILE: scripts/migrate_firestore_to_supabase.py
# PURPOSE: One-shot (idempotent) migration of the Firestore operator database
#          (single consolidated database `sms-db`; project aerosafety-sms-prod)
#          into the Supabase PostgreSQL schema defined in backend/app/db/schema.sql.
#
# FEATURES
#   * Reads every tenant-scoped collection: hazards, reports (VSR/MOR),
#     can_cap (+ `caps` subcollection), surveys, responses, flight_diversions,
#     legacy `verification`, verifications/closures (nested under hazards).
#   * Reads top-level collections: psoe_assessments, state/ssp/risk_register
#     (SSP state risk), caan_reports.
#   * Deterministic UUIDs (uuid5) derived from tenant slug + Firestore doc id
#     so re-runs are idempotent and FK references stay stable.
#   * Batch upserts (INSERT ... ON CONFLICT (id) DO UPDATE) over asyncpg using
#     the Supabase Service Role connection.
#   * Full accounting (inserted/updated/skipped/errors) written to
#     scripts/migration.log.
#
# USAGE
#     # backend/.env supplies FIREBASE_* credentials; DATABASE_URL is read from
#     # env / --database-url.
#     python scripts/migrate_firestore_to_supabase.py
#     python scripts/migrate_firestore_to_supabase.py --database sms-db \
#         --database-url "postgresql://postgres.<ref>:<service_role>@<host>:5432/postgres" \
#         --tenant sita-air --tenant buddha-air --only hazards --dry-run
# ============================================================================

import argparse
import asyncio
import json
import logging
import os
import sys
import traceback
import uuid
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
BACKEND = os.path.join(PROJECT_ROOT, "backend")
sys.path.insert(0, BACKEND)

DEFAULT_DATABASE = "sms-db"
LOG_FILE = os.path.join(SCRIPT_DIR, "migration.log")
BATCH_SIZE = 500

# Synthetic tenant slug used for state-level / regulator-owned documents that
# own no operator tenant (state/ssp/risk_register, caan_reports).
STATE_TENANT_SLUG = "caan"
_NS = uuid.NAMESPACE_DNS


def _uuid5(*parts: str) -> uuid.UUID:
    return uuid.uuid5(_NS, ":".join(p for p in parts if p))


def _tenant_uuid(slug: str) -> str:
    return str(_uuid5("tenant", slug))


# ── logging ──────────────────────────────────────────────────────────────────

def setup_logging() -> logging.Logger:
    fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt)
    root = logging.getLogger()
    if not any(isinstance(h, logging.FileHandler) for h in root.handlers):
        fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
        fh.setFormatter(logging.Formatter(fmt))
        root.addHandler(fh)
    return logging.getLogger("migrate")


log = setup_logging()

# ── value coercion helpers ───────────────────────────────────────────────────

def _pick(doc: dict, *keys: str, default: Any = None) -> Any:
    for k in keys:
        v = doc.get(k)
        if v is not None:
            return v
    return default


def _s(doc: dict, key: str, default: str = "") -> str:
    v = doc.get(key)
    if v is None:
        return default
    return str(v)


def _s_pick(doc: dict, keys: Tuple[str, ...], default: str = "") -> str:
    v = _pick(doc, *keys, default=None)
    if v is None:
        return default
    return str(v)


def _b(doc: dict, key: str, default: bool = False) -> bool:
    v = doc.get(key)
    return default if v is None else bool(v)


def _i(doc: dict, key: str, default: Optional[int] = None) -> Optional[int]:
    v = doc.get(key)
    if v is None or v == "":
        return default
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _f(doc: dict, key: str, default: Optional[float] = None) -> Optional[float]:
    v = doc.get(key)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _js(doc: dict, key: str) -> Any:
    """Value for a JSONB column (dict/list/str) or None."""
    return doc.get(key)


def _dt(v: Any) -> Optional[datetime]:
    """Coerce Firestore Timestamp / datetime / date / ISO string to aware UTC."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
    if isinstance(v, str):
        v = v.strip()
        if len(v) == 10 and v[4] == "-" and v[7] == "-":
            try:
                return datetime.fromisoformat(v).replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(v, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(v)
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    log.warning("Unparseable datetime value: %r", v)
    return None


def _dt_key(doc: dict, *keys: str, default: Optional[datetime] = None) -> Optional[datetime]:
    return _dt(_pick(doc, *keys, default=None)) or default


def _normalize_priority(v: Any, default: str = "M") -> str:
    """Map High/Medium/Low (and H/M/L) to the hazards priority check (H/M/L)."""
    if isinstance(v, str):
        m = v.strip().lower()
        if m in ("h", "high"):
            return "H"
        if m in ("m", "medium"):
            return "M"
        if m in ("l", "low"):
            return "L"
    return default


def _normalize_priority_words(v: Any, default: str = "Medium") -> str:
    """Map H/M/L and High/Medium/Low to the cans/corrective_actions check."""
    if isinstance(v, str):
        m = v.strip().lower()
        if m in ("h", "high"):
            return "High"
        if m in ("m", "medium"):
            return "Medium"
        if m in ("l", "low"):
            return "Low"
    return default


def _normalize_rca_method(v: Any) -> Optional[str]:
    """Map the CAP structured-RCA method to the allowed ('bow_tie','fishbone')."""
    if not isinstance(v, str):
        return None
    m = " ".join(v.strip().lower().replace("_", " ").replace("-", " ").split())
    if "fishbone" in m:
        return "fishbone"
    if "bow" in m and "tie" in m:
        return "bow_tie"
    return None


def _jsonify(v: Any) -> Any:
    """asyncpg cannot bind dict/list for JSONB columns; serialize them."""
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str, ensure_ascii=False)
    return v


# ── column schemas (mirror backend/app/db/schema.sql) ───────────────────────

HAZARD_COLS = (
    "id", "hazard_id", "tenant_id", "title", "description", "source",
    "source_id", "source_url", "adrep_category", "occurrence_type", "taxonomy",
    "taxonomy_specific", "consequence", "severity", "probability", "risk_index",
    "risk_level", "risk_outcome", "tolerability_tier", "priority",
    "recommended_action", "corrective_action", "assigned_to", "assigned_to_uid",
    "department", "srm_conducted", "srm_date", "srm_status", "analysis_mode",
    "sram_data", "status", "follow_up_date", "closed_at", "closed_by", "remarks",
    "is_demo", "created_by", "created_at", "updated_at",
)

REPORT_COLS = (
    "id", "tenant_id", "report_type", "status", "ai_status", "narrative",
    "location", "occurrence_date", "is_anonymous", "flight_number",
    "aircraft_registration", "occurrence_type", "severity",
    "investigation_status", "severity_level", "probability_level", "risk_index",
    "risk_level", "risk_assessment", "ai_suggested_assessment", "ai_analysis",
    "occurrence_class", "latitude", "longitude", "country", "aircraft_make",
    "aircraft_model", "aircraft_serial_number", "operator", "operator_icao",
    "aircraft_category", "engine_make", "engine_model", "engine_serial_number",
    "flight_phase", "flight_type", "departure_airport", "destination_airport",
    "aircraft_utilisation_hours", "aircraft_utilisation_cycles", "crew_count",
    "passenger_count", "fatal_injuries", "serious_injuries", "minor_injuries",
    "occurrence_category", "human_factors", "contributing_factors",
    "investigation_agency", "reporter_name", "reporter_role", "reporter_email",
    "reporter_phone", "reporter_organisation", "reporting_date", "etops",
    "propeller_make", "propeller_model", "call_sign", "organisation_comments",
    "manufacturer_advised", "fdr_data_retained", "is_demo", "created_by", "created_at",
    "updated_at",
)

CAN_COLS = (
    "id", "can_reference", "tenant_id", "hazard_id", "title", "description",
    "required_action", "issued_by", "issued_by_uid", "issued_at",
    "target_completion_date", "assigned_to", "assigned_to_uid", "department",
    "priority", "status", "copies_to", "requested_function",
    "addressed_function", "initial_severity", "initial_probability",
    "initial_risk_index", "initial_risk_level", "initial_risk_outcome",
    "initial_tolerability_tier", "initial_sra", "classification_type",
    "classification_level", "is_demo", "created_by", "created_at", "updated_at",
)

CAP_COLS = (
    "id", "cap_reference", "tenant_id", "can_id", "action_plan", "timeline",
    "resources_required", "implementation_plan", "department",
    "target_completion_date", "submitted_by", "submitted_by_uid",
    "submitted_at", "status", "reviewed_by", "reviewed_by_uid", "reviewed_at",
    "review_comments", "revision_deadline", "company_name", "base_location",
    "area_system_of_interest", "finding_number", "file_ref", "factual_review",
    "rca", "short_term_ca", "long_term_ca", "implementation_timeline",
    "managerial_approval", "caa_acceptance", "residual_severity",
    "residual_probability", "residual_risk_index", "residual_risk_level",
    "residual_risk_outcome", "residual_tolerability_tier", "residual_sra",
    "root_causes", "action_items", "rca_method", "sram_data", "escalated_to_ae",
    "escalated_by", "escalated_at", "escalation_reason", "ae_signature",
    "ae_signed_at", "ae_review_interval_days", "ae_review_date", "sag_sign",
    "sag_signed_by", "sag_signed_at", "manager_approval", "ca_acceptance",
    "process_owner", "manager_confirmation", "closing_remarks", "closed_by",
    "closed_at", "closed_signature", "is_demo", "created_at", "updated_at",
)

SURVEY_COLS = (
    "id", "tenant_id", "submitted_at", "respondent_id", "department",
    "employee_category", "years_experience", "language_used", "survey_version",
    "seed_version", "answers", "question_scores", "element_scores",
    "safety_policy", "safety_risk_management", "safety_assurance",
    "safety_promotion", "overall_sms_maturity", "overall_score_pct", "is_demo",
)

SURVEY_RESPONSE_COLS = (
    "id", "tenant_id", "respondent_id", "answers", "department",
    "employee_category", "years_experience", "language_used", "submitted_at",
    "survey_version", "is_demo",
)

CORRECTIVE_ACTION_COLS = (
    "id", "tenant_id", "hazard_id", "can_id", "event_id", "title",
    "description", "action_plan", "priority", "assigned_to", "assigned_to_uid",
    "assigned_by", "assigned_at", "target_completion_date", "completed_at",
    "reviewed_by", "reviewed_at", "review_comments", "status", "remarks",
    "created_by", "updated_by", "created_at", "updated_at",
)

RISK_REGISTER_COLS = (
    "id", "tenant_id", "hazard_id", "srm_date", "ultimate_consequence",
    "existing_severity", "existing_probability", "existing_risk_index",
    "existing_risk_tolerability", "resultant_severity", "resultant_probability",
    "resultant_risk_index", "resultant_risk_tolerability", "status",
    "follow_up_date", "date_completed", "remarks", "concerned_department",
    "created_by", "updated_by", "created_at", "updated_at",
)

SAFETY_DEFICIENCY_COLS = (
    "id", "tenant_id", "event_id", "source", "hazard_code", "description",
    "taxonomy_main", "taxonomy_type", "taxonomy_specific", "unsafe_event",
    "identified_hazard", "priority", "severity", "assigned_to",
    "assigned_to_uid", "assigned_by", "assigned_at", "follow_up_date",
    "completed_at", "status", "remarks", "csd_remarks", "created_by",
    "updated_by", "created_at", "updated_at",
)

DIVERSION_COLS = (
    "id", "diversion_id", "tenant_id", "date", "flight_number",
    "aircraft_registration", "sector_from", "sector_to", "diverted_to",
    "reason", "reason_details", "captain", "first_officer", "air_hostess",
    "description", "additional_fuel_cost", "passenger_impact", "delay_minutes",
    "remarks", "status", "hazard_id", "hazard_link_url", "created_by",
    "updated_by", "created_at", "updated_at",
)

VERIFICATION_COLS = (
    "id", "tenant_id", "hazard_id", "cap_id", "outcome", "comments", "evidence",
    "verified_by", "verified_by_uid", "verification_date", "revision_deadline",
    "revision_notes", "created_at", "updated_at",
)

CLOSURE_COLS = (
    "id", "tenant_id", "hazard_id", "lessons_learned", "recommendations",
    "approval_notes", "approved_by", "approved_by_uid", "approved_at",
    "created_at", "updated_at",
)

STATE_RISK_COLS = (
    "id", "tenant_id", "icoc_category", "description", "icao_reference",
    "current_risk_index", "tolerability", "tolerability_tier", "level",
    "ssp_target", "actual_ssp_value", "risk_reduction_rate", "trend",
    "contributing_tenants", "quarter", "year", "is_demo", "updated_by", "created_at",
    "updated_at",
)

PSOE_COLS = (
    "id", "tenant_id", "title", "status", "department", "scope", "auditor_name",
    "assessor_email", "assessment_date", "template_version", "responses",
    "component_scores", "overall_score_pct", "overall_level", "notes",
    "is_demo", "created_by", "created_by_uid", "created_at", "updated_at",
)

REG_REPORT_COLS = (
    "id", "tenant_id", "report_type", "period", "year", "quarter", "status",
    "summary", "data", "generated_at", "generated_by", "file_url", "is_demo",
    "created_at", "updated_at",
)

# ── Firestore access ─────────────────────────────────────────────────────────

def init_firestore(project_database: str, fs_collection_tenants: str = "tenants"):
    """Reuse app.firebase's credentials but bind a client to the target database."""
    import firebase_admin
    from firebase_admin import credentials

    import app.firebase as fb
    from app.core.config import settings

    private_key = (
        os.environ.get("FIREBASE_PRIVATE_KEY")
        or (settings.FIREBASE_PRIVATE_KEY or "").replace("\\n", "\n")
    )
    project_id = os.environ.get("FIREBASE_PROJECT_ID") or settings.FIREBASE_PROJECT_ID
    cred = credentials.Certificate({
        "type": "service_account",
        "project_id": project_id,
        "private_key": private_key,
        "client_email": os.environ.get("FIREBASE_CLIENT_EMAIL") or settings.FIREBASE_CLIENT_EMAIL,
        "token_uri": settings.FIREBASE_TOKEN_URI,
    })
    if not firebase_admin._apps:
        app = firebase_admin.initialize_app(cred)
    else:
        app = firebase_admin.get_app()
    from google.cloud import firestore as gcs
    db = gcs.Client(project=project_id, credentials=cred.get_credential(), database=project_database)
    fb._db = db
    fb._firebase_app = app
    log.info("Firestore client bound to database=%s tenants='%s'", project_database, fs_collection_tenants)
    return db


def stream_docs(ref) -> List[Tuple[str, dict]]:
    """Return [(doc_id, doc_dict)] for a Firestore collection reference."""
    return [(snap.id, snap.to_dict() or {}) for snap in ref.stream()]


def get_tenant_ref(db, tenant: str, tenants_col: str = "tenants"):
    return db.collection(tenants_col).document(tenant)


# ── PostgreSQL (asyncpg) ─────────────────────────────────────────────────────

def _asyncpg_connect_args(url: str) -> Tuple[str, Dict[str, Any]]:
    """Split DSN from query string, mapping sslmode to asyncpg's ssl kwarg."""
    dsn = url
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = "postgresql://" + dsn[len("postgresql+asyncpg://"):]
    kwargs: Dict[str, Any] = {}
    if "?" in dsn:
        dsn, _, query = dsn.partition("?")
        params = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
        sslmode = params.get("sslmode", "").lower()
        if sslmode in ("require", "prefer"):
            kwargs["ssl"] = "require"
        elif sslmode in ("verify-ca", "verify-full"):
            kwargs["ssl"] = True
        elif sslmode == "disable":
            kwargs["ssl"] = False
    return dsn, kwargs


async def upsert_rows(conn, stats, table: str, cols: Tuple[str, ...],
                      rows: List[Tuple[Any, ...]]) -> None:
    """Batch INSERT ... ON CONFLICT (id) DO UPDATE, classifying inserts/updates.

    If a whole batch fails (e.g. a single row trips a CHECK/unique constraint
    for an out-of-range value), fall back to row-by-row so the healthy rows are
    still written and each failing row is logged as an error.
    """
    if not rows:
        return
    rows = [tuple(_jsonify(x) for x in r) for r in rows]
    placeholders = ", ".join(f"${i}" for i in range(1, len(cols) + 1))
    updated_cols = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("id", "tenant_id"))
    stmt = (
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT (id) DO UPDATE SET {updated_cols}"
    )

    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]
        existing = await conn.fetch(
            f"SELECT id::text FROM {table} WHERE id = ANY($1::uuid[])", [r[0] for r in batch]
        )
        existing_set = {r["id"] for r in existing}
        try:
            await conn.executemany(stmt, batch)
        except Exception as e:  # pragma: no cover - exercised only on bad data
            log.error("[%s] batch of %d failed (%s); retrying row-by-row", table, len(batch), e)
            for row in batch:
                try:
                    await conn.execute(stmt, *row)
                except Exception as row_err:
                    stats.record_error(table, f"row id={row[0]} rejected: {row_err}")
                    continue
                if row[0] in existing_set:
                    stats.updated(table)
                else:
                    stats.inserted(table)
            continue
        for row in batch:
            if row[0] in existing_set:
                stats.updated(table)
            else:
                stats.inserted(table)


class Stats:
    def __init__(self) -> None:
        self.by_table: Dict[str, Dict[str, int]] = {}

    def _cell(self, table: str) -> Dict[str, int]:
        return self.by_table.setdefault(table, {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0})

    def inserted(self, table: str) -> None:
        self._cell(table)["inserted"] += 1

    def updated(self, table: str) -> None:
        self._cell(table)["updated"] += 1

    def skipped(self, table: str) -> None:
        self._cell(table)["skipped"] += 1

    def record_error(self, table: str, msg: str) -> None:
        self._cell(table)["errors"] += 1
        log.error("[%s] %s", table, msg)

    def log_summary(self) -> None:
        log.info("===== MIGRATION SUMMARY =====")
        for table in sorted(self.by_table):
            c = self.by_table[table]
            log.info(
                "%-24s inserted=%-6d updated=%-6d skipped=%-6d errors=%d",
                table, c["inserted"], c["updated"], c["skipped"], c["errors"],
            )
        log.info("===== END SUMMARY =====")


stats = Stats()


def transform_safely(table: str, doc_id: str, fn: Callable[[], Optional[Dict[str, Any]]])\
        -> Optional[Dict[str, Any]]:
    try:
        return fn()
    except Exception as e:
        stats.record_error(table, f"transform failed for doc {doc_id}: {e}")
        log.debug(traceback.format_exc())
        return None


def _row(cols: Tuple[str, ...], d: Dict[str, Any]) -> Tuple[Any, ...]:
    return tuple(d[c] for c in cols)


async def _stage(table: str, cols: Tuple[str, ...], rows: List[Tuple[Any, ...]],
                 conn, dry_run: bool, tenant: str, extra: str = "") -> None:
    label = f"{table} [{extra}]" if extra else table
    if dry_run:
        log.info("[dry-run] %-24s %s staged=%d rows", label, tenant, len(rows))
        return
    if conn is not None:
        await upsert_rows(conn, stats, table, cols, rows)


# ── entity transformers ──────────────────────────────────────────────────────

def t_hazard(doc_id: str, d: dict, ctx: dict) -> Dict[str, Any]:
    return {
        "id": str(_uuid5("hazard", ctx["tenant"], doc_id)),
        "hazard_id": _s(d, "hazard_id", default=doc_id),
        "tenant_id": ctx["tenant_uuid"],
        "title": _s(d, "title"),
        "description": _s(d, "description"),
        "source": _s(d, "source", default="Other"),
        "source_id": _s(d, "source_id"),
        "source_url": _s_pick(d, ("source_url",)),
        "adrep_category": _s_pick(d, ("adrep_category",)),
        "occurrence_type": _s_pick(d, ("occurrence_type",)),
        "taxonomy": _s(d, "taxonomy", default="Other"),
        "taxonomy_specific": _s_pick(d, ("taxonomy_specific",)),
        "consequence": _s_pick(d, ("consequence",)),
        "severity": _i(d, "severity"),
        "probability": _i(d, "probability"),
        "risk_index": _i(d, "risk_index") or _i(d, "risk_score"),
        "risk_level": _s_pick(d, ("risk_level", "risk_tier")),
        "risk_outcome": _s_pick(d, ("risk_outcome",)),
        "tolerability_tier": _s_pick(d, ("tolerability_tier",)),
        "priority": _normalize_priority(_pick(d, "priority", default="M")),
        "recommended_action": _s_pick(d, ("recommended_action",)),
        "corrective_action": _s_pick(d, ("corrective_action",)),
        "assigned_to": _s_pick(d, ("assigned_to",)),
        "assigned_to_uid": _s_pick(d, ("assigned_to_uid",)),
        "department": _s_pick(d, ("department",)),
        "srm_conducted": _b(d, "srm_conducted"),
        "srm_date": _dt_key(d, "srm_date"),
        "srm_status": _s_pick(d, ("srm_status",)),
        "analysis_mode": _s(d, "analysis_mode", default="FISHBONE_ONLY"),
        "sram_data": _js(d, "sram_data"),
        "status": _s(d, "status", default="Open"),
        "follow_up_date": _dt_key(d, "follow_up_date"),
        "closed_at": _dt_key(d, "closed_at"),
        "closed_by": _s_pick(d, ("closed_by",)),
        "remarks": _s_pick(d, ("remarks",)),
        "is_demo": ctx.get("is_demo", False),
        "created_by": _s_pick(d, ("created_by",)),
        "created_at": _dt_key(d, "created_at", default=datetime.now(timezone.utc)),
        "updated_at": _dt_key(d, "updated_at", default=datetime.now(timezone.utc)),
    }


def t_report(doc_id: str, d: dict, ctx: dict) -> Dict[str, Any]:
    sev = d.get("severity")
    return {
        "id": str(_uuid5("report", ctx["tenant"], doc_id)),
        "tenant_id": ctx["tenant_uuid"],
        "report_type": _s(d, "report_type", default="voluntary"),
        "status": _s(d, "status", default="NEW"),
        "ai_status": _s(d, "ai_status", default="PENDING"),
        "narrative": _s(d, "narrative"),
        "location": _s(d, "location"),
        "occurrence_date": _dt_key(d, "occurrence_date", default=datetime.now(timezone.utc)),
        "is_anonymous": _b(d, "is_anonymous"),
        "flight_number": _s_pick(d, ("flight_number",)),
        "aircraft_registration": _s_pick(d, ("aircraft_registration",)),
        "occurrence_type": _s_pick(d, ("occurrence_type",)),
        "severity": None if sev is None else str(sev),
        "investigation_status": _s_pick(d, ("investigation_status",)),
        "severity_level": _i(d, "severity_level"),
        "probability_level": _i(d, "probability_level"),
        "risk_index": _i(d, "risk_index") or _i(d, "risk_score"),
        "risk_level": _s_pick(d, ("risk_level",)),
        "risk_assessment": _js(d, "risk_assessment"),
        "ai_suggested_assessment": _js(d, "ai_suggested_assessment"),
        "ai_analysis": _js(d, "ai_analysis"),
        "occurrence_class": _s_pick(d, ("occurrence_class",)),
        "latitude": _f(d, "latitude"),
        "longitude": _f(d, "longitude"),
        "country": _s_pick(d, ("country",)),
        "aircraft_make": _s_pick(d, ("aircraft_make",)),
        "aircraft_model": _s_pick(d, ("aircraft_model",)),
        "aircraft_serial_number": _s_pick(d, ("aircraft_serial_number",)),
        "operator": _s_pick(d, ("operator",)),
        "operator_icao": _s_pick(d, ("operator_icao",)),
        "aircraft_category": _s_pick(d, ("aircraft_category",)),
        "engine_make": _s_pick(d, ("engine_make",)),
        "engine_model": _s_pick(d, ("engine_model",)),
        "engine_serial_number": _s_pick(d, ("engine_serial_number",)),
        "flight_phase": _s_pick(d, ("flight_phase",)),
        "flight_type": _s_pick(d, ("flight_type",)),
        "departure_airport": _s_pick(d, ("departure_airport",)),
        "destination_airport": _s_pick(d, ("destination_airport",)),
        "aircraft_utilisation_hours": _f(d, "aircraft_utilisation_hours"),
        "aircraft_utilisation_cycles": _i(d, "aircraft_utilisation_cycles"),
        "crew_count": _i(d, "crew_count"),
        "passenger_count": _i(d, "passenger_count"),
        "fatal_injuries": _i(d, "fatal_injuries"),
        "serious_injuries": _i(d, "serious_injuries"),
        "minor_injuries": _i(d, "minor_injuries"),
        "occurrence_category": _s_pick(d, ("occurrence_category",)),
        "human_factors": _js(d, "human_factors"),
        "contributing_factors": _js(d, "contributing_factors"),
        "investigation_agency": _s_pick(d, ("investigation_agency",)),
        "reporter_name": _s_pick(d, ("reporter_name",)),
        "reporter_role": _s_pick(d, ("reporter_role",)),
        "reporter_email": _s_pick(d, ("reporter_email",)),
        "reporter_phone": _s_pick(d, ("reporter_phone",)),
        "reporter_organisation": _s_pick(d, ("reporter_organisation",)),
        "reporting_date": _dt_key(d, "reporting_date"),
        "etops": _b(d, "etops"),
        "propeller_make": _s_pick(d, ("propeller_make",)),
        "propeller_model": _s_pick(d, ("propeller_model",)),
        "call_sign": _s_pick(d, ("call_sign",)),
        "organisation_comments": _s_pick(d, ("organisation_comments",)),
        "manufacturer_advised": _b(d, "manufacturer_advised"),
        "fdr_data_retained": _b(d, "fdr_data_retained"),
        "is_demo": ctx.get("is_demo", False),
        "created_by": _s(d, "created_by"),
        "created_at": _dt_key(d, "created_at", default=datetime.now(timezone.utc)),
        "updated_at": _dt_key(d, "updated_at", default=datetime.now(timezone.utc)),
    }


def t_can(doc_id: str, d: dict, ctx: dict) -> Optional[Dict[str, Any]]:
    haz_ref = _pick(d, "hazard_doc_id", "hazard_id", default=None)
    haz_uuid = ctx["haz_by_doc"].get(haz_ref) or ctx["haz_by_ref"].get(haz_ref) if haz_ref else None
    if not haz_uuid:
        stats.skipped("cans")
        log.warning("[cans] skipping %s (%s): unresolvable hazard_id=%r (NOT NULL FK)", doc_id, ctx["tenant"], haz_ref)
        return None
    return {
        "id": str(_uuid5("can", ctx["tenant"], doc_id)),
        "can_reference": _s(d, "can_reference", default=f"CAN-{doc_id}"),
        "tenant_id": ctx["tenant_uuid"],
        "hazard_id": haz_uuid,
        "title": _s(d, "title"),
        "description": _s(d, "description"),
        "required_action": _s(d, "required_action"),
        "issued_by": _s(d, "issued_by"),
        "issued_by_uid": _s(d, "issued_by_uid"),
        "issued_at": _dt_key(d, "issued_at"),
        "target_completion_date": _dt_key(d, "target_completion_date"),
        "assigned_to": _s(d, "assigned_to"),
        "assigned_to_uid": _s(d, "assigned_to_uid"),
        "department": _s_pick(d, ("department",)),
        "priority": _normalize_priority_words(_pick(d, "priority", default="Medium")),
        "status": _s(d, "status", default="Open"),
        "copies_to": _s_pick(d, ("copies_to",)),
        "requested_function": _s_pick(d, ("requested_function",)),
        "addressed_function": _s_pick(d, ("addressed_function",)),
        "initial_severity": _i(d, "initial_severity"),
        "initial_probability": _i(d, "initial_probability"),
        "initial_risk_index": _i(d, "initial_risk_index"),
        "initial_risk_level": _s_pick(d, ("initial_risk_level",)),
        "initial_risk_outcome": _s_pick(d, ("initial_risk_outcome",)),
        "initial_tolerability_tier": _s_pick(d, ("initial_tolerability_tier",)),
        "initial_sra": _js(d, "initial_sra"),
        "classification_type": _s_pick(d, ("classification_type",)),
        "classification_level": _s_pick(d, ("classification_level",)),
        "is_demo": ctx.get("is_demo", False),
        "created_by": _s_pick(d, ("created_by",), default=""),
        "created_at": _dt_key(d, "created_at", default=datetime.now(timezone.utc)),
        "updated_at": _dt_key(d, "updated_at", default=datetime.now(timezone.utc)),
    }


def t_cap(doc_id: str, d: dict, ctx: dict, parent_can_doc_id: str) -> Optional[Dict[str, Any]]:
    can_uuid = ctx["can_by_doc"].get(parent_can_doc_id)
    if not can_uuid:
        stats.skipped("caps")
        log.warning("[caps] skipping %s/%s (%s): parent CAN unknown (NOT NULL FK)", parent_can_doc_id, doc_id, ctx["tenant"])
        return None
    return {
        "id": str(_uuid5("cap", ctx["tenant"], parent_can_doc_id, doc_id)),
        "cap_reference": _s(d, "cap_reference", default=f"{parent_can_doc_id}-CAP-{doc_id}"),
        "tenant_id": ctx["tenant_uuid"],
        "can_id": can_uuid,
        "action_plan": _s(d, "action_plan"),
        "timeline": _s(d, "timeline"),
        "resources_required": _s_pick(d, ("resources_required",)),
        "implementation_plan": _s_pick(d, ("implementation_plan",)),
        "department": _s_pick(d, ("department",)),
        "target_completion_date": (
            _dt_key(d, "target_completion_date")
            or _dt_key(d, "created_at")
            or datetime.now(timezone.utc)
        ),
        "submitted_by": _s(d, "submitted_by"),
        "submitted_by_uid": _s(d, "submitted_by_uid"),
        "submitted_at": _dt_key(d, "submitted_at"),
        "status": _s(d, "status", default="In Progress"),
        "reviewed_by": _s_pick(d, ("reviewed_by",)),
        "reviewed_by_uid": _s_pick(d, ("reviewed_by_uid",)),
        "reviewed_at": _dt_key(d, "reviewed_at"),
        "review_comments": _s_pick(d, ("review_comments",)),
        "revision_deadline": _dt_key(d, "revision_deadline"),
        "company_name": _s_pick(d, ("company_name",)),
        "base_location": _s_pick(d, ("base_location",)),
        "area_system_of_interest": _s_pick(d, ("area_system_of_interest",)),
        "finding_number": _s_pick(d, ("finding_number",)),
        "file_ref": _s_pick(d, ("file_ref",)),
        "factual_review": _s_pick(d, ("factual_review",)),
        "rca": _s_pick(d, ("rca",)),
        "short_term_ca": _s_pick(d, ("short_term_ca",)),
        "long_term_ca": _s_pick(d, ("long_term_ca",)),
        "implementation_timeline": _s_pick(d, ("implementation_timeline",)),
        "managerial_approval": _js(d, "managerial_approval"),
        "caa_acceptance": _js(d, "caa_acceptance"),
        "residual_severity": _i(d, "residual_severity"),
        "residual_probability": _i(d, "residual_probability"),
        "residual_risk_index": _i(d, "residual_risk_index"),
        "residual_risk_level": _s_pick(d, ("residual_risk_level",)),
        "residual_risk_outcome": _s_pick(d, ("residual_risk_outcome",)),
        "residual_tolerability_tier": _s_pick(d, ("residual_tolerability_tier",)),
        "residual_sra": _js(d, "residual_sra"),
        "root_causes": _js(d, "root_causes"),
        "action_items": _js(d, "action_items"),
        "rca_method": _normalize_rca_method(d.get("rca_method")),
        "sram_data": _js(d, "sram_data"),
        "escalated_to_ae": _b(d, "escalated_to_ae"),
        "escalated_by": _s_pick(d, ("escalated_by",)),
        "escalated_at": _dt_key(d, "escalated_at"),
        "escalation_reason": _s_pick(d, ("escalation_reason",)),
        "ae_signature": _s_pick(d, ("ae_signature",)),
        "ae_signed_at": _dt_key(d, "ae_signed_at"),
        "ae_review_interval_days": _i(d, "ae_review_interval_days"),
        "ae_review_date": _dt_key(d, "ae_review_date"),
        "sag_sign": _s_pick(d, ("sag_sign",)),
        "sag_signed_by": _s_pick(d, ("sag_signed_by",)),
        "sag_signed_at": _dt_key(d, "sag_signed_at"),
        "manager_approval": _s_pick(d, ("manager_approval",)),
        "ca_acceptance": _s_pick(d, ("ca_acceptance",)),
        "process_owner": _s_pick(d, ("process_owner",)),
        "manager_confirmation": _s_pick(d, ("manager_confirmation",)),
        "closing_remarks": _s_pick(d, ("closing_remarks",)),
        "closed_by": _s_pick(d, ("closed_by",)),
        "closed_at": _dt_key(d, "closed_at"),
        "closed_signature": _s_pick(d, ("closed_signature",)),
        "is_demo": ctx.get("is_demo", False),
        "created_at": _dt_key(d, "created_at", default=datetime.now(timezone.utc)),
        "updated_at": _dt_key(d, "updated_at", default=datetime.now(timezone.utc)),
    }


def t_survey(doc_id: str, d: dict, ctx: dict) -> Dict[str, Any]:
    return {
        "id": str(_uuid5("survey", ctx["tenant"], doc_id)),
        "tenant_id": ctx["tenant_uuid"],
        "submitted_at": _dt_key(d, "submitted_at", "submittedAt", default=datetime.now(timezone.utc)),
        "respondent_id": _s_pick(d, ("respondent_id", "respondentId", "respondent_name")),
        "department": _s_pick(d, ("department",)),
        "employee_category": _s_pick(d, ("employee_category",)),
        "years_experience": _s_pick(d, ("years_experience", "years_of_experience")),
        "language_used": _s(d, "language_used", default="en"),
        "survey_version": _s(d, "survey_version", default="3.0.0"),
        "seed_version": _s_pick(d, ("seed_version",)),
        "answers": _js(d, "answers") or {},
        "question_scores": _js(d, "question_scores") or _js(d, "questionScores"),
        "element_scores": _js(d, "element_scores") or _element_scores_from_doc(d),
        "safety_policy": _i(d, "safety_policy"),
        "safety_risk_management": _i(d, "safety_risk_management"),
        "safety_assurance": _i(d, "safety_assurance"),
        "safety_promotion": _i(d, "safety_promotion"),
        "overall_sms_maturity": _i(d, "overall_sms_maturity") or _i(d, "overallSMSMaturity"),
        "overall_score_pct": _f(d, "overall_score_pct"),
        "is_demo": ctx.get("is_demo", False),
    }


def _element_scores_from_doc(d: dict) -> Optional[dict]:
    keys = [
        "management_commitment", "safety_accountability", "key_safety_personnel",
        "emergency_response_planning", "sms_documentation", "hazard_identification",
        "risk_assessment_and_mitigation", "safety_performance_monitoring",
        "management_of_change", "continuous_improvement", "training_and_education",
        "safety_communication",
    ]
    present = {k: d[k] for k in keys if d.get(k) is not None}
    return present or None


def t_survey_response(doc_id: str, d: dict, ctx: dict) -> Dict[str, Any]:
    return {
        "id": str(_uuid5("response", ctx["tenant"], doc_id)),
        "tenant_id": ctx["tenant_uuid"],
        "respondent_id": _s_pick(d, ("respondent_id", "respondentId")),
        "answers": _js(d, "answers") or {},
        "department": _s_pick(d, ("department",)),
        "employee_category": _s_pick(d, ("employee_category",)),
        "years_experience": _s_pick(d, ("years_experience",)),
        "language_used": _s(d, "language_used", default="en"),
        "submitted_at": _dt_key(d, "submitted_at", "submittedAt", default=datetime.now(timezone.utc)),
        "survey_version": _s(d, "survey_version", default="3.0.0"),
        "is_demo": ctx.get("is_demo", False),
    }


def t_diversion(doc_id: str, d: dict, ctx: dict) -> Dict[str, Any]:
    return {
        "id": str(_uuid5("diversion", ctx["tenant"], doc_id)),
        "diversion_id": _s(d, "diversion_id", default=doc_id),
        "tenant_id": ctx["tenant_uuid"],
        "date": _dt_key(d, "date", default=datetime.now(timezone.utc)),
        "flight_number": _s(d, "flight_number"),
        "aircraft_registration": _s(d, "aircraft_registration"),
        "sector_from": _s(d, "sector_from"),
        "sector_to": _s(d, "sector_to"),
        "diverted_to": _s(d, "diverted_to"),
        "reason": _s(d, "reason"),
        "reason_details": _s_pick(d, ("reason_details",)),
        "captain": _s_pick(d, ("captain",)),
        "first_officer": _s_pick(d, ("first_officer",)),
        "air_hostess": _s_pick(d, ("air_hostess",)),
        "description": _s(d, "description"),
        "additional_fuel_cost": _f(d, "additional_fuel_cost"),
        "passenger_impact": _i(d, "passenger_impact"),
        "delay_minutes": _i(d, "delay_minutes"),
        "remarks": _s_pick(d, ("remarks",)),
        "status": _s(d, "status", default="Pending"),
        "hazard_id": ctx["haz_by_ref"].get(d["hazard_id"]) if d.get("hazard_id") else None,
        "hazard_link_url": _s_pick(d, ("hazard_link_url",)),
        "created_by": _s_pick(d, ("created_by",)),
        "updated_by": _s_pick(d, ("updated_by",)),
        "created_at": _dt_key(d, "created_at", default=datetime.now(timezone.utc)),
        "updated_at": _dt_key(d, "updated_at", default=datetime.now(timezone.utc)),
    }


def t_corrective_action(doc_id: str, d: dict, ctx: dict) -> Dict[str, Any]:
    hz = _pick(d, "hazard_doc_id", "hazard_id", default=None)
    haz_uuid = ctx["haz_by_doc"].get(hz) or ctx["haz_by_ref"].get(hz) if hz else None
    cn = _pick(d, "can_doc_id", "can_id", default=None)
    can_uuid = ctx["can_by_doc"].get(cn) if cn else None
    return {
        "id": str(_uuid5("ca", ctx["tenant"], doc_id)),
        "tenant_id": ctx["tenant_uuid"],
        "hazard_id": haz_uuid,
        "can_id": can_uuid,
        "event_id": _s_pick(d, ("event_id",)) or None,
        "title": _s(d, "title"),
        "description": _s(d, "description"),
        "action_plan": _s(d, "action_plan"),
        "priority": _normalize_priority_words(_pick(d, "priority", default="Medium")),
        "assigned_to": _s_pick(d, ("assigned_to",)),
        "assigned_to_uid": _s_pick(d, ("assigned_to_uid",)),
        "assigned_by": _s_pick(d, ("assigned_by",)),
        "assigned_at": _dt_key(d, "assigned_at"),
        "target_completion_date": _dt_key(d, "target_completion_date"),
        "completed_at": _dt_key(d, "completed_at"),
        "reviewed_by": _s_pick(d, ("reviewed_by",)),
        "reviewed_at": _dt_key(d, "reviewed_at"),
        "review_comments": _s_pick(d, ("review_comments",)),
        "status": _s(d, "status", default="Open"),
        "remarks": _s_pick(d, ("remarks",)),
        "created_by": _s_pick(d, ("created_by",)),
        "updated_by": _s_pick(d, ("updated_by",)),
        "created_at": _dt_key(d, "created_at", default=datetime.now(timezone.utc)),
        "updated_at": _dt_key(d, "updated_at", default=datetime.now(timezone.utc)),
    }


def t_safety_deficiency(doc_id: str, d: dict, ctx: dict) -> Dict[str, Any]:
    return {
        "id": str(_uuid5("deficiency", ctx["tenant"], doc_id)),
        "tenant_id": ctx["tenant_uuid"],
        "event_id": _s_pick(d, ("event_id",)) or None,
        "source": _s(d, "source"),
        "hazard_code": _s_pick(d, ("hazard_code",)),
        "description": _s(d, "description"),
        "taxonomy_main": _s_pick(d, ("taxonomy_main",)),
        "taxonomy_type": _s_pick(d, ("taxonomy_type",)),
        "taxonomy_specific": _s_pick(d, ("taxonomy_specific",)),
        "unsafe_event": _s_pick(d, ("unsafe_event",)),
        "identified_hazard": _s_pick(d, ("identified_hazard",)),
        "priority": _normalize_priority(_pick(d, "priority", default=None), default=None),
        "severity": _s_pick(d, ("severity",)),
        "assigned_to": _s_pick(d, ("assigned_to",)),
        "assigned_to_uid": _s_pick(d, ("assigned_to_uid",)),
        "assigned_by": _s_pick(d, ("assigned_by",)),
        "assigned_at": _dt_key(d, "assigned_at"),
        "follow_up_date": _dt_key(d, "follow_up_date"),
        "completed_at": _dt_key(d, "completed_at"),
        "status": _s(d, "status", default="Open"),
        "remarks": _s_pick(d, ("remarks",)),
        "csd_remarks": _s_pick(d, ("csd_remarks",)),
        "created_by": _s_pick(d, ("created_by",)),
        "updated_by": _s_pick(d, ("updated_by",)),
        "created_at": _dt_key(d, "created_at", default=datetime.now(timezone.utc)),
        "updated_at": _dt_key(d, "updated_at", default=datetime.now(timezone.utc)),
    }


def t_verification(doc_id: str, d: dict, ctx: dict,
                   parent_hazard_doc_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    hz_ref = _pick(d, "hazard_id", default=parent_hazard_doc_id)
    haz_uuid = None
    if hz_ref:
        haz_uuid = ctx["haz_by_doc"].get(hz_ref) or ctx["haz_by_ref"].get(hz_ref)
    if not haz_uuid:
        stats.skipped("verifications")
        log.warning("[verifications] skipping %s (%s): unresolvable hazard_id=%r (NOT NULL FK)",
                    doc_id, ctx["tenant"], hz_ref)
        return None
    c = d.get("cap_id")
    return {
        "id": str(_uuid5("verification", ctx["tenant"], parent_hazard_doc_id or "", doc_id)),
        "tenant_id": ctx["tenant_uuid"],
        "hazard_id": haz_uuid,
        "cap_id": ctx["cap_by_doc"].get(c) if c else None,
        "outcome": _s(d, "outcome"),
        "comments": _s_pick(d, ("comments",)),
        "evidence": _js(d, "evidence"),
        "verified_by": _s(d, "verified_by"),
        "verified_by_uid": _s(d, "verified_by_uid"),
        "verification_date": _dt_key(d, "verification_date", default=datetime.now(timezone.utc)),
        "revision_deadline": _dt_key(d, "revision_deadline"),
        "revision_notes": _s_pick(d, ("revision_notes",)),
        "created_at": _dt_key(d, "created_at", default=datetime.now(timezone.utc)),
        "updated_at": _dt_key(d, "updated_at", default=datetime.now(timezone.utc)),
    }


def t_closure(doc_id: str, d: dict, ctx: dict,
              parent_hazard_doc_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    hz_ref = _pick(d, "hazard_id", default=parent_hazard_doc_id)
    haz_uuid = None
    if hz_ref:
        haz_uuid = ctx["haz_by_doc"].get(hz_ref) or ctx["haz_by_ref"].get(hz_ref)
    if not haz_uuid:
        stats.skipped("closures")
        log.warning("[closures] skipping %s (%s): unresolvable hazard_id=%r (NOT NULL FK)",
                    doc_id, ctx["tenant"], hz_ref)
        return None
    return {
        "id": str(_uuid5("closure", ctx["tenant"], parent_hazard_doc_id or "", doc_id)),
        "tenant_id": ctx["tenant_uuid"],
        "hazard_id": haz_uuid,
        "lessons_learned": _s_pick(d, ("lessons_learned",)),
        "recommendations": _s_pick(d, ("recommendations",)),
        "approval_notes": _s_pick(d, ("approval_notes",)),
        "approved_by": _s(d, "approved_by"),
        "approved_by_uid": _s(d, "approved_by_uid"),
        "approved_at": _dt_key(d, "approved_at", default=datetime.now(timezone.utc)),
        "created_at": _dt_key(d, "created_at", default=datetime.now(timezone.utc)),
        "updated_at": _dt_key(d, "updated_at", default=datetime.now(timezone.utc)),
    }


def t_state_risk(doc_id: str, d: dict, ctx: dict) -> Dict[str, Any]:
    return {
        "id": str(_uuid5("state_risk", doc_id)),
        "tenant_id": _tenant_uuid(STATE_TENANT_SLUG),
        "icoc_category": _s(d, "icoc_category"),
        "description": _s_pick(d, ("description", "name"), default=""),
        "icao_reference": _s_pick(d, ("icao_reference",)),
        "current_risk_index": _i(d, "current_risk_index"),
        "tolerability": _s(d, "tolerability", default="Tolerable"),
        "tolerability_tier": _s_pick(d, ("tolerability_tier",)),
        "level": _s_pick(d, ("level",)),
        "ssp_target": _f(d, "ssp_target"),
        "actual_ssp_value": _f(d, "actual_ssp_value"),
        "risk_reduction_rate": _f(d, "risk_reduction_rate"),
        "trend": _s(d, "trend", default="stable"),
        "contributing_tenants": _js(d, "contributing_tenants"),
        "quarter": _i(d, "quarter"),
        "year": _i(d, "year"),
        "is_demo": ctx.get("is_demo", False),
        "updated_by": _s_pick(d, ("updated_by",)),
        "created_at": _dt_key(d, "created_at", default=datetime.now(timezone.utc)),
        "updated_at": _dt_key(d, "updated_at", default=datetime.now(timezone.utc)),
    }


def t_psoe(doc_id: str, d: dict, ctx: dict) -> Optional[Dict[str, Any]]:
    tenant_slug = _s_pick(d, ("tenant_id",)) or None
    if not tenant_slug:
        stats.skipped("psoe_assessments")
        log.warning("[psoe_assessments] skipping %s: no tenant_id on doc", doc_id)
        return None
    return {
        "id": str(_uuid5("psoe", doc_id)),
        "tenant_id": _tenant_uuid(tenant_slug),
        "title": _s(d, "title"),
        "status": _s(d, "status", default="draft"),
        "department": _s_pick(d, ("department",)),
        "scope": _s_pick(d, ("scope",)),
        "auditor_name": _s_pick(d, ("auditor_name",)),
        "assessor_email": _s_pick(d, ("assessor_email",)),
        "assessment_date": _dt_key(d, "assessment_date"),
        "template_version": _s(d, "template_version", default="1.0.0"),
        "responses": _js(d, "responses") or [],
        "component_scores": _js(d, "component_scores"),
        "overall_score_pct": _f(d, "overall_score_pct"),
        "overall_level": _s_pick(d, ("overall_level",)),
        "notes": _s_pick(d, ("notes",)),
        "is_demo": ctx.get("is_demo", False),
        "created_by": _s_pick(d, ("created_by",)),
        "created_by_uid": _s_pick(d, ("created_by_uid",)),
        "created_at": _dt_key(d, "created_at", default=datetime.now(timezone.utc)),
        "updated_at": _dt_key(d, "updated_at", default=datetime.now(timezone.utc)),
    }


def t_reg_report(doc_id: str, d: dict, ctx: dict, tenant_slug: Optional[str] = None) -> Dict[str, Any]:
    slug = _s_pick(d, ("tenant_id",)) or tenant_slug or STATE_TENANT_SLUG
    return {
        "id": str(_uuid5("regreport", slug, doc_id)),
        "tenant_id": _tenant_uuid(slug),
        "report_type": _s(d, "report_type"),
        "period": _s(d, "period", default=""),
        "year": _i(d, "year", default=0),
        "quarter": _i(d, "quarter"),
        "status": _s(d, "status", default="completed"),
        "summary": _js(d, "summary"),
        "data": _js(d, "data"),
        "generated_at": _dt_key(d, "generated_at"),
        "generated_by": _s_pick(d, ("generated_by",)),
        "file_url": _s_pick(d, ("file_url",)),
        "is_demo": ctx.get("is_demo", False),
        "created_at": _dt_key(d, "created_at", default=datetime.now(timezone.utc)),
        "updated_at": _dt_key(d, "updated_at", default=datetime.now(timezone.utc)),
    }


# ── entity registration (transform + columns per table) ─────────────────────

class Entity:
    def __init__(self, table: str, cols: Tuple[str, ...], fn: Callable,
                 unique_key: Optional[str] = None):
        self.table = table
        self.cols = cols
        self.fn = fn
        self.unique_key = unique_key  # business key; per-tenant duplicate guard


# tenant-scoped entities, ordered so FK dependencies build their id maps first
TENANT_ENTITIES: List[Entity] = [
    Entity("hazards", HAZARD_COLS, t_hazard, unique_key="hazard_id"),
    Entity("reports", REPORT_COLS, t_report),
    Entity("cans", CAN_COLS, t_can, unique_key="can_reference"),
    Entity("caps", CAP_COLS, t_cap, unique_key="cap_reference"),
    Entity("surveys", SURVEY_COLS, t_survey),
    Entity("survey_responses", SURVEY_RESPONSE_COLS, t_survey_response),
    Entity("flight_diversions", DIVERSION_COLS, t_diversion, unique_key="diversion_id"),
    Entity("corrective_actions", CORRECTIVE_ACTION_COLS, t_corrective_action),
    Entity("safety_deficiencies", SAFETY_DEFICIENCY_COLS, t_safety_deficiency),
]

# collection name on the tenant doc for each tenant entity
ENTITY_COLLECTIONS = {
    "hazards": "hazards",
    "reports": "reports",
    "cans": "can_cap",
    "caps": "caps",  # subcollection of each CAN doc
    "surveys": "surveys",
    "survey_responses": "responses",
    "flight_diversions": "flight_diversions",
    "corrective_actions": "corrective_actions",
    "safety_deficiencies": "safety_deficiencies",
}

# ── orchestrator ─────────────────────────────────────────────────────────────

def selected(args, entity: str) -> bool:
    return entity in args.only if args.only else True


async def run(conn, args, fs) -> None:
    tenant_slugs = sorted(args.tenant) if args.tenant else sorted(
        d.id for d in fs.collection(args.tenants_col).stream()
    )
    tenants_for_reg_reports = tenant_slugs if selected(args, "regulatory_reports") else []

    log.info("Migrating %d tenant(s): %s | database=%s dry_run=%s",
             len(tenant_slugs), ", ".join(tenant_slugs), args.database, args.dry_run)
    log.info("Entities: %s", ", ".join(sorted(args.only)) if args.only else "all")

    is_demo_value = False
    log.info("is_demo scope: %s (single consolidated database %s)", is_demo_value, args.database)

    for t in tenant_slugs:
        ctx: Dict[str, Any] = {
            "tenant": t,
            "tenant_uuid": _tenant_uuid(t),
            "is_demo": is_demo_value,
        }
        ten_ref = get_tenant_ref(fs, t, args.tenants_col)

        # Build FK id maps first (deterministic; mirrors the ids the transforms emit).
        if selected(args, "hazards"):
            haz_by_doc, haz_by_ref = {}, {}
            for doc_id, d in stream_docs(ten_ref.collection("hazards")):
                pg = str(_uuid5("hazard", t, doc_id))
                haz_by_doc[doc_id] = pg
                haz_by_ref[_s(d, "hazard_id", default=doc_id)] = pg
            ctx["haz_by_doc"], ctx["haz_by_ref"] = haz_by_doc, haz_by_ref
        else:
            ctx["haz_by_doc"], ctx["haz_by_ref"] = {}, {}

        if selected(args, "cans"):
            can_by_doc = {c_id: str(_uuid5("can", t, c_id))
                          for c_id, _ in stream_docs(ten_ref.collection("can_cap"))}
        else:
            can_by_doc = {}
        ctx["can_by_doc"] = can_by_doc

        cap_by_doc: Dict[str, str] = {}
        if selected(args, "caps"):
            # Firestore auto ids are globally unique, so cap doc id -> pg uuid is safe.
            for c_id, _ in stream_docs(ten_ref.collection("can_cap")):
                for x_id, _ in stream_docs(ten_ref.collection("can_cap").document(c_id).collection("caps")):
                    cap_by_doc[x_id] = str(_uuid5("cap", t, c_id, x_id))
        ctx["cap_by_doc"] = cap_by_doc

        # ── hazards ──
        if selected(args, "hazards"):
            rows, seen = [], set()
            for doc_id, d in stream_docs(ten_ref.collection("hazards")):
                rd = transform_safely("hazards", doc_id, lambda d=d, i=doc_id: t_hazard(i, d, ctx))
                if rd is None:
                    continue
                if rd["hazard_id"] in seen:
                    stats.skipped("hazards")
                    log.warning("[hazards] duplicate hazard_id=%s (%s)", rd["hazard_id"], t)
                    continue
                seen.add(rd["hazard_id"])
                rows.append(_row(HAZARD_COLS, rd))
            await _stage("hazards", HAZARD_COLS, rows, conn, args.dry_run, t)

        # ── reports (VSR/MOR) ──
        if selected(args, "reports"):
            rows = []
            for doc_id, d in stream_docs(ten_ref.collection("reports")):
                rd = transform_safely("reports", doc_id, lambda d=d, i=doc_id: t_report(i, d, ctx))
                if rd is not None:
                    rows.append(_row(REPORT_COLS, rd))
            await _stage("reports", REPORT_COLS, rows, conn, args.dry_run, t)

        # ── CANs (collection `can_cap`) ──
        if selected(args, "cans"):
            rows, seen = [], set()
            for doc_id, d in stream_docs(ten_ref.collection("can_cap")):
                rd = transform_safely("cans", doc_id, lambda d=d, i=doc_id: t_can(i, d, ctx))
                if rd is None:
                    continue
                if rd["can_reference"] in seen:
                    stats.skipped("cans")
                    log.warning("[cans] duplicate can_reference=%s (%s)", rd["can_reference"], t)
                    continue
                seen.add(rd["can_reference"])
                rows.append(_row(CAN_COLS, rd))
            await _stage("cans", CAN_COLS, rows, conn, args.dry_run, t)

        # ── CAPs (subcollection of each CAN doc) ──
        if selected(args, "caps"):
            rows, seen = [], set()
            for c_id, _ in stream_docs(ten_ref.collection("can_cap")):
                caps_ref = ten_ref.collection("can_cap").document(c_id).collection("caps")
                for x_id, d in stream_docs(caps_ref):
                    rd = transform_safely("caps", x_id,
                                          lambda d=d, x=x_id, c=c_id: t_cap(x, d, ctx, c))
                    if rd is None:
                        continue
                    if rd["cap_reference"] in seen:
                        stats.skipped("caps")
                        log.warning("[caps] duplicate cap_reference=%s (%s)", rd["cap_reference"], t)
                        continue
                    seen.add(rd["cap_reference"])
                    rows.append(_row(CAP_COLS, rd))
            await _stage("caps", CAP_COLS, rows, conn, args.dry_run, t)

        # ── surveys + raw responses ──
        if selected(args, "surveys"):
            rows = []
            for doc_id, d in stream_docs(ten_ref.collection("surveys")):
                rd = transform_safely("surveys", doc_id, lambda d=d, i=doc_id: t_survey(i, d, ctx))
                if rd is not None:
                    rows.append(_row(SURVEY_COLS, rd))
            await _stage("surveys", SURVEY_COLS, rows, conn, args.dry_run, t)

        if selected(args, "survey_responses"):
            rows = []
            for doc_id, d in stream_docs(ten_ref.collection("responses")):
                rd = transform_safely("survey_responses", doc_id,
                                      lambda d=d, i=doc_id: t_survey_response(i, d, ctx))
                if rd is not None:
                    rows.append(_row(SURVEY_RESPONSE_COLS, rd))
            await _stage("survey_responses", SURVEY_RESPONSE_COLS, rows, conn, args.dry_run, t)

        # ── flight diversions ──
        if selected(args, "flight_diversions"):
            rows, seen = [], set()
            for doc_id, d in stream_docs(ten_ref.collection("flight_diversions")):
                rd = transform_safely("flight_diversions", doc_id,
                                      lambda d=d, i=doc_id: t_diversion(i, d, ctx))
                if rd is None:
                    continue
                if rd["diversion_id"] in seen:
                    stats.skipped("flight_diversions")
                    log.warning("[flight_diversions] duplicate diversion_id=%s (%s)", rd["diversion_id"], t)
                    continue
                seen.add(rd["diversion_id"])
                rows.append(_row(DIVERSION_COLS, rd))
            await _stage("flight_diversions", DIVERSION_COLS, rows, conn, args.dry_run, t)

        # ── corrective actions / safety deficiencies ──
        if selected(args, "corrective_actions"):
            rows = []
            for doc_id, d in stream_docs(ten_ref.collection("corrective_actions")):
                rd = transform_safely("corrective_actions", doc_id,
                                      lambda d=d, i=doc_id: t_corrective_action(i, d, ctx))
                if rd is not None:
                    rows.append(_row(CORRECTIVE_ACTION_COLS, rd))
            await _stage("corrective_actions", CORRECTIVE_ACTION_COLS, rows, conn, args.dry_run, t)

        if selected(args, "safety_deficiencies"):
            rows = []
            for doc_id, d in stream_docs(ten_ref.collection("safety_deficiencies")):
                rd = transform_safely("safety_deficiencies", doc_id,
                                      lambda d=d, i=doc_id: t_safety_deficiency(i, d, ctx))
                if rd is not None:
                    rows.append(_row(SAFETY_DEFICIENCY_COLS, rd))
            await _stage("safety_deficiencies", SAFETY_DEFICIENCY_COLS, rows, conn, args.dry_run, t)

        # ── verifications (legacy tenant collection + nested under hazards) ──
        if selected(args, "verifications"):
            rows = []
            for doc_id, d in stream_docs(ten_ref.collection("verification")):
                rd = transform_safely("verifications", doc_id,
                                      lambda d=d, i=doc_id: t_verification(i, d, ctx))
                if rd is not None:
                    rows.append(_row(VERIFICATION_COLS, rd))
            await _stage("verifications", VERIFICATION_COLS, rows, conn, args.dry_run, t, extra="legacy")

            rows = []
            for h_id, _ in stream_docs(ten_ref.collection("hazards")):
                vref = ten_ref.collection("hazards").document(h_id).collection("verifications")
                for doc_id, d in stream_docs(vref):
                    rd = transform_safely("verifications", doc_id,
                                          lambda d=d, i=doc_id, h=h_id: t_verification(i, d, ctx, parent_hazard_doc_id=h))
                    if rd is not None:
                        rows.append(_row(VERIFICATION_COLS, rd))
            await _stage("verifications", VERIFICATION_COLS, rows, conn, args.dry_run, t, extra="nested")

        # ── closures (nested under hazards) ──
        if selected(args, "closures"):
            rows = []
            for h_id, _ in stream_docs(ten_ref.collection("hazards")):
                cref = ten_ref.collection("hazards").document(h_id).collection("closure")
                for doc_id, d in stream_docs(cref):
                    rd = transform_safely("closures", doc_id,
                                          lambda d=d, i=doc_id, h=h_id: t_closure(i, d, ctx, parent_hazard_doc_id=h))
                    if rd is not None:
                        rows.append(_row(CLOSURE_COLS, rd))
            await _stage("closures", CLOSURE_COLS, rows, conn, args.dry_run, t)

        # ── regulatory reports (tenant-scoped) ──
        if selected(args, "regulatory_reports"):
            rows = []
            for doc_id, d in stream_docs(ten_ref.collection("reporting")):
                rd = transform_safely("regulatory_reports", doc_id,
                                      lambda d=d, i=doc_id: t_reg_report(i, d, ctx, tenant_slug=None))
                if rd is not None:
                    rows.append(_row(REG_REPORT_COLS, rd))
            await _stage("regulatory_reports", REG_REPORT_COLS, rows, conn, args.dry_run, t, extra="tenant")

    # ── global entities ──
    if selected(args, "state_risk_register"):
        rows = []
        for doc_id, d in stream_docs(fs.collection("state").document("ssp").collection("risk_register")):
            rd = transform_safely("state_risk_register", doc_id,
                                  lambda d=d, i=doc_id: t_state_risk(i, d, {"is_demo": is_demo_value}))
            if rd is not None:
                rows.append(_row(STATE_RISK_COLS, rd))
        await _stage("state_risk_register", STATE_RISK_COLS, rows, conn, args.dry_run, "global")

    if selected(args, "psoe_assessments"):
        rows = []
        for doc_id, d in stream_docs(fs.collection("psoe_assessments")):
            rd = transform_safely("psoe_assessments", doc_id, lambda d=d, i=doc_id: t_psoe(i, d, {"is_demo": is_demo_value}))
            if rd is not None:
                rows.append(_row(PSOE_COLS, rd))
        await _stage("psoe_assessments", PSOE_COLS, rows, conn, args.dry_run, "global")

    if selected(args, "regulatory_reports"):
        rows = []
        try:
            for doc_id, d in stream_docs(fs.collection("caan_reports")):
                rd = transform_safely("regulatory_reports", doc_id,
                                      lambda d=d, i=doc_id: t_reg_report(i, d, {"is_demo": is_demo_value}, tenant_slug=None))
                if rd is not None:
                    rows.append(_row(REG_REPORT_COLS, rd))
        except Exception as e:
            log.warning("[regulatory_reports] caan_reports collection unavailable: %s", e)
        await _stage("regulatory_reports", REG_REPORT_COLS, rows, conn, args.dry_run, "global", extra="caan")


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args(argv):
    from app.core.config import settings
    p = argparse.ArgumentParser(description="Migrate Firestore -> Supabase (schema.sql)")
    default_db = os.environ.get("FIREBASE_DATABASE_ID") or settings.FIREBASE_DATABASE_ID or DEFAULT_DATABASE
    p.add_argument("--database", default=default_db,
                   help="Firestore database id (default: $FIREBASE_DATABASE_ID / settings, else sms-db)")
    p.add_argument("--database-url", default=None,
                   help="Supabase Service Role postgres URL (default: $SUPABASE_DATABASE_URL or $DATABASE_URL)")
    p.add_argument("--tenant", action="append", default=[], help="Restrict to tenant slug (repeatable)")
    p.add_argument("--only", action="append", default=[],
                   help="Restrict to entities: hazards,reports,cans,caps,surveys,survey_responses,"
                        "flight_diversions,verifications,closures,corrective_actions,safety_deficiencies,"
                        "state_risk_register,psoe_assessments,regulatory_reports (repeatable)")
    p.add_argument("--dry-run", action="store_true", help="Transform only; no DB writes")
    return p.parse_args(argv)


async def main_async(args):
    fs = init_firestore(args.database)
    args.tenants_col = "tenants"

    conn = None
    if not args.dry_run:
        from app.core.config import settings
        db_url = (
            args.database_url
            or os.environ.get("SUPABASE_DATABASE_URL")
            or os.environ.get("DATABASE_URL")
            or settings.DATABASE_URL
        )
        if not db_url:
            raise SystemExit(
                "DATABASE_URL not found. Pass --database-url (Supabase Service Role URL) or "
                "set SUPABASE_DATABASE_URL / DATABASE_URL."
            )
        import asyncpg
        dsn, kwargs = _asyncpg_connect_args(db_url)
        log.info("Connecting to Supabase PostgreSQL ...")
        conn = await asyncpg.connect(dsn, **kwargs)
        log.info("Connected. (service role / BYPASSRLS assumed for migration writes)")

    try:
        await run(conn, args, fs)
    finally:
        if conn is not None:
            await conn.close()

    stats.log_summary()
    log.info("Migration complete. Logs appended to %s", LOG_FILE)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    asyncio.run(main_async(args))