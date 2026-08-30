# 📝 AviaSAFE SMS — Project Status Report

**Project**: AviaSAFE SMS — Safety Climate Measurement System (ICAO Annex 19 compliant)
**Report Date**: 2026-08-10
**Prepared by**: AviaSAFE Systems engineering (Opencode-assisted)
**Verification**: All figures below were verified live against the deployed backends (Render), frontend hostings (Firebase Hosting beta + prod), Firebase Auth, both Firestore databases, and the backend test suite on the report date.

---

## 1. Executive Summary

| Item | Value |
|------|-------|
| **Project Name** | AviaSAFE SMS |
| **Report Date** | 2026-08-10 |
| **Overall Status** | **Credential modernization + data-integrity hardening** — simplified user credentials, stricter hazard-source enforcement, and SMS Maturity rename shipped to beta + prod |
| **Current Phase** | Beta Testing (pre-production) |

**Key Highlights**
- **Simplified credentials (2026-08-10) shipped** — 28 new functional role accounts (`safety`, `camo`, `145`, `ops`) across all 7 operators using a readable scheme: `{role}@{tenant}.com` / `{TENANT_CODE}-{ROLE}-2026` (e.g. `safety@buddha-air.com` / `BHA-Safety-2026`). All verified signing in via the Identity Toolkit path.
- **CAAN SUPER_ADMIN removed** — `super-admin-001` (`safety.director@caan.gov.np`) deleted from Auth + Firestore `users`. No `SUPER_ADMIN` currently exists; admin routes now require promoting a CAAN_SMD first.
- **Hazard-source integrity enforced** — hazard creation restricted to an allowed source allow-list; flight diversions now **auto-create linked hazards** (with `source=FLIGHT_DIVERSION`, `source_id`, and a link back to the diversion). New seed + audit scripts added.
- **SMS Maturity terminology rename** — "SMS health" → "SMS maturity" across the API, dashboards, docs, and tests (rename-only; no functional impact).
- **Backend suite green** — **195 backend tests passing** (was 183).

**Key Risks**
- **No SUPER_ADMIN account** — after removing `super-admin-001`, provisioning/seed routes (`/api/v1/admin/*`) require promoting a CAAN_SMD account to `SUPER_ADMIN`. Until then those routes are unusable.
- **Production seeding deferred to go-live** — `sms-db` still has 0 tenants / 0 operational data (by design); tenants/users must be created post-contract.
- **Monitoring & alerts not yet configured** — no dashboards/alerting on the Render backends or Firebase project.

---

## 2. System Overview

- **Application Purpose**: ICAO Annex 19, Doc 9859 (Safety Management Manual) and Doc 10159 (Safety Intelligence Manual) aligned SMS platform for airlines, regulators, and aviation organizations. Measures SMS maturity, identifies hazards, assesses/mitigates risks, and turns safety data into safety intelligence.
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
| **Beta Backend** | `https://aviasafe-unified-platform.onrender.com` | ✅ Live (200) | Render service, `FIREBASE_DATABASE_ID=sms-db-beta`, auto-deploy on push |
| **Production Frontend** | `https://sms.aviasafesystems.com` | ✅ Live (200) | Firebase Hosting, site `aerosafety-sms-prod`, project `aerosafety-sms-prod` |
| **Production Backend** | `https://aviasafe-unified-platform.onrender.com` | ✅ Live (200) | Render service, `FIREBASE_DATABASE_ID=sms-db` (via `backend/render.yaml`) |

Both hostings serve the same `public/` directory. Frontend routing (`public/js/firebase.js`) selects the beta backend/database by hostname containing `beta`.

**Deployments since last report (2026-08-08 → 2026-08-10):**
| Deploy | Ref | Target |
|--------|-----|--------|
| SMS Maturity rename | `1654fd0` | Render auto-deploy (backend) + Firebase Hosting (beta + prod) |
| Hazard source enforcement + diversion auto-create | `f67d358` | Render auto-deploy (backend) + Firebase Hosting (beta + prod) |
| Simplified credentials scheme + migration script | `e11a5d9` | Render auto-deploy (backend) |

### 3.2 Databases (Firestore native)

| Database | Environment | PITR | Tenants | Users | Data Count | Status |
|----------|-------------|------|---------|-------|------------|--------|
| `sms-db` | Production | ✅ 7-day | 0 | **51** | 0 tenants / 0 surveys / 0 hazards / 0 reports | ✅ Go-live ready (clean slate) |
| `sms-db-beta` | Beta | ✅ 7-day | 7 | **51** | 1,033 surveys · 980 reports · 42 hazards · 3 CAN/CAP | ✅ Fully seeded |

> **2026-08-10 change:** both databases now carry **51 user docs** (was 24). The 28 simplified role
> accounts were created in Firebase Auth (shared beta + prod) and mirrored into the `users`
> collection of both databases via `backfill_users_from_auth`. The former CAAN SUPER_ADMIN doc was
> deleted.

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

### 4.1 Completed This Period (2026-08-10)

| Feature | Module | Status | Deployed |
|---------|--------|--------|----------|
| Simplified credential scheme (`{role}@{tenant}.com` / `{CODE}-{ROLE}-2026`) | Auth | ✅ Complete | Auth (shared beta + prod) |
| 28 functional role accounts created (7 operators × safety/camo/145/ops) | Auth | ✅ Complete | Auth + `users` (both DBs) |
| Remove CAAN SUPER_ADMIN `super-admin-001` | Auth | ✅ Complete | Auth + `users` (both DBs) |
| Migration script `backend/scripts/simplify_credentials.py` (dry-run + apply) | Tooling | ✅ Complete | Repo |
| `seed/config.py` + `seed/users.py` extended for the new scheme | Seeding | ✅ Complete | Repo |
| Hazard creation source allow-list (`HAZARD_CREATION_SOURCES`) | Module 2 | ✅ Complete | Beta + Prod |
| Auto-create hazard from flight diversion with `source_id` + link-back | Module 2 | ✅ Complete | Beta + Prod |
| `seed_flight_diversions.py` + `inspect-report-hazard-link.js` scripts | Tooling | ✅ Complete | Repo |
| SMS Maturity terminology rename (API, UI, docs, tests) | Module 1 | ✅ Complete | Beta + Prod |
| Credential reference updated (`credential.md`, `docs/BETA_TESTERS.md`) | Docs | ✅ Complete | Repo (credential.md local-only) |

### 4.2 Completed Features (prior)

See `docs/PROJECT_STATUS_REPORT_2026-08-08.md` §4 for the full inventory (department mapping, escalation, Master Register, Responsible Manager, survey, hazard register, risk matrix, trends, flight diversions, state regulator dashboard, CAN/CAP, admin panel, landing page, security & compliance).

---

## 5. Testing Status

### 5.1 Backend Tests — **195 passing** (all green, `python -m pytest tests/ -q`)

| Category | Test Count | Status |
|----------|------------|--------|
| Admin & Super-Admin | 64 | ✅ Passing |
| Hazards / Risk Assessment / Diversions | 48 | ✅ Passing |
| Regulator & State Risk | 42 | ✅ Passing |
| Surveys | 16 | ✅ Passing |
| Contact (Sender.net endpoint) | 6 | ✅ Passing |
| Health / Metrics / Infrastructure | 12 | ✅ Passing |
| Escalation & Master Register | 7 | ✅ Passing |
| **Total** | **195** | ✅ Passing |

### 5.2 Frontend Tests — **4 passing**

| Category | Test Count | Status |
|----------|------------|--------|
| Dashboard Render Tests (`node frontend-tests/dashboard.test.js`, `npm test`) | 4 | ✅ Passing |

### 5.3 Live Credential Verification (2026-08-10)

| Check | Result |
|-------|--------|
| `safety@buddha-air.com` / `BHA-Safety-2026` sign-in | ✅ OK |
| `camo@tara-air.com` / `TARA-CAMO-2026` sign-in | ✅ OK |
| `145@yeti-airlines.com` / `YETI-145-2026` sign-in | ✅ OK |
| `ops@air-dynasty.com` / `DYNASTY-Ops-2026` sign-in | ✅ OK |
| `safety@simrik-air.com` / `SIMRIK-Safety-2026` sign-in | ✅ OK |
| `safety.director@caan.gov.np` (removed SUPER_ADMIN) | ✅ Rejected (400) |
| `users` collection sync | ✅ 51 docs in `sms-db-beta` + `sms-db` |

---

## 6. Beta Testing Status

### 6.1 Beta Environment (`sms-db-beta`) — verified healthy today

| Aspect | Status | Details |
|--------|--------|---------|
| **Environment** | `sms-db-beta` | Fully seeded, PITR 7-day |
| **Tenants** | 7 | sita-air, buddha-air, tara-air, yeti-airlines, summit-air, simrik-air, air-dynasty |
| **Regulator** | 1 | caan (Nepal) |
| **Users** | 51 | 28 simplified role accounts + 21 legacy operator + 2 CAAN_SMD |
| **Surveys** | 1,033 | Seeded responses |
| **Hazards** | 42 | Clean seeded data (per tenant: 5–7) |
| **Reports** | 980 | Seeded VSR/MOR |
| **CAN/CAP** | 3 | Tara Air demo corrective actions |
| **Audit logs** | active | Escalation writes to `audit_logs` |

### 6.2 Beta Access — Simplified Accounts (2026-08-10)

| Role | Email | Password | Status |
|------|-------|----------|--------|
| AIRLINE_ADMIN | safety@buddha-air.com | `BHA-Safety-2026` | ✅ Working |
| AIRLINE_ADMIN | safety@tara-air.com | `TARA-Safety-2026` | ✅ Working |
| AIRLINE_ADMIN | camo@tara-air.com | `TARA-CAMO-2026` | ✅ Working |
| AIRLINE_ADMIN | 145@yeti-airlines.com | `YETI-145-2026` | ✅ Working |
| AIRLINE_ADMIN | ops@air-dynasty.com | `DYNASTY-Ops-2026` | ✅ Working |
| CAAN_SMD | sms.inspector@caan.gov.np | shared seed | ✅ Working |
| CAAN_SMD | director.safety@caan.gov.np | shared seed | ✅ Working |
| ~~SUPER_ADMIN~~ | ~~safety.director@caan.gov.np~~ | — | ❌ Removed |

Full 28-account table: `credential.md` (§ Simplified Role Accounts).

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
| **Users** | 51 | Pre-provisioned accounts in `users` collection (28 simplified + legacy) |
| **Backend** | ✅ Deployed | Latest code (incl. hazard/diversion + credentials), auto-deploy |
| **Frontend** | ✅ Deployed | Latest code (SMS Maturity rename) |

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
| API Documentation | ✅ Complete | `docs/API.md` (SMS maturity rename applied) |
| Security Guide | ✅ Complete | `docs/SECURITY.md` |
| Deployment Guide | ✅ Complete | `docs/DEPLOYMENT.md` |
| Operations Guide | ✅ Complete | `docs/OPERATIONS.md` |
| User Flow | ✅ Complete | `docs/USER_FLOW.md` |
| Known Limitations | ✅ Complete | `docs/KNOWN_LIMITATIONS.md` |
| Manual Verification Checklist | ✅ Updated | `manual_verification.md` |
| Beta Testers Reference | ✅ Updated 2026-08-10 | `docs/BETA_TESTERS.md` |
| Credential Reference | ✅ Updated 2026-08-10 | `credential.md` (local-only, gitignored) |

### 8.2 Archived Documentation

| Document | Status | Location |
|----------|--------|----------|
| Status Report 05 Aug 2026 | ✅ Archived | `docs/archive/PROJECT_STATUS_REPORT_05AUG2026.md` |
| Status Report 07 Aug 2026 | ✅ In place | `docs/PROJECT_STATUS_REPORT_2026-08-07.md` |
| Status Report 08 Aug 2026 | ✅ In place | `docs/PROJECT_STATUS_REPORT_2026-08-08.md` |
| Status Report 10 Aug 2026 | ✅ This report | `docs/PROJECT_STATUS_REPORT_2026-08-10.md` |

---

## 9. Known Issues & Limitations

| # | Issue | Severity | Status | Notes |
|---|-------|----------|--------|-------|
| 1 | Survey rate limit (5/day/tenant) | Low | ✅ Configurable | Adjustable via dashboard (options 5/10/25/50/100) |
| 2 | **No SUPER_ADMIN account** | High | ⚠️ Action | Removed 2026-08-10; promote a CAAN_SMD to restore admin routes |
| 3 | Sender.net domain verification | Low | ⚠️ Pending | Free-plan limitation; sending domain not yet verified |
| 4 | Production has no operational data | N/A | ✅ Intentional | Clean slate for go-live (51 user accounts present) |
| 5 | Monitoring / alerting | Medium | ⚠️ Pending | Not yet configured |
| 6 | MFA (TOTP/SMS) | Medium | ⚠️ Pending | Not yet implemented |
| 7 | Legacy/orphaned dashboard pages | Low | ⚠️ Known | `public/dashboard/index.html`, `public/portal/*` not linked from nav |

---

## 10. Next Steps & Milestones

| # | Milestone | Target Date | Status |
|---|-----------|-------------|--------|
| 1 | **Restore SUPER_ADMIN** (promote a CAAN_SMD account) | Immediate | ⚠️ Action |
| 2 | Distribute simplified credentials to beta testers | Immediate | ⏳ Pending |
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
| 2 | Distribute the simplified credential sheet to beta testers | High | Project Manager |
| 3 | Invite beta testers (Sita Air, CAAN, Tara Air, Yeti Airlines) | High | Project Manager |
| 4 | Conduct beta testing for 2 weeks | High | Testers |
| 5 | Configure monitoring and alerts (Render + Firebase + GCP Scheduler) | Medium | DevOps |
| 6 | Prepare production seeding plan and execute at go-live | Medium | Super Admin |
| 7 | Implement MFA (TOTP/SMS) | Medium | Development Team |
| 8 | Clean up orphaned dashboard pages (`dashboard/index.html` legacy, `portal/*`) | Low | Development Team |

---

*End of report. Generated 2026-08-10 from live environment data.*
