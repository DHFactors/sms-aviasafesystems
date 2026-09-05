-- ============================================================================
-- SRAM Module - Safety Risk Assessment & Mitigation (Phase 2A/2B)
-- ============================================================================
--   ICAO Annex 19 / Doc 9859 / CAAN Chapter 2.3 compliant Bow-Tie analysis,
--   risk register and barrier register table set.
--
--   Tables created:
--     bow_tie_analyses     - one Bow-Tie analysis per hazard
--     bow_tie_threats      - threats (left side of the Bow-Tie)
--     bow_tie_consequences - consequences (right side of the Bow-Tie)
--     bow_tie_controls     - preventive controls + recovery barriers
--     risk_register        - current/resultant risk plus ALARP acceptance
--     barrier_register     - safety barriers with element scores + BSV
--
--   Every table is tenant-isolated: tenant_id uuid + RLS policy
--   p_<table>_tenant_isolation and tenant-scoped indexes ix_<table>_tenant_*.
--   All statements are idempotent (IF NOT EXISTS / DO $$ guards).
-- ============================================================================

-- 1. BOW-TIE ANALYSES --------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.bow_tie_analyses (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    uuid NOT NULL,
    hazard_id    text NOT NULL,
    hazard_title text,
    top_event    text,
    description  text,
    status       text NOT NULL DEFAULT 'In Progress',
    created_by   text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    is_demo      boolean NOT NULL DEFAULT false,
    CONSTRAINT ck_bow_tie_analyses_status
        CHECK (status IN ('In Progress', 'Assessed', 'Accepted', 'Rejected'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_bow_tie_analyses_tenant_hazard
    ON public.bow_tie_analyses (tenant_id, hazard_id);
CREATE INDEX IF NOT EXISTS ix_bow_tie_analyses_tenant
    ON public.bow_tie_analyses (tenant_id);
CREATE INDEX IF NOT EXISTS ix_bow_tie_analyses_tenant_status
    ON public.bow_tie_analyses (tenant_id, status);

-- 2. BOW-TIE THREATS ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.bow_tie_threats (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    uuid NOT NULL,
    bowtie_id    uuid NOT NULL REFERENCES public.bow_tie_analyses (id) ON DELETE CASCADE,
    threat       text NOT NULL,
    probability  int CHECK (probability BETWEEN 1 AND 5),
    threat_order int NOT NULL DEFAULT 1,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_bow_tie_threats_order
    ON public.bow_tie_threats (bowtie_id, threat_order);
CREATE INDEX IF NOT EXISTS ix_bow_tie_threats_tenant
    ON public.bow_tie_threats (tenant_id);

-- 3. BOW-TIE CONSEQUENCES ----------------------------------------------------
CREATE TABLE IF NOT EXISTS public.bow_tie_consequences (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL,
    bowtie_id         uuid NOT NULL REFERENCES public.bow_tie_analyses (id) ON DELETE CASCADE,
    consequence       text NOT NULL,
    severity_level    text NOT NULL DEFAULT 'C',
    consequence_order int NOT NULL DEFAULT 1,
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_bow_tie_consequences_severity
        CHECK (severity_level IN ('A', 'B', 'C', 'D', 'E'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_bow_tie_consequences_order
    ON public.bow_tie_consequences (bowtie_id, consequence_order);
CREATE INDEX IF NOT EXISTS ix_bow_tie_consequences_tenant
    ON public.bow_tie_consequences (tenant_id);

-- 4. BOW-TIE CONTROLS --------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.bow_tie_controls (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    bowtie_id       uuid NOT NULL REFERENCES public.bow_tie_analyses (id) ON DELETE CASCADE,
    control         text NOT NULL,
    control_type    text NOT NULL,                       -- 'preventive' | 'recovery'
    control_order   int NOT NULL DEFAULT 1,
    owner           text,
    status          text NOT NULL DEFAULT 'Planned',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_bow_tie_controls_type
        CHECK (control_type IN ('preventive', 'recovery')),
    CONSTRAINT ck_bow_tie_controls_status
        CHECK (status IN ('Planned', 'In Progress', 'Implemented', 'Verified'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_bow_tie_controls_order
    ON public.bow_tie_controls (bowtie_id, control_type, control_order);
CREATE INDEX IF NOT EXISTS ix_bow_tie_controls_tenant
    ON public.bow_tie_controls (tenant_id);

-- 5. RISK REGISTER -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.risk_register (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               uuid NOT NULL,
    bowtie_id               uuid REFERENCES public.bow_tie_analyses (id) ON DELETE SET NULL,
    hazard_id               text NOT NULL,
    hazard_title            text,
    probability_current     int NOT NULL,
    severity_current        text NOT NULL,
    risk_index_current      text NOT NULL,
    tolerability_current    text NOT NULL,
    probability_resultant   int,
    severity_resultant      text,
    risk_index_resultant    text,
    tolerability_resultant  text,
    status                  text NOT NULL DEFAULT 'open',   -- open | in_progress | closed
    accepted                boolean NOT NULL DEFAULT false,
    alarp_justification     text,
    accepted_by             text,
    accepted_on             timestamptz,
    review_date             timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    is_demo                 boolean NOT NULL DEFAULT false,
    CONSTRAINT ck_risk_register_severity_current
        CHECK (severity_current IN ('A', 'B', 'C', 'D', 'E')),
    CONSTRAINT ck_risk_register_severity_resultant
        CHECK (severity_resultant IS NULL OR severity_resultant IN ('A', 'B', 'C', 'D', 'E')),
    CONSTRAINT ck_risk_register_probability_current
        CHECK (probability_current BETWEEN 1 AND 5),
    CONSTRAINT ck_risk_register_probability_resultant
        CHECK (probability_resultant IS NULL OR probability_resultant BETWEEN 1 AND 5),
    CONSTRAINT ck_risk_register_status
        CHECK (status IN ('open', 'in_progress', 'closed'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_risk_register_tenant_hazard
    ON public.risk_register (tenant_id, hazard_id);
CREATE INDEX IF NOT EXISTS ix_risk_register_tenant
    ON public.risk_register (tenant_id);
CREATE INDEX IF NOT EXISTS ix_risk_register_tenant_status
    ON public.risk_register (tenant_id, status);

-- 6. BARRIER REGISTER --------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.barrier_register (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id              uuid NOT NULL,
    bowtie_id              uuid REFERENCES public.bow_tie_analyses (id) ON DELETE SET NULL,
    control_id             uuid REFERENCES public.bow_tie_controls (id) ON DELETE SET NULL,
    hazard_id              text NOT NULL,
    barrier                text NOT NULL,
    barrier_type           text NOT NULL,                -- 'preventive' | 'recovery'
    effectiveness          int CHECK (effectiveness BETWEEN 1 AND 5),
    cost_benefit           int CHECK (cost_benefit BETWEEN 1 AND 5),
    practicality           int CHECK (practicality BETWEEN 1 AND 5),
    acceptability          int CHECK (acceptability BETWEEN 1 AND 5),
    enforceability         int CHECK (enforceability BETWEEN 1 AND 5),
    durability             int CHECK (durability BETWEEN 1 AND 5),
    disinclination         int CHECK (disinclination BETWEEN 1 AND 5),
    bsv                    numeric(3, 1),                -- Barrier Strength Value (1-5)
    implementation_status  text NOT NULL DEFAULT 'not_started'
                           -- not_started | in_progress | implemented | verified
                           ,
    action_by              text,
    follow_up_date         timestamptz,
    notes                  text,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    is_demo                boolean NOT NULL DEFAULT false,
    CONSTRAINT ck_barrier_register_type
        CHECK (barrier_type IN ('preventive', 'recovery')),
    CONSTRAINT ck_barrier_register_impl_status
        CHECK (implementation_status IN ('not_started', 'in_progress', 'implemented', 'verified'))
);

CREATE INDEX IF NOT EXISTS ix_barrier_register_tenant
    ON public.barrier_register (tenant_id);
CREATE INDEX IF NOT EXISTS ix_barrier_register_tenant_hazard
    ON public.barrier_register (tenant_id, hazard_id);

-- ============================================================================
-- ROW LEVEL SECURITY
-- ============================================================================
DO $$
DECLARE
    tbl text;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'bow_tie_analyses', 'bow_tie_threats', 'bow_tie_consequences',
        'bow_tie_controls', 'risk_register', 'barrier_register'
    ]
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', tbl);
    END LOOP;
END $$;

DO $$
DECLARE
    tbl text;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'bow_tie_analyses', 'bow_tie_threats', 'bow_tie_consequences',
        'bow_tie_controls', 'risk_register', 'barrier_register'
    ]
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = 'public' AND tablename = tbl
              AND policyname = 'p_' || tbl || '_tenant_isolation'
        ) THEN
            EXECUTE format(
                'CREATE POLICY p_%I_tenant_isolation ON public.%I TO authenticated ' ||
                'USING (tenant_id = ((auth.jwt() -> ''app_metadata''::text) ->> ''tenant_id''::text)::uuid) ' ||
                'WITH CHECK (tenant_id = ((auth.jwt() -> ''app_metadata''::text) ->> ''tenant_id''::text)::uuid);',
                tbl, tbl
            );
        END IF;
    END LOOP;
END $$;

-- ============================================================================
-- GRANTS
-- ============================================================================
GRANT ALL ON TABLE public.bow_tie_analyses TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.bow_tie_threats TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.bow_tie_consequences TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.bow_tie_controls TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.risk_register TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.barrier_register TO anon, authenticated, service_role;

-- ============================================================================
-- DOCUMENTATION
-- ============================================================================
COMMENT ON TABLE public.bow_tie_analyses
    IS 'One Bow-Tie analysis per hazard (ICAO Annex 19 safety risk management).';
COMMENT ON TABLE public.bow_tie_threats
    IS 'Threats on the left side of the Bow-Tie leading to the top event.';
COMMENT ON TABLE public.bow_tie_consequences
    IS 'Consequences on the right side of the Bow-Tie with severity level A-E.';
COMMENT ON TABLE public.bow_tie_controls
    IS 'Preventive controls (left) and recovery barriers (right) on the Bow-Tie.';
COMMENT ON TABLE public.risk_register
    IS 'Current and resultant risk indices with tolerability and ALARP acceptance.';
COMMENT ON TABLE public.barrier_register
    IS 'Safety barriers with 7 element scores and correlated Barrier Strength Value (BSV).';