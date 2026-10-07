<!--
AUTHORITATIVE COPY.
Location: D:\Projects\aviasafesms\docs\step0\Action_Plan.md
Original (historical): D:\Projects\Project_Action_Plan_Finish_AviaSAFE_First.md
Copied: 2026-10-07
Edits must be made here, not in the original.
-->

# Project Action Plan — Finish AviaSAFE First

## Stabilise-and-audit sequence for the Unified Product Vision v1.0

Status: Sequenced Action Plan (business steps, no code)

Date: 2026-10-07

Audience: Concept owner / Subject Matter Expert

Companion documents (same folder):

- `Project_Evalulation_Report.md`
- `Project_Convergence_Blueprint.md`
- `Project_Boundary_Charter_Addendum.md`
- `SOURCE-DATA-CATALOG-AND-ARCHITECTURE-REPORT.md`

---

# 1. The decision in one line

Finish AviaSAFE first — as **stabilise-and-audit**, not feature-build — and freeze the identity/membership decision (G4) and the tenant-key decision (G10) now, before any integration work, so the combined product never migrates twice.

---

# 2. Why AviaSAFE is first

- It is the only working asset: live, real operators, CAAN surfaces, 1062 tests, deployed data plane. SMS360X has no runtime.
- It is a prerequisite: the intelligence layer (OIP, RBO, M14) needs trustworthy registers to compute from. Intelligence cannot be validated on untrusted source data.
- "Finish" means **audit-ready and pilot-proven**, not more features. AviaSAFE is code-complete but audit-incomplete: 64 compliance rows = 9 implemented / 48 partial / 7 missing, and self-assessed NOT READY.

---

# 3. The one trap, and the two pre-committed decisions

If AviaSAFE is finished purely "as it is", it hardens three choices that conflict with the unified vision: Firebase auth, the single `role` string, and regulator access by cross-tenant aggregation. Fixing these before freeze is cheap; fixing them after is a migration.

**Lock now (decision only — no build cost):**

| Decision | Gate | Target | Why now |
|---|---|---|---|
| Identity / membership | G4 | One login provider; effective-dated membership model | Prevents two auth systems and a later identity migration |
| Tenant key | G10 | One tenant key scheme (e.g. deterministic slug) | Prevents key migration across every register |
| Regulator access rule | C-01 / G9 | OIP-only target; aggregation interim, inside operator intelligence only | Prevents hardening a rule the vision reverses |

Everything else may be finished as-is.

---

# 4. Sequenced action plan

## Step 0 — Record the decisions (no development)

- Approve the ownership map (G1) and the canonical domain model (G3).
- Lock G4 (identity/membership) and G10 (tenant key).
- Confirm operator-owns-operational-data / State-owns-state-intelligence and the OIP as the only path out of an operator.
- Exit: a signed decision record; development starts only after G1–G11 are logged.

## Step 1 — Close the audit blockers and the security holes → audit-ready

- Close the 7 Missing rows (5 unique requirements): confidential/voluntary reporting; AE non-delegability and acceptance authority; predictive analysis; prescriptive analysis; data governance.
- Fix the security holes: register the dead RBAC middleware; authorise the unauthenticated SPI/N-HRC paths (H1); stop caller-controlled `tenant_ids` (H2); enforce token revocation (M1).
- Correct the planning note: **State SPI/SPT persistence is a Partial row (Large effort), not one of the 7 Missing** — schedule it here as part of audit-readiness, not as a "missing row".
- Exit: all 7 Missing rows closed, one-signature acceptance retired, tenant isolation demonstrable, audit evidence present.

## Step 2 — Schema and tenancy hygiene

- Fix the `risk_register` dual-shape defect (legacy + SRAM) to one canonical shape.
- Enable RLS on the 6 RLS-disabled tables, or formally exempt and justify each.
- Exit: one shape per register; default-deny RLS on every tenant-owned table.

## Step 3 — Pilot

- Pilot with one operator, then CAAN.
- Confirm the CAAN position on single-signature interim acceptance and the §5.5 sharing boundary before any State-to-State exchange.
- Exit: a pilot-proven product and an audit evidence pack for CAAN.

## Step 4 — Only then open the SMS360X intelligence layer

- Sequence OIP → M14 State products → RBO, consuming AviaSAFE registers and measures.
- Set the SMS Maturity Index formula (G5) and RBO scoring model (G6) before either is claimed as explainable.
- Exit: one number per intelligence measure; State products produced without direct operator-database access.

---

# 5. Freeze list — do not do while finishing AviaSAFE

- Do not add new features; no scope beyond audit-readiness and pilot.
- Do not run two auth systems; do not extend the single `role` string.
- Do not deepen regulator cross-tenant browsing; keep aggregation interim.
- Do not build a second register or a second intelligence engine.

---

# 6. Definition of done

AviaSAFE is "finished" when the 7 Missing rows are closed, the security findings are remediated, one register and one shape exist per object, RLS is default-deny, and one operator plus CAAN have piloted it with an audit evidence pack — with G4 and G10 frozen so the intelligence layer can be added without migration.
