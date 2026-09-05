-- ============================================================================
-- Hazard ICAO / CAAN alignment (Phase 1)
-- ============================================================================
--   * New hazard reference format: {FUNCTION}/{SEQ}/{PRIORITY}/{YEAR}
--     (e.g. OPS/001/M/2026) — the tenant code is dropped from the reference;
--     tenant isolation remains via the (tenant_id, hazard_id) unique index.
--   * New `function` column + index so references can be filtered by area.
--   * CAAN Chapter 2.1 fields: threat, top_event and the SRM / corrective-action
--     flags, plus priority_date / status_date stamps.
--   * Taxonomy is revalued from the legacy 7-value set onto the ICAO-aligned
--     4-value set: Organizational, Technical, Human, Environmental.
-- ============================================================================

-- 1. Function column backing the first component of the new references.
ALTER TABLE hazards ADD COLUMN IF NOT EXISTS function TEXT NOT NULL DEFAULT 'GEN';
CREATE INDEX IF NOT EXISTS ix_hazards_tenant_function ON hazards (tenant_id, function);

-- 2. CAAN Chapter 2.1 fields.
ALTER TABLE hazards ADD COLUMN IF NOT EXISTS threat TEXT;
ALTER TABLE hazards ADD COLUMN IF NOT EXISTS top_event TEXT;
ALTER TABLE hazards ADD COLUMN IF NOT EXISTS corrective_action_flag BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE hazards ADD COLUMN IF NOT EXISTS srm_flag BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE hazards ADD COLUMN IF NOT EXISTS priority_date TIMESTAMPTZ;
ALTER TABLE hazards ADD COLUMN IF NOT EXISTS status_date TIMESTAMPTZ;

-- 3. Backfill the function column from already-migrated new-format references
--    (OPS/001/M/2026 -> OPS). Legacy tenant-coded references (FW-001-H-2026) are
--    re-derived by the Python migration script (migrate_hazard_ids_to_function_format.py);
--    rows that cannot be parsed stay GEN.
UPDATE hazards
SET function = split_part(hazard_id, '/', 1)
WHERE hazard_id LIKE '%/%'
  AND split_part(hazard_id, '/', 1) IN ('OPS','ENG','CAB','MNT','GHD','DSP','SAF','SEC','MED','TRN','ADM','ENV','HUM','ORG','GEN');

-- 4. Backfill the timestamps (priority as current at creation; status as of the
--    last update).
UPDATE hazards SET priority_date = created_at WHERE priority_date IS NULL;
UPDATE hazards SET status_date = updated_at WHERE status_date IS NULL;

-- 5. Taxonomy revaluation: legacy values -> ICAO-aligned 4-value set.
UPDATE hazards SET taxonomy = 'Organizational'
WHERE taxonomy IN ('Organizational-Facilities', 'Organizational-Documentation, Processes and Procedures', 'Other');
UPDATE hazards SET taxonomy = 'Environmental' WHERE taxonomy IN ('Wildlife');
UPDATE hazards SET taxonomy = 'Human' WHERE taxonomy IN ('Human Factors');
UPDATE hazards SET taxonomy = CASE
    WHEN taxonomy IS NULL OR taxonomy = '' THEN 'Organizational'
    ELSE taxonomy END;

-- 6. Enforce the 4-value taxonomy set.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_hazards_taxonomy'
    ) THEN
        ALTER TABLE hazards ADD CONSTRAINT ck_hazards_taxonomy
            CHECK (taxonomy IN ('Organizational', 'Technical', 'Human', 'Environmental'));
    END IF;
END $$;

-- 7. Documentation comments.
COMMENT ON COLUMN hazards.function IS 'ICAO function code first component of the CATM hazard reference (OPS, ENG, CAB, MNT, GHD, DSP, SAF, SEC, MED, TRN, ADM, ENV, HUM, ORG, GEN).';
COMMENT ON COLUMN hazards.threat IS 'CAAN CAR-19 Chapter 2.1: the hazard source / threat that could lead to the top event.';
COMMENT ON COLUMN hazards.top_event IS 'CAAN CAR-19 Chapter 2.1: the loss-of-control / consequence scenario the threat drives.';
COMMENT ON COLUMN hazards.corrective_action_flag IS 'Indicates a Corrective Action was raised from this hazard (drives the Recommended Action flag UI).';
COMMENT ON COLUMN hazards.srm_flag IS 'Indicates a Safety Risk Management (SRM) assessment is required / in scope for this hazard.';
COMMENT ON COLUMN hazards.priority_date IS 'Date the current priority was assigned / last changed.';
COMMENT ON COLUMN hazards.status_date IS 'Date of the latest status transition.';
COMMENT ON CONSTRAINT ck_hazards_taxonomy ON hazards IS 'ICAO-aligned 4-value hazard taxonomy (Organizational, Technical, Human, Environmental).';