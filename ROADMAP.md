# Roadmap

This is the single merged roadmap for the AviaSAFE SMS Platform. It supersedes two prior overlapping files, both archived on 2026-10-07:

- `ROADMAP.md` (2026-10-05) — product roadmap and backlog.
- `IMPLEMENTATION_ROADMAP.md` (2026-10-02) — sequenced schema-note implementation plan.

The two files planned at different layers (product/backlog vs schema-note execution) and are complementary, not contradictory. Where they overlapped, the newer file (ROADMAP.md, 2026-10-05) takes precedence; the older plan's item-level detail is retained unchanged in Part B. See "Conflict notes" below.

---

## Part A — Product Roadmap & Backlog (from ROADMAP.md, 2026-10-05)

Current-state roadmap for the AviaSAFE SMS Platform. Supersedes the earlier "Safety-Health" roadmap
(Supabase/Netlify era). The authoritative status source is
[docs/archive/PROJECT_STATUS_REPORT_05AUG2026.md](./docs/archive/PROJECT_STATUS_REPORT_05AUG2026.md);
the latest dated report is [docs/PROJECT_STATUS_REPORT_2026-08-24.md](./docs/PROJECT_STATUS_REPORT_2026-08-24.md).

## Delivery Notes

> The 12-month demo seed is **synthetic**. It provides a populated demo experience at delivery but is
> **not** a substitute for real customer data. Customers must import their **Master Logsheet** via
> Phase 2B to make the platform authoritative for their operation. Disclose this clearly in the
> delivery scope email.

## Single-Path User Provisioning (Policy — Implemented 2026-09-14)

**Users are always created via Step 3.** There is exactly one way to provision a tenant user:
Production Setup Step 3 (`POST /api/v1/admin/users`, one user at a time).

- The tenant onboarding wizard (`public/admin/tenant-credentials.html`) no longer creates users — it
  is a 5-step tenant-only flow (Tenant Info → Contact → Contract → Review → Done).
- `POST /api/v1/admin/tenants` (`admin_create_tenant`) creates the tenant only; the legacy
  `if data.get("users")` branch was removed.
- `create_tenant_with_credentials` (batch tenant+users) was removed on 2026-09-17
  (see `PASSWORD_RESET_BUG_INVESTIGATION.md`); it no longer exists in the codebase.
- Rationale: a single path is easier to test, monitor, and trust, and matches the real customer
  workflow (create the tenant, then add users one at a time after hand-over).

## Milestones Reached

| Phase | Status | Notes |
|---|---|---|
| **Feature Development** | ✅ 100% | Survey, VSR/MOR, AI suggestions, dashboards, roles, CAN/CAP, verification, diversions, quarterly/annual reports + PDF |
| **RC-1 — Security Hardening** | ✅ COMPLETE | Env-only secrets, admin auth, debug endpoints closed, fail-closed provisioning |
| **RC-2 — Functional Corrections** | ✅ COMPLETE | Unified risk matrix (5/9/15), thresholds plumbed |
| **RC-3 — Documentation & Operational Readiness** | ✅ COMPLETE | GLOSSARY.md, tenant-guide steps 02/03, deploy docs, seed v2.1.0 (10 providers + CAAN), legacy purge, audit tooling, admin feedback review, survey campaign windows |
| **SRA & RCA Analysis Toolkit** | ✅ COMPLETE | 5x5 Safety Risk Assessment matrix, 6-category Fishbone root-cause analysis, 1:1 action-item linkage to CANs (2026-08-16) |
| **Tenant Operational Profiles** | ✅ COMPLETE | Constraint-based demo seeder (fleet, base hub, authorized destinations, hazard domains) + 5 demo reference profiles (2026-08-17) |
| **Multi-tenant Routing & Demo Switcher** | ✅ COMPLETE | Subdomain→tenant resolver, conditional demo persona switcher, email→department mapping (2026-08-17) |
| **Latency Baseline & Local Demo Environment** | ✅ COMPLETE | `[PERF]` request instrumentation (pending Render push), root-cause analysis (cold starts / unfiltered Firestore scans / AI timeouts), one-click local Docker demo targeting `sms-db` (2026-08-24) |

## Remaining Release-Candidate Phases

- **RC-4 — Charter Re-alignment & Compliance Audit:** Survey is now aligned to the 4 ICAO
  components / 12 elements with a backend scoring endpoint (survey v3.0.0); remaining work is a
  formal compliance audit of the 12-element mapping, the live SMS Maturity dashboard output, and any
  residual functional inaccuracies.
- **RC-5 — Platform Hygiene & Tooling:** remove `public/portal` mock code (TD-7), prune dead code
  (TD-11/TD-13 leftovers), CI (lint + pytest + deploy), single `render.yaml` (TD-8), align
  Firestore indexes (TD-10).
- **RC-6 — Pre-Production / Pilot:** App Check server-side enforcement (TD-12), MFA, backups/PITR,
  audit trail, staging environment, penetration/security review.

## Phase 1 — Nav Overhaul (Backlog, Scheduled Post-Pilot)

Role-specific navigation, recorded 2026-09-13 from FIX 5 Phase 1D findings (145@ / sita-air walkthrough).
Not blocking pilot delivery; announced to customers as "coming in the next release."

### Current state
- `shell.js` groups are role-gated at the group level only.
- No item-level gating.
- No distinct nav per role.
- Home links to `safety.html` regardless of role.

### Observed impact (145@ walkthrough)
- DEPT_ADMIN sees **Hazard Management** and **Reporting** — not their job.
- Home from DEPT_ADMIN links to `safety.html` — inaccessible (403).
- Corrective Actions shows **Issue CAN** and **Master Register** — write actions not meant for DEPT_ADMIN.
- AE sees the same nav as the Safety Manager.

### Target state
- Each role has a purpose-built nav (see matrix below).
- Group-level **and** item-level gating.
- Role-aware Home destination:
  - SAFETY → `/safety.html`
  - AE → `/dashboard/ae-dashboard.html`
  - DEPT_ADMIN → `/dashboard/my-tasks.html`
  - CAAN_SMD → `/caan.html`
  - SUPER_ADMIN → `/admin/production-setup.html`

### Role visibility matrix

| Group              | SAFETY | AE        | DEPT_ADMIN | CAAN | SUPER |
|--------------------|--------|-----------|------------|------|-------|
| Dashboard          | ✅     | ✅        | ✅         | ✅   | ✅    |
| Reporting          | ✅     | ❌        | ❌         | ❌   | ✅    |
| Hazard Management  | ✅     | Read-only | ❌         | ❌   | ✅    |
| Risk Assessment    | ✅     | Read-only | ❌         | ❌   | ✅    |
| Corrective Actions | ✅     | Read-only | ✅ dept    | ❌   | ✅    |
| SMS Health         | ✅     | ✅        | ❌         | ✅   | ✅    |
| State Oversight    | ❌     | ❌        | ❌         | ✅   | ✅    |
| Administration     | ✅     | Conditional| ❌         | ❌   | ✅    |

### Implementation
- `NAV_CONFIG` schema extended:
  ```js
  { group, items, visibleTo: ['ROLE1','ROLE2'],
    itemOverrides: { itemId: { visibleTo: [...],
                               readOnly: bool } } }
  ```
- `shell.js` renders per role at login.
- Home destination resolved via `getHomeDestination(role)`.
- Tests cover the matrix.

### Summary decisions
| Item | Decision |
|---|---|
| Reporting group | ❌ Hidden for DEPT_ADMIN (145@) |
| Hazard Management | ❌ Hidden for DEPT_ADMIN (145@) |
| Home destination | Role-aware — DEPT_ADMIN (145@) → `my-tasks.html` |
| Corrective Actions submenu | Refined for DEPT_ADMIN (My Tasks, CAN Register, CAP Register) |
| Issue CAN | Hidden for DEPT_ADMIN (145@) |
| Master Register | Hidden or read-only for DEPT_ADMIN (145@) |
| AE navigation | Distinct AE nav (no longer identical to Safety Manager) |
| Full nav spec | Role-by-role matrix above |
| Backlog | Phase 1 Nav Overhaul |
| Pilot impact | Not blocking — scheduled for post-pilot |

## Phase 1 — Remove `tenant.data.users` Array (Backlog)

Priority: **Medium** — after the delivery stabilizes. Recorded 2026-09-13.

### Context
The tenant row carries a JSONB `users` array (inside the `data` column, `tenants.data->users`) that
duplicates the `users` table. It is a Firestore-era denormalization that survived the migration.

### Impact
- Two sources of truth for user-tenant membership.
- Delete/create paths must update both or drift (today's bug — a delete removed Auth + PG but not
  the array; the re-create refused on the stale array entry).
- Any future user mutation is a candidate for the same class of bug.

### Work
1. Grep for all reads of `tenant.data.users` (backend + frontend).
2. Redirect every read to the `users` table:
   ```sql
   SELECT u.* FROM users u
   JOIN tenants t ON u.tenant_id = t.id
   WHERE t.slug = ?
   ```
3. Stop writing to the array on user create/delete.
4. After a full verification cycle with no writes to the array, drop the `users` key from the
   `data` JSONB (migration).
5. Update models and schemas.

### Effort
~2 days — one source of truth for user-tenant membership; prevents this class of bug permanently.

## Phase 1 — Setup Key Hardening: Server-Issued Short-Lived Tokens (Backlog)

Priority: **HIGH** (Phase 1, foundation). Recorded 2026-09-13. Quick hardening (client idle
timeout for the `sessionStorage` setup key) is shipped in `public/js/admin.js`; this item removes
the static `SETUP_SECRET` from the browser entirely.

### Objective
Eliminate client-side retention of the static setup key. The key is never sent to the browser, so
an XSS or a compromised browser cannot exfiltrate it — the exposure window becomes zero.

### Design
- New `POST /api/v1/admin/setup-token` mints a **15-minute signed token**.
- Exchange the raw `SETUP_SECRET` for the token **exactly once** (SUPER_ADMIN token + setup key
  still required at mint time).
- All ~40 privileged endpoints validate the token instead of the raw key.
- Frontend stores **only the token** (sessionStorage, with the idle timeout already in place).
- Token auto-renews on activity, expires on idle, full teardown on logout.

### Effort
~1–2 days — touches every privileged admin route and page.

## Phase 1 — Welcome Email: Enable Real Delivery (Backlog)

Priority: **Medium** — delivery provider is currently `'none'` (logged, not sent);
new sita-air users received their password only via the one-time on-screen display.
Recorded 2026-09-13.

### Work
1. Configure a real provider (`smtp` / `sendgrid`) for `EMAIL_PROVIDER` in deploy env.
2. Verify `send_welcome_email` path (see `backend/app/services/email_service.py:258`) end-to-end on a stamp user.
3. Fallback UX: if delivery is `'none'`, the Step-3 create page must surface "email will not be sent".

## Phase 1 — Step 3 Create-User: Copy-Password Button (Backlog)

Priority: **Low** — usability. The 14-char generated password is displayed as plain text and must be
hand-typed; a prior incident was traced to a hand-transcription error. Recorded 2026-09-13.

### Work
1. Clipboard API button beside the password on `step3-manage.html` with a visual "copied" confirmation.
2. Keep the one-time display; add a "reveal" toggle if hidden.

## Phase 1 — CI Pipeline: Regression Test Automation (Backlog)

Priority: **MEDIUM** — foundation, not blocking pilot delivery. Recorded 2026-09-13.

### Objective
Run the test suite automatically on every push to `main` and on every PR.

### Design decisions to settle in Phase 1
- **Runner**: GitHub Actions vs Render pre-deploy vs self-hosted.
- **Secrets strategy**: inject the Firebase service account + web API key into the runner
  securely, without committing them to the repo.
- **Live-tests strategy**: keep live-Auth/live-DB tests (e.g. `tests/test_admin_user_password.py`)
  gated behind an explicit env flag so faked tests stay fast and deterministic; live tests run
  only in a trusted environment.
- **Flake policy**: quarantine known-flaky, state-dependent tests so they never block deploys.

### Effort
~1–2 days. The regression test (`tests/test_admin_user_password.py`) already runs locally and
must be run before each commit / milestone until this pipeline exists.

## Phase 1 — Survey Hostname Mapping (Backlog)

Priority: **Low**. Recovered 2026-09-13 from a stale session file. `public/survey/app.js` `routes`
currently maps only `sita-air`, `nepal-airlines`, `caan-ops`.

### Decision to make
- (a) Add new tenant subdomains to the map as they onboard, or
- (b) Standardize on `?tenant=` query params for all surveys.

### Trigger
A tenant outside the current map is onboarded.

### Effort
~1 hour.

## Phase 1 — Registration Activation (Backlog)

Priority: **High** — product activation, gated by the security remediation in
`SECURITY_REVIEW.md` C1/C2 (see the C1/C2 note in `HANDOFF_GUIDE.md`; the
onboarding gate now requires an admin dependency and the hardcoded default key
is removed).

- **Prod-1 — Activate operator self-registration** (`public/register.html`).
  Currently gated by the enterprise access key (`BETA_ACCESS_KEY`).
- **Prod-2 — Activate team onboarding** (`public/join.html`). Currently
  invite-code gated.

Cross-reference: `SECURITY_REVIEW.md:36-42` (C1/C2).

## Phase 1 — Repo Hygiene: No Snapshot Files (Convention)

Working-session artifacts (todos snapshots, session logs, chat exports) must **not** be committed to
the repo. Actionable items recovered from such files go into ROADMAP.md; the source files are
deleted after extraction. Recorded 2026-09-13 (artifacts recovered from
`sms360x/sms-aviasafesystems-main-downloaded/todos.md` before folder deletion).

## Phase 3 — Per-Employee Survey Issuance (Enhancement)

Employee-scoped collection with unique per-employee links or `respondentId`, built on top of the
existing tenant-keyed storage. Enables per-employee analytics. **Not required for the pilot.**
Recovered 2026-09-13 from a stale session file.

## Phase 2A — AE Dashboard Redesign

Dependency for Phase 2B. Details TBD (separate backlog item; recorded 2026-09-13).

## Phase 2B — Historical Import (Excel / CSV)

Priority: HIGH — this is the "move from Excel" feature. Recorded 2026-09-13.

### Objective
Let the Safety Manager upload the customer's Master Logsheet (and related sheets) so the
platform contains **real** safety data, not synthetic seed data.

### Deliverables
- Import UI (card on `safety.html` dashboard, leading to `/import/index.html`)
- Sheet-type detection: Master logsheet, Occurrence, Safety Deficiencies, Hazard log,
  Flight diversions, Risk register
- Column-mapping UI (CSV column → platform field)
- Validation (dates, ADREP codes, required fields)
- Dry-run mode (validate only, no writes)
- Import modes: append / replace / skip-duplicates
- Audit-logged (who imported what, when)
- Per-tenant scoping (a tenant imports only its own data)

### Explicit non-goals
- CAN/CAP import (the customer's Excel has no structured CAN/CAP data — these are platform
  outputs, generated going forward)
- Automatic derivation of hazards from VSR/MOR (Phase 3 — Dynamic Barrier Integrity)

### Post-import outcome
- Tenant's hazards, reports, diversions loaded
- CAN/CAP registers start at zero
- From go-live, the platform becomes authoritative
- Leading and lagging indicators compute from real data

### Cross-reference
- Depends on Phase 2A (AE dashboard redesign) being complete
- Feeds Phase 3 (Safety Intelligence) — statistical indicators need real data, not synthetic

## Product Roadmap (post-pilot, charter-gated)

Per the [Product Charter](./docs/archive/PROJECT_CHARTER.md), feature expansion requires explicit approval.
Candidate product work (not committed):

- Monitoring / alerting for SMS maturity thresholds.
- Notifications service (email/portal).
- AI assistant enhancements (evaluation set, per-tenant prompt tuning).
- State-of-the-System reports and SSP effectiveness reporting automation.

*Nothing here is scheduled without approval.*

---

## Part B — Schema-Note Implementation Plan (from IMPLEMENTATION_ROADMAP.md, 2026-10-02)

AviaSAFE SMS Platform
Status: PHASE 3 COMPLETE — all Phase 0/1/2/3 items (P1-1..P1-31,
P2-1..P2-30, P3-1..P3-15) DONE; Phase 4 (frontend dashboards)
Waves 1-3 complete (P4-1, P4-2, P4-3, P4-6, P4-7); Waves 4-5
(P4-4 AE, P4-5 State Regulator) pending.
Purpose: A dependency-ordered plan to implement every schema note and
compliance remediation defined across the six contracts.

Inputs: `MODULE_A_CONTRACT.md`, `MODULE_B_CONTRACT.md` (§10 SN1-SN17,
§32), `MODULE_C_CONTRACT.md` (§7.4/§8.4/§9.4/§10.4, §13 Appendix SN, §14),
`RBAC_MODEL.md`, `DASHBOARD_CONTRACT.md`, `COMPLIANCE_MATRIX.md`,
`SCHEMA_RECONCILIATION_PLAN.md`.

How to read:
- **ID** — stable work-item id (`P<phase>-<n>`).
- **What / Why** — the change and the contract section it satisfies.
- **SN** — the schema note(s) implemented.
- **Depends** — prerequisite work items.
- **Effort** — XS (<4 h), S (<1 day), M (1-3 days), L (~1 week), XL (>2 weeks).
- **Test** — required verification.

All items are **PENDING** unless marked DONE.

---

## PHASE 0 — BASELINE (already complete)
**Purpose.** Record what is already done so Phase 1 does not redo it.

**Content.** From `SCHEMA_RECONCILIATION_PLAN.md` §3/§6:

| Item | Decision | Status |
|---|---|---|
| `risk_register` split into legacy + `sram_risk_register` | D1 | DONE (ORM + migration) |
| `is_demo` on 10 minor models | D7 | DONE (ORM) |
| `regulators` 8 columns | D5 | DONE |
| `users.phone` UNIQUE | D6 | DONE |
| `tenants.safety_manager` varchar→jsonb | D4 | DONE (migration) |
| `invites`/`feedback` ORM rewrite | D3 | DONE (ORM + call sites) |
| `sms_maturity` ORM rewrite + RLS | D2 | DONE (ORM + RLS; P1-1/P1-2/P1-3) |
| ADREP/HFACS 6 vestigial tables | D8 | DONE — no action (vestigial) |
| `caps` nullability divergence | D9 | DONE — no action (documented) |

**Gap.** `test_domain_schema.py` must be green before Phase 1 (gate,
`SCHEMA_RECONCILIATION_PLAN.md` §6).

---

## PHASE 1 — SCHEMA MIGRATIONS
**Purpose.** Land every `SN#`/`SN-C#` schema change in dependency order, one
migration per table cluster, with rollback.

**Phase 1 completion (2026-09-22).** All items P1-1..P1-31 **DONE**.

| Module | Commit | Scope |
|---|---|---|
| Module A | `846913d` | P1-1..P1-3 — `sms_maturity` ORM/RLS/service boundary |
| Module B | `3a68f38` | P1-4..P1-19 — hazards columns, sram register, new tables, reports |
| Module C | `ce7102a` | P1-20..P1-28 — aggregates, SPT, taxonomy, RLS |
| RBAC | `d15ebd3` | P1-29..P1-31 — role literals, EIP status, AE uniqueness |

- **Migrations:** **16** applied to live (1 Module A RLS + 7 Module B + 7 Module C
  + 1 RBAC), each idempotent.
- **Test baseline at Phase 1 close:** 990 collected → **988 passed, 2 failed**.
  The 2 failures are `test_admin_credentials.py::test_create_user_route_caan_smd_allowed`
  (a Phase-1 regression — see below) and the pre-existing
  `test_tenant_sms.py::TestV1RouterRegistration::test_v1_router_includes_all_sub_routers`
  (unrelated).
- **Known Phase-1 regression (unfixed, reported):**
  `test_create_user_route_caan_smd_allowed` (`backend/tests/test_admin_credentials.py:550`)
  expects a `CAAN_SMD` user to be creatable on a tenant; the P1-31 validator
  now rejects `CAAN_SMD` + `tenant_id` (RBAC §7) and the admin route's broad
  `except Exception` maps the resulting `HTTPException(400)` to a 500.
- **Deferred:** `state_safety_performance_targets.spi_definition_id` carries no
  DB-level FK — SPI definitions are code constants (Q9.1 hybrid; logical
  reference only) — Module C Deviation 2. Runtime seeding of
  `taxonomy_mappings`/`metric_definitions` on a fresh deploy is deferred to
  P6-3.

**Content.**

### 1A — Module A (Survey)

| ID | What | Why | SN | Depends | Effort | Test | Status |
|---|---|---|---|---|---|---|---|
| P1-1 | Rewrite `SmsMaturity` ORM to live shape (drop `days`/`data`); rewrite `_read/_write_sms_maturity`; replace `schema_init.py:283-292` | Module A §7/§8 (App 2 §3.1 persistence) | D2 | Phase 0 | M | `test_sms_maturity_cache.py` round-trip | DONE |
| P1-2 | `ENABLE ROW LEVEL SECURITY` on `sms_maturity` + `p_sms_maturity_tenant_isolation` | Module A §7.2; App 3 | D2 | P1-1 | S | RLS policy present; cross-tenant read denied | DONE |
| P1-3 | Resolve dashboard→`sms_maturity` boundary (expose `POST /sms-maturity/{tenant_id}/cache` or move cache) | Module A §7.1 | D2 | P1-1 | M | ownership test (only Module A writes) | DONE |

### 1B — Module B: `hazards` columns

| ID | What | Why | SN | Depends | Effort | Test | Status |
|---|---|---|---|---|---|---|---|
| P1-4 | Add `hazards.identified_at` (tz-aware) | Module B §3, §2.1 | SN1 | Phase 0 | S | column + create-populate | DONE |
| P1-5 | Add `hazards.equipment`/`area` free-text | Module B §3 (CAAN field ii) | SN2 | P1-4 | XS | nullable round-trip | DONE |
| P1-6 | Add `hazards.first_priority_at`, set once at create | Module B §3; AE KPI | SN7 | P1-4 | S | not re-stamped on priority change | DONE |
| P1-7 | Add `ck_hazards_status` CHECK (6 enum values) | Module B §3; SN8 | SN8 | P1-4 | S | invalid status rejected | DONE |
| P1-8 | Add `hazards.imported_at`/`import_batch_id`/`original_row_ref`/`legacy_hazard_code` | Module B §25 | SN12 | P1-4 | S | import provenance columns | DONE |
| P1-9 | Add `hazards.enrichment_data` JSONB + `enrichment_sources` JSONB | Module B §27 | SN14 | P1-4 | S | JSONB round-trip | DONE |
| P1-10 | Retire the `verification_service.py:122-124` no-op (no schema; code) | Module B §18; SN4 | SN4 | — | XS | no write to non-existent column | DONE |

### 1C — Module B: `sram_risk_register`

| ID | What | Why | SN | Depends | Effort | Test | Status |
|---|---|---|---|---|---|---|---|
| P1-11 | Add process-conformance signer block (`process_by`/`process_signed_at`) | Module B §17; §2.3.3 | SN5 | Phase 0 | S | two signer blocks persist | DONE |
| P1-12 | Add `initial_authority`/`resultant_authority` snapshot columns | Module B §16 | SN6 | P1-11 | XS | snapshot on accept | DONE |
| P1-13 | Add `consequence_id` FK → `bow_tie_consequences.id`; change unique key to (tenant_id, hazard_id, consequence_id) | Module B §11; §2.3.5 | SN10 | P1-11 | M | per-consequence register rows | DONE |

### 1D — Module B: new tables

| ID | What | Why | SN | Depends | Effort | Test | Status |
|---|---|---|---|---|---|---|---|
| P1-14 | Create `hazard_triage` (+ reversal fields) | Module B §26 | SN13 | P1-4 | M | triage + reversal + audit rows | DONE |
| P1-15 | Create `import_batches`/`import_rows`/`import_mappings`/`import_links` | Module B §25 | SN12 | P1-8 | L | staged import round-trip | DONE |
| P1-16 | Create `sag_meetings` + `srb_meetings` (dependency for `action_items`) | Module B §28/§29 | SN16 | — | M | meeting CRUD | DONE |
| P1-17 | Create `action_items` (`meeting_type` discriminator; polymorphic `meeting_id`) | Module B §28/§29 | SN16 | P1-16 | M | SAG/SRB action item | DONE |
| P1-18 | Create `safety_communications` with status enum | Module B §31 | SN17 | — | M | draft→published lifecycle | DONE |

### 1E — Module B: `reports`

| ID | What | Why | SN | Depends | Effort | Test | Status |
|---|---|---|---|---|---|---|---|
| P1-19 | Add `regulatory_category` + `regulatory_deadline_at`/`regulatory_submitted_at`/`regulatory_submission_ref` | Module B §30 | SN15 | — | M | category-tiered deadline math (A=24h/B=72h/C=7d/D=30d) | DONE |

### 1F — Module C (Regulator / SDCPS)

| ID | What | Why | SN | Depends | Effort | Test | Status |
|---|---|---|---|---|---|---|---|
| P1-20 | Create `module_c_aggregates` (`payload` jsonb, `ttl_seconds`, unique key) | Module C §7.4; SN-C5 | SN-C1/C5 | — | M | materialized row round-trip | DONE |
| P1-21 | Create `state_safety_performance_targets` (`spi_definition_id` FK, `target_period`, `approved_by`) | Module C §9.4; SN-C6 | SN-C2/C6 | — | M | SPT persist + read | DONE |
| P1-22 | Create `metric_definitions` (`window_type`, `window_days`, `min_periods`) | Module C §10.4; SN-C7 | SN-C3/C7 | — | S | window config seeded | DONE |
| P1-23 | Create `taxonomy_mappings` (ICAO↔ADREP↔HFACS↔N-HRC), read-only seeded | Module C §8.4; SN-C8 | SN-C4/C8 | — | M | seed from CSVs | DONE |
| P1-24 | Add `hazards.nhrc_category` (auto-derive + manual override) | Module C §8.4; SN-C9 | SN-C9 | P1-23 | S | derivation + override | DONE |
| P1-25 | Add `psoe_findings.cap_id` FK + `caps.source_psoe_finding_id` FK | Module C §14 (Q4.1b) | SN-C10 | — | S | bidirectional nullable linkage | DONE |
| P1-26 | Enable RLS on `caan_reports`, `state_risk_categories`; document `sms_maturity` (P1-2) | Module C §5 (DP-6) | DP-6 | P1-2 | M | RLS on or exempted | DONE |
| P1-27 | NULL-tenant aggregate RLS policy `USING (tenant_id IS NULL AND role='CAAN_SMD')` | Module C SN-C5 / Q7.2 | SN-C5 | P1-20 | M | CAAN-only national rows | DONE |
| P1-28 | Enable CAAN/SUPER_ADMIN cross-tenant RLS policy (uncomment) | RBAC §4; Module C §5.2.5 | — | P1-26 | M | cross-tenant read allowed for CAAN only | DONE |

### 1G — RBAC / platform

| ID | What | Why | SN | Depends | Effort | Test | Status |
|---|---|---|---|---|---|---|---|
| P1-29 | Add literal roles `ACCOUNTABLE_EXECUTIVE`, `SAG_MEMBER` (no `REGULATORY_LIAISON` — folded into `SAFETY_OFFICER` per RBAC Q-R3) to `config.py` role lists/aliases | RBAC §1; Module B §22/§28 | — | — | S | normalization maps | DONE |
| P1-30 | Add `"EIP"` to `CAPStatus` | Module B §21 (Decision 1) | — | — | XS | EIP status round-trip | DONE |
| P1-31 | Role-assignment validator + conflict constraints (AE exclusive, CAAN vs tenant) | RBAC §7 | — | P1-29 | M | conflicting combos rejected | DONE |

**Dependency-critical notes.**
- `P1-4` (identified_at) gates SN3/SN7/SN14/SN12.
- `P1-16` gates `P1-17` (action_items needs meetings).
- `P1-20` gates `P1-27` (RLS policy needs the table).
- `P1-23` gates `P1-24`.

**Gaps.** Migration ordering across three ORM edit sites (`db_models.py`,
`schema_init.py`, `supabase/migrations/`) must be serialized to avoid collisions
(`SCHEMA_RECONCILIATION_PLAN.md` §3).

---

## PHASE 2 — BACKEND SERVICES
**Purpose.** Implement the business logic over the new schema.

**Phase 2 completion (2026-09-22).** All items P2-1..P2-30 **DONE**.

| Module | Commit | Scope |
|---|---|---|
| Module A | `00a16b7` | P2-1, P2-2 — sms_maturity TTL cache + async LLM pipeline |
| Module B (1) | `b3b823b` | P2-3..P2-8 — SRM core (follow-up, overdue, authority, two-signature, BSV, per-consequence) |
| Module B (2) | `78dd589` | P2-9..P2-16 — triage, enrichment, MOR timer, SAG/SRB, comms, import, AE decision, EIP |
| Module C | `9b15eab` | P2-17..P2-25 — materialization, state SPI/SPT, trend baseline, N-HRC, PSOE↔CAP, insights, CAAN audit, confidential |
| RBAC | `98986aa` | P2-26..P2-30 — RBAC middleware, classification, use-limitation, AE KPI |

- **Tests:** **1062** total → **1061 passed, 1 pre-existing failure**
  (`test_tenant_sms.py::TestV1RouterRegistration::test_v1_router_includes_all_sub_routers`,
  unrelated router-shape test).
- **Partial deliveries:** **P2-14** historical import — hazard entity is fully
  staged/validated/promoted; CAN/CAP/bow-tie/barrier/risk-register promotion
  deferred. **P2-25** confidential reporting — schema (flag + custodian FK) and
  the service (flag, custodian access control, de-identification) done;
  ingestion wiring deferred to a Module B cross-module pass.

**Content.**

### 2A — Module A

| ID | What | Why | SN | Depends | Effort | Test | Status |
|---|---|---|---|---|---|---|---|
| P2-1 | Rewrite SMS-maturity cache read/write + TTL invalidation | Module A §7 | D2 | P1-1 | M | cache hit/miss; TTL 6 h | DONE |
| P2-2 | Async LLM analysis pipeline (on submit; not inline) | Module A §7.5/Q3 | — | P2-1 | L | job triggers once per submission | DONE |

### 2B — Module B

| ID | What | Why | Depends | Effort | Test | Status |
|---|---|---|---|---|---|---|
| P2-3 | Derive `follow_up_date` from priority (H+24h/M+7d/L+15d); manual override wins | SN3 | P1-4 | M | derivation + override cases | DONE |
| P2-4 | Derived risk-overdue (sram `review_date`/CAP past, not accepted/closed); CAP-overdue → Closed/Escalated lifecycle | SN4/§18 | P1-13 | M | overdue derivation | DONE |
| P2-5 | Authority-tier enforcement in `accept_risk` (initial-risk authority, non-delegable) | SN6/§16 | P1-11,P1-12 | M | wrong-tier accept rejected | DONE |
| P2-6 | Two-signature acceptance workflow (process + accept) | SN5/§17 | P1-11 | M | both signatures required | DONE |
| P2-7 | Retire continuous BSV; reroute 3 callers to `calculate_bqv` | SN11 | — | M | banded BSV stored | DONE |
| P2-8 | Per-consequence risk-register rows | SN10 | P1-13 | M | one row per consequence | DONE |
| P2-9 | Triage service (accept/reject/duplicate/escalate + reversal + audit) | SN13/§26 | P1-14 | L | decision + reversal audit | DONE |
| P2-10 | Enrichment service (add-not-replace; before/after audit) | SN14/§27 | P1-9 | M | create-only fields untouched | DONE |
| P2-11 | MOR category-tiered timer service | SN15/§30 | P1-19 | M | A/B/C/D deadlines | DONE |
| P2-12 | SAG/SRB service (meetings + shared action items) | SN16/§28/§29 | P1-16,P1-17 | L | meeting + action feed | DONE |
| P2-13 | Safety-communications service (draft→review→published) | SN17/§31 | P1-18 | M | SAFETY_MANAGER approval | DONE |
| P2-14 | Historical import pipeline (Excel/CSV → staging) | SN12/§25 | P1-15 | XL | staged import + provenance | DONE (partial — hazards promoted) |
| P2-15 | AE terminal-decision rule (no reject; immutable after signature) | Module B §22 | P1-29,P1-30 | M | terminal state enforced | DONE |
| P2-16 | EIP persistence + transitions | Module B §21 | P1-30 | S | EIP set/cleared | DONE |

### 2C — Module C

| ID | What | Why | Depends | Effort | Test | Status |
|---|---|---|---|---|---|---|
| P2-17 | Materialization job (hybrid: daily + event-driven) writing `module_c_aggregates` | Module C §7 AGG-1..5; Q7.1 | P1-20 | L | aggregate rows; TTL | DONE |
| P2-18 | State SPI computation (replace placeholder trend) | Module C SLI-1 | P2-17 | L | real period-over-period trend | DONE |
| P2-19 | State SPT set/approve service (persist, CAAN-gated) | Module C SPT-1..4 | P1-21 | M | persist + replace default | DONE |
| P2-20 | Trend-baseline resolver (12-month state / 3-month operational; "insufficient data") | Module C TB-1..4; Q10.2 | P1-22 | M | below-min returns insufficient | DONE |
| P2-21 | N-HRC auto-derivation + manual override | Module C SN-C9 | P1-24 | M | derive + override | DONE |
| P2-22 | PSOE↔CAP linkage service (optional, manual, bidirectional) | Module C Q4.1b | P1-25 | M | link/unlink both ways | DONE |
| P2-23 | State diagnostic/insights output (AL-2) on aggregates (three-lane LLM) | Module C §11; Q11.1 | P2-17 | L | insights non-empty, aggregate-only | DONE |
| P2-24 | CAAN read/share/escalation audit writers (`CAAN_READ_*`, `CAAN_SHARE_*`, `CAAN_ESCALATED_READ`) | Module C DP-3/SS-2/HV-2 | — | M | audit rows per action | DONE |
| P2-25 | Confidential/voluntary reporting class (Module B-owned) | §5.2.4; DP-4 | P1-* | L | flag + protection | DONE (partial — ingestion wiring deferred) |

### 2D — RBAC / cross-cutting

| ID | What | Why | Depends | Effort | Test | Status |
|---|---|---|---|---|---|---|
| P2-26 | Register/rewrite RBAC middleware with canonical roles + module flags | RBAC §9; SECURITY M5 | P1-29 | L | module gate active | DONE |
| P2-27 | Apply `get_caan_user` + tenant validation to regulator/SPI/N-HRC | SECURITY H1/H2 | P2-26 | M | 403 for non-CAAN | DONE (verified, no code change) |
| P2-28 | Data-classification labels (public/internal/confidential/protected) | Module C DP-1 | P1-26 | M | label on artifacts | DONE |
| P2-29 | Use-limitation statements on share/dispatch outputs | Module C DP-7/SS-6 | — | S | text present | DONE |
| P2-30 | AE Hazard-Response-Time KPI computation (SN9 rules) | SN9; Dashboard §4.3 | P1-6 | M | avg days + received count | DONE |

---

## PHASE 3 — API ENDPOINTS
**Purpose.** Expose the service layer through the contract API surfaces.

**Phase 3 completion (2026-09-22).** All items P3-1..P3-15 **DONE**.

| Wave | Commit | Scope |
|---|---|---|
| Wave 1 | `f6db16a` | P3-1..P3-9 — Module B endpoints (triage, enrich, regulatory-submit, SAG/SRB/action-items, bulletins, import, AE queues/decision, dept CAP) |
| Wave 2 | (Part A commit) | P3-10..P3-15 — Module C + dashboard endpoints |

- **Endpoints delivered:** 15 tasks.
- **Tests at Phase 3 close:** see the full-suite result in the close-out report
  (Phase 3 added 9 Wave-1 + 6 Wave-2 test files).
- **Notes / deferred:**
  - **P3-12** escalations are held in an **in-memory registry** with expiry;
    durable persistence is deferred to Phase 6 (pre-production item).
  - **P3-14** link endpoints live under the existing PSOE namespace
    (`/api/v1/supabase/psoe/findings/...`) per convention, with the CAP-side
    reverse lookup at `/api/v1/cans/caps/{cap_id}/linked-findings`.
  - **P3-13** (dashboard standard params) preserves the legacy `days` query
    param for back-compat; `period` takes precedence when both are supplied.

**Content.**

| ID | Endpoint(s) | Module | Depends | Effort | Test | Status |
|---|---|---|---|---|---|---|
| P3-1 | `POST /api/v1/hazards/{id}/triage` (+ list/GET) | B §26 | P2-9 | M | triage actions | DONE |
| P3-2 | `POST /api/v1/hazards/{id}/enrich` (+ attachment) | B §27 | P2-10 | M | enrichment | DONE |
| P3-3 | `POST /api/v1/reports/{id}/regulatory-submit` + timer fields | B §30 | P2-11 | M | deadline + submit | DONE |
| P3-4 | `POST/GET/PATCH /api/v1/sag/*`, `/api/v1/srb/*`, `/action-items` | B §28/§29 | P2-12 | M | meetings/actions | DONE |
| P3-5 | `POST /api/v1/bulletins` lifecycle | B §31 | P2-13 | S | publish | DONE |
| P3-6 | `POST /api/v1/hazards/import` (upload + staging status) | B §25 | P2-14 | L | batch import | DONE |
| P3-7 | AE queue endpoints (`GET /caps?escalated_to_ae=true`; acceptances pending) | B §23 | P1-30,P2-15 | M | queue filters | DONE |
| P3-8 | `POST /api/v1/caps/{id}/ae-decision` (terminal) | B §22 | P2-15 | M | terminal rule | DONE |
| P3-9 | `PATCH /api/v1/caps/{id}` dept-scoped CAP response | B §20; Dashboard §3 | P2-26 | S | dept isolation | DONE |
| P3-10 | `/api/v1/spi/state/targets` (SPT set/approve) | C §9 | P2-19 | M | CAAN-gated persist | DONE |
| P3-11 | State SPI trend + materialized values endpoints | C SLI-1 | P2-18 | M | trend real | DONE |
| P3-12 | `/api/v1/regulator/share/*` (benchmark + escalation) | C §6/§12 | P2-24 | L | share audited | DONE |
| P3-13 | AE dashboard KPI endpoint (`avg_days_registration_to_first_action`, received) | SN9; Dashboard §4 | P2-30 | M | envelope + null-empty | DONE |
| P3-14 | Dashboard standard params (`period`/`granularity`/`group_by`) | Dashboard §7 | P2-26 | M | param handling | DONE |
| P3-15 | PSOE↔CAP link endpoints | C Q4.1b | P2-22 | S | link CRUD | DONE |

---

## PHASE 4 — FRONTEND DASHBOARDS
**Purpose.** Build the four role-scoped dashboards on the shared shell.

**Content.**

| ID | Deliverable | Role | Depends | Effort | Test | Status |
|---|---|---|---|---|---|---|
| P4-1 | Shared shell components (header, period selector, drill-down, empty/loading/error) | all | P3-14 | L | component specs | DONE (`267cce5` Wave 1) |
| P4-2 | Safety Manager dashboard (5-counter KPI strip, color rules, EIP, workspace) | TENANT_ADMIN/SAFETY_OFFICER | P3-3,P3-6 | L | E2E KPI drill-down | DONE (`86f22f8` Wave 2; see deferrals below) |
| P4-3 | Department Head dashboard (3-counter strip, dept CAP response) | DEPT_ADMIN | P3-9 | M | dept scoping | DONE (`eb25641` Wave 3; see deferrals below) |
| P4-4 | AE dashboard (numeric KPI strip, 2 action queues, trends) | ACCOUNTABLE_EXECUTIVE | P3-7,P3-8,P3-13 | L | queues + KPI | PENDING (Wave 4; existing `ae-dashboard.html` predates Phase 4 work) |
| P4-5 | State Regulator dashboard (national KPIs, benchmarks, PSOE, SPI/SPT, escalation) | CAAN_SMD | P3-10,P3-11,P3-12 | XL | read-only + escalation | PENDING (Wave 5; no P4-5 artifact) |
| P4-6 | `nav-config.js` role types update (`ACCOUNTABLE_EXECUTIVE`, `SAG_MEMBER`) | all | P1-29 | S | role menus | DONE (`267cce5` Wave 1) |
| P4-7 | Graceful module-flag degradation | all | P1-* | M | flag-off empty states | DONE (`267cce5` Wave 1) |

**Phase 4 deferrals (documented in-page; DONE is not over-read).**
- P4-2 Safety Manager: create/view/triage wired; enrich, status update,
  assign, SRAM save, CAN issue, CAP create/review/status, bulletin
  publish, import, SAG/SRB authoring deferred (per
  `safety.html` header — this roadmap item is superseded by safety.html).
- P4-3 Department Head: CAP create/edit/submit wired; evidence upload,
  response-to-review, status change beyond submit deferred (per
  `dashboard/my-tasks.html` header — this roadmap item is superseded by
  my-tasks.html).

---

## PHASE 5 — TESTS
**Purpose.** Verify each phase; satisfy the SCHEMA_RECONCILIATION_PLAN gate.

**Content.**

| ID | Test scope | Depends | Effort |
|---|---|---|---|
| P5-1 | Schema/migration suite: new columns/tables + RLS (per P1-*) | Phase 1 | L |
| P5-2 | `test_domain_schema.py` green (gate) | P5-1 | S |
| P5-3 | Service unit tests per SN (triage, enrichment, timer, SAG, BSV, acceptance, SPT, materialization) | Phase 2 | XL |
| P5-4 | RLS/isolation tests: NULL-tenant CAAN-only; cross-tenant denied; dept scoping | P1-27,P1-28 | M |
| P5-5 | RBAC tests: role matrix, conflicts, non-delegability | P1-29,P1-31,P2-26 | L |
| P5-6 | API contract tests (envelope, params, terminal rules) | Phase 3 | L |
| P5-7 | E2E dashboard tests (4 dashboards, KPI drill-down, queues) | Phase 4 | L |
| P5-8 | Security regression (H1/H2/M5 remediations) | P2-27,P2-26 | M |
| P5-9 | Full suite: no regression (`SCHEMA_RECONCILIATION_PLAN.md` §4) | all | M |

**Current implementation.** 137+ backend tests exist; some pre-failing
(`SCHEMA_RECONCILIATION_PLAN.md` §4).

**Gaps.** No tests currently exercise `sms_maturity._read/_write` against
Postgres; no RLS/isolation test for Module C tables.

---

## PHASE 6 — DEPLOYMENT
**Purpose.** Roll out safely with rollback and audit evidence.

**Content.**

| ID | Step | Depends | Effort |
|---|---|---|---|
| P6-1 | Apply migrations in order (ORM + `supabase/migrations`) with rollback per migration | Phase 1, P5-1 | M |
| P6-2 | Apply RLS changes (enable policies; verify CAAN-only) | P6-1, P5-4 | S |
| P6-3 | Seed reference data (`taxonomy_mappings`, `metric_definitions`) | P6-1 | S |
| P6-4 | Flip module feature flags per tenant (`module_b_srm`, `module_b_can_cap`, `module_c_regulator`) | P6-1 | S |
| P6-5 | Deploy backend services + endpoints | Phase 2-3, P5-6 | M |
| P6-6 | Deploy frontend dashboards | Phase 4, P5-7 | M |
| P6-7 | Enable audit writers; verify `audit_logs` coverage | P2-24 | S |
| P6-8 | UAT / pilot (single tenant, then CAAN) per `COMPLIANCE_MATRIX.md` §10 | P6-5,P6-6 | L |
| P6-9 | Assemble audit evidence pack (compliance rows → artifacts) | all | M |

**Gaps.** No CI/CD migration gate documented; deployment is manual per
`SCHEMA_RECONCILIATION_PLAN.md`.

---

## PHASE 7 — POST-PILOT ITERATION (TBD)

**Purpose.** Capture work arising from pilot deployment: audit feedback,
user-observed bugs, compliance adjustments, discovered gaps.

**Content.** TBD pending pilot outcomes. Placeholder tasks:
- P7-1: Audit feedback remediation (from CAAN post-pilot review)
- P7-2: User-observed bug fixes (from operator feedback)
- P7-3: Schema adjustments (from real-data friction)
- P7-4: Predictive/prescriptive analysis implementation (per Q11.2 vendor vs
  in-house decision — deferred)
- P7-5: State-to-State safety information sharing (per Q-C8 — deferred pending
  CAAN agreements)
- P7-6: Additional compliance items surfaced during audit

**Purpose of this placeholder:** Documents that the roadmap does not end at
deployment. Real-world iteration follows.

---

## CRITICAL PATH & SEQUENCING SUMMARY
**Content.**
- **Hard chain:** P1-1 → P2-1 → P2-2 (Module A); P1-4 → P1-7/P1-8/P1-9 →
  P2-3/P2-9 etc.; P1-20 → P1-27 → P2-17 → P2-18/P2-23.
- **Blocking single rows** (`COMPLIANCE_MATRIX.md` §9): confidential reporting
  (P2-25), AE non-delegability (P2-5/P2-15), sms_maturity (P1-1).
- **Recommended wave order:**
  1. Phase 0 gate + P1-1..P1-3 (Module A critical defect).
  2. Module B schema (P1-4..P1-19) + services P2-3..P2-16.
  3. Module C schema (P1-20..P1-28) + services P2-17..P2-23.
  4. RBAC/platform (P1-29..P1-31, P2-26..P2-30).
  5. APIs, dashboards, tests, deployment.
- **Effort roll-up (rough):** Phase 1 ≈ 4-6 weeks; Phase 2 ≈ 8-12 weeks;
  Phase 3 ≈ 3-4 weeks; Phase 4 ≈ 5-7 weeks; Phase 5 ≈ 4-6 weeks; Phase 6 ≈ 2-3
  weeks (serialized; parallelizable by module).

**Gaps.** Estimates are planning-grade, not sprint-committed; no developer
capacity assumption.

---

## OPEN ITEMS
- SN3 timelines — RESOLVED (Chunk 2c decision): H=24h/M=7d/L=15d are ADVISORY
  with automatic overdue flag. Do NOT block workflow. Implementation: P2-3
  derives `follow_up_date`; the overdue flag is computed at read time (per SN4).
- `REGULATORY_LIAISON` — RESOLVED (RBAC Q-R3): FOLD into `SAFETY_OFFICER`. No new
  role. Regulatory reporting handled by `SAFETY_OFFICER` with audit trail. P1-29
  needs only `ACCOUNTABLE_EXECUTIVE` + `SAG_MEMBER` literals.
- Canonical module-flag names / `module3` mismatch (RBAC Q-R5; Dashboard Q-D6).
- Predictive/prescriptive vendor vs in-house (Module C Q11.2) — gates a future
  phase beyond P2-23.
- CAR-19 official text (COMPLIANCE_MATRIX Q-C1).

---

*End of IMPLEMENTATION_ROADMAP.md. Status: PHASE 3 COMPLETE — P1-1..P1-31,
P2-1..P2-30 and P3-1..P3-15 DONE. Phase 1 commits: Module A `846913d`, Module B
`3a68f38`, Module C `ce7102a`, RBAC `d15ebd3` (16 migrations). Phase 2 commits:
Module A `00a16b7`, Module B `b3b823b`+`78dd589`, Module C `9b15eab`, RBAC
`98986aa`. Phase 3 commits: Wave 1 `f6db16a`, Wave 2 (Part A close-out).
Phase 4 Waves 1-3 complete (P4-1, P4-2, P4-3, P4-6, P4-7);
Waves 4-5 (P4-4 AE, P4-5 State Regulator) pending. Phase 5+ items remain PENDING.*


---

## Conflict notes

- **CI pipeline:** Part A proposes a CI pipeline (Phase 1); Part B's Phase 6 notes "No CI/CD migration gate documented". Same gap, two descriptions; Part A (newer) is the current statement.
- **AE dashboard:** Part A lists "Phase 2A — AE Dashboard Redesign (details TBD)"; Part B lists P4-4 AE dashboard PENDING (Wave 4). Consistent; Part B holds the item-level detail.
- **Historical import:** Part A "Phase 2B — Historical Import"; Part B implements it as P2-14/P3-6. Consistent.
- **Security status:** Part B (2026-09-22) marks P2-26/P2-27 (RBAC middleware, H1/H2) DONE; `SECURITY_REVIEW.md` (2026-09-18) and the Step 0 analysis report the middleware unregistered and some routes under-authorized. Retained as recorded in Part B; re-verify against the code in Step 1 before relying on the "DONE" status. No content removed.
- No other conflicts found; all content from both source files is retained.

## Sources

- `ROADMAP.md` (2026-10-05) — archived at `_archive/historical/ROADMAP.md`
- `IMPLEMENTATION_ROADMAP.md` (2026-10-02) — archived at `_archive/historical/IMPLEMENTATION_ROADMAP.md`