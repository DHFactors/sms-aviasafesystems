-- ============================================================================
-- Module C — Phase 1: PSOE finding <-> CAP linkage (P1-25, SN-C10)
-- ============================================================================
--   Bidirectional, optional, manual (Q4.1b). Both columns nullable; no
--   cascade on the back-reference.
--     psoe_findings.cap_id              uuid FK -> caps.id
--     caps.source_psoe_finding_id       uuid FK -> psoe_findings.id
--   Idempotent: safe to re-run (IF NOT EXISTS / guarded constraints).
-- ============================================================================

ALTER TABLE public.psoe_findings ADD COLUMN IF NOT EXISTS cap_id uuid;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_psoe_findings_cap'
    ) THEN
        ALTER TABLE public.psoe_findings ADD CONSTRAINT fk_psoe_findings_cap
            FOREIGN KEY (cap_id) REFERENCES public.caps (id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_psoe_findings_cap ON public.psoe_findings (cap_id);

ALTER TABLE public.caps ADD COLUMN IF NOT EXISTS source_psoe_finding_id uuid;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_caps_source_psoe_finding'
    ) THEN
        ALTER TABLE public.caps ADD CONSTRAINT fk_caps_source_psoe_finding
            FOREIGN KEY (source_psoe_finding_id) REFERENCES public.psoe_findings (id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_caps_source_psoe_finding
    ON public.caps (source_psoe_finding_id);

COMMENT ON COLUMN public.psoe_findings.cap_id
    IS 'SN-C10: optional CAP created from this PSOE finding (bidirectional, manual).';
COMMENT ON COLUMN public.caps.source_psoe_finding_id
    IS 'SN-C10: optional PSOE finding this CAP was created from (no cascade).';
