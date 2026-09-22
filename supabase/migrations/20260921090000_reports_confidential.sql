-- ============================================================================
-- Module C — P2-25 (DP-4): confidential / voluntary reporting class
-- ============================================================================
--   Adds the confidentiality flag + designated custodian to `reports`
--   (Module B-owned table; Module C ingestion adapter per the contract).
--   Reporter identity is visible only to the custodian; downstream consumers
--   use the de-identified projection.
--   Idempotent: safe to re-run (IF NOT EXISTS / guarded constraint).
-- ============================================================================

ALTER TABLE public.reports
    ADD COLUMN IF NOT EXISTS is_confidential BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.reports
    ADD COLUMN IF NOT EXISTS confidential_custodian_id UUID;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_reports_confidential_custodian'
    ) THEN
        ALTER TABLE public.reports ADD CONSTRAINT fk_reports_confidential_custodian
            FOREIGN KEY (confidential_custodian_id) REFERENCES public.users (id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_reports_confidential
    ON public.reports (is_confidential, confidential_custodian_id);

COMMENT ON COLUMN public.reports.is_confidential
    IS 'DP-4: confidential/voluntary reporting class (Appendix 3 protection).';
COMMENT ON COLUMN public.reports.confidential_custodian_id
    IS 'DP-4: users.id of the designated custodian permitted to view reporter identity.';
