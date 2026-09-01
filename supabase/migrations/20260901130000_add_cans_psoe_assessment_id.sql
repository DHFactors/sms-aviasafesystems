-- Add psoe_assessment_id column to cans table
ALTER TABLE cans ADD COLUMN IF NOT EXISTS psoe_assessment_id text;

-- Add index for faster lookups
CREATE INDEX IF NOT EXISTS idx_cans_psoe_assessment_id ON cans(psoe_assessment_id);

-- Comment on column for documentation
COMMENT ON COLUMN cans.psoe_assessment_id IS 'References the PSOE assessment that triggered this CAN (PSOE→CAN link)';