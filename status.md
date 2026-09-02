# Project Status

Last updated: 2026-09-02

## Objective
- Make the **Production Setup page** the super-admin's landing page after login, containing the full Steps 1–7 rollout flow, fully data-driven (no hardcoded tenants/regulators).
- Add per-kind **count inputs** to Step 5 (Dummy Data: VSR, MOR, CAN, CAP, Survey) so the super-admin can set the number seeded for each data type instead of using hardcoded counts.

## Key decisions (latest)
- Super-admin first page after login = **standalone `admin/production-setup.html`** (NOT `dashboard.html`, which defaults to Test Portal). All login redirects re-point to `/admin/production-setup.html`.
- Step 5 (Dummy Data) exposes per-kind **count fields** (VSR default 5, MOR 3, CAN 3, CAP 3, Survey 12) instead of a single hardcoded map. CAP count is clamped to the CAN count (FK — each CAP attaches to a CAN).
- `sms.aviasafesystems.com` is a **custom domain** on the single Firebase site `aerosafety-sms-prod`; it serves exactly what `firebase deploy --only hosting` publishes.
- Render free-tier cold-boots ~30–60s after ~15 min idle; login client timeout raised to 60s to tolerate this.
- `/archive` docs are forbidden reference — never reference/edit anything under `docs/archive/`.

## Complete
- **`admin/production-setup.html`** standalone Steps 1–7 landing page (Step 1 regulator, Step 2 tenants + bulk import + Detailed Wizard link, Step 4 audit log, Step 5 dummy-data seed/unseed, Step 6 PSOE, Step 7 state risk), focused header, step-progress chips, SUPER_ADMIN auth-gated.
- **Step 5 per-kind counts**:
  - Backend `admin_data_service.py`: `_resolve_seed_counts(kinds, counts)` resolves all five kinds from the request `counts` map (clamped 1–500, defaults on missing) and clamps `cap <= can`; `seed_tenant_demo_data(tenant_id, kinds, actor, counts=None)` generates the requested counts for each kind (CANs and CAPs honored separately).
  - Backend `routes/admin.py`: `DemoDataRequest` gained `counts: Optional[Dict[str, int]] = None`; `POST /demo-data` passes `counts=req.counts` on seed.
  - Frontend `production-setup.html` **and** `dashboard.html`: per-kind number inputs in Step 5 with `demoKindChanged()` to enable/disable each quantity, and `demoData()` sends `body.counts` on seed and shows per-kind quantities in the confirm dialog.
- **Redirects re-pointed**: `firebase.js` (`getRoleDestination`), `login.html` developer persona, `admin/login.html`, `admin/index.html`, `admin-credentials.js` `viewTenant()`, `tenant-credentials.html` header back-link, `dashboard.html` test-portal entry.
- **Login timeout**: `login.html` `LOGIN_TIMEOUT_MS` 12000 → 60000.
- **Cache fix**: firebase.json JS/CSS `Cache-Control` from `public, max-age=86400, immutable` → `public, max-age=3600`.
- **Deployed** to `aerosafety-sms-prod`; live-verified at `sms.aviasafesystems.com`.
- **Committed & pushed** (backend auto-deploys on push):
  - `d754cb3` Production Setup as super-admin landing
  - `fdaf938` login timeout raise
  - `3224aa5` hosting cache header fix

## Verification
- `python -m compileall -q app` — OK.
- `pytest tests/test_admin_seed.py` — **35 passed**.
- Inline JS in `production-setup.html` and `dashboard.html` — node `--check` OK.

## Active / Next
- Final commit + push of the Step 5 per-kind counts changes (backend service + route, frontend both pages), then `firebase deploy --only hosting` for the frontend.
- Confirm Render backend deploy via `/live` healthcheck after push.

## Relevant files
- `public/admin/production-setup.html` — Steps 1–7 landing page (Step 5 count inputs).
- `public/admin/dashboard.html` — supplementary Full Admin surface (mirrors Step 5 count inputs).
- `backend/app/services/admin_data_service.py` — `_resolve_seed_counts`, `seed_tenant_demo_data` counts, `unseed_tenant_demo_data`.
- `backend/app/routes/admin.py` — `DemoDataRequest.counts`, `POST /demo-data` passthrough.
- `backend/app/services/seed_surfaces.py` — PSOE baselines + state-risk reference.
- `backend/tests/test_admin_seed.py` — 35 tests.
- `docs/archive/` — do not reference or edit (all stale).
