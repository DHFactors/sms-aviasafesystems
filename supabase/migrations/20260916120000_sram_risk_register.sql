-- ============================================================================
-- SRAM Risk Register - D1: numeric sram_risk_register table
-- ============================================================================
--   CAAN SRM Manual §2.3.6.4 numeric risk register:
--     severity_current       int 1-5  (5=Catastrophic(A) .. 1=Negligible(E))
--     probability_current    int 1-5
--     risk_index_current     int = severity * probability (1-25)
--   Letter labels A-E are a display convention rendered by the UI layer; they
--   are never stored. Legacy `risk_register` (legacy SRM shape) is untouched.
--
--   Idempotent: safe to re-run (IF NOT EXISTS / DO $$ guards).
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.sram_risk_register (
    id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                uuid NOT NULL,
    bowtie_id                uuid REFERENCES public.bow_tie_analyses (id) ON DELETE SET NULL,
    hazard_id                text NOT NULL,
    hazard_title             text,
    probability_current      int NOT NULL,
    severity_current         int NOT NULL,
    risk_index_current       int NOT NULL,
    tolerability_current     text NOT NULL,
    probability_resultant    int,
    severity_resultant       int,
    risk_index_resultant     int,
    tolerability_resultant   text,
    status                   text NOT NULL DEFAULT 'open',
    accepted                 boolean NOT NULL DEFAULT false,
    alarp_justification      text,
    accepted_by              uuid,
    accepted_on              timestamptz,
    review_date              timestamptz,
    is_demo                  boolean DEFAULT true,
    created_at               timestamptz NOT NULL DEFAULT now(),
    updated_at               timestamptz NOT NULL DEFAULT now(),
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

CREATE UNIQUE INDEX IF NOT EXISTS ux_sram_risk_register_tenant_hazard
    ON public.sram_risk_register (tenant_id, hazard_id);
CREATE INDEX IF NOT EXISTS ix_sram_risk_register_tenant
    ON public.sram_risk_register (tenant_id);
CREATE INDEX IF NOT EXISTS ix_sram_risk_register_tenant_status
    ON public.sram_risk_register (tenant_id, status);

-- ============================================================================
-- ROW LEVEL SECURITY
-- ============================================================================
ALTER TABLE public.sram_risk_register ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'sram_risk_register'
          AND policyname = 'p_sram_risk_register_tenant_isolation'
    ) THEN
        EXECUTE format(
            'CREATE POLICY p_sram_risk_register_tenant_isolation ON public.sram_risk_register TO authenticated ' ||
            'USING (tenant_id = ((auth.jwt() -> ''app_metadata''::text) ->> ''tenant_id''::text)::uuid) ' ||
            'WITH CHECK (tenant_id = ((auth.jwt() -> ''app_metadata''::text) ->> ''tenant_id''::text)::uuid);'
        );
    END IF;
END $$;

-- ============================================================================
-- GRANTS
-- ============================================================================
GRANT ALL ON TABLE public.sram_risk_register TO anon, authenticated, service_role;

-- ============================================================================
-- DOCUMENTATION
-- ============================================================================
COMMENT ON TABLE public.sram_risk_register
    IS 'SRAM risk register. Severity/probability are stored numerically 1-5 and risk index as severity x probability (1-25); letter labels A-E are a display convention per CAAN SRM Manual §2.3.6.4.';
COMMENT ON COLUMN public.sram_risk_register.severity_current
    IS 'Numeric severity 1-5 (5=Catastrophic, 4=Major/Hazardous, 3=Moderate/Major, 2=Minor, 1=Negligible); display letter A-E is derived, never stored.';
COMMENT ON COLUMN public.sram_risk_register.risk_index_current
    IS 'risk index = severity_current * probability_current, integer 1-25.';
COMMENT ON COLUMN public.sram_risk_register.accepted_by
    IS 'users.id (uuid) of the accepting user, resolved from the Firebase uid/email at accept time.';