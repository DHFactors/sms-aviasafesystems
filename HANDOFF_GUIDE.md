# Starting a New Session — Handoff Guide

## Current State (as of 2026-09-25)
- Platform: sms.aviasafesystems.com (production, live)
- Backend: Render (auto-deploy on push to main)
- Frontend: Firebase Hosting (MANUAL deploy — see follow-ups)
- Database: Supabase Postgres
- Auth: Firebase Auth + App Check (reCAPTCHA Enterprise)
- Status: All systems operational. Login and admin dashboard verified
  working in incognito.

## Resolved: App Check Login Failure (2026-09-25)
Four compounding bugs, all fixed in this session:
1. Legacy reCAPTCHA v3 key mismatch (fixed via new Enterprise key
   6LdPWs0t...)
2. Frontend silently dropped App Check token (fixed in firebase.js
   + login.html with retry + fail-loud)
3. Loguru %s placeholders swallowed exception messages (fixed in
   app_check.py ×2, spi_service.py; follow-up sweep also fixed the
   lenient path, copilot routes ×2, groq_copilot, plus a malformed
   placeholder from the first pass)
4. Backend called non-existent SDK method verify_app_check_token
   (fixed to verify_token)

Full write-up: LOGIN_FAILURE_DIAGNOSIS.md

## Key Facts
- Firebase project: aerosafety-sms-prod (project number 527947363983)
- Working reCAPTCHA key: 6LdPWs0tAAAAAJaWc4bRA0mK6mn1fYxbAEiFGAKb
  (status: Protected; only key remaining)
- Admin account: ezondiza.dhf@gmail.com (SUPER_ADMIN role)
- Backend URL: aviasafe-unified-platform.onrender.com
- Frontend URL: sms.aviasafesystems.com
- Git: github.com/DHFactors/sms-aviasafesystems (branch: main)

## Current Project State
- Phase 1 (schema): complete
- Phase 2 (services): complete
- Phase 3 (API endpoints): complete
- Phase 4 (dashboards): Waves 1-3 complete; Wave 4 (AE) and Wave 5
  (State Regulator) pending
- Phase 5 (tests): pending
- Phase 6 (deployment): pending

## App Check Posture
- Backend middleware verifies App Check tokens on protected endpoints
- Firebase App Check enforcement is deliberately OFF
- Admin pages (/admin/*) intentionally skip App Check (Guard 2 in
  firebase.js) — this is a design choice, not a bug
- Login flow: App Check token is required and verified

## Follow-ups (prioritized)
### Tier 1 — This week
1. Automate Firebase Hosting deploy (GitHub Action) — currently manual
2. Grep for any remaining silent-failure patterns in frontend

### Tier 2 — This month
3. Migrate google.generativeai to google.genai (deprecation warning
   in every Render startup)
4. Add favicon.ico to backend to fix 404 in logs
5. Consider removing ?appcheck=false debug flag from firebase.js
   (documented in source but should not be in production)

### Tier 3 — Next quarter
6. Remove /admin/* App Check bypass, then enable Firebase App Check
   enforcement
7. Add App Check headers to api/client.js shared HTTP client (used
   by all authenticated API calls)
8. Standardize on one logging library (currently mixed loguru +
   stdlib)
9. Full production hardening review

## Loguru Gotcha (postmortem pattern)
Loguru uses {} formatting, not %s. Any logger.warning("...%s", x)
with loguru prints the literal %s and discards x. This caused a
full day of hidden errors. Search before adding new loguru calls:

Get-ChildItem -Path backend -Include *.py -Recurse |
  Select-String -Pattern 'logger\.\w+\([^)]*%[sd]'

Stdlib `logging` files are fine with %s.

## Key Documents
- LOGIN_FAILURE_DIAGNOSIS.md (root cause history)
- CONNECTION_STABILITY_REPORT.md (test suite infra notes)
- MODULE_A_CONTRACT.md, MODULE_B_CONTRACT.md, MODULE_C_CONTRACT.md
- RBAC_MODEL.md, DASHBOARD_CONTRACT.md, COMPLIANCE_MATRIX.md
- IMPLEMENTATION_ROADMAP.md

## Quick Reference
| What | Location |
|---|---|
| Backend code | D:\projects\aviasafesms\backend\ |
| Frontend code | D:\projects\aviasafesms\public\ |
| Test suite | D:\projects\aviasafesms\backend\tests\ |
| Contracts | D:\projects\aviasafesms\*.md (repo root) |
| Backend deployed | aviasafe-unified-platform.onrender.com |
| Frontend deployed | sms.aviasafesystems.com |
| Git repo | github.com/DHFactors/sms-aviasafesystems |

---
Last updated: 2026-09-25
HEAD at time of writing: 5cc3308c819de5ed3f5070e13f1c8abd90a52016

## Session Update — 2026-09-27

### Fixed in this session

**Admin user management (step3-manage.html) — fully functional now:**
- Block-nesting trap that made Edit/Manage buttons dead
  (commit 4df7f50)
- entityDone ordering bug that loaded the wrong list after a
  regulator save (commit 1613103)
- entitySubmitLabel span destroyed by the submit spinner,
  breaking Edit on every post-save click (commit 0b8b90b)
- Hardened openEntityModal / openEditUserModal with try/catch
  so async failures toast instead of dying silently (commit
  1613103)
- Removed 5 stale Firestore references from user-visible copy
  (commits 78f3bc1, 01a6090)
- Guarded Firestore mirror sync so tenant PATCH succeeds after
  PG update (commit 94095f8)

**Broader Firestore copy cleanup:**
- Removed 8 more user-visible Firestore references across admin
  pages and the privacy policy (commit c397b67)
- Privacy policy now correctly cites Supabase (PostgreSQL) as
  the data storage layer

**Documentation:**
- IMPLEMENTATION_ROADMAP.md — Phase 4 Waves 1-3 marked DONE
  (commit 67aeaa8)
- DASHBOARD_CONTRACT.md — stale page-existence claims corrected
  (commits bfd6927, b09f583)

**Deploy pipeline:**
- Firebase Hosting auto-deploy via GitHub Actions workflow
  (commits fdaddee, 318c010, 474f4c5)
- Node 22 upgrade on the workflow
- Render auto-deploy confirmed working (dashboard needs refresh
  to show new deploys — the UI does not live-update)

### Known follow-ups (unchanged from before, plus new)

- **Bug B — resync contract** (production_seed.py:334-343):
  "tenant exists in Postgres → resync instead of reject" is
  dead code. Decide: fix the backend or fix the copy.
- **Frontend audit Fix 1** — api/client.js should attach App
  Check token and log token/tenant failures instead of silent
  null returns.
- **Frontend audit Fix 2-4** — smaller HIGH-priority items.
- **Backend Firestore cleanup** (bulk): ~15 guarded mirror
  blocks, firestore_deleted response fields, ~10 test functions
  pinning dead behavior. Multi-session project.
- **Multi-tenant routing test** — non-super-admin login must be
  verified end-to-end.
- **Tenants list slow-refresh** — backend aggregates run per
  tenant; consider batching.

## Session Update — 2026-09-27 (Part 2)

### Commits landed this session
- fed2293 — backend report_type filter on /dashboard/recent
- e4b4aa6 — Safety Manager dashboard rebuild (6 KPIs, dual trend
  charts, 4 recent-activity cards)
- 26c7361 — removed 5 orphan/stub HTML files
- 13a8493 — demo password reset script
- b3ae6ee — role-guard batch fix (4 files)
- 8e1fa1c — nav cleanup + setActiveNav fix
- ccb7d77 — Reports tab on unified Master Register (role-gated)
- feef695 — DEPT_ADMIN scoped register + nav + link fixes
- (plus earlier: f93b130, 777991e, 94095f8)

### What works now
- Login for every demo role
- Safety Manager dashboard rebuilt with all sections
- Unified Master Register: Hazards/CANs/CAPs/Reports tabs,
  role-gated, URL param selection
- Department Master Register: CANs + CAPs only, no tabs,
  department-scoped
- DEPT_ADMIN nav: My Tasks + Master Register
- Submit Report button routes to /reports/new.html
- Full MOR/VSR forms reachable from the wizard
- Auto-deploy: GitHub Actions (frontend) + Render (backend)
- Demo passwords: AviaSafeDemo2026! for all 16 pilot users

### Tomorrow morning — first test
Test DEPT_ADMIN end-to-end as camo@sitaair.com.np
(password: AviaSafeDemo2026!) in incognito:
1. Nav shows only My Tasks + Master Register
2. Master Register → /dashboard/dept-master-register.html
3. Dept register: CANs + CAPs only, no tabs
4. CAN row click → /can_cap/can_detail.html
5. Submit Report → /reports/new.html
6. Wizard Step 2 shows MOR + VSR full-form links
7. Both links reach /report/mor.html and /report/vsr.html

### Queued work (priority order)
1. Multi-tenant routing test — Air Dynasty + Saurya
2. Adaptive chart granularity — day/week/month/year buckets
3. CAAN role-boundary audit + PSOE under Performance
4. AE dashboard refinement (High Risk + Critical counters)
5. Frontend audit Fix 1 — api/client.js App Check
6. Firestore cleanup (bulk)
7. Shell migration (legacy → modern, incremental)

### Production readiness checklist
- Replace demo users with real users
- Upgrade Render + Supabase tiers (cold-start delay)
- join.html production scrutiny
- PSOE scope enforcement audit
- Remove AIRLINE_ADMIN from step-3 dropdown + role checks

### Known limitations (demo-acceptable)
- Right trend chart may show "Loading…" during Render cold
  start (30-60s after 15min idle on free tier)
- Folder split report/ (individual) vs reports/ (hub) is
  intentional — do not merge
