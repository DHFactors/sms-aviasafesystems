# B — Frontend Cleanup Report (Firestore removal)

**Scope:** Remove all Firestore client code from `public/`; keep Firebase Auth as the
only client dependency; replace direct Firestore reads with backend API calls only where an
equivalent endpoint exists. Delivered under STOP before C.

---

## 1. What changed (per file)

### 1.1 Firestore SDK loader — `public/js/firebase.js`
- Removed `databaseId: "sms-db"` from `PROD_CONFIG`.
- `loadFirebaseSDK()` no longer loads the Firestore compat SDK; its `onerror` branch for
  Firestore removed. Chain is now `app → auth → app-check → storage`.
- Removed `let db = null`, the entire **NAMED DATABASE BINDING** section
  (`getNamedFirestore`, `patchFirestoreFactory`, `_compatFirestoreFactory`, `_namedDbCache`),
  and the Firestore branch in `initServices()`. Auth-only service init, documented in a
  header comment.
- Auto-init block no longer assigns/nulls `window.db` in any `.then`/`.catch` path.
- `loadAuthCompatIfNeeded` unchanged (still needed — some pages load `firebase.js` before
  auth-compat finishes).

### 1.2 Orphaned portal tree — deleted `public/portal/dashboards/` (4 files)
- `safety.html`, `caan.html`, `dashboard.js`, `caan.js` — orphaned single-page app with no
  live links (only a comment header self-reference and an archived entry in
  `docs/archive/FILE_STRUCTURE.md`). `dashboard.js` contained the one Firestore read with no
  API equivalent (`getFirestore(app,"sms-db")` + `responses` collectionGroup query).

### 1.3 Tenant selector — `public/dashboard/sms-maturity.html`
- Removed `firebase-firestore-compat.js` script tag.
- Replaced the SUPER_ADMIN Firestore `tenants` read (L241) with
  `ApiClient.get('/api/v1/admin/tenants')` → `res.tenants`, mapped `{id, name, icao, surveyConfig}`
  (rows are keyed by tenant slug `id`). AIRLINE_ADMIN path unchanged.

### 1.4 CAAN maturity page — `public/dashboard/caan-sms-maturity.html`
- Removed `firebase-firestore-compat.js` script tag.
- Deleted `loadTenantMap()` and `loadLastSurveyDates()` (both Firestore reads:
  `collection('tenants')` and `collectionGroup('surveys')`).
- Operator display names now come from the CAAN-scoped
  `GET /api/v1/dashboard/caan/state` endpoint (`operators[].name`, keyed by `tenant_id`),
  with try/catch degrade to slug when unavailable.
- "Latest assessment" per operator now reads the server-provided `operator.assessment_date`
  from `GET /api/v1/dashboard/caan/survey-maturity` (see §1.7). Rendering logic in
  `renderOperatorCards` (ISO → `new Date(...).toLocaleDateString()`, else `—`) unchanged —
  no structural card changes.

### 1.5 Tenant validation — `public/js/tenant.js`
- `validateTenant` / `getTenantMetadata` rewired from
  `db.collection('tenants').doc(id).get()` to raw `fetch GET /api/v1/tenants/{id}` with an
  optional Firebase ID-token Bearer header.
- Self-contained (no dependency on `api/client.js`) — required because `report/vsr.html`
  loads `tenant.js` but NOT `api/client.js`.
- Explicit `tenantApi()` helper with `APP_CONFIG.apiBaseUrl → API_BASE_URL → Render URL`
  fallback and envelope unwrap (`data` when present).
- Lifecycle-inactive tenants rejected exactly like the legacy `active === false` check, via
  `status ∈ {INACTIVE, SUSPENDED, RETIRED, CANCELLED}` (the model's `active` boolean is not
  exposed by the API). Failure/timeout → treated as "not found" (invalid), preserving the
  legacy strict behavior.

### 1.6 Tenant context — `public/js/tenant_context.js`
- `resolveTenantTitle` rewired from the Firestore `profile/operational.tenant_name` +
  `tenants/{id}` reads to a single raw `fetch GET /api/v1/tenants/{tenant_id}/config`
  (public, auth-optional) → `data.name`, falling back to `prettifySlug`.
- **Documented data loss:** the curated `profile/operational.tenant_name` has no API
  equivalent; display title now derives from the tenant row `name`. Verified no other page
  depends on the curated field.

### 1.7 Backend exception (sole approval for B) — `backend/app/services/dashboard_service.py`
- `get_caan_survey_maturity()`: new `allowed: set` maintained always; after aggregation it
  hydrates each operator with `op["assessment_date"]` from
  `_latest_survey_assessment_dates(tenant_ids=allowed or None)`.
- New private helper `_latest_survey_assessment_dates()`:
  `SELECT tenant_id, MAX(submitted_at) FROM survey_responses WHERE is_demo = demo_scope()
   GROUP BY tenant_id`; uuid→slug via `tenant_slug`; optional set filter; returns
  `{slug: 'YYYY-MM-DD'}`; on any query failure returns `{}` (operators degrade to `—`).
- Nothing else in the endpoint, service, routes, or schemas touched.

### 1.8 Tag-only pages — removed `firebase-firestore-compat.js` (9 files)
`login.html`, `safety.html`, `administration.html`, `caan.html`, `caan-state-risk.html`,
`admin/login.html`, `report/mor.html`, `report/vsr.html`, `report/detail.html` — script tags
were loaded but unused (no Firestore code anywhere in these pages).

---

## 2. Grep verification (`public/`) — final state

Patterns: `firebase.firestore | getFirestore | initializeFirestore | firestore-compat |
getNamedFirestore | patchFirestoreFactory | databaseId | sms-db`

- **0 live references.** Remaining hits are comments only:
  - `js/firebase.js:178` — comment documenting the removed shim (intentional).
  - `js/aviasdcps-api.js` + `js/views/{home,occurrence,hazard,sdc,spis}.js` — `@target sms-db`
    JSDoc header comments; no Firestore code (these target the legacy SDK/API surface).
- Zero `window.db`, `.collection(`, `.firestore(`, `db =` references remain in `public/`.

---

## 3. Smoke results (all green)

### 3.1 Backend suite
`python -m pytest -p no:cacheprovider -q --tb=short` → **810 passed, 0 failed** in 12:18
(unchanged from A8 baseline; the `assessment_date` field is accessor-compatible with the
fixed tests in `test_state_risk.py` / `test_regulators.py`).

### 3.2 HTTP smoke (python -m http.server on `public/`)
All pages and the module files `firebase.js`/`tenant.js`/`tenant_context.js`/`api/client.js`
serve **200 OK**. (Note: the uvicorn backend does not mount StaticFiles — `public/` is hosted
separately — so page serving was verified via a static server.)

### 3.3 Headless browser console/network smoke (playwright-core + installed Chrome/Edge)
15 pages loaded, 9 s dwell, capturing console errors/warnings and network requests:
- **ALL CLEAN.** No `firestore`/`getFirestore`/`db`/`sms-db`/`window.db` console tokens; no
  requests to `firestore.googleapis.com` on any page.

**Observation (out of scope, pre-existing):** when the gstatic CDN is unreachable (this
offline sandbox), `firebase.js` logs `[AppCheck] Safe fallback activated; proceeding without
App Check: initializeAppCheck is not defined`. This is an intentional graceful-degradation
warning, unaffected by B and absent when the CDN is reachable. Escalate to a phase-F item if
you want the guard hardened.

---

## 4. Chat-decisions logged
- **Option 1 (delete portal/dashboards tree) + Option 2 (backend exception) both approved.**
- assessment_date source: per instruction, computed from `survey_responses.submitted_at`
  (MAX) — not a Firestore read.
- `_latest_survey_assessment_dates` uses `session_scope` (real DB) — unrelated to the
  `_survey_svc` fake `_DB()` monkeypatch. Fixed tests access `operators`/`by_id` keys only,
  so no test edits were required for B.
- `tenant.js` ship shape: self-contained raw fetch (not ApiClient) due to `vsr.html`.

## 5. STOP — awaiting approval to proceed to C
All B items implemented and verified. Next phase **C** begins only on approval; the repo
working tree (A+B combined, 68 files, +1229/−2299) remains uncommitted pending any commits
you request.