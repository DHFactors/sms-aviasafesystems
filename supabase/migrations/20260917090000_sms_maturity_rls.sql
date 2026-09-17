-- ============================================================================
-- D2: sms_maturity RLS enable (Module A)
-- ============================================================================
--   The ORM now adopts the live assessment shape; nothing changes on the live
--   table itself (it already exists). This migration only turns on Row Level
--   Security with the tenant-isolation policy used elsewhere (surveys /
--   survey_responses / sram_risk_register pattern), plus the matching grants.

ALTER TABLE public.sms_maturity ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_sms_maturity_tenant_isolation
    ON public.sms_maturity
    FOR ALL
    TO authenticated
    USING (tenant_id = ((auth.jwt() -> 'app_metadata'::text) ->> 'tenant_id'::text)::uuid)
    WITH CHECK (tenant_id = ((auth.jwt() -> 'app_metadata'::text) ->> 'tenant_id'::text)::uuid);

GRANT ALL ON TABLE public.sms_maturity TO anon, authenticated, service_role;