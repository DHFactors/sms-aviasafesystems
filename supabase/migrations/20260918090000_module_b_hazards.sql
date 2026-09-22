-- ============================================================================
-- Module B — Phase 1: hazards columns (P1-4..P1-9)
-- ============================================================================
--   SN1  (P1-4) hazards.identified_at      timestamptz  (date identified)
--   SN2  (P1-5) hazards.equipment          text         (CAAN §2.1 field ii)
--   SN7  (P1-6) hazards.first_priority_at  timestamptz  (set once at creation)
--   SN8  (P1-7) ck_hazards_status CHECK    6-value enum
--   SN12 (P1-8) imported_at / import_batch_id / original_row_ref /
--               legacy_hazard_code        (import provenance)
--   SN14 (P1-9) enrichment_data / enrichment_sources  jsonb
--
--   Idempotent: safe to re-run (IF NOT EXISTS / DO $$ guards).
--   The import_batch_id FK is added in 20260918090400_module_b_import.sql
--   (after import_batches exists).
-- ============================================================================

ALTER TABLE public.hazards ADD COLUMN IF NOT EXISTS identified_at      TIMESTAMPTZ;
ALTER TABLE public.hazards ADD COLUMN IF NOT EXISTS first_priority_at  TIMESTAMPTZ;
ALTER TABLE public.hazards ADD COLUMN IF NOT EXISTS equipment          TEXT;
ALTER TABLE public.hazards ADD COLUMN IF NOT EXISTS imported_at        TIMESTAMPTZ;
ALTER TABLE public.hazards ADD COLUMN IF NOT EXISTS import_batch_id    UUID;
ALTER TABLE public.hazards ADD COLUMN IF NOT EXISTS original_row_ref   TEXT;
ALTER TABLE public.hazards ADD COLUMN IF NOT EXISTS legacy_hazard_code TEXT;
ALTER TABLE public.hazards ADD COLUMN IF NOT EXISTS enrichment_data    JSONB;
ALTER TABLE public.hazards ADD COLUMN IF NOT EXISTS enrichment_sources JSONB;

CREATE INDEX IF NOT EXISTS ix_hazards_tenant_legacy_code
    ON public.hazards (tenant_id, legacy_hazard_code);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_hazards_status'
    ) THEN
        ALTER TABLE public.hazards ADD CONSTRAINT ck_hazards_status
            CHECK (status IN ('Open', 'Processing', 'Under Review',
                              'Pending Closure', 'Closed', 'Reopened'));
    END IF;
END $$;

COMMENT ON COLUMN public.hazards.identified_at
    IS 'SN1: date the hazard was identified (not registered), distinct from created_at.';
COMMENT ON COLUMN public.hazards.first_priority_at
    IS 'SN7: instant the initial priority was assigned; set once at creation, never re-stamped.';
COMMENT ON COLUMN public.hazards.equipment
    IS 'SN2: CAAN SRM Manual §2.1 field (ii) free-text area/operation/equipment.';
COMMENT ON COLUMN public.hazards.legacy_hazard_code
    IS 'SN12: legacy operator hazard code preserved on import (e.g. OPS/001/M/2026).';
