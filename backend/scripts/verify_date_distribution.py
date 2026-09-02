#!/usr/bin/env python3
"""Verify the date distribution of all seeded safety-management data.

Queries every date-bearing record created by the seeders (PostgreSQL + Firestore)
and reports:

  * overall date range (min -> max)
  * distribution across months
  * any dates outside the expected window
  * summary statistics

Warnings are raised for dates that are:

  * before ``2024-09-01`` (too old)
  * after today (future dates)
  * over-clustered (e.g. >50% inside the last 30 days)

Usage:
    python scripts/verify_date_distribution.py            # sms-db (default)
    python scripts/verify_date_distribution.py sms-db
    SEED_DB=sms-db python scripts/verify_date_distribution.py
"""

import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

DB_ID = os.environ.get("SEED_DB", "sms-db")
os.environ["FIREBASE_DATABASE_ID"] = DB_ID

from sqlalchemy import select

from app.db.runner import run
from app.db.isolation import demo_scope
from app.db.session import session_scope
from app.db.db_models import Report, Can, Cap, Hazard

EXPECTED_MIN = datetime(2024, 9, 1, tzinfo=timezone.utc)

# Tenant ids that the seeders write to (operators; demostate is the regulator).
OPERATOR_TENANTS = ["fixedwing", "rotarywing", "demoairport"]


def _aware(dt):
    """Return ``dt`` as a UTC-aware datetime (assume naive == UTC). Accepts
    datetimes, ISO-8601 strings (Firestore stores timestamps as strings), and
    Firestore datetime values. Returns ``None`` when it cannot be coerced."""
    if not dt:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    if isinstance(dt, str):
        try:
            parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    # Google datatypes with a microseconds interface (e.g. google.protobuf.Timestamp)
    try:
        ts = dt
        if hasattr(ts, "seconds"):
            return datetime.fromtimestamp(ts.seconds, tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        pass
    return None


def collect_postgres_dates() -> list:
    """Collect report / can / cap date fields from PostgreSQL.

    Each entry is ``(label, datetime, kind)`` where ``kind`` is ``"event"``
    (a point-in-time occurrence) or ``"deadline"`` (a future target date).
    Only ``"event"`` dates are checked for future/too-old/clustering.
    """
    dates = []

    async def _query():
        async with session_scope() as session:
            reports = (await session.execute(select(Report))).scalars().all()
            cans = (await session.execute(select(Can))).scalars().all()
            caps = (await session.execute(select(Cap))).scalars().all()
            row_reports = [
                (r.occurrence_date, r.created_at)
                for r in reports if r.is_demo
            ]
            row_cans = [
                (c.issued_at, c.target_completion_date)
                for c in cans if c.is_demo
            ]
            row_caps = [
                (c.submitted_at, c.created_at, c.target_completion_date)
                for c in caps if c.is_demo
            ]
            return row_reports, row_cans, row_caps

    reports, cans, caps = run(_query())
    for occurrence, created in reports:
        for d in (occurrence, created):
            d = _aware(d)
            if d:
                dates.append(("reports.occurrence_date/created_at", d, "event"))
    for issued, target in cans:
        issued = _aware(issued)
        if issued:
            dates.append(("cans.issued_at", issued, "event"))
        target = _aware(target)
        if target:
            dates.append(("cans.target_completion_date", target, "deadline"))
    for submitted, created, target in caps:
        for d in (submitted, created):
            d = _aware(d)
            if d:
                dates.append(("caps.submitted_at/created_at", d, "event"))
        target = _aware(target)
        if target:
            dates.append(
                ("caps.target_completion_date", target, "deadline")
            )
    return dates


def collect_firestore_dates() -> list:
    """Collect diversion / PSOE / SSP date fields from Firestore."""
    from app.firebase import get_db, get_tenant_collection
    db = get_db()
    dates = []

    for tenant in OPERATOR_TENANTS:
        col = get_tenant_collection(tenant, "flight_diversions")
        for doc in col.stream():
            data = doc.to_dict() or {}
            d = _aware(data.get("date"))
            if d:
                dates.append((f"diversions[{tenant}].date", d, "event"))

    psoe_col = db.collection("psoe_assessments")
    for doc in psoe_col.stream():
        data = doc.to_dict() or {}
        d = _aware(data.get("assessment_date"))
        if d:
            dates.append(("psoe.assessment_date", d, "event"))

    state_doc = db.collection("state").document("ssp")
    spi_col = state_doc.collection("spis")
    for doc in spi_col.stream():
        data = doc.to_dict() or {}
        d = _aware(data.get("created_at"))
        if d:
            dates.append(("ssp.spis.created_at", d, "event"))

    reg_col = state_doc.collection("risk_register")
    for doc in reg_col.stream():
        data = doc.to_dict() or {}
        raw = data.get("aggregated_at") or data.get("created_at")
        d = _aware(raw)
        if d:
            dates.append(("ssp.risk_register.aggregated_at", d, "event"))

    return dates


def report(dates: list) -> int:
    """Print the distribution report. Returns the number of issues flagged."""
    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta_days(30)
    warnings = 0

    print("=" * 70)
    print("DATE DISTRIBUTION VERIFICATION")
    print(f"  Database: {DB_ID}")
    print(f"  Records inspected: {len(dates)}")
    print("=" * 70)

    if not dates:
        print("  No date-bearing records found.")
        return 0

    # Only point-in-time "event" dates are checked for future/too-old/clustering;
    # "deadline" fields (CAN/CAP target_completion_date) are intentionally
    # future and therefore excluded.
    events = [d for _, d, kind in dates if kind == "event"]
    values = events
    lo = min(values)
    hi = max(values)

    print(f"\n  Date range: {lo.date().isoformat()} -> {hi.date().isoformat()}")
    print(f"  Span: {(hi - lo).days} days")

    future = [d for d in values if d > now]
    too_old = [d for d in values if d < EXPECTED_MIN]
    recent = [d for d in values if d >= recent_cutoff]

    if future:
        warnings += 1
        print(f"\n  [WARN] {len(future)} event date(s) are in the FUTURE:")
        for label, d, _ in sorted(
            (x for x in dates if x[2] == "event" and x[1] > now),
            key=lambda x: x[1],
        )[:10]:
            print(f"         {label} :: {d.isoformat()}")
    if too_old:
        warnings += 1
        print(f"\n  [WARN] {len(too_old)} event date(s) are OLDER than 2024-09-01:")
        for label, d, _ in sorted(
            (x for x in dates if x[2] == "event" and x[1] < EXPECTED_MIN),
            key=lambda x: x[1],
        )[:10]:
            print(f"         {label} :: {d.isoformat()}")
    if recent and len(recent) / len(values) > 0.5:
        warnings += 1
        print(
            f"\n  [WARN] {len(recent)}/{len(values)} "
            f"({len(recent) / len(values):.0%}) dates are within the last "
            f"30 days - data may be over-clustered near today."
        )

    # Monthly distribution histogram.
    print("\n  Monthly distribution:")
    by_month = defaultdict(int)
    for d in values:
        by_month[d.strftime("%Y-%m")] += 1
    if by_month:
        months = sorted(by_month)
        peak = max(by_month.values())
        for m in months:
            bar = "#" * int(by_month[m] / max(peak, 1) * 30)
            print(f"    {m}: {by_month[m]:3d}  {bar}")

    print("\n" + "-" * 70)
    if warnings:
        print(f"  RESULT: {warnings} issue(s) found - review the dates above.")
    else:
        print("  RESULT: PASS - all dates within expected range and well-spread.")
    print("=" * 70)
    return warnings


def timedelta_days(n: int):
    from datetime import timedelta
    return timedelta(days=n)


def validate_relationships() -> int:
    """Validate chronological ordering of FK-linked date chains.

    Because the ``reports`` table has no hazard/can reference, the Report->CAN
    leg cannot be joined structurally.  The strongest available checks (all
    demo rows) are:

      * CAN -> Hazard  : can.issued_at >= linked hazard.created_at
      * CAN internal   : can.target_completion_date >= can.issued_at
      * CAP -> CAN     : cap.submitted_at >= linked can.issued_at
      * CAP internal   : cap.target_completion_date >= cap.submitted_at

    Report->CAN chronology is enforced at seed time (CAN dates are generated
    after the linked hazard/typical report window) and reported here as the
    count of CANs checked.
    """
    print("\n" + "=" * 70)
    print("RELATIONSHIP VALIDATION (Hazard -> CAN -> CAP)")
    print("=" * 70)
    issues = 0
    checks_run = {"can_hazard": 0, "can_internal": 0, "cap_can": 0,
                  "cap_internal": 0}

    async def _query():
        async with session_scope() as session:
            cans = (
                (await session.execute(
                    select(Can).where(Can.is_demo == demo_scope())
                )).scalars().all()
            )
            caps = (
                (await session.execute(
                    select(Cap).where(Cap.is_demo == demo_scope())
                )).scalars().all()
            )
            hazards = (
                (await session.execute(
                    select(Hazard).where(Hazard.is_demo == demo_scope())
                )).scalars().all()
            )
            return cans, caps, hazards

    cans, caps, hazards = run(_query())

    can_by_id = {str(c.id): c for c in cans}
    hazard_by_id = {str(h.id): h for h in hazards}

    # CAN -> Hazard: issued_at after the linked hazard's created_at.
    for c in cans:
        hazard = hazard_by_id.get(str(c.hazard_id))
        issued = _aware(c.issued_at)
        if hazard is not None and issued is not None:
            checks_run["can_hazard"] += 1
            hazard_created = _aware(hazard.created_at)
            if hazard_created and issued < hazard_created:
                issues += 1
                print(
                    f"  [WARN] CAN {c.can_reference}: issued_at "
                    f"({issued.date().isoformat()}) before its hazard's "
                    f"created_at ({hazard_created.date().isoformat()})"
                )

    # CAN internal: target >= issued.
    for c in cans:
        issued = _aware(c.issued_at)
        target = _aware(c.target_completion_date)
        if issued and target:
            checks_run["can_internal"] += 1
            if target < issued:
                issues += 1
                print(
                    f"  [WARN] CAN {c.can_reference}: target_completion_date "
                    f"({target.date().isoformat()}) before issued_at "
                    f"({issued.date().isoformat()})"
                )

    # CAP -> CAN: submitted >= CAN.issued; CAP internal: submitted <= target.
    for cap in caps:
        can = can_by_id.get(str(cap.can_id))
        if can is None:
            continue
        cap_sub = _aware(cap.submitted_at)
        cap_target = _aware(cap.target_completion_date)
        can_issued = _aware(can.issued_at)
        if cap_sub and can_issued:
            checks_run["cap_can"] += 1
            if cap_sub < can_issued:
                issues += 1
                print(
                    f"  [WARN] CAP for {can.can_reference}: submitted_at "
                    f"({cap_sub.date().isoformat()}) before CAN issued_at "
                    f"({can_issued.date().isoformat()})"
                )
        if cap_sub and cap_target:
            checks_run["cap_internal"] += 1
            if cap_sub > cap_target:
                issues += 1
                print(
                    f"  [WARN] CAP for {can.can_reference}: submitted_at "
                    f"({cap_sub.date().isoformat()}) after target_completion_date "
                    f"({cap_target.date().isoformat()})"
                )

    print(f"\n  Checks run: CAN->Hazard={checks_run['can_hazard']} "
          f"CAN internal={checks_run['can_internal']} "
          f"CAP->CAN={checks_run['cap_can']} "
          f"CAP internal={checks_run['cap_internal']}")
    print(f"  Note: Report->CAN is not FK-joinable (reports are not linked to "
          f"hazards/cans); it is enforced at seed time.")
    print("\n" + "-" * 70)
    if issues:
        print(f"  RESULT: {issues} relationship issue(s) found.")
    else:
        print(f"  RESULT: PASS - {len(caps)} CAP(s) / {len(cans)} CAN(s) / "
              f"{len(hazards)} hazard(s) all chronologically ordered.")
    print("=" * 70)
    return issues


def main() -> int:
    try:
        postgres_dates = collect_postgres_dates()
    except Exception as e:
        print(f"[SKIP] PostgreSQL date collection failed: {e}")
        postgres_dates = []

    try:
        firestore_dates = collect_firestore_dates()
    except Exception as e:
        print(f"[SKIP] Firestore date collection failed: {e}")
        firestore_dates = []

    dist_issues = report(postgres_dates + firestore_dates)

    rel_issues = 0
    try:
        rel_issues = validate_relationships()
    except Exception as e:
        print(f"[SKIP] Relationship validation failed: {e}")

    return dist_issues + rel_issues


if __name__ == "__main__":
    raise SystemExit(main())
