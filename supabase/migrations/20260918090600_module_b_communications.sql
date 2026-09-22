-- ============================================================================
-- Module B — Phase 1: safety_communications / bulletins (P1-18, SN17)
-- ============================================================================
--   Tenant-scoped safety bulletin derived from hazard/risk analysis
--   (§31, Doc 9859 §9.6.5). Status draft/review/published/archived;
--   approval by the safety-manager capability.
--   Idempotent: safe to re-run (IF NOT EXISTS / guarded policy).
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.safety_communications (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               uuid NOT NULL,
    title                   text NOT NULL,
    body                    text,
    status                  text NOT NULL DEFAULT 'draft',
    audience                jsonb,
    derived_from_hazard_ids uuid[],
    published_at            timestamptz,
    published_by            uuid REFERENCES public.users (id),
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_safety_communications_status
        CHECK (status IN ('draft', 'review', 'published', 'archived'))
);
CREATE INDEX IF NOT EXISTS ix_safety_communications_tenant
    ON public.safety_communications (tenant_id);
CREATE INDEX IF NOT EXISTS ix_safety_communications_tenant_status
    ON public.safety_communications (tenant_id, status);

ALTER TABLE public.safety_communications ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public'
          AND tablename = 'safety_communications'
          AND policyname = 'p_safety_communications_tenant_isolation'
    ) THEN
        EXECUTE format(
            'CREATE POLICY p_safety_communications_tenant_isolation ON public.safety_communications TO authenticated ' ||
            'USING (tenant_id = ((auth.jwt() -> ''app_metadata''::text) ->> ''tenant_id''::text)::uuid) ' ||
            'WITH CHECK (tenant_id = ((auth.jwt() -> ''app_metadata''::text) ->> ''tenant_id''::text)::uuid);'
        );
    END IF;
END $$;

GRANT ALL ON TABLE public.safety_communications TO anon, authenticated, service_role;

COMMENT ON COLUMN public.safety_communications.derived_from_hazard_ids
    IS 'SN17: hazards.id (uuid[]) this bulletin is derived from.';
