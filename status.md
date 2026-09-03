# Project Status

Last updated: 2026-09-04

## Objective
- **AviaSAFE SMS** production platform at `sms.aviasafesystems.com` (Firebase `aerosafety-sms-prod` + Render `aviasafe-unified-platform`) — single consolidated `sms-db` Firestore + Supabase Postgres.
- Super-admin landing = `admin/production-setup.html` (Steps 1–7 data-driven), executive = `dashboard/ae-dashboard.html` (minimalist), safety = `safety.html` (data-rich), all verified via live UAT. Platform cleanup consolidated.

## Key decisions (latest)
- **Platform cleanup 2026-09-04:** `dashboard.html` deprecated — `firebase.json` 301 `→ /admin/production-setup.html`, meta refresh + banner, `Full Admin` nav now `Production Setup — Active Admin`; governance toggle (`ACTIVE/SUSPENDED`) absorbed into `production-setup.html` lifecycle `Manage`.
- **AE redesign:** `ae-dashboard.html` rebuilt minimalist — hero + 4-chip situ banner + 3-card grid (PSOE big-score, Residual Exposure heatmap, Executive Decisions queue) + link to Safety Workspace; removed departmental matrix, velocity/trend charts, culture card, What-If simulator, detailed roster for uncluttered CEO view (410 lines vs 1600).
- **Safety verified:** `safety.html` untouched, remains dedicated robust workspace (master-register, risk-distribution, monthly-trends, hazard-frequency, actions-summary, recent reports) with department scoping — no executive overlap.
- **Routing:** SUPER_ADMIN → `/admin/production-setup.html`, CAAN_SMD → `/caan.html`, DEPT_ADMIN (camo/145/ops) → `/dashboard/responsible-manager.html`, AE (`ae@`) → `/dashboard/ae-dashboard.html`; `dashboard.html` no longer in active nav.
- `EmailStr` → `str` in `auth.py`, `firebase.js` deferred `registerAutoRecovery`, `?v=4.0.1` cache-bust, `is_demo` scoping fixed, unseed FK `CAPs→CANs→Reports/Surveys→Hazards`, UUID `uuid.UUID(_tid)` + `await flush`, user deletion `deleted:true` flat contract via `AdminUI.apiPost`.

## Complete
- **`public/admin/production-setup.html`** — Steps 1–7 + Existing Regulators/Tenants with `Manage` (demo/trial/active/suspended/retired/cancelled + from/to + setup-key modal + Dates column), User Management — Cleanup (filter, Delete via `POST /users/delete`), Audit Log, Dummy Data per-kind counts, PSOE, State Risk, confirm + lifecycle modals.
- **`public/admin/dashboard.html`** — deprecated: 301 redirect, banner, meta refresh, `Test Portal` retained as dev reference only.
- **`public/dashboard/ae-dashboard.html`** — minimalist executive (hero, banner, 3 cards, decision ledger, link to `safety.html`), retains `riskAcceptModal` + situational awareness.
- **`public/safety.html`** — verified data-rich, unchanged.
- **`public/js/firebase.js`** — `getRoleDestination` DEPT_ADMIN, safe auto-recovery.
- **`backend/app/routes/auth.py`** — `str` emails; **`middleware/auth.py`** — `ops→Flight Operations`; **`admin_data_service.py`** — expanded statuses + from/to + UUID/flush fixes; **`regulator_service.py`** — lifecycle + `update_regulator_status`; **`routes/admin.py`** — tenants/regulators status + users delete/list + psoe/state-risk.
- **Deployed** — `aerosafety-sms-prod` (firebase deploy, 175 files) + Render auto-deploy; `ea002dc` live.

## Verification
- `python -m py_compile` + `node --check public/js/firebase.js` — OK.
- `firebase.json` redirect `301 /admin/dashboard.html → /admin/production-setup.html` live; `production-setup.html` no longer links to deprecated dashboard.
- `ae-dashboard.html` minimalist renders 3 cards, no dept-matrix/simulator, passes `ae@fixedwing.com` auth gate.
- `safety.html` still serves master-register + risk charts, correctly scoped.
- `Phase 3 UAT` 26/27 PASS (1 expected 403), `POST /users/delete` → `{success:true, deleted:true}` flat.

## Active / Next
- Monitor executive feedback on minimalist AE — iterate if CEO needs additional KPIs.
- Keep `dashboard.html` file for 1 release then delete; no active links remain.
- Re-seed demo tenants via Step 5 after unseed wipe if needed.

## Relevant files
- `public/admin/production-setup.html` — active super-admin (lifecycle Manage + User Management).
- `public/admin/dashboard.html` — deprecated, 301 to production-setup.
- `public/dashboard/ae-dashboard.html` — minimalist executive (new).
- `public/safety.html` — dedicated safety workspace (unchanged).
- `public/js/firebase.js` + `public/js/api/client.js` + `firebase.json` (redirect + cache 3600).
- `backend/app/routes/admin.py` + `services/admin_data_service.py` + `services/regulator_service.py` + `middleware/auth.py`.
- `render.yaml` + `status.md` (this file).
