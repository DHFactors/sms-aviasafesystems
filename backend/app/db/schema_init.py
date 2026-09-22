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
        id                UUID PRIMARY KEY,  -- app writes uuid5('tenant:'||slug)
        tenant_id         TEXT,
        slug              TEXT NOT NULL UNIQUE,
        name              TEXT,
        icao              TEXT,
        country           TEXT,
        regulator_id      TEXT,
        status            TEXT,
        is_demo           BOOLEAN NOT NULL DEFAULT FALSE,
        is_beta_sandbox   BOOLEAN NOT NULL DEFAULT FALSE,
        active            BOOLEAN DEFAULT TRUE,
        auto_expire_days  INTEGER,
        safety_manager    JSONB,
        contact_id        TEXT,
        contact_name      TEXT,
        contact_email     TEXT,
        contact_phone     TEXT,
        contact_title     TEXT,
        contact_created_at TIMESTAMPTZ,
        oversight_level   TEXT,
        oversight_effective_date DATE,
        module_access     JSONB,
        modules           JSONB,
        data              JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_tenants_status ON tenants (status);",
    "CREATE INDEX IF NOT EXISTS ix_tenants_demo ON tenants (is_demo);",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS tenant_id TEXT;",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS icao TEXT;",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS country TEXT;",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS regulator_id TEXT;",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS contact_id TEXT;",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS contact_name TEXT;",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS contact_email TEXT;",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS contact_phone TEXT;",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS contact_title TEXT;",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS contact_created_at TIMESTAMPTZ;",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS oversight_level TEXT;",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS oversight_effective_date DATE;",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS module_access JSONB;",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS modules JSONB;",
    "UPDATE tenants SET tenant_id = slug WHERE tenant_id IS NULL;",
    "ALTER TABLE tenants ALTER COLUMN tenant_id DROP NOT NULL;",
    # The live DB provisioned tenants.regulator_id / contact_id as UUID, but the
    # app stores string keys (regulator slug e.g. "caan", contact id) everywhere.
    # Coerce to TEXT so future CREATE/INSERTs accept the string values
    # (idempotent for fresh DBs where they are already TEXT).
    "ALTER TABLE tenants ALTER COLUMN regulator_id TYPE TEXT USING regulator_id::text;",
    "ALTER TABLE tenants ALTER COLUMN contact_id TYPE TEXT USING contact_id::text;",
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
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id        UUID NOT NULL REFERENCES tenants (id),
        assessment_date  TIMESTAMPTZ DEFAULT now(),
        overall_score    DOUBLE PRECISION,
        level            INTEGER CHECK (level BETWEEN 1 AND 5),
        pillar_scores    JSONB,
        element_scores   JSONB,
        gap_analysis     JSONB,
        recommendations  JSONB,
        created_at       TIMESTAMPTZ DEFAULT now(),
        updated_at       TIMESTAMPTZ DEFAULT now()
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
    """
    CREATE TABLE IF NOT EXISTS sram_risk_register (
        id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id                UUID NOT NULL,
        bowtie_id                UUID REFERENCES bow_tie_analyses (id) ON DELETE SET NULL,
        hazard_id                TEXT NOT NULL,
        hazard_title             TEXT,
        probability_current      INTEGER NOT NULL,
        severity_current         INTEGER NOT NULL,
        risk_index_current       INTEGER NOT NULL,
        tolerability_current     TEXT NOT NULL,
        probability_resultant    INTEGER,
        severity_resultant       INTEGER,
        risk_index_resultant     INTEGER,
        tolerability_resultant   TEXT,
        status                   TEXT NOT NULL DEFAULT 'open',
        accepted                 BOOLEAN NOT NULL DEFAULT FALSE,
        alarp_justification      TEXT,
        accepted_by              UUID,
        accepted_on              TIMESTAMPTZ,
        review_date              TIMESTAMPTZ,
        is_demo                  BOOLEAN DEFAULT TRUE,
        created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_sram_risk_register_probability_current
            CHECK (probability_current BETWEEN 1 AND 5),
        CONSTRAINT ck_sram_risk_register_probability_resultant
            CHECK (probability_resultant IS NULL OR probability_resultant BETWEEN 1 AND 5),
        CONSTRAINT ck_sram_risk_register_severity_current
            CHECK (severity_current BETWEEN 1 AND 5),
        CONSTRAINT ck_sram_risk_register_severity_resultant
            CHECK (severity_resultant IS NULL OR severity_resultant BETWEEN 1 AND 5),
        CONSTRAINT ck_sram_risk_register_index_current
            CHECK (risk_index_current BETWEEN 1 AND 25),
        CONSTRAINT ck_sram_risk_register_index_resultant
            CHECK (risk_index_resultant IS NULL OR risk_index_resultant BETWEEN 1 AND 25),
        CONSTRAINT ck_sram_risk_register_status
            CHECK (status IN ('open', 'in_progress', 'closed'))
    );
    """,
    # NOTE: the sram_risk_register unique key is (tenant_id, hazard_id,
    # consequence_id) and is created in _MODULE_B_DDL after consequence_id is
    # added (SN10 / P1-13) — the legacy whole-hazard unique index is dropped
    # there.
    "CREATE INDEX IF NOT EXISTS ix_sram_risk_register_tenant "
    "ON sram_risk_register (tenant_id);",
]


# ----------------------------------------------------------------------------
# MODULE B — PHASE 1 SCHEMA (P1-4..P1-19)
#
# Idempotent ALTER/CREATE mirroring the Module B Phase-1 migrations in
# supabase/migrations/. Applied by ensure_domain_schema_async so a running
# deployment converges without manual DDL. Every statement is safe to re-run.
# ----------------------------------------------------------------------------

# New Module B tables that carry tenant_id and follow the same RLS
# tenant-isolation policy as the rest of Module B.
_MODULE_B_RLS_TABLES = [
    "hazard_triage",
    "import_batches",
    "import_rows",
    "import_mappings",
    "import_links",
    "sag_meetings",
    "srb_meetings",
    "action_items",
    "safety_communications",
]


def _module_b_rls_ddl(table: str) -> list:
    policy = f"p_{table}_tenant_isolation"
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;",
        f"DROP POLICY IF EXISTS {policy} ON public.{table};",
        f"CREATE POLICY {policy} ON public.{table} TO authenticated "
        "USING (tenant_id = ((auth.jwt() -> 'app_metadata'::text) "
        "->> 'tenant_id'::text)::uuid) "
        "WITH CHECK (tenant_id = ((auth.jwt() -> 'app_metadata'::text) "
        "->> 'tenant_id'::text)::uuid);",
        f"GRANT ALL ON TABLE public.{table} TO anon, authenticated, service_role;",
    ]


_MODULE_B_DDL = [
    # -- P1-4..P1-9: hazards columns + status CHECK -------------------------
    "ALTER TABLE hazards ADD COLUMN IF NOT EXISTS identified_at TIMESTAMPTZ;",
    "ALTER TABLE hazards ADD COLUMN IF NOT EXISTS first_priority_at TIMESTAMPTZ;",
    "ALTER TABLE hazards ADD COLUMN IF NOT EXISTS equipment TEXT;",
    "ALTER TABLE hazards ADD COLUMN IF NOT EXISTS imported_at TIMESTAMPTZ;",
    "ALTER TABLE hazards ADD COLUMN IF NOT EXISTS import_batch_id UUID;",
    "ALTER TABLE hazards ADD COLUMN IF NOT EXISTS original_row_ref TEXT;",
    "ALTER TABLE hazards ADD COLUMN IF NOT EXISTS legacy_hazard_code TEXT;",
    "ALTER TABLE hazards ADD COLUMN IF NOT EXISTS enrichment_data JSONB;",
    "ALTER TABLE hazards ADD COLUMN IF NOT EXISTS enrichment_sources JSONB;",
    "CREATE INDEX IF NOT EXISTS ix_hazards_tenant_legacy_code "
    "ON hazards (tenant_id, legacy_hazard_code);",
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_hazards_status'
        ) THEN
            ALTER TABLE hazards ADD CONSTRAINT ck_hazards_status
                CHECK (status IN ('Open', 'Processing', 'Under Review',
                                  'Pending Closure', 'Closed', 'Reopened'));
        END IF;
    END $$;
    """,
    # -- P1-19: reports regulatory-timer columns ----------------------------
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS regulatory_category TEXT;",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS regulatory_deadline_at TIMESTAMPTZ;",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS regulatory_submitted_at TIMESTAMPTZ;",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS regulatory_submission_ref TEXT;",
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_reports_regulatory_category'
        ) THEN
            ALTER TABLE reports ADD CONSTRAINT ck_reports_regulatory_category
                CHECK (regulatory_category IS NULL
                       OR regulatory_category IN ('A', 'B', 'C', 'D'));
        END IF;
    END $$;
    """,
    # -- P1-11..P1-13: sram_risk_register columns + unique-key change --------
    "ALTER TABLE sram_risk_register ADD COLUMN IF NOT EXISTS process_by UUID;",
    "ALTER TABLE sram_risk_register ADD COLUMN IF NOT EXISTS process_signed_at TIMESTAMPTZ;",
    "ALTER TABLE sram_risk_register ADD COLUMN IF NOT EXISTS initial_authority TEXT;",
    "ALTER TABLE sram_risk_register ADD COLUMN IF NOT EXISTS resultant_authority TEXT;",
    "ALTER TABLE sram_risk_register ADD COLUMN IF NOT EXISTS consequence_id UUID;",
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'fk_sram_risk_register_process_by'
        ) THEN
            ALTER TABLE sram_risk_register ADD CONSTRAINT fk_sram_risk_register_process_by
                FOREIGN KEY (process_by) REFERENCES users (id);
        END IF;
    END $$;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'fk_sram_risk_register_consequence'
        ) THEN
            ALTER TABLE sram_risk_register ADD CONSTRAINT fk_sram_risk_register_consequence
                FOREIGN KEY (consequence_id) REFERENCES bow_tie_consequences (id)
                ON DELETE SET NULL;
        END IF;
    END $$;
    """,
    "DROP INDEX IF EXISTS ux_sram_risk_register_tenant_hazard;",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_sram_risk_register_tenant_hazard_consequence "
    "ON sram_risk_register (tenant_id, hazard_id, consequence_id);",
    "CREATE INDEX IF NOT EXISTS ix_sram_risk_register_consequence "
    "ON sram_risk_register (consequence_id);",
    # -- P1-14: hazard_triage ----------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS hazard_triage (
        id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id         UUID NOT NULL,
        hazard_id         UUID NOT NULL REFERENCES hazards (id) ON DELETE CASCADE,
        triaged_by        UUID REFERENCES users (id),
        triaged_at        TIMESTAMPTZ,
        decision          TEXT NOT NULL,
        notes             TEXT,
        initial_priority  TEXT,
        reversal_of       UUID REFERENCES hazard_triage (id) ON DELETE SET NULL,
        reversal_reason   TEXT,
        reversed_by       UUID REFERENCES users (id),
        reversed_at       TIMESTAMPTZ,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_hazard_triage_decision
            CHECK (decision IN ('Accepted', 'Rejected', 'Duplicate', 'Escalated')),
        CONSTRAINT ck_hazard_triage_initial_priority
            CHECK (initial_priority IS NULL OR initial_priority IN ('H', 'M', 'L'))
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_hazard_triage_tenant ON hazard_triage (tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_hazard_triage_hazard ON hazard_triage (tenant_id, hazard_id);",
    "CREATE INDEX IF NOT EXISTS ix_hazard_triage_reversal_of ON hazard_triage (reversal_of);",
    # -- P1-15: import infrastructure --------------------------------------
    """
    CREATE TABLE IF NOT EXISTS import_batches (
        id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id         UUID NOT NULL,
        source_filename   TEXT,
        source_format     TEXT,
        source_size_bytes INTEGER,
        source_hash       TEXT,
        status            TEXT NOT NULL DEFAULT 'uploaded',
        total_rows        INTEGER NOT NULL DEFAULT 0,
        valid_rows        INTEGER NOT NULL DEFAULT 0,
        error_rows        INTEGER NOT NULL DEFAULT 0,
        uploaded_by       UUID REFERENCES users (id),
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_import_batches_status
            CHECK (status IN ('uploaded', 'parsing', 'staged', 'validated',
                              'review', 'promoted', 'failed')),
        CONSTRAINT ck_import_batches_source_format
            CHECK (source_format IS NULL OR source_format IN ('xlsx', 'csv', 'xls'))
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_import_batches_tenant ON import_batches (tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_import_batches_tenant_hash ON import_batches (tenant_id, source_hash);",
    "CREATE INDEX IF NOT EXISTS ix_import_batches_tenant_status ON import_batches (tenant_id, status);",
    """
    CREATE TABLE IF NOT EXISTS import_rows (
        id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        batch_id          UUID NOT NULL REFERENCES import_batches (id) ON DELETE CASCADE,
        tenant_id         UUID NOT NULL,
        entity_type       TEXT NOT NULL,
        sheet_name        TEXT,
        row_number        INTEGER,
        original_row_ref  TEXT,
        raw_data          JSONB,
        normalized_data   JSONB,
        validation_status TEXT DEFAULT 'pending',
        validation_errors JSONB,
        promoted          BOOLEAN NOT NULL DEFAULT FALSE,
        promoted_record_id UUID,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_import_rows_entity_type
            CHECK (entity_type IN ('hazard', 'risk_register', 'sram_risk_register',
                                   'bow_tie', 'barrier', 'can', 'cap')),
        CONSTRAINT ck_import_rows_validation_status
            CHECK (validation_status IS NULL OR validation_status IN
                   ('pending', 'valid', 'warning', 'error'))
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_import_rows_batch ON import_rows (batch_id);",
    "CREATE INDEX IF NOT EXISTS ix_import_rows_tenant ON import_rows (tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_import_rows_tenant_status ON import_rows (tenant_id, validation_status);",
    """
    CREATE TABLE IF NOT EXISTS import_mappings (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id    UUID NOT NULL,
        entity_type  TEXT NOT NULL,
        sheet_name   TEXT,
        name         TEXT,
        column_map   JSONB NOT NULL DEFAULT '{}'::jsonb,
        is_default   BOOLEAN NOT NULL DEFAULT FALSE,
        created_by   UUID REFERENCES users (id),
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_import_mappings_tenant ON import_mappings (tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_import_mappings_tenant_entity ON import_mappings (tenant_id, entity_type);",
    """
    CREATE TABLE IF NOT EXISTS import_links (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id        UUID NOT NULL,
        batch_id         UUID REFERENCES import_batches (id) ON DELETE SET NULL,
        source_row_id    UUID REFERENCES import_rows (id) ON DELETE CASCADE,
        target_row_id    UUID REFERENCES import_rows (id) ON DELETE SET NULL,
        target_record_id UUID,
        link_type        TEXT,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_import_links_tenant ON import_links (tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_import_links_batch ON import_links (batch_id);",
    # -- P1-16: SAG / SRB meetings -----------------------------------------
    """
    CREATE TABLE IF NOT EXISTS sag_meetings (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        scheduled_at    TIMESTAMPTZ,
        held_at         TIMESTAMPTZ,
        attendees       JSONB,
        minutes_ref     TEXT,
        minutes_summary TEXT,
        status          TEXT NOT NULL DEFAULT 'Scheduled',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_sag_meetings_status
            CHECK (status IN ('Scheduled', 'Held', 'Cancelled'))
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_sag_meetings_tenant ON sag_meetings (tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_sag_meetings_tenant_scheduled ON sag_meetings (tenant_id, scheduled_at);",
    """
    CREATE TABLE IF NOT EXISTS srb_meetings (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        scheduled_at    TIMESTAMPTZ,
        held_at         TIMESTAMPTZ,
        attendees       JSONB,
        minutes_ref     TEXT,
        minutes_summary TEXT,
        status          TEXT NOT NULL DEFAULT 'Scheduled',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_srb_meetings_status
            CHECK (status IN ('Scheduled', 'Held', 'Cancelled'))
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_srb_meetings_tenant ON srb_meetings (tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_srb_meetings_tenant_scheduled ON srb_meetings (tenant_id, scheduled_at);",
    # -- P1-17: shared SAG/SRB action items --------------------------------
    """
    CREATE TABLE IF NOT EXISTS action_items (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id    UUID NOT NULL,
        meeting_type TEXT NOT NULL,
        meeting_id   UUID,
        hazard_id    UUID REFERENCES hazards (id) ON DELETE SET NULL,
        cap_id       UUID REFERENCES caps (id) ON DELETE SET NULL,
        assigned_to  TEXT,
        due_date     TIMESTAMPTZ,
        status       TEXT NOT NULL DEFAULT 'Open',
        notes        TEXT,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_action_items_meeting_type
            CHECK (meeting_type IN ('sag', 'srb'))
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_action_items_tenant ON action_items (tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_action_items_meeting ON action_items (meeting_type, meeting_id);",
    "CREATE INDEX IF NOT EXISTS ix_action_items_tenant_status ON action_items (tenant_id, status);",
    # -- P1-18: safety communications --------------------------------------
    """
    CREATE TABLE IF NOT EXISTS safety_communications (
        id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id                UUID NOT NULL,
        title                    TEXT NOT NULL,
        body                     TEXT,
        status                   TEXT NOT NULL DEFAULT 'draft',
        audience                 JSONB,
        derived_from_hazard_ids  UUID[],
        published_at             TIMESTAMPTZ,
        published_by             UUID REFERENCES users (id),
        created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_safety_communications_status
            CHECK (status IN ('draft', 'review', 'published', 'archived'))
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_safety_communications_tenant ON safety_communications (tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_safety_communications_tenant_status "
    "ON safety_communications (tenant_id, status);",
    # -- P1-8/P1-15: hazards.import_batch_id FK (import_batches now exists) --
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'fk_hazards_import_batch'
        ) THEN
            ALTER TABLE hazards ADD CONSTRAINT fk_hazards_import_batch
                FOREIGN KEY (import_batch_id) REFERENCES import_batches (id);
        END IF;
    END $$;
    """,
]

# RLS for the new Module B tables (same tenant-isolation policy as Module B).
_MODULE_B_DDL += [
    ddl for _t in _MODULE_B_RLS_TABLES for ddl in _module_b_rls_ddl(_t)
]


async def ensure_domain_schema_async(engine: Optional[AsyncEngine] = None) -> None:
    """Create the Firestore-migration domain tables (idempotent)."""
    engine = engine or get_engine()
    async with engine.begin() as conn:
        for ddl in _DOMAIN_DDL:
            await conn.execute(text(ddl))
        for ddl in _MODULE_B_DDL:
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