-- ============================================================================
-- D4: tenants.safety_manager varchar -> jsonb
-- ============================================================================
--   Live column was `character varying` while the ORM and schema_init declare
--   JSONB (db_models.UUID Tenant.safety_manager / schema_init.py:132). All
--   consumers treat it as JSON (auth.py:38 safety_manager["email"].astext;
--   tenant_scheduler.py:272; tenant_credentials.py:185).
--
--   Data conversion:
--     NULL / empty   -> NULL::jsonb
--     '{' or '['     -> parsed JSON (object/array kept as-is)
--     bare text      -> {"name": "<text>"}   (Firestore-era plain string)
--
--   Rollback (down): ALTER TABLE public.tenants
--     ALTER COLUMN safety_manager TYPE varchar USING safety_manager::text;
-- ============================================================================

ALTER TABLE public.tenants
    ALTER COLUMN safety_manager TYPE JSONB USING CASE
        WHEN safety_manager IS NULL OR btrim(safety_manager) = '' THEN NULL::jsonb
        WHEN btrim(safety_manager) ~ '^[{\[]' THEN safety_manager::jsonb
        ELSE jsonb_build_object('name', safety_manager)
    END;