"""Shared Postgres-backed helpers for Module B Phase 2 service tests."""

import asyncio
import logging
import uuid

from sqlalchemy import text

from app.db.db_models import UserProfile
from app.db.ids import register_tenant
from app.db.session import session_scope

log = logging.getLogger(__name__)


def run(coro):
    return asyncio.run(coro)


def unique_slug(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def create_tenant(slug: str) -> str:
    tid = register_tenant(slug)

    async def _go():
        async with session_scope() as s:
            await s.execute(text(
                "INSERT INTO public.tenants "
                "(id, slug, name, is_demo, is_beta_sandbox, created_at, updated_at) "
                "VALUES (:id, :slug, :name, false, false, now(), now()) "
                "ON CONFLICT DO NOTHING"
            ), {"id": tid, "slug": slug, "name": slug})

    run(_go())
    return tid


def create_user(tid: str, uid: str, role: str = "SAFETY_OFFICER") -> str:
    """Insert a users row; returns the users.id UUID as a string."""
    user_id = uuid.uuid4()

    async def _go():
        async with session_scope() as s:
            s.add(UserProfile(
                id=user_id, uid=uid, email=f"{uid}@test.local", role=role,
                tenant_id=uuid.UUID(tid), is_developer=False, phone_verified=False,
            ))

    run(_go())
    return str(user_id)


def cleanup(slug: str, extra_tables=()) -> None:
    """Best-effort cascade delete for a throwaway test tenant.

    Teardown hygiene: this runs in `finally` blocks across the suite, but a
    mid-cleanup failure (live-Supabase connection drop under parallel xdist,
    worker timeout) used to abort the remaining DELETEs and strand the tenant
    row — the source of the ae-*/mat-*/imp-*/enrich-* pollution. Two defenses:
    (1) each DELETE is committed independently, so a later failure cannot roll
    back earlier deletes (session_scope commits once at exit by default);
    (2) every statement is attempted and this function NEVER raises, so one
    dropped statement cannot strand the rest.
    """
    tid = register_tenant(slug)

    async def _go():
        async with session_scope() as s:
            for table in list(extra_tables) + ["users", "tenants"]:
                col = "id" if table == "tenants" else "tenant_id"
                try:
                    await s.execute(
                        text(f"DELETE FROM public.{table} WHERE {col} = :id"), {"id": tid})
                    await s.commit()
                except Exception as e:
                    # Roll back just the failed statement, log, and continue:
                    # a partial cleanup is strictly better than aborting and
                    # stranding the tenant row.
                    try:
                        await s.rollback()
                    except Exception:
                        pass
                    log.warning("test cleanup: DELETE FROM %s failed for %s: %s",
                                table, slug, e)

    try:
        run(_go())
    except Exception as e:
        log.warning("test cleanup: session failed for %s: %s", slug, e)
