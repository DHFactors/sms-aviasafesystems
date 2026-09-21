# RBAC_MODEL.md — Role-Based Access Control Specification

AviaSAFE SMS Platform
Status: DRAFT
Purpose: Single source of truth for roles, capabilities, module access, and
tenant isolation across the platform.

Base of analysis: `MODULE_A_CONTRACT.md`, `MODULE_B_CONTRACT.md`,
`MODULE_C_CONTRACT.md`, `DISCOVERY_REPORT.md`, `SECURITY_REVIEW.md`,
`OVERDUE_MODEL_VERIFICATION.md`, `FIRST_ACTION_KPI_VERIFICATION.md`, and the
current codebase. Every code claim cites `file:line`; every role/capability
traces to a module-contract section. Unknowns are marked
**UNKNOWN — NEEDS HUMAN INPUT**.

---

## 1. ROLES (canonical list)
**Purpose.** Enumerate every platform role with its alias, scope, description,
and who may assign it.

**Content.**

| Role (canonical) | Alias (legacy) | Scope | Description | Who assigns it |
|---|---|---|---|---|
| `SUPER_ADMIN` | — | Platform | Developer/platform owner; cross-tenant all; exclusive | Out-of-band (`users.is_developer`, `admin.py:1806-1810`) |
| `CAAN_SMD` | `regulator` | Regulator | State Regulator (CAAN); cross-tenant read of aggregated/state data | `SUPER_ADMIN` via regulator admin |
| `TENANT_ADMIN` | `AIRLINE_ADMIN`, `safety_manager` (UI) | Tenant | Safety Manager; full tenant Module B workflow + Module A/C views | `SUPER_ADMIN` / onboarding (`config.py:156`) |
| `ACCOUNTABLE_EXECUTIVE` | — (today stubbed by `AIRLINE_ADMIN`) | Tenant (executive) | Accountable Executive (Doc 9859); terminal CAP/EIP + risk acceptance | `SUPER_ADMIN` / tenant provisioning (one per tenant) |
| `DEPT_ADMIN` | `department_head` | Tenant (department) | Department Head; CAN/CAP response within own department only | `TENANT_ADMIN` / `SUPER_ADMIN` (`config.py:157`) |
| `SAFETY_OFFICER` | `safety_manager` (UI label) | Tenant | Safety Officer; hazard triage/enrichment/SRM, CAN/CAP operate | `TENANT_ADMIN` (`config.py:158`) |
| `STAFF` | `USER` | Tenant (self) | Employee; submit reports/surveys, view own submissions | `TENANT_ADMIN` (`config.py:159`) |
| `SAG_MEMBER` | — | Tenant | Safety Action Group member; SAG review + safety-risk acceptance at the Acceptable tier | `TENANT_ADMIN` / Safety Manager (Module B §28) |
| `REGULATORY_LIAISON` (potential) | — | Tenant | Submits MOR/regulatory reports to CAAN (Module B §30) | **UNKNOWN — NEEDS HUMAN INPUT** |

Notes:
- Canonical vs legacy aliases are normalized in `core/rbac.py:49-61`
  (`AIRLINE_ADMIN`→`tenant_admin`, `CAAN_SMD`→`regulator`,
  `SAFETY_OFFICER`→`safety_manager`, `DEPT_ADMIN`→`department_head`,
  `USER`/`STAFF`→`employee`).
- The authoritative role string is stored on `users.role`
  (`DISCOVERY_REPORT.md:192`); there is no multi-role/claims table today.
- `ACCOUNTABLE_EXECUTIVE` and `SAG_MEMBER` are NEW literal roles not yet in
  `config.py` role lists (`MODULE_B_CONTRACT.md:1549-1555`, `:1121-1124`).
- PSOE additionally references `CAAN_ADMIN` / `CAAN_AUDITOR` in its edit-role
  set (`MODULE_C_CONTRACT.md:451`; `api/v1/endpoints/psoe.py:49-52`) — these are
  **not** canonical platform roles; **UNKNOWN — NEEDS HUMAN INPUT** (reconcile).

**Current implementation.** Role constants and alias groups exist
(`config.py:145-161`); per-route dependencies exist (`middleware/auth.py:160-258`).
No role registry table beyond `users.role`; no multi-role support.

**Gaps.** New roles (`ACCOUNTABLE_EXECUTIVE`, `SAG_MEMBER`) unimplemented;
`REGULATORY_LIAISON` undesigned; `CAAN_ADMIN`/`CAAN_AUDITOR` un-reconciled.

---

## 2. CAPABILITIES PER ROLE
**Purpose.** Map capabilities to roles; group by domain.

**Content.** ✓ = allowed, — = denied. Roles: SA=`SUPER_ADMIN`,
CS=`CAAN_SMD`, TA=`TENANT_ADMIN`, AE=`ACCOUNTABLE_EXECUTIVE`,
SG=`SAG_MEMBER`, DH=`DEPT_ADMIN`, SO=`SAFETY_OFFICER`, ST=`STAFF`,
RL=`REGULATORY_LIAISON` (proposed).

*Survey / SMS Health*

| Capability | SA | CS | TA | AE | SG | DH | SO | ST | RL | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| Submit employee survey (anon/auth) | ✓ | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Module A §Overview (`MODULE_A_CONTRACT.md:17`) |
| View tenant SMS maturity | ✓ | — | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | Module A §4 (`:86-95`) |
| View national survey aggregation | ✓ | ✓ | — | — | — | — | — | — | — | Module A (`:73`); Module C §3 |

*Hazard & Risk (CAN/CAP, EIP, acceptance)*

| Capability | SA | CS | TA | AE | SG | DH | SO | ST | RL | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| Create/register hazard | ✓ | — | ✓ | — | — | — | ✓ | ✓ | ✓ | Module B §3; §26 (`:1449`) |
| Triage hazard | ✓ | — | ✓ | — | — | — | ✓ | — | — | Module B §26 (`:1447-1452`) |
| Enrich hazard | ✓ | — | ✓ | — | — | — | ✓ | — | — | Module B §27 (`:1509`) |
| Conduct SRM / bow-tie / barrier | ✓ | — | ✓ | — | — | — | ✓ | — | — | Module B §5/§8 |
| Create/manage CAN | ✓ | — | ✓ | — | — | — | ✓ | — | — | Module B §19 |
| Create/respond CAP | ✓ | — | ✓ | — | ✓ | ✓ | ✓ | — | — | Module B §20; §23 |
| Approve/close CAP | ✓ | — | ✓ | — | — | — | ✓ | — | — | Module B §20 |
| Escalate CAP to AE | ✓ | — | ✓ | — | — | — | ✓ | — | — | Module B §22 (`:1143`) |
| Acknowledge EIP / terminal AE decision | ✓ | — | — | ✓ | — | — | — | — | — | Module B §22 (`:1109-1112`) |
| Sign risk acceptance (§2.3.6.6 authority) | ✓ | — | ✓* | ✓ | ✓* | — | — | — | — | Module B §16 (`:807-832`), §17 |
| Manage SAG meeting/action items | ✓ | — | ✓ | — | ✓ | — | — | — | — | Module B §28 (`:1543-1555`) |
| Publish safety bulletin | ✓ | — | ✓ | — | — | — | — | — | — | Module B §31 (`:1668`) |
| View own submissions | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | baseline |

`*` Acceptance authority is tier-graded on the **initial** risk: Intolerable →
AE; Tolerable → Risk Owner/Functional Chief; Acceptable → SAG member/Safety
Manager (`MODULE_B_CONTRACT.md:814-824`). **Non-delegable** (§6 below).

*State Regulator (SDCPS, PSOE, PII visibility)*

| Capability | SA | CS | TA | AE | SG | DH | SO | ST | RL | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| View state SDCPS aggregates | ✓ | ✓ | — | — | — | — | — | — | — | Module C §2 (`:198-223`) |
| Read NULL-tenant (state) rows | ✓ | ✓ | — | — | — | — | — | — | — | Module C SN-C5 (`:1139-1145`) |
| Run/close PSOE assessment | ✓ | ✓ | — | — | — | — | — | — | — | Module C Q4.3 (`:1046`); `psoe.py:49-52` |
| Set State SPI/SPT | ✓ | ✓ | — | — | — | — | — | — | — | Module C §9 (`:758-769`) |
| CAAN hazard escalation (full detail − reporter identity) | ✓ | ✓ | — | — | — | — | — | — | — | Module C §12 (`:893-910`) |
| View reporter identity / raw survey responses | — | — | — | — | — | — | — | — | — | Module C DP-2 (`:552-555`) |

*Dashboards*

| Capability | SA | CS | TA | AE | SG | DH | SO | ST | RL | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| Safety Manager dashboard | ✓ | — | ✓ | — | — | — | — | — | — | §5 |
| Department Head dashboard | ✓ | — | — | — | — | ✓ | — | — | — | §5 |
| Accountable Executive dashboard | ✓ | — | — | ✓ | — | — | — | — | — | §5; Module B §23 |
| State Regulator dashboard | ✓ | ✓ | — | — | — | — | — | — | — | §5; Module C |
| Super-admin console | ✓ | — | — | — | — | — | — | — | — | Module C/DISCOVERY |

*Tenant admin*

| Capability | SA | CS | TA | AE | SG | DH | SO | ST | RL | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| Manage users/roles (own tenant) | ✓ | — | ✓ | — | — | — | — | — | — | §1; `auth.py` |
| Configure survey window / tenant config | ✓ | — | ✓ | — | — | — | — | — | — | Module A (`:32,80`) |

*Platform admin*

| Capability | SA | CS | TA | AE | SG | DH | SO | ST | RL | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| Provision tenant / create regulator | ✓ | — | — | — | — | — | — | — | — | `admin.py:1806-1810` |
| Toggle tenant/regulator modules | ✓ | — | — | — | — | — | — | — | — | `admin.py:1162-1207` |
| Seed / destructive ops (SUPER_ADMIN + SETUP_SECRET) | ✓ | — | — | — | — | — | — | — | — | `SECURITY_REVIEW.md:30` |

**Current implementation.** A coarse module gate exists
(`core/rbac.py:4-10`: `tenant_admin`/`safety_manager`/`department_head`/
`employee`/`regulator`), but it is role-name based (not the canonical roles)
and its middleware is **not registered** (`SECURITY_REVIEW.md:76-77`). Real
enforcement is per-route dependencies (`middleware/auth.py:160-258`).

**Gaps.** No capability table; `department_head`/`employee` are aliased from
legacy names (`DEPT_ADMIN`/`USER`); AE/SAG capabilities have no code path; the
capability matrix above is the contract, not the implementation.

---

## 3. MODULE ACCESS
**Purpose.** Define per-tenant module flags and which roles may reach each
module.

**Content.** Canonical flags (target) and their current code equivalents:

| Canonical flag | Current code key | Meaning | Default |
|---|---|---|---|
| `module_a_survey` | `module1` | Survey / SMS Health | ON (`production_seed.py:33`) |
| `module_b_srm` | `module2` | Hazard & Risk (base) | OFF (`production_seed.py:34`) |
| `module_b_can_cap` | `module2` subset | CAN/CAP add-on | OFF (no separate flag) |
| `module_c_regulator` | `module3`/`module4` | PSOE + Regulator dashboard | OFF (`production_seed.py:35-36`) |

Per-role accessible modules:

| Role | A (`module_a_survey`) | B (`module_b_srm`/`can_cap`) | C (`module_c_regulator`) |
|---|---|---|---|
| `SUPER_ADMIN` | ✓ | ✓ | ✓ |
| `CAAN_SMD` | aggregate only | aggregate/escalation only | ✓ |
| `TENANT_ADMIN` | ✓ | ✓ | PSOE view / submission |
| `ACCOUNTABLE_EXECUTIVE` | ✓ | ✓ (narrow write) | — |
| `SAG_MEMBER` | ✓ | ✓ | — |
| `DEPT_ADMIN` | ✓ | ✓ (dept-scoped) | — |
| `SAFETY_OFFICER` | ✓ | ✓ | PSOE view |
| `STAFF` | submit-only | submit/view-own | — |
| `REGULATORY_LIAISON` (proposed) | — | reports only | — |

**Current implementation.** Flags live on `tenants.module_access` JSONB
(`db_models.py:1563`) and `regulators.module_access` (`db_models.py:1600`),
keyed `module_1`/`module1` etc.; inheritance for SaaS regulators
(`production_seed.py:70-93`); admin toggles (`admin.py:1024-1207`). Middleware
module map exists but is unregistered (`rbac_middleware.py:8-20`).

**Gaps.** Purpose-named flags (`module_a_survey` …) do not exist in code — the
numeric `module1..module4` scheme is current. `module_b_can_cap` has no
add-on flag. **Backend/frontend module mismatch:** backend `module3` =
`/safety,/dashboard` while frontend gates PSOE on `module3`
(`DISCOVERY_REPORT.md:61,256,343`). Reconciliation is a **decision needed**
before the Dashboard contract.

---

## 4. TENANT ISOLATION
**Purpose.** Guarantee one tenant's data is unreachable from another except
through cross-tenant roles.

**Content.**
- Every query is filtered by `tenant_id` unless the actor holds a cross-tenant
  role (`CROSS_TENANT_ROLES = ["CAAN_SMD", "SUPER_ADMIN"]`,
  `config.py:147`; `TENANT_WIDE_ROLES` `config.py:161`).
- RLS is the enforcement mechanism: per-tenant policies
  `p_<table>_tenant_isolation` using
  `tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid`
  (`scripts/supabase_rls.sql:30-220`; `DISCOVERY_REPORT.md:197`).
- Cross-tenant RLS policy for CAAN/SUPER_ADMIN is present but **commented out**
  (`scripts/supabase_rls.sql:227-236`).
- NULL-tenant rows (state/national aggregates, e.g. `module_c_aggregates`) are
  visible only to CAAN_SMD via an **explicit RLS policy**:
  `USING (tenant_id IS NULL AND role = 'CAAN_SMD')`
  (Module C SN-C5, `MODULE_C_CONTRACT.md:1139-1145`; Q7.2 `:1050`).
- Department isolation: department users (`145`/`camo`/`ops` email prefixes) are
  further scoped to their department's CANs/CAPs (`auth.py:202-220`).

**Current implementation.** RLS enabled on the core domain tables
(`DB_VERIFICATION.md:181`); **disabled** on 6 tables — `caan_reports`,
`sms_maturity`, `state_risk_categories`, `dead_letter_queue`, `sms_dispatches`,
`audit_dispatches` (`DB_VERIFICATION.md:182`). Cross-tenant RLS not active.

**Gaps.**
- H2: `/api/v1/regulator/*` uses `get_current_user`, not `get_caan_user`, and
  `tenant_ids` is caller-controlled — any airline user can read other tenants'
  aggregates (`SECURITY_REVIEW.md:52-54`).
- H1: `/api/v1/nhrc/*` and `/api/v1/spi/*` have no auth dependency at all
  (`SECURITY_REVIEW.md:48-50`).
- Module C tables with RLS disabled (above) are readable beyond CAAN
  (`MODULE_C_CONTRACT.md:543`, DP-6).
- Cross-tenant role policy un-commented; NULL-tenant policy not yet created.

---

## 5. WRITE SCOPES PER DASHBOARD
**Purpose.** Bound each dashboard's write surface.

**Content.**

| Dashboard | Role | Write scope |
|---|---|---|
| Safety Manager | `TENANT_ADMIN` | Full Module B workflow: hazard triage/enrichment, SRM, CAN/CAP create+approve+close, SAG/bulletins, tenant config |
| Department Head | `DEPT_ADMIN` | **CAP response only**, scoped to the user's department (`auth.py:202-220`; Module B §20/§23) |
| Accountable Executive | `ACCOUNTABLE_EXECUTIVE` | **Narrow:** acknowledge EIP (→ EIP) and sign risk acceptances; AE cannot reject a CAP; decision terminal (Module B §22, `:1107-1112`) |
| State Regulator | `CAAN_SMD` | **Read-only** (aggregates, PSOE run/close, escalation request) — no tenant writes (Module C §1, §12) |

**Current implementation.** Safety Manager paths exist via per-route deps
(`get_safety_manager` `auth.py:182-195`). Dept scoping helper exists
(`get_department_scope` `auth.py:209-220`). AE dependency exists but is applied
only to the closure route (`routes/verification.py:76`), never to CAN/CAP
(`auth.py:245-258`; `MODULE_B_CONTRACT.md:1114-1120`).

**Gaps.** AE write surface is **not narrow** today — anyone with the tenant-admin
role can act on the full CAP/risk surface (`MODULE_B_CONTRACT.md:1137-1138`).
No dashboard-level scope enforcement; dashboards to be specified later.

---

## 6. NON-DELEGABILITY RULES
**Purpose.** Ensure high-consequence safety decisions are signed only by the
accountable authority and never on someone else's behalf.

**Content.**
- The `ACCOUNTABLE_EXECUTIVE` role is **non-delegable**: no other user may sign
  on the AE's behalf (Module B §22, `MODULE_B_CONTRACT.md:1112`).
- **Risk acceptance cannot be delegated** — CAAN SRM Manual §2.3.6.6: "Risk
  acceptance authority cannot be delegated… the initial level of risks should be
  duly considered." (quoted `MODULE_B_CONTRACT.md:817-819`).
- **Only the accepting AE can sign** the escalated-CAP terminal decision /
  risk acceptance; the authority is graded on the **initial** risk
  (`MODULE_B_CONTRACT.md:814-824`; `srm_engine.py:101-105`).
- Enforcement is required at **three layers**:
  - **API** — gate with `get_accountable_executive` (`auth.py:245-253`);
    reject any caller that is not the named AE.
  - **Service** — validate the accepting user's role against the §2.3.6.6
    authority table inside `accept_risk` (`sram_service.py:366-402`) and the
    escalated-CAP decision path (`can_cap_service.py:957-1009`).
  - **DB** — persist the immutable signer identity + timestamp
    (`sram_risk_register.accepted_by`/`accepted_on` `db_models.py:1452-1456`;
    `caps.ae_signature` JSONB block `db_models.py:437-444`), one AE per tenant,
    no recall after the AE decision except Closed/Escalated.

**Current implementation.** Documented, **not enforced**.
- `accept_risk` records whoever authenticates; no role check
  (`sram_service.py:366-402`; `MODULE_B_CONTRACT.md:829-832`).
- Any tenant-admin can set an escalated CAP to `Revision Required`/`Completed`
  and write `ae_signature` — no AE gate, no immutability
  (`MODULE_B_CONTRACT.md:1131-1136`).
- No DB uniqueness constraint for "one AE per tenant".

**Gaps.** Implement SN6 role validation + terminal-state immutability + the
"one AE per tenant" constraint; report an audited AE identity, never inferred
from a shared role (`MODULE_B_CONTRACT.md:1146-1148`).

---

## 7. ROLE CONFLICTS AND CONSTRAINTS
**Purpose.** Prevent dangerous role combinations and multi-tenant bleed.

**Content.**
- `ACCOUNTABLE_EXECUTIVE` **cannot be combined** with operational roles
  (Safety Manager, Safety Officer, Dept Admin)
- A single user **cannot hold both** `CAAN_SMD` and any tenant role.
- `SUPER_ADMIN` is **exclusive** (developer only; `SUPER_ADMIN_ROLES`
  `config.py:148`).
- `SAFETY_OFFICER` and the Safety-Manager capability (`TENANT_ADMIN`) may
  coexist in the same tenant but **must be distinct users**
  (`MODULE_B_CONTRACT.md:1449-1452`).
- Cross-tenant roles are disjoint from tenant roles
  (`CROSS_TENANT_ROLES` vs `TENANT_WIDE_ROLES`, `config.py:147,161`).

**Current implementation.** None. `users.role` is a single string
(`DISCOVERY_REPORT.md:192`), so combinations are impossible today but also
unenforced for the reverse risk (a user silently re-purposed). No constraint,
trigger, or validation enforces the rules above.

**Gaps.** Add a role-assignment validator (API + DB CHECK/trigger); define
whether multi-role is supported at all — **UNKNOWN — NEEDS HUMAN INPUT**.

---

## 8. AUDIT TRAIL
**Purpose.** Record every privileged action with enough context to reconstruct
who did what, to whom, in which tenant, and when.

**Content.** Every privileged action writes an `audit_logs` row with:
- `actor` / `actor_uid` — the acting user (`db_models.py:1651`).
- `target` / `target_type` / `target_id` — the affected object, if any
  (`db_models.py:1652-1654`).
- `tenant_id` — scope (`db_models.py:1657`).
- `action` — action type (`db_models.py:1650`).
- `metadata_json` — structured before/after payload (`db_models.py:1660`).
- `created_at` — timestamp (`db_models.py:1661`); plus `ip`, `request_id`
  (`db_models.py:1658-1659`).

Action families:
- Module C CAAN reads: `CAAN_READ_*` (Module C DP-3,
  `MODULE_C_CONTRACT.md:556-558`).
- Module C shares: `CAAN_SHARE_*` (Module C SS-2, `:616-618`).
- Module C escalation reads: `CAAN_ESCALATED_READ` (Module C HV-2, `:899-901`).
- Module B: `HAZARD_TRIAGED`, `HAZARD_TRIAGE_REVERSED`, `HAZARD_ENRICHED`
  (`MODULE_B_CONTRACT.md:631-636`).

**Current implementation.** `audit_logs` schema and indexes exist
(`db_models.py:1646-1668`); SSP-dispatch audits exist
(`MODULE_C_CONTRACT.md:535-537`). No general "regulator read" audit (Module C
G-5.4).

**Gaps.** No `CAAN_READ_*` / `CAAN_SHARE_*` / escalation audit writer; no
dashboard-level audit for privileged writes; no actor/target standardization.

---

## 9. IMPLEMENTATION NOTES
**Purpose.** Record current RBAC implementation state, gaps, and the migration
path.

**Content — current status.**
- Roles/aliases and alias groups defined (`config.py:145-161`;
  `core/rbac.py:49-61`).
- Per-route dependencies: `get_current_user`, `get_caan_user`
  (`auth.py:160-168`), `get_admin_user` (`:171-179`), `get_safety_manager`
  (`:182-195`), `get_responsible_manager` (`:223-242`),
  `get_accountable_executive` (`:245-258`), `get_department_scope` (`:209-220`).
- Module-gate middleware `RBACMiddleware` exists but is **never registered**
  (`rbac_middleware.py:71-73`; `SECURITY_REVIEW.md:76-77`).
- RLS live on core tables, off on 6 (`DB_VERIFICATION.md:181-182`).

**Content — gaps (from `SECURITY_REVIEW.md`).**
- **M5** RBAC/tenant-isolation middleware is dead code.
- **H1** `nhrc.py`/`spi.py` unauthenticated (IDOR read + unauthenticated SPI
  target write).
- **H2** `regulator_dashboard.py` uses any authenticated user, not
  `get_caan_user`; caller-controlled `tenant_ids`.
- **M1** token revocation not checked (`check_revoked=False`).
- `OVERDUE_MODEL_VERIFICATION.md` / `FIRST_ACTION_KPI_VERIFICATION.md` role-relevant
  findings: **UNKNOWN — NEEDS HUMAN INPUT** (not scanned in this pass).

**Content — migration path.**
1. Register/rewrite the RBAC middleware with canonical roles + purpose-named
   module flags; delete or wire up `rbac_middleware.py` (SECURITY_REVIEW
   remediation 6).
2. Apply `get_caan_user` + caller-tenant validation to `regulator_dashboard`,
   `nhrc`, `spi` (remediation 3).
3. Introduce literal roles `ACCOUNTABLE_EXECUTIVE`, `SAG_MEMBER`
   (`config.py` role lists) and the non-delegability enforcement (§6).
4. Add RLS: un-disable the 6 tables or document exemptions
   (`DB_VERIFICATION.md:182`); enable the CAAN cross-tenant policy and the
   NULL-tenant `CAAN_SMD` policy (`scripts/supabase_rls.sql:227-236`;
   Module C SN-C5).
5. Add audit action families (§8) and a role-assignment validator (§7).

---

## 10. CARRY-FORWARD FROM MODULE CONTRACTS
**Purpose.** Consolidate RBAC-relevant items handed off by the module
contracts.

**Content.**
- **From Module A:**
  - Survey submission is open (anonymous/authenticated) and must remain so
    (`MODULE_A_CONTRACT.md:17`).
  - Module C must never see individual tenant-identifiable `survey_responses`
    (`MODULE_A_CONTRACT.md:119`); only aggregates cross the boundary.
  - Survey role scoping for dashboards remains open
    (`MODULE_A_CONTRACT.md:213-219`).
- **From Module B:**
  - New `ACCOUNTABLE_EXECUTIVE` role; AE gates escalated CAPs + risk
    acceptances (`MODULE_B_CONTRACT.md:572-575`, §22).
  - New `SAG_MEMBER` literal role (`MODULE_B_CONTRACT.md:1549-1555`).
  - Non-delegability enforced at API + service + DB (SN6, §16/§17/§22).
  - Triage roles: `SAFETY_OFFICER` + safety-manager capability
    (`MODULE_B_CONTRACT.md:1449-1452`).
  - Two-signature acceptance (Team Leader/SM + AE/Dept Head) — §17.
- **From Module C:**
  - Uniform `CAAN_SMD` gating of regulator / PSOE / SPI / N-HRC / state-risk /
    SDC / Copilot routes (SDCPS-7; `MODULE_C_CONTRACT.md:1082-1098`).
  - Explicit NULL-tenant RLS policy `USING (tenant_id IS NULL AND
    role = 'CAAN_SMD')` (SN-C5, Q7.2).
  - Escalation: temporary, auto-revoked access (24 h default); full detail
    minus reporter identity (HV-2; Q12.1/Q12.2).
  - PSOE closing restricted to `CAAN_SMD` (Q4.3).
  - Audit actions `CAAN_READ_*`, `CAAN_SHARE_*`, `CAAN_ESCALATED_READ`.
  - Module B dependency: confidential-reporting owner (Q5.2) + hazard/report
    mapping columns require coordinated permission changes.

---

## 11. OPEN QUESTIONS
**Purpose.** Enumerate unresolved RBAC decisions.

**Content.**
- **Q-R1** Multi-role support: keep single `users.role`, or introduce a
  roles table? Affects all conflict rules in §7. **UNKNOWN — NEEDS HUMAN INPUT.**
- **Q-R2** `ACCOUNTABLE_EXECUTIVE` identity: Firebase custom claim vs
  `users.is_ae` flag vs dedicated role — Module B leaves this to the AE chunk
  (`MODULE_B_CONTRACT.md:1146-1148`). **Decision needed.**
- **Q-R3** `REGULATORY_LIAISON`: build it, or fold MOR submission into
  `SAFETY_OFFICER`/`TENANT_ADMIN` (Module B §30)? **UNKNOWN — NEEDS HUMAN INPUT.**
- **Q-R4** `CAAN_ADMIN` / `CAAN_AUDITOR` reconciliation with canonical
  `CAAN_SMD` (PSOE `_EDIT_ROLES`, `api/v1/endpoints/psoe.py:49-52`).
  **UNKNOWN — NEEDS HUMAN INPUT.**
- **Q-R5** Canonical module-flag names (`module_a_survey` etc.) vs the live
  `module1..module4` scheme; and the backend/frontend `module3` mismatch
  (`DISCOVERY_REPORT.md:61,256,343`). **Decision needed before Dashboard
  contract.**
- **Q-R6** Is `module_b_can_cap` a real add-on flag (independent of
  `module_b_srm`), or a subset of it? **UNKNOWN — NEEDS HUMAN INPUT.**
- **Q-R7** Whether a single AE is enforced by DB constraint or service check
  only (§6). **Decision needed.**
- **Q-R8** Audit retention/immutability for `CAAN_READ_*`/`CAAN_SHARE_*` rows.
  **UNKNOWN — NEEDS HUMAN INPUT.**
- **Q-R9** `OVERDUE_MODEL_VERIFICATION.md` and
  `FIRST_ACTION_KPI_VERIFICATION.md` role/capability findings not yet folded in.
  **UNKNOWN — NEEDS HUMAN INPUT.**

---

*End of RBAC_MODEL.md. Status: DRAFT. Derived from the three module contracts
and the current codebase; implementation is a separate phase. No fixes or
implementations are proposed.*
