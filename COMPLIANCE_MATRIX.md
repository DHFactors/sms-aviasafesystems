# COMPLIANCE_MATRIX.md — Platform-Wide Compliance Mapping

AviaSAFE SMS Platform
Status: DRAFT COMPLETE — pending implementation
Purpose: Single source of truth for regulatory compliance across all modules.
Audience: CAAN auditors, platform team, developers, users.
Reference framework: ICAO Annex 19 Third Edition (applicable 26 November 2026),
CAAN CAR-19, CAAN SRM Procedure Manual (First Edition, January 2026), Doc 9859,
Doc 10159.

Base of analysis: `MODULE_A_CONTRACT.md`, `MODULE_B_CONTRACT.md` (esp. §32),
`MODULE_C_CONTRACT.md` (esp. §13), `RBAC_MODEL.md`, `DASHBOARD_CONTRACT.md`,
`SCHEMA_RECONCILIATION_PLAN.md`, `DISCOVERY_REPORT.md`, `SECURITY_REVIEW.md`,
`OVERDUE_MODEL_VERIFICATION.md`, `FIRST_ACTION_KPI_VERIFICATION.md`, and the
codebase. Every row cites the owning contract section; every gap cites its
schema note (SN#). Statuses are the **regulatory capability**, not the
underlying service. All rows are **PENDING IMPLEMENTATION** unless noted.

---

## 1. EXECUTIVE SUMMARY
**Purpose.** Present the platform-wide compliance position at a glance and rank
the work needed before a CAAN audit.

**Content.**
- **Total compliance rows: 64**, across six frameworks (Annex 19, CAAN SRM
  Manual, CAR-19, Doc 9859, Doc 10159, cross-cutting).
- **Counts by status: 9 Implemented · 48 Partial · 7 Missing.**

| Framework | Rows | Implemented | Partial | Missing |
|---|---|---|---|---|
| Annex 19 Third Edition (§2) | 15 | 0 | 14 | 1 |
| CAAN SRM Manual (§3) | 16 | 7 | 8 | 1 |
| CAAN CAR-19 (§4) | 8 | 1 | 7 | 0 |
| Doc 9859 (§5) | 10 | 0 | 10 | 0 |
| Doc 10159 (§6) | 9 | 1 | 5 | 3 |
| Cross-cutting (§7) | 6 | 0 | 4 | 2 |
| **Total** | **64** | **9** | **48** | **7** |

- **Overall readiness: NOT READY — DRAFT COMPLETE pending implementation.** The
  SRM computational core of Module B is already implemented (6 CAAN rows;
  Module B §32.5) and Module A produces working survey scores, but no framework
  is audit-complete. The 7 Missing rows are the hard blockers: §5.2.4
  voluntary/confidential reporting; SRM §2.3.6.6 acceptance authority; Doc 10159
  predictive, prescriptive and data-governance; cross-cutting confidential
  reporting and non-delegable AE.
- **Top 10 remediation priorities** (full detail in §9): confidential reporting;
  AE non-delegability/acceptance authority; Module A `sms_maturity`
  reconciliation; two-signature risk acceptance; hazard-registration
  completeness; State SPI/SPT persistence; protection hardening; taxonomy
  unification; safety-intelligence output; RBAC + AE-dashboard enforcement.

**Current implementation.** Module B §32.5 reports 6 Implemented / 12 Partial /
1 Missing (19 rows); Module C §13.4 reports 0 Implemented / 11 Partial / 1
Missing (12 rows); Module A has no module matrix and is derived from
`MODULE_A_CONTRACT.md` §7-§8.

**Gaps.** No single status has been independently audited; the matrix
consolidates self-assessed contract statuses.

---

## 2. ANNEX 19 THIRD EDITION — FULL MAPPING
**Purpose.** Map every relevant Annex 19 Third Edition section to its module(s)
and implementation status.

**Content.**

| Annex 19 § | Description | Module(s) | Section(s) | Status | Notes |
|---|---|---|---|---|---|
| §3.3.2 | State's obligation to require SMS of service providers | C | §4 | Partial | PSOE tracks maturity; categorical binds (Module C §4, Q4.1) |
| §3.4.1.3 | Periodically assess SMS / monitor performance | C | §4 | Partial | PSOE-3/4; periodicity MISSING (Module C Q4.2) |
| §3.4.2.1 | State SPIs (with SPTs) | C | §9 | Partial | `spi_service.py:21-118`; State SPT table SN-C6 not wired |
| §5.1 | Safety intelligence strategy | C | §1 | Partial | Descriptive only; predictive/prescriptive roadmap (Module C §11) |
| §5.2 | SDCPS (capture/store/aggregate/analyse) | C, B | C §2; B §2/§25 | Partial | Aggregation exists; governance §5.2.7 MISSING (Module C §2) |
| §5.2.4 | Voluntary safety reporting system | B | §30 | Missing | Confidential channel absent (Module B §27; DP-4) |
| §5.2.6 | Taxonomy aligned with standardized taxonomies | B, C | B §3; C §8 | Partial | ADREP/ICAO/N-HRC parallel, ununified (Module B SN2; Module C SN-C4/C8) |
| §5.3 | Safety data and information analysis | C | §3 | Partial | Descriptive + diagnostic roadmap (SLI-1..8); predictive/prescriptive MISSING |
| §5.3.1 | Safety performance indicators | C | §9 | Partial | SPI definitions + State SPIs; State trend PLACEHOLDER (`spi_service.py:343,352`) |
| §5.4 | Safety data protection | C | §5 | Partial | Classification + anonymization (DP-1..7); RLS gaps (DP-6) |
| §5.5 | Safety information sharing | C | §6 | Partial | CAAN→operator baseline (SS-1..6); State-to-State deferred (SS-4) |
| App 2 §2.1.1 | Hazard identification | B | §2, §3 | Partial | 11/13 CAAN §2.1 fields; `identified_at` missing (Module B SN1) |
| App 2 §2.2 | Safety risk assessment | B | §5-§9 | Partial | Bow-Tie/profile/barrier/register implemented; acceptance gaps (§17) |
| App 2 §3.1 | Safety performance monitoring & measurement | A | §1, §5 | Partial | Survey scoring works; `sms_maturity` cache broken (Module A §7/§8) |
| App 3 | Protection of safety data/information | C, B | C §5; B §31 | Partial | Use-limitation + classification; confidential class MISSING (Module C §5) |

**Current implementation.** Consolidated from Module B §32.2 (4 Annex rows) and
Module C §13.1 (12 rows), extended with Module A App 2 §3.1.

**Gaps.** 0 Implemented / 14 Partial / 1 Missing. The one Missing row is §5.2.4
(Module B-owned).

---

## 3. CAAN SRM MANUAL — FULL MAPPING
**Purpose.** Map every CAAN SRM Procedure Manual (First Edition, Jan 2026)
section to Module B implementation status.

**Content.** Source: Module B §32.1 (verified against the manual).

| CAAN § | Description | Module | Section | Status | Notes |
|---|---|---|---|---|---|
| §1.1 | Definitions | B | enums | Implemented | Reflected in `models/hazard.py:7-13`, `models/can_cap.py:47-56` |
| §2.1 | Hazard registration (13 fields) | B | §3 | Partial | 11/13 modeled; `identified_at` + equipment/area free-text missing (SN1, SN2) |
| §2.2 | Initial prioritization (H/M/L, ERC) | B | §4 | Partial | ERC question-set missing (Q4, §13); 24h/7d/15d advisory (Q5) |
| §2.3.1 | Bow-Tie analysis | B | §5 | Implemented | — |
| §2.3.2 | Risk Profile | B | §6 | Implemented | — |
| §2.3.3 | Risk Acceptance (two signatures) | B | §7, §17 | Partial | Single-signature today; two-signature pending (SN5) |
| §2.3.4 | Barrier Register | B | §8 | Implemented | — |
| §2.3.5 | Risk Register | B | §9 | Implemented | Legacy + SRAM registers in parallel (SCHEMA_RECONCILIATION_PLAN D1) |
| §2.3.6.1 | Severity (7 impact areas) | B | §11 | Partial | Numerical value computed; per-consequence sheet pending (SN10) |
| §2.3.6.2 | BSV | B | §12 | Partial | Dual implementation; retire continuous (SN11) |
| §2.3.6.3 | Probability / CBSV | B | §13 | Partial | Tables A-E implementation reading — UAT verify (Decision 1, 2d) |
| §2.3.6.4 | Risk Matrix | B | §14 | Implemented | Numeric + severity-letter display |
| §2.3.6.5 | Risk Tolerability | B | §15 | Implemented | — |
| §2.3.6.6 | Acceptance Authority | B | §16 | Missing | Non-delegability not enforced (§22, SN6) |
| §2.4 | CAN | B | §19 | Partial | Platform extension beyond the CAAN manual |
| §2.5 | CAP | B | §20 | Partial | Platform extension beyond the CAAN manual |

**Current implementation.** Module B §32.5 reports **6 Implemented / 12 Partial
/ 1 Missing** across its 19 rows; this table adds §1.1 as Implemented
(7/8/1 over 16 rows).

**Gaps.** Missing: §2.3.6.6 (acceptance authority + non-delegability). Partial
rows are covered by Module B SN1-SN17 (all PENDING).

---

## 4. CAAN CAR-19 REQUIREMENTS
**Purpose.** Map CAR-19 obligations to the platform.

**Content.** Exact CAR-19 text was **not available** in this pass; rows below are
inferred from Annex 19 Chapter/Appendix 2 and the CAAN SRM Manual (as the
national CAR-19 instrument mirrors both). Marked as inferred.

| CAR-19 requirement (inferred) | Module | Section | Status | Notes |
|---|---|---|---|---|
| Hazard identification and taxonomy | B | §2, §3, §8 | Partial | ADREP/ICAO carrying columns; `nhrc_category` pending (SN-C9) |
| Safety risk assessment (SRM) | B | §5-§9 | Partial | Computational core implemented (Module B §32.5) |
| Risk tolerability determination | B | §15 | Implemented | 3-tier matrix (`srm_engine.py:87-113`) |
| Risk acceptance authority (non-delegable) | B | §16, §17 | Partial | Single signature; AE gate + two-signature pending (SN5/SN6) |
| Corrective action (CAN / CAP) | B | §19, §20 | Partial | Platform extension; overdue model verified (`OVERDUE_MODEL_VERIFICATION.md`) |
| Mandatory occurrence reporting (MOR/VSR) | B | §30 | Partial | Occurrence reports exist; category-tiered timer pending (SN15) |
| SSP performance reports (quarterly/annual) | B, C | B §30; C §6 | Partial | `regulatory_reports` + weekly SSP dispatch; not audit-grade |
| State oversight / SDCPS | C | §2, §3 | Partial | Aggregation layer; governance §5.2.7 MISSING (Module C §2) |

**Current implementation.** Inferred only — no CAR-19 document in `data/` or the
repo.

**Gaps.** 1 Implemented / 7 Partial / 0 Missing. **UNKNOWN — NEEDS HUMAN INPUT:**
the official CAR-19 text to replace inferred rows.

---

## 5. DOC 9859 — CHAPTER MAPPING
**Purpose.** Map the Doc 9859 (Safety Management Manual) chapters and paragraphs
referenced across the contracts.

**Content.**

| Doc 9859 § | Description | Module | Section | Status |
|---|---|---|---|---|
| §1.3.4 | Implementation planning | B | §4 | Partial |
| §2.5 | Safety risk management | B | §5-§9 | Partial |
| §4.5 | AE risk-acceptance role | B | §16, §22 | Partial |
| §8 | State safety management | C | §1, §3 | Partial |
| §9.3.6.1 | Safety manager responsibilities | B | §3, §10, §26 | Partial |
| §9.3.6.6 | Prompt collection and analysis | B | §27 | Partial |
| §9.3.6.8 | Safety Review Board (SRB) | B | §29 | Partial |
| §9.3.6.9 | Safety Action Group (SAG) | B | §28 | Partial |
| §9.6.5 | Safety communication | B | §31 | Partial |
| Ch.9 / §9.5 | SMS safety assurance / maturity | A, B | A §1/§5; B §15 | Partial |

**Current implementation.** References catalogued in Module B §32.3; no chapter
is audit-complete.

**Gaps.** 0 Implemented / 10 Partial / 0 Missing. Doc 9859 §1.3.4 heading
confirmation is **UNKNOWN — NEEDS HUMAN INPUT** (Module B §4; Module C §4).

---

## 6. DOC 10159 — SAFETY INTELLIGENCE MAPPING
**Purpose.** Map Doc 10159 (Safety Intelligence Manual) concepts to Module C
implementation.

**Content.** Source: Module C §11, §13.2.

| Doc 10159 concept | Module | Section | Status |
|---|---|---|---|
| Data → Information → Intelligence progression | C | §1, §3, §11 | Partial |
| Safety Intelligence Cycle | C | §3 | Partial |
| D3M (Data-Driven Decision-Making) | C | §3 (SLI-6), §11 | Partial |
| Descriptive analysis | C | §11 (AL-1) | Implemented |
| Diagnostic analysis | C | §11 (AL-2), `nhrc_service.py:301-308` | Partial |
| Predictive analysis | C | §11 (AL-3) | Missing |
| Prescriptive analysis | C | §11 (AL-4) | Missing |
| SDCPS structure | C | §2 (SDCPS-1..8) | Partial |
| Data governance | C | §2 (SDCPS-7, §5.2.7) | Missing |

**Current implementation.** Module C §13.2: descriptive layer live
(`aggregation_service.py:120-210`; `state_risk_service.py:153-275`;
`spi_service.py:303-358`; `nhrc_service.py:280-286`).

**Gaps.** 1 Implemented / 5 Partial / 3 Missing (predictive, prescriptive,
governance). Doc 10159 page-level text was not extracted (Module C §3 UNKNOWN).

---

## 7. CROSS-CUTTING COMPLIANCE ITEMS
**Purpose.** Capture obligations that span modules or the platform layer.

**Content.**

| Item | Module(s) | Section(s) | Status | Notes |
|---|---|---|---|---|
| Multi-tenant isolation | Platform/ RBAC | RBAC §4 | Partial | RLS on core tables; 6 tables RLS-off (`DB_VERIFICATION.md:181-182`); H1/H2 (`SECURITY_REVIEW.md:48-54`) |
| Confidential reporting | B + App 3 | B §27; C §5 | Missing | No confidential class (Module C DP-4; Q5.2 Module B-owned) |
| Non-delegable AE role | B + CAAN §2.3.6.6 | B §16, §22 | Missing | Documented, not enforced (Module B §22; RBAC §6) |
| Audit trail coverage | Platform | RBAC §8 | Partial | `audit_logs` exists; `CAAN_READ_*`/`CAAN_SHARE_*`/escalation writers absent (Module C DP-3/SS-2/HV-2) |
| Data protection and classification | C | C §5 (DP-1..7) | Partial | Classification labels missing (G-5.3); RLS gaps (DP-6); use-limitation pending (DP-7) |
| Role-based access control | Platform | RBAC §1-§3 | Partial | Coarse module gate; middleware unregistered (`SECURITY_REVIEW.md:76-77`); new roles absent |

**Current implementation.** `audit_logs` (`db_models.py:1646-1668`); RLS policies
(`scripts/supabase_rls.sql:30-220`); `RBAC_MODEL.md` as the target.

**Gaps.** 0 Implemented / 4 Partial / 2 Missing.

---

## 8. SUMMARY BY STATUS
**Purpose.** Provide auditable counts across all frameworks.

**Content.**

| Framework | Rows | Implemented | Partial | Missing |
|---|---|---|---|---|
| Annex 19 Third Edition | 15 | 0 | 14 | 1 |
| CAAN SRM Manual | 16 | 7 | 8 | 1 |
| CAAN CAR-19 | 8 | 1 | 7 | 0 |
| Doc 9859 | 10 | 0 | 10 | 0 |
| Doc 10159 | 9 | 1 | 5 | 3 |
| Cross-cutting | 6 | 0 | 4 | 2 |
| **Total** | **64** | **9** | **48** | **7** |

Per-module breakdown (by primary owner; shared rows counted once):

| Module | Primary rows | Implemented | Partial | Missing |
|---|---|---|---|---|
| Module A (Survey) | 1 | 0 | 1 | 0 |
| Module B (Hazard & Risk) | 35 | 7 | 27 | 1 |
| Module C (Regulator/SDCPS) | 22 | 1 | 18 | 3 |
| Cross-cutting (platform/RBAC) | 6 | 0 | 4 | 2 |

**Missing rows (7):** Annex 19 §5.2.4 (voluntary reporting); SRM §2.3.6.6
(acceptance authority); Doc 10159 predictive, prescriptive, data governance;
cross-cutting confidential reporting, non-delegable AE.

**Current implementation.** Counts derived by summing §§2-7 statuses.

**Gaps.** Framework rows overlap thematically (e.g. §5.2.4 appears as Annex 19
and cross-cutting confidential reporting); counts are by framework, not unique
requirements.

---

## 9. REMEDIATION ROADMAP
**Purpose.** Sequence the highest-impact work to reach audit readiness.

**Content.** Ordered by blocking severity and dependency.

1. **Confidential / voluntary reporting class (§5.2.4; App 3).**
   - Missing: confidential/restricted flag + workflow; Module B owns (Q5.2).
   - Risk: the **only Missing Annex 19 row**; undermines §5.4/App 3 protection.
   - Schema note: Module C DP-4; Module B §27.
   - Effort: Medium (flag + RLS + UI). **Dependency:** Module B schema change.

2. **AE non-delegability + acceptance authority (SRM §2.3.6.6).**
   - Missing: role validation, terminal rule, one-AE-per-tenant.
   - Risk: the **only Missing SRM row**; invalidates risk-acceptance chain.
   - Schema note: Module B SN6; RBAC §6.
   - Effort: Medium. **Dependency:** `ACCOUNTABLE_EXECUTIVE` role (RBAC Q-R2).

3. **Module A `sms_maturity` reconciliation + RLS.**
   - Missing: ORM/live shape match; RLS enable; LLM persistence.
   - Risk: silent production failure; App 2 §3.1 output not persisted.
   - Schema note: SCHEMA_RECONCILIATION_PLAN D2 (Step 7).
   - Effort: Medium. **Dependency:** none (Module A-owned).

4. **Two-signature risk acceptance (§2.3.3).**
   - Partial: single signature today; process-conformance signer absent.
   - Risk: acceptance chain not CAAN-conformant.
   - Schema note: Module B SN5 (§17).
   - Effort: Medium. **Dependency:** item 2 (AE signer).

5. **Hazard registration completeness (§2.1).**
   - Partial: 11/13 fields; `identified_at` + equipment/area free-text missing.
   - Risk: SDCPS capture incomplete (Module B §3).
   - Schema note: Module B SN1/SN2.
   - Effort: Small-Medium. **Dependency:** none.

6. **State SPI/SPT persistence + trend (§3.4.2.1 / §5.3.1).**
   - Partial: State trend placeholder (`spi_service.py:343,352`); SPT stub
     non-persisting (`api/v1/spi.py:129-142`).
   - Risk: State analysis descriptive-only.
   - Schema note: Module C SN-C1, SN-C3, SN-C6.
   - Effort: Large. **Dependency:** materialization job (Module C §7).

7. **Protection hardening (§5.4 / App 3).**
   - Partial: RLS on `caan_reports`/`sms_maturity`/`state_risk_categories` off;
     no classification labels; no CAAN read audit.
   - Risk: data-protection non-compliance; blocks §5.5 sharing.
   - Schema note: Module C DP-1/DP-3/DP-6/DP-7.
   - Effort: Medium. **Dependency:** item 3 (sms_maturity RLS overlaps).

8. **Taxonomy unification (§5.2.6).**
   - Partial: ADREP/ICAO/N-HRC parallel.
   - Risk: inconsistent State hazard identification and sharing.
   - Schema note: Module C SN-C4/SN-C8/SN-C9; Module B SN2.
   - Effort: Large (coordinated Module B change). **Dependency:** none.

9. **Safety-intelligence output (§5.3.1(d) / §5.1).**
   - Partial/Missing: empty `insights`/`recommendations`
     (`api/v1/state_risk.py:49-50`); predictive/prescriptive Missing.
   - Risk: Doc 10159 D3M not delivered.
   - Schema note: Module C AL-2..AL-4; Q11.1 three-lane LLM.
   - Effort: Large. **Dependency:** items 6, 7 (aggregates + protection).

10. **RBAC enforcement + AE dashboard/KPI (§5.2.5; RBAC).**
    - Partial: RBAC middleware dead (`SECURITY_REVIEW.md:76-77`); H1/H2
      under-authorized; AE Hazard-Response-Time KPI has no endpoint.
    - Risk: cross-tenant exposure; AE oversight dashboard non-functional.
    - Schema note: RBAC §9 migration path; DASHBOARD_CONTRACT §4.
    - Effort: Large. **Dependency:** items 2, 3.

**Current implementation.** None of the ten is complete.

**Gaps.** 7 Missing rows map to items 1, 2, 9; the remaining items raise Partial
frameworks.

---

## 10. AUDIT READINESS ASSESSMENT
**Purpose.** Give an honest readiness verdict and the path to audit.

**Content.**
- **Is the platform ready for a CAAN audit? No — NOT READY.** Of 64 rows, only
  9 are Implemented (14%), 48 Partial (75%), and 7 Missing (11%). Ten of the
  fifteen Annex 19 rows are Partial and one is Missing; the SRM computational
  core is the strongest area (7 Implemented) but the acceptance chain
  (§2.3.3/§2.3.6.6) is not conformant.
- **What is needed before audit:**
  1. Close the 7 Missing rows (items 1, 2, 9 in §9) — especially §5.2.4
     confidential reporting and SRM §2.3.6.6 non-delegability, which are
     single-row framework blockers.
  2. Reconcile Module A `sms_maturity` so App 2 §3.1 outputs persist.
  3. Persist State SPI/SPT and replace the placeholder State trend.
  4. Harden data protection (RLS + classification + read audit) to support
     §5.4/App 3.
  5. Enforce RBAC uniformly (register the middleware; authorise
     regulator/SPI/N-HRC paths) so tenant isolation is demonstrable.
  6. Produce audit evidence: `audit_logs` coverage for every privileged action
     (RBAC §8).
- **Interim compliance posture:** the platform can demonstrate a working
  descriptive safety-management workflow (survey scoring, hazard identification,
  bow-tie/SRAM, CAN/CAP) under tenant isolation on the core tables. It cannot
  yet demonstrate confidential reporting, non-delegable acceptance, State
  performance-target persistence, or predictive/prescriptive intelligence.
- **Pilot deployment considerations:** a pilot is viable for Module B
  operational workflow and Module A surveys with the understanding that
  (a) acceptance is single-signature, (b) confidential reporting is absent,
  (c) regulator read-audit is absent, and (d) Module C trend/intelligence output
  is descriptive-only. Confirm the CAAN position on §5.5 sharing (Q3) and
  Appendix 3 agreements before any State-to-State exchange.

**Current implementation.** Self-assessed; no external audit performed.

**Gaps.** No audit evidence pack; no penetration test referenced; status counts
are contract-derived, not verified against a running production build in this
pass.

---

## 11. OPEN QUESTIONS
**Purpose.** Enumerate unresolved compliance decisions.

**Content.**
- **Q-C1** Official CAR-19 text: rows in §4 are inferred. **UNKNOWN — NEEDS
  HUMAN INPUT.**
- **Q-C2** Doc 9859 §1.3.4 heading confirmation for implementation planning.
  **UNKNOWN — NEEDS HUMAN INPUT.**
- **Q-C3** Doc 10159 page-level extraction (only the summary PDF was used).
  **UNKNOWN — NEEDS HUMAN INPUT.**
- **Q-C4** Confidential reporting ownership: Module B creates/flags vs Module C
  consumes (Module C Q5.2). **Decision needed.**
- **Q-C5** AE identity mechanism (claim vs flag vs role) — gates SRM §2.3.6.6
  (RBAC Q-R2). **Decision needed.**
- **Q-C6** Canonical module flags and the backend/frontend `module3` mismatch
  (RBAC Q-R5; Dashboard Q-D6). **Decision needed.**
- **Q-C7** Retention/deletion for the protected class (Module C Q5.1).
  **UNKNOWN — NEEDS HUMAN INPUT.**
- **Q-C8** State-to-State sharing recipients and Appendix 3 agreements (Module C
  Q3/SS-4). **UNKNOWN — NEEDS HUMAN INPUT.**
- **Q-C9** Predictive/prescriptive scope and in-house vs vendor (Module C
  Q7/Q11.2). **UNKNOWN — NEEDS HUMAN INPUT.**
- **Q-C10** Will CAAN accept a documented single-signature interim acceptance
  for pilot (Y/N)? **UNKNOWN — NEEDS HUMAN INPUT.**

---

*End of COMPLIANCE_MATRIX.md. Status: DRAFT COMPLETE — pending implementation.
Consolidated from `MODULE_A_CONTRACT.md`, `MODULE_B_CONTRACT.md` §32,
`MODULE_C_CONTRACT.md` §13, `RBAC_MODEL.md`, `DASHBOARD_CONTRACT.md`, and the
verification reports. Every status traces to a contract section; all remediation
items map to schema notes SN1-SN17 / SN-C1-SN-C10. No fixes or implementations
are proposed.*
