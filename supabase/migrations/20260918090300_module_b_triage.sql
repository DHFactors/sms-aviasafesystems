-- ============================================================================
-- Module B — Phase 1: hazard_triage table (P1-14, SN13)
-- ============================================================================
--   Human triage decision at hazard intake + reversal audit
--   (Decision 2: reversible by the safety-manager capability).
--   Idempotent: safe to re-run (IF NOT EXISTS / guarded policy).
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.hazard_triage (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL,
    hazard_id         uuid NOT NULL REFERENCES public.hazards (id) ON DELETE CASCADE,
    triaged_by        uuid REFERENCES public.users (id),
    triaged_at        timestamptz,
    decision          text NOT NULL,
    notes             text,
    initial_priority  text,
    reversal_of       uuid REFERENCES public.hazard_triage (id) ON DELETE SET NULL,
    reversal_reason   text,
    reversed_by       uuid REFERENCES public.users (id),
    reversed_at       timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_hazard_triage_decision
        CHECK (decision IN ('Accepted', 'Rejected', 'Duplicate', 'Escalated')),
    CONSTRAINT ck_hazard_triage_initial_priority
        CHECK (initial_priority IS NULL OR initial_priority IN ('H', 'M', 'L'))
);

CREATE INDEX IF NOT EXISTS ix_hazard_triage_tenant
    ON public.hazard_triage (tenant_id);
CREATE INDEX IF NOT EXISTS ix_hazard_triage_hazard
    ON public.hazard_triage (tenant_id, hazard_id);
CREATE INDEX IF NOT EXISTS ix_hazard_triage_reversal_of
    ON public.hazard_triage (reversal_of);

ALTER TABLE public.hazard_triage ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public'
          AND tablename = 'hazard_triage'
          AND policyname = 'p_hazard_triage_tenant_isolation'
    ) THEN
        EXECUTE format(
            'CREATE POLICY p_hazard_triage_tenant_isolation ON public.hazard_triage TO authenticated ' ||
            'USING (tenant_id = ((auth.jwt() -> ''app_metadata''::text) ->> ''tenant_id''::text)::uuid) ' ||
            'WITH CHECK (tenant_id = ((auth.jwt() -> ''app_metadata''::text) ->> ''tenant_id''::text)::uuid);'
        );
    END IF;
END $$;

GRANT ALL ON TABLE public.hazard_triage TO anon, authenticated, service_role;
