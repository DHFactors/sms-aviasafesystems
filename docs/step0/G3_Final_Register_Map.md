<!--
AUTHORITATIVE COPY.
Location: D:\Projects\aviasafesms\docs\step0\G3_Final_Register_Map.md
Original (historical): D:\Projects\Project_Step0_G3_Final_Register_Map.md
Copied: 2026-10-07
Edits must be made here, not in the original.
-->

# Step 0 — G3 Final Register Map

Definitive map between the CAAN-required registers, the Sita Air composite operator registers, and the AviaSAFE schema.

Status: Read-only evidence — SME decision required. No code, no migrations, no Step 1 work.
Date: 2026-10-07
Scope: `D:\Projects\aviasafesms` only. SMS360X not touched.
Supersedes: `Project_Step0_Confirmation_Analysis.md` §3 (G3 evidence) for the register question. No prior `Project_Step0_G3_Evidence.md` or `Project_Step0_G3_Composite_Register_Map.md` exists on disk.

Sources of ground truth (per instruction): CAAN SRM Procedure Manual First Edition Jan 2026 (§2.1 Hazard Registration Sheet; §2.3.3 Risk Acceptance Record; §2.3.4 Barrier Register; §2.3.5 Risk Register; §2.3.1–2.3.2 Bow-Tie / Risk Profile; §2.3.6 numerical method) and the Sita Air Master Logsheet 2026 composite practice (six working registers).

Method: column lists are transcribed from the defining migration/DDL file cited per table; row counts are quoted from the read-only verification reports with their dates; RLS status is from `DB_VERIFICATION.md` Check 5 (2026-09-16) plus later migrations that add RLS.

---

## 2.1 AviaSAFE Schema Inventory (register-relevant tables)

Legend for row counts: "0 (2026-09-17)" = `PURGE_VERIFICATION_REPORT.md`; "n (2026-10-05)" = `docs/status.md`; "unknown" = not documented.

### 2.1.1 Hazard / occurrence / deficiency / diversion registers

**`hazards`** — hazard register (CAAN §2.1). Defined `supabase/migrations/20260830130516_remote_schema.sql:332-375`; extended by `20260905090000_hazard_icao_alignment.sql:15-24` and `backend/app/db/schema_init.py:405-427,838`.
Columns: `id uuid PK`, `hazard_id text` (business code), `tenant_id uuid`, `title text`, `description text`, `source text`, `source_id text`, `source_url text`, `adrep_category text`, `occurrence_type text`, `taxonomy text` (4-value ICAO: Organizational/Technical/Human/Environmental), `taxonomy_specific text`, `consequence text`, `severity int`, `probability int`, `risk_index int`, `risk_level text`, `risk_outcome text`, `tolerability_tier text`, `priority text` (H/M/L), `recommended_action text`, `corrective_action text`, `assigned_to text`, `assigned_to_uid text`, `department text`, `srm_conducted bool`, `srm_date timestamptz`, `srm_status text`, `analysis_mode text`, `sram_data jsonb`, `status text`, `follow_up_date timestamptz`, `closed_at timestamptz`, `closed_by text`, `remarks text`, `created_by text`, `created_at`, `updated_at`, `is_demo bool`, plus ICAO alignment `function text` (OPS/ENG/…), `threat text`, `top_event text`, `corrective_action_flag bool`, `srm_flag bool`, `priority_date timestamptz`, `status_date timestamptz`, plus Module B `identified_at`, `first_priority_at`, `equipment text`, `imported_at`, `import_batch_id uuid`, `original_row_ref text`, `legacy_hazard_code text`, `enrichment_data jsonb`, `enrichment_sources jsonb`, plus Module C `nhrc_category text`.
Row count: 21 (2026-09-17) / 26 (2026-10-05). RLS: enabled (`DB_VERIFICATION.md:156`).

**`reports`** — occurrence reports (VSR/MOR). Defined `20260830130516_remote_schema.sql:432-502`; extended `schema_init.py:429-432` (regulatory columns) and `:869-884` (confidential reporting).
Columns: `id uuid PK`, `tenant_id uuid`, `report_type text` (voluntary/mandatory), `status text`, `ai_status text`, `narrative text`, `location text`, `occurrence_date timestamptz`, `is_anonymous bool`, `flight_number text`, `aircraft_registration text`, `occurrence_type text`, `severity text`, `investigation_status text`, `severity_level int`, `probability_level int`, `risk_index int`, `risk_level text`, `risk_assessment jsonb`, `ai_suggested_assessment jsonb`, `ai_analysis jsonb`, `occurrence_class text`, `latitude/longitude double`, `country text`, aircraft/engine/flight fields (`aircraft_make/model/serial_number`, `operator`, `operator_icao`, `aircraft_category`, `engine_make/model/serial_number`, `flight_phase`, `flight_type`, `departure_airport`, `destination_airport`, utilisation/pax/injury counts), `occurrence_category text`, `human_factors jsonb`, `contributing_factors jsonb`, `investigation_agency text`, reporter fields, `reporting_date timestamptz`, `etops/propeller_*/call_sign/organisation_comments/manufacturer_advised/fdr_data_retained`, `created_by`, timestamps, `is_demo bool`, plus Module B `regulatory_category text` (A–D), `regulatory_deadline_at`, `regulatory_submitted_at`, `regulatory_submission_ref text`, plus Module C `is_confidential bool`, `confidential_custodian_id uuid`.
Row count: 99 (2026-09-17) / 10 (2026-10-05). RLS: enabled (`DB_VERIFICATION.md:167`). Note: `report_type` CHECK = voluntary/mandatory (`remote_schema.sql:500`).

**`safety_deficiencies`** — safety-deficiency log (matches Sita Air register #3). Defined `20260830130516_remote_schema.sql:541-570`.
Columns: `id uuid PK`, `tenant_id uuid`, `event_id uuid`, `source text`, `hazard_code text`, `description text`, `taxonomy_main text`, `taxonomy_type text`, `taxonomy_specific text`, `unsafe_event text`, `identified_hazard text`, `priority text` (H/M/L), `severity text` (Low/Medium/High/Critical), `assigned_to text`, `assigned_to_uid text`, `assigned_by text`, `assigned_at timestamptz`, `follow_up_date timestamptz`, `completed_at timestamptz`, `status text`, `remarks text`, `csd_remarks text`, `created_by`, `updated_by`, timestamps.
Row count: 0 (2026-09-17). RLS: enabled (`DB_VERIFICATION.md:169`).

**`flight_diversions`** — diversion log (matches Sita Air register #5). Defined `20260830130516_remote_schema.sql:221-248`.
Columns: `id uuid PK`, `diversion_id text`, `tenant_id uuid`, `date timestamptz`, `flight_number text`, `aircraft_registration text`, `sector_from text`, `sector_to text`, `diverted_to text`, `reason text`, `reason_details text`, `captain text`, `first_officer text`, `air_hostess text`, `description text`, `additional_fuel_cost numeric(12,2)`, `passenger_impact int`, `delay_minutes int`, `remarks text`, `status text`, `hazard_id uuid`, `hazard_link_url text`, `created_by`, `updated_by`, timestamps.
Row count: 7 (2026-10-05) / 0 (2026-09-17). RLS: enabled (`DB_VERIFICATION.md:149`).

### 2.1.2 Risk registers

**`risk_register`** (legacy per-hazard SRM) — CAAN §2.3.5 shape. Defined `20260830130516_remote_schema.sql:508-535`; live shape confirmed `DB_VERIFICATION.md:13-48`; ORM `RiskRegisterLegacyEntry` (`backend/app/db/db_models.py:1449-1495`).
Columns: `id uuid PK`, `tenant_id uuid`, `hazard_id uuid FK→hazards(id)`, `srm_date timestamptz NOT NULL`, `ultimate_consequence text NOT NULL`, `existing_severity int`, `existing_probability int`, `existing_risk_index int`, `existing_risk_tolerability text`, `resultant_severity int`, `resultant_probability int`, `resultant_risk_index int`, `resultant_risk_tolerability text`, `status text`, `follow_up_date timestamptz`, `date_completed timestamptz`, `remarks text`, `concerned_department text`, `created_by`, `updated_by`, `created_at`, `updated_at`, `is_demo bool`.
Row count: 0 (2026-09-17). RLS: enabled (`DB_VERIFICATION.md:168`).

**`sram_risk_register`** (SRAM bow-tie register) — defined `20260916120000_sram_risk_register.sql:14-58`; Module B additions `20260918090200_module_b_sram_risk_register.sql:14-52`; boot mirror `schema_init.py:317-362,447-479`; ORM `SramRiskRegisterEntry` (`db_models.py:1498-1563`).
Columns: `id uuid PK`, `tenant_id uuid`, `bowtie_id uuid FK→bow_tie_analyses(id)`, `hazard_id text` (business ref, no FK), `hazard_title text`, `probability_current int`, `severity_current int`, `risk_index_current int`, `tolerability_current text`, `probability_resultant int`, `severity_resultant int`, `risk_index_resultant int`, `tolerability_resultant text`, `status text` (open/in_progress/closed), `accepted bool`, `alarp_justification text`, `accepted_by uuid`, `accepted_on timestamptz`, `review_date timestamptz`, `is_demo bool`, `created_at`, `updated_at`, plus Module B `process_by uuid`, `process_signed_at timestamptz`, `initial_authority text`, `resultant_authority text`, `consequence_id uuid FK→bow_tie_consequences(id)`.
Row count: 0 (2026-09-17). RLS: policy `p_sram_risk_register_tenant_isolation` (`20260916120000...:63-78`) — enabled.

**`state_risk_register`** (Module C state register; distinct object, national scope) — `20260830130516_remote_schema.sql:576-599`.
Columns: `id uuid PK`, `tenant_id uuid`, `icoc_category text` (sic), `description text`, `icao_reference text`, `current_risk_index int`, `tolerability text`, `tolerability_tier text`, `level text`, `ssp_target double`, `actual_ssp_value double`, `risk_reduction_rate double`, `trend text`, `contributing_tenants jsonb`, `quarter int`, `year int`, `updated_by`, timestamps, `is_demo bool`.
Row count: 0 (2026-09-17). RLS: enabled (`DB_VERIFICATION.md:173`).

### 2.1.3 Barrier / bow-tie

**`barrier_register`** — CAAN §2.3.4 shape. Defined `20260905153000_sram_tables.sql:145-179`.
Columns: `id uuid PK`, `tenant_id uuid`, `bowtie_id uuid FK`, `control_id uuid FK`, `hazard_id text`, `barrier text`, `barrier_type text` (preventive/recovery), `effectiveness int`, `cost_benefit int`, `practicality int`, `acceptability int`, `enforceability int`, `durability int`, `disinclination int`, `bsv numeric(3,1)`, `implementation_status text` (not_started/in_progress/implemented/verified), `action_by text`, `follow_up_date timestamptz`, `notes text`, `created_at`, `updated_at`, `is_demo bool`.
Row count: 0 (2026-09-17). RLS: enabled (`DB_VERIFICATION.md:137`). No `srm_date` column.

**`bow_tie_analyses` / `bow_tie_threats` / `bow_tie_consequences` / `bow_tie_controls`** — the §2.3.1–2.3.2 working method (not a register). Defined `20260905153000_sram_tables.sql:21-99`. Key columns: analyses `id, tenant_id, hazard_id text, hazard_title, top_event, description, status(In Progress/Assessed/Accepted/Rejected), created_by, is_demo`; threats `id, tenant_id, bowtie_id FK, threat, probability, threat_order`; consequences `id, tenant_id, bowtie_id FK, consequence, severity_level(A–E), consequence_order`; controls `id, tenant_id, bowtie_id FK, control, control_type(preventive/recovery), control_order, owner, status`.
Row counts: 0 (2026-09-17). RLS: all enabled (`DB_VERIFICATION.md:138-141`).

### 2.1.4 Finding / action lifecycle (CAN/CAP/verification/closure)

- **`cans`** — `20260830130516_remote_schema.sql:52-89`: `id, can_reference, tenant_id, hazard_id, title, description, required_action, issued_by(_uid), issued_at, target_completion_date, assigned_to(_uid), department, priority, status, copies_to, requested_function, addressed_function, initial_severity/probability/risk_index/risk_level/risk_outcome/initial_tolerability_tier, initial_sra jsonb, classification_type/level, created_by, timestamps, is_demo`. Count 16 (2026-09-17) / 6 (2026-10-05). RLS enabled.
- **`caps`** — `:95-165`: includes `can_id`, action/timeline/resources/implementation fields, `submitted_by(_uid)`, `reviewed_by(_uid)`, `review_comments`, `managerial_approval jsonb`, `caa_acceptance jsonb`, `residual_* risk`, `root_causes jsonb`, `action_items jsonb`, `rca_method`, `sram_data jsonb`, `escalated_to_ae`, `ae_signature`, `ae_signed_at`, `ae_review_interval_days/date`, `sag_sign(_by/_at)`, `manager_approval`, `ca_acceptance`, `process_owner`, `manager_confirmation`, closing fields. Count 12 (2026-09-17) / 6 (2026-10-05). RLS enabled. (`DB_VERIFICATION.md:60-71` notes live signatures are jsonb.)
- **`verifications`** — `:655-670` (`hazard_id`, `cap_id`, `outcome`, `comments`, `evidence jsonb`, `verified_by(_uid)`, `verification_date`, `revision_deadline/notes`). Count 0 (2026-09-17). RLS enabled.
- **`closures`** — `:171-183`. Count 0 (2026-09-17). RLS enabled.
- **`corrective_actions`** — `:189-215`. Count 0 (2026-09-17). RLS enabled.

### 2.1.5 Intake / mapping / meetings / communications (Module B)

- **`import_batches`** (`schema_init.py:507-526`), **`import_rows`** (`:532-553`; `entity_type` CHECK = `hazard, risk_register, sram_risk_register, bow_tie, barrier, can, cap`), **`import_mappings`** (`:559-570`; `column_map jsonb`), **`import_links`** (`:575-584`). Counts 0. RLS enabled via `_module_b_rls_ddl` (`schema_init.py:389-400`).

- **`hazard_triage`** (`:482-500`), **`sag_meetings`** (`:590-603`), **`srb_meetings`** (`:608-621`), **`action_items`** (`:627-642`), **`safety_communications`** (`:649-663`). Counts 0. RLS enabled.

### 2.1.6 State / maturity / oversight

- **`psoe_assessments`** (`remote_schema.sql:381-402`), **`psoe_questions`** (`20260905153000_psoe_audit_complete.sql:2-8`), **`psoe_findings`** (`:11-22`, plus `cap_id` added `schema_init.py:840-852`). Counts: assessments 0; questions 21 (`PURGE_VERIFICATION_REPORT.md:69`); findings 0. RLS enabled.
- **`state_safety_performance_targets`** (`schema_init.py:752-765`), **`state_risk_categories`** (`:299-304`; 0 rows), **`module_c_aggregates`** (`:705-716`), **`metric_definitions`** (`:779-792`), **`taxonomy_mappings`** (`:809-817`).
- **`surveys`** / **`survey_responses`** (`remote_schema.sql:623-649` / `:605-617`; 204 each 2026-09-17), **`sms_maturity`** (`schema_init.py:283-295`; 0 rows), **`regulatory_reports`** (`remote_schema.sql:408-426`; 0 rows).
- **`caan_reports`** (`schema_init.py:272-278`; 2 mock rows `PURGE_VERIFICATION_REPORT.md:104`).

### 2.1.7 Governance / reference / legacy RCA

- **`tenants`** (`schema_init.py:119-146`), **`regulators`** (`:173-183`), **`users`** (`:186-197`; 5 rows 2026-09-17), **`audit_logs`** (`:202-216`), **`invites`** (`:247-256`), **`feedback`** (`:260-267`), **`sms_dispatches`** (`:221-227`), **`audit_dispatches`** (`:232-240`), **`dead_letter_queue`** (`:307-313`).
- **Legacy v2 RCA set** (no active register consumer): `hazard_rca_entries` (`:23-41`), `hazard_rca_factors` (`:46-59`), `hazard_assessments` (`:63-76`), `hazard_capas` (`:80-90`). Counts 0. RLS enabled.
- **Reference (live-only; not in `schema.sql` or the tracked migrations):** `icao_adrep_taxonomies` (15 rows), `hfacs_nanocodes` (106 rows), `hazard_adrep_mappings` (0), `hazard_hfacs_codes` (0), `report_adrep_mappings` (0), `report_hfacs_codes` (0) — `DB_VERIFICATION.md:125,189`; `PURGE_VERIFICATION_REPORT.md:69-76`.

RLS summary (2026-09-16, `DB_VERIFICATION.md:129-182`): disabled on **6** tables — `caan_reports`, `sms_maturity`, `state_risk_categories`, `dead_letter_queue`, `sms_dispatches`, `audit_dispatches`. Later DDL adds RLS to three of them — `caan_reports` (`schema_init.py:886-899`), `state_risk_categories` (`:901-912`), `sms_maturity` (`supabase/migrations/20260917090000_sms_maturity_rls.sql`) — leaving `dead_letter_queue`, `sms_dispatches`, `audit_dispatches` without RLS.

---

## 2.2 Canonical Register Mapping Table

| Register | Source | AviaSAFE table | Match quality | Missing columns |
|---|---|---|---|---|
| Hazard Registration (§2.1) | CAAN manual | `hazards` | partial | Hazard code is `hazard_id` (present); "area/operation/equipment" is split (`function` + `equipment`, not one free-text); explicit "threat of hazard" = `threat`; "unsafe/top event" = `top_event`; initial priority = `priority`; Corrective Action Y/N = `corrective_action_flag`; SRM Y/N = `srm_flag`; "recommended action" = `recommended_action`; "follow-up"/"remarks" present. No single "reported date" vs "identified date" split beyond `identified_at`. |
| Risk Acceptance Record (§2.3.3) | CAAN manual | `sram_risk_register` (acceptance columns) + `caps` (signatures) | partial | No dedicated acceptance-record table. Signatures exist as `accepted/accepted_by/accepted_on`, `process_by/process_signed_at`, `initial_authority/resultant_authority`; `caps.ae_signature/manager_approval`. Team-leader + AE two-signature pair is not a first-class record. |
| Barrier Register (§2.3.4) | CAAN manual | `barrier_register` | partial | **No `srm_date`**. Barrier Description=`barrier`, Hazard Code=`hazard_id`, Type=`barrier_type`, Strength=`bsv`, Status=`implementation_status`, Action=`action_by`, Follow-up=`follow_up_date`. S.N is surrogate `id`. |
| Risk Register (§2.3.5) | CAAN manual | `risk_register` | exact | Hazard Code=`hazard_id`, SRM Date=`srm_date`, Consequence(s)=`ultimate_consequence`, Existing Risk=`existing_{severity,probability,risk_index,risk_tolerability}`, Resultant Risk=`resultant_*`, Status=`status`, Follow up=`follow_up_date`. `date_completed` covers Close/date. |
| Bow-Tie / Risk Profile (§2.3.1–2.3.2) | CAAN manual | `bow_tie_analyses` + `_threats` + `_consequences` + `_controls` | partial | Method, not a register; present as a full structure. |
| Master Intake Log | Sita Air | none (spread: `reports` + `hazards` + `safety_deficiencies` + `flight_diversions`; staging `import_batches`/`import_rows`) | none (as one register) | No single intake table with a classification column (Occurrence/Hazard/Safety deficiency/Diversion). |
| Occurrence Log | Sita Air | `reports` | partial | No occurrence code column (Sita Air `SA-Occ-NN-YYYY`); `report_type` is voluntary/mandatory, not occurrence taxonomy; RCA/investigation and mitigation status are JSONB (`ai_analysis`, `investigation_status`). |
| Safety Deficiency Log | Sita Air | `safety_deficiencies` | exact | `hazard_code`, `taxonomy_main/type/specific`, `unsafe_event`, `priority`, `assigned_to`, `follow_up_date`, SRM-via-hazard. |
| Hazard Log | Sita Air | `hazards` | exact | Same object as §2.1. |
| Flight Diversion Log | Sita Air | `flight_diversions` | exact | Flight/crew/FOO/aircraft/reason all present (`flight_number`, `captain`, `first_officer`, `air_hostess`, `aircraft_registration`, `reason`, `reason_details`). Note Sita Air's "FOO" is not a distinct column. |

---

## 2.3 The Two-Table Question — Definitive Answer

**Which CAAN register does `public.risk_register` implement?**
CAAN **§2.3.5 Risk Register**. Its columns map column-for-column to the §2.3.5 list — `hazard_id`, `srm_date`, `ultimate_consequence` (Consequence(s)), `existing_*` (Existing Risk Severity/Probability/Index/Tolerability), `resultant_*` (Resultant Risk), `status`, `follow_up_date` — per `20260830130516_remote_schema.sql:508-535`, confirmed live at `DB_VERIFICATION.md:13-48`, and `schema.sql:459-495` whose header names it "per-hazard SRM". It is the CAAN-mandated Risk Register object.

**Which CAAN register does `public.sram_risk_register` implement?**
No named CAAN register column-for-column. Its shape is the **SRAM output register** carrying risk-acceptance/ALARP fields — `probability_current/severity_current/risk_index_current/tolerability_current` (+ resultant), `accepted`, `alarp_justification`, `accepted_by/on`, and Module B `process_by/process_signed_at/initial_authority/resultant_authority` (`20260916120000_sram_risk_register.sql:14-58`; `schema_init.py:447-451`). It is closest to the **§2.3.3 Risk Acceptance Record** (acceptance authority/signatures) plus a bow-tie current/resultant risk view, not to §2.3.5.

**Two implementations of one register, two distinct registers, or one CAAN + one operator register?**
On the evidence: **two distinct objects**, not two shapes of one object.
- Different columns: §2.3.5 uses `existing_*`/`resultant_*` with integer severity/probability and a `hazard_id uuid` FK; the SRAM table uses `*_current`/`*_resultant`, integer 1–5/1–25, `hazard_id text` (no FK), a `bowtie_id`, and acceptance/ALARP fields.
- Different processes (per SME): HIRM (per-hazard SRM → `risk_register`) vs SRAM (bow-tie → `sram_risk_register`).
- Different linkage: `risk_register.hazard_id` is a UUID FK to `hazards`; `sram_risk_register.hazard_id` is a business-ref text.
- The historical "defect" was a **name collision** (the SRAM `CREATE TABLE IF NOT EXISTS public.risk_register` at `20260905153000_sram_tables.sql:102` silently no-op'd because legacy already existed — `DB_VERIFICATION.md:52`), resolved by D1 into two tables. That was a naming defect, not evidence that the two objects are one.

Caveat (evidence, not decision): `sram_risk_register` overlaps `caps` on acceptance signatures (`caps.ae_signature`, `managerial_approval`), so the "Risk Acceptance Record" role is currently spread across two tables.

---

## 2.4 Operator-to-Canonical Mapping Requirement

**Sita Air register → canonical CAAN register:**

| Sita Air register | Feeds canonical register(s) | Via AviaSAFE table |
|---|---|---|
| 1. Master Logsheet 2026 (intake classification) | Routes to §2.1 Hazard, occurrence (MOR/VSR), safety deficiency, and diversion | No dedicated table; intake must be classified into `hazards` / `reports` / `safety_deficiencies` / `flight_diversions`; staging via `import_batches` + `import_rows` |
| 2. Occurrence 2026 | Occurrence reporting (statutory MOR / VSR; Doc 10159) | `reports` (`report_type` voluntary/mandatory) |
| 3. Safety Deficiencies 2026 | §2.1 Hazard (deficiency variant) | `safety_deficiencies` |
| 4. Hazard Logsheet 2026 | §2.1 Hazard Registration | `hazards` |
| 5. Flight Diversion Report 2026 | Operational occurrence/context (feeds SPI) | `flight_diversions` |
| 6. Risk Register sheet 2026 | §2.3.5 Risk Register (column-for-column) | `risk_register` |

**Tara Air (CAAN-direct) registers:** §2.1 → `hazards`; §2.3.3 → `sram_risk_register` (+ `caps` signatures); §2.3.4 → `barrier_register`; §2.3.5 → `risk_register`.

**What the application must do at the mapping layer:**
- Use the Module B import layer (`import_batches`, `import_rows` with `raw_data`/`normalized_data`, `import_mappings.column_map`) as the single translation surface. Each source register maps to a canonical target through a per-operator `column_map`.
- Extend the `import_rows.entity_type` CHECK (`schema_init.py:547-549`) to cover the registers with no current entity type: `occurrence`, `safety_deficiency`, `flight_diversion`, `master_intake` (today it lists only `hazard, risk_register, sram_risk_register, bow_tie, barrier, can, cap`).
- Validate that CAAN-mandatory columns are populated after mapping regardless of source layout; reject (or flag) rows missing them.
- Because the target tables are operator-owned and tenant-keyed, the same canonical tables accept either operator's layout; no per-operator tables are required.

**Columns unique to Sita Air practice that must be preserved for the operator's own audit evidence:**
- Occurrence code `SA-Occ-NN-YYYY` and Safety-Deficiency code `SA-ORG-N-YY` (business refs; no canonical column — preserve in `raw_data`/`original_row_ref` or a text reference column).
- `safety_deficiencies.taxonomy_main` / `taxonomy_type` / `taxonomy_specific` split (the CAAN hazard taxonomy is a single `taxonomy` + `taxonomy_specific` on `hazards`).
- "Specific components" on the Hazard Logsheet (no canonical column; `equipment` is the nearest).
- Diversion crew fields `captain` / `first_officer` / `air_hostess` and `reason`/`reason_details` (present on `flight_diversions`, must stay populated).
- Master Logsheet classification label and any per-row operator notes (no canonical column; preserve in staging).

**Columns that are CAAN-mandatory and must appear regardless of source:**
- Hazard: hazard code, identified/reported date, area/operation/equipment, description, threat, taxonomy, source, unsafe/top event, consequence, initial priority (H/M/L), recommended action (Corrective Action Y/N, SRM Y/N), status, follow-up, remarks.
- Risk Register: hazard code, SRM date, consequence(s), existing (S/P/index/tolerability), resultant (S/P/index/tolerability), status (Open/Close+date), follow-up.
- Barrier Register: barrier description, hazard code, SRM date, barrier type, barrier strength (BSV), implementation status, action by whom/when, follow-up date.
- Risk Acceptance Record: team-leader/Safety-Manager signature + Accountable-Executive signature (non-delegable).

---

## 2.5 Gap List

**CAAN register with no AviaSAFE table (as a distinct register):**
- §2.3.3 Risk Acceptance Record — no dedicated table; acceptance fields are split across `sram_risk_register` (`accepted_*`, `process_by`, `*_authority`) and `caps` (`ae_signature`, `managerial_approval`, `caa_acceptance`).

**CAAN registers with partial coverage / missing columns:**
- §2.1 Hazard Registration → `hazards`: no single "area/operation/equipment" field; no explicit reported-vs-identified distinction beyond `identified_at`.
- §2.3.4 Barrier Register → `barrier_register`: **`srm_date` missing**; S.N is the surrogate `id`.
- §2.3.1–2.3.2 Bow-Tie / Risk Profile → present as the four `bow_tie_*` tables (method; no "profile" table).

**Operator-only registers with no corresponding AviaSAFE table:**
- Sita Air Master Intake Log — no single intake table (spread across four target tables + import staging).
- Sita Air Occurrence Log — partial via `reports`; no occurrence-code column.
- Sita Air Safety Deficiency Log — covered by `safety_deficiencies`.
- Sita Air Flight Diversion Log — covered by `flight_diversions`.
- Sita Air Risk Register sheet — covered by `risk_register`.

---

## 2.6 Interpretation

**Is AviaSAFE currently a complete implementation of the CAAN register layer?**
No. Of the four named CAAN registers, one maps exactly (`risk_register` = §2.3.5), one is present but missing a mandatory column (`barrier_register` = §2.3.4, no `srm_date`), one is partial with fields spread across tables (`hazards` = §2.1), and one has no dedicated table (§2.3.3 Risk Acceptance Record). §2.3.1–2.3.2 is implemented as a working analysis structure.

**Of Sita Air's composite practice?**
Nearly. Four of the six Sita Air registers map to existing tables (`hazards`, `reports`, `safety_deficiencies`, `flight_diversions`), and the Risk Register sheet maps exactly to `risk_register`. The gap is the Master Intake Log (no single table) plus the loss of operator-specific codes (`SA-Occ-…`, `SA-ORG-…`) unless preserved in staging/raw fields.

**Minimum change needed to match both:**
- Add `srm_date` to `barrier_register` (CAAN §2.3.4 mandatory).
- Provide a Risk Acceptance Record — either a dedicated table or an explicit view over `sram_risk_register` + `caps` signatures — carrying the two signatures and non-delegability.
- Extend the import `entity_type` CHECK to cover `occurrence`, `safety_deficiency`, `flight_diversion`, `master_intake`.
- Preserve operator-specific codes in staging (`raw_data`/`original_row_ref`) or a text reference column; no canonical column is required to hold them.
- No change is needed to accept either operator layout, because the canonical tables are tenant-keyed and source-agnostic.

**Is any table a duplicate of another?**
No. `risk_register` (§2.3.5) and `sram_risk_register` (§2.3.3/SRAM output) are distinct objects with different columns and different processes. `sram_risk_register` and `caps` overlap only on acceptance signatures. No table duplicates another.

**Is any migration required?**
No data migration is required: the two candidate risk tables are empty (0 rows each, `PURGE_VERIFICATION_REPORT.md:99`), as are the barrier and bow-tie tables. Any schema additions above are additive (new nullable columns / new table / CHECK extension) and do not require data movement.

---

*End of Step 0 G3 Final Register Map. Read-only; no repository or database was modified.*
