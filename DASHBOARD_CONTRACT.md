# DASHBOARD_CONTRACT.md — Role-Scoped Dashboards Specification

AviaSAFE SMS Platform
Status: DRAFT
Purpose: Single source of truth for the four role-scoped dashboards, their
data sources, KPI strips, and write scopes.

Base of analysis: `MODULE_A_CONTRACT.md`, `MODULE_B_CONTRACT.md`,
`MODULE_C_CONTRACT.md`, `RBAC_MODEL.md`, `FIRST_ACTION_KPI_VERIFICATION.md`,
`OVERDUE_MODEL_VERIFICATION.md`, `DISCOVERY_REPORT.md`, `SECURITY_REVIEW.md`,
and the current codebase. Endpoint claims cite `path:line`; data sources cite
the owning module contract. Unknowns are marked
**UNKNOWN — NEEDS HUMAN INPUT**.

---

## 1. OVERVIEW
**Purpose.** Explain why the platform has four role-scoped dashboards rather
than one universal dashboard, and fix each dashboard's role, data posture, and
architecture.

**Content.**

Why four, not one:
- Least privilege — each role sees only what its job needs (RBAC_MODEL.md §1).
- Distinct write scopes — a single dashboard cannot simultaneously be read-only
  for one role and write-heavy for another (RBAC_MODEL.md §5).
- Distinct data boundaries — a tenant operator, a department, an executive, and
  a state regulator consume different slices (Module A/B vs Module C).

Role mapping (1:1 with `RBAC_MODEL.md`):

| Dashboard | Canonical role(s) | RBAC § |
|---|---|---|
| Safety Manager | `TENANT_ADMIN` (Safety Manager) or `SAFETY_OFFICER` | §1, §5 |
| Department Head | `DEPT_ADMIN` | §1, §5 |
| Accountable Executive (AE) | `ACCOUNTABLE_EXECUTIVE` | §1, §5, §6 |
| State Regulator | `CAAN_SMD` | §1, §5 |

Read vs write posture:

| Dashboard | Posture | Writes permitted |
|---|---|---|
| Safety Manager | Read + full write | Full Module B workflow |
| Department Head | Read + narrow write | CAP response only (dept-scoped) |
| Accountable Executive | Mostly read + very narrow write | Acknowledge EIP + sign risk acceptances |
| State Regulator | Read-only | None |

Architecture:
- Dashboards consume **module APIs**; they own **no data** and never write
  Module A/B/C tables directly.
- All dashboard responses use the existing envelope
  `{"status", "timestamp", "data"}` (`routes/dashboard.py:26-31`).
- Dashboards are presentation over services: `DashboardService`
  (`routes/dashboard.py:20`), `AggregationService`, `SPIService`, `NHRCService`,
  `StateRiskService`, `CanCapService`, `HazardService`.
- A dashboard is a composition of (a) a KPI strip, (b) a workspace, and
  (c) a navigation set — the three are specified per role below.

**Current implementation.** Only two dashboard surfaces exist today: the
tenant airline dashboard (`routes/dashboard.py:64-279`) and the CAAN/regulator
dashboard (`routes/dashboard.py:287-372`, `routes/regulator_dashboard.py:26-93`).
There is no dedicated Department Head or AE dashboard; `nav-config.js:16`
links an `ae-dashboard.html` and `nav-config.js:14` a Key Indicators page for
Safety. Role scoping is enforced by per-route dependencies, not by dashboard.

**Gaps.** No unified role→dashboard router; the Safety Manager dashboard has no
dedicated page (Safety reuses `/safety.html`, `nav-config.js:14`); AE page is a
stub; the four-dashboard split is contract-only.

---

## 2. SAFETY MANAGER DASHBOARD

**2.1 Role scope.** `TENANT_ADMIN` (Safety Manager) and `SAFETY_OFFICER`
(RBAC_MODEL.md §1). Sees the whole tenant's Module A/B surface; performs the
full Module B safety-management workflow. This is the platform's operational
cockpit.

**2.2 Data sources.**
- Module B: `hazards`, `cans`, `caps`, `reports` (MOR/VSR), `flight_diversions`,
  `bow_tie_*`, `barrier_register` (MODULE_B_CONTRACT.md §2-§20).
- Module A: `surveys` maturity aggregates for the tenant
  (MODULE_A_CONTRACT.md §4).
- Module C: none (tenant scope only).

**2.3 KPI strip.** Five counters, left to right:

| # | KPI | Period total | Status breakdown buckets |
|---|---|---|---|
| 1 | Reports | `kpis.total_reports` | Open / In Process / Closed |
| 2 | Hazards | hazard `by_status` sum | Open / In Process / Closed |
| 3 | CANs | CAN `by_status` sum | Open / In Process / Closed |
| 4 | CAPs | CAP `by_status` sum | Open / In Process / Closed |
| 5 | EIP | escalated CAPs unacknowledged | shows `None` when zero |

Status→bucket mapping (source enums):
- Reports: `open_reports` / `closed_reports` (`routes/dashboard.py:34-40`).
- Hazards: `HazardStatus` = Open, Processing, Under Review, Pending Closure,
  Closed, Reopened (`FIRST_ACTION_KPI_VERIFICATION.md:64-79`); Open→Open;
  Processing/Under Review/Pending Closure/Reopened→In Process; Closed→Closed.
- CANs: `CANStatus` incl. Escalated (`models/can_cap.py:47`).
- CAPs: `CAPStatus` = In Progress, Under Review, Completed, Revision Required,
  Overdue (`models/can_cap.py:50-56`); Completed→Closed, Revision Required→In Process,
  Overdue→Open (attention).
- EIP: there is **no literal `EIP` state** today
  (`OVERDUE_MODEL_VERIFICATION.md:33-35`); derive as `caps.escalated_to_ae =
  true AND ae_signature IS NULL` (`db_models.py:437-444`; MODULE_B §23
  `:1157-1158`). Module B Decision 1 adds a persisted `"EIP"` status to
  `CAPStatus` (`MODULE_B_CONTRACT.md:569-572`), after which the counter reads
  the status directly.

**2.4 KPI behavior.**
- Each counter is **clickable** → opens a status breakdown (Open / In Process /
  Closed) for that KPI, and each bucket → the underlying records.
- Color coding (red / yellow / green) is applied to all five counters:
  - **Green** — no overdue and no open critical items.
  - **Yellow** — items In Process / Under Review / nearing target.
  - **Red** — any Overdue / Escalated / Revision Required item, or breach of the
    CAP `target_completion_date` (MODULE_B §20; `escalation_service.py:88-114`).
  - Exact thresholds (what "nearing" means per KPI) are **UNKNOWN — NEEDS HUMAN
    INPUT**.
- EIP renders the literal text `None` when the count is zero (no red/green).
- Counters honor the active period selector (§6).

**2.5 Workspace.**
- **Hazard list** — `GET /api/v1/hazards` (`routes/hazards.py:62`) with search,
  status, priority.
- **SRM queue** — hazards with `srm_flag=true` and no `srm_date`
  (`FIRST_ACTION_KPI_VERIFICATION.md:44-57`); open Bow-Tie/SRAM
  (`/sram/index.html`).
- **CAN-CAP register** — `GET /api/v1/cans` (`routes/can_cap.py:51`),
  `GET /api/v1/caps` (`:104`), and the unified
  `GET /api/v1/dashboard/master-register` (`routes/dashboard.py:169-249`).
- **EIP monitor** — escalated CAPs awaiting acknowledgement (Queue pattern,
  MODULE_B §23).
- **SAG / SRB** — SAG meetings/action items (MODULE_B §28) and SRB
  (MODULE_B §29) once built.
- **Reports** — recent reports (`GET /api/v1/dashboard/recent`,
  `routes/dashboard.py:98-111`); reporting trends
  (`GET /api/v1/dashboard/trends`, `:124-131`).
- **SMS maturity** — `GET /api/v1/dashboard/airline/sms-maturity`
  (`routes/dashboard.py:252-279`).

**2.6 Write scope.** Full Module B workflow (RBAC_MODEL.md §5):
hazard create/triage/enrich/status/assign; Bow-Tie/SRAM save; CAN issue;
CAP create/review/status; SAG/SRB and bulletin authoring. No Module C writes.
Endpoints: `POST /api/v1/hazards` (`routes/hazards.py:30`),
`PATCH /api/v1/hazards/{id}/status` (`:153`),
`PATCH /api/v1/hazards/{id}/assign` (`:167`),
`PUT /api/v1/hazards/{id}/sram/save` (`:246`),
`POST /api/v1/cans` (`routes/can_cap.py:19`),
`POST /api/v1/cans/{id}/caps` (`:211`),
`PATCH /api/v1/caps/{id}/review` (`:295`),
`PATCH /api/v1/caps/{id}/status` (`:325`).

**2.7 API surface.**

| Area | Endpoint | Source |
|---|---|---|
| KPIs | `GET /api/v1/dashboard/overview` | `routes/dashboard.py:64-83` |
| Hazard stats | `GET /api/v1/hazards/stats` | `routes/hazards.py:109-110` |
| CAN/CAP stats | `GET /api/v1/cans/stats` | `routes/can_cap.py:92-101` |
| Master register | `GET /api/v1/dashboard/master-register` | `routes/dashboard.py:169-249` |
| Trends | `GET /api/v1/dashboard/trends`, `/risk-trends` | `routes/dashboard.py:124-146` |
| Reports | `GET /api/v1/dashboard/recent` | `routes/dashboard.py:98-111` |
| Maturity | `GET /api/v1/dashboard/airline/sms-maturity` | `routes/dashboard.py:252-279` |
| SPI | `GET /api/v1/spi/tenant/{tenant_id}/values` | `api/v1/spi.py:49` |
| N-HRC | `GET /api/v1/nhrc/tenant/{tenant_id}/kpis` | `api/v1/nhrc.py:21` |

**2.8 Layout (blueprint).**
```
+--------------------------------------------------------------+
| Header: user | tenant | module badges | period selector       |
+---------+---------+---------+---------+----------------------+
| Reports | Hazards |  CANs   |  CAPs   |  EIP                 |  KPI strip (5)
+---------+---------+---------+---------+----------------------+
| [click KPI] status breakdown: Open | In Process | Closed     |
+--------------------------------------------------------------+
| Left rail                 | Main workspace                   |
|  - Hazard list            |  - Dashboard panels:             |
|  - SRM queue              |    risk distribution / trends    |
|  - CAN-CAP register       |    recent reports                |
|  - EIP monitor            |    SMS maturity                  |
|  - SAG / SRB              |                                  |
+--------------------------------------------------------------+
```

**Current implementation.** Source endpoints exist and are tenant-scoped
(`routes/dashboard.py` airline block). KPI strip, color coding, EIP counter,
and the dedicated page do not exist.

**Gaps.** No `/safety` KPI-strip page specified in code; EIP requires a derived
query or the Module B `"EIP"` status; color thresholds undefined; SRM queue has
no endpoint.

---

## 3. DEPARTMENT HEAD DASHBOARD

**3.1 Role scope.** `DEPT_ADMIN` (Department Head; RBAC_MODEL.md §1). Sees only
their department's CANs/CAPs and anything assigned to them; writes CAP responses
only. Department restriction is by email prefix (`get_department_scope`,
`middleware/auth.py:209-220`).

**3.2 Data sources.** Module B only, filtered to the department: `cans`, `caps`
(via `department` filter), `reports` (own department). No Module A/C data.

**3.3 KPI strip.** Three counters: **CANs | CAPs | EIP assigned to the
department**. Same clickable → Open / In Process / Closed breakdown and
red/yellow/green coding as §2.4. EIP `None` when zero.

**3.4 Workspace.**
- CANs assigned to the department (`GET /api/v1/cans`, dept-scoped).
- CAPs to draft / submit (`GET /api/v1/caps` `routes/can_cap.py:104-138`;
  submit via `PATCH /api/v1/caps/{id}` `:271`).
- CAP response evidence (attachments — **UNKNOWN / not built**, Module B §27).
- My Tasks queue (`/dashboard/my-tasks.html`, `nav-config.js:15`).

**3.5 Write scope.** CAP response only (RBAC_MODEL.md §5):
draft/update/submit a CAP against an issued CAN. No CAN issuance, no hazard
writes. Endpoint: `PATCH /api/v1/caps/{cap_id}` (`routes/can_cap.py:271`) with
department scope enforced by `get_department_scope` (`auth.py:209-220`).

**3.6 API surface.**

| Area | Endpoint | Source |
|---|---|---|
| CAN/CAP stats | `GET /api/v1/cans/stats` (passes `department`) | `routes/can_cap.py:92-101` |
| CAPs | `GET /api/v1/caps` | `routes/can_cap.py:104-138` |
| Master register | `GET /api/v1/dashboard/master-register` | `routes/dashboard.py:169-249` |
| CAP update | `PATCH /api/v1/caps/{cap_id}` | `routes/can_cap.py:271` |

**3.7 Layout.**
```
+--------------------------------------------------------------+
| Header: user | tenant | dept badge | period selector         |
+----------------+----------------+----------------------------+
|      CANs      |      CAPs      |   EIP (dept)               |  KPI strip (3)
+----------------+----------------+----------------------------+
| CANs assigned          | CAPs to draft / submit             |
|  - ref, status, due    |  - action plan, evidence, submit   |
+------------------------+------------------------------------+
| My Tasks queue (assigned items)                              |
+--------------------------------------------------------------+
```

**Current implementation.** Master register and CAN/CAP list already accept a
`department` filter (`routes/dashboard.py:169-249`; `routes/can_cap.py:104-138`);
`get_department_scope` restricts 145/CAMO/ops accounts
(`auth.py:202-220`). No dedicated department dashboard page.

**Gaps.** No department KPI endpoint; no department page; department mapping is
email-prefix based, not a first-class attribute
(`auth.py:202-206`); evidence upload missing (Module B §27).

---

## 4. ACCOUNTABLE EXECUTIVE DASHBOARD

**4.1 Role scope.** `ACCOUNTABLE_EXECUTIVE` (Doc 9859 AE role; RBAC_MODEL.md
§1/§6; MODULE_B_CONTRACT.md §22). The AE is accountable for the SMS, cannot be
delegated, and has a deliberately narrow write surface. The dashboard is
primarily read-only with two action queues.

**4.2 Data sources.**
- Module B: `hazards` (response-time inputs), `caps` (escalations),
  `sram_risk_register` (acceptances).
- Module A: `surveys` maturity trends.
- Module C: national/industry trends where the AE is a tenant admin with
  Module C view (RBAC_MODEL.md §3) — read-only.

**4.3 KPI strip (numerical, no color band).** Per the AE KPI decision, these
KPI values are rendered as numbers only — **no red/yellow/green banding**.

| KPI | Definition | Shape |
|---|---|---|
| **Hazard Response Time** | Average days from hazard registration to first action | `data.kpis.avg_days_registration_to_first_action` |
| Hazards still Received | Count of open hazards | `data.kpis.hazards_received` |
| Hazards total (period) | Denominator for response rate | `data.kpis.hazards_total` |
| Received rate | `received / total` | `data.kpis.received_rate` |
| EIP awaiting AE | Escalated CAPs unacknowledged | derived (MODULE_B §23) |
| Risk acceptances pending | SRAM entries awaiting signature | derived (MODULE_B §17/§23) |

Hazard Response Time computation (from `FIRST_ACTION_KPI_VERIFICATION.md`)
```
first_action = LEAST(
      COALESCE(h.priority_date, h.created_at),   -- prioritization set
      COALESCE(h.srm_date,          '+infinity'), -- SRM conducted (≈ started)
      COALESCE(MIN(c.issued_at),    '+infinity')) -- first CAN issued
days = DATE(first_action) - DATE(h.created_at)   -- clamp negatives to 0
avg  = round(AVG(days), 1)                        -- hazards WITH a first_action
```
Inputs verified: `hazards.created_at` (`db_models.py:121-123`),
`hazards.priority_date` (`:111`), `hazards.srm_date` (`:103`),
`cans.issued_at` (`:299`). Shape mirrors the existing `avg_closure_days`
null-when-empty convention (`FIRST_ACTION_KPI_VERIFICATION.md:80-91,133-139`).
`Received` reuses `hazards.status='Open'` (`FIRST_ACTION_KPI_VERIFICATION.md:118`).
Exclude `is_demo` hazards (recommended, `FIRST_ACTION_KPI_VERIFICATION.md:121,149`).

**4.4 Workspace.**
- Trend charts (hazards, reports, CAPs, maturity) with a period filter
  (30d / 90d / 1y / custom; §6).
- Risk profile / distribution, top hazards, and SMS maturity trend.
- Read-only drill-down into any KPI.

**4.5 Action queues.**
- **Queue 1 — Escalated CAPs awaiting acknowledgement** → acknowledge → `EIP`
  (`caps.escalated_to_ae = true AND ae_signature IS NULL`,
  `db_models.py:437-442`; MODULE_B §23 `:1157-1158`).
- **Queue 2 — Risk acceptances awaiting AE signature** → SRAM entries with
  `accepted=false`, filtered to the §2.3.6.6 authority tier of the **initial**
  risk (`sram_risk_register` `db_models.py:1451-1452`; MODULE_B §23
  `:1159-1161`).
- AE may **acknowledge/direct/continue**, never reject; the decision is
  **terminal** (MODULE_B §22 `:1108-1112`).

**4.6 Write scope (narrow).** Only: (a) acknowledge an escalated CAP (→ EIP),
(b) sign a risk acceptance. No hazard/CAN/CAP authoring, no tenant settings.
Non-delegability enforced at API (`get_accountable_executive`,
`auth.py:245-253`), service (`accept_risk` `sram_service.py:366-402`), and DB
(immutable `accepted_by`/`ae_signature`) — RBAC_MODEL.md §6.

**4.7 API surface.**

| Area | Endpoint | Source |
|---|---|---|
| CAPs (queue feed) | `GET /api/v1/caps` (no `escalated_to_ae` filter today) | `routes/can_cap.py:104-138`; MODULE_B §23 `:1163-1168` |
| AE decision | `PATCH /api/v1/caps/{cap_id}/review` (writes `ae_signature`) | `routes/can_cap.py:295`; `can_cap_service.py:957-1009` |
| Risk register | `GET /api/v1/sram/risk-register/{tenant_id}` | MODULE_B §23 `:1169` |
| Accept risk | `accept_risk` service path | `sram_service.py:366-402` |
| Hazard response KPI | **NEW** (does not exist) | `FIRST_ACTION_KPI_VERIFICATION.md:131` |
| Maturity trend | `GET /api/v1/dashboard/airline/sms-maturity` | `routes/dashboard.py:252-279` |

**4.8 Layout.**
```
+--------------------------------------------------------------+
| Header: user | tenant | "Executive" | period selector        |
+---------------+---------------+---------------+---------------+  KPI strip
| Hazard Resp.  | Received      | EIP awaiting  | Acceptances   |  (numeric,
| (days)        | (count)       | AE            | pending       |   no color)
+---------------+---------------+---------------+---------------+----------+
| Queue 1: Escalated CAPs to acknowledge → EIP                 |
|  - ref | hazard | reason | escalated_at | [Acknowledge]        |
+--------------------------------------------------------------+
| Queue 2: Risk acceptances awaiting signature (§2.3.3)        |
|  - ref | initial risk | authority tier | [Sign] [View]        |
+--------------------------------------------------------------+
| Trend charts (read-only): hazards / reports / CAPs / maturity |
+--------------------------------------------------------------+
```

**Current implementation.** `get_accountable_executive` exists but is applied
only to the closure route (`routes/verification.py:76`), never to CAN/CAP
(MODULE_B §22 `:1114-1120`). No AE dashboard page (a link stub exists,
`nav-config.js:16`); risk register read exists (MODULE_B §23 `:1169`); the
hazard-response KPI has **no endpoint**.

**Gaps.** AE KPI endpoint missing (`FIRST_ACTION_KPI_VERIFICATION.md:131`);
`GET /api/v1/caps` lacks an `escalated_to_ae` filter (MODULE_B §23 `:1166`);
terminal/non-delegable enforcement not built (MODULE_B §22 `:1131-1136`);
`ACCOUNTABLE_EXECUTIVE` role does not exist as a literal
(`MODULE_B_CONTRACT.md:1121-1124`).

---

## 5. STATE REGULATOR DASHBOARD

**5.1 Role scope.** `CAAN_SMD` (State Regulator; RBAC_MODEL.md §1; Module C §1).
Cross-tenant, read-only national oversight.

**5.2 Data sources.** Module C only — read-only aggregation and state tables
(`state_risk_register`, `state_risk_categories`, `caan_reports`, `psoe_*`,
`regulatory_reports`); Module A/B data reaches it only through the aggregation
layer (Module C §2, MODULE_C_CONTRACT.md §2-§12).

**5.3 KPI strip (national aggregates).**
- State SPI values/status (`GET /api/v1/spi/state/values`, `/status`;
  `api/v1/spi.py`).
- N-HRC State KPIs (`GET /api/v1/nhrc/state/kpis`, `api/v1/nhrc.py:34`).
- State risk register counts by ICAO category
  (`GET /api/v1/state-risk/aggregate`, `api/v1/state_risk.py:19`).
- Industry maturity averages (`GET /api/v1/regulator/industry-averages`,
  `routes/regulator_dashboard.py:26`).
- PSOE completion (`/api/v1/supabase/psoe/*`).

**5.4 Workspace.**
- State trends (`GET /api/v1/dashboard/caan/trends`, `routes/dashboard.py:297`).
- Benchmarks (`GET /api/v1/dashboard/caan/benchmark`, `:365`;
  `GET /api/v1/regulator/benchmark/{tenant_id}`, `regulator_dashboard.py:64`).
- Top hazards (`GET /api/v1/regulator/top-hazards`, `:37`).
- State risk register (`GET /api/v1/state-risk/aggregate`, `:19`;
  `/regulator/risk-register`, `:55`).
- PSOE assessments (`/api/v1/supabase/psoe/assessments`,
  `api/v1/endpoints/psoe.py:152`).
- SPI/SPT management (`/api/v1/spi/state/*`; SPT table per Module C §9).

**5.5 Hazard visibility rules.** Default: truncated 50-char hazard title +
full taxonomy + severity + probability + risk index; **no description, no
reporter identity** (Module C HV-1, `MODULE_C_CONTRACT.md:894-896`; truncation
`aggregation_service.py:201`). Escalation: CAAN may request full detail with a
stated reason → temporary, auto-revoked access (24 h default), every escalation
audited as `CAAN_ESCALATED_READ` (Module C HV-2, `:897-901`; Q12.1/Q12.2).
Reporter identity and raw survey responses are never visible (Module C HV-3).

**5.6 Write scope.** **None — read-only** (RBAC_MODEL.md §5). The only
state-adjacent writes are PSOE run/close (`CAAN_SMD` only, Module C Q4.3) and
SPT target setting, both Module C-internal, not tenant writes.

**5.7 API surface.**

| Area | Endpoint | Source |
|---|---|---|
| Industry averages | `GET /api/v1/regulator/industry-averages` | `regulator_dashboard.py:26` |
| Top hazards | `GET /api/v1/regulator/top-hazards` | `regulator_dashboard.py:37` |
| Risk trends | `GET /api/v1/regulator/risk-trends` | `regulator_dashboard.py:46` |
| Risk register | `GET /api/v1/regulator/risk-register` | `regulator_dashboard.py:55` |
| Benchmark | `GET /api/v1/regulator/benchmark/{tenant_id}` | `regulator_dashboard.py:64` |
| Export | `GET /api/v1/regulator/export/{pdf,excel}` | `regulator_dashboard.py:74,85` |
| CAAN overview | `GET /api/v1/dashboard/caan/overview` | `routes/dashboard.py:287` |
| CAAN state | `GET /api/v1/dashboard/caan/state` | `routes/dashboard.py:337` |
| State risk | `GET /api/v1/state-risk/aggregate` | `api/v1/state_risk.py:19` |
| State SPI | `GET /api/v1/spi/state/{values,status}` | `api/v1/spi.py` |
| State N-HRC | `GET /api/v1/nhrc/state/kpis` | `api/v1/nhrc.py:34` |
| PSOE | `/api/v1/supabase/psoe/*` | `api/v1/endpoints/psoe.py:152-280` |

**5.8 Layout.**
```
+--------------------------------------------------------------+
| Header: user | "CAAN" | regulator scope | period selector    |
+--------+--------+--------+--------+--------------------------+
| SPIs   | N-HRC  | State  | Industry| PSOE                   |  KPI strip
|        | KPIs   | risk   | maturity| completion             |
+--------+--------+--------+--------+--------------------------+
| State trends | Benchmarks | Top hazards                      |
+--------------------------------------------------------------+
| State Risk Register (by ICAO category)                       |
|  - truncated titles + taxonomy + risk index + [Escalate]     |
+--------------------------------------------------------------+
| PSOE assessments | SPI/SPT targets | Share/export            |
+--------------------------------------------------------------+
```

**Current implementation.** Most endpoints exist
(`routes/dashboard.py` CAAN block `:287-372`; `regulator_dashboard.py:26-93`;
`api/v1/state_risk.py`; state `spi`/`nhrc`). Several are **unauthenticated or
under-authorized** (SECURITY_REVIEW.md H1 `:48-50`, H2 `:52-54`), and
`regulator_dashboard.py` uses `get_caan_user` today (`:7,29`) — note the H2
finding predates hardening; verify current state.

**Gaps.** No escalation UI/endpoint (Module C HV-4 is spec-only); state SPI
trend is a placeholder (`spi_service.py:343,352`); no governance/uniform
CAAN_SMD gating (Module C SDCPS-7); unauthenticated `nhrc`/`spi` surfaces.

---

## 6. SHARED COMPONENTS
**Purpose.** Define the common UI/UX building blocks reused by all four
dashboards.

**Content.**
- **Navigation** — role-based, driven by `NAV_CONFIG`
  (`public/js/nav-config.js:7-96`); role resolution via `getUserRoleType`
  (`:100-111`) which maps `SUPER_ADMIN`→SUPER, `CAAN_SMD`/`CAAN_ADMIN`/
  `CAAN_AUDITOR`→CAAN, `ae@`/`ae.`→AE, `AIRLINE_ADMIN`/`TENANT_ADMIN`→SAFETY,
  `DEPT_ADMIN`→DEPT_ADMIN, else ALL. Visibility filter `getVisibleNav`
  (`:113-135`).
- **Header** — current user, tenant, role/dept badge, and module indicators
  (which of `module_a_survey`/`module_b_srm`/`module_b_can_cap`/
  `module_c_regulator` are on for this tenant; §9).
- **Period selector** — 30d / 90d / 1y / custom. Backed by the `days` (or
  `period`) query parameter already used across endpoints
  (`routes/dashboard.py:66,116,126`); `custom` maps to explicit start/end.
- **Drill-down pattern** — counter → status breakdown (Open / In Process /
  Closed) → records list, preserving the period and filters.
- **Empty states** — null/array-empty responses render a neutral message (e.g.
  EIP `None`, `avg_closure_days` null `FIRST_ACTION_KPI_VERIFICATION.md:81`).
- **Loading states** — skeleton placeholders per KPI/panel; endpoints are
  synchronous.
- **Error handling** — the envelope returns `status`; services degrade to empty
  payloads on error (e.g. `routes/dashboard.py:77-83,263-278`). Dashboards must
  show a non-blocking error per panel, not a blank page.

**Current implementation.** `NAV_CONFIG`, `getUserRoleType`, `getVisibleNav`
exist (`nav-config.js`). Envelope + graceful empty fallbacks exist in
`routes/dashboard.py`. No formal shared component library or period-selector
contract; each page implements its own.

**Gaps.** `granularity` and `group_by` parameters (§7) are not implemented;
`nav-config.js` role types do not include `ACCOUNTABLE_EXECUTIVE` or
`SAG_MEMBER` (RBAC_MODEL.md §1); no reusable empty/loading/error components.

---

## 7. API CONTRACT
**Purpose.** Fix one response envelope and a common parameter grammar for all
dashboard endpoints.

**Content.**
- **Envelope** (matches `routes/dashboard.py:26-31`):
  ```json
  { "status": "success", "timestamp": "2026-09-21T12:00:00", "data": { } }
  ```
- **Standard parameters:**
  - `period` — `30d` | `90d` | `1y` | `custom` (existing endpoints use numeric
    `days`: `routes/dashboard.py:66,116,126`).
  - `granularity` — `day` | `week` | `month` | `quarter` — **not implemented**
    today; current trend endpoints bucket internally (e.g. `get_monthly_trends`
    `routes/dashboard.py:124-131`).
  - `group_by` — optional (`department`, `status`, `category`) — **not
    implemented** as a generic parameter.
- **Endpoints per dashboard** — see the tables in §§2.7, 3.6, 4.7, 5.7.
- Cross-tenant endpoints must validate caller/`tenant_ids` (SECURITY_REVIEW.md
  remediation 3 `:137`).

**Current implementation.** Envelope is consistent across `dashboard.py`. Only
ad-hoc query parameters exist (`days`, `page`, `page_size`, `status`,
`department`).

**Gaps.** No `granularity`/`group_by`; numeric `days` vs named `period`
inconsistency; no OpenAPI schema for dashboard payloads.

---

## 8. VISUAL DESIGN SYSTEM
**Purpose.** Establish a consistent visual language across the four dashboards.

**Content.**
- **Layout grid** — 5-column KPI strip across the top (3-column for Department
  Head), full-width main content below, optional left rail for operational
  lists (Safety Manager).
- **Chart types** — line (trends), bar (status breakdowns / frequencies),
  heatmap (risk matrix / N-HRC distribution), sparkline (KPI micro-trends).
- **Color palette** — module accents: Module A (survey) blue, Module B
  (hazard/risk) amber, Module C (regulator) slate/teal; status colors
  red / yellow / green for the KPI strips (§2.4). AE KPI strip uses **neutral
  ink only** (no status banding, §4.3).
- **Typography** — one sans-serif family; numeric KPIs in a tabular-figure
  weight; labels small-caps.
- **Iconography** — Font Awesome (already used,
  `nav-config.js:11,24,38,50,64,76,88`).
- **Spacing / density** — 8-px base unit; KPI cards equal height; dense tables
  for registers.

**Current implementation.** Font Awesome + `shell.js`/`nav-config.js` shared
shell exist (`DISCOVERY_REPORT.md:291-303`); pages are flat-named and styled
ad-hoc.

**Gaps.** No shared design tokens/CSS for the KPI strip, status colors, or
chart theming; **UNKNOWN — NEEDS HUMAN INPUT** whether a design system exists
outside the repo.

---

## 9. MODULE ACCESS AND FEATURE FLAGS
**Purpose.** Define how dashboards respond to tenant module flags.

**Content.** Canonical flags (RBAC_MODEL.md §3) and current code keys:

| Flag | Current key | Dashboards affected |
|---|---|---|
| `module_a_survey` | `module1` | Safety Manager, AE, Dept Head (survey maturity panels) |
| `module_b_srm` | `module2` | Safety Manager, Dept Head, AE (hazard/SRM/CAN/CAP) |
| `module_b_can_cap` | `module2` subset | Safety Manager, Dept Head (CAN/CAP register) |
| `module_c_regulator` | `module3`/`module4` | State Regulator, AE (national trends) |

Graceful degradation rules:
- If a module flag is OFF, hide its nav group (`getVisibleNav`,
  `nav-config.js:113-135`), drop its KPI counters, and render an empty state for
  its workspace panels.
- A dashboard with **all** its modules off shows a "module not enabled" panel,
  not an error.
- Regulator pages respect the regulator's own `module_access`
  (`db_models.py:1600`); tenant pages respect `tenants.module_access`
  (`db_models.py:1563`).

**Current implementation.** Flags stored and inheritable
(`production_seed.py:30-93`); admin toggles (`admin.py:1016-1207`); frontend nav
gating by module (DISCOVERY_REPORT.md:300). No dashboard-level flag gating.

**Gaps.** Purpose-named flags do not exist; `module_b_can_cap` has no add-on
flag; backend/frontend `module3` mismatch (DISCOVERY_REPORT.md:61,256,343).
**Decision needed before Compliance Matrix** (RBAC_MODEL.md §11 Q-R5).

---

## 10. IMPLEMENTATION NOTES
**Purpose.** Record dashboard implementation state, gaps, and migration path.

**Content — current status.**
- Tenant airline dashboard: implemented (`routes/dashboard.py:64-279`).
- CAAN/regulator dashboard: implemented (`routes/dashboard.py:287-372`;
  `routes/regulator_dashboard.py:26-93`).
- CAN/CAP/hazard stats + master register: implemented
  (`routes/can_cap.py:92-101`; `routes/hazards.py:109`; `routes/dashboard.py:169-249`).
- Role-based nav: implemented (`nav-config.js`).
- Department scoping: implemented (`auth.py:209-220`).
- Envelope: implemented (`routes/dashboard.py:26-31`).

**Content — gaps.**
- No dedicated Safety Manager / Department Head / AE pages; AE page is a stub
  (`nav-config.js:16`).
- AE Hazard-Response-Time KPI has **no endpoint**
  (`FIRST_ACTION_KPI_VERIFICATION.md:131`).
- No `escalated_to_ae` filter on `GET /api/v1/caps` (MODULE_B §23 `:1163-1168`).
- No literal `EIP` state (OVERDUE_MODEL_VERIFICATION.md:33-35).
- No `granularity`/`group_by` parameters; `period` vs `days` inconsistency.
- Under-authorized regulator/SPI/N-HRC surfaces (SECURITY_REVIEW.md H1/H2).
- NAV_CONFIG role types exclude `ACCOUNTABLE_EXECUTIVE`/`SAG_MEMBER`.

**Content — migration path.**
1. Define role→dashboard routing and build the four pages on the shared shell.
2. Add the AE KPI endpoint (registration→first-action) per
   `FIRST_ACTION_KPI_VERIFICATION.md` §4/§6.
3. Add AE action-queue endpoints (escalated CAPs, pending acceptances) and the
   terminal/non-delegable gate (MODULE_B §22; RBAC_MODEL.md §6).
4. Add `period`/`granularity`/`group_by` to the dashboard API and a shared
   period selector.
5. Harden regulator/SPI/N-HRC authorization (SECURITY_REVIEW remediation 3).
6. Implement the hazard escalation UI + `CAAN_ESCALATED_READ` audit (Module C
   HV-2/HV-4).

---

## 11. OPEN QUESTIONS
**Purpose.** Enumerate unresolved dashboard decisions.

**Content.**
- **Q-D1** KPI color thresholds: what makes each counter yellow vs red per KPI?
  **UNKNOWN — NEEDS HUMAN INPUT.**
- **Q-D2** EIP source: derive from `escalated_to_ae`/`ae_signature` now, or wait
  for the persisted `"EIP"` CAP status (MODULE_B Decision 1)? **Decision
  needed.**
- **Q-D3** Hazard Response Time: accept `srm_date` (conducted) as a proxy for
  "SRM started", or add `sram_started_at`?
  (`FIRST_ACTION_KPI_VERIFICATION.md:142`). **Decision needed.**
- **Q-D4** "Received" definition: literal `Open` only, or unmapped legacy
  status strings too? (`FIRST_ACTION_KPI_VERIFICATION.md:146`). **Decision
  needed.**
- **Q-D5** Do never-actioned hazards belong in the response-time average, or
  only in the received count?
  (`FIRST_ACTION_KPI_VERIFICATION.md:148`). **Decision needed.**
- **Q-D6** Canonical module flags + `module3` mismatch (RBAC_MODEL.md §11
  Q-R5). **Decision needed before Compliance Matrix.**
- **Q-D7** Is `module_b_can_cap` an independent add-on flag? (RBAC_MODEL.md
  Q-R6). **UNKNOWN — NEEDS HUMAN INPUT.**
- **Q-D8** AE dashboard scope: tenant-only, or does the AE also see national
  trends (Module C)? **UNKNOWN — NEEDS HUMAN INPUT.**
- **Q-D9** Does a design system/token set exist outside the repo? **UNKNOWN —
  NEEDS HUMAN INPUT.**
- **Q-D10** Should the Department Head dashboard include reporting (MOR/VSR) or
  remain CAP-only? **UNKNOWN — NEEDS HUMAN INPUT.**

---

*End of DASHBOARD_CONTRACT.md. Status: DRAFT. Derived from the three module
contracts, RBAC_MODEL.md, and the current codebase; implementation is a
separate phase. No fixes or implementations are proposed.*
