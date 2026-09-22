"""Shared Postgres-backed helpers for Module B Phase 2 service tests."""

import asyncio
import uuid

from sqlalchemy import text

from app.db.db_models import UserProfile
from app.db.ids import register_tenant
from app.db.session import session_scope


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
    tid = register_tenant(slug)

    async def _go():
        async with session_scope() as s:
            for table in list(extra_tables) + ["users", "tenants"]:
                col = "id" if table == "tenants" else "tenant_id"
                await s.execute(
                    text(f"DELETE FROM public.{table} WHERE {col} = :id"), {"id": tid})

    run(_go())
