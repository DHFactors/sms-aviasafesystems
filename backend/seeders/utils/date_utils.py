"""Date utility functions for seeders.

Provides randomised, timezone-aware datetime generation for seeding
realistic safety-management data.  Every datetime returned by these
helpers is UTC-aware (``datetime.now(timezone.utc)``).
"""

import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple


def get_random_date(
    start_days_ago: int = 730,
    end_days_ago: int = 1,
    include_time: bool = True,
) -> datetime:
    """Return a random UTC datetime between *start_days_ago* and
    *end_days_ago* before now.

    Parameters
    ----------
    start_days_ago:
        Upper bound of the look-back window (farthest in the past).
    end_days_ago:
        Lower bound of the look-back window (closest to now).
    include_time:
        If ``True`` the returned datetime includes a random time component;
        otherwise the time is set to midnight.

    Returns
    -------
    datetime
        A timezone-aware datetime in UTC.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=start_days_ago)
    end = now - timedelta(days=end_days_ago)
    delta = (end - start).total_seconds()
    random_seconds = random.uniform(0, max(delta, 0))
    result = start + timedelta(seconds=random_seconds)
    if not include_time:
        result = result.replace(hour=0, minute=0, second=0, microsecond=0)
    return result


def get_date_range(
    days_ago: int = 730,
    count: int = 50,
    spread_days: int = 30,
) -> List[datetime]:
    """Return *count* sequential UTC datetimes spread over *spread_days*,
    starting *days_ago* from now.

    The first date is ``days_ago`` from now; subsequent dates are spaced
    ``spread_days / (count - 1)`` days apart (or zero spread when
    ``count == 1``).

    Parameters
    ----------
    days_ago:
        How far back the first date should be (in days).
    count:
        Number of dates to generate.
    spread_days:
        Total number of days over which the dates are spread.

    Returns
    -------
    list[datetime]
        Timezone-aware UTC datetimes in ascending order.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days_ago)
    if count <= 1:
        return [start]
    step = spread_days / (count - 1)
    return [start + timedelta(days=i * step) for i in range(count)]


def get_random_date_string(date: Optional[datetime] = None) -> str:
    """Return a ``YYYY-MM-DD`` string for the given (or random) date.

    Parameters
    ----------
    date:
        The datetime to format.  If ``None`` a random date is generated
        via :func:`get_random_date`.

    Returns
    -------
    str
        ISO-8601 date string.
    """
    if date is None:
        date = get_random_date()
    return date.strftime("%Y-%m-%d")


def get_random_date_parts(
    date: Optional[datetime] = None,
) -> dict:
    """Return a dict of date components suitable for ``str.format()``.

    Parameters
    ----------
    date:
        The datetime to decompose.  If ``None`` a random date is generated
        via :func:`get_random_date`.

    Returns
    -------
    dict
        Keys: ``year``, ``month``, ``day``, ``date_str`` (``YYYY-MM-DD``),
        ``iso_date`` (alias for ``date_str``), plus human-readable
        ``month_name`` and ``day_month_year`` (e.g. ``"15 August 2026"``).
    """
    if date is None:
        date = get_random_date()
    return {
        "year": str(date.year),
        "month": date.strftime("%B"),
        "day": str(date.day),
        "date_str": date.strftime("%Y-%m-%d"),
        "iso_date": date.strftime("%Y-%m-%d"),
        "month_name": date.strftime("%B"),
        "day_month_year": f"{date.day} {date.strftime('%B')} {date.year}",
    }


def generate_workflow_dates(
    relationship: str = "sequential",
) -> Tuple[datetime, datetime, datetime]:
    """Generate a realistic (report_date, can_date, cap_date) tuple.

    Parameters
    ----------
    relationship:
        ``"sequential"`` (default) produces ``can_date >= report_date``
        and ``cap_date >= can_date`` with a random gap of 1-30 days
        between each stage.

    Returns
    -------
    tuple[datetime, datetime, datetime]
        ``(report_date, can_date, cap_date)`` all UTC-aware.
    """
    report_date = get_random_date(start_days_ago=730, end_days_ago=60)
    can_gap = timedelta(days=random.randint(1, 30))
    can_date = report_date + can_gap
    cap_gap = timedelta(days=random.randint(1, 30))
    cap_date = can_date + cap_gap
    return report_date, can_date, cap_date


def distribute_dates_across_period(
    count: int,
    period_days: int = 730,
    min_gap_days: int = 1,
    max_gap_days: int = 30,
) -> List[datetime]:
    """Return *count* evenly-distributed UTC datetimes over *period_days*.

    Dates are placed at regular intervals (``period_days / count``) and
    each date is jittered randomly within ``[min_gap_days, max_gap_days]``
    of its nominal position to avoid perfectly uniform spacing.

    Parameters
    ----------
    count:
        Number of dates to produce.
    period_days:
        Total length of the period (in days) ending at now.
    min_gap_days:
        Minimum gap (in days) between consecutive dates.
    max_gap_days:
        Maximum gap (in days) between consecutive dates.

    Returns
    -------
    list[datetime]
        Timezone-aware UTC datetimes in ascending order.
    """
    if count <= 0:
        return []
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=period_days)
    if count == 1:
        return [start + timedelta(days=period_days // 2)]

    base_step = period_days / (count - 1)
    dates: List[datetime] = []
    for i in range(count):
        nominal = start + timedelta(days=i * base_step)
        jitter = timedelta(days=random.uniform(min_gap_days, max_gap_days))
        candidate = nominal + jitter
        # Guarantee dates never land in the future (nominal for the last index
        # reaches "now"); clamp any overshoot back to just before now.
        if candidate > now:
            candidate = now - timedelta(seconds=random.uniform(1, 60))
        dates.append(candidate)
    return sorted(dates)
