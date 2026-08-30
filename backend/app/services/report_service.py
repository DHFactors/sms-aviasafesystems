# ==============================================================================
# File: backend/app/services/report_service.py
# Description: Multi-tenant repository and business logic for safety reports
#              (VSR / MOR), backed by PostgreSQL (Supabase).
#
#              ReportService(tenant_id) preserves the legacy sync API used by
#              the mounted reports router. Every method keeps its old signature
#              and Firestore-era dict shape (the route response helpers read
#              the same keys) but persists to the `reports` table via the async
#              engine, dispatching through app.db.runner.
#
#              `analyze_report` / `classify_mandatory` stay module-level
#              imports so tests can monkeypatch them on this module.
# ==============================================================================

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select

from app.core.config import settings
from app.core.metrics import record_ai_result
from app.db.db_models import Report
from app.db.ids import register_tenant, tenant_slug
from app.db.isolation import demo_scope
from app.db.runner import run
from app.db.session import session_scope
from app.services.gemini import analyze_report, classify_mandatory
from app.services.repository import ReportRepository, coerce_utc_datetime
from app.services.risk_matrix import (
    compute_risk_index,
    get_risk_level,
    get_thresholds,
    get_tolerability_tier,
)


def _dt(value: Any):
    """Coerce a payload timestamp (datetime or ISO string) to an aware datetime
    for asyncpg timestamptz columns (it rejects raw strings)."""
    return coerce_utc_datetime(value)


def _json_safe(value: Any) -> Any:
    """Deep-convert datetimes inside dict/list payloads to ISO strings so the
    JSONB bind processor can serialise them (json.dumps cannot handle datetime)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


def _as_uuid(value: Any) -> Optional[uuid.UUID]:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


_REPORT_SKIP_COLUMNS = {"id"}
_REPORT_DT_COLUMNS = {"occurrence_date", "reporting_date", "created_at", "updated_at"}
_REPORT_JSONB_COLUMNS = {
    "risk_assessment",
    "ai_suggested_assessment",
    "ai_analysis",
    "human_factors",
    "contributing_factors",
}


def _report_to_dict(row: Report) -> dict:
    data = {}
    for col in Report.__table__.columns:
        value = getattr(row, col.name)
        if isinstance(value, uuid.UUID):
            value = str(value)
        data[col.name] = value
    data["tenant_id"] = tenant_slug(row.tenant_id)
    if row.risk_index is not None:
        data["tolerability_tier"] = get_tolerability_tier(
            row.risk_index, get_thresholds(data["tenant_id"])
        )
    return _json_safe(data)


def _report_lookup_stmt(tenant_uuid_value: Optional[uuid.UUID], value: uuid.UUID):
    stmt = select(Report).where(Report.id == value, Report.is_demo == demo_scope())
    if tenant_uuid_value is not None:
        stmt = stmt.where(Report.tenant_id == tenant_uuid_value)
    return stmt


async def _create_report_async(self, values: dict) -> Report:
    async with session_scope() as session:
        row = Report(**values)
        session.add(row)
        await session.flush()
        return row


async def _get_reports_async(self, cross_tenant: bool, tenant_uuid_value: uuid.UUID) -> list:
    stmt = (
        select(Report)
        .where(Report.is_demo == demo_scope())
        .order_by(Report.created_at.desc())
    )
    if cross_tenant:
        stmt = stmt.limit(settings.REPO_QUERY_LIMIT)
    else:
        stmt = stmt.where(Report.tenant_id == tenant_uuid_value)
    async with session_scope() as session:
        rows = (await session.execute(stmt)).scalars().all()
        return [_report_to_dict(r) for r in rows]


async def _get_report_async(self, tenant_uuid_value: Optional[uuid.UUID], report_uuid: uuid.UUID):
    async with session_scope() as session:
        row = (
            await session.execute(_report_lookup_stmt(tenant_uuid_value, report_uuid))
        ).scalars().first()
        if not row:
            return None
        return _report_to_dict(row)


async def _set_ai_status_async(self, tid: uuid.UUID, report_uuid: uuid.UUID, ai_status: str):
    async with session_scope() as session:
        row = (
            await session.execute(_report_lookup_stmt(tid, report_uuid))
        ).scalars().first()
        if row:
            row.ai_status = ai_status
            row.updated_at = datetime.now(timezone.utc)


async def _run_ai_analysis_async(self, report_id: str, narrative: str) -> dict:
    start = time.monotonic()
    tid = register_tenant(self.tenant_id)
    report_uuid = _as_uuid(report_id)
    if report_uuid is None:
        logger.error(f"AI analysis skipped: invalid report id {report_id}")
        return {}

    try:
        await _set_ai_status_async(self, tid, report_uuid, "PROCESSING")

        analysis = analyze_report(narrative)
        mandatory = classify_mandatory(narrative)
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)

        ai_analysis = {
            "occurrence_type": analysis.get("occurrence_type"),
            "human_factors": analysis.get("human_factors", []),
            "risk_level": analysis.get("risk_level") or "High",
            "phase_of_flight": analysis.get("phase_of_flight"),
            "confidence": analysis.get("confidence", 0.0),
            "summary": analysis.get("summary"),
            "recommendations": analysis.get("recommendations", []),
            "mandatory_check": mandatory,
            "ai_model": settings.AI_MODEL,
            "prompt_version": settings.AI_PROMPT_VERSION,
            "processing_time_ms": elapsed_ms,
            "processed_at": datetime.now(timezone.utc),
        }

        suggested_severity = analysis.get("suggested_severity")
        suggested_probability = analysis.get("suggested_probability")
        ai_suggested_assessment = None
        if suggested_severity is not None and suggested_probability is not None:
            thresholds = get_thresholds(self.tenant_id)
            ai_risk_index = compute_risk_index(suggested_severity, suggested_probability)
            ai_risk_level = get_risk_level(ai_risk_index, thresholds)
            ai_suggested_assessment = {
                "suggested_severity": suggested_severity,
                "suggested_probability": suggested_probability,
                "suggested_risk_index": ai_risk_index,
                "suggested_risk_level": ai_risk_level,
                "tolerability_tier": get_tolerability_tier(ai_risk_index, thresholds),
                "confidence": analysis.get("confidence", 0.0),
                "severity_explanation": analysis.get("severity_explanation"),
                "probability_explanation": analysis.get("probability_explanation"),
            }

        now = datetime.now(timezone.utc)
        async with session_scope() as session:
            row = (
                await session.execute(_report_lookup_stmt(tid, report_uuid))
            ).scalars().first()
            if not row:
                raise ValueError(f"Report {report_id} not found")
            row.ai_analysis = _json_safe(ai_analysis)
            row.ai_suggested_assessment = _json_safe(ai_suggested_assessment)
            row.ai_status = "COMPLETED"
            row.status = "COMPLETED"
            row.updated_at = now

        logger.info(
            f"AI analysis completed for report {report_id} "
            f"(model={settings.AI_MODEL}, {elapsed_ms}ms)"
        )
        record_ai_result(True)
        return ai_analysis

    except Exception as e:
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        logger.error(
            f"AI analysis failed for report {report_id} after "
            f"{elapsed_ms}ms: {e}"
        )
        try:
            await _set_ai_status_async(self, tid, report_uuid, "FAILED")
        except Exception as inner:
            logger.error(
                f"Failed to update ai_status for report {report_id}: {inner}"
            )
        record_ai_result(False)
        return {}


async def _confirm_risk_assessment_async(
    self, report_uuid: uuid.UUID, severity: int, probability: int, user: dict, notes: str
) -> dict:
    cross_tenant = user.get("role") in settings.CROSS_TENANT_ROLES
    tid = None if cross_tenant else register_tenant(self.tenant_id)

    async with session_scope() as session:
        row = (
            await session.execute(_report_lookup_stmt(tid, report_uuid))
        ).scalars().first()
        if not row:
            raise ValueError("Report not found")

        report_slug = tenant_slug(row.tenant_id)
        risk_index = compute_risk_index(severity, probability)
        thresholds = get_thresholds(report_slug)
        risk_level = get_risk_level(risk_index, thresholds)
        tolerability_tier = get_tolerability_tier(risk_index, thresholds)
        now = datetime.now(timezone.utc)

        risk_assessment = {
            "severity": severity,
            "probability": probability,
            "risk_index": risk_index,
            "risk_level": risk_level,
            "tolerability_tier": tolerability_tier,
            "assessed_by": user["uid"],
            "assessed_at": now,
            "notes": notes,
        }

        row.severity_level = severity
        row.probability_level = probability
        row.risk_index = risk_index
        row.risk_level = risk_level
        row.risk_assessment = _json_safe(risk_assessment)
        row.updated_at = now
        await session.flush()
        return _report_to_dict(row)


class ReportService:
    COLLECTION = settings.FIREBASE_COLLECTION_REPORTS

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def create_report(self, payload: dict, user: dict) -> dict:
        now = datetime.now(timezone.utc)
        tid = register_tenant(self.tenant_id)

        severity_level = payload.get("severity_level")
        probability_level = payload.get("probability_level")
        risk_index = None
        risk_level = None
        tolerability_tier = None
        if severity_level is not None and probability_level is not None:
            risk_index = compute_risk_index(severity_level, probability_level)
            thresholds = get_thresholds(self.tenant_id)
            risk_level = get_risk_level(risk_index, thresholds)
            tolerability_tier = get_tolerability_tier(risk_index, thresholds)

        values: Dict[str, Any] = {}
        for col in Report.__table__.columns:
            key = col.name
            if key in _REPORT_SKIP_COLUMNS:
                continue
            if key == "tenant_id":
                values[key] = tid
                continue
            if key == "is_demo":
                values[key] = demo_scope()
                continue
            if key == "risk_index":
                values[key] = risk_index
                continue
            if key == "risk_level":
                values[key] = risk_level
                continue
            if key == "created_by":
                values[key] = user["uid"]
                continue
            if key == "occurrence_date":
                values[key] = _dt(payload.get("occurrence_date")) or now
                continue
            if key == "reporting_date":
                values[key] = _dt(payload.get("reporting_date"))
                continue
            if key in ("created_at", "updated_at"):
                values[key] = now
                continue
            if key in _REPORT_JSONB_COLUMNS:
                raw = payload.get(key)
                values[key] = _json_safe(raw) if raw is not None else None
                continue
            if key == "status":
                values[key] = payload.get("status", "NEW")
                continue
            if key == "ai_status":
                values[key] = payload.get("ai_status", "PENDING")
                continue
            if key in ("is_anonymous", "etops", "manufacturer_advised", "fdr_data_retained"):
                values[key] = payload.get(key, False)
                continue
            values[key] = payload.get(key)

        row = run(_create_report_async(self, values))
        data = _report_to_dict(row)
        data["id"] = str(row.id)
        data["tolerability_tier"] = tolerability_tier
        logger.info(f"Report {row.id} created for tenant {self.tenant_id}")
        ReportRepository().invalidate_cache(prefix=f"{self.tenant_id}::")
        return data

    def get_reports(self, user: dict) -> List[dict]:
        try:
            cross_tenant = user.get("role") in settings.CROSS_TENANT_ROLES
            tid = None
            if not cross_tenant:
                tid = register_tenant(self.tenant_id)
            return run(_get_reports_async(self, cross_tenant, tid))
        except Exception as e:
            logger.error(f"Failed to retrieve reports: {e}")
            raise

    def get_report_by_id(self, report_id: str, user: dict) -> Optional[dict]:
        try:
            report_uuid = _as_uuid(report_id)
            if report_uuid is None:
                return None
            cross_tenant = user.get("role") in settings.CROSS_TENANT_ROLES
            tid = None
            if not cross_tenant:
                tid = register_tenant(self.tenant_id)
            return run(_get_report_async(self, tid, report_uuid))
        except Exception as e:
            logger.error(f"Failed to retrieve report {report_id}: {e}")
            raise

    def run_ai_analysis(self, report_id: str, narrative: str) -> dict:
        return run(_run_ai_analysis_async(self, report_id, narrative))

    def confirm_risk_assessment(
        self, report_id: str, severity: int, probability: int, user: dict, notes: str = None
    ) -> dict:
        try:
            report_uuid = _as_uuid(report_id)
            if report_uuid is None:
                raise ValueError("Report not found")
            return run(_confirm_risk_assessment_async(
                self, report_uuid, severity, probability, user, notes
            ))
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to confirm risk assessment for {report_id}: {e}")
            raise