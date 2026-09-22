-- ============================================================================
-- Module C — Phase 1: module_c_aggregates (P1-20 + P1-27 + P1-28)
-- ============================================================================
--   SN-C1 / SN-C5: materialized SDCPS aggregation row.
--     tenant_id NULL = national/state scope (CAAN-only RLS, Q7.2).
--   P1-27: explicit NULL-tenant policy
--          USING (tenant_id IS NULL AND role = 'CAAN_SMD').
--   P1-28: cross-tenant policy for CAAN_SMD / SUPER_ADMIN.
--   Idempotent: safe to re-run (IF NOT EXISTS / guarded policy).
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.module_c_aggregates (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid,
    metric_type    text NOT NULL,
    metric_key     text,
    period_start   timestamptz,
    period_end     timestamptz,
    payload        jsonb NOT NULL DEFAULT '{}'::jsonb,
    computed_at    timestamptz NOT NULL DEFAULT now(),
    ttl_seconds    integer,
    source_version text
);

-- NULLS NOT DISTINCT so NULL tenant_id / metric_key still de-duplicate.
CREATE UNIQUE INDEX IF NOT EXISTS ux_module_c_aggregates_key
    ON public.module_c_aggregates
    (tenant_id, metric_type, metric_key, period_start) NULLS NOT DISTINCT;
CREATE INDEX IF NOT EXISTS ix_module_c_aggregates_tenant
    ON public.module_c_aggregates (tenant_id);
CREATE INDEX IF NOT EXISTS ix_module_c_aggregates_type
    ON public.module_c_aggregates (metric_type);

ALTER TABLE public.module_c_aggregates ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_module_c_aggregates_tenant_isolation
    ON public.module_c_aggregates;
CREATE POLICY p_module_c_aggregates_tenant_isolation
    ON public.module_c_aggregates FOR ALL TO authenticated
    USING (tenant_id = ((auth.jwt() -> 'app_metadata'::text) ->> 'tenant_id'::text)::uuid)
    WITH CHECK (tenant_id = ((auth.jwt() -> 'app_metadata'::text) ->> 'tenant_id'::text)::uuid);

-- P1-27: national (NULL-tenant) rows visible only to CAAN_SMD.
DROP POLICY IF EXISTS p_module_c_aggregates_national
    ON public.module_c_aggregates;
CREATE POLICY p_module_c_aggregates_national
    ON public.module_c_aggregates FOR SELECT TO authenticated
    USING (tenant_id IS NULL
           AND ((auth.jwt() -> 'app_metadata'::text) ->> 'role'::text) = 'CAAN_SMD');

-- P1-28: cross-tenant access for CAAN / SUPER_ADMIN.
DROP POLICY IF EXISTS p_module_c_aggregates_cross_tenant
    ON public.module_c_aggregates;
CREATE POLICY p_module_c_aggregates_cross_tenant
    ON public.module_c_aggregates FOR ALL TO authenticated
    USING (((auth.jwt() -> 'app_metadata'::text) ->> 'role'::text) IN ('CAAN_SMD', 'SUPER_ADMIN'))
    WITH CHECK (((auth.jwt() -> 'app_metadata'::text) ->> 'role'::text) IN ('CAAN_SMD', 'SUPER_ADMIN'));

GRANT ALL ON TABLE public.module_c_aggregates TO anon, authenticated, service_role;

COMMENT ON TABLE public.module_c_aggregates
    IS 'SN-C5: materialized SDCPS aggregates. tenant_id NULL = national/state scope (CAAN-only).';
