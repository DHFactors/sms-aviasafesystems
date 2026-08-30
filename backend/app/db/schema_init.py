# ============================================================================
# FILE: schema_init.py
# PATH: backend/app/db/schema_init.py
# PURPOSE: Idempotent bootstrap for the Postgres tables that are NOT part of
#          schema.sql - the v2 ICAO/HFACS RCA table set used by the async
#          HazardService. The 15 schema.sql tables are applied out-of-band
#          (via psql / the migration script); these are created here so a
#          Firestore-era deployment can run the v2 path without manual DDL.
# ============================================================================

from __future__ import annotations

import asyncio
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import get_engine

_V2_DDL = [
    """
    CREATE TABLE IF NOT EXISTS hazard_rca_entries (
        id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        resource_id           TEXT NOT NULL,
        tenant_id             UUID NOT NULL,
        title                 TEXT NOT NULL,
        description           TEXT NOT NULL,
        source_type           TEXT NOT NULL,
        source_reference_id   TEXT,
        functional_area       TEXT NOT NULL,
        status                TEXT NOT NULL DEFAULT 'under_assessment',
        risk_summary          JSONB,
        hfacs_summary         JSONB,
        identified_by         JSONB,
        assigned_owner        JSONB,
        target_completion_date TIMESTAMPTZ,
        created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
        closed_at             TIMESTAMPTZ
    );
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_hazard_rca_entries_tenant ON hazard_rca_entries (tenant_id, resource_id);",
    "CREATE INDEX IF NOT EXISTS ix_hazard_rca_entries_tenant ON hazard_rca_entries (tenant_id);",
    """
    CREATE TABLE IF NOT EXISTS hazard_rca_factors (
        id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id             UUID NOT NULL,
        entry_id              UUID NOT NULL REFERENCES hazard_rca_entries (id),
        resource_id           TEXT NOT NULL,
        tier                  INT,
        category              TEXT,
        subcategory           TEXT,
        nanocode              TEXT,
        definition            TEXT,
        contributing_narrative TEXT,
        order_sequence        INT,
        created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_hazard_rca_factors_tenant ON hazard_rca_factors (tenant_id);",
    """
    CREATE TABLE IF NOT EXISTS hazard_assessments (
        id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id             UUID NOT NULL,
        entry_id              UUID NOT NULL REFERENCES hazard_rca_entries (id),
        resource_id           TEXT NOT NULL,
        assessment_type       TEXT,
        severity              JSONB,
        probability           JSONB,
        risk_index            TEXT,
        tolerability          TEXT,
        assessed_by           TEXT,
        assessed_at           TIMESTAMPTZ,
        created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_hazard_assessments_tenant ON hazard_assessments (tenant_id);",
    """
    CREATE TABLE IF NOT EXISTS hazard_capas (
        id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id             UUID NOT NULL,
        entry_id              UUID NOT NULL REFERENCES hazard_rca_entries (id),
        resource_id           TEXT NOT NULL,
        status                TEXT,
        implemented_at        TIMESTAMPTZ,
        verified_by           TEXT,
        data                  JSONB,
        created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_hazard_capas_tenant ON hazard_capas (tenant_id);",
]

_v2_schema_ready: Optional[bool] = None


async def _ensure_v2_schema(engine: Optional[AsyncEngine] = None) -> None:
    global _v2_schema_ready
    if _v2_schema_ready:
        return
    engine = engine or get_engine()
    async with engine.begin() as conn:
        for ddl in _V2_DDL:
            await conn.execute(text(ddl))
    _v2_schema_ready = True


def ensure_v2_schema(engine: Optional[AsyncEngine] = None) -> None:
    """Synchronous entry point (dispatches onto the bridge loop)."""
    from app.db.runner import run

    run(_ensure_v2_schema(engine))


async def ensure_v2_schema_async(engine: Optional[AsyncEngine] = None) -> None:
    global _v2_schema_ready
    if _v2_schema_ready:
        return
    engine = engine or get_engine()
    async with engine.begin() as conn:
        for ddl in _V2_DDL:
            await conn.execute(text(ddl))
    _v2_schema_ready = True