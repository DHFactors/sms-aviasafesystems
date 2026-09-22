-- ============================================================================
-- Module C — Phase 1: taxonomy_mappings reference table + seed (P1-23, SN-C8)
-- ============================================================================
--   Read-only, CAAN-owned ICAO <-> ADREP <-> HFACS <-> N-HRC mapping.
--   Seeded from data/icao_adrep_taxonomies.csv (15 ICAO/ADREP categories)
--   and public/data/hfacs_nanocodes.json (109 HFACS nanocodes) = 124 rows.
--   Idempotent: safe to re-run (IF NOT EXISTS / ON CONFLICT DO NOTHING).
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.taxonomy_mappings (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    icao_code      text,
    adrep_code     text,
    hfacs_nanocode text,
    nhrc_category  text,
    valid_from     timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- NULLS NOT DISTINCT so repeated seeds of the same (possibly NULL) code tuple
-- collapse to one row (PostgreSQL 15+).
CREATE UNIQUE INDEX IF NOT EXISTS ux_taxonomy_mappings_codes
    ON public.taxonomy_mappings (icao_code, adrep_code, hfacs_nanocode)
    NULLS NOT DISTINCT;
CREATE INDEX IF NOT EXISTS ix_taxonomy_mappings_icao
    ON public.taxonomy_mappings (icao_code);
CREATE INDEX IF NOT EXISTS ix_taxonomy_mappings_hfacs
    ON public.taxonomy_mappings (hfacs_nanocode);

-- Seed (read-only reference data).
INSERT INTO public.taxonomy_mappings
    (icao_code, adrep_code, hfacs_nanocode, nhrc_category)
VALUES
    ('LOC-I', 'LOC-I', NULL, 'LOC-I'),
    ('CFIT', 'CFIT', NULL, 'CFIT'),
    ('RE', 'RE', NULL, 'RE'),
    ('ARC', 'ARC', NULL, 'ARC'),
    ('SCF-PP', 'SCF-PP', NULL, NULL),
    ('SCF-NP', 'SCF-NP', NULL, NULL),
    ('F-POST', 'F-POST', NULL, NULL),
    ('F-NI', 'F-NI', NULL, NULL),
    ('RAMP', 'RAMP', NULL, NULL),
    ('WSTRW', 'WSTRW', NULL, NULL),
    ('SEC', 'SEC', NULL, NULL),
    ('GTOW', 'GTOW', NULL, NULL),
    ('NAV', 'NAV', NULL, NULL),
    ('BIRD', 'BIRD', NULL, 'WS'),
    ('UNK', 'UNK', NULL, NULL),
    (NULL, NULL, 'AE101', NULL),
    (NULL, NULL, 'AE102', NULL),
    (NULL, NULL, 'AE103', NULL),
    (NULL, NULL, 'AE104', NULL),
    (NULL, NULL, 'AE105', NULL),
    (NULL, NULL, 'AE107', NULL),
    (NULL, NULL, 'AE201', NULL),
    (NULL, NULL, 'AE202', NULL),
    (NULL, NULL, 'AE203', NULL),
    (NULL, NULL, 'AE205', NULL),
    (NULL, NULL, 'AE206', NULL),
    (NULL, NULL, 'AV001', NULL),
    (NULL, NULL, 'AV002', NULL),
    (NULL, NULL, 'AV003', NULL),
    (NULL, NULL, 'PE101', NULL),
    (NULL, NULL, 'PE103', NULL),
    (NULL, NULL, 'PE106', NULL),
    (NULL, NULL, 'PE108', NULL),
    (NULL, NULL, 'PE109', NULL),
    (NULL, NULL, 'PE110', NULL),
    (NULL, NULL, 'PE201', NULL),
    (NULL, NULL, 'PE202', NULL),
    (NULL, NULL, 'PE203', NULL),
    (NULL, NULL, 'PE204', NULL),
    (NULL, NULL, 'PE205', NULL),
    (NULL, NULL, 'PE206', NULL),
    (NULL, NULL, 'PE207', NULL),
    (NULL, NULL, 'PE208', NULL),
    (NULL, NULL, 'PC302', NULL),
    (NULL, NULL, 'PC304', NULL),
    (NULL, NULL, 'PC305', NULL),
    (NULL, NULL, 'PC307', NULL),
    (NULL, NULL, 'PC310', NULL),
    (NULL, NULL, 'PC311', NULL),
    (NULL, NULL, 'PC312', NULL),
    (NULL, NULL, 'PC314', NULL),
    (NULL, NULL, 'PC315', NULL),
    (NULL, NULL, 'PC317', NULL),
    (NULL, NULL, 'PC318', NULL),
    (NULL, NULL, 'PC319', NULL),
    (NULL, NULL, 'PC320', NULL),
    (NULL, NULL, 'PC202', NULL),
    (NULL, NULL, 'PC203', NULL),
    (NULL, NULL, 'PC204', NULL),
    (NULL, NULL, 'PC205', NULL),
    (NULL, NULL, 'PC206', NULL),
    (NULL, NULL, 'PC207', NULL),
    (NULL, NULL, 'PC208', NULL),
    (NULL, NULL, 'PC209', NULL),
    (NULL, NULL, 'PC215', NULL),
    (NULL, NULL, 'PC501', NULL),
    (NULL, NULL, 'PC502', NULL),
    (NULL, NULL, 'PC503', NULL),
    (NULL, NULL, 'PC504', NULL),
    (NULL, NULL, 'PC505', NULL),
    (NULL, NULL, 'PC507', NULL),
    (NULL, NULL, 'PC508', NULL),
    (NULL, NULL, 'PC511', NULL),
    (NULL, NULL, 'PC101', NULL),
    (NULL, NULL, 'PC102', NULL),
    (NULL, NULL, 'PC103', NULL),
    (NULL, NULL, 'PC104', NULL),
    (NULL, NULL, 'PC105', NULL),
    (NULL, NULL, 'PC106', NULL),
    (NULL, NULL, 'PC107', NULL),
    (NULL, NULL, 'PC108', NULL),
    (NULL, NULL, 'PC109', NULL),
    (NULL, NULL, 'PC110', NULL),
    (NULL, NULL, 'PP101', NULL),
    (NULL, NULL, 'PP103', NULL),
    (NULL, NULL, 'PP104', NULL),
    (NULL, NULL, 'PP105', NULL),
    (NULL, NULL, 'PP106', NULL),
    (NULL, NULL, 'PP107', NULL),
    (NULL, NULL, 'PP108', NULL),
    (NULL, NULL, 'PP109', NULL),
    (NULL, NULL, 'SV001', NULL),
    (NULL, NULL, 'SV002', NULL),
    (NULL, NULL, 'SV003', NULL),
    (NULL, NULL, 'SV004', NULL),
    (NULL, NULL, 'SP001', NULL),
    (NULL, NULL, 'SP002', NULL),
    (NULL, NULL, 'SP003', NULL),
    (NULL, NULL, 'SP006', NULL),
    (NULL, NULL, 'SP007', NULL),
    (NULL, NULL, 'SI001', NULL),
    (NULL, NULL, 'SI002', NULL),
    (NULL, NULL, 'SI003', NULL),
    (NULL, NULL, 'SI004', NULL),
    (NULL, NULL, 'SI005', NULL),
    (NULL, NULL, 'SI006', NULL),
    (NULL, NULL, 'SI007', NULL),
    (NULL, NULL, 'SI008', NULL),
    (NULL, NULL, 'OR001', NULL),
    (NULL, NULL, 'OR003', NULL),
    (NULL, NULL, 'OR005', NULL),
    (NULL, NULL, 'OR006', NULL),
    (NULL, NULL, 'OR008', NULL),
    (NULL, NULL, 'OR009', NULL),
    (NULL, NULL, 'OS001', NULL),
    (NULL, NULL, 'OS002', NULL),
    (NULL, NULL, 'OP001', NULL),
    (NULL, NULL, 'OP002', NULL),
    (NULL, NULL, 'OP003', NULL),
    (NULL, NULL, 'OP004', NULL),
    (NULL, NULL, 'OP005', NULL),
    (NULL, NULL, 'OP006', NULL),
    (NULL, NULL, 'OP007', NULL),
    (NULL, NULL, 'OC001', NULL)
ON CONFLICT DO NOTHING;

-- RLS: authenticated read (global reference) + CAAN/Super-Admin write.
ALTER TABLE public.taxonomy_mappings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_taxonomy_mappings_read ON public.taxonomy_mappings;
CREATE POLICY p_taxonomy_mappings_read ON public.taxonomy_mappings
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS p_taxonomy_mappings_cross_tenant ON public.taxonomy_mappings;
CREATE POLICY p_taxonomy_mappings_cross_tenant ON public.taxonomy_mappings
    FOR ALL TO authenticated
    USING (((auth.jwt() -> 'app_metadata'::text) ->> 'role'::text) IN ('CAAN_SMD', 'SUPER_ADMIN'))
    WITH CHECK (((auth.jwt() -> 'app_metadata'::text) ->> 'role'::text) IN ('CAAN_SMD', 'SUPER_ADMIN'));

GRANT ALL ON TABLE public.taxonomy_mappings TO anon, authenticated, service_role;
