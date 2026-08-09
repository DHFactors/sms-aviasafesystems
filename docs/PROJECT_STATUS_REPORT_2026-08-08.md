# 📝 AviaSAFE SMS — Project Status Report

**Project**: AviaSAFE SMS — Safety Climate Measurement System (ICAO Annex 19 compliant)
**Report Date**: 2026-08-08
**Prepared by**: AviaSAFE Systems engineering (Opencode-assisted)
**Verification**: All figures below were verified live against the deployed backends (Render), frontend hostings (Firebase Hosting beta + prod), the Cloud Scheduler job, and the backend test suite on the report date.

---

## 1. Executive Summary

| Item | Value |
|------|-------|
| **Project Name** | AviaSAFE SMS |
| **Report Date** | 2026-08-08 |
| **Overall Status** | **Beta feature expansion** — department-scoped workflows, automated escalation, and unified Master Register shipped to beta + prod |
| **Current Phase** | Beta Testing (pre-production) |

**Key Highlights**
- **Department Mapping (Phase 1) shipped** — `department` field on users, auto-populated onto hazards / CANs / CAPs at assignment, with `?department=` filters on the hazard, CAN, and CAP APIs.
- **Automated Escalation (Phases 2–3) shipped** — CANs past their `target_completion_date` auto-flip to **Escalated**, CAPs past due to **Overdue**, audited to the `audit_logs` collection. Driven by a new **Cloud Scheduler** job (`check-overdue`, daily 00:00 UTC) calling an internal `POST /api/v1/admin/tasks/check-overdue` endpoint.
- **Master Register (Phase 4) shipped** — unified Hazards + CANs + CAPs view (`/dashboard/master-register.html`) with status/department/search filters, sortable table, and stat cards.
- **Responsible Manager dashboard (Phase 5) shipped** — "My Tasks" (`/dashboard/responsible-manager.html`) scoped to the signed-in user's assigned CANs/CAPs; USERs with a `department` claim are routed there on login.
- **SMS Health visibility fixed** — SMS Health link added to the airline dashboard sidebar (`safety.html`); a **National SMS Health** summary card added to the CAAN landing dashboard (`caan.html`), one-click to the full State Risk Register.
- **Backend suite green** — **183 backend tests passing** (was 176; +7 new escalation / master-register tests).

**Key Risks**
- **Production seeding deferred to go-live** — `sms-db` still has 0 tenants / 0 operational data (by design); tenants/users must be created post-contract.
- **Monitoring & alerts not yet configured** — no dashboards/alerting on the Render backends or Firebase project.
- **`TASK_API_KEY` is required on Render** — the escalation scheduler depends on `X-Task-Key` matching `TASK_API_KEY`; key is set on both services and the Cloud Scheduler job (verified live with a manual run).

---

## 2. System Overview

- **Application Purpose**: ICAO Annex 19, Doc 9859 (Safety Management Manual) and Doc 10951 (Safety Intelligence Manual) aligned SMS platform for airlines, regulators, and aviation organizations. Measures SMS maturity, identifies hazards, assesses/mitigates risks, and turns safety data into safety intelligence.
- **Current Phase**: Beta Testing / Pre-Production
- **Target Audience**: Airlines (7 operators), Regulators (CAAN), MROs, Aerodromes

**Key Modules**
| Module | Focus |
|--------|-------|
| Module 1: SMS Health Assessment | Bilingual gap-analysis survey, survey lifecycle (open/close), per-tenant config, national aggregation |
| Module 2: Hazard / Risk Monitoring | Hazard register, auto-hazard creation from reports, risk matrix, trends, flight diversions, state regulator dashboard, escalation |
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

**Deployments today (2026-08-08):**
| Deploy | Ref | Target |
|--------|-----|--------|
| Feature commit | `8316cc9` | Render auto-deploy (backend) + Firebase Hosting (beta + prod) |
| Docs commit | `115f09b` | — |
| SMS Health sidebar + CAAN card | deployed | Firebase Hosting (beta + prod) |

### 3.2 Databases (Firestore native)

| Database | Environment | PITR | Tenants | Data Count | Status |
|----------|-------------|------|---------|------------|--------|
| `sms-db` | Production | ✅ 7-day | 0 | 24 pre-provisioned user accounts; **0 tenants / 0 surveys / 0 hazards / 0 reports** | ✅ Go-live ready (clean slate) |
| `sms-db-beta` | Beta | ✅ 7-day | 7 | 1,033 surveys · 980 reports · 42 hazards · 3 CAN/CAP · `audit_logs` now actively written by escalation | ✅ Fully seeded |

> **Note**: Production is *not* byte-for-byte empty — the 24 demo/seed user accounts are pre-provisioned in the `users` collection (mirrored beta accounts). No tenant documents or operational data exist yet; tenant/user creation is deferred to go-live.

### 3.3 Scheduled Jobs

| Job | Schedule | Endpoint | Auth | Status |
|-----|----------|----------|------|--------|
| **`check-overdue`** (Cloud Scheduler) | `0 0 * * *` (daily 00:00 UTC) | `POST /api/v1/admin/tasks/check-overdue` | `X-Task-Key` header (matches `TASK_API_KEY`) | ✅ Created, ENABLED, manual run verified (HTTP 200) |

### 3.4 Third-Party Services

| Service | Purpose | Status |
|---------|---------|--------|
| **Firebase Auth** | Authentication (email + custom claims: AIRLINE_ADMIN, CAAN_SMD, SUPER_ADMIN, USER) | ✅ Active |
| **Upstash Redis** | Rate limiting (beta only; `REDIS_URL` set on beta service) | ✅ Active (beta) |
| **Gemini AI** | SMS health scoring / recommendations | ✅ Configured (key in env) |
| **Sender.net** | Contact form subscriber capture | ✅ Active — key set on both beta + prod Render services |

---

## 4. Development Status

### 4.1 Completed This Period (2026-08-08)

| Feature | Module | Status | Deployed |
|---------|--------|--------|----------|
| Department field on users (`users.py` — doc mirror + `get_user_department()`) | Module 4 | ✅ Complete | Beta + Prod |
| Auto-populate department on hazard assign / CAN issue / CAP submit | Module 4 | ✅ Complete | Beta + Prod |
| `?department=` filters on hazards / cans / caps APIs | Module 4 | ✅ Complete | Beta + Prod |
| `ESCALATED` status in `CANStatus` enum + frontend badges | Module 3 | ✅ Complete | Beta + Prod |
| Escalation service (`escalation_service.py`: `check_tenant_overdue`, `check_all_overdue`) | Module 3 | ✅ Complete | Beta + Prod |
| Internal endpoint `POST /api/v1/admin/tasks/check-overdue` (`verify_task_auth`) | Module 3 | ✅ Complete | Beta + Prod |
| `TASK_API_KEY` config setting | Module 3 | ✅ Complete | Beta + Prod |
| Cloud Scheduler job `check-overdue` (daily 00:00 UTC) | Module 3 | ✅ Complete | GCP (`aerosafety-sms-prod`) |
| Escalation audit rows to `audit_logs` (`log_audit`) | Module 3 | ✅ Complete | Beta + Prod |
| Master Register service + `GET /api/v1/dashboard/master-register` | Module 4 | ✅ Complete | Beta + Prod |
| Master Register page `/dashboard/master-register.html` | Module 4 | ✅ Complete | Beta + Prod |
| Responsible Manager page `/dashboard/responsible-manager.html` | Module 4 | ✅ Complete | Beta + Prod |
| Sidebar links (Master Register, My Tasks) + role routing (`getRoleDestination`) | Module 4 | ✅ Complete | Beta + Prod |
| SMS Health sidebar link on `safety.html` → `/dashboard/index.html` | Module 1 | ✅ Complete | Beta + Prod |
| National SMS Health card on `caan.html` (with tier, click-through) | Module 1 | ✅ Complete | Beta + Prod |
| Verification docs updated (manual checklist + audit_logs corrections) | — | ✅ Complete | `115f09b` |

### 4.2 Completed Features (prior)

See `docs/PROJECT_STATUS_REPORT_2026-08-07.md` §4 for the full inventory (survey, hazard register, risk matrix, trends, flight diversions, state regulator dashboard, CAN/CAP, admin panel, landing page, security & compliance).

---

## 5. Testing Status

### 5.1 Backend Tests — **183 passing** (all green, `python -m pytest tests/ -q`)

| Category | Test Count | Status |
|----------|------------|--------|
| Admin & Super-Admin | 64 | ✅ Passing |
| Hazards / Risk Assessment | 36 | ✅ Passing |
| Regulator & State Risk | 42 | ✅ Passing |
| Surveys | 16 | ✅ Passing |
| Contact (Sender.net endpoint) | 6 | ✅ Passing |
| Health / Metrics / Infrastructure | 12 | ✅ Passing |
| **Escalation & Master Register (new)** | **7** | ✅ Passing (test_escalation_master_register.py) |
| **Total** | **183** | ✅ Passing |

New tests cover: CAN escalated when past due, idempotency on re-run, CAP overdue, `check_all_overdue` summary, master register combining types, department filter, assignee filter.

### 5.2 Frontend Tests — **4 passing**

| Category | Test Count | Status |
|----------|------------|--------|
| Dashboard Render Tests (`node frontend-tests/dashboard.test.js`, `npm test`) | 4 | ✅ Passing |

### 5.3 Manual Verification Status

| Area | Status | Notes |
|------|--------|-------|
| Airline Dashboard | ✅ Verified | All flows working |
| CAAN Dashboard | ✅ Verified | All 7 operators visible |
| SMS Health (per-tenant) | ✅ Linked | Sidebar link on `safety.html` → `/dashboard/index.html` (live, HTTP 200) |
| National SMS Health (CAAN) | ✅ Card added | `caan.html` stat card + tier, click-through to State Risk Register |
| Master Register | ⏳ To verify live | Endpoint live (auth-gated); page deployed |
| Responsible Manager | ⏳ To verify live | Requires a USER account with a `department` claim |
| Escalation | ✅ Endpoint verified | Manual scheduler run returned HTTP 200; escalation run clean |

> The manual checklist (`manual_verification.md`) was updated with new sections (Master Register, Responsible Manager, Department Mapping, Escalation & Audit Trail); rows for the new flows are marked pending live re-verification.

---

## 6. Beta Testing Status

### 6.1 Beta Environment (`sms-db-beta`) — as of prior report, re-verified healthy today

| Aspect | Status | Details |
|--------|--------|---------|
| **Environment** | `sms-db-beta` | Fully seeded, PITR 7-day |
| **Tenants** | 7 | sita-air, buddha-air, tara-air, yeti-airlines, summit-air, simrik-air, air-dynasty |
| **Regulator** | 1 | caan (Nepal) |
| **Users** | 24 | Demo accounts (7 operators × 3 + 3 CAAN/SUPER_ADMIN) |
| **Surveys** | 1,033 | Seeded responses |
| **Hazards** | 42 | Clean seeded data (per tenant: 5–7) |
| **Reports** | 980 | Seeded VSR/MOR |
| **CAN/CAP** | 3 | Tara Air demo corrective actions |
| **Audit logs** | active | Escalation writes to `audit_logs` |

### 6.2 Beta Access (demo accounts; unique passwords per `BETA_CREDENTIALS_2026-08-08.md`)

| Role | Email | Status |
|------|-------|--------|
| AIRLINE_ADMIN | `safety.tara-air@taraair.com` | ✅ Working |
| AIRLINE_ADMIN | `safety.sita-air@sitaair.com.np` | ✅ Working |
| AIRLINE_ADMIN | `safety.buddha-air@buddhaair.com` | ✅ Working |
| CAAN_SMD | `sms.inspector@caan.gov.np` | ✅ Working |
| CAAN_SMD | `director.safety@caan.gov.np` | ✅ Working |
| SUPER_ADMIN | `safety.director@caan.gov.np` | ✅ Working |

### 6.3 Beta Tester Onboarding

| Item | Status | Details |
|------|--------|---------|
| Invitation Template | ✅ Ready | `docs/BETA_INVITATION_TEMPLATE.md` |
| Tester Checklist | ✅ Ready | `docs/BETA_TEST_CHECKLIST.md` (audit_logs note corrected) |
| Tester Accounts Reference | ✅ Ready | `docs/BETA_TESTERS.md` |
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
| **Users** | 24 | Pre-provisioned seed accounts present in `users` collection |
| **Backend** | ✅ Deployed | Latest code (incl. escalation + master register), auto-deploy |
| **Frontend** | ✅ Deployed | Latest code (incl. SMS Health links + CAAN card) |

### 7.2 Go-Live Checklist

| Item | Status | Details |
|------|--------|---------|
| Production Domain | ✅ Configured | `sms.aviasafesystems.com` |
| SSL Certificate | ✅ Valid | Firebase Hosting managed (Let's Encrypt) |
| Backend | ✅ Deployed | Render auto-deploy |
| Frontend | ✅ Deployed | Firebase Hosting |
| Database | ✅ Ready | Clean slate, PITR 7-day |
| Rate Limiting | ✅ Configured | IP-based, 60 req/min per IP (configurable) |
| Scheduled escalation job | ✅ Configured | Cloud Scheduler `check-overdue`, daily 00:00 UTC |
| `TASK_API_KEY` | ✅ Set | Both prod + beta Render services |
| PITR | ✅ Enabled | 7-day retention (verified) |
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
| API Documentation | ✅ Complete | `docs/API.md` |
| Database Schema | ⏳ Pending | No `docs/DATABASE_SCHEMA.md` — covered inline in code + `docs/BETA_ENVIRONMENT.md` |
| Security Guide | ✅ Complete | `docs/SECURITY.md` |
| Deployment Guide | ✅ Complete | `docs/DEPLOYMENT.md` |
| Testing Guide | ⏳ Pending | No `docs/TESTING.md` |
| CI/CD Guide | ⏳ Pending | No `docs/CICD.md` |
| Troubleshooting Guide | ⏳ Pending | No `docs/TROUBLESHOOTING.md` |
| File Structure | ✅ Complete | `docs/FILE_STRUCTURE.md` |
| Operations Guide | ✅ Complete | `docs/OPERATIONS.md` (audit_logs note corrected) |
| User Flow | ✅ Complete | `docs/USER_FLOW.md` |
| Installation | ✅ Complete | `docs/INSTALLATION.md` |
| Known Limitations | ✅ Complete | `docs/KNOWN_LIMITATIONS.md` |
| Admin Guide | ✅ Complete | `docs/ADMIN_GUIDE.md` |
| Hazard Taxonomy | ✅ Complete | `docs/HAZARD_TAXONOMY.md` |
| Manual Verification Checklist | ✅ Updated 2026-08-08 | `manual_verification.md` (new sections: Master Register, Responsible Manager, Department Mapping, Escalation & Audit Trail) |

### 8.2 Beta Documentation

| Document | Status | Location |
|----------|--------|----------|
| Beta Test Checklist | ✅ Complete | `docs/BETA_TEST_CHECKLIST.md` |
| Beta Invitation Template | ✅ Complete | `docs/BETA_INVITATION_TEMPLATE.md` |
| Beta Testers | ✅ Complete | `docs/BETA_TESTERS.md` |
| Beta Environment | ✅ Complete | `docs/BETA_ENVIRONMENT.md` |
| Feedback Form Structure | ✅ Complete | `docs/FEEDBACK_FORM_STRUCTURE.md` |
| Go-Live Shutdown Runbook | ✅ Complete | `docs/GO_LIVE_SHUTDOWN_RUNBOOK.md` |

### 8.3 Archived Documentation

| Document | Status | Location |
|----------|--------|----------|
| Status Report 05 Aug 2026 | ✅ Archived | `docs/archive/PROJECT_STATUS_REPORT_05AUG2026.md` |
| Status Report 07 Aug 2026 | ✅ In place | `docs/PROJECT_STATUS_REPORT_2026-08-07.md` |
| Project Charter | ✅ Archived | `docs/archive/PROJECT_CHARTER.md` |
| GAPS | ✅ Archived | `docs/archive/GAPS.md` |
| Pre-Launch Assurance Report | ✅ Archived | `docs/archive/PRE_LAUNCH_ASSURANCE_REPORT.md` |
| Beta Monitoring Guide | ✅ Archived | `docs/archive/BETA_MONITORING_GUIDE.md` (audit_logs note corrected) |
| Demo Guide | ✅ Archived | `docs/archive/DEMO_GUIDE.md` |

---

## 9. Known Issues & Limitations

| # | Issue | Severity | Status | Notes |
|---|-------|----------|--------|-------|
| 1 | Survey rate limit (5/day/tenant) | Low | ✅ Configurable | Adjustable via dashboard (options 5/10/25/50/100) |
| 2 | Sender.net domain verification | Low | ⚠️ Pending | Free-plan limitation; sending domain not yet verified |
| 3 | Sender.net test-contact cleanup | Low | ⚠️ Known | Pending/unconfirmed subscribers cannot be removed via API; delete in Sender dashboard |
| 4 | Production has no operational data | N/A | ✅ Intentional | Clean slate for go-live (24 seed user accounts present) |
| 5 | Monitoring / alerting | Medium | ⚠️ Pending | Not yet configured |
| 6 | MFA (TOTP/SMS) | Medium | ⚠️ Pending | Not yet implemented |
| 7 | Legacy/orphaned dashboard pages | Low | ⚠️ Known | `public/dashboard/index.html`, `public/portal/*` not linked from nav (SMS Health now linked from `safety.html`) |
| 8 | New flows require live manual verification | Low | ⚠️ Pending | Master Register / My Tasks / department filters verified in tests, pending on-screen checks |

---

## 10. Next Steps & Milestones

| # | Milestone | Target Date | Status |
|---|-----------|-------------|--------|
| 1 | Live-verify Master Register / My Tasks / department flows on beta | Immediate | ⏳ Pending |
| 2 | Verify escalation job overnight run (or trigger manually) | Immediate | ⏳ Pending |
| 3 | Invite beta testers (Sita Air, CAAN, Tara Air, Yeti) | Immediate | ⏳ Pending |
| 4 | Beta Launch | TBD | ⏳ Pending |
| 5 | Beta Testing Period | 2 weeks (post-launch) | ⏳ Pending |
| 6 | Feedback Collection | During beta | ⏳ Pending |
| 7 | Production Go-Live | Post-beta | ⏳ Pending |
| 8 | Post-Launch Monitoring | Ongoing | ⏳ Pending |

---

## 11. Risk Assessment

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| 1 | Escalation job fails to authenticate | Low | Medium | `X-Task-Key` matches `TASK_API_KEY` on both services; manual run verified |
| 2 | Department data missing on legacy records | Medium | Low | Only new assignments auto-populate; filters simply return empty for unset departments |
| 3 | Master Register slow on large data | Low | Medium | Single endpoint aggregates hazards + CANs + CAPs; pagination not yet added |
| 4 | Low beta tester participation | Low | Medium | Active outreach, clear instructions, per-role demo accounts |
| 5 | Production seeding errors | Low | High | Preview before deploy, PITR 7-day, provisioning runbook |
| 6 | Sender API key exposure | Low | High | Key held server-side only (env var), never committed |
| 7 | `TASK_API_KEY` rotation drift | Low | Low | Job header and Render env must be updated together if rotated |

---

## 12. Recommendations

| # | Recommendation | Priority | Owner |
|---|----------------|----------|-------|
| 1 | Live-verify Master Register, My Tasks, and department filters on beta | High | Development Team |
| 2 | Confirm the first scheduled escalation run (00:00 UTC) via `audit_logs` | High | Development Team |
| 3 | Invite beta testers (Sita Air, CAAN, Tara Air, Yeti Airlines) | High | Project Manager |
| 4 | Conduct beta testing for 2 weeks | High | Testers |
| 5 | Collect and analyze feedback | High | Project Manager |
| 6 | Fix critical issues identified in beta | High | Development Team |
| 7 | Configure monitoring and alerts (Render + Firebase + GCP Scheduler) | Medium | DevOps |
| 8 | Prepare production seeding plan and execute at go-live | Medium | Super Admin |
| 9 | Implement MFA (TOTP/SMS) | Medium | Development Team |
| 10 | Clean up orphaned dashboard pages (`dashboard/index.html` legacy, `portal/*`) | Low | Development Team |
| 11 | Add pagination to Master Register if performance requires | Low | Development Team |
| 12 | Create `docs/DATABASE_SCHEMA.md`, `docs/TESTING.md`, `docs/CICD.md`, `docs/TROUBLESHOOTING.md` | Low | Documentation Team |

---

*End of report. Generated 2026-08-08 from live environment data.*
