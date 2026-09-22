# ============================================================================
# FILE: regulatory_timer_service.py
# PATH: backend/app/services/regulatory_timer_service.py
# PURPOSE: Module B §30 (SN15) — MOR category-tiered regulatory timer.
#          ICAO Annex 13 categories: A=24h, B=72h, C=7d, D=30d; the tenant
#          default applies when a MOR carries no category.
# ============================================================================

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select

from app.db import pg
from app.db.db_models import Report
from app.db.ids import register_tenant, tenant_slug
from app.db.runner import run
from app.db.session import session_scope
from app.services.audit_service import log_audit

# ICAO Annex 13 category → reporting window (Module B §30 / Decision 1).
MOR_CATEGORY_WINDOWS = {
    "A": timedelta(hours=24),
    "B": timedelta(hours=72),
    "C": timedelta(days=7),
    "D": timedelta(days=30),
}


def resolve_category(category: Optional[str], tenant_default: Optional[str] = None) -> Optional[str]:
    """Resolve the effective MOR category (explicit wins, else tenant default)."""
    for value in (category, tenant_default):
        cat = (value or "").strip().upper()
        if cat in MOR_CATEGORY_WINDOWS:
            return cat
    return None


def compute_deadline(
    submitted_at: Optional[datetime],
    category: Optional[str],
    tenant_default: Optional[str] = None,
) -> Optional[datetime]:
    """Return ``submitted_at + window(category)`` (None when no category)."""
    if submitted_at is None:
        return None
    cat = resolve_category(category, tenant_default)
    if cat is None:
        return None
    window = MOR_CATEGORY_WINDOWS[cat]
    if submitted_at.tzinfo is None:
        submitted_at = submitted_at.replace(tzinfo=timezone.utc)
    return submitted_at + window


def set_mor_deadline(
    report_id: str,
    tenant_id: str,
    *,
    category: Optional[str],
    submitted_at: Optional[datetime],
    tenant_default: Optional[str] = None,
) -> Optional[str]:
    """Persist the computed MOR deadline + category on the reports row."""
    deadline = compute_deadline(submitted_at, category, tenant_default)
    if deadline is None:
        return None
    try:
        register_tenant(tenant_id)
        pg.update(Report, "id", report_id, {
            "regulatory_category": resolve_category(category, tenant_default),
            "regulatory_deadline_at": deadline,
        })
        logger.info(
            f"MOR {report_id} regulatory deadline {deadline.isoformat()} "
            f"(category {resolve_category(category, tenant_default)})"
        )
        return deadline.isoformat()
    except Exception as e:
        logger.warning(f"Failed to set MOR deadline for {report_id}: {e}")
        return None


def check_overdue_mors(tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return MORs past their regulatory deadline and not yet submitted.

    When ``tenant_id`` is given the scan is scoped to that tenant; otherwise it
    spans all tenants. Breaches are also written to the audit log.
    """
    now = datetime.now(timezone.utc)
    tid = register_tenant(tenant_id) if tenant_id else None

    async def _fetch() -> List[Dict[str, Any]]:
        async with session_scope() as session:
            stmt = select(Report).where(
                Report.report_type == "mandatory",
                Report.regulatory_deadline_at.isnot(None),
                Report.regulatory_deadline_at < now,
                Report.regulatory_submitted_at.is_(None),
            )
            if tid:
                stmt = stmt.where(Report.tenant_id == tid)
            rows = (await session.scalars(stmt)).all()
            return [
                {
                    "id": str(r.id),
                    "report_id": getattr(r, "report_id", None),
                    "tenant_id": tenant_slug(r.tenant_id),
                    "regulatory_category": r.regulatory_category,
                    "regulatory_deadline_at": r.regulatory_deadline_at.isoformat()
                    if r.regulatory_deadline_at else None,
                }
                for r in rows
            ]

    try:
        overdue = run(_fetch())
    except Exception as e:
        logger.error(f"MOR deadline scan failed: {e}")
        return []

    for item in overdue:
        log_audit(
            action="MOR_DEADLINE_BREACHED",
            user="system",
            tenant_id=item["tenant_id"],
            target_type="report",
            target_id=item["id"],
            metadata={
                "regulatory_category": item["regulatory_category"],
                "regulatory_deadline_at": item["regulatory_deadline_at"],
            },
        )
    if overdue:
        logger.warning(f"MOR deadline scan: {len(overdue)} breach(es)")
    return overdue
