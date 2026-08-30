-- ============================================================================
-- FILE: schema.sql
-- PATH: backend/app/db/schema.sql
-- ENGINES: PostgreSQL 13+ (Supabase)
-- PURPOSE: Relational schema mirroring the Pydantic models in
--          backend/app/models/ plus the survey / response documents persisted
--          by backend/app/routes/surveys.py.
--
-- CONVENTIONS
--   * Every business table carries a MANDATORY `tenant_id UUID NOT NULL`
--     column for multi-tenant isolation. A dedicated index per table backs
--     tenant-scoped lookups; compound indexes cover the hottest filter
--     combinations (status, assigned_to, created_at).
--   * Composite Pydantic value objects (SramData, BowTie configs, risk
--     assessments, root-cause trees, sign-off blocks, ...) are stored as
--     JSONB so the API can round-trip them without joins.
--   * String lists (human_factors, contributing_factors, evidence, ...) use
--     JSONB for symmetric mapping with SQLAlchemy `JSON` / `JSONB` types.
--   * `id` defaults to gen_random_uuid() (built-in since PostgreSQL 13);
--     the pgcrypto guard below is harmless and supports older engines.
--
-- MULTI-TENANCY: apply Row-Level Security per tenant on top of these tables
-- (policy key = tenant_id) once the `tenants` table exists.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================================
-- 1. HAZARDS  (backend/app/models/hazard.py - HazardResponse / HazardListItem)
-- ============================================================================

CREATE TABLE hazards (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hazard_id           TEXT NOT NULL,
    tenant_id           UUID NOT NULL,

    title               TEXT NOT NULL,
    description         TEXT NOT NULL,
    source              TEXT NOT NULL,
    source_id           TEXT NOT NULL,
    source_url          TEXT,

    adrep_category      TEXT,
    occurrence_type     TEXT,
    taxonomy            TEXT NOT NULL,
    taxonomy_specific   TEXT,
    consequence         TEXT,

    severity            INT CHECK (severity BETWEEN 1 AND 5),
    probability         INT CHECK (probability BETWEEN 1 AND 5),
    risk_index          INT,
    risk_level          TEXT,
    risk_outcome        TEXT,
    tolerability_tier   TEXT,

    priority            TEXT NOT NULL CHECK (priority IN ('H', 'M', 'L')),

    recommended_action  TEXT,
    corrective_action   TEXT,
    assigned_to         TEXT,
    assigned_to_uid     TEXT,
    department          TEXT,

    srm_conducted       BOOLEAN NOT NULL DEFAULT FALSE,
    srm_date            TIMESTAMPTZ,
    srm_status          TEXT,
    analysis_mode       TEXT NOT NULL DEFAULT 'FISHBONE_ONLY',
    sram_data           JSONB,              -- SramData: severity/barriers/risk_profile/bowtie/fishbone/signoffs

    status              TEXT NOT NULL,
    follow_up_date      TIMESTAMPTZ,
    closed_at           TIMESTAMPTZ,
    closed_by           TEXT,
    remarks             TEXT,

    is_demo             BOOLEAN NOT NULL DEFAULT FALSE,

    created_by          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_hazards_tenant_id       ON hazards (tenant_id, hazard_id);
CREATE INDEX        ix_hazards_tenant          ON hazards (tenant_id);
CREATE INDEX        ix_hazards_tenant_status   ON hazards (tenant_id, status);
CREATE INDEX        ix_hazards_tenant_assignee ON hazards (tenant_id, assigned_to);
CREATE INDEX        ix_hazards_tenant_created  ON hazards (tenant_id, created_at);
CREATE INDEX        idx_hazards_tenant_demo    ON hazards (tenant_id, is_demo);

-- ============================================================================
-- 2. VSR / MOR REPORTS  (backend/app/models/report.py)
--    One unified table: `report_type` = 'voluntary' (VSR) | 'mandatory' (MOR).
--    ReportResponse is the superset carrying both the VSR and MOR field sets.
-- ============================================================================

CREATE TABLE reports (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                   UUID NOT NULL,

    report_type                 TEXT NOT NULL CHECK (report_type IN ('voluntary', 'mandatory')),
    status                      TEXT NOT NULL,
    ai_status                   TEXT NOT NULL DEFAULT 'PENDING',

    narrative                   TEXT NOT NULL,
    location                    TEXT NOT NULL,
    occurrence_date             TIMESTAMPTZ NOT NULL,
    is_anonymous                BOOLEAN NOT NULL DEFAULT FALSE,

    flight_number               TEXT,
    aircraft_registration       TEXT,
    occurrence_type             TEXT,
    severity                    TEXT,
    investigation_status        TEXT,

    severity_level              INT CHECK (severity_level BETWEEN 1 AND 5),
    probability_level           INT CHECK (probability_level BETWEEN 1 AND 5),
    risk_index                  INT,
    risk_level                  TEXT,
    risk_assessment             JSONB,       -- RiskAssessment
    ai_suggested_assessment     JSONB,       -- AiSuggestedAssessment
    ai_analysis                 JSONB,       -- AiAnalysisResult

    occurrence_class            TEXT,
    latitude                    DOUBLE PRECISION,
    longitude                   DOUBLE PRECISION,
    country                     TEXT,

    aircraft_make               TEXT,
    aircraft_model              TEXT,
    aircraft_serial_number      TEXT,
    operator                    TEXT,
    operator_icao               TEXT,
    aircraft_category           TEXT,
    engine_make                 TEXT,
    engine_model                TEXT,
    engine_serial_number        TEXT,

    flight_phase                TEXT,
    flight_type                 TEXT,
    departure_airport           TEXT,
    destination_airport         TEXT,
    aircraft_utilisation_hours  DOUBLE PRECISION,
    aircraft_utilisation_cycles INT,

    crew_count                  INT,
    passenger_count             INT,
    fatal_injuries              INT,
    serious_injuries            INT,
    minor_injuries              INT,

    occurrence_category         TEXT,
    human_factors               JSONB,       -- List[str]
    contributing_factors        JSONB,       -- List[str]
    investigation_agency        TEXT,

    reporter_name               TEXT,
    reporter_role               TEXT,
    reporter_email              TEXT,
    reporter_phone              TEXT,
    reporter_organisation       TEXT,
    reporting_date              TIMESTAMPTZ,

    -- MOR-only block (merged into ReportResponse)
    etops                       BOOLEAN NOT NULL DEFAULT FALSE,
    propeller_make              TEXT,
    propeller_model             TEXT,
    call_sign                   TEXT,
    organisation_comments       TEXT,
    manufacturer_advised        BOOLEAN NOT NULL DEFAULT FALSE,
    fdr_data_retained           BOOLEAN NOT NULL DEFAULT FALSE,

    created_by                  TEXT NOT NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_reports_tenant           ON reports (tenant_id);
CREATE INDEX ix_reports_tenant_status    ON reports (tenant_id, status);
CREATE INDEX ix_reports_tenant_occdate   ON reports (tenant_id, occurrence_date);
CREATE INDEX ix_reports_tenant_aircraft  ON reports (tenant_id, aircraft_registration);
CREATE INDEX ix_reports_tenant_created   ON reports (tenant_id, created_at);
CREATE INDEX idx_reports_tenant_demo     ON reports (tenant_id, is_demo);

-- ============================================================================
-- 3. CAN (Corrective Action Notice)  (backend/app/models/can_cap.py)
--    Only CAN-scoped fields live here; CAP form fields live on `caps`.
-- ============================================================================

CREATE TABLE cans (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    can_reference            TEXT NOT NULL,
    tenant_id                UUID NOT NULL,
    hazard_id                UUID NOT NULL REFERENCES hazards (id),

    title                    TEXT NOT NULL,
    description              TEXT NOT NULL,
    required_action          TEXT NOT NULL,

    issued_by                TEXT NOT NULL,
    issued_by_uid            TEXT NOT NULL,
    issued_at                TIMESTAMPTZ,
    target_completion_date   TIMESTAMPTZ,
    assigned_to              TEXT NOT NULL,
    assigned_to_uid          TEXT NOT NULL,
    department               TEXT,
    priority                 TEXT NOT NULL CHECK (priority IN ('High', 'Medium', 'Low')),
    status                   TEXT NOT NULL,

    -- CANFormFields (FORM SMSM 8.8.2 issuance block)
    copies_to                TEXT,
    requested_function       TEXT,
    addressed_function       TEXT,
    initial_severity         INT CHECK (initial_severity BETWEEN 1 AND 5),
    initial_probability      INT CHECK (initial_probability BETWEEN 1 AND 5),
    initial_risk_index       INT CHECK (initial_risk_index BETWEEN 1 AND 25),
    initial_risk_level       TEXT,
    initial_risk_outcome     TEXT,
    initial_tolerability_tier TEXT,
    initial_sra              JSONB,
    classification_type      TEXT,
    classification_level     TEXT,

    is_demo                  BOOLEAN NOT NULL DEFAULT FALSE,

    created_by               TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_cans_tenant_ref ON cans (tenant_id, can_reference);
CREATE INDEX        ix_cans_tenant     ON cans (tenant_id);
CREATE INDEX        ix_cans_tenant_status ON cans (tenant_id, status);
CREATE INDEX        ix_cans_tenant_assignee ON cans (tenant_id, assigned_to);
CREATE INDEX        ix_cans_hazard     ON cans (tenant_id, hazard_id);
CREATE INDEX        idx_cans_tenant_demo ON cans (tenant_id, is_demo);

-- ============================================================================
-- 4. CAP (Corrective Action Plan)  (backend/app/models/can_cap.py)
--    CAPCreate/CAPUpdate/CAPResponse + CAPFormFields (FORM SMSM 8.8.2 closure
--    block, structured RCA and CAAN CAR-19 SRM data).
-- ============================================================================

CREATE TABLE caps (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cap_reference           TEXT NOT NULL,
    tenant_id               UUID NOT NULL,
    can_id                  UUID NOT NULL REFERENCES cans (id),

    action_plan             TEXT NOT NULL,
    timeline                TEXT NOT NULL,
    resources_required      TEXT,
    implementation_plan     TEXT,
    department              TEXT,
    target_completion_date  TIMESTAMPTZ NOT NULL,

    submitted_by            TEXT NOT NULL,
    submitted_by_uid        TEXT NOT NULL,
    submitted_at            TIMESTAMPTZ,
    status                  TEXT NOT NULL,
    reviewed_by             TEXT,
    reviewed_by_uid         TEXT,
    reviewed_at             TIMESTAMPTZ,
    review_comments         TEXT,
    revision_deadline       TIMESTAMPTZ,

    -- CAPFormFields - identification header
    company_name            TEXT,
    base_location           TEXT,
    area_system_of_interest TEXT,
    finding_number          TEXT,
    file_ref                TEXT,

    -- CAPFormFields - Section 5.1 analysis
    factual_review          TEXT,
    rca                     TEXT,
    short_term_ca           TEXT,
    long_term_ca            TEXT,
    implementation_timeline TEXT,

    -- CAPFormFields - sign-off blocks
    managerial_approval     JSONB,          -- {name, signature, date}
    caa_acceptance          JSONB,          -- {accepted, signature, date}

    -- CAPFormFields - residual risk / closure
    residual_severity       INT CHECK (residual_severity BETWEEN 1 AND 5),
    residual_probability    INT CHECK (residual_probability BETWEEN 1 AND 5),
    residual_risk_index     INT CHECK (residual_risk_index BETWEEN 1 AND 25),
    residual_risk_level     TEXT,
    residual_risk_outcome   TEXT,
    residual_tolerability_tier TEXT,
    residual_sra            JSONB,

    -- CAPFormFields - structured RCA (fishbone 6M / bow-tie CAR-19)
    root_causes             JSONB,          -- [{id, category, description, is_primary}]
    action_items            JSONB,          -- [{id, description, root_cause_id, owner, target_date}]
    rca_method              TEXT CHECK (rca_method IN ('bow_tie', 'fishbone')),
    sram_data               JSONB,          -- CAAN CAR-19 SRM block

    -- CAPFormFields - governance escalation + AE risk acceptance
    escalated_to_ae         BOOLEAN,
    escalated_by            TEXT,
    escalated_at            TIMESTAMPTZ,
    escalation_reason       TEXT,
    ae_signature            TEXT,
    ae_signed_at            TIMESTAMPTZ,
    ae_review_interval_days INT CHECK (ae_review_interval_days BETWEEN 1 AND 365),
    ae_review_date          TIMESTAMPTZ,

    -- CAPFormFields - closing block
    sag_sign                TEXT,
    sag_signed_by           TEXT,
    sag_signed_at           TIMESTAMPTZ,
    manager_approval        TEXT,
    ca_acceptance           TEXT,
    process_owner           TEXT,
    manager_confirmation    TEXT,
    closing_remarks         TEXT,
    closed_by               TEXT,
    closed_at               TIMESTAMPTZ,
    closed_signature        TEXT,

    is_demo                 BOOLEAN NOT NULL DEFAULT FALSE,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_caps_tenant_ref ON caps (tenant_id, cap_reference);
CREATE INDEX        ix_caps_tenant     ON caps (tenant_id);
CREATE INDEX        ix_caps_tenant_status ON caps (tenant_id, status);
CREATE INDEX        ix_caps_can        ON caps (tenant_id, can_id);
CREATE INDEX        idx_caps_tenant_demo ON caps (tenant_id, is_demo);

-- ============================================================================
-- 5. SURVEYS (scored)  (backend/app/routes/surveys.py - SurveySubmission)
--    Scored ICAO pillar output consumed by dashboards.
-- ============================================================================

CREATE TABLE surveys (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                UUID NOT NULL,

    submitted_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    respondent_id            TEXT,
    department               TEXT,
    employee_category        TEXT,
    years_experience         TEXT,
    language_used            TEXT,
    survey_version           TEXT NOT NULL,
    seed_version             TEXT,

    answers                  JSONB NOT NULL,
    question_scores          JSONB,
    element_scores           JSONB,

    safety_policy            INT CHECK (safety_policy BETWEEN 1 AND 5),
    safety_risk_management   INT CHECK (safety_risk_management BETWEEN 1 AND 5),
    safety_assurance         INT CHECK (safety_assurance BETWEEN 1 AND 5),
    safety_promotion         INT CHECK (safety_promotion BETWEEN 1 AND 5),
    overall_sms_maturity     INT CHECK (overall_sms_maturity BETWEEN 1 AND 5),
    overall_score_pct        NUMERIC(5, 2),

    is_demo                  BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ix_surveys_tenant        ON surveys (tenant_id);
CREATE INDEX ix_surveys_tenant_date   ON surveys (tenant_id, submitted_at);
CREATE INDEX ix_surveys_tenant_dept   ON surveys (tenant_id, department);
CREATE INDEX idx_surveys_tenant_demo  ON surveys (tenant_id, is_demo);

-- ============================================================================
-- 6. SURVEY RESPONSES (raw, for audit)
--    Raw answer payload persisted alongside each scored survey.
-- ============================================================================

CREATE TABLE survey_responses (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                UUID NOT NULL,

    respondent_id            TEXT,
    answers                  JSONB NOT NULL,
    department               TEXT,
    employee_category        TEXT,
    years_experience         TEXT,
    language_used            TEXT,
    submitted_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    survey_version           TEXT NOT NULL,

    is_demo                  BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ix_survey_responses_tenant      ON survey_responses (tenant_id);
CREATE INDEX ix_survey_responses_tenant_date ON survey_responses (tenant_id, submitted_at);
CREATE INDEX idx_survey_responses_tenant_demo ON survey_responses (tenant_id, is_demo);

-- ============================================================================
-- 7. CORRECTIVE ACTIONS  (backend/app/models/corrective_action.py)
-- ============================================================================

CREATE TABLE corrective_actions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,

    hazard_id               UUID REFERENCES hazards (id),
    can_id                  UUID REFERENCES cans (id),
    event_id                UUID,           -- polymorphic: report / diversion / deficiency event

    title                   TEXT NOT NULL,
    description             TEXT NOT NULL,
    action_plan             TEXT NOT NULL,
    priority                TEXT NOT NULL DEFAULT 'Medium' CHECK (priority IN ('High', 'Medium', 'Low')),

    assigned_to             TEXT,
    assigned_to_uid         TEXT,
    assigned_by             TEXT,
    assigned_at             TIMESTAMPTZ,
    target_completion_date  TIMESTAMPTZ,
    completed_at            TIMESTAMPTZ,

    reviewed_by             TEXT,
    reviewed_at             TIMESTAMPTZ,
    review_comments         TEXT,
    status                  TEXT NOT NULL,
    remarks                 TEXT,

    created_by              TEXT,
    updated_by              TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_corrective_actions_tenant        ON corrective_actions (tenant_id);
CREATE INDEX ix_corrective_actions_tenant_status ON corrective_actions (tenant_id, status);
CREATE INDEX ix_corrective_actions_tenant_assignee ON corrective_actions (tenant_id, assigned_to);
CREATE INDEX ix_corrective_actions_hazard        ON corrective_actions (tenant_id, hazard_id);
CREATE INDEX ix_corrective_actions_can           ON corrective_actions (tenant_id, can_id);

-- ============================================================================
-- 8. RISK REGISTER (per-hazard SRM)  (backend/app/models/risk_register.py)
-- ============================================================================

CREATE TABLE risk_register (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                UUID NOT NULL,
    hazard_id                UUID NOT NULL REFERENCES hazards (id),

    srm_date                 TIMESTAMPTZ NOT NULL,
    ultimate_consequence     TEXT NOT NULL,

    existing_severity        INT CHECK (existing_severity BETWEEN 1 AND 5),
    existing_probability     INT CHECK (existing_probability BETWEEN 1 AND 5),
    existing_risk_index      INT,
    existing_risk_tolerability TEXT,

    resultant_severity       INT CHECK (resultant_severity BETWEEN 1 AND 5),
    resultant_probability    INT CHECK (resultant_probability BETWEEN 1 AND 5),
    resultant_risk_index     INT,
    resultant_risk_tolerability TEXT,

    status                   TEXT NOT NULL,
    follow_up_date           TIMESTAMPTZ,
    date_completed           TIMESTAMPTZ,
    remarks                  TEXT,
    concerned_department     TEXT,

    created_by               TEXT,
    updated_by               TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_risk_register_tenant         ON risk_register (tenant_id);
CREATE INDEX ix_risk_register_tenant_status  ON risk_register (tenant_id, status);
CREATE INDEX ix_risk_register_tenant_hazard  ON risk_register (tenant_id, hazard_id);
CREATE INDEX ix_risk_register_tenant_srmdate ON risk_register (tenant_id, srm_date);

-- ============================================================================
-- 9. SAFETY DEFICIENCIES  (backend/app/models/safety_deficiency.py)
-- ============================================================================

CREATE TABLE safety_deficiencies (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,

    event_id            UUID,               -- polymorphic: report / diversion / hazard event
    source              TEXT NOT NULL,
    hazard_code         TEXT,
    description         TEXT NOT NULL,
    taxonomy_main       TEXT,
    taxonomy_type       TEXT,
    taxonomy_specific   TEXT,
    unsafe_event        TEXT,
    identified_hazard   TEXT,

    priority            TEXT CHECK (priority IN ('H', 'M', 'L')),
    severity            TEXT CHECK (severity IN ('Low', 'Medium', 'High', 'Critical')),

    assigned_to         TEXT,
    assigned_to_uid     TEXT,
    assigned_by         TEXT,
    assigned_at         TIMESTAMPTZ,
    follow_up_date      TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,

    status              TEXT NOT NULL,
    remarks             TEXT,
    csd_remarks         TEXT,

    created_by          TEXT,
    updated_by          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_safety_deficiencies_tenant        ON safety_deficiencies (tenant_id);
CREATE INDEX ix_safety_deficiencies_tenant_status ON safety_deficiencies (tenant_id, status);
CREATE INDEX ix_safety_deficiencies_tenant_assignee ON safety_deficiencies (tenant_id, assigned_to);

-- ============================================================================
-- 10. FLIGHT DIVERSIONS  (backend/app/models/flight_diversion.py)
-- ============================================================================

CREATE TABLE flight_diversions (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    diversion_id          TEXT NOT NULL,
    tenant_id             UUID NOT NULL,

    date                  TIMESTAMPTZ NOT NULL,
    flight_number         TEXT NOT NULL,
    aircraft_registration TEXT NOT NULL,
    sector_from           TEXT NOT NULL,
    sector_to             TEXT NOT NULL,
    diverted_to           TEXT NOT NULL,
    reason                TEXT NOT NULL,
    reason_details        TEXT,
    captain               TEXT,
    first_officer         TEXT,
    air_hostess           TEXT,
    description           TEXT NOT NULL,

    additional_fuel_cost  NUMERIC(12, 2),
    passenger_impact      INT,
    delay_minutes         INT,
    remarks               TEXT,

    status                TEXT NOT NULL,
    hazard_id             UUID REFERENCES hazards (id),
    hazard_link_url       TEXT,

    created_by            TEXT,
    updated_by            TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_flight_diversions_tenant_ref ON flight_diversions (tenant_id, diversion_id);
CREATE INDEX        ix_flight_diversions_tenant     ON flight_diversions (tenant_id);
CREATE INDEX        ix_flight_diversions_tenant_date ON flight_diversions (tenant_id, date);
CREATE INDEX        ix_flight_diversions_tenant_status ON flight_diversions (tenant_id, status);
CREATE INDEX        ix_flight_diversions_hazard     ON flight_diversions (tenant_id, hazard_id);

-- ============================================================================
-- 11. VERIFICATIONS (CAP effectiveness)  (backend/app/models/verification.py)
-- ============================================================================

CREATE TABLE verifications (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          UUID NOT NULL,
    hazard_id          UUID NOT NULL REFERENCES hazards (id),
    cap_id             UUID NOT NULL REFERENCES caps (id),

    outcome            TEXT NOT NULL,
    comments           TEXT,
    evidence           JSONB,              -- List[str]
    verified_by        TEXT NOT NULL,
    verified_by_uid    TEXT NOT NULL,
    verification_date  TIMESTAMPTZ NOT NULL,
    revision_deadline  TIMESTAMPTZ,
    revision_notes     TEXT,

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_verifications_tenant      ON verifications (tenant_id);
CREATE INDEX ix_verifications_tenant_date  ON verifications (tenant_id, verification_date);
CREATE INDEX ix_verifications_tenant_hazard ON verifications (tenant_id, hazard_id);
CREATE INDEX ix_verifications_tenant_cap   ON verifications (tenant_id, cap_id);

-- ============================================================================
-- 12. HAZARD CLOSURES  (backend/app/models/verification.py - ClosureResponse)
-- ============================================================================

CREATE TABLE closures (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL,
    hazard_id        UUID NOT NULL REFERENCES hazards (id),

    lessons_learned  TEXT,
    recommendations  TEXT,
    approval_notes   TEXT,
    approved_by      TEXT NOT NULL,
    approved_by_uid  TEXT NOT NULL,
    approved_at      TIMESTAMPTZ NOT NULL,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_closures_tenant      ON closures (tenant_id);
CREATE INDEX ix_closures_tenant_hazard ON closures (tenant_id, hazard_id);

-- ============================================================================
-- 13. STATE RISK REGISTER (SSP)  (backend/app/models/state_risk.py)
--     State-level / cross-operator aggregates. tenant_id is retained to honour
--     the uniform multi-tenant column contract (operator-specific snapshots).
-- ============================================================================

CREATE TABLE state_risk_register (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL,

    icoc_category         TEXT NOT NULL,
    description           TEXT NOT NULL,
    icao_reference        TEXT,
    current_risk_index    INT CHECK (current_risk_index BETWEEN 1 AND 25),
    tolerability          TEXT NOT NULL,
    tolerability_tier     TEXT,
    level                 TEXT,

    ssp_target            DOUBLE PRECISION,
    actual_ssp_value      DOUBLE PRECISION,
    risk_reduction_rate   DOUBLE PRECISION,
    trend                 TEXT NOT NULL,
    contributing_tenants  JSONB,           -- List[str]

    quarter               INT CHECK (quarter BETWEEN 1 AND 4),
    year                  INT,

    is_demo               BOOLEAN NOT NULL DEFAULT FALSE,

    updated_by            TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_state_risk_register_tenant ON state_risk_register (tenant_id);
CREATE INDEX ix_state_risk_register_tenant_period ON state_risk_register (tenant_id, year, quarter);
CREATE INDEX idx_state_risk_register_tenant_demo ON state_risk_register (tenant_id, is_demo);

-- ============================================================================
-- 14. PSOE ASSESSMENTS  (backend/app/models/psoe.py - PSOEAssessment)
--     CAAN Appendix 10 Audit & Surveillance assessments.
-- ============================================================================

CREATE TABLE psoe_assessments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,

    title               TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'draft',
    department          TEXT,
    scope               TEXT,
    auditor_name        TEXT,
    assessor_email      TEXT,
    assessment_date     TIMESTAMPTZ,
    template_version    TEXT NOT NULL,

    responses           JSONB NOT NULL,    -- List[PSOEAnswer]
    component_scores    JSONB,
    overall_score_pct   DOUBLE PRECISION,
    overall_level       TEXT,
    notes               TEXT,

    is_demo             BOOLEAN NOT NULL DEFAULT FALSE,

    created_by          TEXT,
    created_by_uid      TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_psoe_assessments_tenant      ON psoe_assessments (tenant_id);
CREATE INDEX ix_psoe_assessments_tenant_status ON psoe_assessments (tenant_id, status);
CREATE INDEX ix_psoe_assessments_tenant_date  ON psoe_assessments (tenant_id, assessment_date);
CREATE INDEX idx_psoe_assessments_tenant_demo  ON psoe_assessments (tenant_id, is_demo);

-- ============================================================================
-- 15. REGULATORY REPORTS (quarterly/annual SSP/SMS)  (backend/app/models/reporting.py)
--     Generated safety-management reports, distinct from operational VSR/MOR
--     `reports`.
-- ============================================================================

CREATE TABLE regulatory_reports (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL,

    report_type    TEXT NOT NULL CHECK (report_type IN ('quarterly', 'annual')),
    period         TEXT NOT NULL,
    year           INT NOT NULL,
    quarter        INT CHECK (quarter BETWEEN 1 AND 4),

    status         TEXT NOT NULL,
    summary        JSONB,
    data           JSONB,
    generated_at   TIMESTAMPTZ,
    generated_by   TEXT,
    file_url       TEXT,

    is_demo        BOOLEAN NOT NULL DEFAULT FALSE,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_regulatory_reports_tenant        ON regulatory_reports (tenant_id);
CREATE INDEX ix_regulatory_reports_tenant_status ON regulatory_reports (tenant_id, status);
CREATE INDEX ix_regulatory_reports_tenant_period ON regulatory_reports (tenant_id, report_type, year, quarter);
CREATE INDEX ix_regulatory_reports_tenant_created ON regulatory_reports (tenant_id, created_at);
CREATE INDEX idx_regulatory_reports_tenant_demo   ON regulatory_reports (tenant_id, is_demo);