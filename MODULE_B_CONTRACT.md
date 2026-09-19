# MODULE_B_CONTRACT.md — Hazard & Risk Management Module

AviaSAFE SMS Platform — Module B Specification
Status: DRAFT COMPLETE — pending implementation
Chunks 2a-2g delivered (Sections 1-33; Schema Notes SN1-SN17)

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
Safety Management System, **Component 2 — Safety Risk Management**. Text **VERIFIED**
against the shipped Third Edition PDF (`data/an19_cons (4).pdf`), which supersedes
all previous editions on **26 November 2026** (Annex 19 adoption note):
- **Element 2.1 — Hazard identification (2.1.1):** "The service provider shall
  develop and maintain a process to identify hazards, including hazards related
  to internal and external interfaces, associated with its aviation products or
  services." (2.1.2: identification is based on a combination of **reactive and
  proactive** methods.)
- **Element 2.2 — Safety risk assessment and mitigation:** "The service provider
  shall develop and maintain a process that ensures analysis, assessment and
  control of the safety risks associated with identified hazards."

Also anchored in the Third Edition's **Chapter 5 — Development of Safety
Intelligence** (SDCPS built on proactive + reactive collection, §5.2; analysis,
§5.3; protection, §5.4) and **Appendix 3 — Principles for the Protection of
Safety Data, Safety Information and Related Sources** (confidential safety
reporting), which underpin Module B's hazard-intake and reporter-identity
protection obligations (Section 2). Implementation detail follows CAAN SRM
Procedure Manual (First Edition, January 2026) Chapter 2, §2.1-§2.2 (compliance
fields and prioritization, Sections 3-4) and §2.3.x (analysis to acceptance,
Sections 5-17).

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
identity segregation/protection. **GAP — MISSING.** Citation: Annex 19 Third
Edition, **Appendix 3 — Principles for the Protection of Safety Data, Safety
Information and Related Sources** (verified against `data/an19_cons (4).pdf`,
the Third Edition file shipped in this repo).

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
existing/new **recovery measures** (verified, CAAN Manual §2.3.1). Definitions:
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
authority **cannot be delegated**" (verified, CAAN Manual §2.3.6.6). After acceptance,
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

## 10. SCHEMA NOTES — SN1-SN17

Binding decisions. SN1-SN3 carried from Chunk 2a; SN4 CORRECTED in Chunk 2c;
SN5-SN6 finalized in Chunk 2c (§2.3.3/§2.3.6 work); SN7-SN9 NEW (Chunk 2c);
SN10-SN11 NEW (Chunk 2d); SN12 NEW (Chunk 2e); SN13-SN15 NEW (Chunk 2f) and
finalized with SN16-SN17 in Chunk 2g. None implemented yet (all PENDING).

- **SN1 — `identified_at` (was Q1; Chunk 2a).** Add `hazards.identified_at`
  (timezone-aware DateTime) distinct from `created_at`: the date the hazard was
  identified, not registered. Populate from the originating report's
  occurrence/received date where the source carries one, else `now` at creation
  (`hazard_service.py:364`). PENDING.
- **SN2 — `equipment`/`area` (was Q2; Chunk 2a).** Add nullable free-text
  column (e.g. `hazards.equipment` / `hazards.area`) for CAAN field (ii)
  area/operation/equipment beyond `function`+`department`. PENDING.
- **SN3 — `follow_up_date` auto-derive (was Q6; Chunk 2a).** At creation derive
  `follow_up_date` from priority: H → +24h, M → +7d, L → +15d (§2.2
  timelines), anchored on SN1, fallback `created_at`; manual value always
  overrides; on priority change re-derive **unless** manually overridden
  (`hazard_service.py:461-465`). Enforcement hardness is Q5 (still open).
  PENDING.
- **SN4 — Overdue model CORRECTED (was Q7; Chunk 2c).** Owner decision:
  *Hazards have NO overdue state* — a hazard is a condition, not an action
  (CAAN §1.1). The existing no-op is removed: `verification_service.py:122-124`
  (`VerificationOutcome.OVERDUE`, `models/verification.py:11`) writes
  `{"overdue": True}` which `pg._split_doc` silently drops
  (`pg.py:250-284` — no `hazards.overdue` column, `db_models.py:64-139`).
  Delete the branch. Risk-overdue is **DERIVED**: a `sram_risk_register` entry
  is overdue when `review_date` (`db_models.py:1456`) or the linked CAP target
  is past and the entry is not accepted/closed. CAP-overdue is its own
  lifecycle status resolving to **Closed** or **Escalated** — see Section 18.
  Escalation is a separate manual action requiring AE sign-off (Section 18.4).
- **SN5 — Two-signature fields (Chunk 2c).** `sram_risk_register` gains a
  process-conformance signer block (`process_by`/`process_signed_at`) alongside
  the existing accepting signer (`accepted_by`/`accepted_on`,
  `db_models.py:1454-1455`) — CAAN §2.3.3 two-signature rule (Section 17).
- **SN6 — Authority tier enforcement (Chunk 2c).** Acceptance must be gated on
  §2.3.6.6 initial-risk authority (Sections 15-16). `accepted_by` must match the
  required authority for the initial risk level (non-delegable); snapshot
  `initial_authority`/`resultant_authority` at acceptance for audit.
- **SN7 — `first_priority_at` (NEW; Chunk 2c).** Add
  `hazards.first_priority_at`: the instant the initial priority was assigned,
  set once at creation (`hazard_service.py:356` area), **never** re-stamped on
  priority change (unlike `priority_date`, `hazard_service.py:463-465`). Feeds
  AE KPI Q2 (first-action response time; `FIRST_ACTION_KPI_VERIFICATION.md`).
  PENDING.
- **SN8 — CHECK on `hazards.status` (NEW; Chunk 2c).** Status is an enum on
  the Pydantic model (`HazardStatus`, `models/hazard.py:7-13`: Open, Processing,
  Under Review, Pending Closure, Closed, Reopened) but an unconstrained Text
  column (`db_models.py:110`). Add `ck_hazards_status CHECK (status IN ('Open',
  'Processing', 'Under Review', 'Pending Closure', 'Closed', 'Reopened'))` to
  the Hazard `__table_args__` block (`:128-139`). PENDING.
- **SN9 — AE KPI uses `srm_date`; Q3-Q5 decisions (NEW; Chunk 2c).** KPI
  Q1 (SRM started) reads `hazards.srm_date` (`db_models.py:103`) — the
  SRM-completion stamp written by `save_sram`
  (`routes/hazards.py:326-328`, status "Conducted"); NO new `sram_started_at`
  column is introduced. Q3: only literal `status='Open'` = Received. Q4:
  never-actioned hazards included in average, **capped at 30 days**. Q5:
  `is_demo=True` hazards excluded from AE KPI (`db_models.py:118`;
  `demo_scope()` filter). Implementation lives in a new KPI endpoint (Dashboard
  Contract — `FIRST_ACTION_KPI_VERIFICATION.md`).

**Owner decisions accepted in Chunk 2d.**
- **DECISION 1 — §2.3.6.3 CBSV-Likelihood Tables A-E (Section 13).** Accept the
  implementation's equal-width-5-band reading of the CBSV→probability tables
  (ONB/Max verified against Fig c). No schema change. UAT verification against
  the printed table cells is required but does not block.
- **DECISION 2 — §2.3.6.1/§2.3.5 severity sheet (Section 11).** Per-consequence
  7-impact sheet (CAAN §2.3.6.1 Table e) and per-consequence Risk Register row
  (CAAN §2.3.5 "Consequence(s)" column). Captured as SN10.
- **DECISION 3 — §2.3.6.2 BSV (Section 12).** Retire the continuous
  `risk_calculator.calculate_bsv`; keep the discrete `srm_engine` Fig-b banding
  as the single canonical BSV. Captured as SN11.

- **SN10 — `consequence_id` FK (NEW; Chunk 2d, Decision 2).** Add
  `consequence_id` → `bow_tie_consequences.id` (nullable, ON DELETE SET NULL) on
  `sram_risk_register` and the legacy `risk_register`. Each bow-tie consequence
  gets its OWN register row: its own 7-impact severity sheet (CAAN §2.3.6.1),
  severity A-E, probability, risk index, tolerability — matching the §2.3.5 Risk
  Register "Consequence(s)" column. Change the unique key from
  (tenant_id, hazard_id) (`db_models.py:1473`) to (tenant_id, hazard_id,
  consequence_id); consequence_id NULL where a single (whole-hazard) row is kept
  for back-compat. `hazard_id` stays text (`:1441`); the legacy row currently
  holds `ultimate_consequence` TEXT (`:1393`) — new data moves to the FK.
  PENDING IMPLEMENTATION.
- **SN11 — Retire continuous BSV (NEW; Chunk 2d, Decision 3).**
  `risk_calculator.calculate_bsv` (`risk_calculator.py:250-291`, continuous
  weighted mean clamped-1dp) is retired in favour of `srm_engine.calculate_bqv`
  (`srm_engine.py:164-190`) — discrete Fig-b bands (42-50→5 … 10-17→1,
  `BQV_BANDS` `:57-64`). Reroute the three SRAM callers — `add_control`
  (`sram_service.py:248`), `calculate_risk` (`:312`), `update_barrier` (`:493`) —
  to `calculate_bqv` (7 positional element scores; the caller already holds the
  element values) and store the banded BSV on `barrier_register.bsv` (Float,
  `:1499`). Update tests (banded expectations already exist in
  `tests/test_srm_engine.py:100-112`); remove/stop referencing `calculate_bsv`.
  PENDING IMPLEMENTATION.

**Owner decisions accepted in Chunk 2e.**
- **DECISION 1 — EIP mechanics (Section 21).** Persistent status: add `"EIP"`
  to `CAPStatus` (`models/can_cap.py:50-55`) — a stored status, not a
  view/overlay.
- **DECISION 2 — AE identity (Section 22).** A distinct `ACCOUNTABLE_EXECUTIVE`
  role is introduced; the AE role gates escalated CAP decisions and risk
  acceptances (widening from `get_accountable_executive`'s current AIRLINE_ADMIN
  check, `auth.py:245-253`).
- **DECISION 3 — Legacy risk register (Section 9).** Keep `risk_register`
  (`db_models.py:1385`) and `sram_risk_register` (`:1434`) in parallel —
  `risk_register` is explicitly left in place per its own comment (`:1382`).
- **DECISION 4 — Import scope (Section 25).** Full scope (hazards, both risk
  registers, bow-tie, barriers, CAN, CAP) minus demo rows; `is_demo=True` rows
  are excluded (`db_models.py:118`, `isolation.py:15`).
- **DECISION 5 — Import formats (Section 25.3).** Excel (.xlsx) + CSV native,
  both feeding one staging pipeline; legacy .xls optional; reject .xlsm/.xlsb/
  .xltm; no internal Excel-to-CSV converter.

- **SN12 — Historical import provenance and infrastructure (Chunk 2e;
  Decisions 4/5).** New tables — `import_batches` (one per upload; source file,
  format, size, status), `import_rows` (staged rows tagged with entity type,
  validation result, per-row error text), `import_mappings` (per-tenant,
  per-entity/per-sheet column maps; saved templates), `import_links`
  (cross-sheet + cross-batch row links). New columns on `hazards` (`:65`),
  `cans` (`:284`), `caps` (`:379`), `risk_register` (`:1385`),
  `sram_risk_register` (`:1434`), `bow_tie_analyses` (`:1278`),
  `barrier_register` (`:1479`): `imported_at TIMESTAMPTZ`,
  `import_batch_id UUID FK`, `original_row_ref TEXT`. On `hazards` only, also
  `legacy_hazard_code TEXT` (preserves the legacy operator code — CAAN §2.1
  field v, e.g. `OPS/001/M/2026` — distinct from the platform-generated
  `hazard_id`, `db_models.py:68,133`). Historical dates preserved: `created_at`
  reflects the original identification date (§2.1 field i), `imported_at` the
  ingestion moment. PENDING IMPLEMENTATION.

**Owner decisions accepted in Chunk 2g (FINAL).**
- **DECISION 1 — MOR window: category-tiered with tenant default (§30).**
  ICAO Annex 13 categories: **A = 24 h (emergency), B = 72 h (urgent), C = 7
  days, D = 30 days**; the tenant-config default applies when a MOR has no
  category. Updates SN15.
- **DECISION 2 — Triage reversal: reversible with audit (§26).** Reversals
  require the SAFETY_MANAGER capability (AIRLINE_ADMIN/TENANT_ADMIN,
  `config.py:156`), not just a Safety Officer; every reversal writes a new
  `hazard_triage` row with `reversal_of`, `reversal_reason`, `reversed_by`,
  `reversed_at`. Updates SN13.
- **DECISION 3 — SAG/SRB artifacts (§§28-29).** (a) **Shared `action_items`
  table** with `meeting_type` discriminator (`'sag'` | `'srb'`) — SN16. (b)
  **Minutes referenced**: `minutes_ref` (URL/document ID) + optional
  `minutes_summary` text — no embedded document editor.
- **DECISION 4 — Enrichment storage: hybrid (§27).** Structured columns for
  manual enrichment fields (existing `hazards` columns) PLUS
  `hazards.enrichment_data` JSONB (machine feeds — FDM/QAR/ATC) PLUS
  `hazards.enrichment_sources` JSONB (array of source types). Updates SN14.
- **DECISION 5 — Bulletins: new `safety_communications` table (§31).** Status
  draft/review/published/archived, title, body, published_at/by, audience,
  derived_from_hazard_ids; approval by SAFETY_MANAGER. SN17.

- **SN13 — `hazard_triage` table (Chunk 2f/2g). Final:** id (uuid PK),
  tenant_id, hazard_id FK → hazards.id, triaged_by (user_id), triaged_at
  TIMESTAMPTZ, decision enum (Accepted / Rejected / Duplicate / Escalated),
  notes TEXT, initial_priority TEXT (H/M/L, may differ from registration).
  **Reversal fields (Decision 2, 2g):** `reversal_of` UUID FK (self-ref to a
  prior triage row, nullable), `reversal_reason` TEXT, `reversed_by` UUID →
  users.id, `reversed_at` TIMESTAMPTZ. Every triage and every reversal writes
  an `audit_logs` entry (`action="HAZARD_TRIAGED"` /
  `"HAZARD_TRIAGE_REVERSED"`, `db_models.py:1650-1660`). PENDING IMPLEMENTATION.
- **SN14 — Enrichment audit + hybrid storage (Chunk 2f/2g, Decisions 2 + 4).
  Final:** enrichment adds, never replaces the create-only fields
  (`identified_at`, `hazard_code`, `source`, `initial_priority`); every change
  is logged with before/after values via `audit_logs` `action="HAZARD_ENRICHED"`
  in `metadata_json` (`db_models.py:1660`) — a dedicated `hazard_enrichment`
  table only if UAT proves audit_logs too coarse. **Storage (Decision 4, 2g):**
  manual enrichment fields use the existing structured `hazards` columns
  (`description` `:73`, `taxonomy` `:80-81`, `consequence` `:83`, `top_event`
  `:84`, `recommended_action` `:94`, `follow_up_date` `:113`, `remarks` `:116`);
  machine feeds (FDM/QAR/ATC) land in new `enrichment_data` JSONB; source
  provenance in new `enrichment_sources` JSONB (array). PENDING IMPLEMENTATION.
- **SN15 — MOR regulatory timer, category-tiered (Chunk 2f/2g, Decisions 4 +
  1). Final:** new columns on `reports` (`db_models.py:158`):
  `regulatory_category TEXT` (`'A'`/`'B'`/`'C'`/`'D'`, ICAO Annex 13 — A=24h,
  B=72h, C=7d, D=30d), `regulatory_deadline_at TIMESTAMPTZ` = submission +
  category window (tenant-config default if no category is supplied at MOR
  submission), `regulatory_submitted_at TIMESTAMPTZ` (when actually
  transmitted), `regulatory_submission_ref TEXT` (CAA reference). PENDING
  IMPLEMENTATION.
- **SN16 — Shared SAG/SRB action items (Chunk 2g, Decision 3a).** New table
  `action_items`: id, tenant_id, `meeting_type` enum (`'sag'` | `'srb'`),
  meeting_id (FK, polymorphic → sag_meetings/srb_meetings), hazard_id (nullable
  FK → hazards.id), cap_id (nullable FK → caps.id), assigned_to, due_date,
  status, notes, created_at, updated_at. PENDING IMPLEMENTATION.
- **SN17 — Safety communications (Chunk 2g, Decision 5).** New table
  `safety_communications`: id, tenant_id, title, body, `status` enum
  (draft / review / published / archived), `audience` JSONB (roles or 'all'),
  `derived_from_hazard_ids` UUID[] (bulletin ⇄ hazard linkage), published_at,
  published_by, created_at, updated_at. Approval by SAFETY_MANAGER (§31).
  PENDING IMPLEMENTATION.

**Still open from Chunk 2a/2b.** Q3 (hazard-survey adapter); Q4 (ERC support —
mapped in Section 14); Q5 (24h/7d/15d hard vs advisory) affects SN3.

---

## 11. §2.3.6.1 SEVERITY VALUES (7 IMPACT AREAS)

**Purpose.** Derive a single severity value from the 7 weighted impact areas and
persist it numerically (1-5).

**Compliance anchor.** CAAN SRM Manual §2.3.6.1 — seven impact areas: Pax/Public
safety **4x**, Employee/Worker safety **3x**, Product/Service quality **2x**,
Asset/Financial loss **1x**, Reputation loss **1x**, Aviation Security compromise
**1x**, Environmental damage **1x** (verified, §2.3.6.1 item list). Impact levels
0-5 (Nil … Very High). Consolidated Impact Score = Σ(impact level × weight),
range **0-65**, correlated in Table c to Severity Value: **52-65 A**, 39-51 B,
26-38 C, 13-25 D, **1-12 E**; Table d descriptors (E Insignificant …
A Catastrophic).

**Implementation (VERIFIED).**
- Weights `SEVERITY_FACTORS` (`srm_engine.py:25-33`); score
  `4·pax + 3·worker + 2·quality + asset + rep + sec + env` (`:153-155`).
- Discrete bands `SEVERITY_BANDS` (`srm_engine.py:36-42`): 52-65 A, 39-51 B,
  26-38 C, 13-25 D, **0-12 E** — the E band starts at 0 because a NIL score
  (all seven areas zero) is achievable while the manual's Table c prints 1-12;
  boundary note, semantics identical (`calculate_severity` `:138-161`).
- Numeric storage: severity persisted as INTEGER **1-5** (E=1 … A=5),
  `SEVERITY_LETTER_TO_NUMERIC` (`srm_engine.py:115`) applied at save
  (`routes/hazards.py:316`); letters are a display convention
  (`risk_calculator.py:25-53`). DB column `hazards.severity` Integer + CHECK
  1-5 (`db_models.py:86,:49-51`); `sram_risk_register.severity_current/_resultant`
  Integer (`db_models.py:1444,1448`).
- Save route authoritatively recomputes and rejects a severity-letter mismatch
  with the submitted inputs (`routes/hazards.py:277-286`); the impact sheet
  persists inside `sram_data.severity` (`:307-314`).

**Gap.** Bow-tie consequences still carry a single letter per consequence
(`severity_level` A-E, `add_consequence` `sram_service.py:189-195`, CHECK
`db_models.py:1211-1214`) with no impact-score sheet; the 7-impact method
exists only in the SRM workspace. UNKNOWN — needs owner decision whether the
per-consequence sheet is required.

## 12. §2.3.6.2 BARRIER STRENGTH VALUE (BSV)

**Purpose.** Score each barrier's quality elements to a discrete BSV (1-5).

**Compliance anchor.** CAAN SRM Manual §2.3.6.2 — seven barrier quality elements
i-vii with weightage: Effectiveness **3x**, Cost-Benefit 1x, Practicality 1x,
Acceptability 1x, Enforceability 1x, Durability 1x, **Disinclination 2x**; each
element scored 1-5 (Poor…Excellent, Fig a). TBQV = Σ(score×weight), range 10-50;
Fig b maps TBQV to BSV: **42-50→5**, 34-41→4, 26-33→3, 18-25→2, **10-17→1**.
Applied to ECM / NCM / ERB / NRB barrier sets.

**Implementation (VERIFIED).**
- `BQV_FACTORS` (`srm_engine.py:46-54`) and `BQV_BANDS` (`:57-64`) match Fig b
  exactly, plus a defensive unreachable `(0,9)→0 "Ineffective"` band (min TBQV is
  10); `calculate_bqv` (`:164-190`).
- Existing BSV = Σ(ECM.bsv)+Σ(ERB.bsv); CBSV = Existing + Σ(NCM)+Σ(NRB)
  (`evaluate_risk_profile` `:285-290`); `evaluate_barriers`
  (`:252-264`) normalises all four sets. SRM save runs this engine
  (`routes/hazards.py:290-298`).
- Barriers persist with the 7 element scores + `bsv` Float on `barrier_register`
  (`db_models.py:1492-1499`).

**Gap — dual BSV implementations (flagged for Chunk 2d).** The bow-tie control
path (`add_control`/`update_barrier`/`calculate_risk`) still scores with
`risk_calculator.calculate_bsv` — a **continuous** weighted mean
(`weighted_total/10`, clamped-1dp, `risk_calculator.py:250-291`) rather than the
discrete Fig-b bands. e.g. TBQV 26 → manual BSV 3 vs continuous 2.6. The SRM
workspace result is CAAN-aligned and authoritative; decision: retire
`risk_calculator.calculate_bsv` or keep both with documented precedence.

## 13. §2.3.6.3 PROBABILITY / CBSV → LIKELIHOOD

**Purpose.** Classify probability (1-5) from the consolidated barrier strength
(CBSV) for a given severity value.

**Compliance anchor.** CAAN SRM Manual §2.3.6.3, Fig c — Optimum Number of
Barriers per severity: **E→2 (Max CBSV 10), D→3 (15), C→4 (20), B→6 (30),
A→8 (40)**, where Max CBSV = ONB × 5 (max BSV). Each severity uses its own
CBSV-Likelihood table (A-E). Fewer/weaker barriers ⇒ higher predicted
likelihood.

**Implementation (VERIFIED).** `PROBABILITY_CONFIG` (`srm_engine.py:77-83`)
encodes each severity's `(ONB, max, 5 contiguous bands)`; every table splits
0..max into 5 equal-width bands mapping CBSV → probability **5 at CBSV 0**
down to **1 at max**, e.g. A: (0-7,5)(8-15,4)(16-23,3)(24-31,2)(32-40,1);
E: (0-1,5)(2-3,4)(4-5,3)(6-7,2)(8-10,1). `calculate_probability`
(`:193-213`) clamps values to 0..max and bands; `PROBABILITY_DESCRIPTORS`
(`:68-74`) 5 Certain … 1 Extremely Improbable. `evaluate_risk_profile`
(`:296-300`) derives initial/resultant probability from Existing BSV vs CBSV.
ONB/Max column values match Fig c exactly. Probability persisted INTEGER 1-5
(`hazards.probability` `db_models.py:87`; `sram_risk_register`
`probability_current/_resultant` `:1443,1447`).

**UNKNOWN — NEEDS HUMAN INPUT.** The manual's Tables A-E are embedded figures
and cannot be machine-read; the equal-width-5-band split is the implementation's
canonical reading of §2.3.6.3 (Fig c numbers match). Confirm against the printed
table cell values before Module B UAT.

## 14. §2.3.6.4 RISK MATRIX

**Purpose.** Combine probability (1-5) × severity (A-E) into the 5×5 risk matrix
and the risk index.

**Compliance anchor.** CAAN SRM Manual §2.3.6.4 — "Determine the risk matrix of
consequence of hazard considering the Probability and Severity Values"
(matrix figure).

**Implementation (VERIFIED).**
- 5×5 grid. Severity stored numerically (E=1…A=5); risk index =
  probability × severity (1-25); display form "pS" e.g. 4C. Comment chain
  `db_models.py:1429-1432`, `risk_calculator.py:25-53` (`SEVERITY_TO_VALUE`).
- `get_risk_matrix` (`risk_calculator.py:155-177`) — numeric severity +
  `risk_index = prob × sev` + letters + tolerability + colour;
  `build_risk_matrix` all 25 cells (`:219-243`); `normalize_severity` accepts
  A-E or 1-5 (`:88-100`).
- Persisted: `hazards.severity/probability/risk_index` with CHECKs
  (`db_models.py:49-54,:86-88`); `sram_risk_register` current/resultant cells +
  1-25 index CHECKs (`:1465-1472`). SRM save writes `sev_num × prob`
  (`routes/hazards.py:316-325`).
- Legacy risk_index used for auto-prioritization (`routes/occurrence_reports.py:356-365`).

## 15. §2.3.6.5 RISK TOLERABILITY

**Purpose.** Classify each matrix cell Intolerable / Tolerable / Acceptable.

**Compliance anchor.** CAAN SRM Manual §2.3.6.5 — risk tolerability table
(coloured matrix figure).

**Implementation (VERIFIED — both engines agree).**
- `risk_calculator.py:55-59`: Intolerable = 5A-5C, 4A-4B, 3A; Tolerable =
  5D-5E, 4C-4E, 3B-3D, 2A-2C, 1A; Acceptable = 3E, 2D-2E, 1B-1E. Colours
  red/yellow/green (`:61-65,:203-216`).
- `srm_engine.TOLERABILITY_MATRIX` (`srm_engine.py:87-99`) — identical 25-cell
  mapping; projected to the 3-tier operator tolerance tier
  (Acceptable→LOW, Tolerable→HIGH, Intolerable→VERY HIGH, `:109-113`).
- Persisted: `sram_risk_register.tolerability_current/_resultant`
  (`db_models.py:1446,1450`); `hazards.tolerability_tier` (`:91`,
  recomputed on severity/probability change `hazard_service.py:482-491`).

**Status.** IMPLEMENTED + VERIFIED against §2.3.6.5 as read from the figure.

## 16. §2.3.6.6 ACCEPTANCE AUTHORITY (SIGNOFF)

**Purpose.** Enforce the accepting authority for the resultant risk, graded on
the **initial** risk; authority is non-delegable.

**Compliance anchor.** CAAN SRM Manual §2.3.6.6 — mitigation rule (apply the
optimum number of barriers; mix preventive + recovery controls; address all
threats; no duplicated barriers) and the accepting-authority table by **initial**
risk: Intolerable → **Accountable Manager**; Tolerable → **Risk owner or
function/domain chief**; Acceptable → **Related SAG member / Safety Manager**;
"Risk acceptance authority **cannot be delegated**. While determining the
authority to accept the risks, the initial level of risks should be duly
considered." (verified §2.3.6.6).

**Implementation (VERIFIED).**
- `SIGNOFF_AUTHORITY` (`srm_engine.py:101-105`): Intolerable→Accountable
  Manager; Tolerable→Risk Owner / Functional Chief; Acceptable→Safety Manager /
  SAG Member.
- `evaluate_risk_profile` returns `initial_authority` + `resultant_authority`
  keyed on initial/resultant tolerability (`:321-325`); `save_sram` defaults the
  sign-off block from the resultant risk (`routes/hazards.py:300-305`).

**Gap.** `accept_risk` (`sram_service.py:366-402`) records whoever authenticates;
nothing validates the accepting user's role against the §2.3.6.6 table (SN6) and
non-delegation is documented, not enforced. Acceptance always uses resultant
tolerability, so the initial-risk authority in §2.3.6.6 is not the enforcing key.

## 17. §2.3.3 TWO-SIGNATURE RISK ACCEPTANCE MODEL

> Note on the label: the CAAN manual has **no** subsection "2.3.3a" — the
> acceptance form is §2.3.3 "Acceptance of Risk" carrying two signature blocks
> (reinforced by §2.3.6.6). "§2.3.3a" is used here as an internal work-item label.

**Compliance anchor.** CAAN SRM Manual §2.3.3 — acceptance form with **two**
named signature blocks (verified):
1. **Team Leader / Safety Manager / Dept. Head** — the person with the authority
   and knowledge to ensure the SRM process was duly followed — Name, Signature.
2. **Accountable Executive / Department Head or similar** — the person with the
   authority to **accept** the resultant risks — Name, Signature.
Manual note: after acceptance, continuously monitor barrier implementation and
hazard status via the Barrier Register (§2.3.4) and Risk Register (§2.3.5).

**Current state — SINGLE signature (Section 7).**
- `sram_risk_register`: `accepted`, `alarp_justification`, `accepted_by` (UUID),
  `accepted_on`, `review_date` (`db_models.py:1452-1456`).
- `accept_risk` writes one `accepted_by` resolved from the authenticated user
  (`sram_service.py:384-393`; `_resolve_user_uuid` `:519-549`). `RiskAcceptance`
  payload has **no signature fields** (`endpoints/sram.py:81-87`). There is no
  process-conformance signer and no captured signature artefact.
- Two-signature patterns already exist elsewhere as reference: Can
  `issued_by_signature_*` + `reviewed_by_signature` (`db_models.py:323-331`);
  Cap `po_signature_*` / `ma_signature_*` (+ `ae_signature` for escalation,
  `:441-469`).

**Contracted change (SN5 + SN6, Chunk 2c+).**
- Add a second signer block to `sram_risk_register`: process-conformance signer
  (authority + knowledge, block 1 of §2.3.3) parallel to the existing accepting
  signer (authority to accept, block 2 of §2.3.3). Both blocks capture name,
  signature (image/hash/verified), and timestamp — reuse the Can/Cap signature
  column pattern.
- Snapshot `initial_authority`/`resultant_authority` (§2.3.6.6) at acceptance so
  the recorded authority maps to the **initial** risk.
- Extend `RiskAcceptance` (`endpoints/sram.py:81-87`) with signer fields;
  enforce non-delegation — the accepting signer must be the §16 authority for the
  initial risk level.

**Status.** GAP — MIGRATION NEEDED (single → two-signature).

## 18. §2.2 OVERDUE MODEL (CORRECTED)

**Purpose.** Define "overdue" precisely per entity, replacing the current
hazard-level no-op. Binding owner decisions (Chunk 2c); corrects SN4/Q7.

**Compliance anchor.** CAAN SRM Manual §1.1: a hazard is a **condition** — "a
condition or an object with the potential to cause or contribute to an aircraft
incident or accident" (verified). Conditions are not actioned and carry no
overdue state; overdue applies to the actions raised from them (CAN/CAP) and to
risk-register review. The platform models four DISTINCT overdue concepts:

**18.1 — Hazard: NO overdue state (condition, not action).**
Remove the misleading escalation branch: the verification OVERDUE outcome
(`verification_service.py:122-124`; `VerificationOutcome.OVERDUE`
`models/verification.py:11`) writes `{"overdue": True, ...}` which
`pg._split_doc` silently drops — `hazards` has no `overdue` column and no JSONB
`data` bag (`db_models.py:64-139`; `pg.py:250-284`) — so the "marked overdue" log
is false. Delete the branch. Also delete dead code `workers/escalation_worker.py`
(never imported): it writes `Can.status="Overdue"` — a value outside the CAN
vocabulary (`models/can_cap.py` CanStatus uses "Escalated") — plus an
`overdue_at` column that does not exist on `Can` and is silently dropped
(`escalation_worker.py:71-75`).

**18.2 — Risk-register OVERDUE: DERIVED.**
A `sram_risk_register` entry is overdue when its review is due but not done:
`review_date` (`db_models.py:1456`) or the linked CAP target is in the past and
the entry is not accepted/closed (`status in open/in_progress` and
`accepted=False`, `db_models.py:1451-1452`). No stored flag; computed in the
risk-register read model (Chunk 2d).

**18.3 — CAP OVERDUE: resolving status.**
`escalation_service.check_tenant_overdue` (`escalation_service.py:45-122`): CAN
past target and status not Closed → **Escalated** (`:70`); CAP past target and
not Completed/Overdue → **Overdue** (`:97`; `CAP_TERMINAL_STATUSES = {"Completed",
"Overdue"}` `:31`). Contracted change: CAP "Overdue" is an **intermediate**
status that must resolve — the CAP is either completed (→ Closed) or escalated to
an AE sign-off (→ Escalated). Terminal stop set = {Completed, Closed, Escalated}.

**18.4 — Escalation: SEPARATE MANUAL ACTION with AE sign-off.**
Escalation is not an automatic terminal state; it is a deliberate management
action recorded with Accountable-Executive sign-off: `caps.escalated_to_ae`,
`escalated_by`, `escalated_at`, `escalation_reason`, `ae_signature`, `ae_signed_at`
(`db_models.py:437-444`). The daily auto task detects lateness
(`escalation_service.py:45-122`, wired `POST /api/v1/admin/tasks/check-overdue`
`routes/admin.py:808-809`) but the AE decision itself is a manual, audited
acceptance (audit actions `CAN_ESCALATED`/`CAP_OVERDUE`,
`escalation_service.py:71-81,98-109`).

**18.5 — Corrective actions (Chunk 2c/2g):**
1. Delete the OVERDUE no-op branch `verification_service.py:122-124`.
2. Delete the dead worker `workers/escalation_worker.py` (unreferenced).
3. Keep `VerificationOutcome.OVERDUE` (`models/verification.py:11`) as the
   verification reviewer's manual rejection signal — it no longer writes
   `hazards`.
4. CAP overdue handling: make "Overdue" resolve to Closed/Escalated (§18.3).

**18.6 — Contract intent.** The four concepts — hazard condition / risk-review
overdue / CAP overdue / escalation — are DISTINCT and must not be collapsed into
one flag. Every API/UI "overdue" surface must name the entity it qualifies.

---

## 19. §2.4 CAN (CORRECTIVE ACTION NOTICE)

**Purpose.** Issuing a Corrective Action Notice against a hazard assigns ownership
of the required fix (who, by when, with what priority) and records the initial
risk assessment at issuance (per the §2.3.6 methods).

**Compliance anchor.** The shipped CAAN SRM Procedure Manual has **NO §2.4/§2.5** —
its Chapter 2 covers §2.1, §2.2, §2.3 (with §2.3.1-§2.3.6 only); "corrective
action" appears solely as hazard-registration field (x) (YES/NO — whether the
hazard can be eliminated by conventional corrective action) and in remarks (xiv).
CAN is therefore a **platform-level extension** implementing the corrective-action
concept of **ICAO Doc 9859** (prevention of recurrence) and Annex 19 Element 2.2
(control of safety risks). The code itself models the operator form (Buddha Air
FORM SMSM 8.8.2 issuance block, `can_cap_service.py:453-460`).

**Current implementation (VERIFIED).**
- `cans` table (`db_models.py:283-354`): `can_reference` `CAN-YY-NNN`
  (`generate_can_reference` `:57-59`, sequence `_next_reference_seq` `:67-84`,
  unique (tenant_id, can_reference) `:348`); `hazard_id` is a real FK →
  hazards.id (`:289-291`).
- `CanCapService` (`can_cap_service.py:287`): `issue_can` (`:353-479`) resolves /
  auto-stubs the hazard (`_resolve_hazard` `:230-276`), canonicalises the initial
  SRA server-side (`classify_sra` `:311-338`), sets `status="Open"` (`:445`) and
  the linked hazard → `Processing` (`:466`).
- Statuses: `CANStatus` enum Open / Under Review / Closed / Escalated
  (`models/can_cap.py:43-47`); stored as unconstrained Text (`db_models.py:307`);
  `Escalated` is written by the daily overdue scan (`escalation_service.py:70`).
- Initial SRA: severity / probability / index / level / outcome / tolerability +
  `initial_sra` JSONB (`db_models.py:312-318`), 5×5 risk matrix per §2.3.6.4.
- Two-signature issuance block: `issued_by_signature` + `reviewed_by_signature`
  JSONB (`db_models.py:323-331`) — the §2.3.3 two-signature reference pattern.
- API (`app/routes/can_cap.py`, mounted `/api/v1` `main.py:245`): `POST /cans/`
  issue (`get_safety_manager` `:19-48`); `GET /cans/` list + filters `:51-89`;
  `GET /cans/stats` `:92-101`; `GET /cans/{id}` `:141-151`;
  `PATCH /cans/{id}/status` (`get_safety_manager` `:154-174`);
  `DELETE /cans/{id}` (`get_safety_manager` `:177-206`). Stats bucket Open /
  Under Review / Closed (`can_cap_service.py:1053`).

**Gaps.**
1. **No status CHECK** on `cans.status` — the table checks cover only priority /
   severity / probability / index (`db_models.py:343-354`); `update_can_status`
   (`:607-622`) writes any string.
2. **Hazard status write bypasses `HazardService`**: directly set to `Processing`
   (`can_cap_service.py:466`, `_set_hazard_status` `:481-490`) with no
   `status_date` stamp (HazardService stamps it `hazard_service.py:449-465`) —
   drift risk for the SN9 KPI source data.
3. **Auto-stub hazards**: an unresolved reference creates a stub hazard row
   (`_resolve_hazard` `:255-276`, `source="CAN"`) that can pollute hazard KPIs.
4. CAN terminal state is `Closed` alone (`CAN_TERMINAL_STATUSES`
   `escalation_service.py:30`); completion flows through the CAP (§20).

**Specification.** Keep the CAN lifecycle + FORM SMSM 8.8.2 block; add a
`ck_cans_status` CHECK mirroring `CANStatus`; route hazard-status changes through
HazardService; flag stub hazards for exclusion from SN9-style KPIs.

**Implementation note.** NEXT (bundled with the §20 service refactor).

**Open questions.**
- Reject an unresolved CAN hazard reference instead of stubbing?
- Should `reviewed_by_signature` be a true two-phase gate (issue is blocked until
  block 2 signs), or recorded at issuance only?

## 20. §2.5 CAP (CORRECTIVE ACTION PLAN)

**Purpose.** The CAP answers the CAN: root cause, the planned corrective /
preventive actions, the residual risk after mitigation, and the sign-off chain —
feeding closure and the AE governance flow (§§21-22).

**Compliance anchor.** Same as §19: no CAAN §2.5 exists; CAP is a platform-level
extension aligned with Doc 9859 corrective-action procedures and Annex 19
Element 2.2, modeled on the operator form (Buddha Air FORM SMSM 8.8.2 submission
and sign-off blocks, `can_cap_service.py:739-761,938-963`).

**Current implementation (VERIFIED).**
- `caps` table (`db_models.py:378-472`): `cap_reference` `CAP-YY-NNN`
  (`generate_cap_reference` `:62-64`); `can_id` FK → cans.id (`:384-386`);
  `target_completion_date` NOT NULL (`:393-395`); FORM SMSM block
  (`:409-422`); residual SRA fields + `residual_sra` JSONB (`:424-430`);
  RCA (`root_causes`/`action_items` JSONB, `rca_method` CHECK
  bow_tie|fishbone `:361-363`); `sram_data` JSONB (`:435`); the **AE escalation +
  sign-off block** `escalated_to_ae`/`escalated_by`/`escalated_at`/
  `escalation_reason`/`ae_signature`/`ae_signed_at`/`ae_review_interval_days`
  (CHECK 1-365 `:373-375`)/`ae_review_date` (`:437-444`); closure block + image
  signatures (`:446-469`).
- `submit_cap` (`can_cap_service.py:643-782`): status `"In Progress"` (`:732`),
  CAN → `Under Review` (`:766`); residual SRA canonicalised via `classify_sra`.
- `review_cap` (`:917-1034`): takes `CAPReview` (`models/can_cap.py:277-280`)
  with `status: CAPStatus`; writes managerial/CAA sign-offs, RCA, escalation
  block, AE signature (derives `ae_review_date` from
  `ae_review_interval_days` `:1005-1009`); `Completed` stamps
  `closed_by/closed_at/closed_signature`, CAN → `Closed`, hazard → `Under Review`
  (`:1011-1028`).
- `CAPStatus` enum In Progress / Under Review / Completed / Revision Required /
  Overdue (`models/can_cap.py:50-55`); **no EIP** (§21). Stored as unconstrained
  Text (`db_models.py:400`) — **no status CHECK**.
- API (`routes/can_cap.py`): `POST /cans/{can_id}/caps` submit
  (`get_responsible_manager` `:211-244`); `GET /cans/{can_id}/caps` `:247-255`;
  `GET /caps` all-CAP list `:104-138`; `GET /caps/{cap_id}` `:258-268`;
  `PATCH /caps/{cap_id}` (`get_responsible_manager` `:271-292`);
  `PATCH /caps/{cap_id}/review` (`get_safety_manager` `:295-322`);
  `PATCH /caps/{cap_id}/status` (`get_responsible_manager` `:325-345`).
  Stats bucket In Progress / Under Review / Completed / Revision Required /
  Overdue (`can_cap_service.py:1088`).

**Gaps.**
1. **No status CHECK** — a reviewer may set any CAPStatus, incl. `Overdue`
   manually and back to `In Progress`; `Overdue` also arrives from the daily scan
   (`escalation_service.py:97`).
2. **`Overdue` treated as terminal** in the scan (`CAP_TERMINAL_STATUSES`
   `:31`) and never auto-resolves — contradicts §18.3 (Overdue must resolve to
   Closed/Escalated).
3. **AE actions run through the generic review surface** (`get_safety_manager`)
   with no AE-role gate and no EIP status (§§21-22) — a tenant admin can
   "Complete" or "Revision-Required" an escalated CAP.

**Specification.** Add `ck_caps_status` (incl. `EIP` once §21 lands); make
`Overdue` resolve to Closed/Escalated (§18.3); gate escalated-CAP decisions on
the AE terminal rule (§22).

**Implementation note.** NEXT (service refactor bundling §19).

**Open questions.** None beyond §§21-22.

## 21. EIP STATE (ESCALATED-IN PROGRESS)

**Purpose.** Give an AE-acknowledged escalated CAP a first-class monitoring state:
the AE has taken ownership, the work continues, and the Safety Department can
administer the resulting out-of-normal cycle.

**Design (platform-owner intent).**
- When a CAP is escalated and the AE acknowledges, it becomes **EIP**.
- The AE **cannot reject** — only acknowledge, provide a reason, and continue.
- EIP items remain visible until resolved (**Closed** or **further-escalated**).
- **No time limit** — EIP can last as long as needed.
- Safety Department monitors EIP items as an administrative cycle.

**Current implementation (VERIFIED).** No EIP state anywhere
(`OVERDUE_MODEL_VERIFICATION.md:33`, grep `EIP` → 0 hits).
- `CAPStatus` has no EIP (`models/can_cap.py:50-55`).
- Escalation is an orthogonal flag + sign-off block on `caps`
  (`db_models.py:437-444`); an escalated CAP keeps its status
  (`OVERDUE_MODEL_VERIFICATION.md:99-103`).
- The demo AE surface already models "no reject": its only decisions are
  `authorize` / `accept_risk` (`routes/demo.py:123-124`), overlaying
  `result_status` "In Progress" (`:137`).
- `get_cap_stats` has no EIP bucket (`can_cap_service.py:1088-1094`);
  `caps.html` has no EIP badge.

**Specification.**
- Add `EIP = "EIP"` to `CAPStatus` (`models/can_cap.py:50-55`) and to the new
  `ck_caps_status` CHECK (§20). `review_cap` ("AE acknowledge") sets status EIP
  when escalation is acknowledged; AE continue/direct returns it to
  In Progress / Completed / Escalated.
- `get_cap_stats` gains an EIP bucket (`can_cap_service.py:1088`); the register
  badge set grows (§24).
- No deadline math: EIP has no expiry (owner design) and is exempt from the
  daily overdue scan's CAP branch (`escalation_service.py:94`).

**Implementation note.** NEXT — with the §22 AE surface; PENDING until then.

## 22. AE ESCALATION AND TERMINAL DECISION RULE

**Purpose.** Enforce the Accountable Executive's terminal decision on escalated
CAPs and on risk acceptances (§2.3.6.6 non-delegability).

**Compliance anchor.** CAAN Manual §2.3.6.6 — the accepting authority for
Intolerable risks is the **Accountable Manager/Executive**, and "risk acceptance
authority **cannot be delegated**". Doc 9859 assigns the AE the accountability
for the SMS.

**Design (platform-owner intent).**
- AE is the Accountable Executive (Doc 9859 role).
- AE **cannot reject** a CAP — only acknowledge (→ EIP), direct, or continue.
- AE's decision is **terminal** (no further escalation possible).
- AE's write surface is **narrow**: escalated CAPs + risk acceptances only.
- **Non-delegability**: no one else may sign on the AE's behalf.

**Current implementation (VERIFIED).**
- Escalation block exists (`caps` `db_models.py:437-444`); written by any
  safety-manager via `review_cap` (`can_cap_service.py:957-1009`).
- `get_accountable_executive` exists (`auth.py:245-253`, requires AIRLINE_ADMIN
  or CAAN roles) but is applied **only** to the closure route
  (`routes/verification.py:76`) — never to CAN/CAP. CAN/CAP review is gated on
  `get_safety_manager` / `get_responsible_manager` (`auth.py:182-241`).
- **Role conflation**: `AIRLINE_ADMIN` is simultaneously the tenant admin /
  Safety Manager and the AE stand-in (config.py:16-17 — "Canonical tenant admin
  (Safety Manager); AIRLINE_ADMIN is its legacy alias"). No distinct
  ACCOUNTABLE_EXECUTIVE role exists.
- The demo AE overlay works (demo-only): `POST /api/v1/demo/session/decision`
  `authorize`/`accept_risk` (`routes/demo.py:114-163`), never a reject.
- Risk acceptances: `accept_risk` (`sram_service.py:366-402`) records the
  authenticated user with no AE gate (Sections 7/16).

**Gaps.**
1. **Terminal rule NOT enforced.** A reviewer (any tenant-admin role) can set an
   escalated CAP to `Revision Required` (reject-like) or `Completed`, and can
   sign `ae_signature` — there is no AE-role gate and no immutability after the
   AE decision.
2. **No non-delegability check.** Nothing verifies the AE identity/role when
   `ae_signature` is captured (SN6 pattern).
3. **Write surface is NOT narrow.** Safety managers act on the full CAP/risk
   surface with the same role used for AE decisions.

**Specification.**
- AE decisions are terminal: after `ae_signature`/EIP, the CAP may only resolve
  to Closed/Escalated (§18.3); no recall to revision.
- Gate escalated-CAP decisions with `get_accountable_executive`
  (`auth.py:245-253`); capture AE name + signature + timestamp (reuse the
  `ae_signature` JSONB block `db_models.py:441`).
- Decide a distinct AE identity (role claim or user flag) in Chunk 2f; until
  then record the AE as an audited identity, never inferred from a shared role.
- Risk acceptance mirrors the same AE gate (§2.3.6.6, SN6).

**Implementation note.** NEXT (Chunk 2e/2f build) — PENDING.

## 23. AE DASHBOARD ACTION QUEUES

**Purpose.** Document the data-model requirements for the AE dashboard (built in
a later chunk) so its two queues can be served without schema surprises.

**Queue 1 — Escalated CAPs awaiting acknowledgement.** CAPs with
`escalated_to_ae=true` and `ae_signature IS NULL` (`db_models.py:437-442`).
**Queue 2 — Risk acceptances awaiting AE signature.** SRAM entries with
`accepted=false` (status open/in_progress, `sram_risk_register` `db_models.py:1451-1452`),
filtered to the §2.3.6.6 authority tier of the initial risk (SN6).

**Current implementation (VERIFIED).** No dedicated queue endpoints.
- Queued data is partly fetchable: `GET /api/v1/caps` returns `escalated_to_ae`,
  `escalated_by`, `escalated_at`, `escalation_reason`, `ae_signature` (boolean),
  `ae_review_date` + barrier health aggregate (`routes/can_cap.py:528-538`) but
  has **no `escalated_to_ae` filter**; the status filter only (`:104-138`,
  `list_all_caps` `can_cap_service.py:832-833`).
- Risk register read: `GET /api/v1/sram/risk-register/{tenant_id}`
  (`endpoints/sram.py:271`); accept: `POST /api/v1/sram/risk/accept`
  (`:218`). No "pending acceptance" list surfaced.
- Demo AE session overlay exists (demo-only): `routes/demo.py:114-163`,
  `demo/session_manager.py:137-183`.

**Specification.**
- Queue endpoints (later chunk) filter on the two predicates above; no new
  columns required beyond SN5/SN6/SN10 (signature blocks + authority snapshot +
  consequence rows).
- Include `days_overdue` (§24) and the §18 overdue derivation in Queue 1 rows.

**Implementation note.** DEFERRED to the dashboard build (Chunk 2f).

## 24. CAN-CAP REGISTER

**Purpose.** The register shows CANs and CAPs with their statuses; overdue CAPs
carry the **Overdue** badge, and `days_overdue` is a computed display column
(§18 — never stored).

**Current implementation (VERIFIED).**
- CAP register: `public/can_cap/caps.html` — Status column (`:85`), badge via
  `capStatusBadgeClass(c.status)` (`:178-183`), filter fed by `stats.caps.by_status`
  (`:202-205`, confirmed in OVERDUE_MODEL_VERIFICATION.md:106-118). CAN register:
  `public/can_cap/cans.html`.
- Backend lists return raw `status`: `GET /caps` (`routes/can_cap.py:104-138` →
  `list_all_caps` `can_cap_service.py:806-880`, status filter `:832-833`); stats
  bucket `Overdue` (`:1088-1094`).
- `days_overdue` is computed **on the fly for reminder emails only**
  (`email_service.py:364,623-628`); **not stored, not displayed**.

**Gaps.**
1. **No `days_overdue` in any list/register view** (`OVERDUE_MODEL_VERIFICATION.md:115-118`).
2. No EIP badge until §21 lands; register filter/stat lists are hard-coded to the
   current `CAPStatus` set.
3. Register joins only via `list_all_caps` (CAP-CAN-hazard triple select
   `can_cap_service.py:820-829`); CAN register lacks a `latest CAP status`
   column.

**Specification.**
- Keep **Overdue** as a status; add **`days_overdue`** as a read-time display
  column on `GET /caps` and the list item (`_to_cap_list_item`
  `routes/can_cap.py:506-538`): `days_overdue = now − target_completion_date`
  when status = Overdue (else null), matching the email math
  (`email_service.py:364`).
- Extend badge/filter sets for EIP (§21) and keep `days_overdue` out of storage
  (derived per §18).

**Implementation note.** NEXT (with §21).

---

## 25. HISTORICAL IMPORT

**Purpose.** The front door for a new tenant to onboard existing safety records
when their platform tenant is provisioned: the historical hazard register, risk
registers, bow-tie analyses and barrier registers (SDCPS-mandated), and
optionally CAN/CAP lifecycle records from a prior SMS tool or a hard-copy regime
(organizational). Its output is Annex 19 §5.2-compliant retention plus
institutional continuity: past decisions and latent vulnerabilities survive the
migration untruncated.

**25.1 - Purpose and scope.**
The Safety Department runs it during tenant onboarding, immediately after tenant
provisioning (`register_tenant()` creates the slugified tenant + primary
AIRLINE_ADMIN administrator, `services/tenant_registration.py:7-10`). It is a
**create** path only — it does not reconcile bidirectional changes with the old
system. All Module B entities are importable per the two-category split of 25.2;
no entity from outside Module B (25.10).

**Current implementation (VERIFIED).** **None — MISSING.** There is no import
code, staging table, or upload endpoint. Greping `backend/` for
`import_batch|staging|upload|xlsx|openpyxl|pandas` yields only export-side
`openpyxl` use (`aggregation_service.py:262-268`, `regulator_dashboard.py:94`)
and deployment-environment naming (`config.py:65`). The pieces that the import
feature can build on exist: multipart parsing (`python-multipart>=0.0.6`,
`requirements.txt`) and a background scheduler (`apscheduler>=3.10.4`, wired in
`app/core/lifecycle.py:18-23`, jobs `:87/:102`).

**Gaps (MISSING — greenfield).** No `import_batches`/`import_rows`/
`import_mappings`/`import_links` tables (SN12); no parser (Excel or CSV); no
content-type/size validation; no staging or promotion service; no re-upload
handling; no review UI; `openpyxl` is not declared as a dependency for parsing
(only the guarded export import, `aggregation_service.py:262-268`).

**25.2 - The two categories (SDCPS vs organizational).**
Two real-world categories, treated differently by this contract (owner Decision 4):

| Entity(s) | Category | Regulatory meaning | Import support | Format | Target table (`db_models.py`) |
|---|---|---|---|---|---|
| Hazards | SDCPS-mandated | Annex 19 §5.2 artifact | **REQUIRED** | Excel / CSV (.xls optional) | `hazards` (`:65`) |
| Risk register (legacy) | SDCPS-mandated | Annex 19 §5.2 artifact (CAAN §2.3.5) | **REQUIRED** | Excel / CSV (.xls optional) | `risk_register` (`:1385`) |
| SRAM risk register | SDCPS-mandated | Annex 19 §5.2 artifact | **REQUIRED** | Excel / CSV (.xls optional) | `sram_risk_register` (`:1434`) |
| Bow-tie analyses (+ threats / consequences / controls) | SDCPS-mandated | Annex 19 §5.2 artifact | **REQUIRED** | Excel / CSV (.xls optional) | `bow_tie_analyses` (`:1278`), `bow_tie_threats` (`:1304`), `bow_tie_consequences` (`:1327`), `bow_tie_controls` (`:1351`) |
| Barrier registers | SDCPS-mandated | Annex 19 §5.2 artifact | **REQUIRED** | Excel / CSV (.xls optional) | `barrier_register` (`:1479`) |
| CANs | Organizational | Internal administrative; Doc 9859 corrective action | **OPTIONAL** | Excel / CSV, or manual post-scan | `cans` (`:284`) |
| CAPs | Organizational | Internal administrative; Doc 9859 corrective action | **OPTIONAL** | Excel / CSV, or manual post-scan | `caps` (`:379`) |

The regulator requires the service provider to maintain SDCPS artifacts, so
hazard/risk import is **mandatory for every tenant**; CAN/CAP are the
organization's own administrative process, so digitizing them is the
organization's call (the platform still provides the capability).

**25.3 - Supported input formats.**
- **Supported:** Excel `.xlsx`; CSV `.csv`.
- **Legacy (optional, behind a per-tenant flag):** Excel `.xls`
  (`application/vnd.ms-excel`).
- **REJECTED before parse:** `.xlsm`, `.xlsb`, `.xltm` — macro-enabled / binary
  formats are a security risk and are blocked on extension **and** content.
- **Content-type validation, not just extension:** the uploaded bytes are
  sniffed — ZIP/OLE2 magic + declared MIME
  (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`,
  `text/csv`, `application/vnd.ms-excel`). Extension/MIME mismatch → rejected.
  Uploads ride the existing multipart path
  (`python-multipart>=0.0.6`, `requirements.txt`).
- **File size limit per upload:** 50 MB default (an uncompressed-xml guard on
  top of the byte cap protects against zip-bombs); tunable per tenant.
- **No internal Excel-to-CSV converter.** `.xlsx` and `.csv` are parsed natively
  by two parsers that emit the same normalized `import_rows` staging shape
  (SN12); one staging pipeline (25.5) consumes both. (`openpyxl` must be added
  to `requirements.txt` as a hard dependency for the native xlsx parser — today
  it appears only under a guarded export import, `aggregation_service.py:262-268`.)

**25.4 - Data mapping (source → platform).**
- **Hazards — canonical target.** The CAAN SRM Manual §2.1 13-field registration
  sheet (elements i-xiii; the contract maps each element to `hazards` columns in
  Section 3, `db_models.py:64-139`). The operator maps each source column to one
  of those fields. Legacy codes (CAAN §2.1 field v, e.g. `OPS/001/M/2026`) are
  preserved on `legacy_hazard_code` (SN12); the platform reference is generated
  at promotion (`hazard_service.py:71-89`).
- **Excel-specific.** Multi-sheet workbooks: the operator maps **each sheet** to
  an entity type (Hazard / Risk Register / SRAM Risk Register / Bow-Tie /
  Barrier / CAN / CAP). Sheet-level mapping templates are saved per tenant
  (`import_mappings`, SN12). Formulas are evaluated — the **value** is used, the
  formula is never stored or promoted. Merged cells and hidden sheets are flagged
  during the parse for operator resolution before staging.
- **CSV-specific.** One file = one sheet = one entity type. Header row required.
  Encoding: UTF-8 default with UTF-8-BOM and Latin-1 fallback detection.
  Delimiter detection: comma default; tab/semicolon via operator override.
- **Both formats.** Per-tenant column mapping templates are saved for reuse.
  Source fields with no platform target are left NULL and flagged for manual
  completion in the review UI (25.9).

**25.5 - Staging and validation pipeline.**
`Upload → Parse → Stage → Validate → Review → Link → Promote`
- **Upload:** multipart POST; content-type + size validation (25.3); an
  `import_batches` row is created.
- **Parse:** native parser (25.3) writes normalized rows tagged with entity type
  into `import_rows`.
- **Stage:** rows are staged only — nothing touches Module B tables yet.
- **Validate (per entity):**
  - Required fields present — hazards per CAAN §2.1 (i-xiii); risk register per
    CAAN §2.3.5; CAN/CAP per §§19-20; etc.
  - Enum values valid — taxonomy (ICAO 4-value CHECK `db_models.py:58-61`);
    priority H/M/L (`:55-57`); hazard status (`models/hazard.py:7-13`);
    CANStatus/CAPStatus (`models/can_cap.py:43-55`); risk-register severity /
    probability / index bands and status (CHECKs `db_models.py:1247-1273`).
  - Hazard code format — `{FUNCTION}/{SEQ:03d}/{PRIORITY}/{YEAR}`
    (`hazard_service.py:71-89`) or a configured per-tenant pattern (CAAN example
    `OPS/001/M/2026`).
  - Date sanity — in sequence; within a reasonable range (future beyond a small
    tolerance or pre-deployment-dates flagged).
  - Duplicates:
    - within a single upload — **blocking** (row rejected);
    - against existing promoted records — **warning + auto-link**
      (`import_links`), operator confirms;
    - cross-sheet within a workbook — **warning + auto-link** (Hazard sheet row
      ↔ Risk-Register sheet row).
- **Review:** operator UI for flagged/warned rows (25.9).
- **Link:** cross-referencing resolve/persist (`import_links`).
- **Promote:** transactional writes into the target tables with provenance
  (25.6). Promotion is never automatic — operator approval required (25.10).

**25.6 - Promotion and provenance.**
Promoted records carry — `imported_at TIMESTAMPTZ`; `import_batch_id UUID FK`;
`original_row_ref TEXT` (sheet+cells, or CSV line); `legacy_hazard_code TEXT`
(hazards only). Historical dates are preserved: `created_at` reflects the
original identification date (CAAN §2.1 field i) — closing the Section 3 field
(i) gap for imported rows — while `imported_at` records the ingestion moment.
Targets: Hazards → `hazards` (`:65`); Risk register → `risk_register` (legacy,
CAAN §2.3.5; `:1385`) and/or `sram_risk_register` (`:1434`) per the sheet
mapping (Decision 3 — both stay in parallel, comment at `:1382`); Bow-tie →
`bow_tie_analyses` + threats/consequences/controls (`:1278`, `:1304`, `:1327`,
`:1351`); Barrier → `barrier_register` (`:1479`); CAN → `cans` (`:284`); CAP →
`caps` (`:379`). Promoted rows are always `is_demo=False` (Decision 4).

**25.7 - Volume handling.**
- Up to **5,000 rows per batch**: synchronous, in the request.
- Above 5,000: **background**, reusing the existing APScheduler
  `BackgroundScheduler` (`app/core/lifecycle.py:18-23`; jobs `:87/:102`;
  `apscheduler>=3.10.4`). The operator polls batch status via `import_batches`.
- **Hard cap: 100,000 rows per batch** — above this the upload is rejected.

**25.8 - Re-upload behavior.**
- Prior batches for the tenant are detected (`import_batches` keyed by tenant +
  source file hash), so re-uploads are visible, not silently duplicate.
- **Blocking** dedup against already-promoted rows (match keys: legacy code /
  reference / unique keys of the target table).
- **Warning** dedup against staged rows still sitting in unapproved batches —
  flagged, operator resolves before promotion.

**25.9 - Error reporting.**
- A downloadable CSV of rejected rows with reasons (one row = one error, plus a
  single-error-per-row summary).
- Per-row error messages persisted on `import_rows`.
- An operator review UI for flagged rows: edit staged values, re-validate,
  approve for promotion.

**25.10 - Boundaries.**
- **Cannot bypass RBAC** — import routes carry the same tenant scoping and role
  gates as the rest of Module B (tenant admin / safety manager,
  `config.py:146-161`).
- **Cannot write outside Module B** — hazards, risk registers, bow-tie, barriers,
  CAN/CAP only. No reports, surveys, users, or tenant metadata.
- **Cannot auto-promote** without operator approval (Review gate, 25.5).
- **Cannot import SMS health surveys** — Module A boundary (surveys
  `db_models.py:506` are out of scope).
- Never modifies demo data (Decision 4; `is_demo` `db_models.py:118`).

**25.11 - Compliance anchor.**
- **Annex 19 Third Edition §5.2 — SDCPS:** a State shall require that its
  service providers establish and maintain the means to collect, store,
  aggregate, process, and enable the analysis of safety data and safety
  information. The historical hazard and risk registers are foundational SDCPS
  artifacts — import is **MANDATORY** for every tenant (Decision 4).
- **CAN/CAP** are organizational extensions — the Doc 9859 corrective-action
  concept, not regulator-mandated SDCPS artifacts — so their import is
  **OPTIONAL** (25.2, Decision 4).
- **Hazard mapping target:** CAAN SRM Manual §2.1 13-field registration sheet
  (elements i-xiii), per Section 3.

**Specification summary.** Greenfield per SN12 (four `import_*` tables + five
provenance columns + `legacy_hazard_code`) and 25.2-25.10 (two formats, one
staging pipeline, six-stage validation, provenance/promotion rules, volume
tiers, re-upload handling, error reporting). No changes to existing Module B
tables beyond the SN12 columns.

**Implementation note (PENDING).** Build order — SN12 schema → native parsers
(+ `openpyxl` as a hard dependency) → staging/validation service → `/import/...`
routes → sync/background promotion → review UI. All PENDING; nothing changes
existing behavior.

**25.12 - Open questions.**
- Upsert semantics: re-imported legacy code that already sits on a promoted row —
  update-in-place vs new row with a warning?
- Who may edit staged rows in review — safety manager only, or any tenant user?
- Legacy risk register: per-sheet choice of `risk_register` vs
  `sram_risk_register`, or import into both by default (Decision 3 parallel
  keep)?
- Background-batch observability: progress events and completion email.
- Digitized CAN/CAP: should scanned attachments (images/PDF) be part of the same
  import batch as the spreadsheet?

---

## 26. TRIAGE

**26.1 - Purpose.** Initial classification of an inbound hazard/report at
registration: decide whether it progresses into SRM, is rejected with a reason,
is a duplicate of an existing record, or needs immediate escalation.

**26.2 - Compliance anchor.** SDCPS workflow — Doc 9859 (analysis of reported
data; safety manager ensures prompt collection/analysis, §9.3.6.6) and Annex 19
Third Edition §5.2. There is no explicit CAAN §2.x section — triage is
operational process between §2.1 registration (Section 3) and §2.2 initial
prioritization (Section 4).

**26.3 - Current implementation (VERIFIED).** **MISSING.** No triage table,
route, or logic exists (grep `triage` across `backend/` → 0 hits). Hazard
creation auto-classifies the initial risk server-side (`create_hazard_v1`
`hazard_service.py:243`, `:250-274`) but there is no human decision gate between
registration and SRM. Hazard statuses are Open / In Progress / Conducted /
Closed etc. (`models/hazard.py:7-13`) with no Rejected/Duplicate states.

**26.4 - Gaps (MISSING — greenfield).** The human triage gate; duplicate
detection + linkage at intake; escalation-notification path; priority override
at intake; audited decisions.

**26.5 - Specification.**
- `hazard_triage` table per SN13.
- Roles: triage by `SAFETY_OFFICER` (`config.py:158`) and the safety-manager
  capability (`AIRLINE_ADMIN`/`TENANT_ADMIN`, `config.py:156`; no literal
  SAFETY_MANAGER role exists — `SAFETY_OFFICER` maps to the UI label
  "safety_manager", `rbac.py:49-61`).
- Decision paths:
  - **Accepted** → proceeds to §2.2 prioritization / SRM (no status change).
  - **Rejected** → hazard closed with reason (decision `notes` on
    `hazard_triage`; hazard status → a rejected/closed state).
  - **Duplicate** → linked to the existing hazard (link stored, hazard closed).
  - **Escalated** → immediate prioritization `H` + notifies the Safety Manager
    (email via `email_service.py`; notification pattern to be built).
- Audit: every triage writes an `audit_logs` entry
  (`action="HAZARD_TRIAGED"`, `db_models.py:1650-1660`).
- API surface: new `POST /api/v1/hazards/{id}/triage` (+ list/GET per hazard).
  No triage route exists today — MISSING.

**26.6 - Open questions.** Can a triage decision be revised after the fact (and
who)? Does Rejected reopen on new evidence? Does Escalated force full SRM or
short-circuit to priority H only?

**Implementation note.** PENDING — greenfield (SN13 first).

---

## 27. ENRICHMENT

**27.1 - Purpose.** Add information to a hazard after registration — flight
data, weather, ATC transcripts, FDM/QAR, maintenance records, crew rosters —
from external systems, so the analysis package is complete.

**27.2 - Compliance anchor.** Doc 9859 SDCPS enrichment phase; §9.3.6.6 (safety
manager responsible for prompt collection and analysis of safety data).

**27.3 - Current implementation (VERIFIED).** **MISSING.** No enrichment
endpoint, audit, or upload path. `PUT /hazards/{id}` (`routes/hazards.py:131`)
is an unguarded full update — it overwrites fields with no create-only guard and
no before/after audit. The hazard fields already exist for most enrichment
targets: `description` (`:73`), `taxonomy`/`taxonomy_specific` (`:80-81`),
`consequence` (`:83`), `top_event` (`:84`), `recommended_action` (`:94`),
`follow_up_date` (`:113`), `remarks` (`:116`), `function`/`department`
(`:71/:100`) — see Section 3 mapping. `identified_at` does not exist (Section 3 
field-(i) gap). There is **no file-upload infrastructure anywhere** (grep
`UploadFile` across `backend/` → 0 hits).

**27.4 - Gaps.** (a) no create-only guard against `PUT` overwrite; (b) no
before/after audit; (c) no attachment upload; (d) no API-import channel for
machine feeds (would reuse the §25 `import_mappings`/per-entity path).

**27.5 - Specification.**
- Enrichment **adds to** an existing hazard, never replaces:
  - **Create-only (never touched by enrichment):** `identified_at`,
    `hazard_code` (= `hazard_id`), `source`, `initial_priority`
    (`priority` + `priority_date`).
  - **Enrichment-allowed:** area/equipment, `description`, `taxonomy`,
    `top_event`, `consequence`, `recommended_action`, `follow_up_date`,
    `remarks`.
  - **Workflow-only:** `status` (moved only by status transitions, never by
    enrichment).
- Every enrichment change writes an `audit_logs` entry
  (`action="HAZARD_ENRICHED"`, before/after in `metadata_json`) — SN14.
- Sources: manual entry by Safety Officer; attachment upload (new upload
  infrastructure — MISSING); API import (batch feeds via §25 machinery).
- New `POST /api/v1/hazards/{id}/enrich` (+ optional
  `POST /api/v1/hazards/{id}/enrich/attachment`).

**27.6 - Open questions.** Attachment size/type limits and storage location
(no S3/upload module exists); whether FDM/QAR feeds land in dedicated columns or
an analysis JSONB blob.

**Implementation note.** PENDING — needs the §25 import plumbing + new upload
infra.

---

## 28. SAG REVIEW (SAFETY ACTION GROUP)

**28.1 - Purpose.** Operational/tactical review of analysis packages. The SAG
decides which line-management actions are needed to implement the SRB's
strategies.

**28.2 - Compliance anchor.** Doc 9859 §9.3.6.9 — SAGs are more operationally
focused, composed of managers and front-line personnel, chaired by a designated
manager; they monitor operational safety performance, review safety data,
identify control strategies and ensure employee feedback.

**28.3 - Current implementation (VERIFIED).** **PARTIAL.** No SAG meetings or
action-item artifact (grep `sag_meetings|sag_action_items` → 0 hits; tables
MISSING). A SAG member list is already configured on tenant data (`sag_members`,
read by `tenant_scheduler.py:269-275`) — the SRB dispatch emails that list — but
no meeting records exist.

**28.4 - Gaps (MISSING).** `sag_meetings`, `sag_action_items`, cadence
scheduling, API surface, role model.

**28.5 - Specification.**
- `sag_meetings`: id, tenant_id, scheduled_at, held_at, attendees JSONB,
  minutes_ref TEXT, status (Scheduled / Held / Cancelled).
- `sag_action_items`: id, meeting_id FK, hazard_id FK (nullable), cap_id FK
  (nullable), assigned_to, due_date, status, notes.
- Cadence: **quarterly default**; per-tenant override in `tenants.data`
  (`db_models.py:1565`) — Decision 3.
- API: `POST /api/v1/sag/meetings`, `GET /api/v1/sag/meetings`,
  `PATCH /api/v1/sag/meetings/{id}`, `POST /api/v1/sag/action-items`,
  `PATCH /api/v1/sag/action-items/{id}`.
- Roles: `SAFETY_MANAGER` capability (AIRLINE_ADMIN/TENANT_ADMIN,
  `config.py:156`) + new `SAG_MEMBER` literal role (add to `config.py` role
  lists; none exists today).

**28.6 - Open questions.** `SAG_MEMBER` provisioning vs free-form attendees;
does a SAG action item feed a CAP (linkage to §20)?

**Implementation note.** PENDING.

---

## 29. SRB REVIEW (SAFETY REVIEW BOARD)

**29.1 - Purpose.** Strategic governance body: sets SPIs/SPTs, allocates
resources, approves acceptance of significant risks, monitors SMS effectiveness.
**Cadence: 6-monthly** (Decision 3; Doc 9859 §9.3.6.8 "at least twice a year"
owner reading — code has no such statement).

**29.2 - Compliance anchor.** Doc 9859 §9.3.6.8 — the highest-level safety
committee includes the accountability holder (AE) and senior managers, with the
safety manager advisory; it is strategic and monitors SMS effectiveness, timely
risk-control implementation, safety performance and mitigation-strategy
effectiveness.

**29.3 - Current implementation (VERIFIED).** **Infrastructure exists; cadence
mismatch to reconcile.**
- Monthly SRB**-report** dispatch job: `lifecycle.py:38-45` (entry),
  registered `:101-114` (1st of month 00:00 NPT), worker
  `tenant_scheduler.py:49-91` — this is a **monthly report-email mechanism**
  that builds a report payload (`:166`), renders a PDF
  (`TenantPdfGenerator.build_srb_report_pdf` `:102`), and emails recipients from
  `safety_manager` + SAG list (`:269-280`). Manual dispatch also exists
  (`routes/api/v1/tenant_reports.py:111-141`).
- This is NOT an SRB meeting record: no `srb_meetings` table, no attendance, no
  minutes, no AE chair. The SRB itself is **6-monthly** (D3); the monthly job
  name/cadence must be reconciled with the SRB cadence.
- The AE must chair per §22 — `get_accountable_executive` (`auth.py:245-253`)
  is currently wired only to verification closure (`routes/verification.py:76`).

**29.4 - Gaps.**
1. Monthly dispatch job contradicts the 6-monthly SRB cadence (Decision 3) —
   rename/reschedule to SRB cadence; keep the PDF report as the pre-meeting
   briefing.
2. No `srb_meetings` artifact; SRB actions not linked to escalated CAPs (§21
   EIP) or accepted risks.
3. SAG + SRB recipients are conflated in one email list.

**29.5 - Specification.**
- `srb_meetings`: id, tenant_id, scheduled_at, held_at, attendees JSONB,
  minutes_ref, status — chaired by the AE (`get_accountable_executive`,
  `auth.py:245-253`), safety manager advisory (Doc 9859 §9.3.6.8).
- Cadence: **6-monthly default**, per-tenant override in `tenants.data`
  (`db_models.py:1565`); reconcile the monthly job (`lifecycle.py:101-114`) to
  SRB cadence in the same change.
- SRB action items linked to escalated CAPs (EIP, §§21-22) and risk acceptances
  (§§7/16); reuse a shared action-items table with a meeting-type discriminator
  or a parallel `srb_action_items`.

**29.6 - Open questions.** Split the SAG/SRB recipient lists? Keep one
action-items table for both SAG and SRB? Does the 6-monthly reconciliation also
gate the manual dispatch endpoint?

**Implementation note.** NEXT — needs Decision 3 application + §22 AE gate.

---

## 30. REGULATORY REPORTING

**30.1 - Purpose.** Reporting to CAAN per CAR-19: mandatory occurrence reports
(MOR) on time, plus the periodic SSP/oversight reporting stream.

**30.2 - Compliance anchor.** CAAN CAR-19; Annex 19 Third Edition §5.2 (SDCPS);
Annex 13 (accident/incident notification — MOR is the national mandatory
occurrence-reporting mechanic).

**30.3 - Current implementation (VERIFIED).**
- **Weekly SSP dispatch exists:** `run_weekly_ssp_dispatch`
  (`workers/scheduler.py:25`, class `ScheduledReportWorker` `:18`), job
  `weekly_ssp_dispatch` (Mon 02:00 NPT, `lifecycle.py:87-99`), registers
  authorities + emails CAAN SSP PDFs (`scheduler.py:41-56`, PDF
  `CaanPdfGenerator.build_ssp_report_pdf` `:97`). Audit logs written.
- **Periodic CAAN reports:** `regulatory_reports` table
  (`db_models.py:1048`) with `report_type` CHECK **'quarterly', 'annual'**
  (`:1043`) — quarterly and annual report types ARE covered; generators in
  `routes/reporting.py` (quarterly `:150`/`:201`, annual `:284`), persisted via
  `pg.upsert` (`:60`).
- **MOR:** `reports` table, `report_type='mandatory'`
  (`occurrence_reports.py:150`), CAMO/QA-restricted (`:136`). **No regulatory
  timer** — no deadline/submission tracking fields exist (SN15 MISSING).

**30.4 - Gaps.** 1) No MOR deadline computation/column (SN15). 2) No
deadline-approaching alert job. 3) `caan_reports` (`db_models.py:1767`) coexists
with `regulatory_reports` — ownership/relationship undocumented.

**30.5 - Specification.**
- On MOR submission (`POST /occurrence_reports/mor`,
  `occurrence_reports.py:115`): compute and store
  `regulatory_deadline_at` = now + CAR-19 reporting window (**72 hours**
  default — "Category A: Immediate mandatory (72 hours)" `gemini.py:159`),
  configurable per tenant. Track `regulatory_submitted_at` and
  `regulatory_submission_ref` (SN15).
- New daily alert job (APScheduler, reuse `lifecycle.py:50-59` pattern) warns
  when a MOR deadline approaches or is breached.
- Periodic reports: no new types needed (`RR_TYPE_CHECK` `:1043` covers
  quarterly/annual); confirm each generator's owner in UAT.
- Weekly SSP dispatch: document only — no change.

**30.6 - Open questions.** Exact CAR-19 window wording (72 h confirmed, or
category-tiered?); who populates `regulatory_submission_ref` (reporter vs safety
manager); `caan_reports` vs `regulatory_reports` relationship.

**Implementation note.** PENDING — SN15 first, then the alert job.

---

## 31. FEEDBACK (TO REPORTER AND ORGANIZATIONAL)

**31.1 - Purpose.** Close the SDCPS loop: acknowledge the reporter on
submission, notify the outcome when the hazard is resolved, and publish
organizational safety communications derived from hazard/risk analysis.

**31.2 - Compliance anchor.** Annex 19 Third Edition Appendix 3 (protection of
safety data — never breach reporter confidentiality); Doc 9859 §9.6.5 (safety
communication via newsletters, notices, bulletins, briefings/training,
§9.6.5.1; assess effectiveness §9.6.5.3; ongoing §9.6.5.4).

**31.3 - Current implementation (VERIFIED).** **MISSING.**
- `feedback` table (`db_models.py:1739-1764`) is **platform user feedback**
  (user_email / rating / subject / message / page / status) — never safety
  feedback (Decision 5).
- No per-reporter acknowledgment/outcome flow — the only "acknowledgment"
  machinery is tenant registration emails (`gmail_dispatcher.py:122-207`).
- No bulletin mechanism (the only "safety bulletin" strings are AI-suggestion
  text, `nhrc_service.py:76`).
- Submission returns an API acknowledgment to the caller
  (`occurrence_reports.py:87/:115`) but nothing is persisted per reporter.

**31.4 - Gaps (MISSING).** Outcome notification, tenant bulletin board,
per-reporter communication record, and the anonymity guard (anonymous reporter
receives feedback through what channel?).

**31.5 - Specification.**
- **Per-reporter feedback (Module B):** persistence-backed acknowledgment on
  submission; outcome notification when the hazard is resolved (procedure
  updated, training provided, etc.). Never discloses reporter identity —
  `is_anonymous` (`db_models.py:172`) rows get outcome only via a secure
  channel/pull view, honoring Annex 19 Appendix 3.
- **Organizational bulletins:** derived from hazard/risk analysis (SPI/trends),
  published to a tenant-scoped bulletin board (new artifact;
  tenant-scoped columns), per Doc 9859 §9.6.5 means.
- **Module A feedback (survey participants):** OUT OF SCOPE — documented in
  MODULE_A_CONTRACT.md (Decision 5).
- The `feedback` table stays platform-only; Module B adds its own
  communication records.

**31.6 - Open questions.** New `safety_communications` table vs reuse; how an
anonymous reporter is notified (no email on file?); bulletin approval workflow.

**Implementation note.** PENDING.

---

## 32. COMPLIANCE MATRIX (MODULE B)

**Purpose.** Maps every CAAN SRM Manual § and Annex 19 Third Edition requirement
to the Module B section(s) that implement it, with a current status and a
reminder. Each status traces to the cited contract section and its schema notes.

**32.1 - CAAN SRM Manual mapping.**

| CAAN § | Description | Module B § | Status | Notes |
|---|---|---|---|---|
| §2.1 | Hazard registration (13 fields) | §3 | Partial | 11/13 modeled; `identified_at` + free-text equipment/area missing (SN1, SN2) |
| §2.2 | Initial prioritization (H/M/L, ERC) | §4 | Partial | ERC question-set missing (Q4, §13); 24h/7d/15d advisory (Q5) |
| §2.3.1 | Bow-Tie analysis | §5 | Implemented | — |
| §2.3.2 | Risk Profile | §6 | Implemented | — |
| §2.3.3 | Risk Acceptance (two signatures) | §7 + §17 | Partial | Single-signature today; two-signature pending (SN5) |
| §2.3.4 | Barrier Register | §8 | Implemented | — |
| §2.3.5 | Risk Register | §9 | Implemented | Legacy + SRAM registers kept in parallel |
| §2.3.6.1 | Severity (7 impact areas) | §11 | Partial | Numerical value computed; per-consequence sheet pending (SN10) |
| §2.3.6.2 | BSV | §12 | Partial | Dual implementation; retire continuous (SN11) |
| §2.3.6.3 | Probability / CBSV | §13 | Partial | Tables A-E implementation reading — UAT verify (Decision 1, 2d) |
| §2.3.6.4 | Risk Matrix | §14 | Implemented | Numeric + severity-letter display |
| §2.3.6.5 | Risk Tolerability | §15 | Implemented | — |
| §2.3.6.6 | Acceptance Authority | §16 | Missing | Non-delegability not enforced (§22, SN6) |
| §2.4 | Corrective Action Notice (CAN) | §19 | Partial | Platform extension beyond the CAAN manual |
| §2.5 | Corrective Action Plan (CAP) | §20 | Partial | Platform extension beyond the CAAN manual |

**32.2 - Annex 19 Third Edition mapping.**

| Annex 19 § | Description | Module B § | Status |
|---|---|---|---|
| App 2 §2.1.1 | Hazard identification | §2 + §3 | Partial |
| App 2 §2.2 | Safety risk assessment | §5-§9 | Partial |
| §5.2 | SDCPS (collect / store / aggregate / analyse) | §2 + §25 | Partial |
| App 3 | Protection of safety data & information | §2 + §31 | Partial |

**32.3 - Doc 9859 references used across Module B.** §4.5 AE risk-acceptance
(`models/can_cap.py:153`); §9.3.6.1 safety manager (§§3, 10, 26);
§9.3.6.6 prompt collection/analysis (§27); §9.3.6.8 SRB (§29); §9.3.6.9 SAG
(§28); §9.6.5 safety communication (§31); corrective-action concept (§§19-20).

**32.4 - CAAN CAR-19 references used across Module B.** Hazard taxonomy
(`models/hazard.py:23`); SRAM engine (`srm_engine.py:4`); 3-tier tolerance
(`risk_matrix.py:52`, `srm_engine.py:107`); CAP bow-tie SRAM block
(`can_cap_service.py:758`); MOR/VSR reporting (§2, §30, `occurrence_reports.py`);
quarterly/annual SSP reports (§30, `db_models.py:1043`); report disclaimers
(`pdf_canvas.py:7-8`).

**32.5 - Summary — status counts.** Across 19 rows (15 CAAN + 4 Annex 19):
**6 Implemented / 12 Partial / 1 Missing.** Implemented: §2.3.1, §2.3.2,
§2.3.4, §2.3.5, §2.3.6.4, §2.3.6.5. Missing: §2.3.6.6 (acceptance authority).
All Annex 19 rows Partial.

**32.6 - Top 5 remediation priorities.**
1. **§2.1 registration completeness** — SN1 `identified_at` + SN2
   `equipment`/`area`: closes the 11/13 gap (Section 3) and feeds triage (SN13).
2. **§2.3.3 + §2.3.6.6 acceptance** — two-signature model (SN5, §17) and the
   AE **non-delegable** terminal sign-off (SN6, §22): the only Missing row and
   the CAAN-mandated acceptance chain.
3. **§2.3.6.2 BSV single source** — retire the continuous
   `risk_calculator.calculate_bsv`; keep discrete banding (SN11, §12).
4. **Operational workflow** — `hazard_triage` (SN13, §26) + CAN/CAP statuses
   with EIP and the Overdue→Closed/Escalated resolution (SN4, §§19-21, §18).
5. **SDCPS readiness** — historical import (SN12, §25) + MOR category-tiered
   timer (SN15, §30) + AE dashboard action queues (§23).

**32.7 - Compliance readiness assessment (CAAN audit).** **NOT READY — DRAFT
COMPLETE pending implementation.** The SRM computational core is already
implemented (bow-tie §2.3.1, risk profile §2.3.2, barrier §2.3.4, risk register
§2.3.5, matrix §2.3.6.4, tolerability §2.3.6.5) — 6/15 CAAN rows. Mandatory
gaps before an audit claim: §2.1 fields (identified_at / equipment-area),
§2.3.3 two-signature acceptance, and §2.3.6.6 acceptance non-delegability.
Every remaining Partial row has a defined path via SN1-SN17 (all binding,
all PENDING).

---

## 33. MODULE B CONTRACT SIGN-OFF

- **Total sections:** 33 numbered sections (1-33) delivered across 7 chunks
  (2a-2g); Section 10 is the Schema Notes ledger (SN1-SN17). Numbered plan
  included 25 core sub-sections plus the §2.3.3a / §2.2a supplements (Sections
  17-18) and the operational layer (Sections 26-31).
- **Schema notes (Section 10):** **SN1-SN17** — finalized in this chunk;
  **all PENDING IMPLEMENTATION** (SN13-SN17 updated/new in Chunk 2g).
- **Open questions:** ≈30 across 12 blocks (Section 10 Q3-Q5; §§3, 4, 19,
  25.12, 26.6-31.6) — every UNKNOWN is enumerated in-chunk and carried forward
  to Module C / UAT.
- **Reconciliation flagged:** monthly SRB-report dispatch job cadence → 6-monthly
  SRB (§29, Decision 3); `caan_reports` vs `regulatory_reports` ownership (§30);
  CAN hazard-status writes bypassing HazardService (§19); hazard registration
  fields (§3, SN1/SN2).
- **Status:** **DRAFT COMPLETE — pending implementation.**
- **Next steps:** Module C contract → RBAC build (SAG_MEMBER,
  ACCOUNTABLE_EXECUTIVE literal roles, triage/review gates, §28/§22) →
  Dashboard build (SN9 KPI endpoint; AE action queues §23) → platform-wide
  Compliance Matrix. Contact CAAN on the §2.1 hazard-survey adapter (Q3) per
  SURVEY_RISK_INJECTION_VALIDATION.md §7.

---

*End of MODULE_B_CONTRACT.md (Chunks 2a-2g). Sections 1-33; Schema Notes
SN1-SN17 all PENDING; chunk decisions recorded in Section 10. Status: DRAFT
COMPLETE — pending implementation. This document describes current state and
gaps only — no fixes or implementations are proposed.*