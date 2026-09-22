-- ============================================================================
-- Module B — Phase 1: reports regulatory timer (P1-19, SN15)
-- ============================================================================
--   SN15: MOR category-tiered timer (ICAO Annex 13).
--     regulatory_category      text  'A'|'B'|'C'|'D' (A=24h, B=72h, C=7d, D=30d)
--     regulatory_deadline_at   timestamptz  submission + category window
--     regulatory_submitted_at  timestamptz  when actually transmitted
--     regulatory_submission_ref text         CAA reference
--
--   Idempotent: safe to re-run (IF NOT EXISTS / DO $$ guards).
-- ============================================================================

ALTER TABLE public.reports ADD COLUMN IF NOT EXISTS regulatory_category      TEXT;
ALTER TABLE public.reports ADD COLUMN IF NOT EXISTS regulatory_deadline_at   TIMESTAMPTZ;
ALTER TABLE public.reports ADD COLUMN IF NOT EXISTS regulatory_submitted_at  TIMESTAMPTZ;
ALTER TABLE public.reports ADD COLUMN IF NOT EXISTS regulatory_submission_ref TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_reports_regulatory_category'
    ) THEN
        ALTER TABLE public.reports ADD CONSTRAINT ck_reports_regulatory_category
            CHECK (regulatory_category IS NULL
                   OR regulatory_category IN ('A', 'B', 'C', 'D'));
    END IF;
END $$;

COMMENT ON COLUMN public.reports.regulatory_category
    IS 'SN15: ICAO Annex 13 MOR category A=24h / B=72h / C=7d / D=30d.';
COMMENT ON COLUMN public.reports.regulatory_deadline_at
    IS 'SN15: MOR submission + category reporting window (tenant default when no category).';
