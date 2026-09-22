# ============================================================================
# FILE: sms_maturity_service.py
# PATH: backend/app/services/sms_maturity_service.py
# PURPOSE: Module A-owned SMS maturity assessment cache (the `sms_maturity`
#          table) and its LLM analysis pipeline.
#
#          This service is the SOLE reader/writer of Module A's cache: the
#          dashboard layer consumes it (and the public
#          `/api/v1/sms-maturity/{tenant_id}/cache` endpoints) instead of
#          touching the table directly, preserving module ownership
#          (MODULE_A_CONTRACT.md §7.1).
#
#          P2-1: TTL-based cache freshness + invalidation.
#          P2-2: the LLM analysis runs in a background APScheduler job, never
#          on the request path — the dashboard reads the cache only.
# ============================================================================

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import select

from app.core.config import settings
from app.db import pg
from app.db.db_models import SmsMaturity
from app.db.ids import register_tenant
from app.db.runner import run
from app.db.session import session_scope
from app.services.gemini import recommend_sms_maturity_actions

# P2-1: cache freshness window (MODULE_A_CONTRACT.md §7; 6 hours).
SMS_MATURITY_CACHE_TTL = settings.SMS_MATURITY_CACHE_TTL


def _as_datetime(value: Any) -> Optional[datetime]:
    """Coerce a stored timestamp (datetime or ISO string) to tz-aware UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def read_sms_maturity(
    tenant_id: str, *, ttl_seconds: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Latest cached SMS maturity assessment for a tenant (by assessment_date).

    Returns the stored fields plus cache-freshness metadata (P2-1):
      * ``generated_at`` — the assessment write timestamp
      * ``age_seconds`` — seconds since it was written
      * ``is_fresh`` — True when ``age_seconds < ttl_seconds`` (default 6 h)

    A ``None`` return means no assessment exists yet ("analysis pending").
    """
    try:
        tid = register_tenant(tenant_id)

        async def _fetch() -> Optional[Dict[str, Any]]:
            async with session_scope() as session:
                row = (await session.execute(
                    select(SmsMaturity)
                    .where(SmsMaturity.tenant_id == tid)
                    .order_by(SmsMaturity.assessment_date.desc().nullslast())
                    .limit(1)
                )).scalar_one_or_none()
                if row is None:
                    return None
                return {
                    "generated_at": row.updated_at or row.assessment_date or row.created_at,
                    "overall_sms_maturity": row.overall_score,
                    "pillars": row.pillar_scores,
                    "level": row.level,
                    "element_scores": row.element_scores,
                    "gap_analysis": row.gap_analysis,
                    "recommendations": row.recommendations or [],
                }

        cached = run(_fetch())
        if cached is None:
            return None

        generated_at = _as_datetime(cached.get("generated_at"))
        ttl = SMS_MATURITY_CACHE_TTL if ttl_seconds is None else ttl_seconds
        if generated_at is None:
            cached["age_seconds"] = None
            cached["is_fresh"] = False
        else:
            age = (datetime.now(timezone.utc) - generated_at).total_seconds()
            cached["age_seconds"] = age
            cached["is_fresh"] = age < ttl
        return cached
    except Exception as e:
        logger.warning(f"Failed to read sms_maturity cache for {tenant_id}: {e}")
        return None


def write_sms_maturity(tenant_id: str, payload: Dict[str, Any]) -> None:
    """Persist one SMS maturity assessment row (D2 live shape).

    A new row is inserted per assessment (no ``days``/unique key remains — the
    read takes the latest by ``assessment_date``). Both the legacy caller
    payload (``pillars``/``question_averages``/``low_pillars``/
    ``overall_sms_maturity``/``recommendations``) and the live column names
    (``element_scores``/``gap_analysis``) are accepted and translated onto the
    new columns.
    """
    try:
        tid = register_tenant(tenant_id)
        overall = payload.get("overall_sms_maturity")
        level = None
        if isinstance(overall, (int, float)) and 1 <= overall <= 5:
            level = int(round(overall))
        now = datetime.now(timezone.utc)
        doc = {
            "tenant_id": tid,
            "assessment_date": now,
            "overall_score": overall,
            "level": level,
            "pillar_scores": payload.get("pillars"),
            "element_scores": payload.get("element_scores") or payload.get("question_averages"),
            "gap_analysis": payload.get("gap_analysis") or payload.get("low_pillars"),
            "recommendations": payload.get("recommendations"),
            "updated_at": now,
        }
        pg.insert(SmsMaturity, doc)
    except Exception as e:
        logger.warning(f"Failed to write sms_maturity cache for {tenant_id}: {e}")


def invalidate_sms_maturity(tenant_id: str) -> int:
    """Drop the cached assessment(s) for a tenant (P2-1 invalidation).

    Called on a new survey submission and on manual refresh; the background
    analysis job repopulates the cache. Returns the number of rows deleted.
    """
    try:
        tid = register_tenant(tenant_id)
        deleted = pg.delete(SmsMaturity, "tenant_id", tid) or 0
        logger.info(f"Invalidated sms_maturity cache for {tenant_id} ({deleted} row(s))")
        return deleted
    except Exception as e:
        logger.warning(f"Failed to invalidate sms_maturity cache for {tenant_id}: {e}")
        return 0


def analyze_sms_maturity(
    tenant_id: str, *, days: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Run the LLM maturity analysis for a tenant and cache the result.

    This is the background job body (P2-2) and is never invoked on the request
    path. It reuses the dashboard's survey-aggregation math, calls the shared
    Gemini/Groq recommendation service, and writes ``gap_analysis`` /
    ``recommendations`` / ``level`` to ``sms_maturity`` via
    :func:`write_sms_maturity`.
    """
    # Lazy import avoids a module-load cycle (dashboard_service imports this
    # module) while reusing the single source of the survey-score math.
    from app.services.dashboard_service import DashboardService

    days = days or settings.SMS_MATURITY_ANALYSIS_WINDOW_DAYS
    svc = DashboardService({"role": "CAAN_SMD", "tenant_id": tenant_id})
    docs = [
        d for d in svc._survey_docs(days)
        if (d.to_dict().get("tenant_id") or None) == tenant_id
    ]
    data = svc._aggregate_surveys(docs)
    ops = data.get("operators", [])
    op = ops[0] if ops else None
    if not op:
        logger.info(f"SMS maturity analysis skipped for {tenant_id}: no surveys")
        return None

    model = svc._sms_maturity_model(op)
    recs = []
    if model["low_pillars"]:
        recs = recommend_sms_maturity_actions(tenant_id, {
            "pillars": op["pillars"],
            "pcts": model["pcts"],
            "tiers": model["tiers"],
            "question_averages": op.get("question_averages", {}),
            "response_count": op["response_count"],
        })

    write_sms_maturity(tenant_id, {
        "pillars": op["pillars"],
        "pcts": model["pcts"],
        "tiers": model["tiers"],
        "overall_sms_maturity": op["overall_sms_maturity"],
        "question_averages": op.get("question_averages", {}),
        "low_pillars": model["low_pillars"],
        "recommendations": recs,
    })
    logger.info(
        f"SMS maturity analysis cached for {tenant_id}: "
        f"{len(recs)} recommendation(s)"
    )
    return {
        "tenant_id": tenant_id,
        "overall_sms_maturity": op["overall_sms_maturity"],
        "recommendations": recs,
    }


def _run_sms_maturity_analysis(tenant_id: str, attempt: int = 1) -> None:
    """APScheduler entry point: run the analysis with bounded retries (P2-2)."""
    from app.core.metrics import record_ai_result

    logger.info(f"SMS maturity analysis started for {tenant_id} (attempt {attempt})")
    try:
        analyze_sms_maturity(tenant_id)
        record_ai_result(True)
        logger.info(f"SMS maturity analysis finished for {tenant_id}")
    except Exception as e:
        record_ai_result(False)
        logger.error(f"SMS maturity analysis failed for {tenant_id}: {e}")
        if attempt < settings.SMS_MATURITY_ANALYSIS_MAX_RETRIES:
            enqueue_sms_maturity_analysis(tenant_id, attempt=attempt + 1)


def enqueue_sms_maturity_analysis(tenant_id: str, *, attempt: int = 1) -> bool:
    """Queue a one-off background analysis job on the shared APScheduler.

    Never blocks the caller (survey submission / dashboard read). Returns True
    when the job was queued. Uses the same scheduler singleton as the periodic
    jobs in ``app/core/lifecycle.py``.
    """
    try:
        from apscheduler.triggers.date import DateTrigger

        from app.core.lifecycle import get_scheduler

        scheduler = get_scheduler()
        run_date = datetime.now(timezone.utc) + timedelta(seconds=2 * max(1, attempt))
        scheduler.add_job(
            _run_sms_maturity_analysis,
            trigger=DateTrigger(run_date=run_date),
            args=[tenant_id, attempt],
            id=f"sms_maturity_analysis:{tenant_id}",
            name=f"SMS maturity analysis ({tenant_id})",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(f"SMS maturity analysis enqueued for {tenant_id} (attempt {attempt})")
        return True
    except Exception as e:
        logger.warning(f"Failed to enqueue SMS maturity analysis for {tenant_id}: {e}")
        return False
