# Stale File Inventory

Read-only inventory of project documentation for SME classification. Nothing moved, renamed, deleted, or modified.

Status: Read-only. Date: 2026-10-07.
Scope: `D:\Projects\aviasafesms` (repo) and `D:\Projects\` (project-management docs). Excludes `node_modules`, `.git`, `__pycache__`, `.venv`, `venv`, `dist`, `build`, `.pytest_cache`, `test-results`. `D:\Projects\sms360x` not touched. Source code not opened.

Category guess key: `live` · `historical` · `superseded` · `scratch` · `unknown`.
"First heading (H1)" is the first `# ` line of the file. Files whose first H1 line exceeds the read window are shown truncated.

---

## A. Repository root documentation (`D:\Projects\aviasafesms\*.md`)

| Path | Size (bytes) | Last modified | First heading (H1) | Category guess | Notes |
|---|---|---|---|---|---|
| COMPLIANCE_MATRIX.md | 21761 | 2026-09-21 | # COMPLIANCE_MATRIX.md - Platform-Wide Compliance Mapping | live | current 64-row compliance source; referenced by RBAC/contracts |
| CONNECTION_STABILITY_REPORT.md | 12458 | 2026-09-22 | # CONNECTION_STABILITY_REPORT.md - Live-Supabase connection instability in the full test suite | historical | one-off test-suite investigation |
| DASHBOARD_CONTRACT.md | 33818 | 2026-10-02 | # DASHBOARD_CONTRACT.md - Role-Scoped Dashboards Specification | live | active contract |
| DB_VERIFICATION.md | 9450 | 2026-09-16 | # DB_VERIFICATION.md - Live Supabase schema verification | historical | point-in-time DB snapshot (2026-09-16) |
| DISCOVERY_REPORT.md | 42743 | 2026-09-16 | # AviaSAFE Platform - Architectural Discovery Report | historical | discovery snapshot; widely referenced |
| FIRST_ACTION_KPI_VERIFICATION.md | 8964 | 2026-09-17 | # FIRST_ACTION_KPI_VERIFICATION - Timestamps for "registration first action" | historical | verification report |
| HANDOFF_GUIDE.md | 70639 | 2026-10-05 | # Starting a New Session - Handoff Guide | live | current session handoff |
| IMPLEMENTATION_ROADMAP.md | 26268 | 2026-10-02 | # IMPLEMENTATION_ROADMAP.md - Sequenced Schema-Note Implementation Plan | live | overlaps ROADMAP.md |
| LOGIN_FAILURE_DIAGNOSIS.md | 9245 | 2026-09-25 | # LOGIN_FAILURE_DIAGNOSIS.md - Production login "App Check token required" | historical | resolved incident diagnosis |
| MODULE_A_CONTRACT.md | 18829 | 2026-09-16 | # MODULE_A_CONTRACT.md - Survey / SMS Health Module | live | active contract |
| MODULE_B_CONTRACT.md | 104531 | 2026-09-19 | # MODULE_B_CONTRACT.md - Hazard & Risk Management Module | live | active contract |
| MODULE_C_CONTRACT.md | 67752 | 2026-09-21 | # MODULE_C_CONTRACT.md - State Regulator / SDCPS / PSOE Module | live | active contract |
| OVERDUE_MODEL_VERIFICATION.md | 12297 | 2026-09-17 | # OVERDUE_MODEL_VERIFICATION - Overdue across Hazards and CAPs | historical | verification report |
| PASSWORD_RESET_BUG_INVESTIGATION.md | 14959 | 2026-09-17 | # PASSWORD_RESET_BUG_INVESTIGATION.md | historical | investigation record |
| PURGE_VERIFICATION_REPORT.md | 12084 | 2026-09-17 | # PURGE VERIFICATION REPORT - Phase 1 (Read-Only) | historical | purge analysis; row counts cited |
| RBAC_MODEL.md | 24251 | 2026-09-21 | # RBAC_MODEL.md - Role-Based Access Control Specification | live | RBAC spec; Step 1 source |
| README.md | 7571 | 2026-09-12 | # AviaSAFE SMS Platform | live | main readme; dated |
| ROADMAP.md | 15113 | 2026-10-05 | # Roadmap | live | overlaps IMPLEMENTATION_ROADMAP.md |
| SCHEMA_DRIFT_REPORT.md | 22592 | 2026-09-16 | # SCHEMA DRIFT REPORT - ORM (SQLAlchemy) vs Live Supabase PostgreSQL | historical | snapshot; D1 context |
| SCHEMA_RECONCILIATION_PLAN.md | 32421 | 2026-09-17 | # SCHEMA RECONCILIATION PLAN - ORM vs Live Drift Resolution | historical | D1 plan; D1 resolved per G3 (2026-10-07) |
| SECURITY_REVIEW.md | 13870 | 2026-09-18 | # AviaSAFE SMS - Pre-Production Security Review | live | Step 1 source (H1/H2/M1/M5) |
| SURVEY_RISK_INJECTION_VALIDATION.md | 15427 | 2026-09-16 | # Survey Risk Injection Validation Report | historical | validation report |
| session-ses_eff1.md | 239615 | 2026-10-04 | # Role-aware nav recon: SPI dashboard and NHRC KPIs | scratch | session transcript |
| session-ses_f061.md | 403670 | 2026-10-02 | # Project E Batch 3 recon: parking 3 dashboards | scratch | session transcript; largest doc file |
| session-ses_f64b.md | 143492 | 2026-09-13 | # New session - 2026-09-13T15:05:16.708Z | scratch | session transcript |

---

## B. Repository `docs/` folder (excluding `docs/step0/`)

| Path | Size (bytes) | Last modified | First heading (H1) | Category guess | Notes |
|---|---|---|---|---|---|
| docs/status.md | 15695 | 2026-10-05 | # AviaSAFE - Project Status & Architecture Report | live | current status; row counts cited |
| docs/delivery-workorder-20260914.md | 3481 | 2026-09-13 | # Delivery Work Order - 2026-09-14 (Sita Air Delivery Day) | historical | delivery record; date-suffixed |

No `*.txt` under `docs/` or repo root. No `_hold/` under `docs/`.

---

## C. Repository `docs/step0/` (authoritative Step 0)

| Path | Size (bytes) | Last modified | First heading (H1) | Category guess | Notes |
|---|---|---|---|---|---|
| docs/step0/README.md | 895 | 2026-10-07 | # Step 0 - Project Decisions | live | folder index; states authoritative |
| docs/step0/Decision_Record.md | 6185 | 2026-10-07 | # Project Step 0 - Decision Record | live | authoritative copy (G1–G11) |
| docs/step0/Confirmation_Analysis.md | 29709 | 2026-10-07 | # Step 0 Confirmation Analysis | live | authoritative copy (G4/G10/G3) |
| docs/step0/G3_Final_Register_Map.md | 27551 | 2026-10-07 | # Step 0 - G3 Final Register Map | live | authoritative copy |
| docs/step0/Action_Plan.md | 5193 | 2026-10-07 | # Project Action Plan - Finish AviaSAFE First | live | authoritative copy |
| docs/step0/Convergence_Blueprint.md | 25204 | 2026-10-07 | # Project Convergence Blueprint | live | authoritative copy |
| docs/step0/Boundary_Charter_Addendum.md | 11074 | 2026-10-07 | # Project Boundary Charter - Addendum | live | authoritative copy |
| docs/step0/Evaluation_Report.md | 25054 | 2026-10-07 | # Project Evaluation Report | live | authoritative copy |

All eight carry an AUTHORITATIVE COPY header and are marked `live` regardless of age (per copy policy 2026-10-07).

---

## D. Repository `_hold/` folder

Folder `public\_hold\` exists (a prior parking area). Its own README declares it "parked files pending confirmation".

| Path | Size (bytes) | Last modified | First heading (H1) | Category guess | Notes |
|---|---|---|---|---|---|
| public/_hold/README.md | 4673 | 2026-10-02 | # _hold/ - parked files pending confirmation | historical | prior archive attempt |

Other non-markdown files in `public/_hold/` (HTML/JS; not opened):

```
public/_hold/aviasdcps.html                              9477  2026-09-04
public/_hold/demo-contract.html                         16776  2026-09-23
public/_hold/test-portal.html                            1107  2026-09-02
public/_hold/hazards/create.html                        21836  2026-10-01
public/_hold/hazards/index.html                         11685  2026-09-04
public/_hold/portal/index.html                           7631  2026-09-04
public/_hold/portal/survey/index.html                    1172  2026-08-19
public/_hold/dashboard/dept-head-dashboard.html         37269  2026-09-28
public/_hold/dashboard/safety-dashboard.html            47017  2026-09-28
public/_hold/dashboard/shared/shell.html                 5324  2026-09-23
public/_hold/admin/dashboard.html                       65376  2026-09-23
public/_hold/frontend-tests/test_dept_head_dashboard.js  8225  2026-09-23
public/_hold/frontend-tests/test_safety_dashboard.js    13071  2026-09-23
public/_hold/views/*.html  (15 files, 2026-08-26; caan-oversight, data, hazard-analysis,
                           hazard, home, hrc, occurrence-analysis, occurrence, preferences,
                           reports, sdc, spis, taxonomy, tenant-dashboard, tools)
public/_hold/views/partials/.gitkeep                        0  2026-08-26
```
(30 files total including README.)

---

## E. Other archive / legacy folders and other documentation locations

### E1. `backend\scripts\legacy\` (folder named "legacy")

README:
| Path | Size (bytes) | Last modified | First heading (H1) | Category guess | Notes |
|---|---|---|---|---|---|
| backend/scripts/legacy/README.md | 3007 | 2026-09-13 | # Legacy Scripts - Do Not Run | historical | self-declared legacy |

Non-documentation files (Python; **not opened**): 25 `*_DEPRECATED.py` scripts plus 25 matching `__pycache__/*.pyc`, all dated 2026-09-13. Self-declared "Do Not Run".

### E2. Other README documentation

| Path | Size (bytes) | Last modified | First heading (H1) | Category guess | Notes |
|---|---|---|---|---|---|
| load-tests/README.md | 4889 | 2026-08-30 | # AviaSAFE SMS - Load Testing | live | load-test docs |
| tests/README.md | 3708 | 2026-08-05 | # Testing | live | test docs; dated |
| data/README.md | 589 | 2026-09-13 | # Data Archive | historical | reference-data archive notes |

### E3. Product / tenant documentation (`public/docs/tenant-guide/`)

| Path | Size (bytes) | Last modified | First heading (H1) | Category guess | Notes |
|---|---|---|---|---|---|
| public/docs/tenant-guide/01-getting-started/1.0-overview.md | 4821 | 2026-09-12 | # Getting Started - Overview | live | end-user guide |
| public/docs/tenant-guide/02-account-setup/1.0-account-profile-setup.md | 5114 | 2026-08-11 | # Account & Profile Setup | live | end-user guide |
| public/docs/tenant-guide/03-safety-reporting/1.0-vsr-mor-submission.md | 5633 | 2026-08-04 | # Safety Reporting (VSR / MOR) | live | end-user guide |
| public/docs/tenant-guide/templates/STEP_DOCUMENTATION_TEMPLATE.md | 2382 | 2026-07-30 | # STEP TITLE | live | doc template |

### E4. Date-suffixed run logs (not documentation; matching the date-suffix pattern)

`backend/scripts/logs/` contains 15 date-suffixed `.log`/`.json` run records dated 2026-08-24 to 2026-09-01 (e.g. `setup_two_tenants_beta_20260824_191923.json`, `wipe_tenant_data_20260901_042745.log`). Category guess: scratch. Not opened.

---

## F. Project management documents (`D:\Projects\`)

All carry a HISTORICAL ORIGINAL pointer header added 2026-10-07 and map to an authoritative repo copy — except `SOURCE-DATA-CATALOG-AND-ARCHITECTURE-REPORT.md`, which is NOT a `Project_*.md` and has no repo copy.

| Path | Size (bytes) | Last modified | First heading (H1) | Category guess | Notes |
|---|---|---|---|---|---|
| Project_Step0_Decision_Record.md | 6209 | 2026-10-07 | # Project Step 0 - Decision Record | historical | pointer header; copy at docs/step0/Decision_Record.md |
| Project_Step0_Confirmation_Analysis.md | 29727 | 2026-10-07 | # Step 0 Confirmation Analysis | historical | pointer header; copy at docs/step0/Confirmation_Analysis.md |
| Project_Step0_G3_Final_Register_Map.md | 27569 | 2026-10-07 | # Step 0 - G3 Final Register Map | historical | pointer header; copy at docs/step0/G3_Final_Register_Map.md |
| Project_Action_Plan_Finish_AviaSAFE_First.md | 5205 | 2026-10-07 | # Project Action Plan - Finish AviaSAFE First | historical | pointer header; copy at docs/step0/Action_Plan.md |
| Project_Convergence_Blueprint.md | 25228 | 2026-10-07 | # Project Convergence Blueprint | historical | pointer header; copy at docs/step0/Convergence_Blueprint.md |
| Project_Boundary_Charter_Addendum.md | 11094 | 2026-10-07 | # Project Boundary Charter - Addendum | historical | pointer header; copy at docs/step0/Boundary_Charter_Addendum.md |
| Project_Evalulation_Report.md | 25081 | 2026-10-07 | # Project Evaluation Report | historical | pointer header; copy at docs/step0/Evaluation_Report.md (source name is misspelled "Evalulation") |
| SOURCE-DATA-CATALOG-AND-ARCHITECTURE-REPORT.md | 30149 | 2026-10-07 | # SMS360X Source Data Catalog & Technical Architecture Report | historical | not a Project_*.md; **no authoritative repo copy** |

---

## G. Suspected duplicates (same H1 heading, different paths)

Confirmed copy/original pairs (intentional, per copy policy 2026-10-07) — 7 pairs:

| H1 | Authoritative copy | Historical original |
|---|---|---|
| # Project Step 0 - Decision Record | docs/step0/Decision_Record.md | Project_Step0_Decision_Record.md |
| # Step 0 Confirmation Analysis | docs/step0/Confirmation_Analysis.md | Project_Step0_Confirmation_Analysis.md |
| # Step 0 - G3 Final Register Map | docs/step0/G3_Final_Register_Map.md | Project_Step0_G3_Final_Register_Map.md |
| # Project Action Plan - Finish AviaSAFE First | docs/step0/Action_Plan.md | Project_Action_Plan_Finish_AviaSAFE_First.md |
| # Project Convergence Blueprint | docs/step0/Convergence_Blueprint.md | Project_Convergence_Blueprint.md |
| # Project Boundary Charter - Addendum | docs/step0/Boundary_Charter_Addendum.md | Project_Boundary_Charter_Addendum.md |
| # Project Evaluation Report | docs/step0/Evaluation_Report.md | Project_Evalulation_Report.md |

Suspected (not identical H1; unverified content overlap):
- `ROADMAP.md` ("# Roadmap") vs `IMPLEMENTATION_ROADMAP.md` ("# IMPLEMENTATION_ROADMAP.md…") — both are roadmaps; overlap likely.
- `public/_hold/dashboard/safety-dashboard.html` and `public/_hold/dashboard/dept-head-dashboard.html` may duplicate pages under `public/dashboard/` (not verified; code not opened).

---

## Summary

**Total documentation files inventoried: 52** (`.md`; no `*.txt` in scope were found). Breakdown: A=25 (repo root), B=2 (`docs/`), C=8 (`docs/step0/`), D=1 (`public/_hold/` README), E=8 (legacy README, other READMEs, tenant-guide), F=8 (`D:\Projects\`). Non-documentation archive files also observed but not opened: 30 files in `public/_hold/` (HTML/JS), 25 `*_DEPRECATED.py` + 25 `.pyc` in `backend/scripts/legacy/`, and 15 date-suffixed run logs in `backend/scripts/logs/`.

**Count by category guess (52 docs): live 26 · historical 23 · scratch 3 · superseded 0 · unknown 0.** Live = the 8 `docs/step0/` files, 11 repo contracts/status/security docs, `docs/status.md`, 3 READMEs, and the 4 tenant-guide docs. Historical = 11 root verification/investigation reports plus 2 in `docs/`/data/legacy plus all 8 `D:\Projects\` originals. Scratch = the 3 `session-ses_*.md` transcripts.

**Obvious duplicates:** the 7 intentional copy/original pairs in section G (same H1). Possible further duplication between `ROADMAP.md`/`IMPLEMENTATION_ROADMAP.md` and between `public/_hold/dashboard/*` and `public/dashboard/*` (unverified).

**Prior archive attempt:** `public/_hold/` is explicitly a parking folder ("parked files pending confirmation"), and `backend/scripts/legacy/` is a self-declared "Do Not Run" legacy area. These are the two existing archive-style folders.

**Files that look referenced by others:** `COMPLIANCE_MATRIX.md`, `MODULE_A/B/C_CONTRACT.md`, `RBAC_MODEL.md`, `DASHBOARD_CONTRACT.md`, `SECURITY_REVIEW.md`, `DISCOVERY_REPORT.md`, `SCHEMA_DRIFT_REPORT.md`, `SCHEMA_RECONCILIATION_PLAN.md`, and `DB_VERIFICATION.md` are cited across the contract/verification set and by `docs/step0/Confirmation_Analysis.md`.

**Dangling references (a file cites another that is not present under the cited name):**
- `docs/step0/*` copies still cite the original `Project_*.md` filenames (e.g. `Decision_Record.md` §3a cites `Project_Step0_G3_Final_Register_Map.md`; `Action_Plan.md` cites the `Project_` names). Those names now exist only at `D:\Projects\` (with pointer headers), not inside `docs/step0/`.
- `README.md` references `docs/ARCHITECTURE.md`, which is not present in `docs/` (also flagged in `Project_Evalulation_Report.md:237`).
- `SOURCE-DATA-CATALOG-AND-ARCHITECTURE-REPORT.md` is listed as a companion by the blueprint but has no authoritative repo copy.

No recommendation to delete or move is made. Report only.

---

*End of Stale File Inventory. Read-only; nothing was moved, renamed, deleted, or modified.*
