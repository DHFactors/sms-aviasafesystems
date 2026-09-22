-- ============================================================================
-- Module B — Phase 1: sram_risk_register columns + unique-key change
-- (P1-11..P1-13, SN5/SN6/SN10)
-- ============================================================================
--   SN5  (P1-11) process_by / process_signed_at      (two-signature rule)
--   SN6  (P1-12) initial_authority / resultant_authority (authority snapshot)
--   SN10 (P1-13) consequence_id FK → bow_tie_consequences.id
--                unique key (tenant_id, hazard_id) → (tenant_id, hazard_id,
--                consequence_id)
--
--   Idempotent: safe to re-run (IF NOT EXISTS / DO $$ guards).
-- ============================================================================

ALTER TABLE public.sram_risk_register ADD COLUMN IF NOT EXISTS process_by          UUID;
ALTER TABLE public.sram_risk_register ADD COLUMN IF NOT EXISTS process_signed_at   TIMESTAMPTZ;
ALTER TABLE public.sram_risk_register ADD COLUMN IF NOT EXISTS initial_authority   TEXT;
ALTER TABLE public.sram_risk_register ADD COLUMN IF NOT EXISTS resultant_authority TEXT;
ALTER TABLE public.sram_risk_register ADD COLUMN IF NOT EXISTS consequence_id      UUID;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_sram_risk_register_process_by'
    ) THEN
        ALTER TABLE public.sram_risk_register
            ADD CONSTRAINT fk_sram_risk_register_process_by
            FOREIGN KEY (process_by) REFERENCES public.users (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_sram_risk_register_consequence'
    ) THEN
        ALTER TABLE public.sram_risk_register
            ADD CONSTRAINT fk_sram_risk_register_consequence
            FOREIGN KEY (consequence_id)
            REFERENCES public.bow_tie_consequences (id) ON DELETE SET NULL;
    END IF;
END $$;

-- Per-consequence register rows (SN10): the whole-hazard unique key is
-- replaced by one row per (tenant, hazard, consequence). consequence_id is
-- NULL for the single whole-hazard row kept for back-compat.
DROP INDEX IF EXISTS public.ux_sram_risk_register_tenant_hazard;
CREATE UNIQUE INDEX IF NOT EXISTS ux_sram_risk_register_tenant_hazard_consequence
    ON public.sram_risk_register (tenant_id, hazard_id, consequence_id);
CREATE INDEX IF NOT EXISTS ix_sram_risk_register_consequence
    ON public.sram_risk_register (consequence_id);

COMMENT ON COLUMN public.sram_risk_register.process_by
    IS 'SN5: users.id (uuid) of the process-conformance signer.';
COMMENT ON COLUMN public.sram_risk_register.consequence_id
    IS 'SN10: bow_tie_consequences.id; NULL = single whole-hazard register row.';
COMMENT ON COLUMN public.sram_risk_register.initial_authority
    IS 'SN6: acceptance authority tier required for the initial risk level (snapshot).';
