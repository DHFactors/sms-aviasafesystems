# 📝 AviaSAFE SMS — Project Status Report

**Project**: AviaSAFE SMS — Safety Climate Measurement System (ICAO Annex 19 compliant)
**Report Date**: 2026-08-11
**Prepared by**: AviaSAFE Systems engineering (Opencode-assisted)
**Verification**: All figures below were verified live against the deployed backends (Render), frontend hostings (Firebase Hosting beta + prod), Firebase Auth, both Firestore databases, and the backend test suite on the report date.

---

## 1. Executive Summary

| Item | Value |
|------|-------|
| **Project Name** | AviaSAFE SMS |
| **Report Date** | 2026-08-11 |
| **Overall Status** | **RBAC credentials + State terminology refactor + SMSM 8.8.2 CAN/CAP form equivalence + official CAA CAP form (5.1(1)–5.1(5)) with A4 PDF export** — department-scoped role claims live in Auth, "National"→"State" rename completed, CAN/CAP forms now mirror FORM SMSM 8.8.2 / the CAA CAP document, and the CAP record exports as an A4 PDF |
| **Current Phase** | Beta Testing (pre-production) |

**Key Highlights**
- **CAN/CAP = SMSM 8.8.2 form equivalence (commit `5171d45`, deployed beta + prod)** — CAN issuance carries initial severity/probability/risk-index + classification; CAP submission carries RCA, residual-risk assessment and process owner; CAP review records CA acceptance and SAG sign-off. Dashboard "All Time" (`days=0`) date filter fixed for `/trends` + `/caan/trends` (previously returned 422).
- **Official CAA CAP form + A4 PDF export (commit `81fab62`)** — CAP schema extended with identification header (`company_name`, `base_location`, `area_system_of_interest`, `finding_number`, `file_ref`), Section 5.1(1)–5.1(5) analysis items (`factual_review`, `rca`, `short_term_ca`, `long_term_ca`, `implementation_timeline`) and `managerial_approval` / `caa_acceptance` sign-off dicts. `cap_submit.html` / `cap_review.html` rebuilt as the CAA document grid; `css/can-cap-print.css` renders the form as a clean A4 document via `window.print()` on `cap_review.html` and `can_detail.html`.
- **RBAC role mapping for the simplified credentials deployed live (2026-08-11)** — `safety@{tenant}.com` stays **AIRLINE_ADMIN**; `camo`/`145`/`ops@{tenant}.com` became **USER** accounts carrying a `department` custom claim (**CAMO / Part-145 / Flight Operations**) so they route to the Responsible Manager dashboard. **28 accounts updated in Firebase Auth** and the `users` collection re-synced (**51 docs**) in both `sms-db-beta` and `sms-db`.
- **Super-Admin tenant lifecycle status management** — new `POST /api/v1/admin/tenants/{id}/status` endpoint + production-setup UI: status (Trial/Active/Inactive) either set explicitly or derived from contract dates + payment status; audit-logged.
- **Super-Admin dummy-data seed/unseed tooling** — `POST /api/v1/admin/demo-data` seeds/unseeds VSR/MOR/CAN/CAP demo docs (tagged `admin-demo-1`); unseed deletes only demo-tagged docs and never touches real data.
- **"National" → "State" terminology + API-contract refactor** — global rename (UI, JS identifiers, `data.national` → `data.state`, services, tests, docs) with a recursive contract guard; cross-tenant reporting now scopes via `_effective_tenant()` (CAAN_SMD/SUPER_ADMIN default to state scope, explicit `tenant_id` overrides).
- **CAAN state-regulator tenant** — `seed/operators.create_caan_tenant()` creates the `tenants/caan` state-regulator doc in the full-seed flow; `DEMO_USERS` consolidated to a single `smd-caan-001` bound to `tenant_id="caan"`.
- **Backend suite green** — **231 backend tests passing** (re-verified after the CAP schema changes).

**Key Risks**
- **No SUPER_ADMIN account** — after removing `super-admin-001`, provisioning/seed routes (`/api/v1/admin/*`) require promoting a CAAN_SMD account to `SUPER_ADMIN`. Until then those routes are unusable.
- **Production seeding deferred to go-live** — `sms-db` still has 0 tenants / 0 operational data (by design); tenants/users must be created post-contract.
- **Frontend hosting deploy pending for the CAA form/PDF release** — the CAN/CAP 8.8.2 + `days=0` release (`5171d45`) is live on both hostings, but commit `81fab62` (CAA CAP form + A4 PDF export) reaches Firebase Hosting beta + prod only after `firebase deploy`.
- **Monitoring & alerts not yet configured** — no dashboards/alerting on the Render backends or Firebase project.

---

## 2. System Overview

- **Application Purpose**: ICAO Annex 19, Doc 9859 (Safety Management Manual) and Doc 10951 (Safety Intelligence Manual) aligned SMS platform for airlines, regulators, and aviation organizations. Measures SMS maturity, identifies hazards, assesses/mitigates risks, and turns safety data into safety intelligence.
- **Current Phase**: Beta Testing / Pre-Production
- **Target Audience**: Airlines (7 operators), Regulators (CAAN), MROs, Aerodromes

**Key Modules**
| Module | Focus |
|--------|-------|
| Module 1: SMS Maturity Assessment | Bilingual gap-analysis survey, survey lifecycle (open/close), per-tenant config, state aggregation |
| Module 2: Hazard / Risk Monitoring | Hazard register, auto-hazard creation from reports **and flight diversions**, risk matrix, trends, state regulator dashboard, escalation |
| Module 3: Risk Management (CAN/CAP) | Corrective action / preventive action register, review workflow, escalation to Escalated/Overdue |
| Module 4: Department & Role Workflows | Department-scoped assignments, Master Register, Responsible Manager ("My Tasks") |

---

## 3. Infrastructure Status

### 3.1 Hosting & Deployment

| Environment | URL | Status | Notes |
|-------------|-----|--------|-------|
| **Beta Frontend** | `https://sms-beta.web.app` | ✅ Live (200) | Firebase Hosting, site `sms-beta`, project `gap-analysis-ssp` |
| **Beta Backend** | `https://sms-aviasafesystems-beta.onrender.com` | ✅ Live (200) | Render service, `FIREBASE_DATABASE_ID=sms-db-beta`, auto-deploy on push |
| **Production Frontend** | `https://sms.aviasafesystems.com` | ✅ Live (200) | Firebase Hosting, site `aerosafety-sms-prod`, project `aerosafety-sms-prod` |
| **Production Backend** | `https://aviasafe-unified-platform.onrender.com` | ✅ Live (200) | Render service, `FIREBASE_DATABASE_ID=sms-db` (via `backend/render.yaml`) |

Both hostings serve the same `public/` directory. Frontend routing (`public/js/firebase.js`) selects the beta backend/database by hostname containing `beta`.

**Changes since last report (2026-08-10):** alongside the RBAC/State work, two CAN/CAP releases landed today:
1. **`5171d45` — SMSM 8.8.2 CAN/CAP form equivalence + dashboard `days=0` filter fix** — **deployed to Firebase Hosting beta + prod** (both returned HTTP 200).
2. **`81fab62` — official CAA CAP form structure 5.1(1)–5.1(5) + A4 PDF export stylesheet** — committed + pushed to `main` (Render backend auto-deploys on push); Firebase Hosting beta + prod deploy **pending as of this report**.

### 3.2 Databases (Firestore native)

| Database | Environment | PITR | Tenants | Users | Data Count | Status |
|----------|-------------|------|---------|-------|------------|--------|
| `sms-db` | Production | ✅ 7-day | 0 | **51** | 0 tenants / 0 surveys / 0 hazards / 0 reports | ✅ Go-live ready (clean slate) |
| `sms-db-beta` | Beta | ✅ 7-day | 7 | **51** | 1,033 surveys · 980 reports · 42 hazards · 3 CAN/CAP | ✅ Fully seeded |

> **2026-08-11 change:** the 28 simplified role accounts were **re-claimed** in Firebase Auth (shared beta + prod) via
> `simplify_credentials.py --apply` — `safety` kept AIRLINE_ADMIN; `camo`/`145`/`ops` switched to USER with a
> `department` claim. `users` re-synced to **51 docs** in both databases via `backfill_users_from_auth`.

### 3.3 Scheduled Jobs

| Job | Schedule | Endpoint | Auth | Status |
|-----|----------|----------|------|--------|
| **`check-overdue`** (Cloud Scheduler) | `0 0 * * *` (daily 00:00 UTC) | `POST /api/v1/admin/tasks/check-overdue` | `X-Task-Key` header (matches `TASK_API_KEY`) | ✅ Created, ENABLED, manual run verified (HTTP 200) |

### 3.4 Third-Party Services

| Service | Purpose | Status |
|---------|---------|--------|
| **Firebase Auth** | Authentication (email + custom claims: AIRLINE_ADMIN, CAAN_SMD, SUPER_ADMIN, USER) | ✅ Active (51 accounts) |
| **Upstash Redis** | Rate limiting (beta only; `REDIS_URL` set on beta service) | ✅ Active (beta) |
| **Gemini AI** | SMS maturity scoring / recommendations | ✅ Configured (key in env) |
| **Sender.net** | Contact form subscriber capture | ✅ Active — key set on both beta + prod Render services |

---

## 4. Development Status

### 4.1 Completed This Period (2026-08-11)

| Feature | Module | Status | Deployed |
|---------|--------|--------|----------|
| RBAC role mapping for simplified credentials (`safety`=AIRLINE_ADMIN; `camo`/`145`/`ops`=USER + `department` claim) | Auth | ✅ Complete | Auth (shared beta + prod) + `users` (both DBs) |
| `simplify_credentials.py` claim-sync (dry-run + apply) — 28 accounts updated, 51 users backfilled | Tooling | ✅ Complete | Auth + Firestore (live) |
| Tenant lifecycle status endpoint `POST /api/v1/admin/tenants/{id}/status` (Trial/Active/Inactive, contract dates, payment) | Admin | ✅ Complete | Repo (Render auto-deploy on push) |
| Demo-data seed/unseed endpoint `POST /api/v1/admin/demo-data` (VSR/MOR/CAN/CAP, `admin-demo-1` tagged, safe unseed) | Admin | ✅ Complete | Repo (Render auto-deploy on push) |
| `admin_data_service.py` + audit logging (`TENANT_STATUS_UPDATED`, `DEMO_DATA_SEED/UNSEED`) | Admin | ✅ Complete | Repo |
| Production-setup UI: tenant Status badge + Manage form + Dummy Data card (Step 5) | Admin | ✅ Complete | Repo (pending hosting deploy) |
| "National" → "State" terminology + API-contract refactor (`data.state`, `_effective_tenant()`, recursive guard) | Reporting / State Risk | ✅ Complete | Repo (pending hosting deploy) |
| CAAN state-regulator tenant doc (`create_caan_tenant`, `SEED_VERSION 1.2.0`, `smd-caan-001`) | Seeding | ✅ Complete | Repo |
| CAN issuance = SMSM 8.8.2 (severity/probability/risk-index, classification, reference) + CAP submission = SMSM 8.8.2 (cause/effect, RCA, residual-risk, process owner) — `5171d45` | CAN/CAP | ✅ Complete | ✅ Beta + Prod hosting (live) |
| CAP review = SMSM 8.8.2 (CA acceptance, SAG sign-off, status flow, corrective/preventive classification) — `5171d45` | CAN/CAP | ✅ Complete | ✅ Beta + Prod hosting (live) |
| Dashboard date-filter fix — `days=0` = "All Time" for `/trends` + `/caan/trends` (was returning 422) — `5171d45` | Dashboard | ✅ Complete | ✅ Beta + Prod hosting (live) |
| Official CAA CAP form schema — identification header (`company_name`, `base_location`, `area_system_of_interest`, `finding_number`, `file_ref`), Section 5.1(1)–5.1(5) (`factual_review`, `rca`, `short_term_ca`, `long_term_ca`, `implementation_timeline`), `managerial_approval` + `caa_acceptance` sign-off dicts — `81fab62` | CAN/CAP | ✅ Complete | ⏳ Hosting deploy pending (backend auto-deployed) |
| A4 PDF export — `css/can-cap-print.css` (`@media print`, A4 page, form-grid borders, chrome stripped) + "Download / Export PDF" buttons on `cap_review.html`/`can_detail.html` wired to `window.print()` — `81fab62` | CAN/CAP | ✅ Complete | ⏳ Hosting deploy pending |
| `tests/test_rbac_claims.py` + `tests/test_reporting_scoping.py` + 18 new admin tests | Testing | ✅ Complete | Repo |

### 4.2 Completed Features (prior)

See `docs/PROJECT_STATUS_REPORT_2026-08-10.md` §4 for the full inventory (simplified credential scheme creation, CAAN SUPER_ADMIN removal, hazard-source enforcement + diversion auto-hazard, SMS Maturity rename, department mapping, escalation, Master Register, Responsible Manager, survey, hazard register, risk matrix, trends, flight diversions, state regulator dashboard, CAN/CAP, admin panel, landing page, security & compliance).

---

## 5. Testing Status

### 5.1 Backend Tests — **231 passing** (all green, `python -m pytest tests/ -q`)

| Category | Test Count | Status |
|----------|------------|--------|
| Admin seed / tenant lifecycle / demo-data (`test_admin_seed.py`) | 38 | ✅ Passing |
| Super-Admin credentials (`test_admin_credentials.py`) | 17 | ✅ Passing |
| Regulator & State Risk (`test_state_risk.py` + `test_regulators.py` + `test_reporting_scoping.py`) | 51 | ✅ Passing |
| Risk Assessment & Lifecycle (`test_risk_assessment_lifecycle.py` + `test_risk_matrix.py` + `test_dashboard_risk_trends.py`) | 41 | ✅ Passing |
| RBAC credential claims (`test_rbac_claims.py`) | 9 | ✅ Passing |
| Surveys & Tenants (`test_surveys.py` + `test_tenants_config.py` + `test_tenants_users.py`) | 43 | ✅ Passing |
| Escalation & Master Register (`test_escalation_master_register.py`) | 7 | ✅ Passing |
| Metrics / Health / Contact / Feedback | 25 | ✅ Passing |
| **Total** | **231** | ✅ Passing |

**+36 since 2026-08-10:** 18 admin (tenant status derivation, update, demo seed/unseed, routes), 9 state-scoping (API contract + `_effective_tenant`), 9 RBAC claims. **Suite re-verified at 231 passing after the CAA CAP schema changes** (commit `81fab62`).

### 5.2 Frontend Tests — **4 passing**

| Category | Test Count | Status |
|----------|------------|--------|
| Dashboard Render Tests (`node frontend-tests/dashboard.test.js`, `npm test`) | 4 | ✅ Passing |

### 5.3 Live Verification (2026-08-11)

| Check | Result |
|-------|--------|
| `simplify_credentials.py --apply` (beta backfill) | ✅ 28/28 accounts updated, 51 users synced (`sms-db-beta`) |
| `simplify_credentials.py --apply --db sms-db` (prod backfill) | ✅ 28/28 accounts updated, 51 users synced (`sms-db`) |
| Auth claims applied | ✅ `safety`→`{"role":"AIRLINE_ADMIN","tenant_id":...}`; `camo`/`145`/`ops`→`{"role":"USER","tenant_id":...,"department":...}` |
| `users` collection sync | ✅ 51 docs in `sms-db-beta` + `sms-db` |
| No SUPER_ADMIN (`super-admin-001`) | ✅ Not present — nothing to remove |
| CAN/CAP = SMSM 8.8.2 release (`5171d45`) | ✅ Backend tests 231/231; hosted on beta + prod (HTTP 200) |
| CAA CAP form + PDF release (`81fab62`) | ✅ Backend tests 231/231; pushed to `main` (hosting deploy pending) |

---

## 6. Beta Testing Status

### 6.1 Beta Environment (`sms-db-beta`) — verified healthy today

| Aspect | Status | Details |
|--------|--------|---------|
| **Environment** | `sms-db-beta` | Fully seeded, PITR 7-day |
| **Tenants** | 7 | sita-air, buddha-air, tara-air, yeti-airlines, summit-air, simrik-air, air-dynasty |
| **Regulator** | 1 | caan (Nepal) — now a `tenants/caan` state-regulator doc |
| **Users** | 51 | 28 simplified role accounts + 21 legacy operator + 2 CAAN_SMD |
| **Surveys** | 1,033 | Seeded responses |
| **Hazards** | 42 | Clean seeded data (per tenant: 5–7) |
| **Reports** | 980 | Seeded VSR/MOR |
| **CAN/CAP** | 3 | Tara Air demo corrective actions |
| **Audit logs** | active | Escalation + tenant-status + demo-data writes to `audit_logs` |

### 6.2 Beta Access — Simplified Accounts (2026-08-11, RBAC roles)

| Role | Department | Email | Password | Status |
|------|-----------|-------|----------|--------|
| AIRLINE_ADMIN | Safety | safety@buddha-air.com | `BHA-Safety-2026` | ✅ Working |
| AIRLINE_ADMIN | Safety | safety@tara-air.com | `TARA-Safety-2026` | ✅ Working |
| USER | CAMO | camo@tara-air.com | `TARA-CAMO-2026` | ✅ Working → Responsible Manager |
| USER | Part-145 | 145@yeti-airlines.com | `YETI-145-2026` | ✅ Working → Responsible Manager |
| USER | Flight Operations | ops@air-dynasty.com | `DYNASTY-Ops-2026` | ✅ Working → Responsible Manager |
| CAAN_SMD | — | sms.inspector@caan.gov.np | shared seed | ✅ Working |
| CAAN_SMD | — | director.safety@caan.gov.np | shared seed | ✅ Working |
| ~~SUPER_ADMIN~~ | — | ~~safety.director@caan.gov.np~~ | — | ❌ Removed |

Full 28-account table: `credential.md` (§ Simplified Role Accounts). `camo`/`145`/`ops` route to `/dashboard/responsible-manager.html` via their `department` claim (`getRoleDestination`); `safety` routes to the full dashboard.

### 6.3 Beta Tester Onboarding

| Item | Status | Details |
|------|--------|---------|
| Invitation Template | ✅ Ready | `docs/BETA_INVITATION_TEMPLATE.md` |
| Tester Checklist | ✅ Ready | `docs/BETA_TEST_CHECKLIST.md` |
| Tester Accounts Reference | ✅ Ready | `docs/BETA_TESTERS.md` (updated 2026-08-10) |
| Feedback Form | ✅ Ready | Google Form integrated (see `docs/FEEDBACK_FORM_STRUCTURE.md`) |
| Testers Invited | ⏳ Pending | Sita Air, CAAN, Tara Air, Yeti Airlines |

---

## 7. Production Readiness

### 7.1 Production Environment (`sms-db`)

| Aspect | Status | Details |
|--------|--------|---------|
| **Environment** | `sms-db` | Clean slate — PITR 7-day |
| **Tenants** | 0 | Will be created post-contract |
| **Operational Data** | 0 | No surveys/hazards/reports/CAN-CAP |
| **Users** | 51 | Pre-provisioned accounts in `users` collection (28 simplified + legacy), claims current as of 2026-08-11 |
| **Backend** | ✅ Deployed | Latest code auto-deploys on push |
| **Frontend** | 🟡 Mostly live | CAN/CAP 8.8.2 + `days=0` release (`5171d45`) live on beta + prod; CAA form + PDF release (`81fab62`) pending `firebase deploy` |

### 7.2 Go-Live Checklist

| Item | Status | Details |
|------|--------|---------|
| Production Domain | ✅ Configured | `sms.aviasafesystems.com` |
| SSL Certificate | ✅ Valid | Firebase Hosting managed (Let's Encrypt) |
| Backend | ✅ Deployed | Render auto-deploy |
| Frontend | ⏳ Deploy pending | CAA CAP form + PDF export release (`81fab62`) on `firebase deploy` |
| Database | ✅ Ready | Clean slate, PITR 7-day |
| Rate Limiting | ✅ Configured | IP-based, 60 req/min per IP (configurable) |
| Scheduled escalation job | ✅ Configured | Cloud Scheduler `check-overdue`, daily 00:00 UTC |
| `TASK_API_KEY` | ✅ Set | Both prod + beta Render services |
| PITR | ✅ Enabled | 7-day retention (verified) |
| **SUPER_ADMIN account** | ⚠️ **Action** | **Removed 2026-08-10 — promote a CAAN_SMD before admin routes are needed** |
| Monitoring | ⏳ Pending | To be configured |
| Alerts | ⏳ Pending | To be configured |

### 7.3 Production Seeding

| Item | Status | Details |
|------|--------|---------|
| Regulator Creation | ⏳ Pending | Will be done at go-live |
| Tenant Creation | ⏳ Pending | Will be done post-contract |
| User Creation | ⏳ Pending | Will be done post-contract |
| Data Seeding | ⏳ Pending | Will be done post-contract |

---

## 8. Documentation Status

### 8.1 Technical Documentation

| Document | Status | Location |
|----------|--------|----------|
| Architecture Overview | ✅ Complete | `docs/ARCHITECTURE.md` |
| API Documentation | ✅ Updated 2026-08-11 | `docs/API.md` (State terminology + CAP payload schema / CAA form fields) |
| Security Guide | ✅ Complete | `docs/SECURITY.md` |
| Deployment Guide | ✅ Complete | `docs/DEPLOYMENT.md` |
| Operations Guide | ✅ Complete | `docs/OPERATIONS.md` |
| User Flow | ✅ Complete | `docs/USER_FLOW.md` |
| Known Limitations | ✅ Complete | `docs/KNOWN_LIMITATIONS.md` |
| Manual Verification Checklist | ✅ Updated 2026-08-11 | `manual_verification.md` (231 passing; RBAC + State checks) |
| Beta Testers Reference | ✅ Updated 2026-08-10 | `docs/BETA_TESTERS.md` |
| Credential Reference | ✅ Updated 2026-08-10 | `credential.md` (local-only, gitignored) |

### 8.2 Archived Documentation

| Document | Status | Location |
|----------|--------|----------|
| Status Report 05 Aug 2026 | ✅ Archived | `docs/archive/PROJECT_STATUS_REPORT_05AUG2026.md` |
| Status Report 07 Aug 2026 | ✅ In place | `docs/PROJECT_STATUS_REPORT_2026-08-07.md` |
| Status Report 08 Aug 2026 | ✅ In place | `docs/PROJECT_STATUS_REPORT_2026-08-08.md` |
| Status Report 10 Aug 2026 | ✅ In place | `docs/PROJECT_STATUS_REPORT_2026-08-10.md` |
| Status Report 11 Aug 2026 | ✅ This report | `docs/PROJECT_STATUS_REPORT_2026-08-11.md` |

---

## 9. Known Issues & Limitations

| # | Issue | Severity | Status | Notes |
|---|-------|----------|--------|-------|
| 1 | Survey rate limit (5/day/tenant) | Low | ✅ Configurable | Adjustable via dashboard (options 5/10/25/50/100) |
| 2 | **No SUPER_ADMIN account** | High | ⚠️ Action | Removed 2026-08-10; promote a CAAN_SMD to restore admin routes |
| 3 | Sender.net domain verification | Low | ⚠️ Pending | Free-plan limitation; sending domain not yet verified |
| 4 | Production has no operational data | N/A | ✅ Intentional | Clean slate for go-live (51 user accounts present) |
| 5 | Frontend hosting deploy pending for the CAA form/PDF release | Low | ⚠️ Pending | `firebase deploy` beta + prod for `81fab62` (CAN/CAP 8.8.2 + `days=0` release already live) |
| 6 | Monitoring / alerting | Medium | ⚠️ Pending | Not yet configured |
| 7 | MFA (TOTP/SMS) | Medium | ⚠️ Pending | Not yet implemented |
| 8 | Legacy/orphaned dashboard pages | Low | ⚠️ Known | `public/dashboard/index.html`, `public/portal/*` not linked from nav |

---

## 10. Next Steps & Milestones

| # | Milestone | Target Date | Status |
|---|-----------|-------------|--------|
| 1 | **Restore SUPER_ADMIN** (promote a CAAN_SMD account) | Immediate | ⚠️ Action |
| 2 | Deploy frontend hosting (CAA CAP form + PDF export release `81fab62`) | Immediate | ⏳ Pending |
| 3 | Distribute simplified credentials to beta testers | Immediate | ⏳ Pending |
| 4 | Invite beta testers (Sita Air, CAAN, Tara Air, Yeti) | Immediate | ⏳ Pending |
| 5 | Beta Launch | TBD | ⏳ Pending |
| 6 | Beta Testing Period | 2 weeks (post-launch) | ⏳ Pending |
| 7 | Feedback Collection | During beta | ⏳ Pending |
| 8 | Production Go-Live | Post-beta | ⏳ Pending |
| 9 | Post-Launch Monitoring | Ongoing | ⏳ Pending |

---

## 11. Risk Assessment

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| 1 | No SUPER_ADMIN → admin/provisioning lockout | High | High | Promote a CAAN_SMD to SUPER_ADMIN immediately; document in ops runbook |
| 2 | Simplified passwords are predictable | Medium | Medium | Beta/seed environments only; rotate to unique passwords for real tenants at go-live |
| 3 | Auto-created diversion hazards duplicate manual entries | Medium | Low | Source-link check; seed script + audit script to reconcile |
| 4 | Escalation job fails to authenticate | Low | Medium | `X-Task-Key` matches `TASK_API_KEY` on both services; manual run verified |
| 5 | Production seeding errors | Low | High | Preview before deploy, PITR 7-day, provisioning runbook |
| 6 | Sender API key exposure | Low | High | Key held server-side only (env var), never committed |

---

## 12. Recommendations

| # | Recommendation | Priority | Owner |
|---|----------------|----------|-------|
| 1 | **Promote a CAAN_SMD account to SUPER_ADMIN** to restore admin routes | High | Super Admin |
| 2 | Deploy frontend hosting (beta + prod) for the CAA CAP form + PDF export release (`81fab62`) | High | DevOps |
| 3 | Distribute the simplified credential sheet to beta testers | High | Project Manager |
| 4 | Invite beta testers (Sita Air, CAAN, Tara Air, Yeti Airlines) | High | Project Manager |
| 5 | Conduct beta testing for 2 weeks | High | Testers |
| 6 | Configure monitoring and alerts (Render + Firebase + GCP Scheduler) | Medium | DevOps |
| 7 | Prepare production seeding plan and execute at go-live | Medium | Super Admin |
| 8 | Implement MFA (TOTP/SMS) | Medium | Development Team |
| 9 | Clean up orphaned dashboard pages (`dashboard/index.html` legacy, `portal/*`) | Low | Development Team |

---

*End of report. Generated 2026-08-11 from live environment data.*
