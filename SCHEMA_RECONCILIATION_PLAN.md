# SCHEMA RECONCILIATION PLAN — ORM vs Live Drift Resolution

- **Status**: IN IMPLEMENTATION. Steps 1 (D7), 2 (D1), 3 (D5), 4 (D6) complete in the ORM; Step 2 applies to the live DB via migration `supabase/migrations/20260916120000_sram_risk_register.sql`; Step 5 (D4) pending. §3 reflects the applied numeric D1 decisions (see Step 2).
- **Inputs**: SCHEMA_DRIFT_REPORT.md (all drift verdicts), MODULE_A_CONTRACT.md §2.2/§7/§8, SURVEY_RISK_INJECTION_VALIDATION.md (D10), DB_VERIFICATION.md, live DB introspection, CAAN SRM Procedure Manual (First Edition, January 2026).
- **Finals**: Decisions D1–D10 are FINAL and taken as given. No alternatives proposed.

---

## 1. Executive Summary

**Tables affected by this plan: 4 CRITICAL + 3 MEDIUM + 11 MINOR = 18 tables.** The 11 MINOR split as: 10 tables gaining `is_demo` in the ORM (D7) + `caps` documented only (D9). The 6 live-only ADREP/HFACS tables are not ORM-migrated here (D8, fact-finding only).

**Files to modify (estimate ~14):** `backend/app/db/db_models.py`, `backend/app/db/schema_init.py`, `backend/app/db/pg.py`, `backend/app/services/sram_service.py`, `backend/app/services/admin_data_service.py`, `backend/app/services/invites.py`, `backend/app/services/dashboard_service.py`, `backend/app/routes/feedback.py`, `backend/app/routes/admin.py`, `backend/tests/test_domain_schema.py` (updated), plus 2–3 new DB migration files and new/updated test files. `backend/app/services/report_generator.py` requires audit only (verified: it references `StateRiskRegisterEntry` only — no D1 change needed).

**Order of implementation (summary — full detail in §3):**
1. D7 (add `is_demo` to 10 MINOR ORM models) — lowest risk, feeds Module B gate
2. D1 (split `risk_register` into legacy `risk_register` + new `sram_risk_register`) — Module B blocker
3. D5 (regulators ORM extension) · 4. D6 (users.phone UNIQUE) · 5. D4 (tenants.safety_manager type) · 6. D9 (caps — document only)
7. D2 (sms_maturity ORM rewrite + RLS enable) — Module A
8. D3 (invites + feedback ORM rewrite) — shared
9. D8 (ADREP/HFACS fact-finding)
10. Full test suite

**Readiness gate for Module B contract: NOT YET READY** — blocked on D1 (risk_register split) + D7 (`is_demo` on the 10 MINOR models) + a full passing test suite. Steps 2 and 1 of the sequence clear the D1/D7 gate. Steps 7 (D2), 8 (D3), 5 (D4), 3 (D5), 4 (D6), 9 (D8) do not block Module B. See §6 for the precise gate.

**Explicit statement:** Module B's contract is **blocked until `risk_register` (legacy shape) and `sram_risk_register` (SRAM shape) both exist** with their target shapes and `sram_service.py` writes/reads the SRAM table successfully.

Note: the live database holds demo data only (all `is_demo = true`; `risk_register`, `sms_maturity`, `invites`, `feedback` are 0 rows; `tenants` is 1 demo row). Every live migration below therefore has near-zero data-loss risk, but is still implemented with a migration + rollback step per §3.

---

## 2. Per-Table Plan

Legend: Impact = effort estimate. Regression risk = likelihood of breaking currently-passing behavior/tests.

| # | Table | Decision | Current state (drift) | Target state | Files to change (full paths) | Impact | Regression risk | Test coverage needed |
|---|---|---|---|---|---|---|---|---|
| 1 | `risk_register` | **D1** | ORM=SRAM shape (db_models.py:1321-1360) vs live=legacy SRM shape; every SRAM SELECT/INSERT fails (`UndefinedColumn`) | keeps legacy shape; ORM model renamed `RiskRegisterLegacyEntry`; SRAM writes move to `sram_risk_register` | `backend/app/db/db_models.py`, `backend/app/services/sram_service.py`, `backend/app/services/admin_data_service.py`, `backend/app/services/report_generator.py` (audit only — no change), new migration | **Large** | Med — rename touches 3 services; report_generator confirmed clean | SRAM write→read round-trip; legacy-table unaffected; purge/export still reference `risk_register` name |
| 2 | `sram_risk_register` (new table) | **D1** | does not exist (live or ORM) | new table + ORM `SramRiskRegisterEntry` (SRAM shape) | `backend/app/db/db_models.py`, `backend/app/db/schema_init.py` (new DDL), `backend/app/db/pg.py` (PK map), new migration | **Large** | Low — additive table | `sram_service.calculate_risk` / `accept_risk` / `get_risk_register` / `_resolve_risk_entry` against new table |
| 3 | `sms_maturity` | **D2** | ORM tenant_id:TEXT/days/data (1633-1647) vs live assessment shape; RLS OFF; writes/reads fail (`days` UndefinedColumn, probe-confirmed) | ORM adopts live shape; `dashboard_service` R/W rewritten; schema_init DDL replaced; RLS enabled | `backend/app/db/db_models.py`, `backend/app/services/dashboard_service.py`, `backend/app/db/schema_init.py`, new migration (R) , `backend/tests/test_domain_schema.py` (update) | **Medium** | Med — breaks `test_domain_schema.py` (must update same step) | cache write→read round-trip per tenant; RLS policy `p_sms_maturity_tenant_isolation` present |
| 4 | `invites` | **D3** | ORM code=TEXT PK + `data` jsonb vs live uuid PK, email NOT NULL, tenant_id uuid FK, department/created_by, code UNIQUE | ORM matches live (id uuid PK, role/department/status fields) | `backend/app/db/db_models.py`, `backend/app/services/invites.py`, `backend/app/routes/feedback.py` (no), `backend/tests/test_domain_schema.py` (update) | **Medium** | Med — breaks `test_domain_schema.py` (PK/data assertions) | invite create/list against live shape; code lookup by UNIQUE column |
| 5 | `feedback` | **D3** | ORM email/category/data vs live user_email/rating/subject/message/page/status; mirror write + admin list fail-logged | ORM matches live shape | `backend/app/db/db_models.py`, `backend/app/routes/feedback.py`, `backend/app/routes/admin.py`, `backend/tests/test_domain_schema.py` (update) | **Small** | Low | feedback mirror write; `admin.list_feedback` status query |
| 6 | `tenants` | **D4** | `safety_manager` JSONB (ORM) vs varchar (live); live UNIQUE(tenant_id) not declared | ORM unchanged (jsonb); live column migrates varchar→jsonb with parse+re-store of the 1 demo row | new DB migration script (`backend/app/db/migrations/0014_tenants_safety_manager_jsonb.py` proposed), `backend/tests/test_tenants_config.py` (extend) | **Small** | Low — 1 demo row | jsonb read/write round-trip; legacy varchar value parses |
| 7 | `regulators` | **D5** | ORM missing 8 live columns (short_name, country_code, country_name, domain, status, contact_email, contact_phone, website) | ORM extended with the 8 columns (Module C surface) | `backend/app/db/db_models.py`, `backend/tests/test_regulators.py` (extend) | **Small** | Low — additive | create/read with extended columns |
| 8 | `users` | **D6** | live UNIQUE(phone) not in ORM | ORM `UserProfile.phone` gets `unique=True` | `backend/app/db/db_models.py` | **Trivial** | Low | duplicate-phone insert rejected at ORM level |
| 9 | `caps` | **D9** | ORM `resources_required`/`implementation_plan` NOT NULL vs live nullable | NO code change — documented known divergence (ORM stricter) | none | **None** | None | none (documented in §5) |
| 10 | `corrective_actions` | **D7** | live-only `is_demo` bool default true | ORM adds `is_demo bool nullable default true` | `backend/app/db/db_models.py` | **Small** | Low | ORM insert preserves is_demo |
| 11 | `safety_deficiencies` | **D7** | live-only `is_demo` | ORM adds `is_demo` | `backend/app/db/db_models.py` | **Small** | Low | same |
| 12 | `flight_diversions` | **D7** | live-only `is_demo` | ORM adds `is_demo` | `backend/app/db/db_models.py` | **Small** | Low | same |
| 13 | `verifications` | **D7** | live-only `is_demo` | ORM adds `is_demo` | `backend/app/db/db_models.py` | **Small** | Low | same |
| 14 | `closures` | **D7** | live-only `is_demo` | ORM adds `is_demo` | `backend/app/db/db_models.py` | **Small** | Low | same |
| 15 | `psoe_questions` | **D7** | live-only `is_demo` | ORM adds `is_demo` | `backend/app/db/db_models.py` | **Small** | Low | same |
| 16 | `psoe_findings` | **D7** | live-only `is_demo` | ORM adds `is_demo` | `backend/app/db/db_models.py` | **Small** | Low | same |
| 17 | `bow_tie_threats` | **D7** | live-only `is_demo` | ORM adds `is_demo` | `backend/app/db/db_models.py` | **Small** | Low | same |
| 18 | `bow_tie_consequences` | **D7** | live-only `is_demo` | ORM adds `is_demo` | `backend/app/db/db_models.py` | **Small** | Low | same |
| 19 | `bow_tie_controls` | **D7** | live-only `is_demo` | ORM adds `is_demo` | `backend/app/db/db_models.py` | **Small** | Low | same |

Note on D7 count: the MINOR bucket is 11 tables (`caps` + 10). D7 operates on the 10 listed above with a nullable defaulted column — identical to how hazards/reports/cans/caps already model `is_demo` (db_models.py:118, 242, 333, 471).

---

## 3. Implementation Sequence

### Step 1 — D7: add `is_demo` to the 10 MINOR ORM models
- **Changes**: add `is_demo: Mapped[bool] = mapped_column(Boolean, nullable=True, default=True)` to `CorrectiveAction` (db_models.py:588), `SafetyDeficiency` (:658), `FlightDiversion` (:713), `Verification` (:772), `Closure` (:815), `PsoeQuestion` (:960), `PsoeFinding` (:993), `BowTieThreat` (:1251), `BowTieConsequence` (:1272), `BowTieControl` (:1294). No live change (column exists).
- **Prerequisites**: none.
- **Dependents**: Step 2 shares db_models.py; Step 10 runs the suite.
- **Success criteria**: all 10 models carry the column; ORM table metadata collects; existing tests pass unchanged.
- **Rollback**: revert db_models.py (pure ORM edit, no DB change).

### Step 2 — D1: split `risk_register` → legacy `risk_register` + `sram_risk_register` (Module B blocker)
- **Changes**: (a) rename `RiskRegisterEntry` (db_models.py:1321) → `RiskRegisterLegacyEntry`, remap columns to the live legacy shape (id, tenant_id uuid FK, hazard_id uuid FK→hazards.id, srm_date NOT NULL, ultimate_consequence NOT NULL, existing_*/resultant_* index+severity+probability+tolerability, status, follow_up_date, date_completed, remarks, concerned_department, created_by, updated_by, created_at, updated_at, is_demo). (b) add `SramRiskRegisterEntry` mapped to new `sram_risk_register` (id, tenant_id, hazard_id TEXT business reference [deviation: NOT uuid FK — matches bow_tie/barrier conventions and sram_service round-trips on business hazard ids], bowtie_id FK→bow_tie_analyses(id) ON DELETE SET NULL, hazard_title, probability_current/severity_current/risk_index_current/tolerability_current NOT NULL, resultant_*, status default 'open', accepted bool default false, alarp_justification, accepted_by uuid, accepted_on, review_date timestamptz [deviation: plan said `date`; ORM/service write datetimes so TIMESTAMPTZ used for round-trip consistency], is_demo, created_at, updated_at). (c) **Numeric storage** (final decision, CAAN §2.3.6.4): severity/probability stored int 1-5, risk_index = severity × probability (int 1-25), letters A-E are display-only (A=5 … E=1). RiskCalculations return numeric `severity` and `risk_index` plus `severity_letter`/`risk_index_display` for the UI. (d) update `sram_service.py` import/usage: `calculate_risk` (:339-348), `accept_risk` (:365-399), `get_risk_register` (:452-459), `_resolve_risk_entry` (:570-595) → `SramRiskRegisterEntry`; `accept_risk` resolves the auth user's uid/email to `users.id` uuid via `UserProfile` lookup into `accepted_by` (None if unresolved — never a non-UUID string; replaces the email-text write at :383). (e) `admin_data_service.py`: import (:60), scoped purge delete (:1102), demo count (:1387) → `RiskRegisterLegacyEntry`. (f) audit `report_generator.py` — confirmed no `RiskRegisterEntry` reference (only `StateRiskRegisterEntry`, :8/:302); no change. (g) add CREATE TABLE DDL for `sram_risk_register` to `backend/app/db/schema_init.py`; add `("sram_risk_register", "id")` to the PK map in `backend/app/db/pg.py` (:62 area); add a DB migration that creates the new table (legacy table untouched). (h) add mapping helpers to `risk_calculator.py`: `SEVERITY_TO_VALUE` A=5…E=1, `VALUE_TO_SEVERITY`, `CAAN_SEVERITY_REFERENCE`, `severity_to_letter`, `risk_index_to_display`; `get_risk_matrix`/`build_risk_matrix` return numeric values. No letter→numeric conversion migration is needed: live `risk_register` is the pre-SRAM legacy shape (numeric ints, no SRAM/letter columns, 0 rows) and `sram_risk_register` starts empty.
- **Prerequisites**: Step 1 (db_models.py edit pattern proven).
- **Dependents**: Module B contract (this step clears its gate); Step 10.
- **Success criteria**: live `risk_register` shape untouched; `sram_risk_register` exists with target columns; `calculate_risk`/`accept_risk`/`get_risk_register` round-trip against the new table with numeric severity/probability/risk_index (flight e.g. probability 4 + severity C → severity 3, risk_index 12); `accept_risk` stores a users.id uuid into `accepted_by`; `test_domain_schema.py` stays green (34/34).
- **Rollback**: drop `sram_risk_register`; keep rename (revert import updates) — empty table, no data loss.

### Step 3 — D5: regulators ORM extension
- **Changes**: add 8 columns to `Regulator` (db_models.py:1464): `short_name`, `country_code`, `country_name`, `domain`, `status` (default 'active'), `contact_email`, `contact_phone`, `website` (all Text, nullable except `status`).
- **Prerequisites**: none.
- **Dependents**: Module C contract (consumes extended fields); Step 10.
- **Success criteria**: ORM metadata includes the 8 columns; `create_regulator`/reads work with them.
- **Rollback**: revert db_models.py.

### Step 4 — D6: users.phone UNIQUE
- **Changes**: `UserProfile.phone` (db_models.py:1506) → `unique=True`.
- **Prerequisites**: none. **Dependents**: Step 10.
- **Success criteria**: ORM DDL declares UNIQUE(phone); live already enforces it (no live change).
- **Rollback**: revert db_models.py.

### Step 5 — D4: tenants.safety_manager varchar→jsonb (live migration)
- **Changes**: DB migration only. Live `tenants.safety_manager` (varchar) → jsonb; parse the single existing demo row (string→object) and re-store. ORM and `schema_init.py:132` already declare JSONB — no ORM change.
- **Prerequisites**: Steps 3 share no files; can run in parallel. **Dependents**: platform/dashboard reads of safety_manager; Step 10.
- **Success criteria**: live column type is jsonb; demo row's safety_manager is a JSON object; `pg`/ORM jsonb reads parse.
- **Rollback**: migration down-script re-casts to varchar (values back to JSON-string text).

### Step 6 — D9: caps nullability
- **Changes**: none. Document as known divergence (ORM stricter than live) in §5. No code, no migration.
- **Prerequisites**: none. **Dependents**: none.
- **Success criteria**: divergence recorded; no behavioral change.

### Step 7 — D2: sms_maturity ORM rewrite + RLS enable (Module A)
- **Changes**: (a) rewrite `SmsMaturity` (db_models.py:1633-1647) to live shape (id uuid PK, tenant_id uuid FK→tenants.id, assessment_date timestamptz default now(), overall_score double, level int CHECK 1-5, pillar_scores/element_scores/gap_analysis/recommendations jsonb, created_at, updated_at) — remove `days`, `data`, the unique(days) constraint. (b) rewrite `dashboard_service._read_sms_maturity` (:950-963) and `_write_sms_maturity` (:966-972) to live columns. (c) replace `schema_init.py:283-292` DDL with the live shape (idempotent). (d) RLS: ENABLE ROW LEVEL SECURITY on `sms_maturity` with `p_sms_maturity_tenant_isolation`, following the surveys/survey_responses pattern. (e) update `backend/tests/test_domain_schema.py` (drop `sms_maturity` `data` column assertion at :53, PK assertion at :28 already `id`).
- **Prerequisites**: Steps 1-2 (db_models.py stable first). **Dependents**: Module A production; Step 10.
- **Success criteria**: `_write_sms_maturity`/`_read_sms_maturity` round-trip against live; RLS enabled + policy present; `test_domain_schema.py` updated and green.
- **Rollback**: revert ORM + schema_init; RLS remains OFF if migration down-script runs (or policy revoked).

### Step 8 — D3: invites + feedback ORM rewrite (shared)
- **Changes**: (a) rewrite `Invite` (db_models.py:1581-1595): id uuid PK default gen_random_uuid(), email NOT NULL, tenant_id uuid FK→tenants(id), role NOT NULL, department, code NOT NULL UNIQUE, status default 'pending', created_by, expires_at default now()+7d, created_at. (b) rewrite `Feedback` (db_models.py:1598-1613): id uuid PK, user_email NOT NULL, tenant_id uuid FK, rating int CHECK 1-5, subject, message, page, status default 'new', created_at. (c) update call sites: `services/invites.py` (:96, :120, :210, :256), `routes/feedback.py:73` (mirror write), `routes/admin.py:1490-1544` (`list_feedback` — query `Feedback.status` instead of `Feedback.data["status"]`). (d) update `backend/tests/test_domain_schema.py` (invites PK `code` at :25 → `id`; drop `data` assertions for invites :50 and feedback :51).
- **Prerequisites**: Steps 1-2. **Dependents**: task said shared concern; Step 10.
- **Success criteria**: invite create/list work against live; feedback mirror write + admin list succeed against live; `test_domain_schema.py` green.
- **Rollback**: revert ORM + service/route edits (empty tables, no data loss).

### Step 9 — D8: ADREP/HFACS fact-finding (no fix)
- **Changes**: investigate (a) usage of `hazard_adrep_mappings`, `hazard_hfacs_codes`, `report_adrep_mappings`, `report_hfacs_codes`; (b) usage of `icao_adrep_taxonomies` (15 rows), `hfacs_nanocodes` (106 rows); (c) whether `hazards.adrep_category` / `hazards.occurrence_type` supersede the mapping tables. No ORM models, no DDL.
- **Prerequisites**: none. **Dependents**: Module B/C contract scope decision on taxonomy tables.
- **Success criteria**: documented answers to D8(a)(b)(c); recommendation filed for a later contract phase.
- **Rollback**: N/A (read-only).

### Step 10 — Full test suite
- **Changes**: run `backend/tests/` in full; confirm no currently-passing test regressed and no new failures.
- **Prerequisites**: Steps 1-8 complete. **Dependents**: Module B contract gate (§6).
- **Success criteria**: all previously-passing tests still pass; new tests from §4 pass.
- **Rollback**: upstream step reverts as defined.

---

## 4. Test Impact

Prior inventory: **137+ backend tests in `backend/tests/`** (some already failing per earlier inventory). References below by test file.

| Fix (Step) | Existing tests that may break | Tests currently failing this may resolve | New tests to add | Owner test file |
|---|---|---|---|---|
| D7 (Step 1) | none expected — additive nullable column | `test_seed_scope.py`, `test_purge_demo_data.py`: ORM can now read/write `is_demo` on these tables (previously invisible) — may stabilise demo-scope assertions | per-model is_demo insert round-trip for the 10 tables | new `backend/tests/test_is_demo_columns.py` |
| D1 (Step 2) | `test_admin_export.py` (:50,:52) and `test_purge_demo_data.py` (:35,:37) reference the *table string* `risk_register` — preserved (table keeps its name); `test_srm_engine.py` (pure calc, no DB) unaffected | none known | SRAM round-trip (calculate→accept→get_risk_register→resolve), legacy table untouched, `sram_risk_register` in purge/export scope lists | new `backend/tests/test_risk_register_d1.py`; extend `test_admin_export.py`, `test_purge_demo_data.py` |
| D5 (Step 3) | `test_admin_seed.py` (create_regulator, :241-293), `test_regulators.py` — additive cols safe | none | create/read regulator with extended columns | extend `backend/tests/test_regulators.py` |
| D6 (Step 4) | none | none | ORM rejects duplicate phone | extend `backend/tests/test_identity_pg.py` |
| D4 (Step 5) | `test_domain_schema.py` (:44 keeps jsonb) — safe; `test_pg_doc_mapping.py`/`pg_bridge.py` treat `safety_manager` as jsonb — consistent | none | legacy varchar value parses to json; round-trip | extend `backend/tests/test_tenants_config.py` |
| D2 (Step 7) | **`test_domain_schema.py`** (:53 asserts `sms_maturity.data` exists — breaks; :28 `id` PK OK) — update in same step | none | `_write_sms_maturity`/`_read_sms_maturity` round-trip; RLS policy present | new `backend/tests/test_sms_maturity_cache.py`; update `test_domain_schema.py` |
| D3 (Step 8) | **`test_domain_schema.py`** (:25 invites PK `code`, :50 invites `data`, :51 feedback `data` — break) — update in same step; `test_feedback.py`/`test_admin_feedback.py` are Firestore-mocked and read-route based — expected safe, verify | none | invite create/list against live shape; feedback mirror + admin list | new `backend/tests/test_invites.py`; extend `backend/tests/test_feedback.py`; update `test_domain_schema.py` |
| D9 (Step 6) | none | none | none | none |

Independent of the fixes: no test currently exercises `sms_maturity._read/_write` against Postgres (MODULE_A_CONTRACT.md §7 item 8) — the new `test_sms_maturity_cache.py` closes this gap.

---

## 5. Deferred Items

> **D9 (caps nullability) — accepted, no action (Step 6, 2026-09-17).** `Cap.resources_required` / `Cap.implementation_plan` remain NOT NULL in the ORM (db_models.py:390-391) while live `caps` keeps both columns nullable (probe-confirmed 2026-09-17). The ORM is deliberately stricter; no code change and no migration.

| Item | Reason for deferral | Addressed where |
|---|---|---|
| D8 — `icao_adrep_taxonomies`, `hfacs_nanocodes`, `hazard_adrep_mappings`, `hazard_hfacs_codes`, `report_adrep_mappings`, `report_hfacs_codes` (6 live-only tables) | ORM registration deferred pending the Step 9 fact-finding (are they code-referenced? do `hazards.adrep_category`/`occurrence_type` supersede the mapping tables?) | Module B or Module C contract after Step 9 findings |
| Constraint-naming divergence (auto vs explicit names on ~20 matched tables) | Non-breaking (SCHEMA_DRIFT_REPORT.md §6.2); cosmetic | Future phase (not any contract) |
| live-only extra CHECK `regulatory_reports.quarter BETWEEN 1 AND 4` | Non-breaking; live-side guardrail | Future phase |
| live extra indexes (`ix_hazards_tenant_function`, `idx_cans_psoe_assessment_id`, `ix_bow_tie_analyses_tenant_status`, regulator indexes) | Informational | Future phase |
| `caps` nullability divergence (D9) | Deliberate no-action (ORM stricter); documented here | Module B contract (known divergence) |
| Boundary violation — dashboard→`sms_maturity` direct write (MODULE_A_CONTRACT.md §7.1: `dashboard_service._write_sms_maturity` :966) | D2 fixes the storage shape only; the ownership redesign (module owns its tables) is a contract concern | Module A contract remediation / dashboard contract, NOT Module B |
| `sms_maturity` LLM async cache pipeline (MODULE_A_CONTRACT.md §7 items 4-5: inline synchronous Gemini call at gemini.py:405; no background job) | Out of scope here — D2 is storage-only | Module A contract / future phase |
| `psoe_questions.is_demo` exists in live but is intentionally NOT modelled in the ORM (2026-09-17) | The table is GLOBAL reference data shared across tenants and must not participate in tenant/demo purge; the purge coverage guard (`test_purge_covers_every_is_demo_table`) excludes it explicitly | Known divergence; documented at admin_data_service.py (purge comment) and db_models.py (PsoeQuestion) |

---

## 6. Readiness Gate for Module B Contract

Module B's contract may be written when:

- [x] D1 complete: `risk_register` and `sram_risk_register` both exist with their target shapes (ORM + migration `20260916120000_sram_risk_register.sql`; legacy table untouched)
- [x] D1 complete: `sram_service.py` updated to use `SramRiskRegisterEntry`
- [x] D1 complete: `report_generator.py` and `admin_data_service.py` audited for `RiskRegisterEntry` usage (report_generator clean; admin_data_service → `RiskRegisterLegacyEntry`)
- [x] D7 complete: `is_demo` added to all 10 MINOR ORM models (caps is handled separately by D9 — no change required, ORM already stricter)
- [ ] Test suite passes: all currently-passing tests still pass (gate: `test_domain_schema.py` 34/34 green)
- [ ] No new failures introduced

**Module B contract note (D1 numeric SRAM register):** the contract MUST specify numeric severity/probability (int 1-5) and numeric risk index (int = severity × probability, 1-25); A-E letters are display-only and never stored. The safe-domain descriptor mapping is 5=Catastrophic, 4=Major/Hazardous, 3=Moderate/Major, 2=Minor, 1=Negligible/Insignificant (CAAN §2.3.6.4). API responses carry numeric `severity`/`risk_index` plus `severity_letter`/`risk_index_display` for the UI (see `risk_calculator.get_risk_matrix`). `accepted_by` is the accepting user's `users.id` (uuid), resolved from the stored uid/email at accept time.

Items deferred (do not block Module B):
- D2 (`sms_maturity`) — Module A concern
- D3 (invites/feedback) — shared concern
- D4 (tenants.safety_manager) — platform concern
- D5 (regulators) — Module C concern
- D6 (users.phone) — platform concern
- D8 (ADREP/HFACS) — pending investigation

---

## 7. Step 9 — D8 ADREP/HFACS Investigation Results

Date: 2026-09-17. Mode: read-only (grep + context reads; no writes, no live-DB
queries in this pass). Inputs: SCHEMA_DRIFT_REPORT.md §4.4/§5/§7 (6 live-only
tables), DB_VERIFICATION.md, this plan's D8 deferral entry.

### Q1 — Are the four mapping tables referenced anywhere in the codebase?

**No functional references.** No ORM model, service, route, or SQLAlchemy query
touches `hazard_adrep_mappings`, `hazard_hfacs_codes`, `report_adrep_mappings`,
`report_hfacs_codes`. All matches are bookkeeping/documentation:

| file:line | context |
|---|---|
| `backend/scripts/reset_to_virgin.py:105-108` | `PRESERVED` list — tables are **never truncated/deleted**, only counted and reported (`# *` = "may not exist yet" / reference) |
| `SCHEMA_DRIFT_REPORT.md:17,198-201` | Drift inventory (live-only, 0 rows, FK shapes) |
| `SCHEMA_RECONCILIATION_PLAN.md:115,153` | Step-9 scope + D8 deferral row |
| `DB_VERIFICATION.md:125,150-166,189` | RLS existence scan |

Partial-match evidence (substring `hfacs_code` / `adrep_mapping`):

| file:line | context |
|---|---|
| `backend/app/services/aggregation_service.py:88` | `"hfacs_code": None` — a **field name** on the anonymized hazard dict, hardcoded `None` (never populated) |
| `backend/app/services/aggregation_service.py:153` | `h.get("hfacs_code")` — reads that dict field (always `None`); never queries a table |
| `backend/seeders/hazards/hazard_seeder.py:450,456-474,482,546` | `self.hfacs_codes = self._load_hfacs_codes()` loads `public/data/hfacs_nanocodes.json` (a **JSON file**, not the PG table); `"hfacs_codes": hazard_data.get("hfacs", [])` writes a codes list into the **hazard seed row** |

`adrep_mapping` matches are only the docs and `reset_to_virgin.py` rows above.

**Q1 verdict:** the four mapping tables are unreferenced by runtime code and
hold **0 rows** live → vestigial.

### Q2 — Are the two reference tables referenced anywhere in the codebase?

**No runtime/ORM references** to `icao_adrep_taxonomies` / `hfacs_nanocodes`.
Matches:

| file:line | context |
|---|---|
| `backend/scripts/reset_to_virgin.py:103-104` | `PRESERVED` (never deleted; counted/reported only) |
| `data/README.md:10-11` | CSV archive → "imported to Postgres table …" (import provenance, not runtime) |
| `docs/status.md:109-111` | HFACS **JSON** correction (`hfacs_nanocodes.json` header comments; 109 codes, 0 dupes) |
| `docs/status.md:219-220` | "`data/icao_adrep_taxonomies.csv` is imported to Supabase; keep reference CSVs versioned alongside `hfacs_nanocodes.csv`" |
| `SCHEMA_DRIFT_REPORT.md:17,196-197` / `DB_VERIFICATION.md:157-158` | Live-only inventory: 15 / 106 rows |

The taxonomy data that the application actually consumes comes from a **static
JSON copy**, not these tables:

| file:line | context |
|---|---|
| `public/js/views/hazard-analysis.js:67` | `fetch('/data/hfacs_nanocodes.json')` populates the HFACS dropdown |
| `backend/seeders/hazards/hazard_seeder.py:458-474` | loads `../../../public/data/hfacs_nanocodes.json` for seed validation |
| `tests/e2e/phase2_uat_verification.py:92-96` | verifies `public/data/hfacs_nanocodes.json` loads |

**Q2 verdict:** reference tables are an import-time data archive; runtime reads
the versioned JSON (`public/data/hfacs_nanocodes.json`) and CSVs, not the PG
tables → vestigial for runtime.

### Q3 — Is there a parallel taxonomy mechanism in use?

**Yes.** Taxonomy is stored **denormalized as TEXT directly on the hazard and
report rows**; the mapping tables are bypassed entirely.

`hazards` columns (first-class, modelled):

| file:line | context |
|---|---|
| `backend/app/db/db_models.py:78-81` | `Hazard` ORM: `adrep_category`, `occurrence_type`, `taxonomy`, `taxonomy_specific` |
| `backend/app/db/schema.sql:44-46` + `supabase/migrations/20260830130516_remote_schema.sql:341` | DDL matches (`adrep_category`/`occurrence_type`, taxonomy CHECK) |
| `backend/app/models/hazard.py:205,256,298` | `HazardCreate` / read schemas carry `adrep_category` |

Writers:

| file:line | context |
|---|---|
| `backend/app/services/hazard_service.py:322-323` | `HazardService.create_hazard` writes `adrep_category=payload.get("adrep_category")`, `occurrence_type=…` |
| `backend/app/routes/occurrence_reports.py:385-386` | auto-created hazard copies `reports.occurrence_category → adrep_category`, `reports.occurrence_type → occurrence_type` |
| `backend/app/services/admin_data_service.py:728-729` | dummy-hazard seeding writes `occurrence_type` / `adrep_category` |
| `public/hazards/create.html:347` | hazard form posts `adrep_category` |

Readers:

| file:line | context |
|---|---|
| `backend/app/routes/hazards.py:414-415` | hazard serialization returns both columns |
| `backend/app/services/report_generator.py:215` | top-risk categories from `adrep_category or taxonomy` |
| `backend/app/services/state_risk_service.py:381-386` | state-risk classification uses `occurrence_category / taxonomy / adrep_category / occurrence_type` |
| `backend/app/services/aggregation_service.py:87,89,153,204` | ADREP category → benchmark/top-hazard rollups |
| `public/hazards/detail.html:256` | shows `h.adrep_category` |

`reports` side: `Report.occurrence_type` (`db_models.py:176`) and
`Report.occurrence_category` (`db_models.py:216`) store taxonomy text on the
row; there is **no** `adrep_category`/HFACS column in the `Report` ORM and no FK
to the mapping tables. (The separate `regulatory_reports.hfacs_summary` JSONB,
`db_models.py:1110`, is a different domain and not a mapping-table consumer.)

**Q3 verdict:** hazards/reports carry taxonomy **inline** (text columns); no code
path reads or writes any of the 6 tables.

### Q4 — Recommendation

**(b) The 6 tables are vestigial — leave them in place, do NOT model them.**

Evidence:
- Mapping tables: **0 rows** + zero runtime references (Q1) → dead schema.
- Reference tables: populated (15/106) but the only consumers are the static
  `public/data/hfacs_nanocodes.json` + CSVs + `reset_to_virgin` bookkeeping
  (Q2) → data archive, not a live path.
- The active taxonomy mechanism is the denormalized-column approach on
  `hazards`/`reports` (Q3); introducing ORM models now would add Module B
  contract surface with **no reader**.
- `reset_to_virgin.py:101-109` already treats them as `PRESERVED` (never
  wiped), so leaving them unmodelled is operationally safe.

Actions (no Module B contract items):
- Close **D8** as **no action**: no ORM models, no DDL, no migration for the 6
  tables.
- Keep the CSV/JSON data archive (`data/`, `public/data/hfacs_nanocodes.json`)
  as the maintained taxonomy source; if a future feature wants
  drop-down-from-DB taxonomy, model the two reference tables as **read-only**
  reference rows then — explicitly out of scope today.
- Consider dropping the `PRESERVED` list entries only if the tables are ever
  dropped; until then leave them untouched.

Note: the drift report's framing ("tables powering `hazards.adrep_category` /
`occurrence_type`") describes their **intended** v2 role (SCHEMA_DRIFT_REPORT.md:192);
this investigation shows the app evolved past them to inline columns + static
JSON before they were ever wired up.

---

*Planning/implementation document. Current implementation status per Steps 1-5 of §3; §6 gate tracking as of last code commit. Step 9 (D8 fact-finding) appended 2026-09-17.*