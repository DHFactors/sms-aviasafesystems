# SCHEMA DRIFT REPORT — ORM (SQLAlchemy) vs Live Supabase PostgreSQL

- Objective: Systematically compare every ORM model (`backend/app/db/db_models.py`) against the LIVE database schema to detect drift, before Module B's contract is written.
- Method: Live introspection via psycopg2 (2026-09-16) against `SUPABASE_DATABASE_URL` in `backend/.env`. Queried for all 38 ORM tables: `information_schema.columns`, `pg_constraint` (via `pg_get_constraintdef`), `pg_indexes`, `pg_tables` (RLS), and row counts. ORM source read in full (`backend/app/db/db_models.py`, 1675 lines). No data was written; read-only.
- Scope: 38 ORM tables + 6 live-only tables discovered. Constraint *names* that differ only in auto-generated vs explicit naming are noted but treated as non-breaking.

---

## 1. Executive Summary

| Verdict | Count | Tables |
|---|---|---|
| **CRITICAL** — shape drifted so ORM reads/writes fail at runtime | 4 | `sms_maturity`, `risk_register`, `invites`, `feedback` |
| **MEDIUM** — type or column-set drift; writes may misbehave or silently drop data | 3 | `tenants`, `regulators`, `users` |
| **MINOR** — nullable/`is_demo`/constraint-name drift; no runtime error | 11 | `caps`, `corrective_actions`, `safety_deficiencies`, `flight_diversions`, `verifications`, `closures`, `psoe_questions`, `psoe_findings`, `bow_tie_threats`, `bow_tie_consequences`, `bow_tie_controls` |
| **MATCH** — no functional drift | 20 | `hazards`, `reports`, `cans`, `surveys`, `survey_responses`, `state_risk_register`, `psoe_assessments`, `regulatory_reports`, `hazard_rca_entries`, `hazard_rca_factors`, `hazard_assessments`, `hazard_capas`, `bow_tie_analyses`, `barrier_register`, `audit_logs`, `sms_dispatches`, `audit_dispatches`, `caan_reports`, `state_risk_categories`, `dead_letter_queue` |
| **Live-only tables** (no ORM model) | 6 | `icao_adrep_taxonomies`, `hfacs_nanocodes`, `hazard_adrep_mappings`, `hazard_hfacs_codes`, `report_adrep_mappings`, `report_hfacs_codes` |

**Most important finding for Module B:** `risk_register` — the table the SRAM flow writes to — has CRITICAL drift. The ORM model `RiskRegisterEntry` (db_models.py:1321) is the **SRAM shape** (bowtie_id, probability_current/severity_current/risk_index_current/tolerability_current, resultant_*, accepted, alarp_justification, etc.), but the **live table is the legacy SRM shape** (srm_date, ultimate_consequence, existing_*/resultant_* index fields, concerned_department, date_completed). The active SRAM service (`sram_service.calculate_risk`, sram_service.py:339-348; `get_risk_register`, sram_service.py:452-459) constructs/selects SRAM columns that do not exist in live → `UndefinedColumn` at runtime.

Second: `sms_maturity` (Module A's own table) is CRITICAL and was **confirmed by live write/read probe** on 2026-09-16 (see MODULE_A_CONTRACT.md §3): ORM shape INSERT and SELECT both fail with `UndefinedColumn: column "days" does not exist`. Table is empty (0 rows).

Third pair: the utility tables `invites` and `feedback` are completely out of step — the ORM models carry the stale Firestore-era shape while the live tables were rebuilt with a richer schema. Active ("best-effort") code paths touch both and fail/log errors (see §6).

---

## 2. Method & Sources

- ORM source of truth: `backend/app/db/db_models.py` (all 38 models).
- Live source of truth: live Supabase project (`postgres.bftnwljnpnpniksmalnk` pooler).
- Comparison probes: (1) full-drift introspection run capturing columns/constraints/indexes/RLS/counts for all 38 tables; (2) dedicated shape probe for the 6 live-only tables; (3) prior write/read field probe for `sms_maturity` (already documented in MODULE_A_CONTRACT.md).
- Code-path references for drifted tables verified in: `backend/app/services/sram_service.py`, `backend/app/services/invites.py`, `backend/app/routes/feedback.py`, `backend/app/routes/admin.py`, `backend/app/services/dashboard_service.py`, `backend/app/services/admin_data_service.py`, `backend/app/services/report_generator.py`.
- Row counts are live as of 2026-09-16.

Legend: ORM≠Live uses `A → B` meaning "ORM declares A, live has B".

---

## 3. Verdict Summary — all 38 ORM tables

| # | Table | Rows | RLS | ORM model (db_models.py) | Verdict | Key drift |
|---|---|---|---|---|---|---|
| 1 | hazards | 21 | ON | Hazard (64) | MATCH | +1 live index only (`ix_hazards_tenant_function`) |
| 2 | reports | 99 | ON | Report (157) | MATCH | constraint names only |
| 3 | cans | 16 | ON | Can (283) | MATCH | +1 live index (`idx_cans_psoe_assessment_id`) |
| 4 | caps | 12 | ON | Cap (378) | MINOR | `resources_required`, `implementation_plan` nullable in live vs NOT NULL in ORM |
| 5 | surveys | 204 | ON | Survey (505) | MATCH | — |
| 6 | survey_responses | 204 | ON | SurveyResponse (553) | MATCH | — |
| 7 | corrective_actions | 0 | ON | CorrectiveAction (588) | MINOR | live-only `is_demo` (bool, default true) |
| 8 | safety_deficiencies | 0 | ON | SafetyDeficiency (658) | MINOR | live-only `is_demo` |
| 9 | flight_diversions | 0 | ON | FlightDiversion (713) | MINOR | live-only `is_demo` |
| 10 | verifications | 0 | ON | Verification (772) | MINOR | live-only `is_demo` |
| 11 | closures | 0 | ON | Closure (815) | MINOR | live-only `is_demo` |
| 12 | state_risk_register | 0 | ON | StateRiskRegisterEntry (856) | MATCH | — |
| 13 | psoe_assessments | 0 | ON | PsoeAssessment (908) | MATCH | — |
| 14 | psoe_questions | 21 | ON | PsoeQuestion (960) | MINOR | live-only `is_demo`; unique constraint named `unique_component_question` vs ORM `uq_psoe_questions_component_number` |
| 15 | psoe_findings | 0 | ON | PsoeFinding (993) | MINOR | live-only `is_demo` |
| 16 | regulatory_reports | 1 | ON | RegulatoryReport (1031) | MATCH | +1 live CHECK (`quarter BETWEEN 1 AND 4`) not in ORM |
| 17 | hazard_rca_entries | 0 | ON | HazardRcaEntry (1082) | MATCH | — |
| 18 | hazard_rca_factors | 0 | ON | HazardRcaFactor (1121) | MATCH | — |
| 19 | hazard_assessments | 0 | ON | HazardAssessment (1144) | MATCH | — |
| 20 | hazard_capas | 0 | ON | HazardCapa (1167) | MATCH | — |
| 21 | bow_tie_analyses | 0 | ON | BowTieAnalysis (1225) | MATCH | +1 live index (`ix_bow_tie_analyses_tenant_status`) |
| 22 | bow_tie_threats | 0 | ON | BowTieThreat (1251) | MINOR | live-only `is_demo` |
| 23 | bow_tie_consequences | 0 | ON | BowTieConsequence (1272) | MINOR | live-only `is_demo` |
| 24 | bow_tie_controls | 0 | ON | BowTieControl (1294) | MINOR | live-only `is_demo` |
| 25 | **risk_register** | 0 | ON | RiskRegisterEntry (1321) | **CRITICAL** | ORM=SRAM shape vs live=legacy SRM shape |
| 26 | barrier_register | 0 | ON | BarrierRegisterEntry (1363) | MATCH | — |
| 27 | tenants | 1 | ON | Tenant (1420) | MEDIUM | `safety_manager` JSONB (ORM) vs varchar (live); live UNIQUE(tenant_id) |
| 28 | regulators | 1 | ON | Regulator (1464) | MEDIUM | 8 live-only columns |
| 29 | users | 5 | ON | UserProfile (1490) | MEDIUM | live-only UNIQUE(phone) + `email_change_confirm_status` CHECK |
| 30 | audit_logs | 204 | ON | AuditLog (1518) | MATCH | — |
| 31 | sms_dispatches | 0 | OFF | SmsDispatch (1543) | MATCH | — |
| 32 | audit_dispatches | 2 | OFF | AuditDispatch (1560) | MATCH | — |
| 33 | **invites** | 0 | ON | Invite (1581) | **CRITICAL** | ORM has `data`, `code`=PK; live has `id` uuid PK, no `data`, +`department`,`created_by` |
| 34 | **feedback** | 0 | ON | Feedback (1598) | **CRITICAL** | ORM `email/category/data` vs live `user_email/rating/subject/message/page/status` |
| 35 | caan_reports | 2 | OFF | CaanReport (1616) | MATCH | — |
| 36 | **sms_maturity** | 0 | OFF | SmsMaturity (1633) | **CRITICAL** | ORM `tenant_id:Text/days/data` vs live `tenant_id:uuid FK/assessment_date/overall_score/level/...` |
| 37 | state_risk_categories | 0 | OFF | StateRiskCategory (1650) | MATCH | — |
| 38 | dead_letter_queue | 0 | OFF | DeadLetterEntry (1661) | MATCH | — |

RLS note: the six RLS-OFF tables are the "sink" tables — `sms_dispatches`, `audit_dispatches`, `caan_reports`, `sms_maturity`, `state_risk_categories`, `dead_letter_queue` (already captured in DB_VERIFICATION.md).

---

## 4. CRITICAL drift detail (4 tables)

### 4.1 risk_register (0 rows, RLS on) — affects Module B directly

ORM `RiskRegisterEntry` (db_models.py:1321-1360) declares the SRAM bow-tie risk-register shape. The live table is the **legacy SRM shape** already flagged in DB_VERIFICATION.md §"risk_register".

Columns ONLY in ORM (missing in live → every ORM SELECT/INSERT references these):

| ORM column | db_models.py line |
|---|---|
| bowtie_id (FK bow_tie_analyses SET NULL, nullable) | 1326 |
| hazard_title | 1330 |
| probability_current (NOT NULL) | 1331 |
| severity_current (NOT NULL) | 1332 |
| risk_index_current (NOT NULL) | 1333 |
| tolerability_current (NOT NULL) | 1334 |
| probability_resultant | 1335 |
| severity_resultant | 1336 |
| risk_index_resultant | 1337 |
| tolerability_resultant | 1338 |
| accepted (NOT NULL, default false) | 1340 |
| alarp_justification | 1341 |
| accepted_by | 1342 |
| accepted_on | 1343 |
| review_date | 1344 |

Columns ONLY in live (missing in ORM): `srm_date` (NOT NULL), `ultimate_consequence` (NOT NULL), `existing_severity`, `existing_probability`, `existing_risk_index`, `existing_risk_tolerability`, `resultant_severity`, `resultant_probability`, `resultant_risk_index`, `resultant_risk_tolerability`, `follow_up_date`, `date_completed`, `remarks`, `concerned_department`, `created_by`, `updated_by`.

Shared columns only: `id`, `tenant_id`, `hazard_id`, `status`, `is_demo`, `created_at`, `updated_at`. Note live `hazard_id` is `uuid` with a real FK to `hazards(id)` (`risk_register_hazard_id_fkey`); the ORM treats it as plain `Text`. Live also enforces `current_risk_index`-style CHECKs via `existing_*/resultant_*` (1-5) unlike the ORM's `risk_index_current` etc.

**Runtime consequence (verified code paths):**
- `sram_service.calculate_risk` (sram_service.py:339-348) builds `RiskRegisterEntry(...)` with `bowtie_id`, `hazard_title`, `probability_current`, ... → INSERT fails `UndefinedColumn`.
- `sram_service.get_risk_register` (sram_service.py:452-459) SELECTs the ORM columns → fails at runtime.
- `sram_service._get_risk_entry_by_hazard` (sram_service.py:570-578) → fails.
- `sram_service.accept_risk` (sram_service.py:365+) → fails.
- `report_generator.py` (imports at:8) and `admin_data_service.py:1387` touch `RiskRegisterEntry` only with shared columns (`is_demo`, `tenant_id`) so those specific queries may survive; but any ORM column projection does not.

**Impact on Module B:** the SRAM (bow-tie + risk register) workstream breaks at the DB layer today. Module B contract writing is BLOCKED on a decision between (a) migrate `risk_register` in live to the SRAM shape (align live → ORM) or (b) rebuild the ORM model and services to the legacy SRM shape. Either option requires a migration/MSP decision from the human owner (see §9).

### 4.2 sms_maturity (0 rows, RLS off) — Module A table, already confirmed

ORM `SmsMaturity` (db_models.py:1633-1647): `id`, `tenant_id` TEXT NOT NULL, `days` INTEGER nullable, `data` JSONB, `created_at`; UNIQUE(`tenant_id`,`days`); index `ix_sms_maturity_tenant`.

Live: `id`, `tenant_id` UUID NOT NULL FK→`tenants(id)`, `assessment_date` timestamptz DEFAULT now(), `overall_score` double precision, `level` integer CHECK 1-5, `pillar_scores` jsonb, `element_scores` jsonb, `gap_analysis` jsonb, `recommendations` jsonb, `created_at`, `updated_at`. RLS OFF.

**Confirmed by live probe (2026-09-16):** INSERT of ORM-shape row → `UndefinedColumn: column "days" does not exist`; SELECT of ORM-shape columns → same error; SELECT of live columns succeeds (0 rows). Full write-up in MODULE_A_CONTRACT.md §3. Affected code: `dashboard_service._read_sms_maturity` / `_write_sms_maturity` (dashboard_service.py:950-972). Already surfaced; kept here for completeness.

### 4.3 invites (0 rows, RLS on)

ORM `Invite` (db_models.py:1581-1595): `code` TEXT **primary key**, `tenant_id` TEXT nullable, `email` TEXT nullable, `role` TEXT nullable, `status` TEXT nullable, `data` JSONB (DEFAULT `{}`), `created_at`, `expires_at` nullable. Index `ix_invites_tenant`.

Live: `id` **uuid PK** (gen_random_uuid), `email` TEXT **NOT NULL**, `tenant_id` **uuid FK→tenants(id)**, `role` TEXT **NOT NULL**, `department` TEXT, `code` TEXT NOT NULL with **UNIQUE index** `invites_code_key`, `status` TEXT DEFAULT 'pending', `created_by` TEXT, `expires_at` timestamptz DEFAULT now()+7 days, `created_at`.

Differences:
- ORM-primary-key `code` vs live surrogate `id` PK + `code` UNIQUE (ORM write of a new row would also produce a UUID PK mismatch — SQLAlchemy would attempt to use `code` as PK → `KeyError`-style failure or PK-not-generated error).
- ORM `data` column does NOT exist in live → `pg.insert(Invite, doc)` fails.
- `tenant_id` type Text → uuid (ORM passing a slug would hit UUID cast error).
- Live has `department`, `created_by`; email/role NOT NULL vs nullable in ORM (ORM-insert without them → NOT NULL violation on live).

**Runtime consequence:** `services/invites.py:210` (`pg.insert(Invite, doc)`), `:256` (`pg.fetch_all(Invite, where=tenants)`), `:96/:120` (`pg.fetch_by(Invite, "code", ...)`) — all affected. Route surface: `app/routes/auth.py:365-380` (`GET /invites`), `app/routes/tenants.py:195` uses `department_to_code` helper (independent of this model). The invite-creation path using the ORM is broken against live.

### 4.4 feedback (0 rows, RLS on)

ORM `Feedback` (db_models.py:1598-1613): `id`, `email` TEXT, `tenant_id` TEXT, `category` TEXT, `data` JSONB (DEFAULT `{}`), `created_at`. Indexes `ix_feedback_tenant`, `ix_feedback_created`.

Live: `id` uuid PK, `user_email` TEXT NOT NULL, `tenant_id` **uuid FK→tenants(id)**, `rating` integer CHECK 1-5, `subject`, `message`, `page`, `status` TEXT DEFAULT 'new', `created_at`.

Differences (every ORM-specified column except `id`/`created_at` is wrong for live): `email`→`user_email`, `category`/`data` do not exist in live; `tenant_id` Text→uuid.

**Runtime consequence:** `app/routes/feedback.py:73` `pg.insert(Feedback, doc)` is a defensive "mirror" write (primary path is Firestore, feedback.py:54-87) — it raises `UndefinedColumn: column "data" does not exist`, is caught and logged ("Feedback mirror write failed", feedback.py:84). `app/routes/admin.py:1490-1544` `list_feedback` queries `Feedback.data["status"]`, `Feedback.created_at` (admin.py:1510-1515) — fails against live, caught behind an error log (admin.py:1519). Both are active but silently broken paths.

---

## 5. MEDIUM drift detail (3 tables)

### 5.1 tenants (1 row, RLS on) — `safety_manager` type drift

ORM `Tenant` (db_models.py:1420-1461):
- `safety_manager`: **JSONB** (db_models.py:1439) vs live **character varying** (drift probe line ~989). A JSONB-typed write into a varchar column will persist a JSON *string*; JSONB reads of a varchar column return the raw string (no parse guarantee). Behavioural mismatch, needs a human decision on intended type. `UNKNOWN — NEEDS HUMAN INPUT`.
- `slug`: ORM Text (unique) vs live varchar — compatible.
- `oversight_level`: ORM Text vs live varchar — compatible.
- Live has additional UNIQUE constraint on `tenant_id` (`tenants_tenant_id_key`) not declared in ORM (ORM uses `tenant_id` only as a nullable Text mirror column).
- Live default status `'demo'`, modules/module_access defaults differ in shape from any ORM default (ORM has none for these). Live also carries `active`/`is_beta_sandbox`, `contact_*` — all present in ORM.

### 5.2 regulators (1 row, RLS on) — 8 live-only columns

ORM `Regulator` (db_models.py:1464-1487) is missing these live columns: `short_name`, `country_code`, `country_name`, `domain`, `status` (default 'active'), `contact_email`, `contact_phone`, `website`. All nullable — so ORM reads/writes still succeed, but any ORM write silently drops these fields, and the live regulators table was evidently created/evolved by a newer DDL than the ORM (5 extra indexes: `idx_regulators_display_name`, `_regulator_type`, `_saas_customer`, `_slug`, `_subscription_status`).

### 5.3 users (5 rows, RLS on) — Supabase-auth artifacts not modelled

ORM `UserProfile` (db_models.py:1490-1515) matches all 13 live columns. Live additionally has: `users_phone_key` UNIQUE(phone) (ORM phone is non-unique → ORM would allow duplicate phone writes that live rejects), and a CHECK `email_change_confirm_status BETWEEN 0 AND 2` referencing a column not present in either ORM or the column list printed — `UNKNOWN — NEEDS HUMAN INPUT` (introspection also returned `users_pkey` twice; likely a duplicated constraint row from the table's provenance, worth confirming). These are Supabase-auth-flavoured artefacts; Module C may need to account for them.

---

## 6. Consistently repeating minor drift patterns

1. **Live-only `is_demo` on the old Firestore-migrated tables** — `corrective_actions`, `safety_deficiencies`, `flight_diversions`, `verifications`, `closures`, `psoe_questions`, `psoe_findings`, `bow_tie_threats`, `bow_tie_consequences`, `bow_tie_controls` (all `boolean`, nullable, default `true`). ORM models for these tables lack `is_demo` entirely. Because the column is nullable with a default, ORM inserts still succeed; the ORM just cannot query/preserve the flag.
2. **Constraint naming**: live mostly uses auto-generated names (`hazards_severity_check`, `reports_report_type_check`, `caps_rca_method_check`, ...) where the ORM declares explicit names (`ck_hazards_severity`, `ck_reports_type`, `ck_caps_rca_method`, ...). Expressions are identical; only `ck_hazards_taxonomy`/`ck_bow_tie_*`/`ck_barrier_*` were created with explicit names in live. Non-breaking.
3. **`caps` nullability**: `resources_required` and `implementation_plan` are `NOT NULL` in ORM (db_models.py:390-391) but nullable in live. ORM is stricter than DB; direct DB writes may insert NULLs the ORM would reject. Low impact.
4. **Extra indexes in live not declared in ORM** (informational): `ix_hazards_tenant_function`, `idx_cans_psoe_assessment_id`, `ix_bow_tie_analyses_tenant_status`, `idx_tenants_regulator` (+`_id`), the 5 regulator indexes, `idx_invites_code`, `ix_invites_tenant` vs ORM `ix_invites_tenant`.
5. **`regulatory_reports`** has an extra live CHECK `quarter BETWEEN 1 AND 4` the ORM does not declare (ORM relies on the app layer). Guardrail is live-side; non-breaking.

---

## 7. Live-only tables (no ORM model, no schema.sql/schema_init.py entry)

All RLS ON. These are v2 ADREP/HFACS reference + mapping tables powering `hazards.adrep_category`/`occurrence_type` and reports taxonomy.

| Table | Rows | Shape (live) | Purpose |
|---|---|---|---|
| icao_adrep_taxonomies | 15 | `id` uuid PK, `category_code` varchar UNIQUE, `domain_type` text, `occurrence_category` text, `description`, `is_active` bool default true, `created_at` | ICAO ADREP occurrence-taxonomy reference |
| hfacs_nanocodes | 106 | `id` uuid PK, `code` varchar UNIQUE, `level_1_category`, `level_2_subcategory`, `nanocode_name`, `description`, `is_active` bool, `created_at` | HFACS nanocode reference |
| hazard_adrep_mappings | 0 | `hazard_id` FK→hazards (CASCADE), `adrep_id` FK→icao_adrep_taxonomies (RESTRICT), `tenant_id`, `assigned_at`; PK(hazard_id,adrep_id) | hazard↔ADREP mapping |
| hazard_hfacs_codes | 0 | `hazard_id` FK→hazards (CASCADE), `nanocode_id` FK→hfacs_nanocodes (RESTRICT), `tenant_id`, `assigned_at`; PK(hazard_id,nanocode_id) | hazard↔HFACS mapping |
| report_adrep_mappings | 0 | `report_id` FK→reports (CASCADE), `adrep_id` FK→icao_adrep_taxonomies (RESTRICT), `tenant_id`, `assigned_at`; PK(report_id,adrep_id) | report↔ADREP mapping |
| report_hfacs_codes | 0 | `report_id` FK→reports (CASCADE), `nanocode_id` FK→hfacs_nanocodes (RESTRICT), `tenant_id`, `assigned_at`; PK(report_id,nanocode_id) | report↔HFACS mapping |

Module B impact: accessing these from ORM requires either new models or raw SQL. The mapping tables are currently empty (0 rows) despite the reference data being seeded (15 + 106). `UNKNOWN — NEEDS HUMAN INPUT` on whether the ORM was refactored away from these tables or they pre-date the current model set.

---

## 8. Impact on Module B Contract

Module B (Hazard & Risk) touches these surfaces. State at close of this review:

| Module B surface | Drift status | Blocker? |
|---|---|---|
| hazards / reports / cans / caps (SRM core) | MATCH | No |
| bow_tie_analyses / threats / consequences / controls | MATCH (child tables +live-only `is_demo`) | No |
| barrier_register | MATCH | No |
| **risk_register** | **CRITICAL** | **Yes — SRAM risk-register write/read path fails** |
| state_risk_register (SSP / Module C-adjacent) | MATCH | No |
| corrective_actions / verifications / closures / safety_deficiencies / flight_diversions | MINOR (+`is_demo`) | No |
| hazard_rca_entries / hazard_rca_factors / hazard_assessments / hazard_capas | MATCH | No |
| ADREP/HFACS taxonomy mapping (6 live-only tables) | not in ORM | Depends on scope — see §9 |

The single hard blocker for Module B's contract is `risk_register`. Everything else under Module B's lens is match or trivially driftable.

---

## 9. Open questions needing human input

1. `risk_register`: should live be migrated to the SRAM shape (ORM = source of truth) or should the ORM + sram_service + report_generator be downgraded to the legacy SRM shape? This blocks Module B's contract.
2. `sms_maturity`: already flagged in MODULE_A_CONTRACT.md — live carries the assessment-shaped schema (Module A intends it); ORM needs to adopt the live shape. Owner to confirm the ORM update is in scope for the corrective phase (not for these read-only docs).
3. `tenants.safety_manager`: intended type jsonb vs varchar? Live DDL and ORM disagree. `UNKNOWN — NEEDS HUMAN INPUT`.
4. `users`: what is the `email_change_confirm_status` column the live CHECK refers to (it is not in the introspection column list), and why does `users_pkey` appear twice in `pg_constraint`? `UNKNOWN — NEEDS HUMAN INPUT`.
5. `invites`/`feedback`: are the Postgres-backed paths (invite create/list; feedback mirror + admin list) still in scope, or superseded by Firestore/Supabase Auth flows? If live, the ORM models must be updated to the live shapes.
6. Do the ADREP/HFACS mapping tables need ORM models + endpoints as part of Module B (specialists attaching ICAO taxonomy to hazards/reports), or are these consumed elsewhere (raw SQL / admin tooling)? `UNKNOWN — NEEDS HUMAN INPUT`.