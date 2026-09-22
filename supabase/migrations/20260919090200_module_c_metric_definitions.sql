-- ============================================================================
-- Module C — Phase 1: metric_definitions (P1-22, SN-C7)
-- ============================================================================
--   Trend-baseline window registry (read-only, CAAN-owned, seeded).
--   Defaults (Q10.2): state metrics = rolling_12m / 12 min periods;
--   operational metrics = rolling_90d / 3 min periods.
--   Idempotent: safe to re-run (IF NOT EXISTS / ON CONFLICT DO NOTHING).
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.metric_definitions (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_type  text NOT NULL,
    metric_key   text,
    window_type  text NOT NULL DEFAULT 'rolling_12m',
    window_days  integer,
    min_periods  integer,
    valid_from   timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_metric_definitions_window_type
        CHECK (window_type IN ('rolling_12m', 'rolling_90d', 'quarter_over_quarter'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_metric_definitions_type_key
    ON public.metric_definitions (metric_type, metric_key) NULLS NOT DISTINCT;

-- Seed the two default windows (metric_key NULL = type default).
INSERT INTO public.metric_definitions
    (metric_type, metric_key, window_type, window_days, min_periods)
VALUES
    ('state',       NULL, 'rolling_12m', 365, 12),
    ('operational', NULL, 'rolling_90d',  90,  3)
ON CONFLICT DO NOTHING;

ALTER TABLE public.metric_definitions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_metric_definitions_read ON public.metric_definitions;
CREATE POLICY p_metric_definitions_read ON public.metric_definitions
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS p_metric_definitions_cross_tenant ON public.metric_definitions;
CREATE POLICY p_metric_definitions_cross_tenant ON public.metric_definitions
    FOR ALL TO authenticated
    USING (((auth.jwt() -> 'app_metadata'::text) ->> 'role'::text) IN ('CAAN_SMD', 'SUPER_ADMIN'))
    WITH CHECK (((auth.jwt() -> 'app_metadata'::text) ->> 'role'::text) IN ('CAAN_SMD', 'SUPER_ADMIN'));

GRANT ALL ON TABLE public.metric_definitions TO anon, authenticated, service_role;
