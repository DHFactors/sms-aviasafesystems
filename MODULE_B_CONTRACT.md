# MODULE_B_CONTRACT.md — Hazard & Risk Management Module

AviaSAFE SMS Platform — Module B Specification
Status: DRAFT (Chunk 2b of 7)
Chunks 2c-2g to follow

---

## 1. OVERVIEW

**Purpose.** Module B is the Safety Department's Safety Risk Management (SRM)
instrument. It owns the end-to-end Hazard & Risk workflow: hazards are
registered via fixed-format references (OPS/001/M/2026) on a 13-field
registration sheet, initially prioritized (H/M/L), and then analyzed, assessed,
and mitigated through CAN/CAP, bow-tie/SRAM, verification, and closure
(Chunks 2c-2g). The Module B `hazards` table is the single normalized hazard
entity; every ingestion adapter in Section 2 writes to it.

**Ownership.** Safety Department. Hazard registration, prioritization, risk
assessment, and follow-up are safety-manager actions. Per CAAN SRM Manual §2.3.6.6
risk acceptance authority cannot be delegated — escalations end at the Accountable
Executive/airline admin (covered in Chunk 2f).

**Compliance anchor.** Annex 19 Third Edition, Appendix 2 — Framework for a
Safety Management System, **Component 2 — Safety Risk Management**:
- **Element 2.1 — Hazard identification:** "The service provider shall develop
  and maintain a process that ensures that hazards in the delivery of the
  service provider's services are identified."
- **Element 2.2 — Safety risk assessment and mitigation:** "The service provider
  shall develop and maintain a process that ensures the analysis, assessment and
  control of the safety risks in the delivery of the service provider's services."

Implemented in detail by CAAN SRM Procedure Manual (First Edition, January 2026)
Chapter 2, §2.1-§2.2 (compliance fields and prioritization, cited in Sections 3-4).
UNKNOWN — NEEDS HUMAN INPUT: the exact Annex 19 Third Edition wording and
numbering above is the stable Appendix 2 requirement text but could NOT be
re-verified against a local copy — `data/an19_cons (4).pdf` and `data/Doc 9859.pdf`
are NOT present in this repo (only the CAAN PDF and CSV/XLSX datasets are shipped
in `data/`). Confirm against the Third Edition print before finalizing.

**Boundaries — Module B MUST NOT:**
1. Consume Module A survey scores as hazards. Per SURVEY_RISK_INJECTION_VALIDATION.md,
   the SMS health survey is safety data (§1.1 of the CAAN manual), not a hazard
   source; no injection adapter may be built for it.
2. Write to Module A tables (`surveys`, `survey_responses`, `sms_maturity`) or
   Module C tables (`state_risk_register`, `psoe_*`, `regulatory_reports`,
   `caan_reports`, `spi_*`, `nhrc_*`).
3. Submit VSR/MORs itself — report intake is an ingestion front-door (Section 2),
   hazard auto-creation is the boundary; the `reports` table stays owned by the
   ingestion layer.
4. Leak reporter identity — confidential/anonymous reporting (Section 2) must not
   surface in Module B output.

**Interfaces.**
- To dashboards: `GET /api/v1/dashboard/hazards` (hazard frequency trend,
  `routes/dashboard.py:149`), hazard stats (`routes/hazards.py:109`),
  list/detail (`routes/hazards.py:62,118`), verification metrics
  (`routes/verification.py:48`).
- To Module C (regulator view): `GET /api/v1/regulator/top-hazards`
  (`routes/regulator_dashboard.py:37`), `GET /api/v1/regulator/risk-register`
  (`routes/regulator_dashboard.py:55`), and the SRAM risk register read model
  `GET /api/v1/sram/risk-register/{tenant_id}` (`api/v1/endpoints/sram.py:271`).
- Data model: `hazards` (ORM `db/db_models.py:64-139`) plus the SRAM/RCA/CAN/CAP
  satellite tables consumed in later chunks.

---

## 2. INGESTION

**Purpose.** Convert all inbound hazard information into normalized `hazards`
rows. The CAAN manual (§2.1) lists **seven sources of hazard information**;
the platform implements a subset of them.

**Compliance anchor.** CAAN SRM Manual §2.1 (source list); Annex 19, Element 2.1.

**CAAN §2.1 seven sources vs. platform support:**

| # | CAAN source (§2.1) | Platform status | Implementation |
|---|---|---|---|
| 1 | Voluntary Hazard Reports (VSR) | IMPLEMENTED | `POST /api/v1/reports/` + `POST /api/v1/reports/vsr` — `report_type='voluntary'` auto-registers a hazard (`routes/occurrence_reports.py:175,210`; `_auto_create_hazard_from_report` `:368-407`) |
| 2 | Occurrence Notifications / Investigation Reports (MOR/accident) | PARTIAL | MOR auto-registers hazards (`routes/occurrence_reports.py:115,160`); **MOR only** — occurrence investigation reports are not modeled |
| 3 | Internal Audit Reports | PARTIAL | No audit adapter; "Internal Audit" is a legal manual source value for `POST /api/v1/hazards` (`models/hazard.py:93`; `HAZARD_CREATION_SOURCES` `models/hazard.py:187-194`, enforced `routes/hazards.py:37-43`) |
| 4 | External Audit Reports | PARTIAL | "CAAN Audit" / "Quality Audit" legal manual sources (same whitelist) — no dedicated adapter |
| 5 | Hazard Survey Reports | MISSING | `HazardSource.SAFETY_SURVEY` ("Safety Survey") exists in the enum (`models/hazard.py:94`) but is **not** in `HAZARD_CREATION_SOURCES` and has no adapter. Per SURVEY_RISK_INJECTION_VALIDATION this is the *hazard-identification survey*, NOT the Module A SMS health survey — the latter must stay excluded |
| 6 | Operational Data Review Reports | MISSING | No adapter |
| 7 | Operational Trial Reports | MISSING | No adapter |

**Additional platform front-doors beyond the manual's list:**
- Flight diversions → hazards: `POST /api/v1/flight-diversions/{id}/link-hazard` (`routes/flight_diversions.py:179`; source `Flight Diversion`, whitelisted).
- aviaSDCPS bulk ingestion: `POST /api/v1/sdc/validate` and `POST /api/v1/sdc/ingest` commit mapped records into hazards/reports/cans/caps (`routes/sdc.py:31,171,250`).

**Confidential reporting — NEW REQUIREMENT, NOT IMPLEMENTED.**
Per Annex 19 Third Edition **Appendix 3**, confidential safety reporting is a new
State requirement. The platform today has only an `is_anonymous` boolean on the
report row (`db/db_models.py:172`; forced `False` for MOR `routes/occurrence_reports.py:151`,
may be `True` for VSR `:197`). There is NO separate confidential channel with
identity segregation/protection. **GAP — MISSING.** Exact appendix citation
UNKNOWN — NEEDS HUMAN INPUT (Third Edition file not in repo).

**Normalization.** All adapters converge on the `HazardCreate` payload
(`models/hazard.py:197-247`) — title, description, source(+id/url), function,
taxonomy, threat/consequence/top event, severity/probability/risk index, priority,
stamps — then `HazardService.create_hazard` (`services/hazard_service.py:243`).
Auto-registered hazards are constructed inline and inherit report severity/
probability/occurrence category (`routes/occurrence_reports.py:379-393`).

---

## 3. §2.1 HAZARD REGISTRATION

**Purpose.** Register a hazard with every element required for later risk
assessment and mitigation. Reference `hazards` uses the CAAN function format
`{FUNCTION}/{SEQ:03d}/{PRIORITY}/{YEAR}` (e.g. `OPS/001/M/2026`,
`services/hazard_service.py:71-89`).

**Compliance anchor.** CAAN SRM Manual §2.1 (essential registration elements i-xiii).
Note: the manual's requirement list enumerates 13 elements (i-xiii); its sample
sheet and explanatory note additionally render "Threat of Hazard" — the platform
models `threat` so this is covered either way.

**13 required fields vs. current implementation** (ORM `Hazard`,
`db/db_models.py:64-139`; live columns verified per `DB_VERIFICATION.md:79-94`):

| # | CAAN field | Column | Status |
|---|---|---|---|
| i | Hazard identified/reported date | `created_at` (`db_models.py:121`) | PARTIAL — date of *registration*, not of identification; no distinct `identified_at`/`reported_at` field |
| ii | Area/operation/equipment | `function` (`:71`) + `department` (`:100`) | PARTIAL — ICAO function code + department only; no free-text equipment/area field |
| iii | Description of hazard | `description` (`:73`) | ✓ |
| iv | Hazard taxonomy | `taxonomy` + `taxonomy_specific` (`:80-81`), ICAO 4-value CHECK (`:58-61`) | ✓ |
| v | Hazard Code | `hazard_id` (`:68`), unique per tenant (`:133`) | ✓ |
| vi | Source of information | `source`, `source_id`, `source_url` (`:74-76`) | ✓ |
| vii | Unsafe / top event | `top_event` (`:84`) | ✓ |
| viii | Consequence | `consequence` (`:83`) | ✓ |
| ix | Initial prioritization | `priority` (H/M/L, `:93`, CHECK `:55-57`) + `priority_date` (`:111`) | ✓ (gaps in §2.2) |
| x | Recommended actions | `recommended_action` (`:94`), `corrective_action` (`:95`), `corrective_action_flag` (`:96`), `srm_flag` (`:97`) | ✓ |
| xi | Status | `status` (`:110`, enum `models/hazard.py:7-13`) + `status_date` (`:112`) | ✓ |
| xii | Follow-up | `follow_up_date` (`:113`) | ✓ storage; scheduling/manual only — see §2.2 timelines |
| xiii | Remarks | `remarks` (`:116`) | ✓ |

**Gaps.** (i) missing identification/reporting date distinct from `created_at`;
(ii) missing free-text area/operation/equipment. Both documented in
SCHEMA_RECONCILIATION_PLAN.md risk areas. No migration proposed in this contract —
decisions needed (see below).

**API surface** (`routes/hazards.py`, prefix `/api/v1/hazards` `core/config.py:38`,
mounted `main.py:227`; legacy `/api/hazards` `main.py:235`):

| Method | Path | Purpose | Auth |
|---|---|---|---|
| POST | `/hazards/` | Create (source whitelist enforced `:38`) | tenant user (`:34`) |
| GET | `/hazards/` | List + filters (`:62`) | tenant user |
| GET | `/hazards/stats` | Stats (`:109`) | tenant user |
| GET | `/hazards/{id}` | Detail (`:118`) | tenant user |
| PUT | `/hazards/{id}` | Update (`:131`) | tenant user |
| PATCH | `/hazards/{id}/status` | Status transition (`:153`) | tenant user |
| PATCH | `/hazards/{id}/assign` | Assignment (`:167`) | tenant user |
| POST | `/hazards/{id}/sram/calculate` | Live SRM calc (`:212`) | §2.4 |
| PUT | `/hazards/{id}/sram/save` | SRM persist (`:246`) | §2.4 |

Service: `HazardService` (`services/hazard_service.py:213`); create path
`create_hazard_v1` (`:243`); risk auto-classification on create (`:250-274`);
reference builder (`:292-309`).

**Open questions.**
- Q1. Should field (i) be split into `identified_at`/`reported_at` vs `registered_at`,
  or is `created_at` + report `occurrence_date` sufficient?
- Q2. Should field (ii) add a free-text `equipment`/`area` column, or is the ICAO
  function code + department claim the canonical mapping?
- Q3. Hazard survey reports (CAAN source 5): add an adapter, or keep manual
  registration? Needs platform-owner decision (contact CAAN per
  SURVEY_RISK_INJECTION_VALIDATION.md §7).

---

## 4. §2.2 INITIAL PRIORITIZATION

**Purpose.** On receipt, set the initial priority (H/M/L) that determines how
quickly a hazard is addressed. CAAN offers two methods: severity-only, or the
Event Risk Classification (ERC) 4×4 matrix.

**Compliance anchor.** CAAN SRM Manual §2.2:
- **Method A (severity-only):** consequence class → Accident=**H**,
  Serious Incident=**M**, Incident=**L**.
- **Method B (ERC):** two team questions (most-credible outcome: Catastrophic/
  Major/Minor/Negligible; remaining-barrier effectiveness: Effective/Limited/
  Minimal/Not effective) form a **4×4 matrix** → risk weight colour Red=**H**,
  Yellow=**M**, Green=**L**.
- **Timelines:** H start ≤ **24 hours**; M start ≤ **7 days**; L start ≤ **15 days**
  of receiving/identifying the hazard.

**Current implementation.**
- Field: `priority` H/M/L with CHECK constraint `ck_hazards_priority`
  (`db_models.py:55-57,93`); default `M` (`hazard_service.py:308`).
- `priority_date`: stamped `= now` at creation (`hazard_service.py:356`) and
  re-stamped whenever priority changes (`hazard_service.py:461-465`).
- Auto-created hazards: priority derived from the **5×5** risk index
  (severity×probability): `risk >= 12 → H`, `>= 6 → M`, else `L`
  (`routes/occurrence_reports.py:356-365`).
- Manual `POST /hazards/`: priority is client-supplied (`models/hazard.py:221`) —
  **no server-side prioritization verification**.
- Follow-up: `follow_up_date` set by client/seeder (`hazard_service.py:358`); no
  scheduling logic.

**Gaps.**
1. **ERC (Method B) — MISSING.** No `ERC`/Event Risk anywhere in `backend/`
   (grep confirms a single false positive). The 4×4 outcome×barrier matrix,
   barrier-effectiveness question, and R/Y/G→H/M/L mapping are entirely unmapped.
2. **Method A — MISSING.** No mapping from the occurrence class
   (ACCIDENT / SERIOUS_INCIDENT / INCIDENT; string values on `Report`,
   `models/report.py:28`) to H/M/L. The 5×5 risk-index rule is a platform
   equivalent, not the manual's severity-class rule.
3. **Timelines — MISSING (not enforced).** No 24h/7d/15d deadline logic:
   `priority_date` is informational; nothing computes a start-deadline, and no
   worker marks hazards late. The closest automation is CAN/CAP overdue handling
   (`services/escalation_service.py:45`, `workers/escalation_worker.py:14`) and a
   hazard-overdue write that targets a **non-existent `overdue` column** on the
   ORM (`services/verification_service.py:123` — `pg.update(Hazard, ..., {"overdue": True})`).
4. **No ERC endpoint/UI.** Only the 5×5 `risk_index` is exposed (`severity`,
   `probability`, `risk_index`, 1-25).

**API surface.** Same as §3 plus: `_determine_hazard_priority` for auto-created
hazards (`routes/occurrence_reports.py:356-365`) and the risk-classification
service used at create time (`services/risk_matrix.py`:
`compute_risk_index`, `classify_risk`, `get_tolerability_tier` imported at
`services/hazard_service.py:48-55`).

**Open questions.**
- Q4. Which prioritization method is canonical for Module B: Method A
  (severity class), Method B (ERC 4×4), or the current 5×5 risk index? The manual
  allows "any one" but current 5×5 is not one of the two enumerated methods.
- Q5. Are the 24h/7d/15d timelines to be enforced as hard deadlines (blocking /
  overdue state) or as advisory SLA columns, given "Organization can also apply
  other approaches acceptable to CAAN" (§2.2)?
- Q6. Should `follow_up_date` be auto-derived from priority (e.g. H≤24h, M≤7d,
  L≤15d) at creation, or stay manual?
- Q7. The stray `overdue=True` write (`verification_service.py:123`) targets a
  column absent from the `Hazard` ORM — confirm intended behaviour before Chunk 2g.

---

## 5. §2.3.1 BOW-TIE ANALYSIS

**Purpose.** Document the causal path from hazard to consequence: threats on the
left of the top event, preventive controls stopping escalation to the top event,
and recovery measures (right side) preventing the top event from becoming the
ultimate consequence. The bow-tie is the manual's core analysis artefact; it
feeds the Risk Profile (§2.3.2) and Barrier Register (§2.3.4).

**Compliance anchor.** CAAN SRM Manual §2.3.1 — six-step process: (1) identify
the hazard, (2) determine the top event, (3) identify threats, (4) determine the
consequence, (5) identify existing/new **preventive controls**, (6) identify
existing/new **recovery measures** (`caan_srm.txt:576-605`). Definitions:
threat = action/event that could trigger the top event; consequence = potential
outcome of the top event; preventive controls = measures on the left of the top
event; recovery measures = measures on the right managed to prevent an accident.
Annex 19 Appendix 2 Element 2.2 (analysis and control of safety risks).

**Current implementation.** An SRAM module under prefix `/api/v1/sram`
(`api/v1/endpoints/sram.py:34`; service `services/sram_service.py`):

| Manual artefact | Column / object | Implementation |
|---|---|---|
| Bow-Tie head (hazard, top event, description) | `bow_tie_analyses` (`db_models.py:1277-1300`) | get-or-create per hazard (`sram_service.py:89-125`); `hazard_id` is the CAAN text code, **not an FK** (`:1282`) |
| Threats | `bow_tie_threats` (`:1303-1323`) — `threat`, `probability` (1-5, nullable), `threat_order` | `add_threat` (`sram_service.py:151-174`) |
| Consequences | `bow_tie_consequences` (`:1326-1347`) — `consequence`, `severity_level` A-E (CHECK `:1211-1214`), order | `add_consequence` (`:177-201`) |
| Preventive / recovery controls | `bow_tie_controls` (`:1350-1376`) — `control_type` preventive/recovery (CHECK `:1215-1218`), `owner`, `status` | `add_control` (`:204-280`) — also materialises the matching barrier_register row |
| Lifecycle | `status`: In Progress → Assessed → Accepted (CHECK `:1207-1210`; `Rejected` unused) | create (`:117`), `calculate_risk` (`:351-353`), `accept_risk` (`:395-398`) |

**API surface** (`endpoints/sram.py`): `POST /bowtie` `:137`; `GET /bowtie/{hazard_id}`
`:148` (returns head + threats + consequences + controls + risk entry,
`sram_service.py:128-148`); `POST /bowtie/{id}/threat` `:159`;
`POST /bowtie/{id}/consequence` `:171`; `POST /bowtie/{id}/control` `:185`.

**Gaps.**
1. **No linkage.** The bow-tie is a directed model — preventive controls sit on
   threat pathways, recovery measures on consequence pathways. The implementation
   stores flat lists with `control_type` only; nothing binds a control to the
   specific threat/consequence it mitigates, so "make sure all the threats of a
   hazard are addressed by the controls / no duplicated barriers" (§2.3.6.6)
   cannot be system-verified.
2. **No escalation factors** as a first-class construct. Escalation is folded into
   the 7th BQE ("Disinclination / Unintended consequences / Escalation factor",
   §2.3.6.2 vii; weight 2x, `risk_calculator.py:78`). UNKNOWN — NEEDS HUMAN INPUT
   whether per-manual disinclination scoring is a sufficient surrogate or a separate
   escalation register is expected.

**Downstream feeds.** Threat `probability` and consequence `severity_level`
(A-E); controls feed BSV → CBSV → resultant probability (Sections 6, 8).

---

## 6. §2.3.2 RISK PROFILE

**Purpose.** Compare **current** vs **resultant** risk. Current = existing
control measures (ECM, prevent hazard→top event) + existing recovery barriers
(ERB, prevent top event→ultimate consequence) in place and working; resultant =
after new control measures (NCM) + new recovery barriers (NRB) are implemented.
Each group contributes BSV; consolidated CBSV (`CBSV = ECM+ERB+NCM+NRB BSV`)
drives the resultant probability.

**Compliance anchor.** CAAN SRM Manual §2.3.2 (gaps a-o), fed by §2.3.6.1
(severity from 7 impact areas), §2.3.6.2 (BSV), §2.3.6.3 (CBSV→probability tables
A-E), §2.3.6.4 (5×5 risk matrix), §2.3.6.5 (tolerability).

**Current implementation.**
- `sram_risk_register` (`db_models.py:1428-1475`): `probability_current`,
  `severity_current`, `risk_index_current`, `tolerability_current` + the 4
  `*_resultant` columns; unique per tenant+hazard (`:1473`); status
  open/in_progress/closed (CHECK `:1271-1274`).
- `calculate_risk` (`sram_service.py:287-363`): computes the current cell via
  `risk_calculator.get_risk_matrix` (`risk_calculator.py:155-177`); risk index =
  probability × severity, numeric 1-25 (`:173`; letters A-E are display-only,
  `:25-53`); tolerability from explicit cell bands per §2.3.6.5 (Intolerable
  `:55`, Tolerable `:56-58`, Acceptable `:59`). Resultant cell requires *both*
  resultant inputs when either is supplied (`sram_service.py:301-307`).
- Endpoint `POST /api/v1/sram/risk/calculate` (`endpoints/sram.py:207-215`);
  payload `RiskCalculation` (`:72-79`) — probability 1-5, severity A-E, optional
  resultant pair + `barrier_scores`. Response includes the full 5×5 matrix
  (`build_risk_matrix`, `risk_calculator.py:219-243`).

**Gaps.**
1. **CBSV→probability MISSING.** Manual §2.3.2 note 11 derives resultant
   probability from CBSV via Tables A-E (§2.3.6.3, ONB 2-8 per severity value).
   The system only accepts user-supplied `probability_resultant`; no aggregate
   BSV→probability engine exists.
2. **Severity misses the 7-impact-area method.** §2.3.6.1 derives severity from 7
   weighted impact areas (Pax/Public 4x, Employee 3x, Product/Service 2x,
   Asset/Financial, Reputation, Aviation Security, Environmental).
   Implementation stores a single severity letter/number with no consequence
   impact-score sheet.
3. **Groups not decomposed.** Register stores only the 4 current/resultant cells —
   no ECM/ERB/NCM/NRB sub-totals, Total BSV (d/k) or CBSV (L) columns.

---

## 7. §2.3.3 RISK ACCEPTANCE

**Purpose.** Formal, documented acceptance of the resultant risk once the full
SRM process is complete, under the manual's **two-signature** rule and its
delegated-authority table.

**Compliance anchor.** CAAN SRM Manual §2.3.3 — two signature blocks on the
acceptance form:
1. **Team Leader / Safety Manager / Dept. Head** (person with the authority and
   knowledge to ensure the SRM process was followed) — Name, Signature.
2. **Accountable Executive / Department Head or similar** (person with the
   authority to **accept** the resultant risks) — Name, Signature.

Plus §2.3.6.6: accepting authority is graded by the **initial** risk —
Intolerable → Accountable Manager; Tolerable → Risk owner or function/domain
chief; Acceptable → related SAG member / Safety Manager — and "risk acceptance
authority **cannot be delegated**" (`caan_srm.txt:1077-1111`). After acceptance,
continuously monitor barrier and hazard status via the Barrier and Risk Registers
(§2.3.3 note).

**Current implementation.**
- `accept_risk` (`sram_service.py:366-402`): requires `alarp_justification`
  ≥10 chars (`:371-373`); sets `accepted=True`, `alarp_justification`,
  `accepted_by` (resolved to the accepting user's UUID, `:519-549`),
  `accepted_on = now` (`:387`), optional `review_date` (`:388-389`); status →
  `closed` when `in_progress` (`:390`); bow-tie → `Accepted` (`:395-398`).
- Columns on `sram_risk_register` (`db_models.py:1452-1456`): `accepted`,
  `alarp_justification`, `accepted_by` (UUID), `accepted_on`, `review_date`.
- Endpoint `POST /api/v1/sram/risk/accept` (`endpoints/sram.py:218-232`);
  payload `RiskAcceptance` (`:81-86`) accepts `risk_id`, `hazard_id`, `status`,
  `review_date`.

**Gaps.**
1. **Single-signature only.** One `accepted_by`/`accepted_on`; the manual requires
   two distinct blocks (§2.3.3) — a process-conformance signer AND a
   risk-accepting authority signer.
2. **No authority verification.** Nothing maps the registered risk to the
   §2.3.6.6 accepting authority (Accountable Manager / Risk owner-Domain Chief /
   SAG member-Safety Manager); any tenant user may accept any risk, and
   non-delegation is not enforced.
3. **`review_date` doubles as revision/follow-up** — distinct from the manual's
   Close/date and Follow-up columns (Section 9).

---

## 8. §2.3.4 BARRIER REGISTER

**Purpose.** List every barrier applied during SRM with its current status and
follow-up, so barrier health is continuously monitorable after acceptance.

**Compliance anchor.** CAAN SRM Manual §2.3.4 — register columns (nine printed
columns incl. S.N.): S.N., Barrier Description, Hazard Code, SRM Date, Barrier
Type (Control/Recovery), **Barrier Strength (BSV)**, Implementation Status,
Action by whom and when, Follow-up date.

**Current implementation.**
- `barrier_register` (`db_models.py:1478-1517`): `barrier`, `barrier_type`
  (CHECK `:1223-1225`), the 7 BQE score columns + `bsv` (Float),
  `implementation_status` (not_started/in_progress/implemented/verified, CHECK
  `:1227-1229`), `action_by`, `follow_up_date`, `notes`; links `bowtie_id`,
  `control_id`, `hazard_id` (text).
- Rows are materialised by `add_control` (`sram_service.py:252-273`) — every
  bow-tie control also appears in the register; BSV is computed immediately when
  `barrier_scores` are supplied (`:247-250`; `risk_calculator.calculate_bsv`
  `risk_calculator.py:250-291`).
- BSV: 7 BQE scored 1-5; weights Effectiveness 3x, Cost-Benefit 1x, Practicality
  1x, Acceptability 1x, Enforceability 1x, Durability 1x, Disinclination 2x
  (`risk_calculator.py:71-79` — matches §2.3.6.2 items i-vii); BSV = weighted
  total / 10, clamped to 1-5 (`:283`); tier label Strong / Satisfactory /
  Moderate / Weak / Very Weak (`:304-313`).
- API (`endpoints/sram.py`): `GET /barriers` `:239`; `GET /barriers/{hazard_id}`
  `:248` (`get_barrier_register`, `sram_service.py:409-428`);
  `PATCH /barriers/{barrier_id}` `:259` (`update_barrier`, `:477-512` — update
  implementation status / action / follow-up / notes / rescore).

**Gaps.**
1. **BSV banding divergence.** Manual Fig b maps discrete TBQV bands to BSV
   (10-17→1, 18-25→2, 26-33→3, 34-41→4, 42-50→5); implementation computes a
   continuous weighted mean (`weighted_total/10`). Band-relevant inputs can
   differ (e.g. TBQV 26 → manual BSV 3 vs implemented 2.6).
2. **No SRM Date and no S.N./sequence column.** `created_at` is not labelled/used
   as SRM date; "Action by whom and when" is a single `action_by` text with no
   action date.
3. Barriers can only be registered through `add_control` on a bow-tie — no
   standalone barrier-registration route.

---

## 9. §2.3.5 RISK REGISTER

**Purpose.** Provide the whole risk picture of each hazard — original and
resultant risks, status and follow-up — the at-a-glance "safety health" view.

**Compliance anchor.** CAAN SRM Manual §2.3.5 — columns: S.N., Hazard Code, SRM
Date, Consequence(s), Existing Risk (Severity / Probability / Risk Index / Risk
Tolerability), Resultant Risk (same 4), Status (**Open** / **Close/date**),
Follow-up.

**Current implementation.**
- Active register: `sram_risk_register` (`db_models.py:1428-1475`); read via
  `GET /api/v1/sram/risk-register/{tenant_id}` (`endpoints/sram.py:271-277`,
  `sram_service.get_risk_register` `:455-470`). Row shape: current + resultant
  cells (4 each), `status`, `accepted` + `accepted_on` (close), `review_date`
  (follow-up-adjacent); unique per tenant+hazard.
- **Dormant legacy register:** the pre-existing `risk_register` table
  (`RiskRegisterLegacyEntry`, `db_models.py:1379-1425`) carries the manual's
  columns almost exactly — `srm_date`, `ultimate_consequence`, existing/resultant
  severity/probability/risk-index/tolerability, `status`, `follow_up_date`,
  `date_completed`, `remarks`, `concerned_department`; FK `hazard_id →
  hazards.id` (`:1389-1391`). It is **no longer written**: active SRAM flows
  target `sram_risk_register`; the only live references are purge/seed
  bookkeeping (`admin_data_service.py:60,1107,1393`).

**Gaps.**
1. **Register column drift.** The manual §2.3.5 columns (SRM Date, Consequence(s),
   Close/date, Follow-up) are present on the legacy row but absent from the active
   SRAM register (no `srm_date`, no consequence text — consequences live on
   `bow_tie_consequences`; no explicit `follow_up_date`; `created_at` /
   `accepted_on` / `review_date` are partial stand-ins).
2. **Two registers.** Legacy vs SRAM shapes are unreconciled; the platform writes
   and exposes the SRAM shape while the manual's §2.3.5 layout matches the dormant
   legacy shape. UNKNOWN — NEEDS HUMAN INPUT whether `sram_risk_register` should
   absorb the missing columns (SRM date, consequence, follow-up, close-date) so
   the legacy table can be retired.

---

## 10. SCHEMA NOTES — SN1-SN4

Binding decisions carried over from Chunk 2a Q1/Q2/Q6/Q7. None implemented yet.

- **SN1 — `identified_at` (was Q1).** Add `hazards.identified_at` (timezone-aware
  DateTime) distinct from `created_at`: the date the hazard was identified, not
  registered. Populate from the originating report's occurrence/received date
  where the source carries one, else `now` at creation. **PENDING
  IMPLEMENTATION — Chunk 2c (registration).** Decision approved in Chunk 2a.
- **SN2 — `equipment`/`area` (was Q2).** Add a nullable free-text column (e.g.
  `hazards.equipment` / `hazards.area`) for CAAN field (ii) area/operation/
  equipment beyond `function`+`department`. **PENDING IMPLEMENTATION — Chunk 2c
  (registration).** Decision approved in Chunk 2a.
- **SN3 — `follow_up_date` auto-derive (was Q6).** At creation derive
  `follow_up_date` from priority: H → +24h, M → +7d, L → +15d, anchored on
  `identified_at` (SN1), falling back to `created_at`; a manual value always
  overrides; on priority change re-derive **unless** manually overridden.
  Enforcement hardness is Q5 (still open). **PENDING IMPLEMENTATION — Chunk 2c +
  Chunk 2g scheduling.** Decision approved in Chunk 2a.
- **SN4 — `overdue` write is live but a silent no-op (was Q7).** Q7 answered:
  `verification_service.py:123` runs
  `pg.update(Hazard, ..., {"overdue": True, "updated_at": now})`. The branch is
  reachable (outcome `Overdue` is an allowed `VerificationOutcome` value,
  `models/verification.py:11`), but `hazards` has neither an `overdue` column nor
  a JSONB `data` bag (`db_models.py:64-139`), so `pg._split_doc` silently drops
  the key (`pg.py:250-284`) and only `updated_at` is written. The "marked
  overdue" log is misleading and no hazard-overdue state exists. **Decision
  needed before Chunk 2g:** (a) remove the branch, or (b) add a real
  `overdue`/`overdue_since` column and wire the escalation worker to it.
  **PENDING — needs owner decision.**

**Still open from Chunk 2a.** Q3 (hazard-survey adapter), Q4 implementation
detail (support BOTH severity-only and ERC methods while the 5×5 rule stays for
auto-created hazards — mapped in the §2.3.6 chunk), Q5 (24h/7d/15d hard vs
advisory enforcement — affects SN3).

---

*End of Chunk 2b of 7 (Sections 5-10: §2.3.1 bow-tie, §2.3.2 risk profile,
§2.3.3 acceptance, §2.3.4 barrier register, §2.3.5 risk register, schema notes).
§2.3.6 supplementary methods (7-impact-area severity, CBSV probability tables
A-E, discrete BSV banding, tolerability authority enforcement, Q4 prioritization
rules) are referenced above and mapped in the next chunk. This document describes
current state and gaps only — no fixes or implementations are proposed.*