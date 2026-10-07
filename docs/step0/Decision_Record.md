<!--
AUTHORITATIVE COPY.
Location: D:\Projects\aviasafesms\docs\step0\Decision_Record.md
Original (historical): D:\Projects\Project_Step0_Decision_Record.md
Copied: 2026-10-07
Edits must be made here, not in the original.
-->

# Project Step 0 — Decision Record

## Pre-integration gate sign-off (G1–G11)

Status: For SME sign-off — no development until signed

Date: 2026-10-07

Audience: Concept owner / Subject Matter Expert

Companion documents (same folder):

- `Project_Action_Plan_Finish_AviaSAFE_First.md`
- `Project_Convergence_Blueprint.md`
- `Project_Boundary_Charter_Addendum.md`
- `Project_Evalulation_Report.md`
- `SOURCE-DATA-CATALOG-AND-ARCHITECTURE-REPORT.md`

---

# 1. Purpose

This is the Phase 0 / Step 0 gate from the Convergence Blueprint and the Boundary Charter Addendum. It records the eleven pre-integration decisions so that no build, migration, or intelligence work begins before the direction is frozen. Each row needs a decision, a date, and an accountable owner. G4 and G10 must be frozen before any other development.

---

# 2. How to use this record

1. Read the recommended position for each gate (drawn from the companion documents).
2. Record the actual decision in the last column, or write "Adopt recommendation".
3. Sign the record at Section 4. Unsigned gates are treated as not decided.

---

# 3. Gate decisions

| Gate | Decision required | Owner | Recommended position (source) | Decision recorded / date |
|---|---|---|---|---|
| G1 | Approve the layer and object ownership map | SME | Adopt as written — one owner per object (Addendum §2–3) | |
| G2 | Approve the statutory-versus-protected reporting policy | SME / legal | Adopt the two-channel rule; statutory MOR travels its own legal path, protected data leaves only as intelligence (Addendum §4) | |
| G3 | Approve the canonical domain model and resolve the `risk_register` dual-shape defect | SME + technical | **RESOLVED 2026-10-07 — no dual-shape defect; see §3a** | ✓ 2026-10-07 |
| G4 | **Choose one identity and membership model** | SME + technical | One login: Supabase Auth (Blueprint C-02 / §8.3); membership: effective-dated, single active context (C-03). **Freeze before development.** | |
| G5 | Approve the SMS Maturity Index formula | SME | SMS360X governs the approved formula; AviaSAFE engine computes it. Formula definition pending — approve the owner and mandate the formula. | |
| G6 | Approve the RBO scoring model | SME | Approve before any explainability claim. Model definition pending — approve inputs, weights, bands, explanation view. | |
| G7 | Approve the OIP lifecycle and immutability rule | SME | Adopt the lifecycle; a published OIP is versioned and immutable for its period (Addendum §7) | |
| G8 | Approve default-deny RLS as the single access model | SME + technical | Adopt default-deny on all tenant-owned tables; no bypass path (Addendum §5) | |
| G9 | Confirm the legal basis for any regulator record-level access | SME / legal | Confirm the lawful basis; access is exceptional, purpose-bound, time-limited, audited (Addendum §5) | |
| G10 | **Decide the single tenant key scheme** | SME + technical | One scheme, e.g. deterministic slug (Blueprint §7; Addendum §3). **Freeze before development.** | |
| G11 | Enforce "no duplicate register, no duplicate intelligence engine" | All | Adopt as a binding rule for every phase (Blueprint §4; Addendum §8) | |

---

## 3a. G3 resolution (2026-10-07)

**RESOLVED 2026-10-07 — No dual-shape defect.** Evidence in `Project_Step0_G3_Final_Register_Map.md` confirms:

- `public.risk_register` = CAAN SRM Manual **§2.3.5 Risk Register**. Exact column match.
- `public.sram_risk_register` = CAAN SRM Manual **§2.3.3 Risk Acceptance Record**, not a second Risk Register. Columns include `accepted_*`, `alarp_justification`, `process_by`, `*_authority`.
- The historic "defect" was a name collision in migration `20260905153000_sram_tables.sql:102` (no-op on an existing table), not a data defect.
- No duplicate table. No migration required. Candidate tables are empty. Schema changes required are additive.

**Canonical register model:** Hazard Registration §2.1 (partial, split across `hazards` table), Risk Acceptance §2.3.3 (partial, split across `sram_risk_register` + `caps`), Barrier Register §2.3.4 (missing `srm_date`), Risk Register §2.3.5 (exact), Bow-Tie §2.3.1-2.3.2 (present). **Operator practice:** application must accept both Sita Air composite and Tara Air manual-direct layouts. Operator codes (`SA-Occ-*`, `SA-ORG-*`) require a canonical column. A Master Intake table is required for Sita Air practice.

**Step 2 of the Action Plan is superseded:** no "fix the dual-shape defect" action; replaced with "document the canonical register model and the operator-to-canonical mapping."

---

# 4. Freeze declaration and signature

By signing, the owner freezes **G4 (identity/membership)** and **G10 (single tenant key)** as the target for the combined product, and approves the remaining gates as recorded above. Any change to a frozen gate requires re-signing this record.

| Role | Name | Decision | Signature | Date |
|---|---|---|---|---|
| Concept owner / SME | | ☐ Approved  ☐ Approved with changes | | |
| Legal (G2, G9) | | ☐ Approved  ☐ Approved with changes | | |
| Technical lead (G3, G4, G8, G10) | | ☐ Approved  ☐ Approved with changes | | |

---

# 5. Exit criterion

This Step 0 gate is closed when every row in Section 3 has a recorded decision and this record is signed. Only then does Step 1 (close the audit blockers and security holes) begin. Open definition items G5 and G6 must have a named owner and a due date before Step 4 (the intelligence layer) starts.

---

# 6. Step 0 Confirmation Analysis — G3 correction

**G3 correction:** The Convergence Blueprint characterised the `risk_register` split as a defect. SME manual review of the CAAN SRM Procedure Manual §2.3.4 and §2.3.5 confirms it is not a defect. Two registers, two processes, both required. Step 2 of the Action Plan must drop the "unify `risk_register`" action and replace it with "document both registers and their processes". No schema change.
