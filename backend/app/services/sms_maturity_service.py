# ============================================================================
# FILE: sms_maturity_service.py
# PATH: backend/app/services/sms_maturity_service.py
# PURPOSE: Module A-owned SMS maturity assessment cache (the `sms_maturity`
#          table). This service is the SOLE reader/writer of Module A's cache:
#          the dashboard layer consumes it (and the public
#          `/api/v1/sms-maturity/{tenant_id}/cache` endpoints) instead of
#          touching the table directly, preserving module ownership
#          (MODULE_A_CONTRACT.md §7.1).
# ============================================================================

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import select

from app.db import pg
from app.db.db_models import SmsMaturity
from app.db.ids import register_tenant
from app.db.runner import run
from app.db.session import session_scope


def read_sms_maturity(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Latest cached SMS maturity assessment for a tenant (by assessment_date).

    Returns the stored fields plus ``generated_at`` (the assessment write
    timestamp) so callers can apply a TTL. Queries the live assessment shape
    (D2) — the old ``days``/``data`` columns are gone.
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

        return run(_fetch())
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
