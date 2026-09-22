# IMPLEMENTATION_ROADMAP.md — Sequenced Schema-Note Implementation Plan

AviaSAFE SMS Platform
Status: PHASE 3 COMPLETE — all Phase 0/1/2/3 items (P1-1..P1-31,
P2-1..P2-30, P3-1..P3-15) DONE; Phase 4 (frontend dashboards)
implementation begins next.
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

| ID | Deliverable | Role | Depends | Effort | Test |
|---|---|---|---|---|---|
| P4-1 | Shared shell components (header, period selector, drill-down, empty/loading/error) | all | P3-14 | L | component specs |
| P4-2 | Safety Manager dashboard (5-counter KPI strip, color rules, EIP, workspace) | TENANT_ADMIN/SAFETY_OFFICER | P3-3,P3-6 | L | E2E KPI drill-down |
| P4-3 | Department Head dashboard (3-counter strip, dept CAP response) | DEPT_ADMIN | P3-9 | M | dept scoping |
| P4-4 | AE dashboard (numeric KPI strip, 2 action queues, trends) | ACCOUNTABLE_EXECUTIVE | P3-7,P3-8,P3-13 | L | queues + KPI |
| P4-5 | State Regulator dashboard (national KPIs, benchmarks, PSOE, SPI/SPT, escalation) | CAAN_SMD | P3-10,P3-11,P3-12 | XL | read-only + escalation |
| P4-6 | `nav-config.js` role types update (`ACCOUNTABLE_EXECUTIVE`, `SAG_MEMBER`) | all | P1-29 | S | role menus |
| P4-7 | Graceful module-flag degradation | all | P1-* | M | flag-off empty states |

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
Phase 4 (dashboards) begins next; Phase 4+ items remain PENDING.*
