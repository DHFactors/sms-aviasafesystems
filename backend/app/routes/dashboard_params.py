# ============================================================================
# FILE: dashboard_params.py
# PATH: backend/app/routes/dashboard_params.py
# PURPOSE: DASHBOARD_CONTRACT.md §7 — shared standard query parameters
#          (period / granularity / group_by) for all dashboard endpoints.
#          Centralised so every dashboard speaks the same period vocabulary.
# ============================================================================

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, Query, status

# period token -> trailing days (None = caller supplies explicit boundaries).
PERIOD_DAYS: Dict[str, Optional[int]] = {
    "30d": 30,
    "90d": 90,
    "1y": 365,
    "custom": None,
}

VALID_GRANULARITIES = {"day", "week", "month", "quarter", "year"}
VALID_PERIODS = set(PERIOD_DAYS)


def _parse_date(value: str, field: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field} must be an ISO-8601 date/datetime",
        )
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def dashboard_params(
    period: Optional[str] = Query(
        None, description="Standard window: 30d | 90d | 1y | custom"),
    granularity: Optional[str] = Query(
        None, description="Bucket size: day | week | month | quarter | year"),
    group_by: Optional[str] = Query(
        None, description="Endpoint-specific grouping key"),
    period_start: Optional[str] = Query(
        None, description="ISO start (required when period=custom)"),
    period_end: Optional[str] = Query(
        None, description="ISO end (required when period=custom)"),
    days: Optional[int] = Query(
        None, ge=0, description="Legacy window in days (back-compat)"),
) -> Dict[str, Any]:
    """Reusable dependency normalising the dashboard standard params.

    Returns a dict with the resolved window and echoes the input tokens so each
    endpoint can apply them without re-validating. Back-compatible: an endpoint
    that still receives `days` gets a matching `days` value.
    """
    if period is not None and period not in VALID_PERIODS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"period must be one of {sorted(VALID_PERIODS)}",
        )
    if granularity is not None and granularity not in VALID_GRANULARITIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"granularity must be one of {sorted(VALID_GRANULARITIES)}",
        )

    resolved_days = days
    start = end = None
    if period == "custom":
        if not period_start or not period_end:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="period=custom requires period_start and period_end",
            )
        start = _parse_date(period_start, "period_start")
        end = _parse_date(period_end, "period_end")
        if end < start:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="period_end must not precede period_start",
            )
        resolved_days = max(1, (end - start).days)
    elif period in PERIOD_DAYS and PERIOD_DAYS[period] is not None:
        resolved_days = PERIOD_DAYS[period]

    return {
        "period": period,
        "granularity": granularity,
        "group_by": group_by,
        "period_start": start,
        "period_end": end,
        "days": resolved_days,
    }
