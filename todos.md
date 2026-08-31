# AviaSAFE — TODOs (next session)

## Completed
### "My Tasks" role-based visibility
- Hides the "My Tasks" button for safety-management roles (`safety@` prefix
  emails, or admin profiles); shows only for operational/departmental logins
  (`ops@`, `145`, responsible managers).
- Applied dynamically once authentication resolves
  (`firebase.auth().currentUser` email / claims check).
- Files touched: `public/css/main.css`, `public/js/firebase.js`
  (`initRoleClassToggle` / `isSafetyManagementRole`),
  `public/can_cap/caps.html`, `public/can_cap/cans.html`,
  `public/dashboard/master-register.html` (added `operational` class),
  `public/index.html` (tenant-query redirect added this session).

### Survey tenant query-param routing (landing page)
- `public/index.html` redirects to `/survey/?tenant=…` from the tenant query
  param so DEMO tenants (`buddha-air`, `yeti-airlines`) don't need hostnames.

### Survey status window validation
- `enforceSurveyWindow()` per-tenant window enforced; no code change was
  needed (verified only).

### Survey analytics aligned to Postgres (Path A) — 137 tests
- Root cause: `POST /api/v1/surveys/` persisted only to Postgres
  (`surveys` / `survey_responses`), while the dashboard survey aggregates
  read Firestore `collection_group("surveys"|"responses")` — so live
  submissions never surfaced on the dashboards.
- Fix: `backend/app/services/dashboard_service.py` now reads the PG
  `surveys` / `survey_responses` tables directly (`_survey_docs`,
  `_survey_responses`, `_PGSurveyDoc`, `_register_all_tenant_slugs`),
  scoped by `is_demo == demo_scope()` and `submitted_at` cutoff in SQL.
  Docstring in `backend/app/routes/surveys.py` corrected to describe PG
  persistence.
- Tests updated to patch the data-fetch methods for aggregation-focused
  coverage and added real-PG integration tests
  (`test_state_risk.py`, `test_regulators.py`). Verified: **137 passed**.

## Parked (not in current scope)
## 2. Survey hostname mapping
- `public/survey/app.js` `routes` still only maps `sita-air`, `nepal-airlines`,
  `caan-ops`.
- Decide: add `buddha-air` / `yeti-airlines` hostnames, or keep using
  `?tenant=buddha-air` / `?tenant=yeti-airlines` links.

## 3. Optional: per-employee survey issuance
- Employee-scoped collection: unique per-employee links or `respondentId` on
  top of the existing tenant-keyed storage/validation.

## Context refs
- Status report: `docs/PROJECT_STATUS_REPORT.md` (2026-08-30)
- "My Tasks" button grep: `public/**/[Mm]y.?[Tt]asks`
- Survey tenant resolution: `public/survey/app.js` `resolveTenantContext()`
- Backend surveys: `backend/app/routes/surveys.py`
- Survey dashboard PG source: `backend/app/services/dashboard_service.py`
- Cleanup script: `backend/scripts/cleanup_firestore_surveys.py`