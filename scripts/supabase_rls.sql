-- ============================================================================
-- FILE: scripts/supabase_rls.sql
-- PURPOSE: Enable PostgreSQL Row-Level Security (RLS) on every table from
--          backend/app/db/schema.sql and enforce multi-tenant isolation.
--
-- POLICY EXPRESSION
--     Each row is visible / writable only when its `tenant_id` matches the
--     tenant embedded in the caller's Supabase JWT:
--         tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid
--
--     * USING   -> applies to SELECT / UPDATE / DELETE (row visibility)
--     * WITH CHECK -> applies to INSERT / UPDATE (row enforcement)
--
-- USAGE
--     Run against the Supabase database (SQL editor, or):
--         psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/supabase_rls.sql
--
-- NOTES
--     * The `service_role` key has BYPASSRLS and is unaffected by these
--       policies (server-side jobs / admin tooling keep full access).
--     * Users whose JWT has no app_metadata.tenant_id (or malformed uuid)
--       match zero rows -> default deny.
--     * See the OPTIONAL section at the bottom for cross-tenant regulator
--       access (CAAN_SMD / SUPER_ADMIN).
-- ============================================================================

-- ── 1. hazards ─────────────────────────────────────────────────────────────
ALTER TABLE hazards ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_hazards_tenant_isolation ON hazards;

CREATE POLICY p_hazards_tenant_isolation
    ON hazards
    AS PERMISSIVE
    FOR ALL
    TO authenticated
    USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid)
    WITH CHECK (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);

-- ── 2. reports (VSR / MOR) ─────────────────────────────────────────────────
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_reports_tenant_isolation ON reports;

CREATE POLICY p_reports_tenant_isolation
    ON reports
    AS PERMISSIVE
    FOR ALL
    TO authenticated
    USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid)
    WITH CHECK (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);

-- ── 3. cans ────────────────────────────────────────────────────────────────
ALTER TABLE cans ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_cans_tenant_isolation ON cans;

CREATE POLICY p_cans_tenant_isolation
    ON cans
    AS PERMISSIVE
    FOR ALL
    TO authenticated
    USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid)
    WITH CHECK (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);

-- ── 4. caps ────────────────────────────────────────────────────────────────
ALTER TABLE caps ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_caps_tenant_isolation ON caps;

CREATE POLICY p_caps_tenant_isolation
    ON caps
    AS PERMISSIVE
    FOR ALL
    TO authenticated
    USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid)
    WITH CHECK (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);

-- ── 5. surveys (scored) ────────────────────────────────────────────────────
ALTER TABLE surveys ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_surveys_tenant_isolation ON surveys;

CREATE POLICY p_surveys_tenant_isolation
    ON surveys
    AS PERMISSIVE
    FOR ALL
    TO authenticated
    USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid)
    WITH CHECK (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);

-- ── 6. survey_responses (raw audit) ────────────────────────────────────────
ALTER TABLE survey_responses ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_survey_responses_tenant_isolation ON survey_responses;

CREATE POLICY p_survey_responses_tenant_isolation
    ON survey_responses
    AS PERMISSIVE
    FOR ALL
    TO authenticated
    USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid)
    WITH CHECK (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);

-- ── 7. corrective_actions ──────────────────────────────────────────────────
ALTER TABLE corrective_actions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_corrective_actions_tenant_isolation ON corrective_actions;

CREATE POLICY p_corrective_actions_tenant_isolation
    ON corrective_actions
    AS PERMISSIVE
    FOR ALL
    TO authenticated
    USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid)
    WITH CHECK (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);

-- ── 8. risk_register ───────────────────────────────────────────────────────
ALTER TABLE risk_register ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_risk_register_tenant_isolation ON risk_register;

CREATE POLICY p_risk_register_tenant_isolation
    ON risk_register
    AS PERMISSIVE
    FOR ALL
    TO authenticated
    USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid)
    WITH CHECK (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);

-- ── 9. safety_deficiencies ─────────────────────────────────────────────────
ALTER TABLE safety_deficiencies ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_safety_deficiencies_tenant_isolation ON safety_deficiencies;

CREATE POLICY p_safety_deficiencies_tenant_isolation
    ON safety_deficiencies
    AS PERMISSIVE
    FOR ALL
    TO authenticated
    USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid)
    WITH CHECK (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);

-- ── 10. flight_diversions ──────────────────────────────────────────────────
ALTER TABLE flight_diversions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_flight_diversions_tenant_isolation ON flight_diversions;

CREATE POLICY p_flight_diversions_tenant_isolation
    ON flight_diversions
    AS PERMISSIVE
    FOR ALL
    TO authenticated
    USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid)
    WITH CHECK (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);

-- ── 11. verifications ──────────────────────────────────────────────────────
ALTER TABLE verifications ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_verifications_tenant_isolation ON verifications;

CREATE POLICY p_verifications_tenant_isolation
    ON verifications
    AS PERMISSIVE
    FOR ALL
    TO authenticated
    USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid)
    WITH CHECK (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);

-- ── 12. closures ───────────────────────────────────────────────────────────
ALTER TABLE closures ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_closures_tenant_isolation ON closures;

CREATE POLICY p_closures_tenant_isolation
    ON closures
    AS PERMISSIVE
    FOR ALL
    TO authenticated
    USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid)
    WITH CHECK (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);

-- ── 13. state_risk_register ────────────────────────────────────────────────
ALTER TABLE state_risk_register ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_state_risk_register_tenant_isolation ON state_risk_register;

CREATE POLICY p_state_risk_register_tenant_isolation
    ON state_risk_register
    AS PERMISSIVE
    FOR ALL
    TO authenticated
    USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid)
    WITH CHECK (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);

-- ── 14. psoe_assessments ───────────────────────────────────────────────────
ALTER TABLE psoe_assessments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_psoe_assessments_tenant_isolation ON psoe_assessments;

CREATE POLICY p_psoe_assessments_tenant_isolation
    ON psoe_assessments
    AS PERMISSIVE
    FOR ALL
    TO authenticated
    USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid)
    WITH CHECK (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);

-- ── 15. regulatory_reports (quarterly / annual) ────────────────────────────
ALTER TABLE regulatory_reports ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_regulatory_reports_tenant_isolation ON regulatory_reports;

CREATE POLICY p_regulatory_reports_tenant_isolation
    ON regulatory_reports
    AS PERMISSIVE
    FOR ALL
    TO authenticated
    USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid)
    WITH CHECK (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);

-- ============================================================================
-- OPTIONAL: CROSS-TENANT REGULATOR ACCESS
-- ----------------------------------------------------------------------------
-- The tenant-scoped policies above deny cross-tenant reads. The operational
-- regulator roles (CAAN_SMD, SUPER_ADMIN) are intended to view / write across
-- all operator tenants. If the JWT exposes the role in app_metadata, uncomment
-- a per-table override of the form:
--
--   CREATE POLICY p_hazards_cross_tenant
--       ON hazards
--       AS PERMISSIVE
--       FOR ALL
--       TO authenticated
--       USING ((auth.jwt() -> 'app_metadata' ->> 'role') IN ('CAAN_SMD', 'SUPER_ADMIN'))
--       WITH CHECK ((auth.jwt() -> 'app_metadata' ->> 'role') IN ('CAAN_SMD', 'SUPER_ADMIN'));
--
-- Repeat for every table above. Apply these only AFTER confirming the exact
-- key path ('role' vs 'roles') used during Firebase -> Supabase JWT claims
-- mapping. Until then the strict per-tenant isolation is the safe default.
-- ============================================================================