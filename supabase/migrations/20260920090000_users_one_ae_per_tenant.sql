-- ============================================================================
-- RBAC — Phase 1: one Accountable Executive per tenant (P1-31)
-- ============================================================================
--   RBAC_MODEL.md §7: ACCOUNTABLE_EXECUTIVE is exclusive (one per tenant).
--   Partial unique index so the constraint applies only to AE rows and never
--   blocks other roles sharing a tenant.
--   Idempotent: safe to re-run (IF NOT EXISTS).
-- ============================================================================

CREATE UNIQUE INDEX IF NOT EXISTS ux_users_one_ae_per_tenant
    ON public.users (tenant_id)
    WHERE role = 'ACCOUNTABLE_EXECUTIVE';

COMMENT ON INDEX public.ux_users_one_ae_per_tenant
    IS 'RBAC §7: at most one ACCOUNTABLE_EXECUTIVE per tenant.';
