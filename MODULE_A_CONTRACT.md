# MODULE_A_CONTRACT.md — Survey / SMS Health Module

AviaSAFE SMS Platform — Module A Specification
Platform: sms.aviasafesystems.com | Auth: Firebase | Hosting: Firebase Hosting
No vendor changes. No migrations. This document describes the interface, not the implementation.

---

## 1. PURPOSE

Module A is the ICAO Annex 19 SMS health measurement instrument, owned by the Safety Department. It has two functions:

1. **Numeric survey scoring.** Accepts anonymous and authenticated employee survey submissions, validates answers against the master question contract (v3.0.0: 23 questions / v4.0.0: 31 questions mapping to 4 ICAO pillars and 12 elements), and computes server-side scores: overall SMS maturity %, pillar scores (1–5), per-element proportional scores (0–100), and per-question normalized scores (1–5). Persists both the scored `surveys` row (for dashboards) and the raw `survey_responses` row (for audit).

2. **Qualitative LLM analysis.** Produces gap analysis, recommendations, and narrative summary from survey answers. Provider: Groq for testing; Gemini for production (`AI_MODEL=gemini-2.0-pro-exp-02-05` per `core/config.py:116`). Intended cache target: `sms_maturity` table. **Currently broken** — see Section 8.

**Users:** employees (submit surveys, no auth required), safety managers (view airline SMS maturity), CAAN SMD (view national aggregation).

**Compliance anchor:** Directly supports **Element 3.1 — Safety Performance Monitoring and Measurement** (Annex 19 Appendix 2 Requirement 3.1: "The service provider shall develop and maintain the means to verify the safety performance of the organization and to validate the effectiveness of safety risk controls."). Sources: [Annex 19 Appendix 2](https://cil.nus.edu.sg/wp-content/uploads/2019/02/1944-Convention-on-International-Civil-Aviation-Annex-19.pdf); [ICAO SMM Doc 9859 Ch.9](https://www.icao.int/safety-management/SMI/SMM/Chapter%209). The survey instrument's output (maturity scores, pillar scores, element scores) constitutes a safety performance indicator per §3.1.2: "The service provider's safety performance shall be verified in reference to the safety performance indicators and safety performance targets of the SMS in support of the organization's safety objectives."

---

## 2. DATA OWNERSHIP

### 2.1 Tables

| Table | Live columns (DB query 2026-09-16) | Purpose | RLS |
|---|---|---|---|
| `surveys` | id uuid, tenant_id uuid, submitted_at timestamptz, respondent_id, department, employee_category, years_experience, language_used, survey_version, seed_version, answers jsonb, question_scores jsonb, element_scores jsonb, safety_policy int, safety_risk_management int, safety_assurance int, safety_promotion int, overall_sms_maturity int, overall_score_pct numeric, is_demo bool | Scored survey — consumed by dashboards. **ORM matches live.** | ✅ enabled |
| `survey_responses` | id uuid, tenant_id uuid, respondent_id, answers jsonb, department, employee_category, years_experience, language_used, submitted_at timestamptz, survey_version, is_demo bool | Raw audit copy of answers. **ORM matches live.** | ✅ enabled |
| `sms_maturity` | ⚠️ **CRITICAL DRIFT — see §2.2** | AI recommendation cache. **ORM does not match live. LLM output NOT persisted.** | ❌ **DISABLED** |
| `tenants.data` (JSONB sub-object `surveyConfig`) | Shared resource; Module A reads survey open/close window here (`routes/surveys.py:189-198`). Platform-owned. | Survey configuration (active flag, open/close dates, rate limit). | Platform table |

### 2.2 CRITICAL — sms_maturity schema drift (ORM vs Live)

| Attribute | ORM (`SmsMaturity`, `db/db_models.py:1633-1647`) | Live (DB query) |
|---|---|---|
| `tenant_id` | `TEXT`, no FK | `uuid`, **FK → tenants(id)** |
| `days` | `INTEGER` (unique with tenant_id) | **DOES NOT EXIST** |
| `data` | `JSONB` (single bag) | **DOES NOT EXIST** |
| `assessment_date` | — | `timestamptz` |
| `overall_score` | — | `double precision` |
| `level` | — | `integer` (CHECK 1-5) |
| `pillar_scores` | — | `jsonb` |
| `element_scores` | — | `jsonb` |
| `gap_analysis` | — | `jsonb` |
| `recommendations` | — | `jsonb` |
| `created_at` | `timestamptz` | `timestamptz` |
| `updated_at` | — | `timestamptz` |
| Unique constraint | `ux_sms_maturity_tenant_days` on `(tenant_id, days)` | **None** |
| Bootstrap DDL | `db/schema_init.py:283-292` creates old shape | Overwritten; DDL is stale |

Probe confirmed: ORM shape INSERT/SELECT both fail with `psycopg2.errors.UndefinedColumn: column "days" does not exist`. Table has **0 rows**.

---

## 3. PUBLIC API SURFACE

### 3.1 Module A's own endpoints

| Method | Path | Purpose | Mount |
|---|---|---|---|
| `POST` | `/api/v1/surveys/` | Submit ICAO-aligned SMS survey. Validates answers, computes 4-pillar + 12-element scores, persists `surveys` + `survey_responses` rows. | `main.py:250` |
| `POST` | `/api/surveys/` | Same endpoint, legacy alias. | `main.py:251` (hidden from OpenAPI) |

No other `/surveys/*` or `/sms-maturity/*` routes exist. The `sms_maturity` table is written by service-layer code, not an HTTP endpoint.

### 3.2 Consumed By (cross-reference only — NOT Module A endpoints)

| Consumer layer | Endpoint / function | How it consumes Module A |
|---|---|---|
| Dashboard | `GET /api/v1/dashboard/airline/sms-maturity` (`routes/dashboard.py:252`) | Reads `surveys` via `dashboard_service._survey_docs()` for tenant SMS maturity view |
| Dashboard | `GET /api/v1/dashboard/caan/survey-maturity` (`routes/dashboard.py:327`) | Reads `surveys` across tenants for CAAN national view |
| Dashboard | `GET /api/v1/dashboard/caan/sms-maturity-assessment` (`routes/dashboard.py:349`) | Reads `surveys` + writes AI recs to `sms_maturity` cache |
| Dashboard | `GET /api/v1/dashboard/trends` (`routes/dashboard.py:124`) | Reads `surveys` for trend time series |
| Dashboard | `dashboard_service._write_sms_maturity()` (`services/dashboard_service.py:966`) | Writes to Module A's `sms_maturity` table (boundary violation — §7) |
| Module C | `aggregation_service.collect_maturity_scores()` (`services/aggregation_service.py:98`) | Reads `surveys.overall_sms_maturity` for national aggregation |
| Module C | `GET /api/v1/regulator/industry-averages` (`routes/regulator_dashboard.py:26`) | Consumes aggregation output derived from Module A surveys |
| Platform | `GET /api/v1/tenants/{id}/config` (`routes/tenants.py:99`) | Module A reads survey config from `tenants.data` JSONB |
| Platform | `PUT /api/v1/tenants/{id}/config` (`routes/tenants.py:204`) | Admin updates survey config |

---

## 4. AGGREGATABLE OUTPUTS (for Module C)

### 4.1 Numeric values (from `surveys` table)

| Value name | Type | Computable now? | Source |
|---|---|---|---|
| SMS health score per tenant | float 1-5 (`overall_sms_maturity`) | ✅ YES | `surveys.overall_sms_maturity` — latest per tenant; `dashboard_service._aggregate_surveys()` |
| Per-pillar maturity score | float 1-5 | ✅ YES | `surveys.safety_policy`, `safety_risk_management`, `safety_assurance`, `safety_promotion` |
| Per-element score | float 0-100 | ✅ YES | `surveys.element_scores` (JSONB) — proportional score per ICAO element |
| Per-question average | float 1-5 | ✅ YES | `surveys.question_scores` (JSONB) — `dashboard_service._question_averages()` |
| Survey participation rate per tenant | int | ✅ YES | COUNT of `survey_responses` per tenant |
| Overall SMS maturity % | float 0-100 | ✅ YES | `surveys.overall_score_pct` |

### 4.2 LLM-derived values (intended from `sms_maturity` — currently BROKEN)

| Value name | Type | Computable now? | Source |
|---|---|---|---|
| Benchmark band per tenant | enum: Red/Yellow/Green | ❌ BROKEN | Intended: `sms_maturity.level` + `sms_maturity.overall_score` |
| National band distribution | counts per band | ❌ BROKEN | Intended: aggregated from per-tenant bands |
| Gap analysis | JSONB | ❌ BROKEN | Intended: `sms_maturity.gap_analysis` |
| Recommendations | JSONB | ❌ BROKEN | Intended: `sms_maturity.recommendations` |
| Element gap frequency | dict of element → count | ❌ BROKEN | Intended: derived from `gap_analysis` |

### 4.3 Benchmark thresholds (platform defaults)

| Band | Threshold | Label | Action |
|---|---|---|---|
| Red | < 70% | Recommended Action | Requires action |
| Yellow | 71–79% | On Watch | Monitor closely |
| Green | ≥ 80% | Monitor | Continue monitoring |

Applied to `overall_score_pct` (0–100 scale). Whether tenant-configurable is OPEN — see §9 Q1.

### 4.4 BOUNDARY RULE

Module C must NEVER see individual tenant-identifiable `survey_responses` rows. Module C may only consume aggregates derived from `surveys` (scored, anonymized by aggregation) or from `aggregation_service` pre-aggregated endpoints.

---

## 5. COMPLIANCE ANCHORS

### 5.1 Directly supported (verifiable citation)

**Annex 19 Appendix 2 Requirement 3.1 — Safety Performance Monitoring and Measurement.** Module A's sole operational purpose is SMS performance measurement. The survey produces overall SMS maturity scores, per-pillar scores, and per-element scores as safety performance indicators.

- §3.1.1: "The service provider shall develop and maintain the means to verify the safety performance of the organization and to validate the effectiveness of safety risk controls."
- §3.1.2: "The service provider's safety performance shall be verified in reference to the safety performance indicators and safety performance targets of the SMS in support of the organization's safety objectives."

Sources: [Annex 19 Appendix 2](https://cil.nus.edu.sg/wp-content/uploads/2019/02/1944-Convention-on-International-Civil-Aviation-Annex-19.pdf); [ICAO SMM Doc 9859 Ch.9](https://www.icao.int/safety-management/SMI/SMM/Chapter%209).

### 5.2 Measured but NOT directly supported

The survey questions span all 12 Annex 19 elements, but measuring an element is not the same as implementing it:

- **Elements 1.1–1.5 (Safety Policy & Objectives):** questions `q1_aware`..`q5_spi` measure awareness — but implementing policy is the organization's responsibility, not Module A's.
- **Elements 2.1–2.2 (Safety Risk Management):** questions `q6`..`q13` measure risk management culture — implementation belongs to Module B.
- **Element 3.2 (Management of Change):** questions `q30_moc_process`, `q31_moc_risk` — implementation belongs to Module B's hazard workflow.
- **Element 3.3 (Continuous Improvement):** questions `q19_invest_outcome`, `q20_corrective` — implementation belongs to Module B's CAN/CAP lifecycle.
- **Elements 4.1–4.2 (Safety Promotion):** questions `q17`, `q18`, `q21`..`q23_peer` — implementation belongs to the organization's training program.

---

## 6. BOUNDARIES

Module A MUST NOT:

1. Import from Module B (`hazard_service`, `can_cap_service`, `verification_service`, `sram_service`, `risk_calculator`, `state_machine`, `flight_diversion_service`) or Module C (`psoe_service`, `state_risk_service`, `spi_service`, `nhrc_service`, `aggregation_service`, `regulator_service`).
2. Write to any table owned by Module B (hazards, reports, cans, caps, verifications, closures, corrective_actions, safety_deficiencies, flight_diversions, bow_tie_*, barrier_register, hazard_rca_*, hazard_assessments, hazard_capas, risk_register) or Module C (state_risk_register, psoe_assessments/questions/findings, regulatory_reports, caan_reports, audit_dispatches, sms_dispatches, dead_letter_queue).
3. Expose raw `survey_responses` to Module C.
4. Own hazard, risk, CAN, CAP, or PSOE data.

---

## 7. IDENTIFIED GAPS

1. **CRITICAL — sms_maturity schema drift.** ORM (`db/db_models.py:1633`) defines `tenant_id TEXT`, `days INT`, `data JSONB`; live table has `tenant_id UUID FK`, `assessment_date`, `overall_score`, `level`, `pillar_scores`, `element_scores`, `gap_analysis`, `recommendations`, `updated_at`. Probe confirmed: writes/reads fail with `UndefinedColumn: column "days" does not exist`. See §8.
2. **sms_maturity RLS disabled.** Live `rowsecurity = false` on `sms_maturity`. All other Module A tables (`surveys`, `survey_responses`) have RLS enabled. Any authenticated user can query any tenant's SMS maturity assessment rows.
3. **No HTTP endpoint for sms_maturity.** The table is written by `dashboard_service._write_sms_maturity()` (`services/dashboard_service.py:966-972`) but has no direct HTTP endpoint. No way to read or write the cache except through the dashboard service layer.
4. **LLM output not persisted.** The `sms_maturity` columns `gap_analysis`, `recommendations`, and `level` (intended for LLM output) are never populated because the write path is broken. LLM analysis is regenerated on every dashboard load.
5. **No async pipeline for LLM analysis.** The `recommend_sms_maturity_actions()` function (`services/gemini.py:405`) calls Gemini synchronously inline during dashboard request handling. No background job, no queue, no async processing.
6. **survey_scoring v3/v4 dual engine.** The scoring engine supports v3.0.0 (23 questions, no element scores) and v4.0.0 (31 questions, 12 elements, weighted composite). v3 submissions produce empty `element_scores` (`routes/surveys.py:279`). No migration path documented; version auto-detected from answered questions.
7. **Benchmark thresholds not configurable.** The Red/Yellow/Green thresholds (<70/71–79/≥80) are hardcoded. Whether they should be tenant-configurable per survey config is OPEN — see §9 Q1.
8. **No test coverage for sms_maturity cache lifecycle.** `tests/test_state_risk.py` tests `get_caan_survey_maturity()` and `get_airline_sms_maturity()` with mock data that bypasses the ORM entirely. No test verifies actual `_read_sms_maturity` / `_write_sms_maturity` against Postgres.

### 7.1 Boundary Violation to Resolve

The dashboard layer writes to Module A's `sms_maturity` table directly via `dashboard_service._write_sms_maturity()` (`services/dashboard_service.py:966-972`). This violates the rule that only the owning module writes to its own tables.

Resolution options (do NOT choose one here):
  - (a) Module A exposes `POST /api/v1/sms-maturity/{tenant_id}/cache` for the dashboard to call.
  - (b) The AI recommendation cache moves to dashboard-owned storage.
  - (c) The cache is eliminated — recompute always.

Flagged for the Module A implementation phase.

---

## 8. PRODUCTION DEFECTS REQUIRING IMMEDIATE ATTENTION

### DEFECT 1 — sms_maturity cache is broken in production (silent failure)

| Attribute | Detail |
|---|---|
| **ORM definition** | `SmsMaturity` at `db/db_models.py:1633-1647` — columns: `id uuid`, `tenant_id TEXT`, `days INT`, `data JSONB`, `created_at timestamptz`. Unique on `(tenant_id, days)`. |
| **Live DB shape** | `sms_maturity` — columns: `id uuid`, `tenant_id uuid FK→tenants(id)`, `assessment_date timestamptz`, `overall_score double`, `level int (1-5)`, `pillar_scores jsonb`, `element_scores jsonb`, `gap_analysis jsonb`, `recommendations jsonb`, `created_at timestamptz`, `updated_at timestamptz`. No `days`, `data`, or TEXT `tenant_id`. |
| **Bootstrap DDL** | `db/schema_init.py:283-292` creates old shape (`tenant_id TEXT`, `days INT`, `data JSONB`). This DDL was applied at boot but live table has been overwritten; DDL is stale. |
| **Silent-failure call sites** | `services/dashboard_service.py:950-963` (`_read_sms_maturity`): queries `SmsMaturity.tenant_id == tenant_id AND SmsMaturity.days == days` — columns don't exist → `UndefinedColumn` → caught by `except Exception`, returns `None`. |
| | `services/dashboard_service.py:966-972` (`_write_sms_maturity`): inserts `{"id": ..., "tenant_id": ..., "days": ..., "data": ...}` via `pg.upsert()` — columns don't exist → `UndefinedColumn` → caught by `except Exception`, silently logged. |
| **Probe result (2026-09-16)** | 1) ORM shape INSERT: `UndefinedColumn: column "days" of relation "sms_maturity" does not exist`. 2) ORM shape SELECT: `UndefinedColumn: column "days" does not exist`. 3) Live shape SELECT: SUCCEEDED — 0 rows. 4) Live shape INSERT: `ForeignKeyViolation` (expected — probe UUID not in tenants). Table has **0 rows**. |
| **Consequence** | SMS maturity assessment cache never populates. Every dashboard request that calls `_get_assessment_actions()` (`services/dashboard_service.py:243`) re-generates AI recommendations from scratch, bypassing the 6-hour TTL cache (`SMS_MATURITY_CACHE_TTL = 6 * 3600`, `services/dashboard_service.py:36`). Wastes Gemini/Groq API calls. Adds latency to every dashboard load. LLM gap analysis and recommendations are never persisted. |

### DECISION REQUIRED (not resolved by this contract)

Which shape is canonical for `sms_maturity`?

  - **(a) ORM shape:** `tenant_id TEXT` + `days INT` + `data JSONB`
  - **(b) Live shape:** `tenant_id UUID FK` + `assessment_date` + `overall_score` + `level` + `pillar_scores` + `element_scores` + `gap_analysis` + `recommendations` + `updated_at`

Considerations:
  - (a) preserves existing ORM code and `_read_sms_maturity`/`_write_sms_maturity` logic; requires rewriting the live table (no data to lose — table is empty).
  - (b) matches the dashboard read model and the live DDL; requires rewriting the ORM model, `_read_sms_maturity`, `_write_sms_maturity`, `schema_init.py` DDL, and any query filtering by `days`.

This decision must be made by the platform owner before Module A implementation. Module A's contract specifies the interface required (tenant-scoped maturity lookup with TTL), not the storage shape.

---

## 9. OPEN QUESTIONS

**Q1 — Benchmark thresholds configurability.**
Band edges are confirmed as <70 Red, 71–79 Yellow, ≥80 Green (applied to `overall_score_pct`). Should these be configurable per tenant via `tenants.data.surveyConfig`, or fixed as platform defaults? If configurable, the threshold values must be read during survey submission and stored with the scored result.

**Q2 — Production LLM provider.**
The `AI_MODEL` config defaults to `gemini-2.0-pro-exp-02-05` (`core/config.py:116`), suggesting Gemini is the production provider. However, `services/groq_copilot.py` exists for Groq. Is the production LLM for survey analysis Gemini or Groq? This affects API key requirements, rate limits, and output format.

**Q3 — LLM analysis trigger timing.**
Target behavior appears to be: LLM analysis runs on survey submit, result cached in `sms_maturity` with TTL (`SMS_MATURITY_CACHE_TTL = 6` hours, `services/dashboard_service.py:36`), invalidated on new survey submission. Confirm this is the intended architecture. Currently, because the cache is broken, LLM analysis runs inline on every dashboard request — this is NOT the target behavior.

---

*End of MODULE_A_CONTRACT.md. This document describes the interface and flags gaps; implementation is a separate phase.*
