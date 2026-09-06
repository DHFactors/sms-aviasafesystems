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


# ----------------------------------------------------------------------------
# DOMAIN TABLES (Firestore → Postgres migration, Batch 0)
#
# Idempotent DDL mirroring the new models in app/db/db_models.py. Each table
# carries a JSONB `data` column for the original schemaless Firestore document
# so the one-time data migration preserves every field.
# ----------------------------------------------------------------------------

_DOMAIN_DDL = [
    """
    CREATE TABLE IF NOT EXISTS tenants (
        id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        slug              TEXT NOT NULL UNIQUE,
        name              TEXT,
        status            TEXT,
        is_demo           BOOLEAN NOT NULL DEFAULT FALSE,
        is_beta_sandbox   BOOLEAN NOT NULL DEFAULT FALSE,
        active            BOOLEAN DEFAULT TRUE,
        auto_expire_days  INTEGER,
        safety_manager    JSONB,
        data              JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_tenants_status ON tenants (status);",
    "CREATE INDEX IF NOT EXISTS ix_tenants_demo ON tenants (is_demo);",
    """
    CREATE TABLE IF NOT EXISTS regulators (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        slug                TEXT NOT NULL UNIQUE,
        name                TEXT,
        regulator_type      TEXT,
        display_name        TEXT,
        operator_tenant_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
        data                JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        uid          TEXT PRIMARY KEY,
        email        TEXT,
        display_name TEXT,
        role         TEXT,
        tenant_id    TEXT,
        department   TEXT,
        claims       JSONB,
        data         JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);",
    "CREATE INDEX IF NOT EXISTS ix_users_tenant ON users (tenant_id);",
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        action      TEXT NOT NULL,
        actor       TEXT,
        target      TEXT,
        target_type TEXT,
        target_id   TEXT,
        detail      TEXT,
        result      TEXT,
        tenant_id   TEXT,
        ip          TEXT,
        request_id  TEXT,
        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant ON audit_logs (tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_created ON audit_logs (created_at);",
    """
    CREATE TABLE IF NOT EXISTS sms_dispatches (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id   TEXT,
        status      TEXT,
        data        JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_sms_dispatches_tenant ON sms_dispatches (tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_sms_dispatches_created ON sms_dispatches (created_at);",
    """
    CREATE TABLE IF NOT EXISTS audit_dispatches (
        audit_id     TEXT PRIMARY KEY,
        tenant_id    TEXT,
        regulator_id TEXT,
        status       TEXT,
        data         JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at   TIMESTAMPTZ
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_audit_dispatches_tenant ON audit_dispatches (tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_audit_dispatches_regulator ON audit_dispatches (regulator_id);",
    "CREATE INDEX IF NOT EXISTS ix_audit_dispatches_created ON audit_dispatches (created_at);",
    "CREATE INDEX IF NOT EXISTS ix_audit_dispatches_status ON audit_dispatches (status);",
    """
    CREATE TABLE IF NOT EXISTS invites (
        code       TEXT PRIMARY KEY,
        tenant_id  TEXT,
        email      TEXT,
        role       TEXT,
        status     TEXT,
        data       JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        expires_at TIMESTAMPTZ
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_invites_tenant ON invites (tenant_id);",
    """
    CREATE TABLE IF NOT EXISTS feedback (
        id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email      TEXT,
        tenant_id  TEXT,
        category   TEXT,
        data       JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_feedback_tenant ON feedback (tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_feedback_created ON feedback (created_at);",
    """
    CREATE TABLE IF NOT EXISTS caan_reports (
        id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        report_id  TEXT UNIQUE,
        tenant_id  TEXT,
        data       JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_caan_reports_tenant ON caan_reports (tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_caan_reports_created ON caan_reports (created_at);",
    """
    CREATE TABLE IF NOT EXISTS sms_maturity (
        id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id  TEXT NOT NULL,
        days       INTEGER,
        data       JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ux_sms_maturity_tenant_days UNIQUE (tenant_id, days)
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_sms_maturity_tenant ON sms_maturity (tenant_id);",
    """
    CREATE TABLE IF NOT EXISTS state_risk_categories (
        slug       TEXT PRIMARY KEY,
        name       TEXT,
        data       JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS dead_letter_queue (
        id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        key        TEXT UNIQUE,
        status     TEXT,
        data       JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_dead_letter_queue_created ON dead_letter_queue (created_at);",
    "CREATE INDEX IF NOT EXISTS ix_dead_letter_queue_status ON dead_letter_queue (status);",
]


async def ensure_domain_schema_async(engine: Optional[AsyncEngine] = None) -> None:
    """Create the Firestore-migration domain tables (idempotent)."""
    engine = engine or get_engine()
    async with engine.begin() as conn:
        for ddl in _DOMAIN_DDL:
            await conn.execute(text(ddl))


def ensure_domain_schema(engine: Optional[AsyncEngine] = None) -> None:
    """Synchronous entry point (dispatches onto the bridge loop)."""
    from app.db.runner import run

    run(ensure_domain_schema_async(engine))


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