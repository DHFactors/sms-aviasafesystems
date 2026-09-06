# ============================================================================
# FILE: pg.py
# PATH: backend/app/db/pg.py
# PURPOSE: Synchronous Postgres data-access port for the Firestore → SQLAlchemy
#          migration. Legacy service functions are sync, so reads/writes run on
#          the bridge loop via app/db/runner.py (NullPool engine is cross-loop
#          safe). Domain documents are stored as typed columns (a projection of
#          frequently queried fields) PLUS a JSONB `data` bag preserving the
#          original schemaless Firestore fields — so the one-time data migration
#          loses nothing and already-migrated consumers see the full doc shape.
# ============================================================================

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from sqlalchemy import delete as sa_delete
from sqlalchemy import select as sa_select
from sqlalchemy import update as sa_update

from app.db import db_models
from app.db.runner import run
from app.db.session import get_session_factory

# Default Firestore-facing id column per model (the string key Firestore used).
# UUID-keyed domain tables list the PK column itself so `row_to_doc` exposes
# the row id as the document ``id`` (as Firestore documents carried one).
_ID_COLUMNS: Dict[str, str] = {
    "tenants": "slug",
    "regulators": "slug",
    "users": "uid",
    "invites": "code",
    "caan_reports": "report_id",
    "state_risk_categories": "slug",
    "dead_letter_queue": "key",
    "audit_dispatches": "audit_id",
    "hazards": "id",
    "reports": "id",
    "cans": "id",
    "caps": "id",
    "surveys": "id",
    "survey_responses": "id",
    "verifications": "id",
    "closures": "id",
    "corrective_actions": "id",
    "safety_deficiencies": "id",
    "flight_diversions": "id",
    "psoe_assessments": "id",
    "psoe_findings": "id",
    "psoe_questions": "id",
    "state_risk_register": "id",
    "regulatory_reports": "id",
    "hazard_rca_entries": "id",
    "hazard_rca_factors": "id",
    "hazard_assessments": "id",
    "hazard_capas": "id",
    "bow_tie_analyses": "id",
    "bow_tie_threats": "id",
    "bow_tie_consequences": "id",
    "bow_tie_controls": "id",
    "risk_register": "id",
    "barrier_register": "id",
}
_BOOKKEEPING = {"id", "created_at", "updated_at", "data"}


def row_to_doc(row: Any) -> Dict[str, Any]:
    """Project an ORM row into a Firestore-shaped document.

    The stored JSONB `data` bag wins; typed columns overlay only keys the doc
    does not already carry. A non-UUID key column (slug/uid/code) is exposed as
    ``id`` for callers that used the Firestore document id.
    """
    if row is None:
        return {}
    table = row.__table__
    name = table.name
    doc = dict(getattr(row, "data", None) or {})
    for col in table.columns.keys():
        if col in _BOOKKEEPING:
            if col == "id" and name not in _ID_COLUMNS:
                continue
            if col in ("created_at", "updated_at"):
                if col in doc:
                    continue
                continue
            continue
        val = getattr(row, col, None)
        if val is not None and col not in doc:
            doc[col] = val
    id_col = _ID_COLUMNS.get(name)
    if id_col and getattr(row, id_col, None) is not None and "id" not in doc:
        doc["id"] = getattr(row, id_col)
    return doc


def _split_doc(model: type, doc: Dict[str, Any]) -> Dict[str, Any]:
    """Route Firestore-shaped fields into typed columns vs the JSONB bag.

    Models without a JSONB ``data`` column drop the unrecognized extras.
    """
    table = model.__table__
    typed: Dict[str, Any] = {}
    extras: Dict[str, Any] = {}
    for key, value in doc.items():
        if value is None:
            continue
        if key in table.columns:
            typed[key] = value
        elif "data" in table.columns:
            extras[key] = value
    if extras and "data" in table.columns:
        typed["data"] = extras
    return typed


def fetch_all(
    model: type,
    *,
    where: Optional[Sequence[Any]] = None,
    order_by: Optional[Any] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return all rows as documents, optionally filtered/ordered/limited."""

    async def _go(session) -> List[Any]:
        stmt = sa_select(model)
        if where:
            stmt = stmt.where(*where)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        if limit:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    session = get_session_factory()()
    try:
        rows = run(_go(session))
        return [row_to_doc(r) for r in rows]
    finally:
        run(session.close())


def fetch_by(model: type, column: str, value: Any) -> Optional[Dict[str, Any]]:
    """Return the first row matching `column == value` (as a document)."""
    return next(iter(fetch_all(model, where=[getattr(model, column) == value])), None)


def insert(model: type, doc: Dict[str, Any]) -> None:
    """Insert a Firestore-shaped document (typed columns + JSONB bag)."""

    async def _go(session) -> None:
        session.add(model(**_split_doc(model, doc)))
        await session.commit()

    run(_go(get_session_factory()()))


def upsert(model: type, key_column: str, key_value: Any, doc: Dict[str, Any]) -> None:
    """Insert-or-merge a document keyed by `key_column` (in one transaction)."""

    async def _go(session) -> None:
        existing = (
            await session.execute(
                sa_select(model).where(getattr(model, key_column) == key_value)
            )
        ).scalar_one_or_none()
        kwargs = _split_doc(model, dict(doc))
        if existing is None:
            kwargs[key_column] = key_value
            session.add(model(**kwargs))
        else:
            for k, v in kwargs.items():
                setattr(existing, k, v)
        await session.commit()

    run(_go(get_session_factory()()))


def update(
    model: type,
    column: str,
    value: Any,
    doc: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Merge fields into the row keyed by `column == value` (typed + JSONB).

    Returns the merged document (None when no row matched).
    """
    existing = fetch_by(model, column, value)
    if existing is None:
        return None
    merged = dict(existing)
    merged.update(doc)
    key_col = _ID_COLUMNS.get(model.__tablename__, "id")
    kwargs = _split_doc(model, merged)
    kwargs.pop(key_col, None)
    kwargs[key_col] = value

    async def _go(session) -> None:
        await session.execute(
            sa_update(model).where(getattr(model, column) == value).values(**kwargs)
        )
        await session.commit()

    run(_go(get_session_factory()()))
    return merged


def delete(model: type, column: str, value: Any) -> int:
    """Delete rows where `column == value`; returns affected row count."""

    async def _go(session) -> int:
        result = await session.execute(
            sa_delete(model).where(getattr(model, column) == value)
        )
        await session.commit()
        return result.rowcount or 0

    return run(_go(get_session_factory()()))