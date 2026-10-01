# Starting a New Session — Handoff Guide

## Current State (as of 2026-10-01)
- Platform: sms.aviasafesystems.com (production, live)
- Backend: Render (auto-deploy on push to main)
- Frontend: Firebase Hosting (auto-deploy via GitHub Actions on
  push to main, paths public/**)
- Database: Supabase Postgres (transaction pooler :6543)
- Auth: Firebase Auth + App Check (reCAPTCHA Enterprise)
- Platform: multi-tenant aviation SMS per ICAO Annex 19 3rd
  Edition, Doc 9859, Doc 10159
- HEAD: fb4bb3b (all pushed, working tree clean)
- Latest Firebase Hosting deploy: #32 on fb4bb3b (36s, green)
- Latest Render deploy: fb4bb3b (priority derivation; 1m42s, Live)
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
9. Un-assessed hazards: a hazard that has been registered but not
   yet SRAM-assessed has NULL for risk_level, risk_outcome, and
   tolerability_tier. SRAM is the sole writer of these fields.
   CAAN-facing aggregations exclude un-assessed hazards entirely;
   airline-facing displays show "Not assessed". Any future
   consumer of those three Hazard columns must handle NULL
   explicitly.
10. normalize_tolerability now returns "UNASSESSED" (a fourth
    value beyond LOW/HIGH/VERY HIGH) for None, empty, and
    unrecognized labels. It no longer fabricates "HIGH". Any
    caller that assumed three values must be updated. The
    deliberate design choice is that an unknown label is not
    the same as a high-risk label.
11. The earlier HANDOFF_GUIDE entry describing a PDF immutability
    typo ("Dc decision" in pdf_canvas.py) was stale documentation
    — the defect never existed in code. That entry has been
    removed. Future readers should not re-add it.
12. The VSR form currently uses the MOR-shaped wizard (sections:
    About You, Aircraft, Flight, Occurrence, Risk Assessment,
    Review & Submit). Per Sita Air's accepted SMS Manual Appendix D,
    the VSR reporter describes what was observed; they do not
    classify the occurrence. The form should match Appendix D's
    simple single-page layout. Queued as Project D.

## Follow-ups (prioritized)
### Active projects (multi-session)
1. Project B — tenant-configurable tolerability grid and
   follow-up windows. Multi-session. Recon first.
2. Project C — CAN auto-derivation + threshold-scheme
   deprecation on the hazard path.
3. Project D — Report intake forms aligned to Sita Air's
   accepted manuals (VSR first, then MOR).

### Tier 1 — This week
1. Tenant-user VSR smoke test — verify the deployed fb4bb3b
   build accepts VSR submissions with a real tenant context
   (the earlier test was done as Super Admin, which has no
   tenant).
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

### Tier 2 — This month
1. Safety Deficiency service + routes: the SafetyDeficiency
   model exists (db_models.py:725-774) with the right columns
   but has no service layer and no API. Needs
   SafetyDeficiencyService and /api/v1/deficiencies/* routes.
2. Exposure data model: no first-class table for operator
   flight movements (FMs) and flight hours (FHs) per period.
   Needed for N-HRC per-10,000 rate calculations. Add an
   OperatorExposure table plus a route and minimal UI for
   operators to declare monthly exposure.
3. Component score edge cases — verify null-data handling.
4. Migrate google.generativeai to google.genai (deprecation warning
    in every Render startup)
5. Add favicon.ico to backend to fix 404 in logs
6. Consider removing ?appcheck=false debug flag from firebase.js
    (documented in source but should not be in production)
7. **Bug B — resync contract** (production_seed.py:334-343):
    "tenant exists in Postgres → resync instead of reject" is
    dead code. Decide: fix the backend or fix the copy.
8. **Frontend audit Fix 2-4** — smaller HIGH-priority items.
9. Multi-tenant routing test — Air Dynasty + Saurya
10. Adaptive chart granularity — day/week/month/year buckets
    based on selected period. Spec agreed: <=60d daily,
    61-180d weekly, 181-365d monthly, >365d yearly.

### Tier 3 — Next quarter
1. Airline Safety dashboard rebuild — after the Safety
    Deficiency service and Exposure data model land (Tier 2
    items 1-2).
2. CAAN dashboard finalization — regulator view; aggregate-only.
    Add the N-HRC KPI card, per-operator drilldown, state EI
    score, and the other cards identified during this session.
    Multi-session.
3. AE dashboard finalization — parked this session pending the
    marketing/demonstration framing being fully specced. The
    AE dashboard is a marketing artifact for prospective
    customer airlines as well as a regulatory intelligence
    tool.
4. Firestore cleanup (bulk): ~15 guarded mirror blocks,
    firestore_deleted response fields, ~10 test functions
    pinning dead behavior. Multi-session project.
5. Frontend audit Fix 1 — api/client.js App Check attachment
    + token/tenant failure logging. NOTE: App Check work must
    be verified on the deployed site (see gotcha 7).
6. AE dashboard RCA seeder enrichment — add factual_review
    + rca narrative to the demo CAP. Seeder-only change.
7. Remove /admin/* App Check bypass, then enable Firebase App Check
    enforcement
8. Tenants list slow-refresh — backend aggregates run per
    tenant; consider batching.
9. Replace demo users with real users
10. Upgrade Render + Supabase tiers (cold-start delay)
11. join.html production scrutiny
12. PSOE scope enforcement audit
13. Retired role cleanup — multi-session project. Includes:
    (a) AIRLINE_ADMIN decommission across ~98 references in
    ~58 files (60 backend, 38 frontend); (b) fix
    get_accountable_executive in auth.py to allow
    ACCOUNTABLE_EXECUTIVE (own tenant), drop CROSS_TENANT and
    AIRLINE_ADMIN; (c) STAFF retirement from code; (d)
    SAFETY_OFFICER -> OFFICER stored-claim migration; (e)
    remove the SAFETY_OFFICER shim. One coordinated project
    because they share root cause: role-name drift not yet
    reconciled.
14. _cap_to_dict signature shape inconsistency — three
    shapes for ae_signature across three read paths (bool /
    full dict / name string). Deferred refactor; needs a
    plan for how to unify without breaking any of the six
    callers of _cap_to_dict.
15. Test file updates — ~18 test files pin the SAFETY_OFFICER
    literal; several pin old AE menu shape (test_ae_narrow_menu)
    and SAFETY_OFFICER -> ALL mapping (test_nav_config). Update
    to match the shim + new nav shape.
16. Standardize on one logging library (currently mixed loguru +
    stdlib)
17. Cosmetic debt: alert() used for success confirmation in
    submitAeDecision (ae-dashboard.html). No toast idiom
    exists in the file; consider adding a shared one.
18. Full production hardening review
19. AE dashboard Trends section — feature planned but not yet
    built. The dead nav item that pointed to a nonexistent
    #trends anchor was removed in 03b485b, so the defect is
    closed, but the underlying feature was never implemented.
    Per the earlier session's design note, Trends content is
    scoped to Annex 13 / Annex 19 / Doc 10159 and does not
    include manpower or finance. Candidate charts: hazard
    identification rate over time by taxonomy family,
    residual risk distribution movement between tolerability
    bands, top SPIs, AE decision trend, SMS maturity trend.
    To be specced as part of the AE dashboard rebuild.
20. Refactor HANDOFF_GUIDE.md: move historical session updates into
    docs/handoffs/YYYY-MM-DD.md and keep HANDOFF_GUIDE.md focused on
    current state and the queued list. The session-update log is now
    five entries and will keep growing. Small, one-time.

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
Last updated: 2026-10-01
HEAD at time of writing: fb4bb3b

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
  decommission queued (see Follow-ups, Tier 3 item 13)
- get_accountable_executive (auth.py) is broken and unused
  except verification.py:76; fix folded into the same cleanup

### Deploys
- Firebase Hosting #28 on cb4d875 (31s, green)
- Render #30 on b4f8770 (1m55s, Live)

### First task queued for next session
- Confirm git state, then txt queue item 1 (PDF typo fix).
  See Follow-ups, Tier 1.

## Session Update — 2026-09-30

### Commits landed this session
- bc29bd1 — dashboard cleanup pass (AE and CAAN)
- d5f1161 — SRAM severity letters + aggregation null-safety
- 03b485b — dead Trends nav item removed from AE
- a33ebf5 — un-assessed hazards must not count as high-risk
- b4523ae — hazard detail renders "Not yet assessed"

### Reverted work (documented for history)
An earlier attempt to null the hazard create-path tolerability
writes was reverted because the blast-radius check found 11
consumer sites. The full-scope fix was done properly in
a33ebf5.

### Key architectural decisions recorded this session
- SRAM is the sole writer of hazard tolerability
  (risk_level, risk_outcome, tolerability_tier). The hazard
  create and update paths do not write these; they stay NULL
  for a registered-but-un-assessed hazard.
- normalize_tolerability returns UNASSESSED (not HIGH) for
  None, empty, and unrecognized labels.
- Un-assessed hazards are an airline-internal workflow state.
  They have no value to CAAN. CAAN-facing aggregations
  exclude them entirely; airline-facing displays show
  "Not assessed".
- The domain workflow is: report → Safety Dept triage →
  Hazard Register (registered, un-assessed) → SRAM analysis
  (produces tolerability) → Risk Register. Tolerability is a
  stage-2 output, not a stage-1 one.
- Priority derivation on the hazard create path should be by
  consequence (Accident→H, Serious Incident→M, Incident→L), per
  CAAN SRM Manual §2.2. Not yet implemented in code — the
  current create form takes operator-entered priority directly.
  Queued.

### Deployments
- Firebase Hosting: run #31 on b4523ae (hazard detail page)
- Render backend: a33ebf5 (hazard tolerability fix)

### Known follow-ups (not in this session)
- Priority derivation by consequence (CAAN §2.2) is not yet
  implemented. Queued as the first task for the next session.
- The "SMS Health: Healthy" chip on the AE dashboard
  contradicts the SMS Maturity card's "Watch" state. Both
  read from the Module 1 survey but apply different
  thresholds or read different fields. To be resolved as
  part of the AE dashboard rebuild.

### First task for the new session
- Confirm git state (git log --oneline -5, git status,
  git log origin/main --oneline -1). Then choose from the
  queue. Recommendation: item 1 (priority derivation by
  consequence) — it is small, it closes the last correctness
  gap in the hazard pipeline, and the CAAN SRM Manual §2.2
  mapping is unambiguous.

HEAD at time of writing: b4523ae

## Session Update — 2026-10-01 (morning)

### Commits landed this session
- fb4bb3b — feat(hazard): derive priority from consequence
  (CAAN SRM §2.2)

### Context on this session's work
This commit closed the priority-derivation correctness issue
that was the last item in the hazard pipeline. It replaces two
inconsistent rules (operator-selected priority on the create
form; risk-index bands in the report auto-create path) with
the CAAN SRM Manual §2.2 rule, which is also what Sita Air's
accepted SMS Manual §5.5 (item 7) prescribes: priority is
derived from the Annex 13 occurrence category of the reported
or projected Unsafe Event / Consequence.

### Key architectural decisions recorded this session
- Priority derivation is a service-layer concern
  (derive_priority_from_consequence in hazard_service.py).
  The helper is the single source of truth. The create form
  and the report auto-create path both call it.
- Priority is a derived output, not a client input, on the
  hazard create path. HazardCreate.priority is now Optional
  with default None (accepted for backward compatibility,
  ignored by the service). HazardUpdate.priority remains
  available for manual override after review.
- The reporter does not classify the occurrence. The VSR form
  no longer asks for "Occurrence Type" — that field is the
  Safety Department's classification, not the reporter's.
  Sita Air's accepted VSR template (Appendix D) confirms this.
- Three follow-up projects are queued and scoped:
    Project B — tenant-configurable tolerability grid and
      follow-up windows. The grid is currently hardcoded in
      four places (risk_calculator.py, srm_engine.py,
      schemas/tenant_sms.py, hazard_service.py); the follow-up
      windows are hardcoded in hazard_service.py. Sita Air's
      manual differs from CAAN's: 1A is Acceptable (not
      Tolerable); the L window is 30 days (not 15). Both need
      to be per-tenant configurable.
    Project C — CAN target_completion_date auto-derivation
      from hazard priority via the tenant's configured
      windows, plus deprecation of the threshold-based risk
      classification scheme on the hazard path (hazards should
      use the cell grid everywhere).
    Project D — Report intake forms aligned to Sita Air's
      accepted manuals. VSR: replace the MOR-shaped wizard
      with Sita Air Appendix D (single-page, simple). MOR:
      enrich to match Sita Air Appendix C. VSR first.

### Deployments
- Firebase Hosting: run #32 on fb4bb3b
- Render backend: fb4bb3b

### Known follow-ups (not in this session)
- Projects B, C, and D as noted above.
- On the deployed site, the smoke test of fb4bb3b was partially
  run (create-form derivation verified visually). The VSR form
  smoke test was performed as Super Admin (no tenant assigned);
  a tenant-user smoke test to confirm submission still works is
  pending.
- No HTTP-level test asserts the fastapi 422 fix for
  HazardCreate.priority (the schema is now Optional). The fix is
  confirmed by the schema change and by service-level tests.

### First task for the new session
- Confirm git state (git log --oneline -5, git status,
  git log origin/main --oneline -1). Then begin Project B with
  a read-only reconnaissance of the four tolerability grids and
  the follow-up windows, so we can plan the config
  consolidation. The recon prompt will be provided separately.

HEAD at time of writing: fb4bb3b
