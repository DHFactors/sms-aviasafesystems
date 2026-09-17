# PASSWORD_RESET_BUG_INVESTIGATION.md

Investigation: "Passwords set during user creation by Super Admin (Production Setup Step 3)
become invalid within 1–2 minutes."

Date: 2026-09-17. Environment: `aerosafety-sms-prod` (Firebase) + Supabase PG (`postgres`).
Mode: read-only. No code or data was modified.

---

## 1. Executive summary

- There is **no scheduled job, worker, or cron** in the repo that resets Firebase Auth
  passwords (let alone on a 30s–3min interval). APScheduler runs only a weekly SSP dispatch
  and a monthly SRB dispatch; `render.yaml` defines no cron jobs.
- The Step-3 creation flow (`POST /api/v1/admin/users`) creates the Auth user, sets claims,
  mirrors the row to PG (`users`), and returns the password **once**. Nothing in that flow
  resets the password afterwards.
- The **only** code that resets an existing user's password inside the app is
  `reset_admin_password` / `send_welcome_email_for_tenant`, and both target **a single**
  tenant admin user (the first `AIRLINE_ADMIN`), not every tenant user.
- The batch provisioning path that once created all tenant users together
  (`create_tenant_with_credentials`) is now **not called by any route** (tests only) and, on
  an existing email, it returns `"email already exists"` **without rotating the password**.
- Live evidence shows the three `@sitaair.com.np` users had their passwords
  **batch-rotated at 2026-09-13 12:46:37–40 UTC (18:31:37–40 NPT)** — all three within ~3
  seconds, i.e. one process looping over the users. This rotation has **no corresponding
  audit_log entry**, which means it did **not** go through any app route. A minute later all
  three accounts were successfully logged into from the admin's IP. This matches a
  developer/UAT reset tool run (e.g. `seed/users.py` or `seed/reset_passwords.py`), not an
  automated bug.
- The reported example user `camo@sitaair.com.np` does **not exist** anywhere (not in PG
  `users`; not in Firebase Auth), and no user-creation event occurred on 2026-09-15/16/17.
  The "1–2 minutes" claim therefore cannot be reproduced from production data as-is.
- **Verdict: no in-repo code path silently rotates a freshly created user's password.**
  The observed rotation is batch-wide, triggered outside the audited app surface. The most
  probable real-world cause is a dev/ops tool (or the legacy batch path) being re-run over
  the tenant after Step-3 creation, replacing the passwords for all tenant users and thus
  invalidating the password that Step 3 had just displayed.

## 2. The reported bug

"Password set when creating a user via Super Admin Production Setup Step 3 becomes invalid
within 1–2 minutes (example: camo@sitaair.com.np)." The affected tenant is `sita-air`.

## 3. End-to-end user-creation flow (Production Setup Step 3)

1. UI: `public/admin/setup/step3-manage.html` → `createUserForm` →
   `AdminUI.apiPost('/api/v1/admin/users', …)`.
2. Route: `backend/app/routes/admin.py:2035` `admin_create_user`.
3. Service: `backend/app/services/tenant_credentials.py:208` `create_user_for_tenant`:……
4. `_create_auth_user` (`tenant_credentials.py:101`):
   - `auth.create_user(email, password, …)` — password from `u["password"] or generate_password()`;
   - `auth.update_user(uid, custom_claims={role, tenant_id, dept})`;
   - `upsert_user_doc` → PG `users` mirror row.
5. Tenant `users` array appended (`_patch_tenant`), best-effort welcome email.
6. Audit: `USER_CREATED` written to PG `audit_logs`.

The generated password is **never persisted** and is returned to the caller exactly once.
No step of this flow writes to the Firebase Auth user afterwards.

## 4. Scheduled jobs / workers / crons

- `backend/app/core/lifecycle.py`: APScheduler — weekly SSP dispatch (Mon 02:00 NPT) and
  monthly tenant SRB dispatch (1st 00:00 NPT). No short-interval jobs.
- Workers (`backend/app/workers/…`): `scheduler.py`, `tenant_scheduler.py`,
  `escalation_worker.py` (`check_overdue_cans`), `report_worker.py`. None touch Firebase
  Auth users or passwords.
- Cron endpoints (`backend/app/api/v1/cron.py`, `backend/app/routes/scheduled_jobs.py`,
  `check-overdue-caps`): task-key protected; dispatch/replay only. No user writes.
- `backend/app/middleware/tenant_status_cache.py`: 45s TTL tenant-status cache only.
- `render.yaml`: single web service; **no cron jobs**. `Dockerfile` runs only uvicorn.

## 5. Code paths that can overwrite Firebase Auth user state

All `auth.update_user(...)` / `delete_user(...)` writers (grep of `password=` +
`update_user`):

| Location | Operation |
|---|---|
| `app/firebase.py:132` | set custom claims |
| `app/routes/auth.py:180,518` | set custom claims / update user (claims) |
| `app/routes/auth.py:171,260,408` | self-service password change / register / reset |
| `app/routes/admin.py:230,311,385,757` | claims/update; `:1870,:1983` delete |
| `app/routes/admin.py:893-917` | `reset_admin_password` / welcome email — **single** admin user only |
| `app/services/admin_data_service.py:472,1733` | claims sync / delete |
| `app/services/tenant_credentials.py:111` | create (password at creation time) |
| `app/services/tenant_credentials.py:359,380` | reset **single** admin password |
| `seed/users.py:25,48` | `sync_password=True` re-syncs existing bootstrap users |
| `seed/reset_passwords.py:147` | CLI reset of demo-user specs |
| `seeders/tenants/tenant_seeder.py:238,326` | claims / delete |
| `scripts/reset_to_virgin.py:421` | deletes all Auth users (guard-gated, operator-only) |
| `scripts/legacy/simplify_credentials_DEPRECATED.py:142-150` | one account per tenant only |
| `scripts/legacy/fix_summit_air_user_DEPRECATED.py` | hardcoded single user (deprecated) |

**None of these loops over all of a tenant's users resetting passwords.** In particular
`tenant_credentials.py:150` (`user_results = [_create_auth_user(auth, u, tid) for u in users]`)
creates new users; on an existing email it returns `email already exists` and does **not**
update the password.

## 6. PG → Firebase sync jobs

None. `backend/app/services/users.py` mirrors **Auth → PG** only (`backfill_users_from_auth`,
`upsert_user_doc`). `sync_tenant_module_claims` (`admin_data_service.py:454-472`) reads PG
users and updates **claims only**, never passwords (triggered by tenant module toggles).

## 7. Live database findings (Supabase PG)

Connection: `postgresql://…@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres` (sslmode=require).

- **`users` table**: `camo@sitaair.com.np` **absent**. Four sita-air users, all created
  2026-09-13/14:
  - `safety@sitaair.com.np` (AIRLINE_ADMIN), `145@sitaair.com.np` (DEPT_ADMIN),
    `ae@sitaair.com.np` (AIRLINE_ADMIN), `scratch-20260914a@sitaair.com.np` (DEPT_ADMIN).
  - `last_login` is NULL for all four.
- **`audit_logs` (2026-09-13 → 09-14), relevant rows** (UTC):
  - `10:54:15` LOGIN super admin `ezondiza.dhf@gmail.com` (IP `113.199.226.75`)
  - `11:00:09` TENANT_CREATED `sita-air` (actor uid `hLXs4mvtf5bb1hRSifnh6HuUHpC2`)
  - `11:03:45` USER_CREATED `safety@sitaair.com.np`
  - `11:06:13` USER_CREATED `145@sitaair.com.np`
  - `11:07:25` USER_CREATED `ae@sitaair.com.np` (dept=Management) — superseded
  - `11:11:34`, `11:15:04` USER_DELETED (`Ox93GqwR…`, `J15VwE…`) — the first ae/145 pass
  - `12:23:02` USER_CREATED `ae@sitaair.com.np` again (dept=Executive)
  - `12:24:27` DEMO_DATA_UNSEED, `12:29:20` DEMO_DATA_SEED_12M (sita-air)
  - **`12:50:39`, `12:52:26`, `12:53:29` LOGIN `ae@`, `safety@`, `145@` — all SUCCESSFUL
    from `113.199.226.75`** — immediately after the password rotation (see §8)
  - `13:57:11` USER_CREATED `scratch-bug-test@…` → `13:57:16` USER_DELETED (IP `127.0.0.1`)
  - `2026-09-14`: overnight system jobs (`CAN_ESCALATED`, `CAP_OVERDUE`, `OVERDUE_CHECK_RUN`);
    `06:43:13-23` (02:43 NPT) LOGINs of scratch-gen/chars/edge users from `113.199.226.124`;
    `05:26:07` USER_CREATED `scratch-20260914a@`; `13:02:10` super-admin LOGIN.
  - **No `TENANT_PASSWORD_RESET` / `TENANT_WELCOME` / mass-reset action exists in the log**
    — the password rotation at `12:46:37` was **not** performed by any app route.
- **`dead_letter_queue`**: empty for the investigated window.
- **`tenants`**: `sita-air` present; users/audit metadata stored as documented.

## 8. Firebase Auth state (project aerosafety-sms-prod)

5 Auth users total. The three sita users (epoch ms → UTC / NPT):

| user | createdAt | passwordUpdatedAt | lastLoginAt |
|---|---|---|---|
| `safety@` | 11:03:38 UTC (16:48:38) | **12:46:37 UTC (18:31:37)** | 12:52:28 UTC (18:52:28) |
| `ae@` | 12:22:56 UTC (18:07:56) | **12:46:38 UTC (18:31:38)** | 12:50:40 UTC (18:50:40) |
| `145@` | 11:06:07 UTC (16:51:07) | **12:46:40 UTC (18:31:40)** | 12:53:30 UTC (18:53:30) |
| `scratch-20260914a@` | 05:26:01 UTC | == createdAt | none (never logged in) |
| super admin | 2026-08-26 | — | 2026-09-14 ~13:24 UTC |

**Smoking gun:** the three `passwordUpdatedAt` values are 1–2s apart → one process resettling
all three tenant users. ~4–7 minutes later all three logged in successfully from
`113.199.226.75` (the exactly matching audit LOGIN rows are in §7). The resettler knew the
new passwords → deliberate provisioning/verification action, performed **outside** the app
(no audit event). No `tokensValidAfterTime` / `validSince` is set on any sita user.

## 9. Correlation with the Single-Path policy change (2026-09-14)

- The "Single-Path" change is **uncommitted** (working-tree edits to
  `ROADMAP.md`, `tenant_credentials.py`, `tenant-credentials.html`, `admin-credentials.js`,
  `docs/status.md`, plus an unrelated in-flight PG/domain refactor in `db_models.py`,
  `schema_init.py`, `risk_calculator.py`, `sram_service.py`, `dashboard_service.py` …).
- In `tenant_credentials.py` the change is **documentation-only**: the header and the
  `create_tenant_with_credentials` docstring are updated to state that tenants are now
  created without Auth users and users are added one at a time (`create_user_for_tenant`,
  POST `/api/v1/admin/users`). **No Auth/password code changed.**
- `create_tenant_with_credentials` (the legacy batch path) is no longer called by any route
  (checked: only `tests/test_admin_credentials.py` references it). Even when it was live, it
  never rotated existing users' passwords (duplicate → error).
- The batch rotation in evidence occurred at `12:46 UTC` on **2026-09-13**, i.e. **before**
  the policy change was even dated (2026-09-14).
- **Conclusion: the Single-Path policy change is NOT the mechanism that invalidates
  passwords.** It neither introduces a deferred reset nor removes any audit trail. It should
  not be reverted; instead the operational discipline around reset/seeding tools needs to
  be tightened.

## 10. Hypotheses (ranked)

1. **Dev/ops batch reset over the tenant (most likely).** A local run of a reset/sync tool
   (e.g. `seed/users.py --sync`, `seed/reset_passwords.py`, or direct Admin-SDK loop) over
   the `sita-air` tenant re-rotated all tenant users' passwords. Any user created in Step 3
   (whose password was shown once) is silently invalidated the moment such a run completes —
   consistent with "works for a minute or two, then fails".
2. **Re-provision / re-create of the tenant** (delete + recreate via the legacy batch path or
   `reset_to_virgin` + seed) which regenerates passwords for every user, again invalidating
   Step-3-created users.
3. **The example user was created and then deleted** (seen twice in the audit: `ae@` created,
   deleted, re-created; `scratch-bug-test@` created at 13:57:11, deleted at 13:57:16).
   A "deleted" user logs in as "invalid password/not found" — this does not require any
   password mechanism at all.
4. **Self-service password change or Firebase admin reset** of the specific user by another
   actor (possible, but there is no record of `get_user_by_email`-style resets for camo).

**Timing note:** every observed password rotation is **batch-wide** (all tenant users,
seconds apart), not a 1–2-minute-delayed auto-reset of a single user. There is no repo
mechanism that would single out a freshly created user.

## 11. Recommended fixes

1. **Remove or fully gate the legacy batch path.** Delete `create_tenant_with_credentials`
   (or raise a permanent 404/403 unless an explicit operator env flag is set and audited).
   It is currently reachable only in tests; leaving it dormant invites re-enablement.
2. **Audit every Auth password mutation.** Add audit_log rows (e.g. `TENANT_PASSWORD_RESET`,
   `AUTH_BATCH_RESET`, `WELCOME_EMAIL`) in `reset_admin_password`, `send_welcome_email_for_tenant`,
   `seed/users.py`, `seed/reset_passwords.py`, and `tenant_seeder.py`. Today these write the
   new password to Firebase with **zero** audit trail — this is exactly why the 12:46 UTC
   rotation is invisible.
3. **No silent rotation guard.** In `_create_auth_user`/`create_user_for_tenant`, if the
   email already exists, do not touch the password (already true for `_create_auth_user`);
   add an explicit test asserting `passwordUpdatedAt` is unchanged on duplicate insert.
4. **Surface password freshness.** Store `password_updated_at` on the PG `users` mirror and
   show "last changed" in the admin user list, so any unexpected rotation is visible in the
   UI and comparable across rows.
5. **Ops confirmation (outside repo):** ask who/what rotated the three passwords at
   2026-09-13 12:46:37 UTC. Check for any scheduled task, CI,
   cron/launchd/Task-Scheduler, or laptop script that targets the prod Firebase project, and
   disable it for production. Any tool that sets deterministic passwords
   (e.g. `{TENANT}-{ROLE}-2026`) must never run against `aerosafety-sms-prod`.
6. **Reproduce under control:** in staging, create a user in Step 3, immediately read its
   Auth record (createdAt == passwordUpdatedAt), wait 5 min, re-read; then run seed sync /
   reset tool and confirm `passwordUpdatedAt` moves and the Step-3 password stops working —
   validating hypothesis 1 before any further code change.

## 12. Unknowns / open questions

- The exact tool/actor that rotated the three passwords at 2026-09-13 12:46:37–40 UTC is not
  identifiable from the repo (no audit event, no matching route). Requires operator/dev shell
  history and machine-level scheduled-task review.
- `camo@sitaair.com.np` cannot be traced (never existed in PG or Auth). The "1–2 minutes"
  figure is not corroborated by any timestamped passwordUpdatedAt delta ≈ 1–2 min for any
  existing user.
- Whether any long-running process is deployed outside this repo (other Render/EC2/CI worker
  or a local daemon) that calls the reset/seed functions against prod.
- Whether RLS on `audit_logs` (or the earlier role) hides some rows: the queries above ran as
  the pooler `postgres` role showing full 09-13/09-14 history; a per-tenant restricted role
  might see fewer rows, but this does not change §8's Auth-side evidence.