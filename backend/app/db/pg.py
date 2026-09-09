# ============================================================================
# FILE: pg.py
# PATH: backend/app/db/pg.py
# PURPOSE: Synchronous Postgres data-access port for the Firestore → SQLAlchemy
#          migration. Legacy service functions are sync, so reads/writes run on
#          the bridge loop via app/db/runner.py. Domain documents are stored as
#          typed columns (a projection of frequently queried fields) PLUS a
#          JSONB `data` bag preserving the original schemaless Firestore fields
#          — so the one-time data migration loses nothing and already-migrated
#          consumers see the full doc shape.
#
#          CONNECTION REUSE: every query here runs on the single bridge loop and
#          is serialized there, so pg.py keeps ONE long-lived session
#          (session.get_bridge_session) instead of a NullPool per query. The
#          ~1.5-3 s Supabase pooler handshake is paid once per process rather
#          than once per query; each operation still runs in its own
#          begin()/commit so no cross-request transaction is held open. A
#          stale timed-out connection is detected and recreated once on the
#          next use.
# ============================================================================

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from loguru import logger
from sqlalchemy import delete as sa_delete
from sqlalchemy import select as sa_select
from sqlalchemy import update as sa_update

from app.db import db_models
from app.db.runner import run
from app.db.session import close_bridge_session, get_bridge_session

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

_SLOW_SQL_MS = float(os.getenv("AVIASAFE_SLOW_SQL_MS", "250"))


def _record_db(op: str, model: type, fn: Callable[[], Any]) -> Any:
    """Execute a bridge-loop query and record its latency.

    - Accumulates per-request totals (query count + cumulative DB ms) into the
      perf context (app/core/perf.py) so the middleware can report them on the
      "[PERF]" line of every request.
    - Logs a `[PERF] slow_sql` line when a single query crosses
      AVIASAFE_SLOW_SQL_MS (default 250ms) — the primitive that pinpoints
      individual slow queries from production logs.
    """
    from time import perf_counter

    t0 = perf_counter()
    try:
        return fn()
    finally:
        ms = (perf_counter() - t0) * 1000
        from app.core.perf import note_append, note_count, note_current

        note_current("db_ms", ms)
        note_count("db_calls", 1)
        if ms >= _SLOW_SQL_MS:
            table = getattr(model, "__tablename__", "?")
            logger.warning(
                f"[PERF] slow_sql op={op} table={table} dur={ms:.0f}ms"
            )
            note_append("slow_sql", f"{op}:{table}:{ms:.0f}ms")


def _run_on_bridge(op: Callable[[Any], Awaitable[Any]]) -> Any:
    """Run one DB operation inside its own transaction on the shared session.

    Every pg.py call funnels through here so the sync path reuses the one
    long-lived bridge-loop connection (session.get_bridge_session) instead of
    opening a fresh TCP/TLS connection per query — the per-query Supabase pooler
    handshake measured at ~1.5-3 s was the dominant constant across all
    dashboard endpoints.

    Each operation gets its own ``begin()``/commit (rolled back on error), so a
    reused connection never holds a transaction across requests. When the
    connection has been dropped by an idle timeout or the pooler, the session is
    recreated once and the operation retried a single time.

    When invoked from inside a coroutine already running on the bridge loop
    (an async service dispatched through ``runner.run``) the shared session is
    bypassed: it is bound to the bridge loop and cannot be awaited from the
    nested loop ``run()`` uses in that case, so the operation runs on its own
    fresh session + NullPool connection instead (session_scope does this
    automatically off the bridge loop).
    """
    from sqlalchemy.exc import OperationalError

    from app.db.runner import in_bridge_loop, run

    if in_bridge_loop():
        async def _go_nested() -> Any:
            from app.db.session import session_scope

            async with session_scope() as session:
                return await op(session)

        try:
            return run(_go_nested())
        except OperationalError:
            return run(_go_nested())

    session = get_bridge_session()

    def once() -> Any:
        async def _go() -> Any:
            async with session.begin():
                return await op(session)

        return run(_go())

    try:
        return once()
    except (OperationalError, ConnectionError, OSError) as exc:
        name = type(exc).__name__
        if (
            name
            in {
                "ConnectionDoesNotExistError",
                "InterfaceError",
                "ProtocolError",
                "AdminShutdownError",
                "ConnectionResetError",
                "PipeError",
                "BrokenPipeError",
            }
            or getattr(exc, "connection_invalidated", False)
        ):
            logger.warning(
                f"[PERF] SQL connection dropped ({name}); recreating once"
            )
            run(close_bridge_session())
            return once()
        raise


def _deterministic_tenant_id(kwargs: Dict[str, Any], fallback_slug: Any = None) -> None:
    """Force a tenants row onto the canonical uuid5('tenant:'+slug) id.

    Every tenant-scoped table stores ``tenant_id`` as this deterministic value
    (app/db/ids.py tenant_uuid), so a random gen_random_uuid() PK silently
    orphans all of a tenant's rows from its tenants record. Injected here so
    ANY tenant write routed through pg.insert/pg.upsert stays consistent.
    """
    if "id" in kwargs:
        return
    slug = kwargs.get("slug") or fallback_slug
    if not slug:
        return
    from app.db.ids import tenant_uuid

    kwargs["id"] = tenant_uuid(str(slug))


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


def _json_safe(value: Any) -> Any:
    """Recursively convert datetime/date to ISO strings for JSONB storage.

    JSONB can never round-trip a datetime as an object — it always decodes as
    an ISO string — so serializing to ISO on write is what reads already
    produce and keeps the ``data`` bag JSON-serializable (avoids the "Object of
    type datetime is not JSON serializable" error from Python's json.dumps).
    """
    from datetime import date, datetime

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _split_doc(model: type, doc: Dict[str, Any]) -> Dict[str, Any]:
    """Route Firestore-shaped fields into typed columns vs the JSONB bag.

    Models without a JSONB ``data`` column drop the unrecognized extras.
    Datetimes destined for the JSONB bag are serialized to ISO strings so the
    bag always round-trips cleanly.
    """
    from datetime import date, datetime
    from sqlalchemy import Date, DateTime

    table = model.__table__
    typed: Dict[str, Any] = {}
    extras: Dict[str, Any] = {}
    for key, value in doc.items():
        if value is None:
            continue
        if key in table.columns:
            coltype = table.columns[key].type
            # row_to_doc flattens the JSONB bag over typed columns, so a typed
            # Date/DateTime column can arrive here as an ISO string (or callers
            # pass `.isoformat()` directly). Coerce back so asyncpg binds cleanly.
            if isinstance(value, str) and isinstance(coltype, (Date, DateTime)):
                try:
                    if isinstance(coltype, DateTime):
                        value = datetime.fromisoformat(value)
                    else:
                        value = date.fromisoformat(value)
                except ValueError:
                    pass
            typed[key] = value
        elif "data" in table.columns:
            extras[key] = _json_safe(value)
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

    rows = _record_db("fetch_all", model, lambda: _run_on_bridge(_go))
    return [row_to_doc(r) for r in rows]


def fetch_by(model: type, column: str, value: Any) -> Optional[Dict[str, Any]]:
    """Return the first row matching `column == value` (as a document)."""
    return next(iter(fetch_all(model, where=[getattr(model, column) == value])), None)


def insert(model: type, doc: Dict[str, Any]) -> None:
    """Insert a Firestore-shaped document (typed columns + JSONB bag)."""

    async def _go(session) -> None:
        kwargs = _split_doc(model, dict(doc))
        _deterministic_tenant_id(kwargs)
        session.add(model(**kwargs))

    _record_db("insert", model, lambda: _run_on_bridge(_go))


def upsert(model: type, key_column: str, key_value: Any, doc: Dict[str, Any]) -> None:
    """Insert-or-merge a document keyed by `key_column` (in one transaction)."""

    async def _go(session) -> None:
        existing = (
            await session.execute(
                sa_select(model).where(getattr(model, key_column) == key_value)
            )
        ).scalar_one_or_none()
        kwargs = _split_doc(model, dict(doc))
        _deterministic_tenant_id(kwargs, key_value if key_column == "slug" else None)
        if existing is None:
            kwargs[key_column] = key_value
            session.add(model(**kwargs))
        else:
            for k, v in kwargs.items():
                setattr(existing, k, v)

    _record_db("upsert", model, lambda: _run_on_bridge(_go))


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
    # fetch_by exposes the key column as a synthetic `id` (slug-as-id for
    # regulator/tenant rows); drop it keying by a non-id column so it is not
    # written into the real UUID `id` column.
    if key_col != "id":
        merged.pop("id", None)
    kwargs = _split_doc(model, merged)
    kwargs.pop(key_col, None)
    kwargs[key_col] = value

    async def _go(session) -> None:
        await session.execute(
            sa_update(model).where(getattr(model, column) == value).values(**kwargs)
        )

    _record_db("update", model, lambda: _run_on_bridge(_go))
    return merged


def delete(model: type, column: str, value: Any) -> int:
    """Delete rows where `column == value`; returns affected row count."""

    async def _go(session) -> int:
        result = await session.execute(
            sa_delete(model).where(getattr(model, column) == value)
        )
        return result.rowcount or 0

    return _record_db("delete", model, lambda: _run_on_bridge(_go))