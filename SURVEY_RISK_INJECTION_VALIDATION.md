# Survey Risk Injection Validation Report

**Date**: 2026-09-16 | **Status**: READ-ONLY ANALYSIS COMPLETE — CAAN MANUAL REVIEWED

**Question**: Are SMS survey pillar scores below 70% automatically injected as risks into the risk register or hazard tables?

---

## 1. Executive Summary

**Answer: NO — no automatic injection of SMS survey pillar scores <70% into risk_register, hazards, corrective_actions, or safety_deficiencies exists anywhere in the codebase.**

When a survey scores below 70% on any pillar, the system computes pillar scores in memory (`survey_scoring.py`), persists results to `surveys` + `survey_responses` only (`routes/surveys.py:94-146`), then on dashboard access classifies "low" pillars and generates LLM text recommendations (`gemini.py:405-479`) cached in `sms_maturity` (`dashboard_service.py:233-279`) — an assessment cache, NOT a risk table. There is no code path that writes survey scores, pillar deficiencies, or recommendations into `risk_register`, `hazards`, `corrective_actions`, or `safety_deficiencies`. The <70% threshold triggers only in-memory classification and LLM prompt construction — the output is narrative text, not structured risk data.

The CAAN SRM Procedure Manual (First Edition, January 2026, Aviation Safety and Security Regulation Directorate, CAAN) is now available at `D:\Projects\aviasafesms\data`. Reading its §2.1 in context with the other six sources of hazard information confirms that "Hazard Survey Reports" refers to a hazard-identification survey, not the SMS health survey. The current code is compliant: survey scores are indicators, not hazards. The live database contains only demo data (all `is_demo = true`); no production data exists. Findings are code-level, not data-level.

---

## 2. Code Investigation (Q1-Q6)

### Q1: Survey submission → scoring pipeline

| File | Line(s) | Function | Behavior |
|---|---|---|---|
| `backend/app/routes/surveys.py` | 149 | `submit_survey` | Entry point for survey POST |
| `backend/app/routes/surveys.py` | 267-280 | scoring block | Calls `compute_survey_result(answers, version)` → returns pillar_scores dict |
| `backend/app/routes/surveys.py` | 94-146 | `_persist_tenant_survey` | Writes ONLY to `surveys` (scored) + `survey_responses` (raw) — no threshold branching, no risk table writes |
| `backend/app/services/survey_scoring.py` | 30+ | `compute_survey_result` | Pure computation — returns `{"pillar_scores": {...}, "overall_maturity": N, ...}` — no side effects |

**Finding**: No `70` threshold check exists in the submission pipeline. No conditional writes to any risk table.

### Q2: Dashboard SMS maturity → LLM analysis

| File | Line(s) | Function | Behavior |
|---|---|---|---|
| `backend/app/services/dashboard_service.py` | 192-231 | `_sms_maturity_model` | Computes pillar pcts; `if pct < 70` at line 209 marks pillar as "low"; stores `improvement_opportunities` in memory — NO DB write |
| `backend/app/services/dashboard_service.py` | 233-279 | `_tenant_recommendations` | If `model["low_pillars"]`: calls `recommend_sms_maturity_actions()` → writes cache via `_write_sms_maturity` → target is `sms_maturity` table (assessment cache), NOT any risk table |
| `backend/app/services/dashboard_service.py` | 776-819 | `get_caan_sms_maturity_assessment` | AI maturity assessment; calls `recommend_sms_maturity_actions` for pillars <70; caches per tenant to `sms_maturity` |
| `backend/app/services/dashboard_service.py` | 950-972 | `_read_sms_maturity` / `_write_sms_maturity` | Read/write helpers targeting the `sms_maturity` table only |

**Finding**: The `sms_maturity` table stores assessment snapshots (pillar_scores, gap_analysis, recommendations as JSONB text). It is NOT a risk register — it has no hazard_id, severity, probability, or tolerability fields.

### Q3: LLM recommendation generator

| File | Line(s) | Function | Behavior |
|---|---|---|---|
| `backend/app/services/gemini.py` | 298-303 | `SURVEY_PILLAR_NAMES` | Maps pillar keys to display names |
| `backend/app/services/gemini.py` | 305 | `SURVEY_PILLAR_ORDER` | Iteration order |
| `backend/app/services/gemini.py` | 315-322 | `sms_maturity_tier` | Tier classification: ≥85 strong, ≥70 watch, ≥50 action, <50 critical |
| `backend/app/services/gemini.py` | 405-479 | `recommend_sms_maturity_actions` | For each pillar <70: builds prompt, calls Gemini LLM, parses JSON response `{"recommendations": [{"pillar": ..., "actions": [...]}]}` — returns list of text recommendations, **no DB writes** |
| `backend/app/services/gemini.py` | 325-400 | `_mock_sms_maturity_actions` | Fallback when LLM unavailable — returns mock text recommendations |
| `backend/app/services/gemini.py` | 393-402 | `mock_sms_maturity_recommendations` | Filters `pct >= 70` to skip; returns mock actions for <70 pillars only — **text payload, no DB write** |

**Finding**: LLM output is JSON-structured text recommendations. The function returns data; the caller (`_tenant_recommendations` / `get_caan_sms_maturity_assessment`) writes the cache. Neither writes to risk tables.

### Q4: Threshold constant `70` — all occurrences in backend

Grep `70` across `backend/**/*.py` found 79 matches. Relevant to this investigation:

| File | Line(s) | Context | Relevance |
|---|---|---|---|
| `dashboard_service.py` | 209, 228, 778 | `if pct < 70` — pillar classification | YES — the threshold trigger |
| `gemini.py` | 318, 399, 411, 430 | `pct >= 70` / `< 70` — tier + prompt filter | YES — LLM only prompts for <70 |
| `spi_service.py` | 90, 584 | `alert_threshold = 70.0` / `float(70+offset)` | NO — SPI performance index alerts, unrelated |
| `report_generator.py` | 356 | SSP compliance `< 70` | NO — report text formatting, unrelated |
| `psoe_service.py` | 147 | `score_pct >= 70` | NO — PSOE pass threshold, unrelated |
| `psoe.py` | 404-424, 512, 584 | CSS `font-weight: 700` + PSOE `>= 70` | NO — formatting + PSOE scoring, unrelated |

No matches found for: `below_70`, `risk_threshold`, `auto_risk`, `inject` (only unrelated: prompt-injection tests, ROADMAP secrets doc).

**Finding**: The `70` threshold appears in exactly two related locations (dashboard_service + gemini), both producing text/cache output — never risk table writes.

### Q5: Workers and scheduled jobs

| Worker | File | What it does | Survey interaction |
|---|---|---|---|
| `ScheduledReportWorker` | `workers/scheduler.py` | Weekly CAAN SSP oversight report dispatch (state_risk based) | NONE — reads regulators, generates PDF, emails |
| `TenantReportWorker` | `workers/tenant_scheduler.py` | Monthly SRB package for active tenants | Reads hazards/reports/cans only; no surveys |
| `report_worker.py` | `workers/report_worker.py` | PDF generation + audit dispatch intent recording | No surveys |
| `escalation_worker.py` | `workers/escalation_worker.py` | CAN/CAP overdue marking (status→Overdue) | No surveys; writes only to `cans` table |

**Lifecycle** (`core/lifecycle.py`):
- `weekly_ssp_dispatch` → `scheduler.py` (no surveys)
- `monthly_tenant_dispatch` → `tenant_scheduler.py` (no surveys)
- `daily_dlq_replay` → DLQ sweep (read-only)

**Finding**: No scheduled job reads survey scores or writes survey-derived data to risk tables.

### Q6: Admin routes and data services

`admin_data_service.py` imports `survey_scoring` functions (line 30-33) solely for demo data seeding (`_seed_surveys` at line 621). The seeding generates random answers, computes scores via `compute_survey_result`, and writes to `surveys` + `survey_responses` only. No admin route converts survey scores to risk entries.

`admin.py` has no survey-to-risk conversion routes (grep for `survey|maturity|pillar` returns only config/metadata references and the demo seed management endpoints).

**Finding**: Admin layer handles survey lifecycle and demo seeding — no risk injection.

---

## 3. Data Investigation (Queries 1-5)

All data in the live database is demo-seeded via `admin_data_service.py`. No production data exists.

### Q1: Survey pillar scores <70%

`SELECT ... FILTER (WHERE ... < 70) FROM surveys WHERE is_demo = false` → **(0, 0, 0)** — zero non-demo surveys total. All 204 surveys have `is_demo = true`.

### Q2: Target table row counts

```
hazards             → all=21 demo=21 live=0
risk_register       → all=0  demo=0  live=0
safety_deficiencies → all=0  demo=0  live=0
corrective_actions  → all=0  demo=0  live=0
```

All four target tables are empty for non-demo data. The live database contains no production data to correlate.

### Q3: Cross-references (survey terminology in risk tables)

`ILIKE '%survey% OR %maturity% OR %pillar%'` on hazards source/description → 0 rows. safety_deficiencies source/description → 0 rows. corrective_actions description → 0 rows. `risk_register` has no source column (legacy SRM shape: tenant_id, hazard_id, status, remarks only).

### Q4: Time-window correlation

`hazards JOIN low-scored surveys` on same tenant within 14 days → no correlatable data exists. All target tables are empty.

### Q5: `sms_maturity` cache table

Columns: id, tenant_id, assessment_date, overall_score, level, pillar_scores/jsonb, element_scores/jsonb, gap_analysis/jsonb, recommendations/jsonb. **0 rows** for any tenant — `sms_maturity` is CRITICALLY drifted per SCHEMA_DRIFT_REPORT.md; `_write_sms_maturity` would fail against the live schema. The only table that receives survey-derived data is non-functional.

---

## 4. CAAN Manual Expectation

### Status: RESOLVED — CAAN SRM Procedure Manual REVIEWED

The **CAAN SRM Procedure Manual (First Edition, January 2026)** at `D:\Projects\aviasafesms\data\safety-risk-management-srm-procedure-manual.pdf` was reviewed. Readings are cited by section number only.

**Q7. Does the CAAN manual require survey scores below a threshold to become a hazard?**

No. §2.1 lists seven sources of hazard information. Six of them are unambiguously hazard-identification activities (VSR, MOR/occurrence, internal audit, external audit, operational data review, operational trial). The seventh, "Hazard Survey Reports," sits in the same list and reads in the same category: a survey conducted specifically to identify hazards.

The SMS health survey is a different activity. It measures organizational safety culture (policy awareness, commitment, communication). It is referenced in §1.1 under "safety data" as a source of information for SMS improvement, not as a source of hazards.

Conclusion: the manual does not require survey scores to become hazards.

**Q8. What does "Hazard Survey Reports" mean in §2.1?**

Not defined in §1.1 (Definitions). Read in context with the other six sources, it is a hazard-identification activity. It is NOT the SMS health survey.

The ambiguity is real but minor: an interpretation note to CAAN could confirm, but the reading is not seriously in doubt.

**Q9. How should a below-threshold survey score be treated per the manual?**

The manual does not address this directly. §2.1's seven sources produce hazards; a survey score is a measurement of SMS health, not a hazard. If a survey identifies a specific unsafe condition, that condition becomes a §2.1 hazard via the normal process — the Safety Manager registers it with the appropriate source attribution.

The survey's output feeds the continuous improvement loop (management review, SMS maturity tracking), not the hazard register.

Cite §1.1 "safety data" definition: "Such safety data is collected from proactive or reactive safety-related activities, including but not limited to: ... e) inspections, audits, surveys." This places surveys in the safety data category, not the hazard category.

---

## 4A. CAAN Manual Reading — Key Sections Reviewed

For traceability, the following CAAN SRM Manual sections were reviewed in making this determination:

- **§1.1 Definitions** — "Safety data" includes "inspections, audits, surveys" as sources of safety data (not hazards). Defines "Hazard: A condition or an object with the potential to cause or contribute to an aircraft incident or accident."
- **§2.1 Hazard registration** — seven sources of hazard information. Lists "Hazard Survey Reports" alongside VSR, MOR, audits, investigations, operational data review, and operational trial reports.
- **§2.1 Essential registration elements** — thirteen enumerated elements (i–xiii) required on the hazard registration sheet; none of them reference survey scores.
- **§2.2 Initial prioritization** — H/M/L prioritization based on consequence severity (accident/serious incident/incident) or ERC. No mention of survey thresholds.
- **§2.3.6.6 Risk acceptance** — "Risk acceptance authority cannot be delegated." Confirms the AE escalation model referenced in earlier platform design decisions.

This manual is the compliance anchor for Module B's contract.

---

## 5. Gap Analysis

### CAAN expectation vs. current state

Current state (code) is compliant with the CAAN SRM Procedure Manual. There is no gap.

| CAAN expectation (§2.1/§2.2) | Actual (code) | Verdict |
|---|---|---|
| Hazard sources: VSR, MOR/occurrence, audits, hazard surveys, operational data review, operational trial reports (§2.1) | Hazards created via report intake and the SRM workflow (`sram_service.py`) | COMPLIANT |
| Survey scores are safety data (§1.1), not hazard sources | Surveys persist to `surveys` + `survey_responses` only; never to risk tables | COMPLIANT |
| No requirement for survey threshold → hazard auto-injection | No such code path exists | COMPLIANT — no gap |

### Confirmed Non-Gaps

| Feature | Status | Evidence |
|---|---|---|
| Survey scoring works | Working (demo data seeded correctly) | `compute_survey_result` + `survey_scoring.py` |
| <70% classification | Working (in-memory) | `dashboard_service.py:209` |
| LLM recommendations | Working (text only) | `gemini.py:405-479` |
| Assessment cache | Broken (CRITICAL drift) | `sms_maturity` table drifted — see SCHEMA_DRIFT_REPORT.md |

### Module B Implication

No survey-to-hazard bridge is required for compliance. Module B consumes hazards from the §2.1 source list (reports, audits, hazard surveys) via the existing SRM workflow, and its `risk_register` schema must align to the manual's Risk Register format (§2.3.5). The `sms_maturity` cache drift remains a separate Module A defect (see Section 6).

---

## 6. Recommendation

**Recommendation: (a) No change required.**

The current codebase is compliant with the CAAN SRM Procedure Manual. Survey scores are indicators, not hazards. The manual's §2.1 seven-source list does not include the SMS health survey as a hazard-identification activity.

Rationale: §2.1's "Hazard Survey Reports" refers to a distinct hazard-identification activity. The SMS health survey is referenced in §1.1 as a source of safety data for SMS improvement, not as a hazard source.

The `sms_maturity` cache drift (MODULE_A_CONTRACT.md §8) remains a separate critical defect that must be resolved before Module A can function in production. This is independent of the survey-to-hazard question.

---

## 7. Open Questions

1. Optional confirmation from CAAN on the interpretation of "Hazard Survey Reports" in §2.1 — recommended for compliance defensibility but not required.

---

*Report generated by opencode read-only analysis. No code, schema, or data modifications were made.*