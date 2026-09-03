# Project Status

Last updated: 2026-09-03

## Objective
- **AviaSAFE SMS** production platform at `sms.aviasafesystems.com` (Firebase `aerosafety-sms-prod` + Render `aviasafe-unified-platform`) — single consolidated `sms-db` Firestore + Supabase Postgres.
- Super-admin landing = `admin/production-setup.html` (Steps 1–7 data-driven), all operator / regulator / safety workflows verified via live UAT.

## Key decisions (latest)
- SUPER_ADMIN → `/admin/production-setup.html`, CAAN_SMD → `/caan.html`, DEPT_ADMIN (camo/145/ops) → `/dashboard/responsible-manager.html` (fixes Access Denied loop), AE (`ae@`) → `/dashboard/ae-dashboard.html`.
- `EmailStr` → `str` in `backend/app/routes/auth.py` (LoginCredentials + 3 models) — strict Pydantic validator blocked `ezondiza.dhf@gmail.com` etc.; validation now client-side + corporate service.
- `public/js/firebase.js` auto-recovery: deferred `registerAutoRecovery` (polls `firebase.apps.length`) — removed broken `onAuthStateChanged` monkey-patch that crashed `Firebase: No Firebase App [DEFAULT]`.
- Cache-busting `?v=4.0.1` on 41 HTML `firebase.js` includes; `firebase.json` JS/CSS `max-age=3600`.
- `is_demo` scoping: seeders write `is_demo` via `demo_scope()` (ENVIRONMENT), `master_register` filters same flag — mismatched ENVIRONMENT produced zeros; verified counts `fixedwing 10H/3CAN/3CAP` etc. exist with `is_demo=true`.
- Admin unseed FK order fixed to `CAPs → CANs → Reports/Surveys → Hazards`; `admin_data_service` UUID casting `uuid.UUID(_tid)` + `await session.flush()` for hazard→can FK.
- User deletion: `DELETE/POST /api/v1/admin/users` + `POST /users/delete` alias, SUPER_ADMIN+SETUP_SECRET, protected emails, audit `USER_DELETED`, frontend `POST /users/delete` via `AdminUI.apiPost` (avoids Firebase Hosting `/api` rewrite 404).
- Setup key UX: moved from header input to **confirm modal** (`#confirmModal` `#confirmSetupKeyWrap` + `#lifecycleModal`) — destructive actions (seed/unseed, PSOE, state-risk, user delete, lifecycle Manage) prompt inside warning modal, stored `sessionStorage`.
- Commercial lifecycle: `TENANT_STATUSES`/`REGULATOR_STATUSES` expanded to `demo,trial,active,suspended,retired,cancelled (+inactive)` with `from_date`/`to_date` top-level + `contract` aliases, `Manage` column + `lifecycleModal` on both Existing Tenants/Regulators tables.

## Complete
- **`public/admin/production-setup.html`** — Steps 1–7, Existing Regulators/Tenants with `Manage` (status + from/to + setup key), User Management — Cleanup (tenant filter, search, Delete), Audit Log, Dummy Data (per-kind counts), PSOE, State Risk, confirm + lifecycle modals with inline setup-key.
- **`public/js/firebase.js`** — `getRoleDestination` DEPT_ADMIN fix, safe auto-recovery defer, `DEMO` context, `isSafetyManagementRole`.
- **`backend/app/routes/auth.py`** — `EmailStr`→`str` (LoginCredentials, RegisterRequest, RegisterTenantRequest, JoinTeamRequest).
- **`backend/app/middleware/auth.py`** — `DEPARTMENT_SCOPE_PREFIXES` now `145→Part-145, camo→CAMO, ops→Flight Operations`.
- **`backend/app/services/admin_data_service.py`** — expanded tenant statuses, `from_date/to_date` handling, `update_tenant_status` commercial aliases, fixed seed UUID + flush, fixed unseed FK order (CAP→CAN→Reports/Surveys→Hazards) + Survey parent delete, per-kind counts.
- **`backend/app/services/regulator_service.py`** — expanded statuses, `_normalize_status`, `update_regulator_status` with from/to + contract sync.
- **`backend/app/routes/admin.py`** — `TenantStatusRequest` from/to, `POST /tenants/{id}/status` + new `POST /regulators/{id}/status` (SUPER_ADMIN+setup_key, audit `REGULATOR_STATUS_UPDATED`/`TENANT_STATUS_UPDATED`), `GET /users` + `DELETE /users` (robust body/query) + `POST /users/delete` with flat `{success:true, deleted:true, uid, email}` contract.
- **Seeders** — hazard/can/cap `register_tenant` UUID handling, `.test→.com` email migration.
- **Responsible Manager** `public/dashboard/responsible-manager.html` — skeleton shimmer during Render cold-boot, empty hidden until load, stats for Flight Ops.
- **Deployed** — `aerosafety-sms-prod` (`firebase deploy --only hosting`, 175 files) + Render `aviasafe-unified-platform` auto-deploy from `main`.

## Verification
- `python -m py_compile backend/app/routes/admin.py backend/app/services/admin_data_service.py` — OK; `node --check public/js/firebase.js` — OK.
- Live `POST /api/v1/admin/users/delete` 403→`Invalid setup key` explicit, 200→`{success:true, deleted:true, uid, email}` flat — frontend guard `!data.success || !data.deleted` passes, no “no confirmation” throw.
- Live `GET /api/v1/admin/users` SUPER_ADMIN 200 (openapi), `sms.aviasafesystems.com/js/firebase.js?v=4.0.1` live with `registerAutoRecovery` and DEPT_ADMIN routing.
- `Phase 3 UAT` live `26/27 PASS` (1 expected 403 CAAN), `GET /dashboard/master-register` with `ops@fixedwing.com` correctly scoped to `Flight Operations` via `user_department`.
- Seeded verification `python verify_demo_true.py` — `fixedwing is_demo=True: 10H/3CAN/3CAP` present; after `seed_tenant_demo_data` `vsr:15 mor:7 can:5 cap:3 survey:12` → `unseed` FK-safe.
- `pytest backend/tests/test_admin*` — green; `AdminUI.apiPost` correctly routes to Render `https://aviasafe-unified-platform.onrender.com`.

## Active / Next
- Monitor Render cold-boot (15min idle → 30–60s wake) with skeleton + 60s login timeout.
- Re-seed demo tenants via Step 5 after unseed wipe (currently all demo tables 0).
- Rotate `SETUP_SECRET` if leaked; keep `sessionStorage` per-tab isolation.

## Relevant files
- `public/admin/production-setup.html` — super-admin Steps 1–7 + Manage lifecycle + User Management + confirm/lifecycle modals (setup-key inline).
- `public/js/firebase.js` — init, `getRoleDestination`, `registerAutoRecovery`, `demo` mirroring.
- `public/js/api/client.js` — `ApiClient` with `API_BASE_URL` + tenant/department headers.
- `public/dashboard/responsible-manager.html` — department-scoped tasks, skeleton, `master-register` + `ApiClient`.
- `backend/app/routes/admin.py` — tenants/regulators lifecycle, demo-data seed/unseed, users list/delete, psoe/state-risk, audit.
- `backend/app/services/admin_data_service.py` — tenant lifecycle, demo data writer, FK-safe unseed, UUID handling.
- `backend/app/services/regulator_service.py` — regulator lifecycle, `update_regulator_status`.
- `backend/app/middleware/auth.py` — `get_department_scope` + `DEPARTMENT_SCOPE_PREFIXES`.
- `backend/app/services/master_register.py` — `_DEPARTMENT_ALIASES`, `normalize_department`, department/assignee filtering.
- `backend/app/routes/auth.py` — `str` email fields, login rate-limit.
- `backend/app/db/ids.py` — `tenant_uuid`/`register_tenant` deterministic UUID5.
- `firebase.json` — hosting `public`, rewrites, `Cache-Control: max-age=3600` for JS/CSS.
- `render.yaml` — Render backend service.
