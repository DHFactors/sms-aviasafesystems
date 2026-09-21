# MODULE_C_CONTRACT.md — State Regulator / SDCPS / PSOE Module

AviaSAFE SMS Platform — Module C Specification
Status: DRAFT COMPLETE — pending implementation (Chunks 3a-3c)
All three chunks delivered; no further chunks planned for Module C.

Base of analysis: `data/an19_cons (4).pdf` (Annex 19 Third Edition, applicable
26/11/26), `data/ICAO Doc 10159 based Turning Data in Decisions.pdf`, and the
current codebase. Every code claim cites `file:line`. Module C is owned by the
State Regulator (CAAN). Chunk 3a covered Overview, SDCPS aggregation (§5.2)
and State-level safety intelligence (§5.3). Chunk 3b covers PSOE, data
protection (§5.4/App 3), safety information sharing (§5.5), and the accepted
decisions Q1-Q7 (aggregation storage, taxonomy, SPI/SPT, trend baseline,
analysis levels, CAAN hazard visibility). Chunk 3c covers the Module C
Compliance Matrix (§13) and the contract sign-off (§14), and finalizes Schema
Notes SN-C5..SN-C10. The Regulator dashboard UI is deferred to the
Dashboard contract (§14, next steps).

---

## 1. OVERVIEW
**Purpose.** Module C is the SDCPS-aligned state-level safety intelligence
layer. It aggregates anonymized aggregate data from Module A (surveys) and
Module B (hazards, risks, CAN/CAP), computes national-level safety metrics
(state SPIs, national hazard categories, state risk register), powers the
State Regulator dashboard (chunk 3c), and feeds CAAN oversight of operators'
SMSs per the Safety Intelligence Manual (Doc 10159). Component "PSOE"
(Post-certification Safety Oversight Evaluation) is Module C-owned but
deferred to chunk 3b.

**Ownership.** State Regulator (CAAN). Role `CAAN_SMD` maps to scope
`regulator` (`core/rbac.py:55`); `CROSS_TENANT_ROLES = ["CAAN_SMD",
"SUPER_ADMIN"]` (`core/config.py:147`); `TENANT_WIDE_ROLES` includes both
(`config.py:161`). Regulator authorities are the module's external recipients
(`Regulator` table `db_models.py:1579`; API `/api/v1/regulators` via
`settings.API_PREFIX_REGULATORS` `config.py:46`).

**Compliance anchor.**
- Annex 19 Third Edition Chapter 5 "Development of safety intelligence"
  (`data/an19_cons (4).pdf`): §5.2 SDCPS; §5.3 safety data and safety
  information analysis; §5.4 safety data and safety information protection
  (Appendix 3); §5.5 safety information sharing and exchange.
- Cross-referenced: §3.3.4 (State-level hazard identification), §3.4.2.1
  (States shall establish safety performance indicators), and Doc 10159
  (Data→Information→Intelligence, the Safety Intelligence Cycle, D3M,
  descriptive/diagnostic/predictive/prescriptive analysis).

**Boundaries (critical rule).** Module C is READ-ONLY against Modules A and B.
Existing consumers comply: `AggregationService`, `SPIService`, `NHRCService`,
`StateRiskService` all read `hazards`, `reports`, `cans/caps`,
`flight_diversions`, `Survey` (maturity aggregates) and never write to them.
- No writes to Module A or Module B tables anywhere in Module C code under
  this contract.
- Module C never sees tenant-identifiable Module A survey responses — only
  aggregate maturity (`AggregationService._latest_maturity`,
  `aggregation_service.py:35-66` reads `overall_sms_maturity` + the 4
  component scores, never raw responses).
- Aggregation vs. raw: Module B hazard/risk counts may reach the Regulator at
  hazard level only where CAAN's oversight mandate requires it (Annex 19
  §5.2.5 — SSP authorities shall have access to safety data); cross-tenant
  data is aggregated or anonymized (see §2, §3).

**Module ownership (from the modularization plan).**
- Module A: surveys (MODULE_A_CONTRACT.md).
- Module B: hazards/risks/CAN/CAP, per-tenant MOR/VSR and quarterly/annual SSP
  reports (MODULE_B_CONTRACT.md §30; `RegulatoryReport` `db_models.py:1047`).
- Module C: `state_risk_register` (`db_models.py:866`), `state_risk_categories`
  (`db_models.py:1816`), `psoe_*`, `regulatory_reports`, `caan_reports`
  (`db_models.py:1767`) — see DISCOVERY_REPORT.md:211. `caan_reports` is
  written by the tenant-side flow (`routes/reporting.py:72`) as a CAAN snapshot
  and read by Module C; Module C itself writes only its own tables.

**Interfaces.**
- To Module A: pulls per-tenant SMS health/maturity aggregates (survey-level
  only) — `aggregation_service.py:98-142`; `spi_service.py:116` (SPI
  "SMS Maturity Survey"); `dashboard_service.py` CAAN maturity assessment
  (`routes/dashboard.py:365-372`).
- To Module B: pulls per-tenant hazard/risk/CAN/CAP aggregates —
  `aggregation_service.py:144-210`; `spi_service.py` snapshots (hazards,
  reports VSR/MOR, CAN/CAP, diversions; `spi_service.py:7,402-410`);
  `state_risk_service.py:357-372` (`_cross_tenant_hazards`/`_cross_tenant_reports`).
- To the State Regulator dashboard: `routes/regulator_dashboard.py`
  (prefix `/api/v1/regulator`, `main.py:286`) + `/api/v1/spi` state +
  `/api/v1/nhrc` state + `/api/v1/state-risk`. Dashboard UI itself is chunk 3c.
- To CAAN external systems: weekly SSP dispatch (PDF by email) —
  `lifecycle.py:26-35`; `workers/scheduler.py:25-164`.

**Open questions (overview).**
- Q0 — Scope of "regulator access": which Module B fields at hazard level may
  CAAN see (agent, system, CATS codes) vs. only risk-level aggregates?
  UNKNOWN — NEEDS HUMAN INPUT (regulator 3b will lean on this).

---

## 2. SDCPS AGGREGATION (Annex 19 §5.2)
**Purpose.** Establish the State safety data collection and processing system
as the mandated aggregation layer, and document what exists today.

**Compliance anchor.**
- §5.2.1: "States shall establish a safety data collection and processing
  system (SDCPS) consisting of a series of integrated processes and schemes to
  capture, store, aggregate, process and enable the analysis of safety data
  and safety information." (Note 2: guidance in Doc 10159.)
- §5.2.2: SDCPS based on both proactive and reactive methods of collection.
- §5.2.3: mandatory safety reporting systems shall be incorporated.
- §5.2.4: States shall establish a voluntary safety reporting system.
- §5.2.5: SSP implementation authorities shall contribute to and have access
  to SDCPS data.
- §5.2.6: SDCPS shall use a taxonomy aligned with standardized taxonomies to
  (a) identify hazards at State level (per §3.3.4), (b) compare data
  consistently, (c) enable sharing/exchange (§5.5).
- §5.2.7 (Recommendation): governance of safety data and safety information.

**Current implementation.**

CAPTURE — mandatory & voluntary (§5.2.3, §5.2.4):
- Mandatory: MOR/VSR occurrences live in `reports`
  (`db_models.py:158`; MOR `report_type='mandatory'`, VSR voluntary —
  `routes/occurrence_reports.py:115-150` per Module B §30). CAAN copy:
  `caan_reports` snapshot upsert (`routes/reporting.py:72`; model
  `db_models.py:1767`, includes `is_anonymous`).
- Voluntary: VSR (`spi_service.py:44` "VSR Reports"; `calculate_vsr_rate`
  `spi_service.py:173-177`) and Module A surveys (maturity — never raw
  responses, `aggregation_service.py:35-66,98-118`).
- Proactive/reactive mix (§5.2.2): reactive from MOR/VSR/diversions
  (`FlightDiversion` `db_models.py:717`); proactive from hazard registration
  (Module B §3) and surveys. PARTIAL — reactive is explicit, proactive is
  hazard-registration + survey activity only (no separate proactive collection
  schemes).
- Taxonomy (§5.2.6): hazards carry `adrep_category` (Module B SN2; taxonomy in
  `models/hazard.py:23`); State layer classifies to ICAO/NASP categories —
  `icoc_category` on `state_risk_register` (`db_models.py:866-909`), 7 N-HRC
  national categories (`models/nhrc.py:12-25`), `state_risk_categories`
  seeded with `icao_reference` (`db_models.py:1816`;
  `state_risk_service.py:89-101`). PARTIAL — three parallel taxonomy devices
  (ADREP / ICAO / N-HRC) not unified.

STORE (§5.2.1): live Module A/B tables (owned by A/B), Module C tables
(`state_risk_register`, `state_risk_categories`, `regulatory_reports`,
`caan_reports`), plus `sms_maturity` (DB_VERIFICATION.md:106,172). IMPLEMENTED.
Note RLS: `state_risk_register` RLS enabled; `caan_reports`, `sms_maturity`,
`state_risk_categories` RLS disabled (DB_VERIFICATION.md:181-182).

AGGREGATE / PROCESS / ENABLE ANALYSIS (§5.2.1):
- `AggregationService` — anonymized industry averages (maturity), top hazards,
  risk trends, anonymized state "risk register" (High/Very High hazards),
  benchmarking; min-3-tenants guard; operators exposed only as
  `Operator-N`. `aggregation_service.py:120-142,144-164,166-187,189-210,
  212-232`. IMPLEMENTED (breadth partial: no CAN/CAP aggregation in this
  service).
- `StateRiskService.aggregate_state_risk` — per-ICAO-category state current
  risk index (counts, Level II-IV tier counts, avg severity/probability,
  1-25 index, SSP target, contributing tenant slugs)
  `state_risk_service.py:153-275`; persisted by
  `sync_register_from_aggregation` `state_risk_service.py:277-330`.
  IMPLEMENTED.
- `SPIService.get_state_values/get_state_status` — 8 SPIs aggregated across
  all operators `spi_service.py:303-358` (definitions `spi_service.py:21-118`).
  IMPLEMENTED.
- `NHRCService.calculate_state_nhrc_kpis` — 7 national high-risk categories
  state KPIs `nhrc_service.py:280-286`; mapping engine
  `nhrc_service.py:171-265`. IMPLEMENTED.
- Weekly SSP dispatch to authorities — `lifecycle.py:26-35,86-99` (Monday
  02:00 NPT); `workers/scheduler.py:25-65` (authorities from `Regulator`
  `scheduler.py:151-163`), per-authority: `aggregate_state_risk`
  `scheduler.py:76`, report payload `scheduler.py:78-95`, PDF
  `CaanPdfGenerator.build_ssp_report_pdf` `scheduler.py:97`, dispatch audit
  `scheduler.py:100-109`, email `scheduler.py:126-137`. IMPLEMENTED.

GOVERNANCE (§5.2.7 Recommendation): MISSING. No data-governance layer;
RBAC middleware does not guard PSOE/SPI/N-HRC/state-risk/sdc/copilot paths
(DISCOVERY_REPORT.md:61), backend module3=`/safety,/dashboard` vs frontend
module3=PSOE mismatch (DISCOVERY_REPORT.md:256,343); state-risk aggregate is
duplicated (`routes/state_risk.py:48,58` vs `api/v1/state_risk.py:19-52`;
DISCOVERY_REPORT.md:254).

**Status summary.**

| §5.2 element | Status | Evidence |
|---|---|---|
| Capture — mandatory (§5.2.3) | IMPLEMENTED | `occurrence_reports.py:115-150`; `db_models.py:158` |
| Capture — voluntary (§5.2.4) | IMPLEMENTED | VSR `spi_service.py:173-177`; Module A surveys (aggregates only) |
| Capture — proactive+reactive (§5.2.2) | PARTIAL | reactive explicit; proactive = hazard reg + surveys only |
| Taxonomy consistency (§5.2.6) | PARTIAL | ADREP/ICAO/N-HRC parallel (see above) |
| Store (§5.2.1) | IMPLEMENTED | live + Module C tables + `caan_reports` snapshot |
| Aggregate/process (§5.2.1) | IMPLEMENTED | AggregationService + StateRisk + SPI + N-HRC state |
| Enable analysis (§5.2.1/§5.3) | PARTIAL | descriptive only; diagnostic limited; predictive/prescriptive MISSING |
| SSP authorities access (§5.2.5) | PARTIAL | weekly SSP email dispatch only; no on-demand authority access |
| Governance (§5.2.7 rec) | MISSING | see governance note |
| Protection (§5.4 / App 3) | PARTIAL | see §2.5 below |

**Gaps.** (1) Analytics breadth — no CAN/CAP or report-recovery state
aggregation in `AggregationService`; (2) State SPI trend is a placeholder
(`spi_service.py:343,352` — `previous_value == value`, `trend = "stable"`);
(3) `api/v1/state_risk.py:46-50` aggregate payload hard-codes `spi_metrics: []`,
`total_reports/cans: 0`, `industry_risk_index: null`; (4) no governance
(5.2.7); (5) no on-demand authority access path (only scheduled email); (6)
protection gaps (RLS + identifier exposure).

**Specification — SDCPS aggregation layer (binding once accepted; PENDING).**
- SDCPS-1: Module C reads Modules A/B only via read-only queries; a Module C
  `sdcps` service is the single aggregation facade (wrapping the existing
  Aggregation/SPI/N-HRC/StateRisk services, or consolidating them).
- SDCPS-2: capture feeds enumerated: `reports` (MOR/VSR),
  `flight_diversions`, `hazards`, `cans/caps`, Module A maturity aggregates,
  `caan_reports` snapshot, `regulatory_reports` (per-tenant SSP).
- SDCPS-3: aggregation enforces: min-N-tenant disclosure rule (currently 3,
  `aggregation_service.py:121`), operator anonymization (`Operator-N`,
  `aggregation_service.py:108`), and CAAN-only access for any
  tenant-identifying field.
- SDCPS-4: taxonomy resolution map (ADREP ↔ ICAO `icoc_category` ↔ N-HRC) is
  documented and maintained in one place; final national taxonomy is a
  decision (Q4).
- SDCPS-5: aggregation output — national SPI values/status (existing 8),
  N-HRC state KPIs (existing 7), state risk register by ICAO category
  (existing), industry maturity averages (existing), plus CAN/CAP closure at
  State level (new, feeds §3).
- SDCPS-6: periodic sync: weekly SSP dispatch (existing cadence) refreshes a
  Module C materialized aggregate snapshot so the Regulator dashboard reads a
  stable table rather than live per-call cross-tenant scans
  (mirrors `state_risk_register` sync `state_risk_service.py:277-330`).
  New tables: DECISION NEEDED (Q2).
- SDCPS-7: governance — Module C routes gated by CAAN_SMD role uniformly; a
  `data_governance` record (policy, retention, access list) to satisfy §5.2.7.
- SDCPS-8: protection — see §2.5.

**Interface (SDCPS).**
- Reuse: `/api/v1/regulator/{industry-averages,top-hazards,risk-trends,
  risk-register,benchmark/{id},export/pdf,export/excel}`
  (`routes/regulator_dashboard.py:26-94`); `/api/v1/state-risk/{aggregate,
  export-pdf,dispatch-email,audit-logs}` (`api/v1/state_risk.py:19-155`);
  `/api/v1/spi/state/{values,status}`; `/api/v1/nhrc/state/kpis`;
  `/api/v1/dashboard/caan/benchmark` (`routes/dashboard.py:365-372`).
- Services: `AggregationService` (`aggregation_service.py:13`),
  `StateRiskService` (`state_risk_service.py:104`), `SPIService`
  (`spi_service.py:139`), `NHRCService` (`nhrc_service.py:231`),
  `ScheduledReportWorker` (`workers/scheduler.py:18`).
- Data models: `state_risk_register` (`db_models.py:866`),
  `state_risk_categories` (`db_models.py:1816`), `caan_reports`
  (`db_models.py:1767`), `Regulator` (`db_models.py:1579`).

**Data protection requirements (§5.4 / Appendix 3).**
- §5.4.1 — protection for voluntary-reporting-derived data; §5.4.2 (rec) —
  extend to mandatory-derived data; §5.4.3 — data shall NOT be made
  available/used for purposes other than maintaining or improving safety,
  unless a §4.3 principle-of-exception applies per Appendix 3; §5.4.4 —
  preventive/corrective/remedial safety actions are never prevented.
- Current exposure: `caan_reports`, `sms_maturity`, `state_risk_categories`
  have RLS DISABLED (DB_VERIFICATION.md:181-182); benchmark exposes
  `tenant_id` (`aggregation_service.py:226`); `state_risk_register` stores
  `contributing_tenants` slug list (`state_risk_service.py:268`).
- Requirements (PENDING): RLS review for Module C tables; audit-log every
  CAAN read of any tenant-identifying field; protection-condition labels on
  shared artifacts (per §5.5.1) and a use-limitation statement in dispatch
  emails/PDFs; keep `Operator-N` anonymization and the min-3 rule.

**Open questions (§2).**
- Q1 — Hazard-level visibility: does CAAN need hazard-level (title, category,
  risk index) visibility across operators, or category-aggregates only?
  (Current: truncated 50-char titles in `aggregation_service.py:201`.)
  DECISION NEEDED for 3b.
- Q2 — Materialized aggregates: new Module C tables (e.g. `state_spi_values`,
  `state_snapshot`) vs compute-on-read. DECISION NEEDED (mirror
  `state_risk_register` precedent).
- Q3 — Sharing (§5.5.1/§5.5.2): to which authorities/partners, and under which
  Appendix 3 agreements? Currently only CAAN SSP email.
  UNKNOWN — NEEDS HUMAN INPUT.
- Q4 — National taxonomy: single source of truth (ADREP vs ICAO vs N-HRC) or
  explicit 3-way map? DECISION NEEDED (ties to Module B SN2).

---

## 3. STATE-LEVEL SAFETY INTELLIGENCE (Annex 19 §5.3 and Doc 10159)
**Purpose.** Specify the State-level analysis processes: State SPIs, national
hazard identification (anonymized), benchmark logic (airline vs national
average), trend analysis (period-over-period), and the
Data→Information→Intelligence progression toward safety intelligence.

**Compliance anchor.**
- §5.3.1: "States shall establish and maintain processes to analyse safety
  data and safety information from the SDCPS," supporting (a) development of
  safety performance indicators (per §3.4.2.1), (b) identification of hazards
  at the State level (per §3.3.4), (c) identification of existing practices
  and operational strategies that resulted in positive safety outcomes, and
  (d) development of safety intelligence.
- Doc 10159 (Safety Intelligence Manual, summary in `data/ICAO Doc 10159
  based Turning Data in Decisions.pdf`): Data→Information→Intelligence;
  Safety Intelligence Cycle; D3M (Data-Driven Decision-Making);
  descriptive/diagnostic/predictive/prescriptive analysis. (Page-level text
  not extracted this session — see UNKNOWNs.)

**Current implementation.**
- State SPIs (§5.3.1a): 8 SPI definitions (`spi_service.py:21-118` — 4
  leading, 4 lagging, incl. MOR Occurrence Rate `spi_service.py:71-81`,
  Hazard Identification Rate `spi_service.py:22-33`, Safety Culture Maturity
  `spi_service.py:106-117`). State values/status: `SPIService("state")`
  `get_state_values` `spi_service.py:303-320`, `get_state_status`
  `spi_service.py:322-358`. Status via thresholds `get_status`
  `spi_service.py:364-385`. IMPLEMENTED.
- State hazard identification (§5.3.1b): (i) ICAO-category risk index with
  tolerability tiers — `state_risk_service.py:153-275` (classify
  `_classify` `:374`, tolerability normalize `:420`); (ii) N-HRC 7-category
  mapping + state KPIs — `nhrc_service.py:171-265,280-286`; (iii) aggregated
  top categories — `aggregation_service.py:144-210`. IMPLEMENTED (aggregate
  level; anonymized per §2).
- Positive safety outcomes (§5.3.1c): MISSING — no endpoint/service identifies
  practices/strategies with positive outcomes.
- Safety intelligence (§5.3.1d): MISSING — `insights`/`recommendations` in the
  state aggregate payload are hard-coded empty lists
  (`api/v1/state_risk.py:49-50`; `workers/scheduler.py:90,94`).
- Benchmark (airline vs national): maturity-level only —
  `get_benchmarking` `aggregation_service.py:212-232` (operator score vs
  industry average; returns `tenant_id` `:226`); dashboard
  `get_caan_benchmark` reads the persisted register
  `dashboard_service.py:1014-1029` with `_state_benchmark`
  `dashboard_service.py:1031-1084` (top-5 state risks, `ssp_target_avg` vs
  `ssp_actual_avg`). PARTIAL — no SPI-level or hazard-level benchmark.
- Trend analysis (period-over-period): tenant SPI trend real (month buckets —
  `get_tenant_trend` `spi_service.py:277-301`; `_month_buckets`
  `spi_service.py:632-648`); STATE SPI trend is a PLACEHOLDER (`previous_value
  == value`, `trend = "stable"` `spi_service.py:343,352`); state register
  trend is a simple prior-entry compare (`_trend`
  `state_risk_service.py:430-439`). PARTIAL.

**Gaps against §5.3 and Doc 10159.**
- No diagnostic analysis output (drivers: N-HRC contributing factors exist
  `nhrc_service.py:301-308` but no State diagnostic report).
- No predictive analysis (no forecasting/trend extrapolation).
- No prescriptive analysis (no risk-reduction recommendations; SSO/SSP action
  items out of scope for now).
- No state tip-per the aggregate board SPI `spi_metrics`, no period-over-period
  state SPI trend, no target-set management at State level
  (`update_spi_targets` returns a count but does NOT persist
  `api/v1/spi.py:129-142` — UNKNOWN to verify in 3b).
- No positive-outcome identification (§5.3.1c).
- No State benchmark for the 7 hazard SPIs / N-HRC KPIs (only maturity).

**Specification — State-level safety intelligence (binding once accepted;
PENDING).**
- SLI-1 — State SPI computation: the existing 8 SPI definitions remain the
  State SPI set (`spi_service.py:21-118`); each is computed at State level by
  summing operator-level numerators/denominators (never averaging of
  averages) per `get_state_values` `spi_service.py:303-320`; status vs SSP
  target; period-over-period trend derived from the materialized snapshot
  (SDCPS-6) — replaces the `stable`/`previous_value==value` placeholder
  (`spi_service.py:343,352`).
- SLI-2 — National hazard identification (anonymized): output = N-HRC 7-state
  KPIs (`nhrc_service.py:280-286`) + ICAO-category state risk register
  (`state_risk_service.py:153-275`); no operator identifier leaves Module C
  except `Operator-N` or aggregated `contributing_tenants` slug counts where
  CAAN's §5.2.5 access mandate applies (Q1).
- SLI-3 — Benchmark logic: extend `get_benchmarking`
  (`aggregation_service.py:212-232`) and `get_caan_benchmark`
  (`dashboard_service.py:1014-1029`) to SPI and N-HRC KPIs — operator value
  vs national average vs SSP target, with min-3-tenant statistical guard
  (Q8); maturity benchmark stays as-is.
- SLI-4 — Trend analysis: month/quarter buckets (pattern of
  `get_tenant_trend` `spi_service.py:277-301`) applied at State level per SPI;
  state risk register trend kept as prior-entry compare
  (`state_risk_service.py:430-439`); output feeds the Regulator dashboard
  (3c).
- SLI-5 — Diagnostic: State report of top contributing factors per N-HRC
  (`nhrc_service.py:301-308`); tolerability-tier distribution per ICAO
  category (`state_risk_service.py:199-207,420-429`).
- SLI-6 — Safety intelligence (§5.3.1d): the `insights`/`recommendations`
  blocks (`api/v1/state_risk.py:49-50`; `scheduler.py:90,94`) become the
  D3M decision-support output of SLI-1..SLI-5 (descriptive→diagnostic→
  prescriptive). Predictive is a future chunk — DECISION OUTSTANDING (Q7).
- SLI-7 — Positive outcomes (§5.3.1c): register of practices yielding
  positive outcomes (out-of-scope for 3b implementation; spec drafted only).
- SLI-8 — SPI targets: State-level SPT registry (reuse per-tenant
  `update_spi_targets` semantics `api/v1/spi.py:129-142`; persist to a Module
  C table — Q5/Decision).

**Interface (State intelligence).**
- Reuse: `/api/v1/spi/state/values`, `/api/v1/spi/state/status`
  (`api/v1/spi.py:97-126`); `/api/v1/nhrc/state/kpis`
  (`api/v1/nhrc.py:35-43`); `/state-risk/aggregate`,
  `/state-risk/export-pdf`, `/state-risk/dispatch-email`
  (`api/v1/state_risk.py:19-143`); `/api/v1/dashboard/caan/benchmark`
  (`routes/dashboard.py:365-372`; service `dashboard_service.py:1014-1084`);
  `/api/v1/regulator/benchmark/{tenant_id}`
  (`routes/regulator_dashboard.py:64-72`).
- Services: `SPIService` (`spi_service.py:139`), `NHRCService`
  (`nhrc_service.py:231`), `StateRiskService` (`state_risk_service.py:104`),
  `AggregationService` (`aggregation_service.py:13`), `DashboardService`
  (`dashboard_service.py`).
- Data models: `state_risk_register` (`db_models.py:866`),
  `state_risk_categories` (`db_models.py:1816`), SPI/N-HRC model classes
  (`models/spi.py`, `models/nhrc.py`), `caan_reports` (`db_models.py:1767`).

**Open questions (§3).**
- Q5 — State SPT source: a new Module C State-SPT table, or reuse built-in
  SPI `target_value` (`spi_service.py:29,77`...)? DECISION NEEDED for 3b.
- Q6 — State trend baseline: comparison window (last quarter vs prior
  quarter; trailing 12 months) and min-history before trend is shown?
  DECISION NEEDED.
- Q7 — Predictive/prescriptive scope: any forecasting/ML acceptable in
  Module C? UNKNOWN — NEEDS HUMAN INPUT.
- Q8 — Statistical benchmark basis: keep min-3 (`aggregation_service.py:121`);
  require margin/thresholds? DECISION NEEDED.

---
## 4. PSOE (POST SAFETY OVERSIGHT EVALUATION)

**Purpose.** CAAN-led, state-level periodic evaluation of each operator's SMS,
meeting Annex 19 §3.4.1.3(a) ("periodically assess the SMS of service
providers"). Scores and findings become Module C state input alongside SPI/N-HRC.

**Compliance anchor.**
- §3.3.2.1: States shall require listed service providers (operators of
  aeroplanes/helicopters in international commercial air transport, ATS,
  certified aerodromes/heliports, approved maintenance orgs, type design, etc.)
  to implement an SMS (`data/an19_cons (4).pdf`, §3.3.2).
- §3.4.1.2: prioritize surveillance toward areas of greater safety concern.
- §3.4.1.3: mechanisms to (a) periodically assess the SMS of providers;
  (b) monitor their safety performance.
- Doc 10159 (state oversight) and Doc 9859 (SMS assessment guidance — §1.3.4.3
  "periodic assessments"; see doc9859 extract; task brief §8 reference noted,
  exact Doc 9859 heading UNKNOWN — NEEDS HUMAN INPUT, confirm in 3c).

**Current implementation.**
- Tables (all RLS enabled — `DB_VERIFICATION.md:160-162`):
  - `psoe_assessments` (`PsoeAssessment` `db_models.py:918`): tenant-bound
    `tenant_id` `:922`; `status` default `'draft'` `:925`; `responses` JSONB
    `:935`; `component_scores` JSONB `:936`; `overall_score_pct` `:937`;
    `overall_level` `:938`; `template_version` `:933`; `is_demo` `:941`.
  - `psoe_questions` (`PsoeQuestion` `:970`): GLOBAL 21-question reference (no
    `is_demo` — deliberate, `:973-976`); `component` CHECK (Safety Management /
    Risk Management / Safety Assurance / Safety Promotion) `:964-967`;
    `question_number` UNIQUE per component `:989`; counts 4×(5/5/6/5)
    (`api/v1/endpoints/psoe.py:140`).
  - `psoe_findings` (`PsoeFinding` `:1007`): `finding_type` CHECK
    (Observation/Finding/Major Finding/Critical Finding) `:997-1000`; `status`
    CHECK (open/in_progress/closed) `:1002-1004`; FK assessment CASCADE `:1014`.
- Services:
  - `psoe_complete_service.py` (PG/Supabase, current): categorical scoring
    (Compliant / Partially Compliant / Non-Compliant / Not Applicable)
    `:9-11,44-45`; `COMPONENT_ORDER` `:37-42`; `_score` (component percentages
    → overall → Level 1-5) `:600-631`; `generate_report` HTML `:454-552`;
    findings CRUD `:347-452`; complete/calculate `:311/:243`.
  - `psoe_service.py` (legacy Firestore — "intentionally untouched"
    `psoe_complete_service.py:19-21`): Appendix 10 template JSON
    `:18-19`; CAAN/ICAO 0-3 implementation scale `:28-31,40-46`; weights
    10/40/30/20 `:33-36`; `compute_component_scores` `:97-127`;
    `compute_overall` `:130-140`; `overall_level` `:143-151`.
- Routes:
  - Current: `/api/v1/supabase/psoe/*` (`api/v1/endpoints/psoe.py:45`;
    mounted `api/v1/router.py:10,21`) — GET `/questions` `:138`; `/assessments`
    list/create/get/save/calculate/complete/report `:152-237`; findings
    add/update/delete `:244-280`. Access: `CAAN_SMD`/`CAAN_ADMIN`/`CAAN_AUDITOR`/
    super admin full (`_EDIT_ROLES` `:49-52`); regulator cross-tenant via
    `_resolve_scope` `:96-113`; AM/SM view-only (docstring `:23-26`).
  - Legacy: `/api/v1/psoe` + `/api/psoe` (`config.py:50,63`; `main.py:280-281`;
    `routes/psoe.py`) — `/template` `:110`; `/assessments` `:123,179,245,279`;
    `/assessments/{id}/export` `:644`.
- Status: **IMPLEMENTED** (dual track — legacy numeric + current categorical).

**Gaps (MISSING / PARTIAL).**
- G-4.1 Two coexisting scoring engines (numeric `psoe_service.py` vs
  categorical `psoe_complete_service.py`) — one must bind.
- G-4.2 PSOE scores not fed into Module C state aggregation (no SPI/N-HRC/
  industry-averages integration).
- G-4.3 Findings standalone — no linkage to Module B action items / CAN/CAP.
- G-4.4 No periodicity model for §3.4.1.3 "periodically" (assessment_date is a
  manual field, `db_models.py:930-932`; no recurrence/scheduling).
- G-4.5 Relationship between PSOE (categorical) and Module A SMS maturity
  survey (numeric) undocumented.

**Specification (binding once accepted; PENDING IMPLEMENTATION).**
- PSOE-1: **categorical track binds** (`psoe_complete_service.py:600-631`:
  Compliant/Partially/Non/Not Applicable; N/A excluded; Level 1-5). Numeric
  `psoe_service.py` retained only as legacy export until deprecated (Q4.1).
- PSOE-2: the 21-question `psoe_questions` questionnaire is the binding
  instrument (4× 5/5/6/5, `api/v1/endpoints/psoe.py:140`).
- PSOE-3: per-assessment findings per `psoe_findings` lifecycle
  (`db_models.py:997-1004`); optional linkage columns to Module B
  actions/CAN/CAP (Q4.1, coordinated with Module B).
- PSOE-4: periodic assessment — one assessment per tenant per surveillance
  cycle; status lifecycle draft→in_progress→submitted→completed→closed
  (`models/psoe.py:111`); a periodicity registry is future (Q4.2).
- PSOE-5: integration — overall Level 1-5 feeds state aggregation as a
  per-tenant SMS-effectiveness component (aligns with SPI "Safety Culture
  Maturity" `spi_service.py:106-117`); landing surface = Regulator dashboard
  (3c).
- PSOE-6: report = `generate_report` HTML (`psoe_complete_service.py:454-552`);
  legacy `/export` kept (`routes/psoe.py:644`).

**Interface.** Endpoints: `/api/v1/supabase/psoe/*` (current),
`/api/v1/psoe/*` (legacy). Services: `psoe_complete_service.py`,
`psoe_service.py`. Data models: `psoe_*` tables (`db_models.py:918-1035`),
`models/psoe.py`.

**Open questions.**
- Q4.1 — Deprecate the numeric track? Add finding↔Module B action linkage
  columns? DECISION NEEDED (3c).
- Q4.2 — Assessment periodicity (annual cycle? per §3.4.1.2 prioritization)?
  UNKNOWN — NEEDS HUMAN INPUT.
- Q4.3 — Role that completes/closes an assessment on the CAAN side?
  DECISION NEEDED.

---
## 5. DATA PROTECTION (§5.4 + APPENDIX 3)

**Purpose.** Protect safety data, safety information and related sources per
Annex 19 §5.4 and Appendix 3, and bound what Module C may store/see.

**Compliance anchor.**
- §5.4.1: protection for data captured by, and information derived from,
  VOLUNTARY safety reporting systems (and related sources) per Appendix 3.
- §5.4.2 (Recommendation): extend that protection to MANDATORY reporting
  systems.
- §5.4.3: data "collected, stored or analysed in accordance with 5.2 or 5.3"
  shall not be made available/used for purposes other than maintaining or
  improving safety, unless an Appendix 3 principle of exception applies.
- §5.4.4: nothing prevents using the data for preventive/corrective/remedial
  action needed to maintain/improve safety.
- §5.4.5: measures, incl. positive safety culture, to encourage reporting.
- Appendix 3: principles of protection; sources = individuals and
  organizations (§5.4 note); custodian responsibilities (App 3 §1.5).

**Current implementation.**
- RLS: enabled on hazards, reports, psoe_*, state_risk_register,
  regulatory_reports, audit_logs etc. (`DB_VERIFICATION.md:181`); DISABLED on
  `caan_reports`, `sms_maturity`, `state_risk_categories`, `dead_letter_queue`,
  `sms_dispatches`, `audit_dispatches` (`DB_VERIFICATION.md:182`).
- Anonymous reporting: `reports.is_anonymous` (`db_models.py:172`).
- Confidential reporting: **MISSING** (no confidential/restricted flag on
  reports/hazards; flagged in Module B §27).
- Anonymization: `AggregationService` exposes `Operator-N`
  (`aggregation_service.py:107-114`); survey reads are maturity-aggregates only
  (`:35-66,98-118`); group rules min-3 (`:121-123,145,167,190,213`); benchmark
  returns the operator's `tenant_id` (`:226`).
- State de-identification: `state_risk_register` stores `contributing_tenants`
  slugs (`state_risk_service.py:268`) — operator-identifying at register level
  (allowed under §5.2.5 access; must be controlled).
- Audit: `audit_logs` `action` + `metadata_json` (`db_models.py:1650,1660`);
  SSP dispatch audit (`workers/scheduler.py:100-109`; `/audit-logs`
  `api/v1/state_risk.py:146-155`). No general "regulator read" audit.
- SDC-ingestion path exists (`routes/sdc.py:171,250` validate/ingest;
  `main.py:283`) — ingestion-side capture aligned to SDCPS.

**Gaps (MISSING / PARTIAL).**
- G-5.1 Confidential reporting class MISSING.
- G-5.2 `caan_reports`/`sms_maturity`/`state_risk_categories` RLS disabled.
- G-5.3 No data-classification labels on stored artifacts.
- G-5.4 No general regulator-read audit (only dispatch audits).
- G-5.5 Reporter identity (non-anonymous MOR) is protectable but nothing
  enforces its exclusion from future CAAN export paths.

**Specification (binding once accepted; PENDING IMPLEMENTATION).**
- DP-1 **Classification:** public / internal / confidential / protected.
  Module C aggregate outputs = internal; raw hazard/report data at CAAN =
  protected (App 3); reporter identity = protected, always.
- DP-2 **Module C never sees** reporter identity or raw Module A survey
  responses — enforced at the service boundary (AggregationService reads only
  maturity fields; `aggregation_service.py:35-66`).
- DP-3 **Audit:** every cross-tenant read by Module C is logged
  (`audit_logs` `action="CAAN_READ_*"` + `metadata_json`, `db_models.py:1650,
  1660`); escalation reads (Q1) get dedicated records.
- DP-4 **Confidential reporting:** new confidential/restricted flag on
  reports/hazards (Module C defines the requirement; schema change coordinated
  with Module B — Section 3/SN2 ledger).
- DP-5 **De-identification for state reporting:** state outputs expose
  `Operator-N` + aggregated contributing-tenant slugs, never individual
  hazard/report source fields beyond the Q1 default set.
- DP-6 **RLS:** assess enabling RLS on `caan_reports`, `sms_maturity`,
  `state_risk_categories` or document a CAAN-owned exception
  (`DB_VERIFICATION.md:182`).
- DP-7 **Use-limitation statement** (§5.4.3) on SSP dispatch emails/PDFs and
  all `/share` outputs (currently absent).

**Interface.** `audit_logs` (`db_models.py:1646-1667`); `AggregationService`
(`aggregation_service.py:13`); `reports.is_anonymous` (`db_models.py:172`);
regulator routes (`routes/regulators.py:29,42`); SDC ingestion
(`routes/sdc.py:171,250`).

**Open questions.**
- Q5.1 — Retention/deletion for the protected class (who may purge, how long)?
  UNKNOWN — NEEDS HUMAN INPUT.
- Q5.2 — Confidential-reporting workflow: Module B (create/flag) or Module C
  (consume only)? DECISION NEEDED (Module B flagged it MISSING).

---
## 6. SAFETY INFORMATION SHARING (§5.5)

**Purpose.** Compliant sharing and exchange per §5.5, within the Q3 baseline
(CAAN→operator aggregated benchmarks now; State-to-State deferred).

**Compliance anchor.**
- §5.5.1: forward safety matters of interest to other States; agree protection
  level/conditions u/App 3 BEFORE sharing.
- §5.5.2: facilitate timely sharing/exchange; safety info used only to
  maintain/improve safety.
- §5.5.3 (Recommendation): promote sharing/exchange among service providers.
- Appendix 3: protection conditions attached to shared data.

**Current implementation.**
- Weekly CAAN SSP dispatch email to regulator authorities
  (`lifecycle.py:26-35,86-99`; `workers/scheduler.py:76-149`) — regulator-
  directed, not operator-facing sharing.
- CAAN-side benchmarking exists but is regulator-only:
  `AggregationService.get_benchmarking` (`aggregation_service.py:212-232`,
  returns operator score vs industry average + distribution) at
  `/regulator/benchmark/{id}` (`routes/regulator_dashboard.py:64-72`);
  `get_caan_benchmark` (`dashboard_service.py:1014-1029`) at
  `/dashboard/caan/benchmark` (`routes/dashboard.py:365-372`).
- NO operator-facing `/share/*` endpoints. **MISSING.**

**Gaps.** Operator cannot self-serve national-benchmark context; every share
event is not audit-trailed; State-to-State not implemented (deferred by Q3).

**Specification (Q3 baseline; binding once accepted; PENDING IMPLEMENTATION).**
- SS-1 **CAAN→operator benchmark share:** operator sees ONLY its own metrics +
  national averages/aggregates. New `/api/v1/regulator/share/benchmark/
  {tenant_id}` delegates to existing `get_benchmarking`
  (`aggregation_service.py:212-232`), gated to the operator's own tenant.
- SS-2 **Audit every share:** `audit_logs` `action="CAAN_SHARE_*"` + payload in
  `metadata_json` incl. operator + artifact + timestamp (`db_models.py:1650,
  1660`).
- SS-3 **Scope:** shares carry only the Q1 default visibility set (§12) — never
  reporter identity, never raw surveys.
- SS-4 **State-to-State: deferred** — documented future capability; requires
  App 3 protection agreements per §5.5.1 (UNKNOWN legal).
- SS-5 **Share API surface:** `/api/v1/regulator/share/*` with CAAN_SMD
  issuance + operator scoping; dashboard UI = chunk 3c.
- SS-6 **Use-limitation statement** attached to every share (per §5.5.2/App 3).

**Interface.** New endpoints `/api/v1/regulator/share/*` (spec; not yet
implemented); reuse `AggregationService.get_benchmarking`
(`aggregation_service.py:212-232`) and `_caan_reports`
(`dashboard_service.py:452`); `audit_logs`; `Regulator` (`db_models.py:1579`).

**Open questions.**
- Q6.1 — Operator benchmark channel: direct self-serve endpoint vs dashboard-
  only display? DECISION NEEDED (3c).
- Q6.2 — Which "matters of interest" auto-trigger State-to-State
  (§5.5.1)? UNKNOWN — NEEDS HUMAN INPUT.

---
## 7. AGGREGATION STORAGE (Q2)

**Purpose.** Hybrid materialization for the SDCPS aggregation layer: cheap
aggregations computed on read; expensive ones materialized.

**Compliance anchor.** §5.2.1 (SDCPS captures, stores, aggregates, processes
and enables analysis); Doc 10159 (data lifecycle). Precedent:
`state_risk_register` sync (`state_risk_service.py:277-330`) is the existing
materialization pattern (`aggregated_at` staleness `:283-284`).

**Specification (Q2 decision; binding once accepted; PENDING IMPLEMENTATION).**
- AGG-1 **Compute-on-read** (small): per-tenant counts, recent activity,
  single-tenant metrics (existing SPI tenant path `spi_service.py:236-301`;
  per-tenant dashboard).
- AGG-2 **Materialized** (expensive): national averages, state-level trend
  baselines (SN-C3 windows), cross-tenant benchmarks, state SPI status/trend.
- AGG-3 **Worker:** APScheduler job (pattern `lifecycle.py:86-99`) computes
  into `module_c_aggregates` (SN-C1); weekly alongside the weekly SSP dispatch,
  plus an on-demand refresh endpoint that invalidates and rewrites a key set.
- AGG-4 **TTL:** per `metric_type` (configurable; stale rows carry
  `computed_at` for consumers, mirroring `state_risk_service.py:283-284`).
- AGG-5 **Refresh triggers:** scheduled + on-demand; reads never force a
  heavyweight recompute.

**7.4 — Schema note SN-C1: `module_c_aggregates`.**
Columns (binding): `id` uuid PK; `tenant_id` uuid NULL (NULL = national scope);
`metric_type` text; `metric_key` text; `period_start`/`period_end` timestamptz;
`value` jsonb; `computed_at` timestamptz NOT NULL; `ttl_seconds` int NULL;
`source_version` text. UNIQUE (`tenant_id`, `metric_type`, `metric_key`,
`period_start`). RLS: national NULL-tenant rows need a CAAN-only policy or a
role gate (Q7.2). PENDING IMPLEMENTATION.

**Interface.** Materialization worker (`workers/scheduler.py` pattern helper);
writers: `AggregationService`/`SPIService`/`StateRiskService`; readers:
Regulator dashboard (3c), compare view.

**Open questions.**
- Q7.1 — Materialization cadence/weekday (weekly with SSP dispatch vs daily)?
  DECISION NEEDED.
- Q7.2 — RLS handling for national (NULL-tenant) rows: dedicated policy vs
  CAAN-only role gate? DECISION NEEDED.

---
## 8. TAXONOMY UNIFICATION (Q4)

**Purpose.** One canonical taxonomy with explicit mappings, satisfying §5.2.6
(State-level hazard identification, consistent comparison, sharing).

**Compliance anchor.** §5.2.6 (taxonomy aligned with standardized taxonomies),
Doc 10159 (taxonomy guidance incl. ADREP).

**Current implementation.**
- `hazards` carry `adrep_category` (Module B SN2; `models/hazard.py:23`);
  `reports.occurrence_type` (`db_models.py:174`).
- State layer classifies independently: `icoc_category` on
  `state_risk_register` (`db_models.py:866-909`; seeded `state_risk_categories`
  `db_models.py:1816`, read via `state_risk_service.py:89-101`); 7 N-HRC
  categories (`models/nhrc.py:12-25`) mapped by rules
  (`nhrc_service.py:171-265`).
- Live mapping tables (RLS true): `hazard_adrep_mappings`,
  `hazard_hfacs_codes`, `report_adrep_mappings`, `report_hfacs_codes`,
  `icao_adrep_taxonomies`, `hfacs_nanocodes`
  (`DB_VERIFICATION.md:125,189`); source CSVs `data/icao_adrep_taxonomies.csv`,
  `data/hfacs_nanocodes.csv`.
- Three parallel devices (ADREP / ICAO / N-HRC) not unified — the gap.

**Specification (Q4 decision: ICAO canonical; binding once accepted;
PENDING IMPLEMENTATION).**
- TX-1 **Canonical = ICAO hazard taxonomy** (Environment / Organization /
  Technical / Human grouping; cf. `models/hazard.py:23`).
- TX-2 **Mapping columns on hazards/reports:** `adrep_category` (exists on
  hazards; add to reports — verify in 3c); `occurrence_type` (exists, reports
  `db_models.py:174`); NEW `hfacs_nanocode` (hazards/reports); NEW
  `nhrc_category` (hazards; derivable via `nhrc_service.py:241-265`).
- TX-3 **Reference table `taxonomy_mappings`** (read-only, seeded): ICAO ↔
  ADREP ↔ HFACS ↔ N-HRC. Complements the live mapping tables
  (`DB_VERIFICATION.md:125`).
- TX-4 **Ownership:** CAAN owns the canonical + mappings; seeds from
  `data/icao_adrep_taxonomies.csv` / `data/hfacs_nanocodes.csv`.

**8.4 — Schema note SN-C4: taxonomy mapping strategy.**
Hybrid: new mapping columns on `hazards`/`reports` (`hfacs_nanocode`,
`nhrc_category`; `adrep_category`/`occurrence_type` retained) + read-only
`taxonomy_mappings` reference table. New columns ARE schema changes to
Module B-owned tables (hazards/reports) driven by Module C — coordinated
change required (Module B ledger SN2/§3). Adopt the six live mapping tables
into ORM (`DB_VERIFICATION.md:189`) or seed `taxonomy_mappings` from their
CSVs — recommendation: adopt for a single source of truth (Q8.1). PENDING
IMPLEMENTATION.

**Interface.** `hazards`/`reports` columns; `models/hazard.py:23`;
`nhrc_service.py:171-265`; reference tables; seed CSVs.

**Open questions.**
- Q8.1 — Add mapping columns on Module B tables (coordinated migration) vs map
  only via `taxonomy_mappings`? DECISION NEEDED.
- Q8.2 — `nhrc_category` auto-derived (service) vs stored snapshot? DECISION
  NEEDED.

---
## 9. STATE-LEVEL SPI/SPT (Q5)

**Purpose.** National-level safety performance indicators and targets.

**Compliance anchor.** §3.4.2.1 (States establish SPIs "supported by
qualitative means as needed" and SPTs "where appropriate" to measure/monitor
the State's civil aviation system) + §5.3.1(a) (SDCPS analysis supports SPI
development).

**Current implementation.**
- SPI definitions are CODE constants (`spi_service.py:21-118`), NOT a DB table.
  **Note:** the task premise "reuse the `spi_definitions` table" does NOT match
  this codebase — no such table was found (db_models/schema); flag for 3c
  decision (Q9.1).
- State SPI values/status computed on read (`get_state_values` `:303-320`;
  `get_state_status` `:322-358`).
- SPT editing is a per-tenant, NON-persisting stub (`api/v1/spi.py:129-142`;
  returns `count` only — no DB write seen). No State SPT exists.

**Specification (Q5 decision: new State-SPT table; binding once accepted;
PENDING IMPLEMENTATION).**
- SPT-1 New table `state_safety_performance_targets` (SN-C2): national-scope
  SPTs set by CAAN, distinct from tenant SPTs.
- SPT-2 State SPIs computed by Module C aggregation (engine: `get_state_values`
  `spi_service.py:303-320`) over the materialized path (SN-C1/§7).
- SPT-3 CAAN sets/approves State SPTs via `/api/v1/spi/state/targets`
  (extension of `api/v1/spi.py` router; persists to SN-C2; CAAN_SMD-gated).
  A row replaces the built-in default (`target_value` `spi_service.py:29,77,
  344`).
- SPT-4 State status uses SPT thresholds via `get_status`
  (`spi_service.py:364-385`) + materialized trend (SN-C3, §10).

**9.4 — Schema note SN-C2: `state_safety_performance_targets`.**
Columns (binding): `id` uuid PK; `spi_id` text NOT NULL (domain = SPI
definitions `spi_service.py:21-118`); `target_value` float NOT NULL;
`warning_threshold` float; `alert_threshold` float; `window_type` text (SN-C3);
`valid_from`/`valid_to` timestamptz; `updated_by` text (CAAN user);
`updated_at` timestamptz. RLS: CAAN-only. PENDING IMPLEMENTATION.

**Interface.** `api/v1/spi.py` router (extend); `SPIService`
(`spi_service.py:139`); `spi.py`/`nhrc.py` v1 routes; `state_safety_
performance_targets` (new).

**Open questions.**
- Q9.1 — Keep code `SPI_DEFINITIONS` as master (current) vs introduce a
  `spi_definitions` reference table (task premise; requires migration)?
  DECISION NEEDED (3c).
- Q9.2 — SPT effective period (fiscal-year vs rolling)? DECISION NEEDED.

---
## 10. TREND BASELINE (Q6)

**Purpose.** Define baseline windows for period-over-period analysis.

**Compliance anchor.** §5.3.1 (analysis processes) + Doc 10159 (trend
analysis).

**Current implementation.**
- Tenant SPI trend is real (month buckets — `get_tenant_trend`
  `spi_service.py:277-301`; `_month_buckets` `:632-648`).
- State SPI trend is a PLACEHOLDER (`previous_value == value`, `trend =
  "stable"` `spi_service.py:343,352`).
- State risk register trend = prior-entry compare (`_trend`
  `state_risk_service.py:430-439`).

**Specification (Q6 decision; binding once accepted; PENDING IMPLEMENTATION).**
- TB-1 **State-level metrics:** 12-month rolling window.
- TB-2 **Operational metrics:** 90-day rolling window.
- TB-3 **Per-metric override** allowed in metric definitions (window_type on
  each SPI/aggregate `metric_key`).
- TB-4 **Baselines computed by the materialization job** (SN-C1) at window
  boundaries — never on read.

**10.4 — Schema note SN-C3: metric windows.**
Reference `module_c_metric_windows` (read-only, CAAN-owned, seeded):
`metric_key` text PK (null/global = default); `window_type` enum
(`rolling_12m` / `rolling_90d` / `quarter_over_quarter`); `window_days` int;
`valid_from` timestamptz. Defaults: state metrics = rolling_12m; operational
metrics = rolling_90d. Overrides apply per SPI/metric (`spi_service.py`
definitions). PENDING IMPLEMENTATION.

**Interface.** Materialization job (`lifecycle.py:86-99` pattern); SPI state
status/trend (`spi_service.py:322-358`); state register (`state_risk_service.py
:430-439`).

**Open questions.**
- Q10.1 — Override authority: CAAN-only via the reference table (SN-C3) vs a
  definition field? DECISION NEEDED.
- Q10.2 — Minimum history before a trend is shown (e.g. ≥ 2 periods)?
  DECISION NEEDED.

---
## 11. ANALYSIS LEVELS (Q7)

**Purpose.** Document the D3M (Doc 10159) analysis levels and their landing.

**Compliance anchor.** Doc 10159 (Safety Intelligence framework:
Data→Information→Intelligence; Descriptive / Diagnostic / Predictive /
Prescriptive).

**Current implementation.**
- Descriptive: PARTIAL — counts/averages/distributions/indices
  (`aggregation_service.py:120-210`; `state_risk_service.py:153-275`;
  `spi_service.py:303-358`; `nhrc_service.py:280-286`).
- Diagnostic: PARTIAL — N-HRC contributing factors (`nhrc_service.py:301-308`);
  SPI status vs thresholds (`spi_service.py:364-385`); Module A LLM survey
  analysis + platform Copilot (`/api/v1/copilot/chat` `routes/copilot.py:46,96`;
  `main.py:278`; `config.py:49`).
- Predictive: MISSING.
- Prescriptive: MISSING (State payload `insights`/`recommendations` are empty
  lists `api/v1/state_risk.py:49-50`; `workers/scheduler.py:90,94`).

**Specification (Q7 roadmap; binding once accepted; PENDING IMPLEMENTATION).**

| Level | Status | Landing |
|---|---|---|
| Descriptive | PARTIAL — formalize as the base layer | NOW |
| Diagnostic | ROADMAP — LLM "why" extended from Module A to Module B (State-level drivers; "why is N-HRC trending") | 3c scope: endpoint/design |
| Predictive | MISSING — future (statistical forecasting on SN-C1 baselines) | FUTURE |
| Prescriptive | MISSING — future (CAAN prioritization recommendations) | FUTURE |

- AL-1 Descriptive formalization: existing services define outputs
  (`aggregation_service.py`, `spi_service.py`, `state_risk_service.py`,
  `nhrc_service.py`); each output labeled descriptive.
- AL-2 Diagnostic roadmap: reuse Copilot infra (`routes/copilot.py:46,96`)
  under CAAN-only, protection-compliant scope (§5); input = SN-C1 aggregates
  (diagnostics run on aggregates, not raw tenant narratives — DP-2 boundary).
- AL-3 Predictive (future): forecasts over materialized trends (SN-C1/SN-C3).
- AL-4 Prescriptive (future): recommendation engine for regulator actions
  (Q11.2).

**Interface.** Copilot (`routes/copilot.py`; `config.py:49`); SPI/N-HRC state
routes; `module_c_aggregates` (SN-C1); `module_c_metric_windows` (SN-C3).

**Open questions.**
- Q11.1 — LLM diagnostics: compute on CAAN-protected aggregates vs tenant
  side? APPENDIX 3 assessment — DECISION NEEDED (legal).
- Q11.2 — Predictive/prescriptive: in-house vs vendor? UNKNOWN — NEEDS HUMAN
  INPUT.

---
## 12. CAAN HAZARD VISIBILITY (Q1)

**Purpose.** Bound what CAAN can see of Module B hazard data per the Q1
decision.

**Compliance anchor.** §3.4.1.3 (State oversight/monitoring) + §5.4/Appendix 3
(protection) + §5.2.5 (SSP authorities access to SDCPS data).

**Current implementation.** Aggregation exposes truncated 50-char titles +
category + risk fields for High/Very High hazards
(`aggregation_service.py:189-210`; slice `[:50]` `:201`); benchmark returns
the operator's `tenant_id` (`:226`). NO escalation mechanism exists.

**Specification (Q1 decision; binding once accepted; PENDING IMPLEMENTATION).**
- HV-1 **Default visibility:** 50-char truncated `title` + full taxonomy +
  severity + probability + risk index. NO description, NO reporter identity.
  (Default already matches `aggregation_service.py:200-205`.)
- HV-2 **Escalation path:** CAAN requests full description with a stated
  reason → temporary access; EVERY escalation logged in `audit_logs`
  (`action="CAAN_ESCALATED_READ"` + reason in `metadata_json`,
  `db_models.py:1650,1660`); access auto-revoked after a configurable
  inspection period.
- HV-3 **Never visible:** reporter identity (anonymous flag `reports.is_
  anonymous` `db_models.py:172`; confidential class future — DP-4); raw survey
  responses (Module A boundary — `aggregation_service.py:35-66`).
- HV-4 **Escalation surface:** extend `/api/v1/regulator` with
  POST `/share/escalations` + GET `/share/escalations/audit` (spec; PENDING).

**Interface.** `routes/regulator_dashboard.py` (extend); `AggregationService`
(`aggregation_service.py:189-210`); `audit_logs` (`db_models.py:1646-1667`);
`reports.is_anonymous` (`db_models.py:172`).

**Open questions.**
- Q12.1 — Inspection-period default (e.g. 72 h / 7 d)? DECISION NEEDED.
- Q12.2 — Escalation scope: hazards only, or also occurrence reports?
  DECISION NEEDED.

---
## 13. COMPLIANCE MATRIX (MODULE C)

**Purpose.** Maps every relevant Annex 19 Third Edition requirement and
Doc 10159 reference to the Module C sub-section(s) that implement it, with a
current status and a note. Each status traces to a cited Module C section and
its schema notes. Decision IDs reference the platform-owner confirmations of
2026-09-19 recorded in §14.1. Status is the Annex-19 *capability*, not the
underlying service (e.g. aggregation services run, but SDCPS is still Partial
because governance §5.2.7 is missing).

**13.1 — Annex 19 Third Edition mapping (primary matrix).**

| Annex 19 § | Description | Module C § | Status | Notes |
|---|---|---|---|---|
| §3.3.2 | State's obligation to require SMS of service providers | §4 | Partial | PSOE tracks SMS maturity (PSOE-1/PSOE-2, categorical binds; Q4.1) |
| §3.4.1.3 | Periodically assess SMS / monitor safety performance | §4 | Partial | PSOE-3/PSOE-4; periodicity registry MISSING (Q4.2); closing role CAAN_SMD (Q4.3) |
| §3.4.2.1 | State SPIs (supported by SPTs where appropriate) | §9 | Partial | `spi_service.py:21-118` + State SPT table (SN-C6); persistence not wired |
| §5.1 | Safety intelligence strategy | §1 | Partial | Descriptive now; predictive/prescriptive roadmap (§11, AL-3/AL-4) |
| §5.2 | SDCPS (capture, store, aggregate, process, analyse) | §2 | Partial | Aggregation layer exists (SDCPS-1..8); governance §5.2.7 MISSING |
| §5.2.4 | Voluntary safety reporting system | §5 | Missing | Confidential channel not built; Module B ownership (Q5.2, DP-4); capture in §2 |
| §5.3 | Safety data and safety information analysis | §3 | Partial | Descriptive + diagnostic roadmap (SLI-1..8); predictive/prescriptive MISSING |
| §5.3.1 | Safety performance indicators | §9 | Partial | SPI definitions + State SPIs; State trend PLACEHOLDER (`spi_service.py:343,352`) |
| §5.4 | Safety data protection | §5 | Partial | Classification + anonymization (DP-1..7); RLS gaps (DP-6) |
| §5.5 | Safety information sharing and exchange | §6 | Partial | CAAN→operator baseline (SS-1..6); State-to-State deferred (SS-4) |
| App 3 | Protection of safety data / safety information | §5 | Partial | Use-limitation + classification (DP-4/DP-7); confidential class MISSING |
| §5.3 + Doc 10159 | D3M / safety intelligence | §11 | Partial | Descriptive only (AL-1); diagnostic roadmap (AL-2) |

**13.2 — Doc 10159 concepts cited where implemented.**
- Data→Information→Intelligence progression — §1, §3, §11 (AL-1..AL-4).
- Safety Intelligence Cycle — §3 (spec framing; page-level text not extracted).
- D3M (Data-Driven Decision-Making) — §3 (SLI-6), §11.
- Descriptive analysis — implemented as the base layer (`aggregation_service.py`
  `:120-210`; `spi_service.py:303-358`; `state_risk_service.py:153-275`;
  `nhrc_service.py:280-286`).
- Diagnostic analysis — PARTIAL / roadmap (`nhrc_service.py:301-308`; AL-2).
- Predictive analysis — MISSING (AL-3; `state_risk_service.py:430-439` is a
  prior-entry compare only).
- Prescriptive analysis — MISSING (AL-4; `api/v1/state_risk.py:49-50` and
  `workers/scheduler.py:90,94` are empty lists).
- Taxonomy guidance (ADREP) — §8 (TX-1..TX-4).

**13.3 — CAAN CAR-19 references used across Module C.**
- State SPI definitions — `spi_service.py:21-118` (§9).
- State SPT — `state_safety_performance_targets` (SN-C6, §9).
- State risk register — `state_risk_register` (`db_models.py:866`),
  `state_risk_categories` (`db_models.py:1816`) (§2, §3).
- N-HRC national categories — `models/nhrc.py:12-25`,
  `nhrc_service.py:171-265` (§3, §8).
- PSOE instrument — `psoe_questions` (`db_models.py:970`),
  `psoe_assessments` (`db_models.py:918`), `psoe_findings`
  (`db_models.py:1007`) (§4).
- Hazard taxonomy / ADREP — `models/hazard.py:23`; `taxonomy_mappings`
  (SN-C8) (§8).
- Confidential reporting — deferred to Module B (DP-4, Q5.2, §5).
- SSP dispatch — `lifecycle.py:26-35`; `workers/scheduler.py:76-149` (§2, §6).

**13.4 — Summary: status counts.** Across the 12 primary matrix rows:
**0 Implemented / 11 Partial / 1 Missing.** The single Missing row is §5.2.4
(voluntary/confidential reporting, Module B-owned). Every other row is Partial.
No Annex 19 capability is complete end-to-end under this contract because each
Partial row carries at least one PENDING specification item (SDCPS/SLI/PSOE/DP/
SS/AGG/TX/SPT/TB/AL/HV) or schema note (SN-C1..SN-C10).

**13.5 — Top 5 remediation priorities.**
1. **§5.2.4 voluntary/confidential reporting (the only Missing row).** Build
   the confidential/restricted class and RLS (DP-4, DP-6) against Module B's
   ownership (Q5.2); Module C consumes it. Blocks any audit claim.
2. **§5.3.1 + §3.4.2.1 State SPI/SPT persistence and trend.** Replace the
   placeholder State SPI trend (`spi_service.py:343,352`) and the non-persisting
   SPT stub (`api/v1/spi.py:129-142`) via SN-C1 materialized aggregates, SN-C3/
   SN-C7 metric windows, and SN-C6 State SPT (SPT-1..SPT-4).
3. **§5.4 / App 3 protection hardening.** Enable or explicitly exempt RLS on
   `caan_reports`, `sms_maturity`, `state_risk_categories` (DP-6), add
   classification labels (DP-1, G-5.3), log every CAAN read (DP-3, G-5.4), and
   attach use-limitation statements (DP-7). Prerequisite to §5.5 sharing.
4. **§5.2.6 taxonomy unification.** Resolve the three parallel devices
   (ADREP/ICAO/N-HRC) into the ICAO-canonical taxonomy + `taxonomy_mappings`
   (SN-C8) and the `nhrc_category` column (SN-C9), per TX-1..TX-4 (Q8.1/Q8.2).
   Prerequisite for consistent State hazard identification and sharing.
5. **§5.3.1(d) + §5.1 safety-intelligence output.** Turn the empty
   `insights`/`recommendations` blocks (`api/v1/state_risk.py:49-50`;
   `workers/scheduler.py:90,94`) into the D3M diagnostic output (AL-2, SLI-6)
   under the three-lane LLM decision (Q11.1), and register positive outcomes
   (SLI-7). Converts descriptive data into usable intelligence.

**13.6 — Module C readiness assessment (CAAN audit).** **NOT READY — DRAFT
COMPLETE pending implementation.** The SDCPS aggregation, State risk register,
SPI/N-HRC computation and weekly SSP dispatch are already implemented (§2, §3
evidence), giving a working descriptive layer. But across the 12 primary
Annex 19 rows the tally is **0 Implemented / 11 Partial / 1 Missing**. The
blocking gaps before any audit-ready claim are (1) the confidential
voluntary-reporting channel (§5.2.4, Module B-owned); (2) State SPI
trend + SPT persistence (§9/§10, SN-C1/SN-C3/SN-C6); (3) protection hardening —
RLS + classification + read audit (§5.4/App 3, DP-1/DP-3/DP-6/DP-7);
(4) taxonomy unification (§5.2.6, SN-C8/SN-C9); and (5) safety-intelligence
output (§5.3.1d/§5.1, AL-2). Every Partial row has a defined path via the
PENDING specification items and SN-C1..SN-C10.

---

## 14. MODULE C CONTRACT SIGN-OFF

- **Total sections:** 14 numbered sections (1-14) delivered across 3 chunks
  (3a-3c). Sections 1-12 are the substantive contract; §13 is the Compliance
  Matrix; §14 is this sign-off. The consolidated Schema Notes ledger
  (SN-C1..SN-C10) is Appendix SN.
- **Total specification items:** 60 binding items across §§2-12 — SDCPS-1..8,
  SLI-1..8, PSOE-1..6, DP-1..7, SS-1..6, AGG-1..5, TX-1..4, SPT-1..4, TB-1..4,
  AL-1..4, HV-1..4. **All PENDING IMPLEMENTATION.**
- **Schema notes:** **SN-C1..SN-C10** (Appendix SN); SN-C5..SN-C10 finalized in
  this chunk; **all PENDING IMPLEMENTATION.**
- **Open questions:** 28 raised across §§1-12; the platform owner confirmed 16
  decision IDs on 2026-09-19 (§14.1); the remaining UNKNOWNs are enumerated in
  §14.2.
- **Status:** **DRAFT COMPLETE — pending implementation.**
- **Next steps:** RBAC model (uniform CAAN_SMD gating of the regulator / PSOE /
  SPI / N-HRC / state-risk / SDC / Copilot paths — DISCOVERY_REPORT.md:61;
  see §14.3) → Dashboard contract (Regulator dashboard UI, deferred from
  chunk 3c) → platform-wide Compliance Matrix (Modules A + B + C).

**14.1 — Confirmed decisions (platform owner, 2026-09-19).**

| ID | Decision | Module C landing |
|---|---|---|
| Q4.1 | PSOE numeric track: ARCHIVE AS LEGACY; new assessments categorical only; no data migration | PSOE-1 |
| Q4.1b | PSOE finding ↔ CAP linkage: BIDIRECTIONAL, OPTIONAL, MANUAL (Safety Manager chooses) | PSOE-3, SN-C10 |
| Q4.3 | PSOE closing role: CAAN_SMD ONLY | PSOE-4 |
| Q5.2 | Confidential-reporting ownership: MODULE B | DP-4, §5 |
| Q6.1 | Share channel: BOTH API endpoints (pull) + periodic push | SS-1, SS-5 |
| Q7.1 | Materialization cadence: HYBRID — daily for state/operational, event-driven for critical alerts | AGG-3, SN-C1/SN-C5 |
| Q7.2 | RLS for NULL-tenant rows: EXPLICIT POLICY `USING (tenant_id IS NULL AND role = 'CAAN_SMD')` | SN-C5 |
| Q8.1 | Taxonomy mapping: BOTH columns + reference table | TX-2/TX-3, SN-C4/SN-C8 |
| Q8.2 | N-HRC derivation: AUTO WITH MANUAL OVERRIDE | SN-C9 |
| Q9.1 | SPI definitions: HYBRID — code constants for standard SPIs + per-tenant override table | SPT-1, SN-C6 |
| Q9.2 | SPT period: ANNUAL DEFAULT, CONFIGURABLE | SPT-1, SN-C6 |
| Q10.1 | Baseline override: CAAN ONLY | TB-3, SN-C7 |
| Q10.2 | Min history: 12-MONTH STATE / 3-MONTH OPERATIONAL; "insufficient data" below minimum | TB-1/TB-2, SN-C7 |
| Q11.1 | LLM diagnostics: THREE LANES — aggregated now; cloud individual deferred (legal review); self-hosted individual now | AL-2 |
| Q12.1 | Escalation window: 24 H DEFAULT, CONFIGURABLE | HV-2 |
| Q12.2 | Escalation scope: FULL DETAIL MINUS REPORTER IDENTITY (description + attachments) | HV-2/HV-3 |

*Note:* the decision brief labels these "15 decisions"; 16 distinct IDs are
recorded (Q4.1 and Q4.1b were grouped in the brief). Listed as 16.

**14.2 — Remaining UNKNOWNs (carried forward).**
- Q0 — Scope of "regulator access": which Module B hazard-level fields
  (agent, system, CATS codes) CAAN may see vs. risk-level aggregates only.
  NEEDS HUMAN INPUT (§1).
- Q3 — §5.5 sharing recipients and the Appendix 3 protection agreements;
  State-to-State deferred pending legal. NEEDS HUMAN INPUT (§2, SS-4).
- Q4.2 — PSOE assessment periodicity (annual cycle vs §3.4.1.2
  prioritization). NEEDS HUMAN INPUT (§4).
- Q5.1 — Retention/deletion for the protected class (who may purge, how long).
  NEEDS HUMAN INPUT (§5).
- Q6.2 — Which "matters of interest" auto-trigger State-to-State sharing
  (§5.5.1). NEEDS HUMAN INPUT (§6).
- Q7 / Q11.2 — Predictive/prescriptive scope; in-house vs vendor.
  NEEDS HUMAN INPUT (§3, §11).
- §4 — Doc 9859 §1.3.4.3 heading confirmation for PSOE periodic-assessment
  guidance. NEEDS HUMAN INPUT.
- Doc 10159 page-level text extraction (only the summary PDF was used).

**14.3 — Carry-forward items for the RBAC model.**
- Gate every Module C route (regulator dashboard, PSOE, SPI state, N-HRC state,
  state-risk, SDC ingestion, Copilot) uniformly by CAAN_SMD (SDCPS-7;
  DISCOVERY_REPORT.md:61).
- Audit actions to define: `CAAN_READ_*`, `CAAN_SHARE_*`, `CAAN_ESCALATED_READ`
  (§5 DP-3, §6 SS-2, §12 HV-2) in `audit_logs`
  (`db_models.py:1646-1667`).
- Explicit RLS policy for NULL-tenant aggregate rows using
  `role = 'CAAN_SMD'` (SN-C5 / Q7.2).
- PSOE closing restricted to CAAN_SMD (Q4.3); reconcile `_EDIT_ROLES`
  (`api/v1/endpoints/psoe.py:49-52`).
- Share endpoint scoping: an operator sees only its own tenant (SS-1);
  escalations grant temporary, auto-revoked access (HV-2 / Q12.1).
- Module B coordination: confidential-reporting owner (Q5.2), plus the
  `hazards`/`reports` mapping columns (SN-C4/SN-C8/SN-C9), require coordinated
  role/permission changes.
- Role literals `SAG_MEMBER` / `ACCOUNTABLE_EXECUTIVE` (Module B §§22, 28)
  interplay with CAAN oversight read paths — confirm no leakage.

**14.4 — Reconciliation flagged.**
- §5.2 is Partial while its services are implemented: status tracks the
  Annex-19 capability, not the service (§13 purpose note).
- Schema Notes SN-C5..SN-C10 finalize/refine SN-C1..SN-C4 (no duplication):
  SN-C5 = SN-C1 final (+`payload` jsonb, explicit NULL-tenant RLS);
  SN-C6 = SN-C2 final (+`spi_definition_id` FK, `target_period`, `approved_by`);
  SN-C7 = SN-C3 final (windows folded into `module_c_aggregates` /
  `metric_definitions`); SN-C8 = SN-C4 reference table finalized; SN-C9 and
  SN-C10 are new.
- The platform-owner decision count ("15" in the brief) resolves to 16 distinct
  IDs (§14.1).
- Legacy §13 Schema Notes heading is replaced by §13 Compliance Matrix; the
  ledger moved to Appendix SN.

---

## APPENDIX SN — SCHEMA NOTES (SN-C1..SN-C10, MODULE C)

Consolidated ledger. Details in §7.4, §8.4, §9.4, §10.4 and this appendix.
All **PENDING IMPLEMENTATION**. SN-C5..SN-C10 finalize/refine SN-C1..SN-C4 per
the 2026-09-19 decisions (§14.1).

- **SN-C1 — `module_c_aggregates`** (§7.4; finalized by SN-C5): materialized
  aggregates; national rows `tenant_id NULL`; `value` jsonb; `computed_at`;
  TTL; RLS gating Q7.2. Cadence = hybrid (Q7.1).
- **SN-C2 — `state_safety_performance_targets`** (§9.4; finalized by SN-C6):
  national-scope SPTs distinct from tenant SPTs; CAAN-only RLS; replaces code
  defaults (`spi_service.py:29,77,344`).
- **SN-C3 — `module_c_metric_windows`** (§10.4; finalized by SN-C7): reference
  window registry; defaults 12-month state / 90-day operational (Q10.2);
  overrides per `metric_key`; CAAN-only override (Q10.1).
- **SN-C4 — taxonomy mapping strategy** (§8.4; finalized by SN-C8): hybrid
  mapping columns + read-only `taxonomy_mappings`; coordinated Module B schema
  change required (Q8.1).
- **SN-C5 — `module_c_aggregates` (final).** Columns (binding): `id` uuid PK;
  `tenant_id` uuid NULL (NULL = national/state scope); `metric_type` text
  NOT NULL; `metric_key` text; `period_start`/`period_end` timestamptz;
  `payload` jsonb NOT NULL; `computed_at` timestamptz NOT NULL; `ttl_seconds`
  int NULL; `source_version` text. UNIQUE (`tenant_id`, `metric_type`,
  `metric_key`, `period_start`). **RLS (Q7.2):** explicit policy — national rows
  visible only via `USING (tenant_id IS NULL AND role = 'CAAN_SMD')`;
  tenant-scoped rows via the existing tenant policy. **Cadence (Q7.1):** daily
  for state-level and operational metric types; event-driven refresh for
  critical-alert metric types. PENDING IMPLEMENTATION.
- **SN-C6 — `state_safety_performance_targets` (final).** Columns (binding):
  `id` uuid PK; `spi_definition_id` text FK (domain = SPI definitions
  `spi_service.py:21-118`, per Q9.1 hybrid); `target_value` numeric NOT NULL;
  `target_period` text NOT NULL (annual default, configurable — Q9.2);
  `set_by` text (CAAN user); `set_at` timestamptz; `approved_by` text
  (CAAN_SMD); `approved_at` timestamptz; `valid_from`/`valid_to` timestamptz.
  RLS: CAAN-only. PENDING IMPLEMENTATION.
- **SN-C7 — metric windows / trend baseline config (final).** Held either as
  part of `module_c_aggregates` (window metadata per `metric_type`/
  `metric_key`) or a dedicated `metric_definitions` table — recommendation:
  dedicated `metric_definitions` (read-only, CAAN-owned, seeded): `metric_key`
  text PK; `window_type` enum (`rolling_12m` / `rolling_90d` /
  `quarter_over_quarter`); `window_days` int; `min_periods` int (12-month state
  / 3-month operational minimum — Q10.2); `valid_from` timestamptz. CAAN-only
  override authority (Q10.1). Below `min_periods`, consumers return
  "insufficient data". PENDING IMPLEMENTATION.
- **SN-C8 — `taxonomy_mappings` reference table (final).** Read-only, seeded,
  CAAN-owned; maps ICAO ↔ ADREP ↔ HFACS ↔ N-HRC. Columns: `id`; `icao_code`;
  `adrep_code`; `hfacs_nanocode`; `nhrc_category`; `valid_from`. Seeds from
  `data/icao_adrep_taxonomies.csv` / `data/hfacs_nanocodes.csv` and the six live
  mapping tables (`DB_VERIFICATION.md:125,189`). Complements (does not replace)
  the mapping columns on `hazards`/`reports` (Q8.1: both). PENDING
  IMPLEMENTATION.
- **SN-C9 — `nhrc_category` column on hazards.** New column on `hazards`
  (Module B-owned; coordinated change): `nhrc_category` text, auto-derived by
  `nhrc_service.py:241-265` with manual CAAN override (Q8.2). Mirrors TX-2.
  PENDING IMPLEMENTATION.
- **SN-C10 — PSOE finding ↔ CAP linkage.** `psoe_findings.cap_id` uuid NULL FK
  → `caps.id` (existing `caps` `db_models.py:378`; `psoe_findings`
  `db_models.py:1007`); plus `caps.source_psoe_finding_id` uuid NULL FK →
  `psoe_findings.id`. Bidirectional, optional, manual — the Safety Manager
  chooses whether to create a CAP from a finding (Q4.1b). Both columns nullable;
  no cascade on the back-reference. PENDING IMPLEMENTATION.

---
*End of MODULE_C_CONTRACT.md (Chunks 3a-3c). Sections 1-14; Appendix SN
(SN-C1..SN-C10, all PENDING); decisions recorded in §14.1. Status: DRAFT
COMPLETE — pending implementation. This document describes current state and
gaps only — no fixes or implementations are proposed.*