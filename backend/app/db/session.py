# ============================================================================
# FILE: session.py
# PATH: backend/app/db/session.py
# PURPOSE: Async SQLAlchemy 2.x engine + session factory for PostgreSQL
#          (asyncpg). Url is read from `settings.DATABASE_URL` and normalised
#          to the `postgresql+asyncpg://` dialect that asyncpg requires.
#
#          The engine is created lazily on first use so importing this module
#          stays safe on Firestore-only deployments (DATABASE_URL unset).
#
#          CONNECTION BUDGET: the engine uses NullPool — no idle connections are
#          held between requests and every session_scope() creates + closes its
#          own connection. Peak connections therefore track only the number of
#          queries in flight, which stays far under Supabase free-tier limits
#          even against the TRANSACTION pooler (port 6543) used on Render.
# ============================================================================

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings

logger = logging.getLogger(__name__)

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _unique_prepared_stmt_name() -> str:
    """Return a globally-unique prepared-statement name.

    SQLAlchemy's asyncpg adapter always calls asyncpg ``Connection.prepare()``
    (named statements). Under PgBouncer transaction pooling, prepared statements
    persist on the shared backend past the transaction boundary, so a
    per-connection counter (asyncpg's default `__asyncpg_stmt_N__`) collides
    across clients routed to the same backend. A unique suffix makes every
    prepared statement name client-globally unique.
    """
    return f"__as_{uuid.uuid4().hex}__"


def _resolve_async_url(url: str) -> str:
    """Normalise a sync / driver-less Postgres URL to the asyncpg dialect.

    Accepts ``postgres://...`` and ``postgresql://...`` (optionally already
    ``postgresql+asyncpg://``) and rewrites the scheme so asyncpg, which only
    understands its own dialect, can connect. Supabase pooler URLs carry
    ``?sslmode=require`` which asyncpg rejects; it is translated to the
    ``ssl`` connection kwarg (require / verify-ca+ / disable).
    """
    url = url.strip()
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            url = url.replace(prefix, "postgresql+asyncpg://", 1)
            break
    else:
        raise ValueError(
            f"DATABASE_URL must be a postgres:// or postgresql:// URL, got: {url[:30]!r}..."
        )
    if "?" in url:
        base, query = url.split("?", 1)
        params = {}
        for part in query.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                params[k] = v
        sslmode = params.pop("sslmode", "").lower()
        if sslmode in ("require", "prefer"):
            params["ssl"] = "require"
        elif sslmode in ("verify-ca", "verify-full"):
            params["ssl"] = "verify-ca"
        elif sslmode == "disable":
            params["ssl"] = "false"
        # PgBouncer client-hint params (pgbouncer=true / transaction_mode=true)
        # are for libpq drivers, not asyncpg: asyncpg rejects unknown connect()
        # kwargs, so they are dropped. Transaction pooling is simply the pooler
        # host on port 6543.
        params.pop("pgbouncer", None)
        params.pop("transaction_mode", None)
        # SQLAlchemy's asyncpg adapter prepares NAMED statements via
        # asyncpg Connection.prepare(); under PgBouncer transaction pooling the
        # prepared statements outlive the transaction on the shared backend and
        # collide across clients (DuplicatePreparedStatementError). Disable the
        # prepared-statement cache via the dialect URL option (0 = disable).
        # This is a SQLAlchemy dialect knob, not an asyncpg connect() kwarg, so
        # it MUST travel as a query parameter.
        params["prepared_statement_cache_size"] = "0"
        url = base + ("?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else "")
    return url


def get_engine() -> AsyncEngine:
    """Return the shared async engine, constructing it on first access."""
    global _engine
    if _engine is None:
        if not settings.DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is not configured. Set it in backend/.env to "
                "enable the PostgreSQL engine (Firestore remains available)."
            )
        async_url = _resolve_async_url(settings.DATABASE_URL)
        logger.info("Creating SQLAlchemy async engine (NullPool cross-loop safe)")
        _engine = create_async_engine(
            async_url,
            echo=settings.DEBUG,
            # NullPool: one connection per in-flight call, closed on return.
            # Zero idle connections -> minimal Supabase free-tier footprint and
            # full compatibility with PgBouncer transaction pooling on 6543.
            poolclass=NullPool,
            pool_pre_ping=True,
            # PgBouncer transaction pooling reassigns transactions across
            # backends, so asyncpg's session-scoped prepared statements collide.
            # statement_cache_size=0 disables asyncpg's cache; the SQLAlchemy
            # adapter still prepares named statements, so give it globally-unique
            # names that cannot collide on a shared backend.
            connect_args={
                "statement_cache_size": 0,
                "prepared_statement_name_func": _unique_prepared_stmt_name,
            },
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the async session factory bound to the shared engine."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async session and closes it.

    Commits/rollbacks are intentionally left to the caller (route/service)
    so query paths stay transactionally explicit.
    """
    session = get_session_factory()()
    try:
        yield session
    finally:
        await session.close()


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager that commits on success, rolls back on error."""
    session = get_session_factory()()
    try:
        yield session
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()


async def check_db_health() -> bool:
    """Run `SELECT 1` against the engine to probe connectivity."""
    async with get_engine().connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        return result.scalar_one() == 1