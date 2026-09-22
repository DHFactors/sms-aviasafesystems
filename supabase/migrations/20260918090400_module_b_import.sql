-- ============================================================================
-- Module B — Phase 1: historical import infrastructure (P1-15, SN12)
-- ============================================================================
--   import_batches  — one row per uploaded file (§25.5)
--   import_rows     — staged/validated rows tagged with entity type
--   import_mappings — per-tenant, per-entity/per-sheet saved column maps
--   import_links    — cross-sheet / cross-batch staged-row links
--   + hazards.import_batch_id FK (column added in the hazards migration)
--
--   Idempotent: safe to re-run (IF NOT EXISTS / guarded policy).
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.import_batches (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL,
    source_filename   text,
    source_format     text,
    source_size_bytes integer,
    source_hash       text,
    status            text NOT NULL DEFAULT 'uploaded',
    total_rows        integer NOT NULL DEFAULT 0,
    valid_rows        integer NOT NULL DEFAULT 0,
    error_rows        integer NOT NULL DEFAULT 0,
    uploaded_by       uuid REFERENCES public.users (id),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_import_batches_status
        CHECK (status IN ('uploaded', 'parsing', 'staged', 'validated',
                          'review', 'promoted', 'failed')),
    CONSTRAINT ck_import_batches_source_format
        CHECK (source_format IS NULL OR source_format IN ('xlsx', 'csv', 'xls'))
);
CREATE INDEX IF NOT EXISTS ix_import_batches_tenant
    ON public.import_batches (tenant_id);
CREATE INDEX IF NOT EXISTS ix_import_batches_tenant_hash
    ON public.import_batches (tenant_id, source_hash);
CREATE INDEX IF NOT EXISTS ix_import_batches_tenant_status
    ON public.import_batches (tenant_id, status);

CREATE TABLE IF NOT EXISTS public.import_rows (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id           uuid NOT NULL REFERENCES public.import_batches (id) ON DELETE CASCADE,
    tenant_id          uuid NOT NULL,
    entity_type        text NOT NULL,
    sheet_name         text,
    row_number         integer,
    original_row_ref   text,
    raw_data           jsonb,
    normalized_data    jsonb,
    validation_status  text DEFAULT 'pending',
    validation_errors  jsonb,
    promoted           boolean NOT NULL DEFAULT false,
    promoted_record_id uuid,
    created_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_import_rows_entity_type
        CHECK (entity_type IN ('hazard', 'risk_register', 'sram_risk_register',
                               'bow_tie', 'barrier', 'can', 'cap')),
    CONSTRAINT ck_import_rows_validation_status
        CHECK (validation_status IS NULL OR validation_status IN
               ('pending', 'valid', 'warning', 'error'))
);
CREATE INDEX IF NOT EXISTS ix_import_rows_batch
    ON public.import_rows (batch_id);
CREATE INDEX IF NOT EXISTS ix_import_rows_tenant
    ON public.import_rows (tenant_id);
CREATE INDEX IF NOT EXISTS ix_import_rows_tenant_status
    ON public.import_rows (tenant_id, validation_status);

CREATE TABLE IF NOT EXISTS public.import_mappings (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    uuid NOT NULL,
    entity_type  text NOT NULL,
    sheet_name   text,
    name         text,
    column_map   jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_default   boolean NOT NULL DEFAULT false,
    created_by   uuid REFERENCES public.users (id),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_import_mappings_tenant
    ON public.import_mappings (tenant_id);
CREATE INDEX IF NOT EXISTS ix_import_mappings_tenant_entity
    ON public.import_mappings (tenant_id, entity_type);

CREATE TABLE IF NOT EXISTS public.import_links (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        uuid NOT NULL,
    batch_id         uuid REFERENCES public.import_batches (id) ON DELETE SET NULL,
    source_row_id    uuid REFERENCES public.import_rows (id) ON DELETE CASCADE,
    target_row_id    uuid REFERENCES public.import_rows (id) ON DELETE SET NULL,
    target_record_id uuid,
    link_type        text,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_import_links_tenant
    ON public.import_links (tenant_id);
CREATE INDEX IF NOT EXISTS ix_import_links_batch
    ON public.import_links (batch_id);

-- hazards.import_batch_id FK (column added by 20260918090000_module_b_hazards.sql)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_hazards_import_batch'
    ) THEN
        ALTER TABLE public.hazards ADD CONSTRAINT fk_hazards_import_batch
            FOREIGN KEY (import_batch_id) REFERENCES public.import_batches (id);
    END IF;
END $$;

-- RLS tenant isolation for all four import tables.
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['import_batches', 'import_rows',
                             'import_mappings', 'import_links'] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', t);
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies WHERE schemaname = 'public'
              AND tablename = t AND policyname = 'p_' || t || '_tenant_isolation'
        ) THEN
            EXECUTE format(
                'CREATE POLICY %I ON public.%I TO authenticated ' ||
                'USING (tenant_id = ((auth.jwt() -> ''app_metadata''::text) ->> ''tenant_id''::text)::uuid) ' ||
                'WITH CHECK (tenant_id = ((auth.jwt() -> ''app_metadata''::text) ->> ''tenant_id''::text)::uuid);',
                'p_' || t || '_tenant_isolation', t
            );
        END IF;
        EXECUTE format('GRANT ALL ON TABLE public.%I TO anon, authenticated, service_role;', t);
    END LOOP;
END $$;
