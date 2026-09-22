-- ============================================================================
-- Module C — Phase 1: RLS on existing Module C tables (P1-26 + P1-28)
-- ============================================================================
--   P1-26: ensure RLS is enabled + a policy exists on `caan_reports`
--          (text tenant_id) and `state_risk_categories` (global reference,
--          no tenant_id — authenticated read).
--   P1-28: cross-tenant CAAN_SMD / SUPER_ADMIN policy on the existing Module C
--          tables (`state_risk_register`, `regulatory_reports`) alongside their
--          existing per-tenant policies.
--   Idempotent: safe to re-run (guarded/rewritten policies).
-- ============================================================================

-- -- caan_reports (tenant_id is TEXT) ---------------------------------------
ALTER TABLE public.caan_reports ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_caan_reports_tenant_isolation ON public.caan_reports;
CREATE POLICY p_caan_reports_tenant_isolation ON public.caan_reports
    FOR ALL TO authenticated
    USING (tenant_id = ((auth.jwt() -> 'app_metadata'::text) ->> 'tenant_id'::text))
    WITH CHECK (tenant_id = ((auth.jwt() -> 'app_metadata'::text) ->> 'tenant_id'::text));

DROP POLICY IF EXISTS p_caan_reports_cross_tenant ON public.caan_reports;
CREATE POLICY p_caan_reports_cross_tenant ON public.caan_reports
    FOR ALL TO authenticated
    USING (((auth.jwt() -> 'app_metadata'::text) ->> 'role'::text) IN ('CAAN_SMD', 'SUPER_ADMIN'))
    WITH CHECK (((auth.jwt() -> 'app_metadata'::text) ->> 'role'::text) IN ('CAAN_SMD', 'SUPER_ADMIN'));

GRANT ALL ON TABLE public.caan_reports TO anon, authenticated, service_role;

-- -- state_risk_categories (global reference data, no tenant_id) -------------
ALTER TABLE public.state_risk_categories ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_state_risk_categories_read ON public.state_risk_categories;
CREATE POLICY p_state_risk_categories_read ON public.state_risk_categories
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS p_state_risk_categories_cross_tenant ON public.state_risk_categories;
CREATE POLICY p_state_risk_categories_cross_tenant ON public.state_risk_categories
    FOR ALL TO authenticated
    USING (((auth.jwt() -> 'app_metadata'::text) ->> 'role'::text) IN ('CAAN_SMD', 'SUPER_ADMIN'))
    WITH CHECK (((auth.jwt() -> 'app_metadata'::text) ->> 'role'::text) IN ('CAAN_SMD', 'SUPER_ADMIN'));

GRANT ALL ON TABLE public.state_risk_categories TO anon, authenticated, service_role;

-- -- P1-28: cross-tenant policy on state_risk_register / regulatory_reports --
DROP POLICY IF EXISTS p_state_risk_register_cross_tenant ON public.state_risk_register;
CREATE POLICY p_state_risk_register_cross_tenant ON public.state_risk_register
    FOR ALL TO authenticated
    USING (((auth.jwt() -> 'app_metadata'::text) ->> 'role'::text) IN ('CAAN_SMD', 'SUPER_ADMIN'))
    WITH CHECK (((auth.jwt() -> 'app_metadata'::text) ->> 'role'::text) IN ('CAAN_SMD', 'SUPER_ADMIN'));

DROP POLICY IF EXISTS p_regulatory_reports_cross_tenant ON public.regulatory_reports;
CREATE POLICY p_regulatory_reports_cross_tenant ON public.regulatory_reports
    FOR ALL TO authenticated
    USING (((auth.jwt() -> 'app_metadata'::text) ->> 'role'::text) IN ('CAAN_SMD', 'SUPER_ADMIN'))
    WITH CHECK (((auth.jwt() -> 'app_metadata'::text) ->> 'role'::text) IN ('CAAN_SMD', 'SUPER_ADMIN'));
