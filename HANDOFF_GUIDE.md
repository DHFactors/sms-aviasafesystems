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
