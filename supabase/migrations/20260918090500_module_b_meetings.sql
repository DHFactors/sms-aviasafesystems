-- ============================================================================
-- Module B — Phase 1: SAG/SRB meetings + shared action items (P1-16/P1-17, SN16)
-- ============================================================================
--   sag_meetings  — Safety Action Group meeting record (§28.5)
--   srb_meetings  — Safety Review Board meeting record (§29.5, AE-chaired)
--   action_items  — shared SAG/SRB action items (meeting_type discriminator,
--                   polymorphic meeting_id)
--   Idempotent: safe to re-run (IF NOT EXISTS / guarded policy).
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.sag_meetings (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    scheduled_at    timestamptz,
    held_at         timestamptz,
    attendees       jsonb,
    minutes_ref     text,
    minutes_summary text,
    status          text NOT NULL DEFAULT 'Scheduled',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_sag_meetings_status
        CHECK (status IN ('Scheduled', 'Held', 'Cancelled'))
);
CREATE INDEX IF NOT EXISTS ix_sag_meetings_tenant
    ON public.sag_meetings (tenant_id);
CREATE INDEX IF NOT EXISTS ix_sag_meetings_tenant_scheduled
    ON public.sag_meetings (tenant_id, scheduled_at);

CREATE TABLE IF NOT EXISTS public.srb_meetings (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    scheduled_at    timestamptz,
    held_at         timestamptz,
    attendees       jsonb,
    minutes_ref     text,
    minutes_summary text,
    status          text NOT NULL DEFAULT 'Scheduled',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_srb_meetings_status
        CHECK (status IN ('Scheduled', 'Held', 'Cancelled'))
);
CREATE INDEX IF NOT EXISTS ix_srb_meetings_tenant
    ON public.srb_meetings (tenant_id);
CREATE INDEX IF NOT EXISTS ix_srb_meetings_tenant_scheduled
    ON public.srb_meetings (tenant_id, scheduled_at);

CREATE TABLE IF NOT EXISTS public.action_items (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    uuid NOT NULL,
    meeting_type text NOT NULL,
    meeting_id   uuid,
    hazard_id    uuid REFERENCES public.hazards (id) ON DELETE SET NULL,
    cap_id       uuid REFERENCES public.caps (id) ON DELETE SET NULL,
    assigned_to  text,
    due_date     timestamptz,
    status       text NOT NULL DEFAULT 'Open',
    notes        text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_action_items_meeting_type
        CHECK (meeting_type IN ('sag', 'srb'))
);
CREATE INDEX IF NOT EXISTS ix_action_items_tenant
    ON public.action_items (tenant_id);
CREATE INDEX IF NOT EXISTS ix_action_items_meeting
    ON public.action_items (meeting_type, meeting_id);
CREATE INDEX IF NOT EXISTS ix_action_items_tenant_status
    ON public.action_items (tenant_id, status);

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['sag_meetings', 'srb_meetings', 'action_items'] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', t);
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies WHERE schemaname = 'public'
              AND tablename = t AND policyname = 'p_' || t || '_tenant_isolation'
        ) THEN
            EXECUTE format(
                'CREATE POLICY %I ON public.%I TO authenticated ' ||
                'USING (tenant_id = ((auth.jwt() -> ''app_metadata''::text) ->> ''tenant_id''::text)::uuid) ' ||
                'WITH CHECK (tenant_id = ((auth.jwt() -> ''app_metadata''::text) ->> ''tenant_id''::text)::uuid);',
                'p_' || t || '_tenant_isolation', t
            );
        END IF;
        EXECUTE format('GRANT ALL ON TABLE public.%I TO anon, authenticated, service_role;', t);
    END LOOP;
END $$;
