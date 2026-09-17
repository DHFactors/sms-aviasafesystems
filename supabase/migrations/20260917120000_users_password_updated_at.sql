-- users.password_updated_at — observability for Firebase Auth password
-- rotation incidents (PASSWORD_RESET_BUG_INVESTIGATION.md, 2026-09-17).
--
-- The Admin SDK does not expose passwordUpdatedAt, so the value is captured at
-- password-set / reset time by tenant_credentials and written to the users
-- mirror row, then surfaced in the Super-Admin user list so any unexpected
-- batch rotation is visible and comparable across rows.
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS password_updated_at TIMESTAMPTZ;

COMMENT ON COLUMN public.users.password_updated_at IS
    'When the Firebase Auth password was last set/reset (mirror of Auth state)';