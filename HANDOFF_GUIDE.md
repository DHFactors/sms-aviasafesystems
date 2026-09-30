# Starting a New Session — Handoff Guide

## Current State (as of 2026-09-28)
- Platform: sms.aviasafesystems.com (production, live)
- Backend: Render (auto-deploy on push to main)
- Frontend: Firebase Hosting (auto-deploy via GitHub Actions on
  push to main, paths public/**)
- Database: Supabase Postgres (transaction pooler :6543)
- Auth: Firebase Auth + App Check (reCAPTCHA Enterprise)
- Platform: multi-tenant aviation SMS per ICAO Annex 19 3rd
  Edition, Doc 9859, Doc 10159
- HEAD: cb4d875 (all pushed, working tree clean)
- Latest Firebase Hosting deploy: #28 on cb4d875 (31s, green)
- Latest Render deploy: #30 on b4f8770 (1m55s, Live)
- All roles can log in: TENANT_ADMIN, DEPT_ADMIN, OFFICER
  (formerly SAFETY_OFFICER), ACCOUNTABLE_EXECUTIVE, CAAN_SMD,
  SUPER_ADMIN
- Demo passwords: AviaSafeDemo2026! (all 16 pilot users),
  except bdevkota@sitaair.com.np (own generated password)
- AE dashboard: working end-to-end (login, SMS Maturity card
  with component score, Executive Decisions panel, CAP review
  modal, decision modal)
- AE decision feature sequence COMPLETE and verified end to end
  on the deployed site: escalation queue -> CAP review ->
  decision modal (attestation-only signature) -> terminal
  decision endpoint -> server-side PDF record -> ledger with
  selection and PDF/CSV export.

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
- Phase 4 (dashboards): Waves 1-4 complete (Wave 4 AE decision
  flow complete and verified end-to-end); Wave 5
  (State Regulator) pending
- Phase 5 (tests): pending
- Phase 6 (deployment): pending

## App Check Posture
- Backend middleware verifies App Check tokens on protected endpoints
- Firebase App Check enforcement is deliberately OFF
- Admin pages (/admin/*) intentionally skip App Check (Guard 2 in
  firebase.js) — this is a design choice, not a bug
- Login flow: App Check token is required and verified

## Known Gotchas
1. Loguru uses {} formatting, not %s. Any logger.warning("...%s", x)
   with loguru prints the literal %s and discards x. This caused a
   full day of hidden errors. Search before adding new loguru calls:

Get-ChildItem -Path backend -Include *.py -Recurse |
  Select-String -Pattern 'logger\.\w+\([^)]*%[sd]'

   Stdlib `logging` files are fine with %s.
2. Role name shim: code accepts BOTH "SAFETY_OFFICER" and
   "OFFICER" everywhere. Do NOT remove SAFETY_OFFICER
   references until a claim migration has run.
3. Firebase Hosting is auto-deploy via GitHub Actions. A push
   to main that changes only backend/ will NOT trigger the
   frontend deploy. Similarly, a push that changes only
   public/** will NOT trigger a Render backend deploy.
4. CSS files have no cache-buster (?v=). Users may need a
   hard-refresh after a CSS change.
5. Render cold start: free tier spins down after ~15 min idle.
   First page load can take 30-60s. Not a bug.
6. Email-prefix routing: safety@ goes to safety.html even
   though role is OFFICER. Confirm any time router is touched.
7. Authenticated frontend changes can ONLY be verified against
   the deployed site. Localhost cannot validate App Check
   (reCAPTCHA Enterprise is registered against deployed
   domains). The development loop is: commit -> push -> verify
   on sms.aviasafesystems.com -> fix forward if needed. There
   is NO local-only verification path for authenticated flows.
8. PowerShell splits inline multi-line git commit -m messages
   into pathspecs. Always use git commit -F <tempfile> for
   multi-line commit messages on this workstation.

## Follow-ups (prioritized)
### Tier 1 — This week
1. PDF immutability text typo — the string in pdf_canvas.py
   currently reads "under ICAO Annex 19 / Dc decision is
   immutable"; should read "under ICAO Annex 19 / Doc 9859.
   The decision is immutable". One-line fix on a
   compliance-facing artifact. DO FIRST.
2. Ledger row shows blank decision and signer fields — the
   AE dashboard ledger renders "-- . --" for decision word and
   signer name despite the detail fetch succeeding. Likely a
   field-name mismatch between what the renderer expects
   (signature.decision, signature.name) and what the detail
   endpoint returns. Frontend-only, small.
3. AE signer name is not first-class — PDF "Signer name"
   currently shows the email, not the typed name; the typed
   name lives inside notes as "Signed by <name> (AE
   attestation)." Fix: add signer_name: Optional[str] to
   AEDecisionRequest, populate the signature block's name
   from it, keep signed_by = user.email. Backend + frontend.
4. Grep for any remaining silent-failure patterns in frontend

### Tier 2 — This month
5. Component score edge cases — verify null-data handling.
6. Migrate google.generativeai to google.genai (deprecation warning
   in every Render startup)
7. Add favicon.ico to backend to fix 404 in logs
8. Consider removing ?appcheck=false debug flag from firebase.js
   (documented in source but should not be in production)
9. **Bug B — resync contract** (production_seed.py:334-343):
   "tenant exists in Postgres → resync instead of reject" is
   dead code. Decide: fix the backend or fix the copy.
10. **Frontend audit Fix 2-4** — smaller HIGH-priority items.
11. Multi-tenant routing test — Air Dynasty + Saurya
12. Adaptive chart granularity — day/week/month/year buckets
    based on selected period. Spec agreed: <=60d daily,
    61-180d weekly, 181-365d monthly, >365d yearly.
13. Trends anchor on AE dashboard — deferred; will define
    content based on Annex 19 3rd Edition. Nav item currently
    points to #trends but no element has that id.

### Tier 3 — Next quarter
14. CAAN dashboard redesign — regulator view; aggregate-only.
    Multi-session.
15. Firestore cleanup (bulk): ~15 guarded mirror blocks,
    firestore_deleted response fields, ~10 test functions
    pinning dead behavior. Multi-session project.
16. Frontend audit Fix 1 — api/client.js App Check attachment
    + token/tenant failure logging. NOTE: App Check work must
    be verified on the deployed site (see gotcha 7).
17. AE dashboard RCA seeder enrichment — add factual_review
    + rca narrative to the demo CAP. Seeder-only change.
18. Remove /admin/* App Check bypass, then enable Firebase App Check
    enforcement
19. Tenants list slow-refresh — backend aggregates run per
    tenant; consider batching.
20. Replace demo users with real users
21. Upgrade Render + Supabase tiers (cold-start delay)
22. join.html production scrutiny
23. PSOE scope enforcement audit
24. Retired role cleanup — multi-session project. Includes:
    (a) AIRLINE_ADMIN decommission across ~98 references in
    ~58 files (60 backend, 38 frontend); (b) fix
    get_accountable_executive in auth.py to allow
    ACCOUNTABLE_EXECUTIVE (own tenant), drop CROSS_TENANT and
    AIRLINE_ADMIN; (c) STAFF retirement from code; (d)
    SAFETY_OFFICER -> OFFICER stored-claim migration; (e)
    remove the SAFETY_OFFICER shim. One coordinated project
    because they share root cause: role-name drift not yet
    reconciled.
25. _cap_to_dict signature shape inconsistency — three
    shapes for ae_signature across three read paths (bool /
    full dict / name string). Deferred refactor; needs a
    plan for how to unify without breaking any of the six
    callers of _cap_to_dict.
26. Test file updates — ~18 test files pin the SAFETY_OFFICER
    literal; several pin old AE menu shape (test_ae_narrow_menu)
    and SAFETY_OFFICER -> ALL mapping (test_nav_config). Update
    to match the shim + new nav shape.
27. Standardize on one logging library (currently mixed loguru +
    stdlib)
28. Cosmetic debt: alert() used for success confirmation in
    submitAeDecision (ae-dashboard.html). No toast idiom
    exists in the file; consider adding a shared one.
29. Full production hardening review

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
Last updated: 2026-09-28
HEAD at time of writing: cb4d875

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

## Session Update — 2026-09-28 (Part 3 + Part 4)

### Commits landed this session
- 036280b — nav fix: DEPT_ADMIN + STAFF workspace nav +
  Submit MOR target + test update
- 2833a45 — OFFICER dual-accept shim + 9-step routing
- 80653e9 — Accountable Executive as first-class role + AE
  dashboard guard
- e891d20 — AE dashboard UX: CAP click-through, decision
  modal, nav cleanup
- a26ed40 — CAP review modal for executive escalation queue
- 2389d3c — SMS Maturity card reads Module A survey data
  (was PSOE)
- a79f9b6 — nav active-dropdown highlight + underline bleed
- 51ec0aa — SMS Maturity card 40:60 restructure + expandable
  chart
- 3a2ca76 — SMS Maturity component score + Residual Exposure
  removal
- 894b6a8 — AE decision flow wired to POST /ae-decision
- b4f8770 — server-side PDF record of terminal AE decision
- cb4d875 — decision ledger render + select + PDF/CSV export

### What works now
- AE decision feature sequence complete end-to-end on the
  deployed site (see Current State above)
- Role model, routing, and nav settled for all six roles
  (details in Architectural decisions below)

### Architectural decisions recorded this session
- Six-role model finalized (TENANT_ADMIN Safety Manager,
  DEPT_ADMIN, OFFICER, ACCOUNTABLE_EXECUTIVE, CAAN_SMD,
  SUPER_ADMIN) with deterministic email-prefix + claim routing
- SAFETY_OFFICER -> OFFICER dual-accept shim; stored claims
  untouched pending migration
- AE decision is attestation-only; signature authority stays
  server-side (_ae_decide_async composes from user.email)
- ae_signature has three read-path shapes (list bool, detail
  dict, _cap_to_dict name string); get_cap_for_decision_record
  bypasses flattening for the PDF route
- AIRLINE_ADMIN is a fossil (~98 refs); coordinated
  decommission queued (see Follow-ups, Tier 3 item 24)
- get_accountable_executive (auth.py) is broken and unused
  except verification.py:76; fix folded into the same cleanup

### Deploys
- Firebase Hosting #28 on cb4d875 (31s, green)
- Render #30 on b4f8770 (1m55s, Live)

### First task queued for next session
- Confirm git state, then txt queue item 1 (PDF typo fix).
  See Follow-ups, Tier 1.

HEAD at time of writing: cb4d875
