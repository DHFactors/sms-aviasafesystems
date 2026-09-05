-- 1. PSOE Questions (4 Components, 21 Questions)
CREATE TABLE IF NOT EXISTS psoe_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    component TEXT NOT NULL CHECK (component IN ('Safety Management', 'Risk Management', 'Safety Assurance', 'Safety Promotion')),
    question_number INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. PSOE Findings (linked to psoe_assessments)
CREATE TABLE IF NOT EXISTS psoe_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id UUID NOT NULL REFERENCES psoe_assessments(id) ON DELETE CASCADE,
    finding_type TEXT CHECK (finding_type IN ('Observation', 'Finding', 'Major Finding', 'Critical Finding')),
    description TEXT NOT NULL,
    corrective_action TEXT,
    status TEXT DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'closed')),
    target_date DATE,
    closed_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_psoe_findings_assessment ON psoe_findings(assessment_id);
CREATE UNIQUE INDEX uq_psoe_questions_component_number ON psoe_questions(component, question_number);
CREATE INDEX idx_psoe_questions_component ON psoe_questions(component);