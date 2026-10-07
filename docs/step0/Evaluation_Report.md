<!--
AUTHORITATIVE COPY.
Location: D:\Projects\aviasafesms\docs\step0\Evaluation_Report.md
Original (historical): D:\Projects\Project_Evalulation_Report.md
Copied: 2026-10-07
Edits must be made here, not in the original.
-->

# Project Evaluation Report

## SMS360X (`D:\Projects\sms360x`) vs AviaSAFE SMS Platform (`D:\Projects\aviasafesms`)

Status: Neutral Comparative Evaluation

Date: 2026-10-07

Prepared from: repository contents on disk only (documentation, source, schema, migrations). No live system was executed and no database was inspected.

---

# 0. Purpose and method

This report compares two local projects on a fixed set of axes and states, for each axis, whether they **MEET** (materially aligned), **DIVERGE** (materially different or conflicting), or are **PARTIAL** (overlapping direction, different depth or status).

Neutrality rules applied:

- Each position is reported from that project's own documents and code, with citations.
- No project is declared "better". Where one is more advanced than the other, that is reported as a maturity difference, not a quality verdict.
- Differences in lifecycle stage (design vs production) are stated explicitly rather than scored away.
- Where a claim is an inference, it is labelled "inference".

Sources are listed in Appendix A.

---

# 1. At-a-glance profiles

| Dimension | SMS360X (`sms360x`) | AviaSAFE (`aviasafesms`) |
|---|---|---|
| Self-description | Aviation safety intelligence operating system / "modular Safety Intelligence Platform" | Multi-tenant aviation SMS intelligence platform for Nepal |
| State | Architecture-first, pre-implementation | Released production v1.0.0 |
| Primary market | Operators, regulators, State Safety Programmes (CAAN context) | Nepal operators and CAAN |
| Frameworks | ICAO Annex 19, Doc 9859, Doc 10159, ADREP, HFACS, Nano-Code | ICAO Annex 19, Doc 9859, Doc 10159, ADREP, HFACS, CAAN CAR-19, CAAN SRM Manual, Nepal NASP |
| Module model | 6 intelligence layers + Module 1 (SMS Maturity), Module 2 (SRM), M14 State Workspace, OIP-01..07 | 3 modules: A Survey/SMS Health, B Hazard & Risk (SRAM), C State Regulator/SDCPS/PSOE + 4 role dashboards |
| Tech stack | TypeScript libraries + Supabase Postgres/RLS (planned Auth); no API/UI | Python 3.11 FastAPI + Firebase Auth + Supabase Postgres + static HTML/JS; Gemini/Groq AI |
| Persistence | 31 tables deployed to Supabase DEV; no runtime | Live Postgres/Supabase; Firestore deprecated 2026-09-12 |
| Authorization | RLS architecture frozen (AD-01..AD-15), default-deny, membership-scoped; migrations drafted, not deployed | Firebase JWT + custom claims; RLS live on core tables (6 disabled); RBAC middleware dead; known gaps |
| Commercial | Explicit tiers: Base, Professional, Advanced, Expert, State; Knowledge Network future | No payment processor; subscription fields only |
| Validation | Synthetic operator dataset spec (5 operators, 36 months); success criteria; not executed | 1062 backend tests, UAT smoke, seeders; audit-readiness self-assessed NOT READY |
| Governance docs | Constitution, ADR-001..008, Decisions 001..034, Tasks 001..040, blueprints, RLS designs | Module contracts A/B/C, RBAC, Dashboard, Compliance Matrix, Discovery, Schema Reconciliation, Security Review, Implementation Roadmap |
| Recorded readiness | Overall 58%, governance 90%, architecture 78%, dashboard 46% | Compliance 64 rows: 9 implemented / 48 partial / 7 missing; audit NOT READY |

---

# 2. Comparison matrix (verdicts)

| # | Axis | Verdict | One-line basis |
|---|---|---|---|
| 1 | Purpose and positioning | PARTIAL | Both claim a "safety intelligence platform"; SMS360X productises intelligence, AviaSAFE operationalises SMS management + compliance. |
| 2 | Regulatory framework alignment | MEET (scope) / DIVERGE (instruments) | Same ICAO core; AviaSAFE adds CAAN CAR-19 + SRM Manual + Nepal NASP; SMS360X adds Nano-Code + explicit NASP/SSP/RBO/Knowledge Network. |
| 3 | Target customer and payer | MEET | Both operator-first with a State/regulator secondary; neither has implemented billing. |
| 4 | Intelligence architecture | DIVERGE | SMS360X defines 6 layers, OIP, M14 S1-S10, RBO; AviaSAFE has SPI/SPT, N-HRC, state risk, PSOE but no OIP/RBO/M14 layer model. |
| 5 | Domain / data model | PARTIAL | Strong overlap on hazard/risk/barrier/occurrence/SPI; AviaSAFE adds operational workflow objects, SMS360X adds governance hierarchy + richer barrier assurance + import lineage. |
| 6 | SRM methodology | MEET | Both use bow-tie, barrier, risk matrix, tolerability/ALARP, non-delegable AE acceptance; details differ. |
| 7 | Ownership / tenancy | PARTIAL | Both operator-tenant ownership + isolation; different regulator access mechanism (aggregation vs OIP intelligence contract). |
| 8 | State / regulator capability | PARTIAL | Both have state risk + SPI/SPT + SSP; AviaSAFE adds PSOE + N-HRC + live dashboards; SMS360X adds RBO + maturity index + OIP + NASP + Knowledge Network (designed). |
| 9 | SMS maturity | MEET (concept) / PARTIAL (detail) | Both 4 ICAO pillars; AviaSAFE implemented survey scoring; SMS360X formula undefined. |
| 10 | Commercial model | DIVERGE | SMS360X defines tiers; AviaSAFE has none. |
| 11 | Technology stack | DIVERGE | Python/FastAPI/Firebase vs TypeScript/Supabase; both Postgres/Supabase multi-tenant. |
| 12 | Security / authorization | PARTIAL | Both use Postgres RLS; SMS360X design is stricter on paper; AviaSAFE is partly live but has documented holes. |
| 13 | Delivery maturity | DIVERGE | AviaSAFE is deployed production with gaps; SMS360X is designed, schema deployed to DEV, no runtime. |
| 14 | Documentation / governance | MEET | Both are documentation-heavy with contract/decision artefacts. |
| 15 | Validation approach | DIVERGE | AviaSAFE = automated tests + live UAT; SMS360X = planned synthetic dataset + success criteria. |
| 16 | Unique capabilities | DIVERGE | Each holds capabilities the other lacks (see Section 5). |

---

# 3. Detailed findings by axis

## 3.1 Purpose and positioning

SMS360X states intelligence is the product and registers are inputs, with a formal data-to-intelligence chain and a "dashboards visualise intelligence, they do not define it" principle (`sms360x/SMS360X-PRODUCT-VISION.md`; `COPILOT-TASK-035.md`; `COPILOT-TASK-036.md`). Its architecture is documentation-first and explicitly not yet implemented (`sms360x/docs/PROJECT-STATUS.md`).

AviaSAFE describes itself as a "multi-tenant aviation Safety Management System (SMS) intelligence platform" (`aviasafesms/README.md`) but its shipped centre of gravity is operational SMS management plus regulatory compliance: reporting, hazard/risk workflow, CAN/CAP, PSOE, dashboards, PDF reports, and state aggregation (`aviasafesms/DISCOVERY_REPORT.md`).

Verdict: PARTIAL. Both invoke "intelligence"; SMS360X treats intelligence productisation as the core, AviaSAFE treats operational SMS execution and regulator compliance as the core, with intelligence as an output.

## 3.2 Regulatory alignment

Shared core: ICAO Annex 19, Doc 9859, Doc 10159, ADREP, HFACS appear in both (`sms360x/README.md`, `sms360x/docs/SMS360X-CONSTITUTION.md`; `aviasafesms/README.md`, `aviasafesms/COMPLIANCE_MATRIX.md`).

AviaSAFE additionally aligns to CAAN CAR-19 and the CAAN SRM Procedure Manual (First Edition, Jan 2026) and Nepal's NASP 2023-2025 National High-Risk Categories (`aviasafesms/COMPLIANCE_MATRIX.md`; `aviasafesms/backend/app/services/nhrc_service.py`). SMS360X adds Nano-Code taxonomy as a first-class classification with its own intelligence layer (`sms360x/docs/DATA-MODEL.md`; `COPILOT-TASK-035.md`).

Verdict: MEET on framework scope; DIVERGE on regulatory instruments (AviaSAFE is CAAN-procedural and NASP-grounded; SMS360X is framework-generic and future-facing).

## 3.3 Target customer and payer

Both serve operators and a State/regulator audience. SMS360X names Safety Manager, Accountable Manager, and State Regulator as primary users and defines operator and State subscription tiers (`sms360x/SMS360X-PRODUCT-VISION.md`). AviaSAFE defines airline (service provider) and CAAN (State) audiences and role-scoped dashboards (`aviasafesms/README.md`; `aviasafesms/DASHBOARD_CONTRACT.md`).

Neither has an implemented payment processor. AviaSAFE carries only subscription lifecycle fields (`aviasafesms/DISCOVERY_REPORT.md` 1.14); SMS360X defines packages but no billing implementation (the whole product is pre-implementation).

Verdict: MEET.

## 3.4 Intelligence architecture

SMS360X (designed): six intelligence layers (Compliance, Operational, Emerging, ADREP, HFACS, Nano-Code), Module 1 SMS Maturity, Module 2 SRM, Operator Intelligence Pack OIP-01..07, M14 State Workspace products S1-S10, Risk-Based Oversight, SSP/NASP, and a Knowledge Network (`sms360x/SMS360X-PRODUCT-VISION.md`; `COPILOT-TASK-034.md`..`040.md`).

AviaSAFE (implemented): SPI/SPT (8 SPIs), N-HRC (7 Nepal NASP categories), state risk register, PSOE, SSP dispatch, and regulator dashboards (`aviasafesms/docs/status.md`; `aviasafesms/MODULE_C_CONTRACT.md`; `aviasafesms/DASHBOARD_CONTRACT.md`). Term search confirms AviaSAFE has no OIP, no "Operator Intelligence", no "Knowledge Network", no "M14", and no exact "Risk-Based Oversight" (Appendix B).

Verdict: DIVERGE. The layer/OIP/RBO/M14/Knowledge-Network construct is substantially unique to SMS360X; SPI/SPT/N-HRC/PSOE is AviaSAFE-specific operational measurement.

## 3.5 Domain and data model

Shared entities: hazard, risk/risk-register, barrier/barrier-register, occurrence/report, findings/actions (SMS360X Action/Finding; AviaSAFE CAN/CAP/verification), SPI, SPT, safety objectives, ADREP and HFACS classification (`sms360x/docs/DATA-MODEL.md`; `aviasafesms/DISCOVERY_REPORT.md` Section 3).

SMS360X-unique: State/Regulator/Operator governance hierarchy with effective-dated memberships and oversight relationships; TopEvent/Consequence; a barrier assurance model with dependencies, redundancy, common-cause failure, failure modes, and an evidence chain; import lineage with historical versioning (`sms360x/docs/ADR-002`, `BARRIER-MODEL-ENHANCEMENT.md`, `ADR-005`, `PERSISTENCE-ARCHITECTURE.md`).

AviaSAFE-unique: CAN/CAP operational workflow with signatures and AE escalation; verification and closure lifecycle; flight diversions; PSOE assessment objects; bow-tie tables; N-HRC; state risk register; audit log and dispatch machinery (`aviasafesms/DISCOVERY_REPORT.md` Sections 3.1-3.5). AviaSAFE also has a known `risk_register` dual-shape conflict (legacy vs SRAM) that SMS360X does not have (`aviasafesms/SCHEMA_DRIFT_REPORT.md`; `DISCOVERY_REPORT.md` 3.7).

Verdict: PARTIAL. Common SRM spine; different operational depth and different governance depth.

## 3.6 SRM methodology

Both implement a Bow-Tie (threats, TopEvent, consequences, preventive/recovery controls), a barrier register, a risk matrix, tolerability, and non-delegable Accountable-Executive risk acceptance. AviaSAFE ties this to the CAAN SRM Manual with Barrier Strength Value, per-consequence risk rows, and two-signature acceptance (`aviasafesms/MODULE_B_CONTRACT.md`; `COMPLIANCE_MATRIX.md` Section 3). SMS360X ties it to a scenario-specific Risk-Barrier relationship with assurance evidence (`sms360x/docs/DATA-MODEL.md` Barrier section; `docs/BARRIER-MODEL-ENHANCEMENT.md`).

Verdict: MEET (same methodology family); detail-level divergence in barrier representation.

## 3.7 Ownership and tenancy

AviaSAFE enforces `tenant_id` on every business table with per-tenant RLS policies and a CAAN cross-tenant role; state/national rows use NULL-tenant rows visible only to CAAN (`aviasafesms/RBAC_MODEL.md` Sections 3-4; `DISCOVERY_REPORT.md` 3.6-3.7).

SMS360X formalises operator ownership, non-owning regulator access through active oversight relationships, purpose-bound default-deny RLS, and an explicit rule that only OIP intelligence products leave the operator (`sms360x/docs/ADR-002`; `TASK-033A-ARCHITECTURE-DECISIONS.md` AD-05..AD-09; `OIP-OPERATOR-INTELLIGENCE-PACK-SPECIFICATION.md`).

Verdict: PARTIAL. Same tenant-ownership principle; different regulator-access mechanism (AviaSAFE aggregation into a cross-tenant role; SMS360X OIP intelligence contract plus no-direct-browse rule).

## 3.8 State / regulator capability

AviaSAFE has working state surfaces: state risk register by ICAO category, state SPI/SPT, N-HRC KPIs, PSOE, industry averages, benchmarks, PDF/Excel export, and a partly built State Regulator dashboard (Wave 5 pending) (`aviasafesms/docs/status.md`; `DASHBOARD_CONTRACT.md` Section 5; `IMPLEMENTATION_ROADMAP.md` P4-5).

SMS360X defines M14 State Workspace outputs S1-S10 including State SMS Maturity Index, National Hazard/Risk Profile, Barrier Health Index, RBO Prioritization Matrix, NASP and SSP intelligence; none is implemented (`sms360x/COPILOT-TASK-037.md`; `VALIDATION-SUCCESS-CRITERIA.md`).

Verdict: PARTIAL. Overlapping state-risk/SPI/SPT/SSP; AviaSAFE stronger in implemented oversight (PSOE, N-HRC, exports); SMS360X stronger in designed oversight model (RBO, maturity index, OIP, NASP, Knowledge Network).

## 3.9 SMS maturity

AviaSAFE Module A scores surveys against 4 ICAO components / 12 elements and persists an `sms_maturity` cache (with RLS added in Phase 1) and an async LLM analysis pipeline (`aviasafesms/MODULE_A_CONTRACT.md`; `IMPLEMENTATION_ROADMAP.md` P1-1..P1-3, P2-1..P2-2).

SMS360X Module 1 defines SMS Maturity Intelligence over the same four pillars plus surveys, audits, and training, but the index formula and weights are still OPEN (see `sms360x/docs/SOURCE-DATA-CATALOG-AND-ARCHITECTURE-REPORT.md`, C3/II-06).

Verdict: MEET conceptually; PARTIAL in detail (AviaSAFE implemented, SMS360X formula pending).

## 3.10 Commercial model

SMS360X defines Base, Professional, Advanced, Expert, and State tiers mapped to intelligence layers, plus a future Knowledge Network (`sms360x/SMS360X-PRODUCT-VISION.md`; `COPILOT-TASK-035.md`; `COPILOT-TASK-038.md`). AviaSAFE has no payments and only subscription state fields; feature gating is by numeric module flags (`aviasafesms/DISCOVERY_REPORT.md` 1.14, 1.6).

Verdict: DIVERGE. SMS360X defines product packaging; AviaSAFE has none implemented.

## 3.11 Technology stack

AviaSAFE: Python 3.11 / FastAPI async, Firebase Auth + App Check, Supabase Postgres (asyncpg plus a sync bridge), static HTML/JS frontend, Gemini and Groq AI, APScheduler, Upstash Redis, Render + Firebase Hosting / Cloud Run (`aviasafesms/README.md`; `DISCOVERY_REPORT.md` 1.1).

SMS360X: TypeScript libraries (workbook engine, mappers, normalization, import orchestrator, operating-context resolver), Supabase Postgres with a 31-table baseline and RLS migrations, no API or UI (`sms360x/lib/**`; `sms360x/supabase/migrations/**`; `types/sms360x.ts`).

Verdict: DIVERGE (languages, frameworks, auth provider). Both converge on Postgres/Supabase and multi-tenant RLS.

## 3.12 Security and authorization

AviaSAFE: Firebase JWT with custom claims; RLS on core tables but disabled on 6 tables; RBAC middleware is unregistered dead code; documented H1 (unauthenticated SPI/N-HRC), H2 (caller-controlled `tenant_ids`), and M1 (token revocation not checked) findings (`aviasafesms/RBAC_MODEL.md` Sections 4/9; `SECURITY_REVIEW.md`). Compliance Matrix rates security-relevant rows Partial/Missing.

SMS360X: RLS architecture frozen as AD-01..AD-15 (canonical identity, authoritative membership chain, single active membership, no membership union, tenant boundary, default deny, non-owning regulator, jurisdiction validation, non-authoritative inputs), with helper/policy/grant migrations drafted but not deployed or verified (`sms360x/TASK-033A-ARCHITECTURE-DECISIONS.md`; `supabase/migrations/2026100711*`; `docs/RLS-IMPLEMENTATION-DESIGN-V1.md`).

Verdict: PARTIAL. Both rely on Postgres RLS within Supabase; SMS360X's model is stricter and more explicit on paper; AviaSAFE has some controls live but with acknowledged holes.

Note: neither project is security-complete. AviaSAFE records security findings; SMS360X records its own unresolved security/deployment gates (`sms360x/docs/PROJECT-STATUS.md`; `SITA-HISTORICAL-IMPORT-STRATEGY.md`).

## 3.13 Delivery maturity

AviaSAFE is a deployed product (v1.0.0, live on Render/Firebase, 4 demo tenants, seeders, 1062 tests) with a self-assessed audit-readiness of "NOT READY" (9 implemented / 48 partial / 7 missing of 64 compliance rows) (`aviasafesms/README.md`; `docs/status.md`; `COMPLIANCE_MATRIX.md` Sections 1/10).

SMS360X is pre-implementation: overall 58%, with a Supabase DEV schema deployed (31 tables, 74 FKs) but no RLS, auth, tenant resolution, APIs, or UI (`sms360x/docs/PROJECT-STATUS.md`).

Verdict: DIVERGE sharply. This is the single largest difference and the one most likely to distort any direct feature comparison.

## 3.14 Documentation and governance

Both are documentation-heavy. AviaSAFE has module contracts, RBAC, dashboard contract, compliance matrix, discovery report, schema reconciliation plan, security review, and a sequenced implementation roadmap (`aviasafesms/*.md`). SMS360X has a constitution, ADRs, a numbered decision log (001-034), numbered task specs (001-040), persistence/RLS blueprints, and a synthetic validation framework (`sms360x/docs/**`; root `COPILOT-TASK-*.md`).

Verdict: MEET.

## 3.15 Validation approach

AviaSAFE validates with automated tests, UAT smoke scripts, seeders, and live deployment evidence (`aviasafesms/docs/status.md` Section 3; `backend/tests/**`). SMS360X validates by design: a 5-operator, 36-month synthetic dataset, a safety case library, and pass/fail success criteria across Module 1, Module 2, OIP, M14, RBO, SSP, NASP (`sms360x/VALIDATION-SUCCESS-CRITERIA.md`; `SYNTHETIC-OPERATOR-PROFILES.md`; `SAFETY-CASE-LIBRARY.md`).

Verdict: DIVERGE (executed testing vs planned synthetic validation).

---

# 4. Where they meet

1. Domain: both model hazard, risk, barrier, occurrence/report, findings/actions, SPI, SPT, safety objectives, ADREP, and HFACS.
2. Method: both use Bow-Tie, barrier registers, a risk matrix, tolerability, and non-delegable Accountable-Executive acceptance.
3. Regulatory frame: both target ICAO Annex 19, Doc 9859, and Doc 10159, for a Nepal/CAAN context.
4. Ownership principle: both keep operator data tenant-owned and isolated, with a separate State/regulator view.
5. SMS maturity: both structure maturity around the four ICAO components.
6. Data platform: both use PostgreSQL on Supabase with RLS as the tenant-isolation mechanism.
7. Audience: both serve an operator audience first and a CAAN/State audience second.
8. Culture: both are specification-first and maintain explicit decision/compliance records.
9. State performance: both expose state-level SPI/SPT and an SSP concept.
10. Shared market context: both reference the same operator names and CAAN/Nepal context (for example Sita Air, Tara Air, Nepal operators), and the SMS360X roadmap explicitly references a downloaded copy of the aviasafesystems repository (`sms360x/ROADMAP.md` line 244). This is evidence of shared lineage/context (inference).

---

# 5. Where they diverge

1. Centre of gravity: SMS360X sells intelligence (OIP, RBO, M14); AviaSAFE sells operational SMS management plus compliance.
2. Lifecycle stage: AviaSAFE is deployed and partly compliant; SMS360X is designed and unimplemented.
3. Intelligence taxonomy: SMS360X's 6 layers, OIP-01..07, S1-S10, and RBO have no equivalent in AviaSAFE.
4. Operational workflow: AviaSAFE's CAN/CAP, verification/closure, PSOE, flight diversions, and PDF reports have no equivalent in SMS360X.
5. Regulator access: AviaSAFE reads tenant data through an aggregation layer and a cross-tenant role; SMS360X forbids direct browsing and permits only OIP intelligence products to leave the operator.
6. Governance model: SMS360X defines a State-Regulator-Operator-User hierarchy with effective-dated memberships and oversight relationships; AviaSAFE uses a single `role` string with tenant isolation and a CAAN cross-tenant role.
7. Barrier/risk depth: SMS360X models barrier assurance, dependencies, common-cause failure, and an evidence chain; AviaSAFE models per-consequence risk and two-signature acceptance.
8. NASP/N-HRC: AviaSAFE implements Nepal NASP 2023-2025 National High-Risk Categories with SEIs; SMS360X references NASP as a State product but does not implement N-HRC.
9. Knowledge Network: SMS360X designs a de-identified cross-operator exchange; AviaSAFE has none.
10. Commercial packaging: SMS360X defines five tiers; AviaSAFE has no packaging or billing.
11. Stack: Python/FastAPI/Firebase vs TypeScript/Supabase Auth.
12. Validation: AviaSAFE runs automated tests and live UAT; SMS360X plans synthetic validation.
13. Data-quality state: AviaSAFE carries a `risk_register` dual-shape defect and 6 RLS-disabled tables; SMS360X has a clean 31-table DEV baseline but no runtime data.

---

# 6. Neutral observations

- The two projects appear to be at opposite ends of the same lifecycle: AviaSAFE is an implemented operational/compliance platform with known gaps; SMS360X is an architecture for an intelligence platform with no runtime. Comparing them as peers would overstate SMS360X's readiness and understate AviaSAFE's delivery.
- They are complementary as much as competing: AviaSAFE holds the operational workflow and live regulator surfaces, SMS360X holds the intelligence productisation, governance hierarchy, and privacy-preserving data-export model.
- Both share the same unresolved market bottleneck: confidential/voluntary reporting and audit-grade state performance persistence. AviaSAFE lists confidential reporting as one of its 7 missing compliance rows; SMS360X lists Voluntary Safety Reports as a source category but has not implemented the protection workflow.
- Both share the same technical bet (Postgres/Supabase + RLS) and the same institutional context (Nepal/CAAN), which makes a convergence or migration path technically plausible (inference, not a recommendation).

---

# 7. Confidence and limitations

- This evaluation is based on repository files only. No database, running service, or test suite was executed.
- AviaSAFE's status counts are self-assessed contract-derived figures, not independently audited (`aviasafesms/COMPLIANCE_MATRIX.md`).
- SMS360X's status percentages are self-reported (`sms360x/docs/PROJECT-STATUS.md`).
- Several aviasafesms documents referenced by its README (for example `docs/ARCHITECTURE.md`) were not present on disk during this review; findings rely on the root-level reports and code that are present.
- Term-frequency checks (Appendix B) are indicative, not exhaustive: they show whether a concept is named, not whether an equivalent capability exists under another name.

---

# Appendix A — Source index

SMS360X:
- `README.md`, `SMS360X-PRODUCT-VISION.md`, `OIP-OPERATOR-INTELLIGENCE-PACK-SPECIFICATION.md`, `VALIDATION-SUCCESS-CRITERIA.md`, `ROADMAP.md`, `SAFETY-CASE-LIBRARY.md`, `SYNTHETIC-*.md`, `TASK-033A-ARCHITECTURE-DECISIONS.md`, `COPILOT-TASK-034..040.md`
- `docs/SMS360X-CONSTITUTION.md`, `docs/PROJECT-STATUS.md`, `docs/DECISIONS.md`, `docs/DATA-MODEL.md`, `docs/BARRIER-MODEL-ENHANCEMENT.md`, `docs/PERSISTENCE-ARCHITECTURE.md`, `docs/ADR-001..008`, `docs/RLS-IMPLEMENTATION-DESIGN-V1.md`, `docs/SOURCE-DATA-CATALOG-AND-ARCHITECTURE-REPORT.md`
- `lib/**`, `types/sms360x.ts`, `supabase/migrations/20261006110352_initial_sms360x_schema_v1.sql`, `supabase/migrations/2026100711*`

AviaSAFE:
- `README.md`, `COMPLIANCE_MATRIX.md`, `DISCOVERY_REPORT.md`, `RBAC_MODEL.md`, `DASHBOARD_CONTRACT.md`, `IMPLEMENTATION_ROADMAP.md`, `ROADMAP.md`, `SECURITY_REVIEW.md`, `SCHEMA_RECONCILIATION_PLAN.md`, `SCHEMA_DRIFT_REPORT.md`, `DB_VERIFICATION.md`, `docs/status.md`, `MODULE_A_CONTRACT.md`, `MODULE_B_CONTRACT.md`, `MODULE_C_CONTRACT.md`
- `backend/app/**`, `backend/tests/**`, `supabase/migrations/**`

---

# Appendix B — Concept term check (indicative)

Counts are substring matches across each repository's text files (documentation, Python, SQL, TypeScript, JavaScript), excluding dependencies and build caches.

| Concept | SMS360X hits | AviaSAFE hits |
|---|---|---|
| NASP | 57 | 46 (all in N-HRC/NASP reference context) |
| OIP | 173 | 0 |
| Knowledge Network | 110 | 0 |
| Risk-Based Oversight (exact) | 26 | 0 |
| RBO | 73 | 0 (case-sensitive) |
| Nano-Code | 36 | 0 (has "nanocode"/HFACS nanocodes: 111) |
| M14 | 22 | 0 |
| Operator Intelligence | 41 | 0 |
| PSOE | 0 | present (Module C) |
| CAN/CAP | 0 | present (Module B) |
| SPI | 144 | present |
| SPT | 78 | present |
| Doc 9859 | 25 | 70 |
| Doc 10159 | 25 | 37 |
| Annex 19 | 32 | 121 |
| ADREP | 121 | 176 |
| HFACS | 125 | 177 |

Interpretation: AviaSAFE is heavily weighted to procedural/regulatory references (Annex 19, Doc 9859, ADREP, HFACS, CAAN); SMS360X is heavily weighted to its intelligence-product vocabulary (OIP, Knowledge Network, RBO, Operator Intelligence, Nano-Code, M14). Both reference NASP and N-HRC, but only AviaSAFE implements N-HRC.

---

*End of Project Evaluation Report.*
