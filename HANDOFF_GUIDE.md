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

## Session Update — 2026-10-01 (afternoon/evening)

### Commits landed this session

Ordered oldest to newest. All pushed to `origin/main`.

- `ab73247` — chore(project-e): create public/_hold/ for parked files pending chain verification
- `cb14de5` — chore(project-e): move Batch 1 files into public/_hold/
- `bcaa9c2` — fix(can_cap): correct department nav, hero title, and register back-links
- `7c922be` — fix(can_cap): remove duplicate header-bar buttons on register pages
- `cb384c0` — fix(dept-master-register): let hero subtitle reflect logged-in department
- `0d24d5b` — chore(project-e): move Batch 2 files into public/_hold/

HEAD at time of writing: `0d24d5b`.

Base for the session: `fb4bb3b` (the priority-derivation commit from the
morning, which was the starting HEAD when this session began).

### Context — what this session was about

This session ran three strands of work in parallel:

1. **Project E (HTML surface inventory and clean-up).** A project to
   inventory all 87 `.html` files under `public/`, determine which are
   live, which are stale, and which are dead, and then park the dead
   ones in a `public/_hold/` folder so the working tree reflects only
   the live surface. The project runs in numbered batches. Each batch
   is one commit, verified on the deployed site after push.

2. **Module 2 (can_cap/) fixes.** Three UI bugs found during
   verification of Project E's Batch 1. The CAN/CAP pages had wrong
   nav on some pages, wrong hero titles on some, a wrong back-link on
   the CAP review page, and redundant header-bar buttons duplicating
   nav entries. All fixed across three commits.

3. **Department register subtitle.** Found during verification of the
   Module 2 fixes. `dept-master-register.html` was showing a static
   subtitle instead of the logged-in user's department. Fixed by
   removing the static `heroSubtitle` so the shell derives it from the
   user's claims.

### Project E — current state

Project E is **mid-flight**. Two of four planned batches are done.

**Batch 0 (`ab73247`) — done.** Created `public/_hold/`, added its
`README.md`, and added `public/_hold/` to `.gitignore`. The README is
the one tracked file inside the folder; the parked HTML files are
ignored.

**Batch 1 (`cb14de5`) — done.** Parked four files with no live inbound
references:

- `public/hazards/index.html` → `public/_hold/hazards/index.html`
- `public/hazards/create.html` → `public/_hold/hazards/create.html`
- `public/test-portal.html` → `public/_hold/test-portal.html`
- `public/portal/survey/index.html` → `public/_hold/portal/survey/index.html`

**Batch 2 (`0d24d5b`) — done.** Parked three more files:

- `public/demo-contract.html` → `public/_hold/demo-contract.html`
- `public/portal/index.html` → `public/_hold/portal/index.html`
- `public/dashboard/shared/shell.html` → `public/_hold/dashboard/shared/shell.html`

The `public/portal/` folder is now empty (both `portal/` and its
`survey/` subdirectory have no remaining files). Empty directories
were left in place; Firebase Hosting serves files, not directories,
so an empty path falls through the catch-all rewrite to `/index.html`.

**Batch 3 (`3b45158`) — done.** Parked three pages and retired
the two dormant frontend tests that read them from disk:
`admin/dashboard.html`, `dashboard/safety-dashboard.html`,
`dashboard/dept-head-dashboard.html`, plus
`frontend-tests/test_dept_head_dashboard.js` and
`frontend-tests/test_safety_dashboard.js`. Updated
`DASHBOARD_CONTRACT.md`, `IMPLEMENTATION_ROADMAP.md`, and
`docs/status.md` to record the supersessions. Fixed a stale mirror
in `backend/tests/test_rbac_claims.py:104`
(`/admin/dashboard.html` → `/admin/production-setup.html`), which
did not match the live router at `firebase.js:655`.

**Batch 4 — pending, separate.** Park `public/aviasdcps.html` and the
`public/views/*` family (13 files). This is the project's origin (the
Annex 19 data-collection shell that the SMS application grew out of)
and is confirmed not to be in any live chain. It is a larger commit
than Batch 3 and should be its own session.

### Module 2 fixes — current state

All three Module 2 fixes are done and verified on the deployed site.

**`bcaa9c2` — nav, title, back-links, dept nav entries.**

- `can_detail.html` and `caps.html` were missing the
  `<script src="/js/nav-config.js">` include, so the shell fell to its
  legacy `NAV_ITEMS` and rendered the Safety Manager nav for
  department users. Added the include to both.
- `can_detail.html`, `cans.html`, and `caps.html` were missing the
  `updateShellTenant(...)` call, so the hero title showed "Unknown".
  Added the standard call (matching `my-tasks.html:176-177`) to all
  three. Each page's `onAuthStateChanged` handler was made `async` and
  given a `const tokenResult = await user.getIdTokenResult();` line,
  because none of the three previously called `getIdTokenResult()`.
- `cap_review.html` top back-link retargeted from `/can_cap/cans.html`
  ("Back to CANs") to `/can_cap/caps.html` ("Back to CAP Register").
  The bottom link remains "Back to Related CAN" →
  `/can_cap/can_detail.html?id=<can_id>`.
- `nav-config.js` `dept_workspace` group extended from two items to
  four: added `dept-can-register` → `/can_cap/cans.html` and
  `dept-cap-register` → `/can_cap/caps.html`. The existing IDs
  (`dept-tasks`, `dept-register`) were preserved.
- `my-tasks.html` header-bar Master Register button removed; its
  rewrite block also removed. The nav entry is now the single source
  for that link.

**`7c922be` — duplicate header buttons.**

- `cans.html` and `caps.html` each rendered a "My Tasks" and a
  "Master Hazard Register" button in the header bar. Both duplicate
  nav entries for the audiences that reach these pages. Removed both
  buttons on both pages.

**`cb384c0` — department register subtitle.**

- `dept-master-register.html` set
  `SHELL_CONFIG.heroSubtitle = 'Department CAN · CAP Register'`,
  which the shell's post-token repaint at `shell.js:982` treats as
  the highest-priority value, overriding
  `getDepartmentLabel(claims)`. Removing the static value lets the
  shell fall through to the department label, so a 145 user sees the
  department name instead of the static string.

### Verified on the deployed site

- `safety.html` — Safety Manager hub, correct nav, all sections render
- `dashboard/ae-dashboard.html` — AE dashboard, SMS Maturity card,
  Executive Decisions card, escalation queue, decision ledger, PDF
  export
- `caan.html` — CAAN dashboard
- `dashboard/my-tasks.html` — department Workspace nav with four
  entries, Submit MOR button present, Master Register header button
  gone
- `can_cap/cans.html` — correct department nav, title resolves, table
  renders
- `can_cap/caps.html` — same
- `can_cap/can_detail.html` — correct department nav, title resolves
- `can_cap/cap_review.html` — top link now "Back to CAP Register"
- `dashboard/dept-master-register.html` — subtitle now reads the
  logged-in department (verified for the 145 user)

### Key decisions recorded this session

- **The four dashboard hubs are:** `public/safety.html` (Module 2 hub,
  Safety Department cockpit), `public/dashboard/ae-dashboard.html`
  (cross-module executive view), `public/caan.html` (Module 3 hub,
  regulator view), `public/dashboard/my-tasks.html` (Module 2
  departmental slice). Confirmed from `firebase.js:644-703`
  (`getRoleDestination`) and the nav config.
- **The three modules are:** Module 1 (SMS Survey), Module 2
  (Hazard/Risk Management), Module 3 (PSOE Audit). Module access is a
  hard per-tenant boundary.
- **The `admin/*` surface is platform operator tooling** for the
  SUPER_ADMIN, not a module. It provisions tenants and users, seeds
  demo data with `is_demo=true`, and purges demo data once the pilot
  walkthrough is complete.
- **`is_demo=true` on subordinate rows is the purge marker.** Sita
  Air's tenant row is `is_demo=false`; its demo content is
  `is_demo=true` and will be purged before handover. Production rows
  are written `is_demo=false` by construction.
- **`flight_diversions/*` is live-intended but currently orphaned.**
  Wiring it into the nav is a queue item, not part of Project E.
- **`aviasdcps.html` and `views/*` are the project's origin**, not the
  current surface, and are confirmed not to be in any live chain.
- **The dashboard subtitles should reflect the logged-in user's
  department**, per the pattern already established on `my-tasks.html`
  and now applied to `dept-master-register.html`.
- **The `nav-config.js` `dept_workspace` group is the department's nav
  source of truth.** Header-bar buttons that duplicate entries in that
  group should be removed, not retargeted.

### Pre-existing issues carried forward

These are not in scope for this session, but they are relevant to
Project B's design and should not be lost.

1. **Module-gate leak.** All four dashboard hubs render module-tagged
   data without a Module 1 / 2 / 3 access check.
   `/api/v1/dashboard*` is absent from
   `rbac_middleware.py:17-28` (`ENDPOINT_MODULE_MAP`), so the
   middleware gate that protects `/api/v1/surveys`,
   `/api/v1/hazards`, `/api/v1/reports`, `/api/v1/cans`,
   `/api/v1/caps`, `/api/v1/regulator`, `/api/v1/psoe`,
   `/api/v1/spi/state`, `/api/v1/nhrc/state` does not touch the
   aggregate endpoints. The AE dashboard's SMS Maturity card renders
   Module 1 data without a Module 1 gate; `safety.html` renders
   Module 2 data without a Module 2 gate; `caan.html` renders Module 3
   data behind a role check only.

2. **`nav-config.js` fail-open.** `getVisibleNav(user)` with no
   `moduleAccess` argument skips module filtering entirely
   (`nav-config.js:250-251`). Several `shell.js` call sites pass no
   argument (e.g. `shell.js:516`), so tagged entries render
   unconditionally.

Both are documented in the Project E Phase 2 reconnaissance and are
relevant to Project B's tenant-configurable tolerability grid design
because the module boundary is one of the things Project B will touch.

### Queue for the next session

**First task — confirm git state.** Run:

- `git log --oneline -5`
- `git status --porcelain`
- `git log origin/main --oneline -1`

Expect HEAD at `0d24d5b` (or a later commit if the handoff itself has
been committed), working tree clean.

**Second task — confirm Batch 2 verification.** If it is not already
done, run the five checks: the four dashboard hubs load, and
`admin/login.html` → `admin/production-setup.html` works.

**Third task — Batch 3 reconnaissance.** Read-only. See the "Batch 3 —
pending" section above for the files and the reasons it needs doc and
test coordination.

**Fourth task — Batch 4.** Park `aviasdcps.html` and `views/*` as a
separate commit.

**Fifth task — session-update consolidation** after Batch 4.

### Deployments this session

- Firebase Hosting: redeployed on `ab73247`, then on each subsequent
  push to `main`
- Render: no backend changes, so no Render deploys this session

### HEAD at time of writing

`0d24d5b`

## Nav Submenu Consistency — new thread opened 2026-10-02

### Context

Batch 3 verification of Project E surfaced a cluster of navigation
inconsistencies on the Safety Manager (TENANT_ADMIN) surface. Several
pages reached via the Performance and Administration submenus render a
different nav from the one that offered them. Two further submenu
entries lead to pages whose content is unwritten (SPI/SPT and N-HRC
KPIs). One submenu entry leads to a page that denies access to the
Safety Manager who reached it.

This is the same class of issue as the CAN/CAP nav bugs fixed earlier
in `bcaa9c2`, but broader: each submenu page appears to choose its own
shell setup independently, so pages from one nav group can render a
nav that belongs to a different group.

### Confirmed findings (from the Batch 3 verification)

1. **Performance → SMS Maturity renders a mixed-module nav.**
   `/dashboard/sms-maturity.html` (reached from
   `safety.html` → Performance → SMS Maturity) renders a nav that
   mixes Module 1, Module 2, and Module 3 entries
   (Home, SMS Maturity, Risk Management, Assurance, Reports, Promotion,
   Administration) instead of the Safety Manager nav the user came
   from.

2. **Performance → SPI/SPT content not developed.**
   `/dashboard/spi-dashboard.html` renders the page shell (title,
   Refresh button, "Leading Indicators", "Lagging Indicators",
   "SPI Trend (Last 6 Months)" headings) but no data or charts.

3. **Performance → N-HRC KPIs content not developed.**
   `/dashboard/nhrc-kpis.html` renders the page shell (title, Refresh
   button, "Total Hazards", "Action Required", "Stable / OK",
   "Avg Risk Index" labels, "N-HRC Trend (Last 6 Months)" heading)
   but no values or chart.

4. **Administration → Team Management renders Access Denied for the
   Safety Manager.**
   `/settings/team.html` shows "Access Denied — Team management is
   available to the Safety Manager (Tenant Admin) and Department Admins
   only." while the logged-in user is `safety@sitaair.com.np`
   (TENANT_ADMIN / Safety Manager). The page's own access check is
   contradicting the nav that offered the link.

5. **Administration → System Settings renders a mismatched nav.**
   `/administration.html` renders fine in the body (ICAO Risk Matrix
   Configuration, SMS Survey Management, further sections below), but
   its nav is the SMS Maturity-style nav, not the Safety Manager nav
   the user came from. Additionally, `/settings/team.html` renders a
   third nav shape (Home, Key Indicators, SMS Maturity, Risk Trends,
   Top Hazards, N-HRC KPIs, SPI/SPT) — a different vocabulary entirely.

### Owner decisions

- **Full inventory required.** Rather than fix these five items
  piecemeal, run a read-only reconnaissance that inventories every
  entry in `public/js/nav-config.js` — what page it lands on, what nav
  that page renders, and whether the rendered nav matches the offering
  nav. Produce a mismatch table, then triage.
- **SPI/SPT and N-HRC KPIs are placeholders.** Their nav entries are
  valid; the content is queued. Add both to a todo list for future
  work, not to this refinement thread.
- **Batch 4 first, then nav recon.** Project E Batch 4
  (`aviasdcps.html` + `views/*`) is unaffected by these findings and
  should complete before the nav thread opens.

### Todo — content development (queued, not in this thread)

- Build `dashboard/spi-dashboard.html` content — Leading Indicators,
  Lagging Indicators, SPI Trend chart, backed by the existing SPI/SPT
  endpoints if they exist; new endpoints if they do not.
- Build `dashboard/nhrc-kpis.html` content — Total Hazards, Action
  Required, Stable / OK, Avg Risk Index, N-HRC Trend chart.
- Both pages already have shells; the work is data wiring plus chart
  rendering.

### First step for the nav thread

A read-only reconnaissance prompt will inventory every submenu entry
across `nav-config.js`. It will quote, for each entry:

- The submenu label and the parent group it appears under.
- The href and the file it resolves to.
- The shell includes that file loads.
- The `SHELL_CONFIG` block on that file.
- The nav the page actually renders (by inspection of the shell
  it loads and the nav-config it consumes).
- Whether the rendered nav matches the offering group's nav, or is
  different.

The result is a mismatch table that makes the full scope visible.

### HEAD at time of writing

`1379e07` (pending push).

## Project E — Complete (2026-10-02)

Project E (HTML surface inventory and clean-up) is complete. All four
batches have landed:

- **Batch 0** (`ab73247`) — created `public/_hold/`, its README, and
  the `.gitignore` rule.
- **Batch 1** (`cb14de5`) — parked four files with no live inbound
  references.
- **Batch 2** (`0d24d5b`) — parked three more files.
- **Batch 3** (`3b45158`) — parked three superseded pages and retired
  the two dormant frontend tests that read them; updated
  `DASHBOARD_CONTRACT.md`, `IMPLEMENTATION_ROADMAP.md`,
  `docs/status.md`, and fixed a stale routing mirror in
  `backend/tests/test_rbac_claims.py:104`.
- **Batch 4** (`0196e33`) — parked `aviasdcps.html` and the fifteen
  `views/*` templates. Final batch.

`public/_hold/` now contains the parked HTML files at their original
relative paths, plus a tracked `README.md` inventory. The folder is
git-ignored except for the README. Restore procedure: `git mv` each
file back from `_hold/` to `public/` at its original path.

### What remains queued

- **Nav Submenu Consistency thread** (opened 2026-10-02, see the
  section above at line ~810). Next step: run the read-only
  reconnaissance to inventory every submenu entry across
  `nav-config.js`, produce a mismatch table, triage, then fix.
- **Todo list** for two placeholder pages whose content is unwritten:
  `dashboard/spi-dashboard.html` and `dashboard/nhrc-kpis.html`.
  These are feature-development items, not nav-thread items.
- **Project B** — tenant-configurable tolerability grid and follow-up
  windows. Design substantially shaped by prior reconnaissance and
  the decisions recorded in the 2026-10-01 (afternoon/evening) session
  update. Has not been started in code.

### HEAD at time of writing

`0196e33` (pending push).

## Session Update — 2026-10-02 (afternoon/evening) — CAAN rename, State Regulator nav, shell consolidation

### Commits landed this session

Ordered oldest to newest. All pushed to `origin/main`.

- `ab73247` — chore(project-e): create public/_hold/ for parked files pending chain verification
- `cb14de5` — chore(project-e): move Batch 1 files into public/_hold/
- `0d24d5b` — chore(project-e): move Batch 2 files into public/_hold/
- `3b45158` — chore(project-e): move Batch 3 pages into public/_hold/ and update references
- `1379e07` — docs(handoff): record Project E Batch 3 as done
- `b4e90ea` — docs(handoff): record Nav Submenu Consistency thread
- `0196e33` — chore(project-e): move Batch 4 into public/_hold/ (aviasdcps + views)
- `8c23d02` — docs(handoff): record Project E completion
- `8d35994` — fix(nav): restructure PSOE Audit as a per-tenant Module 3 entry
- `1851842` — refactor(caan): rename State Regulator pages to state-neutral filenames
- `f184f46` — feat(nav): State Regulator flat four-entry nav (hub-and-spoke)
- `f52d46d` — fix(state): hub page CSS includes and risk register hero fallback
- `ef15547` — refactor(css): consolidate shell header chrome to shell.css
- `4085474` — refactor(css): move header layout to shell.css; stack header rows
- `e7e5527` — fix(css): stretch header children to full width so internal alignment applies

HEAD at time of writing: `e7e5527`.

### Workstream 1 — Project E (complete)

Project E was opened to inventory the 87 `.html` files under
`public/`, determine which are live, which are superseded, and which
are dead, and park the dead ones in `public/_hold/`. It is now
complete across four batches plus a session-close entry.

**Batch 0** (`ab73247`) — created `public/_hold/`, its README, and
the `.gitignore` rule. The folder is git-ignored except for the
README, which is force-added.

**Batch 1** (`cb14de5`) — parked `hazards/index.html`,
`hazards/create.html`, `test-portal.html`,
`portal/survey/index.html`.

**Batch 2** (`0d24d5b`) — parked `demo-contract.html`,
`portal/index.html`, `dashboard/shared/shell.html`.

**Batch 3** (`3b45158`) — parked `admin/dashboard.html`,
`dashboard/safety-dashboard.html`, `dashboard/dept-head-dashboard.html`;
retired the two dormant frontend tests
(`test_dept_head_dashboard.js`, `test_safety_dashboard.js`); updated
`DASHBOARD_CONTRACT.md`, `IMPLEMENTATION_ROADMAP.md`,
`docs/status.md`; fixed a stale routing mirror in
`backend/tests/test_rbac_claims.py:104`.

**Batch 4** (`0196e33`) — parked `aviasdcps.html` and the fifteen
`views/*` templates. Final batch.

Restore procedure is in `public/_hold/README.md`.

### Workstream 2 — PSOE Audit as a per-tenant Module 3 nav entry (`8d35994`)

Module 3 is a per-tenant subscriber module. Two audiences reach the
PSOE Audit surface: CAAN can conduct an audit of a specific tenant,
and a tenant can self-audit. CAAN's aggregated oversight applies to
Module 1 and Module 2 only, not Module 3.

Changes:

- Removed PSOE Audit from the CAAN-only `regulator` group in
  `nav-config.js`.
- Removed the `module_c_regulator` gate from `regulator` (CAAN's
  aggregated Module 1/2 views are not gated by a tenant's Module 3
  subscription).
- Added an `oversight` group with `roles: ['SAFETY', 'CAAN']`,
  `module: 'module_c_regulator'`, containing the PSOE Audit entry.
- `shell.js`: threaded the tenant module bag into both
  `getVisibleNav` call sites. Previously the bag was resolved and
  stored but never passed, so every module gate was inert.

Pre-existing unrelated test failure: `test_nav_config.js` has a
stale AE-menu assertion (`test_ae_narrow_menu`, line 59) that was
failing before any of this session's work. Not touched.

### Workstream 3 — CAAN → state-neutral filenames (`1851842`)

The State Regulator surface is a subscriber-facing product that will
be sold to multiple states. Renamed four CAAN-specific filenames to
state-neutral paths:

```
caan.html                         → state-oversight.html
dashboard/caan-sms-maturity.html  → dashboard/state-sms-maturity.html
caan-state-risk.html              → state-risk-register.html
audits/psoe.html                  → psoe-audit.html
```

Four 301 redirects added to `firebase.json` so old URLs continue to
resolve.

References updated across the platform:

- `public/js/firebase.js` — the CAAN_SMD role router return.
- `backend/tests/test_rbac_claims.py` — the router mirror.
- `public/js/nav-config.js` — four hrefs (including the oversight
  entry found in extended reconnaissance).
- `public/can_cap/can_detail.html` — the live PSOE link.
- `public/js/shell.js` — the legacy `NAV_ITEMS` PSOE path.
- `backend/app/services/groq_copilot.py` — the copilot page-key
  lookup table (`:135`) and its docstring example. The copilot's
  page-aware behaviour depends on this key; leaving it stale would
  have silently lost page-scope instructions for the State oversight
  page.
- `backend/tests/test_copilot.py` and `test_admin_feedback.py` —
  test strings keying on the old page filename.

`public/audits/` is now empty; folder left in place.

**Pattern to remember:** the copilot page-key table in
`groq_copilot.py` is a dependency that future page renames must
update. If a page's filename changes, the key must change with it.

### Workstream 4 — State Regulator flat four-entry nav (`f184f46`)

The State Regulator surface was restructured as hub-and-spoke with a
flat four-entry nav, identical on every State Regulator page:

```
Home           → /state-oversight.html
SMS Maturity   → /dashboard/state-sms-maturity.html
Safety Trends  → /state-safety-trends.html    (new hub)
PSOE           → /psoe-audit.html
```

- `state-safety-trends.html` is a new hub page — a menu with three
  cards linking to its spokes (`state-risk-register.html`,
  `dashboard/spi-dashboard.html`, `dashboard/nhrc-kpis.html`). No
  data on the hub.
- `shell.js` gained a `suppressAutoHome` config key so a page can
  opt out of the automatic Home link (which pointed at
  `/safety.html`, wrong for a State Regulator user).

Known follow-ons documented in the commit message:
- `dashboard/spi-dashboard.html` and `dashboard/nhrc-kpis.html`
  still render the shared `nav-config.js` nav. A CAAN user reaching
  them from the Safety Trends hub sees a different nav from the hub.
- The CAAN-specific entries in `nav-config.js` (regulator group,
  `caan-dashboard` item, `oversight` group) are inert for CAAN after
  this change but remain as fallback for other roles.
- The Operator-side PSOE flow on `psoe-audit.html` now sees the State
  Regulator nav. If that is wrong for operators, a role-aware nav
  variant is the follow-on.

### Workstream 5 — Hub page CSS and risk register hero (`f52d46d`)

- `state-safety-trends.html` was missing four shell includes
  (`tenant-overrides.css`, `chart.js`, `chart-theme.js`,
  `theme.css`). Added in the order used by `state-oversight.html`.
- `state-risk-register.html` briefly showed "Unknown" during the
  initial hero paint — its `SHELL_CONFIG` carried no `tenantTitle` or
  `heroSubtitle`, so the shell fell through to
  `airlineNameFromEmail()`, which cannot derive a name from a
  regulator's email domain. Added both as fallback values. The
  existing dynamic `updateShellTenant` call that refines the title
  once the regulator metadata resolves is unchanged.

### Workstream 6 — Shell header consolidation (`ef15547`, `4085474`, `e7e5527`)

Three commits that together settled the shell header, after several
symptoms surfaced during CAAN page verification.

**The mismatch (`ef15547`).** `shell.js` builds the header element
with `className = 'app-header'`. `shell.css` styled `.shell-header`
— a class that no live element carries. So the shell's own stylesheet
never styled the shell's own header. The navy background came from a
workaround rule in `dashboard-responsive.css:17`
(`.app-header { position: fixed; background: #1a237e; ... }`) that
was load-bearing for seven pages and not loaded on the three CAAN
pages that lacked it. The newly-created `state-safety-trends.html`
rendered teal because it got the fresh CSS without the workaround.

Fix: made `shell.css` the single owner of the base `.app-header`
rule (navy `var(--shell-navy)` = `#072535`, `position: sticky`),
deleted the ten dead `.shell-header` descendant rules, removed the
base `.app-header` rule from `main.css`, `theme.css`, and
`dashboard-responsive.css`, and added `shell.css` to the seven
pages that had been relying on the workaround.

**Layout consolidation (`4085474`).** `shell.css` still defined none
of the header's internal layout classes — `.header-top`,
`.header-left`, `.header-right`, `.header-brand`, `.header-nav`,
`.nav-link`, `.nav-dropdown`, `.dropdown-toggle`, `.dropdown-menu`,
`.header-divider`. All of those lived only in
`dashboard-responsive.css`. So the CAAN pages that load only
`shell.css` rendered a default-block header. This commit moved the
header-layout rules to `shell.css`, added `flex-direction: column`
to `.app-header` so its three children (top row, divider, nav row)
stack as rows, and removed the stale `.main-content { margin-top:
94px }` rule from `dashboard-responsive.css` (that margin existed to
clear the old `position: fixed` header; it produced a blank band
above the sticky header).

**Alignment fix (`e7e5527`).** `align-items: center` on
`.app-header` (added in `4085474`) shrank each child to content
width and centred it, so `.header-top { justify-content:
space-between }` and `.header-nav { justify-content: center }` had
no width to distribute — the brand, user email, and Logout clustered
in a centred group. Changed to `align-items: stretch`, so each child
fills the header's width and the internal alignment rules take
effect.

Verified on the deployed site: `/safety.html` (tenant) and
`/state-safety-trends.html` (regulator) both render brand left, user
email + Logout right, full-width gold divider, nav row centred.

### Key decisions recorded this session

- **Subscriber model.** The platform's audience is two subscriber
  types: tenants (operators) and state regulators. They are both
  "tenants" in the data model — a state regulator has a tenant row,
  a category, and scope that differ from an operator's. The
  SUPER_ADMIN (the vendor) is not a subscriber; the `admin/*` surface
  is vendor-side tooling.

- **State Regulator nav is page-local, not `nav-config.js`.** The
  five CAAN pages declare their own four-entry nav via
  `SHELL_CONFIG.nav`. The shared `nav-config.js` continues to serve
  the tenant roles. Future State Regulator pages use the same
  four-entry array.

- **Top-bar layout stays.** The abandoned `dashboard/shared/shell.js`
  is a sidebar shell. It is not adopted. The top-bar shell
  (`js/shell.js`) remains the platform's shell.

- **`shell.css` owns the whole header** — colour and layout.

### Outstanding follow-ons

1. ~~**Shared spokes role-aware nav**~~ — **RESOLVED 2026-10-03
   (`fa0e8a1`).** `dashboard/spi-dashboard.html` and
   `dashboard/nhrc-kpis.html` now declare `SHELL_CONFIG.navByRole`
   (the four-entry state set for `CAAN`/`SUPER`, falling through to the
   shared operator `NAV_CONFIG` otherwise). `shell.js` renders the
   role-keyed sets at build time and `applyRoleKeyedNav()` chooses one
   after the role resolves, with a role-aware auto-Home (state →
   `/state-oversight.html`, operator → `/safety.html`). No rebuild hook
   was added (Option B as designed). Verified live; see the 2026-10-03
   session entry below.

2. **Nav Submenu Consistency thread** — five issues recorded in the
   session's "Nav Submenu Consistency" entry (`b4e90ea`): SMS
   Maturity mixed nav, SPI/SPT and N-HRC KPI placeholder content,
   Team Management Access Denied, System Settings mismatched nav.
   Needs its own full inventory reconnaissance across
   `nav-config.js`.

3. **Remove now-inert CAAN entries from `nav-config.js`** — the
   `regulator` group, the `caan-dashboard` item, and the `oversight`
   group are inert for CAAN after `f184f46` but remain in place as
   fallback for other roles and other pages. Small cleanup, once we
   are confident nothing consults them.

4. **Park `dashboard/shared/shell.js`** — no live page loads it. One
   `git mv` into `_hold/`, alongside the earlier housekeeping.

### Test status

- `test_rbac_claims.py`, `test_copilot.py`, `test_admin_feedback.py`
  — 54 passed after the rename (commit `1851842`).
- `test_nav_config.js` — fails on a pre-existing stale AE-menu
  assertion (`test_ae_narrow_menu`, line 59). Present on `fb4bb3b`
  and earlier, before any of this session's work. Not modified.

### HEAD at time of writing

`e7e5527`

## Session Update — 2026-10-03 — Option B role-keyed nav shipped

### What shipped

The two State Regulator spokes now render the four-entry state nav for
state users instead of the shared operator `nav-config.js` nav:

- `public/dashboard/spi-dashboard.html`
- `public/dashboard/nhrc-kpis.html`

**Mechanism (Option B — role-keyed nav in `buildHeader`):** both pages
declare `SHELL_CONFIG.navByRole` with the state four-entry set under
`CAAN` and `SUPER` (and no `default` key, so unlisted roles fall through
to the shared `NAV_CONFIG`). `public/js/shell.js` gained:

- `buildNavRoleSet()` / `buildDefaultNavRoleSet()` — render every
  role-keyed set into the DOM at build time (`render all, gate later`).
- a new `else if (navByRole)` branch in the nav-source precedence, after
  `cfg.nav` and before `NAV_CONFIG`.
- `applyRoleKeyedNav()` — runs from `applyNavVisibility()` after claims
  resolve; shows the set matching `getUserRoleType(buildNavUser())`
  (`'CAAN'` / `'SUPER'`) and hides the rest, falling back to the
  `'default'` set. When the chosen set carries its own `Home` entry, the
  generic auto-Home (`/safety.html`) is hidden so the set's Home wins
  (state → `/state-oversight.html`, operator → `/safety.html`).
- `public/css/shell.css` — `.header-nav .nav-role-set { display: contents; }`
  so the wrapper is layout-neutral inside the flex nav row.

No Option A rebuild hook and no Option C role cache were added.

### Files changed

- `public/js/shell.js`
- `public/css/shell.css`
- `public/dashboard/spi-dashboard.html`
- `public/dashboard/nhrc-kpis.html`

108 insertions, 2 deletions.

### Commits

- `fa0e8a1` — `fix(nav): role-keyed State Regulator nav for SPI/N-HRC
  spokes (Option B)`.
- Pushed `e7e5527..fa0e8a1` to `main` (this range also carried the
  earlier local-only docs commit `71be813`). Committed directly on
  `main`; no feature branch and no merge commit were used.

### Verification result

- Deploy: GitHub Actions `Deploy Firebase Hosting`, run
  `37130875214` — **success** (~29s), head SHA `fa0e8a1`.
- Programmatic (live site, cache-busted):
  - `css/shell.css` contains `.nav-role-set` — yes.
  - `js/shell.js` contains `applyRoleKeyedNav` and `navByRole` — yes.
  - `dashboard/spi-dashboard.html` and `dashboard/nhrc-kpis.html`
    contain `navByRole` — yes.
  - `state-safety-trends.html` still has the flat four-entry
    `SHELL_CONFIG.nav` array and no `navByRole` — unchanged.
- Browser (SME, incognito, hard refresh): state user on both spokes →
  four state entries, Home `/state-oversight.html`, one row; operator
  user (`safety@sitaair.com.np`) on the N-HRC spoke → operator nav,
  Home `/safety.html`, no state-nav crossover, one row; state pages
  unchanged. **All checks pass.**

### Now resolved

The "Shared spokes role-aware nav" open item (previously Outstanding
follow-on #1) is closed.

## CAAN -> state rename — deferred backlog + decisions (recorded 2026-10-03)

### Deferred items (do before paid launch)

**A — RLS coverage gap.** 10 `public` tables have RLS enabled with **zero
policies** -> default-deny for any non-owner role: `audit_dispatches`,
`dead_letter_queue`, `feedback`, `hazard_assessments`, `hazard_capas`,
`hazard_rca_entries`, `hazard_rca_factors`, `invites`, `psoe_findings`,
`sms_dispatches`. Separately: the live policies read `auth.jwt()`
(Supabase JWT), **not** Firebase claims, and the backend connects as the
Supabase owner (`rls_forced = false` everywhere) -> RLS is bypassed on the
app path regardless.

**B — Unversioned RLS policies.** ~12 live policies have no repo source:
`audit_logs_admin_only`, `hfacs_nanocodes_read_policy`, `icao_adrep_read_policy`,
`psoe_questions_read_all`, `regulator_read_all`, `tenant_admin_all`,
`tenant_read_own`, `user_read_own`, `tenant_isolation_hazard_adrep`,
`tenant_isolation_hazard_hfacs`, `tenant_isolation_report_adrep`,
`tenant_isolation_report_hfacs`. Action: capture the live `pg_policies`
output into `supabase/migrations/` and add a `pg_policies` drift check.

### Exempt-identifier allowlist (NOT renamed)

Real-world identifiers and kept internal ids: `caanepal.gov.np`,
`caan.gov.np`, `ssp.caanepal.gov.np`, `smd@caanepal.gov.np`,
`smssurvey.gsacharya.com`, `sms.nac.com.np`; the stored tenant/regulator
slug `caan`; `caan-ops` (survey hostname alias); `caan-assd` / `caan-fssd`
(until removed by Plan B).

### Role model direction (Plan B — execution deferred)

`TENANT_ADMIN` is canonical and `AIRLINE_ADMIN` is its alias
(`RBAC_MODEL.md:27`); the code drifted to `AIRLINE_ADMIN`. Bring the code
back to the neutral canonical in Plan B. Do **not** touch it during the
CAAN -> state work.

### Seed scripts retired

`backend/seed/*` and `scripts/firebase/set-claims.js` are retired in favour
of `public/admin/production-setup.html` (`public/admin/setup/step*.html`) for
user/tenant/regulator provisioning.

### Scope decision

Product goal: stop showing "CAAN" in user-visible labels, and generalize the
auth claim `CAAN_SMD` -> `STATE_SMD`. Internal identifier renames (files, CSS
classes, DOM ids, API paths, tenant slug) are **out of scope** unless a
deliverable requires them — no user-visible benefit, real migration risk. The
tenant slug `caan` is kept (it keys the `uuid5`-derived tenant UUID and every
FK). RLS policies are deferred with items A/B.

**Phase 1 (accept `STATE_SMD` alongside `CAAN_SMD`) — in progress:** implemented
as backend boundary normalization (`resolve_user_context` maps
`STATE_SMD -> CAAN_SMD`), plus `STATE_SMD` added to `CROSS_TENANT_ROLES` /
`CANONICAL_ROLES` / `ALLOWED_USER_CREATE_ROLES` / `normalize_legacy_role` and
the `role_validation` regulator-exclusivity check. Claim flip is Phase 2 and
gated on Phase 1 deploy + verify.
