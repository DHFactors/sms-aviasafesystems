-- ============================================================================
-- Module C — Phase 1: state_safety_performance_targets (P1-21, SN-C6)
-- ============================================================================
--   National-scope State SPTs set/approved by CAAN (Q5/Q9.2).
--   spi_definition_id is a logical FK to the SPI definitions in spi_service
--   (Q9.1 hybrid: code constants, no reference table), so it is plain text.
--   RLS: CAAN-only (CAAN_SMD / SUPER_ADMIN).
--   Idempotent: safe to re-run (IF NOT EXISTS / guarded policy).
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.state_safety_performance_targets (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    spi_definition_id text NOT NULL,
    target_value      double precision NOT NULL,
    target_period     text NOT NULL DEFAULT 'annual',
    set_by            text,
    set_at            timestamptz,
    approved_by       text,
    approved_at       timestamptz,
    valid_from        timestamptz,
    valid_to          timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_state_spt_spi
    ON public.state_safety_performance_targets (spi_definition_id);

ALTER TABLE public.state_safety_performance_targets ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_state_safety_performance_targets_caan
    ON public.state_safety_performance_targets;
CREATE POLICY p_state_safety_performance_targets_caan
    ON public.state_safety_performance_targets FOR ALL TO authenticated
    USING (((auth.jwt() -> 'app_metadata'::text) ->> 'role'::text) IN ('CAAN_SMD', 'SUPER_ADMIN'))
    WITH CHECK (((auth.jwt() -> 'app_metadata'::text) ->> 'role'::text) IN ('CAAN_SMD', 'SUPER_ADMIN'));

GRANT ALL ON TABLE public.state_safety_performance_targets
    TO anon, authenticated, service_role;

COMMENT ON COLUMN public.state_safety_performance_targets.spi_definition_id
    IS 'SN-C6: logical reference to spi_service SPI_DEFINITIONS (no DB FK; Q9.1 hybrid).';
