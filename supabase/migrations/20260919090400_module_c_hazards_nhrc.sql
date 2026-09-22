-- ============================================================================
-- Module C — Phase 1: hazards.nhrc_category (P1-24, SN-C9)
-- ============================================================================
--   CROSS-MODULE SCHEMA ADDITION: a Module C-driven column on the Module
--   B-owned `hazards` table (coordinated change per MODULE_C_CONTRACT §8.4 /
--   SN-C9). Auto-derived by nhrc_service with manual CAAN override (Q8.2);
--   derivation is service-layer — this migration only adds the column.
--   Idempotent: safe to re-run (IF NOT EXISTS).
-- ============================================================================

ALTER TABLE public.hazards ADD COLUMN IF NOT EXISTS nhrc_category text;

COMMENT ON COLUMN public.hazards.nhrc_category
    IS 'SN-C9: N-HRC category (auto-derived with manual CAAN override). Module C-owned addition on a Module B table.';
