<!--
AUTHORITATIVE COPY.
Location: D:\Projects\aviasafesms\docs\step0\Convergence_Blueprint.md
Original (historical): D:\Projects\Project_Convergence_Blueprint.md
Copied: 2026-10-07
Edits must be made here, not in the original.
-->

# Project Convergence Blueprint

## Combining AviaSAFE (`D:\Projects\aviasafesms`) and SMS360X (`D:\Projects\sms360x`) into one product

Status: Strategic Blueprint for SME Decision

Date: 2026-10-07

Audience: Concept owner / Subject Matter Expert (no coding required to act on this document)

Companion documents (same folder):

- `Project_Evalulation_Report.md` — neutral comparison of the two projects
- `SOURCE-DATA-CATALOG-AND-ARCHITECTURE-REPORT.md` — SMS360X source data and open architecture questions

---

# 1. Purpose of this blueprint

This document answers one question:

> Can AviaSAFE and SMS360X be combined into something better than either alone, and if so, how should it be done?

It is written for a concept owner, not a developer. It explains, in plain terms:

- what each project already owns,
- what must be unified so the combination does not become two products glued together,
- a recommended target shape,
- a phased path from today to that target,
- the decisions only you (the SME) can make,
- the risks and how to manage them.

It contains no code and no instruction to write code. Phase 0 is decisions, not development.

---

# 2. The one-paragraph answer

Yes, they can be combined, and the combination is stronger than either part. AviaSAFE is a working operational safety-management system (registers, hazard/risk workflow, regulator oversight). SMS360X is a designed safety-intelligence and governance architecture (how data becomes intelligence, who owns what, and what leaves an operator). Put SMS360X's intelligence and ownership model **on top of** AviaSAFE's working operational core, define one shared vocabulary and one authorization model, and you get a single product that both runs an SMS day-to-day and produces defensible State/regulator intelligence. The main work is not coding — it is deciding ownership boundaries, the shared domain model, and which of the two existing implementations becomes the "system of record".

---

# 3. Why this is a real fit (reasoning)

Four facts make the fusion natural rather than forced:

1. **Same domain.** Both already model hazard, risk, barrier, occurrence/report, findings/actions, SPI, SPT, and the same ICAO frameworks (Annex 19, Doc 9859, Doc 10159, ADREP, HFACS). There is no conceptual translation problem at the safety level.
2. **Same market and institution.** Both target Nepal/CAAN operators and the State. Both even reference the same operators and the same NASP context.
3. **Opposite strengths.** AviaSAFE is strong where SMS360X is empty (running workflow, live deployment, tests, regulator surfaces). SMS360X is strong where AviaSAFE is weak (intelligence productization, ownership model, authorization rigor, historical lineage).
4. **Shared technical foundation.** Both run on PostgreSQL/Supabase with row-level security (RLS) as the tenant-isolation mechanism. The plumbing bet is already the same.

In short: they are two halves of one product that were built in the same house at different times.

---

# 4. Guiding principles

These principles should govern every decision in the merge. They are derived from the documents already approved in both projects.

1. **One system of record per object.** For each safety object (hazard, risk, barrier, occurrence, action, etc.) exactly one system is authoritative. No duplicated registers.
2. **Operator owns operational data. State owns state intelligence.** This ownership rule is already agreed in both projects and must be preserved.
3. **Intelligence is the product; registers are inputs.** Dashboards display intelligence; they do not define it.
4. **One authorization model.** One identity, one membership model, one RLS design. Two authorization models cannot coexist.
5. **Only intelligence leaves the operator.** The Operator Intelligence Pack (OIP) is the controlled boundary between operator data and the State.
6. **Evidence and history are preserved.** Every intelligence output must be traceable to source evidence and reproducible for its reporting period.
7. **Incremental, not "big bang".** Merge layer by layer, always keeping a working product.
8. **Fix the known blockers before adding new capability.** Both projects have open audit blockers; merging does not remove them.

---

# 5. What each project brings (asset inventory)

| Area | AviaSAFE brings (working) | SMS360X brings (designed) |
|---|---|---|
| Operational registers | Hazards, VSR/MOR reports, CAN/CAP, verifications, closures, flight diversions | Occurrence, hazard, risk, barrier, finding, action (mappers only, no runtime) |
| SRM method | Bow-Tie, barrier register (BSV), risk matrix, two-signature acceptance, AE escalation | Scenario-specific Risk-Barrier relationship, barrier assurance evidence chain, dependencies/common cause |
| SMS maturity | Survey scoring on 4 ICAO components / 12 elements, sms_maturity cache, LLM analysis | Module 1 SMS Maturity Intelligence (formula still open) |
| State capability | State risk register, state SPI/SPT, N-HRC (Nepal NASP), PSOE, SSP dispatch, regulator dashboard, PDF/Excel | M14 State Workspace S1-S10, RBO prioritization, NASP/SSP monitoring, OIP |
| Intelligence taxonomy | SPI/SPT, N-HRC, PSOE, descriptive analysis | 6 intelligence layers, OIP-01..07, Knowledge Network, Nano-Code intelligence |
| Governance | Tenant isolation, CAAN cross-tenant role, RBAC (partial), audit logs | State-Regulator-Operator membership hierarchy, default-deny RLS, non-owning regulator |
| Commercial | None implemented | Base/Professional/Advanced/Expert/State tiers |
| Validation | 1062 automated tests, UAT, live deployment | Synthetic 5-operator 36-month dataset + success criteria (not run) |
| Deployment | Live on Render + Firebase Hosting | Supabase DEV schema only (31 tables) |

Observation: the columns barely overlap at the capability level. That is exactly why merging adds value rather than duplicating.

---

# 6. Target architecture (business view, no code)

Think of the combined product as a stack. Data rises from operations to intelligence.

```
+--------------------------------------------------------------+
|  6. STATE & REGULATOR INTELLIGENCE (SMS360X M14 + AviaSAFE)  |
|     National profiles, RBO, SSP/NASP, PSOE, N-HRC            |
+--------------------------------------------------------------+
|  5. INTELLIGENCE PRODUCTS (SMS360X OIP-01..07)               |
|     Mandatory occurrence, performance, hazard, risk,         |
|     investigation, context, annual report                    |
+--------------------------------------------------------------+
|  4. INTELLIGENCE LAYERS (SMS360X)                            |
|     Compliance, Operational, Emerging, ADREP, HFACS,         |
|     Nano-Code                                                 |
+--------------------------------------------------------------+
|  3. SHARED SAFETY REGISTERS (AviaSAFE system of record)      |
|     Hazards, Risk, Barriers, Occurrences, Actions, Findings  |
+--------------------------------------------------------------+
|  2. OPERATIONAL WORKFLOW (AviaSAFE)                          |
|     Triage, SRM, CAN/CAP, verification, closure, diversions  |
+--------------------------------------------------------------+
|  1. GOVERNANCE & ACCESS (SMS360X model)                      |
|     Identity, membership, tenant ownership, RLS, audit       |
+--------------------------------------------------------------+
|  0. SOURCE DATA (both)                                       |
|     Reports, audits, surveys, training, MOC, investigations  |
+--------------------------------------------------------------+
```

Reading the stack:

- Layers 0–3 are mostly AviaSAFE (it already runs them). SMS360X contributes the governance rigor at layer 1 and richer barrier/risk modelling at layer 3.
- Layers 4–6 are mostly SMS360X (designed). AviaSAFE contributes the implemented measurement (SPI/SPT, N-HRC, PSOE) that feeds them.
- The OIP (layer 5) is the formal handover point from operator data to State intelligence.

---

# 7. Canonical domain model (the shared vocabulary)

This is the single most important decision in the merge. Each object below must have **one owner**. "Owner" here means the authoritative store, not who created it.

| Canonical object | Recommended authoritative source | Notes / conflict |
|---|---|---|
| Tenant / Operator | Existing in both | AviaSAFE uses deterministic tenant IDs; SMS360X uses owner organizations. Unify on one tenant key. |
| State / Regulator / Membership | SMS360X model | AviaSAFE has a single `role` string and a CAAN cross-tenant role; SMS360X has effective-dated memberships. Adopt SMS360X. |
| Occurrence / Report (VSR/MOR) | AviaSAFE | Already live with regulatory timers and ADREP fields. |
| Hazard | AviaSAFE | Already live with triage, enrichment, N-HRC category. |
| Risk | AviaSAFE (after fixing the dual-shape defect) | AviaSAFE has a known `risk_register` conflict between two shapes; SMS360X has a cleaner Risk-Barrier model. Resolve before merging. |
| Barrier | SMS360X model, AviaSAFE data | SMS360X's barrier assurance model is richer; AviaSAFE has the live barrier register and BSV. Merge the model, keep the data. |
| TopEvent / Consequence | SMS360X | Present in SMS360X; AviaSAFE has bow-tie controls/consequences. Reconcile to one structure. |
| Finding / Action (CAN/CAP) | AviaSAFE | CAN/CAP and verification are live and audit-relevant. SMS360X Action/Finding map onto them. |
| SPI / SPT / Safety Objective | Both | AviaSAFE computes live SPI/SPT; SMS360X defines objectives. Choose AviaSAFE as the calculation store, SMS360X for definitions. |
| SMS Maturity | AviaSAFE (implementation) + SMS360X (formula governance) | AviaSAFE has working survey scoring; SMS360X must supply the approved index formula. |
| Classification (ADREP / HFACS / Nano-Code / N-HRC) | Shared | ADREP/HFACS in both; Nano-Code only SMS360X; N-HRC only AviaSAFE. Keep one classification service. |
| OIP / State products | SMS360X | New capability; sits on top of AviaSAFE registers. |
| Knowledge Network | SMS360X | New capability; future phase. |
| Import history / lineage | SMS360X model | AviaSAFE has import staging for hazards; SMS360X has a versioned lineage model. Adopt SMS360X's lineage. |

Business rule: if an object appears in both projects under different names or shapes, it still becomes **one** object. Duplicate registers are the main danger of merging.

---

# 8. Ownership and access unification

This is the second most important decision. The two projects disagree in one specific place: how a regulator reaches operator data.

## 8.1 The disagreement, in plain terms

- **AviaSAFE today:** a CAAN user holds a "cross-tenant" role and reads aggregated operator data. The regulator can reach into operator data through the aggregation layer.
- **SMS360X rule:** the State workspace is **not** an operator database browser. Only intelligence products (OIP) leave the operator. Regulator access is non-owning, purpose-bound, and audited.

## 8.2 Recommended resolution

Adopt the SMS360X rule as the long-term target because it is the more defensible position for safety-report confidentiality and operator trust. Keep AviaSAFE's working aggregation only as an interim mechanism inside the operator's own intelligence generation, not as regulator browsing.

Practical shape:

1. Operator data stays in the operator tenant (owner: operator).
2. The operator's own intelligence is generated inside its tenant.
3. The OIP packages that intelligence and is published to the State workspace.
4. The State owns the state intelligence products (S1-S10, national profiles).
5. Any regulator record-level access is exceptional, purpose-bound, time-limited, and audited.

## 8.3 Identity and membership

Adopt one identity and one membership model:

- Identity: one login provider for the whole product. SMS360X assumes Supabase Auth; AviaSAFE currently uses Firebase Auth. This must be a single decision — running both permanently is a security and maintenance risk.
- Membership: a user can belong to an operator tenant, a regulator, or the State, with effective dates and a single active context per request. This is the SMS360X model and it replaces AviaSAFE's single `role` string.
- Authorization: one default-deny RLS design (SMS360X AD-01..AD-15), tenant-bounded, with regulator access only through validated oversight relationships.

---

# 9. Intelligence layer unification (avoid two brains)

Both projects generate "intelligence". If both keep generating it independently, the combined product will report different numbers for the same reality. Define **one owner per intelligence output**.

| Intelligence output | Keep from | Role of the other |
|---|---|---|
| SPI / SPT | AviaSAFE | SMS360X defines the SPT/objective governance |
| N-HRC (Nepal NASP) | AviaSAFE | Feed into SMS360X Layer 4 / State products |
| PSOE (oversight evaluation) | AviaSAFE | Feed into SMS360X M14 / RBO |
| SMS Maturity Index | AviaSAFE engine + SMS360X formula | One formula, one calculation |
| OIP-01..07 | SMS360X | Consumes AviaSAFE registers |
| M14 State products S1-S10 | SMS360X | Consumes OIP; may reuse AviaSAFE state risk/SPI |
| RBO prioritization | SMS360X | Consumes OIP + AviaSAFE maturity/SPI/N-HRC |
| Knowledge Network | SMS360X | Future; de-identified only |
| ADREP / HFACS / Nano-Code layers | SMS360X | AviaSAFE supplies ADREP/HFACS coding |

Rule: when AviaSAFE already computes a measure, SMS360X consumes it; SMS360X supplies the product packaging and the higher-order intelligence. This prevents duplicate "brains".

---

# 10. What "better" looks like (the combined product)

By audience:

- **Safety Manager (operator):** one workspace with reporting, hazard/risk/barrier workflow, SMS maturity, and CAP in one place — all already partly working in AviaSAFE.
- **Accountable Executive:** SPI/SPT performance, maturity trend, barrier health, CAP performance — with the AE's non-delegable acceptance properly enforced.
- **Regulator / CAAN:** state risk, N-HRC, PSOE, plus new RBO prioritisation and national profiles — without direct operator-database browsing.
- **State / SSP / NASP:** national maturity, hazard/risk profiles, SSP/NASP monitoring, annual State report dataset.
- **Cross-operator learning:** a governed Knowledge Network of de-identified lessons (future).

Compared with either project alone, the combined product covers the full chain: source data to registers to operator intelligence to State intelligence to oversight decisions.

---

# 11. Integration options (and the recommendation)

| Option | Description | Cost | Risk | Verdict |
|---|---|---|---|---|
| A. AviaSAFE as base, SMS360X as intelligence + governance layer | Keep AviaSAFE's live operational core; add SMS360X intelligence, ownership model, OIP, RBO, M14 | Medium | Medium | **Recommended** |
| B. SMS360X as target, reimplement AviaSAFE workflow | Rebuild AviaSAFE features on SMS360X architecture | High | High | Cleaner long-term, too slow now |
| C. Two products, shared contracts only | Keep both, exchange via OIP/API | Low short term | High long term | Creates the duplicate-brain and duplicate-register problems |

**Recommended: Option A.**

Reasoning:

- It preserves the only working, deployed asset (AviaSAFE) instead of discarding it.
- It adopts the stronger architecture (SMS360X governance and intelligence) where it matters most.
- It is incremental: each phase leaves a working product.
- It avoids building two versions of the same register.

The natural interface between them is the **OIP**: AviaSAFE produces operational data and measures; SMS360X consumes them and produces intelligence.

---

# 12. Phased path (business phases)

No dates are promised here; effort estimates are relative.

## Phase 0 — Decisions and governance (no development)

- Confirm the product identity and owner of the combined product.
- Adopt the canonical domain model (Section 7).
- Adopt one identity/membership model and one access rule (Section 8).
- Agree that AviaSAFE is the operational system of record and SMS360X is the intelligence/governance layer.
- Set the OIP as the operator-to-State boundary.
- Output: signed decision record (see Section 14).

## Phase 1 — Stabilise the base (AviaSAFE)

Close the audit blockers that would otherwise be inherited by the merged product:

- Confidential / voluntary reporting workflow.
- AE non-delegability and two-signature acceptance enforcement.
- SMS maturity persistence and RLS.
- Resolve the `risk_register` dual-shape defect.
- Enable the 6 RLS-disabled tables or formally exempt them.
- Enforce RBAC; fix the unauthenticated/under-authorized SPI/N-HRC/regulator surfaces.

## Phase 2 — Unify governance and data

- Introduce the membership model and one identity.
- Migrate tenant/ownership keys to one scheme.
- Establish the canonical registers and de-duplicate overlaps.
- Apply default-deny RLS on all tenant-owned tables.
- Keep the product working throughout.

## Phase 3 — Add the intelligence layer

- Implement OIP-01..07 over AviaSAFE registers.
- Implement M14 State products S1-S10.
- Implement RBO prioritisation using AviaSAFE maturity/SPI/N-HRC plus OIP.
- Wire N-HRC and PSOE into the State products.
- Define and publish the SMS Maturity Index formula.

## Phase 4 — Validation and pilot

- Run the SMS360X synthetic 5-operator, 36-month validation.
- Confirm RBO priorities match the expected operator stories.
- Run AviaSAFE's test suite and live UAT against the merged product.
- Produce an audit evidence pack for CAAN.

## Phase 5 — Commercial and scale

- Activate the SMS360X subscription tiers.
- Add the Knowledge Network (de-identified) as a later add-on.
- Establish monitoring, backup, and incident response.

---

# 13. Conflict register (things that must be settled)

| ID | Conflict | Why it matters | Recommended resolution |
|---|---|---|---|
| C-01 | Regulator access: AviaSAFE aggregation vs SMS360X OIP-only | Confidentiality and operator trust | Adopt SMS360X OIP-only long term; use aggregation only inside operator intelligence |
| C-02 | Identity: Firebase vs Supabase Auth | Two auth systems is a security and cost risk | Choose one; recommended Supabase Auth per SMS360X |
| C-03 | Membership: single `role` string vs effective-dated memberships | Correctness of access across tenants | Adopt SMS360X membership model |
| C-04 | `risk_register` dual shape | Wrong or failing risk data | Fix to one canonical shape before merge |
| C-05 | Duplicate maturity/intelligence logic | Different numbers for the same reality | One owner per output (Section 9) |
| C-06 | Tech stack: Python vs TypeScript | Cost, skills, maintenance | Keep AviaSAFE backend as system of record; SMS360X intelligence as a service |
| C-07 | Module flags: AviaSAFE `module1..4` vs SMS360X layers/M14 | Inconsistent feature gating; backend/frontend mismatch in AviaSAFE | Define one canonical module-flag scheme |
| C-08 | Commercial model absent in AviaSAFE | Cannot charge consistently | Adopt SMS360X tiers |
| C-09 | Data lineage: AviaSAFE staging vs SMS360X versioned model | Audit reproducibility | Adopt SMS360X lineage model |
| C-10 | Module naming: A/B/C vs intelligence layers and M14 | Confusing product story | Define one public product map; keep internal module names only if useful |

This register should be extended by the SME if additional conflicts are found; it is not exhaustive.

---

# 14. Decisions only you (the SME) can make

These are business and governance decisions, not technical ones. Development should not start until they are recorded.

1. **Product identity.** What is the single product called, and who owns it (you, or the organisation)?
2. **System of record.** Confirm AviaSAFE as the operational base and SMS360X as the intelligence layer (recommended), or choose another option.
3. **Ownership doctrine.** Confirm operator owns operational data and the State owns state intelligence. Confirm the OIP as the only path for data to leave an operator.
4. **Regulator access.** Confirm the no-direct-browse rule, with exceptional, audited access only.
5. **Identity.** Choose one login provider for the combined product.
6. **Commercial intent.** Confirm the subscription tiers and which capabilities are operator vs State.
7. **Compliance priority.** Confirm that closing the confidential-reporting and risk-acceptance blockers is required before any pilot.
8. **Data scope.** Confirm which operator datasets may be used for the combined validation.
9. **Legal / confidentiality basis.** Confirm the legal basis under which CAAN may see any operator-level information.
10. **Governance of the merge.** Who approves the canonical domain model and the phased plan?

---

# 15. Risks of merging (and mitigations)

| Risk | Description | Mitigation |
|---|---|---|
| Duplicate logic | Two maturity engines, two risk registers | One owner per object/output (Sections 7 and 9) |
| Regression | Merging breaks the working AviaSAFE product | Incremental phases; keep the product working after each phase; regression tests |
| Security regression | Two auth models or RLS gaps | One identity/authorization model; default-deny; adversarial isolation tests |
| Scope explosion | Trying to build everything at once | Follow the phases; Phase 0 is decisions only |
| Ownership/legal | Operator data exposed incorrectly | OIP-only boundary; audited access; legal basis confirmed |
| Inherited debt | Merging before fixing AviaSAFE blockers | Finish Phase 1 first |
| Vendor/stack lock-in | Two languages and two clouds | Decide one runtime direction in Phase 0 |

---

# 16. Success criteria for the combined product

The merge is successful when:

1. There is exactly one register for each safety object.
2. There is exactly one number for each intelligence measure.
3. Operator data ownership and tenant isolation are demonstrated, including negative tests.
4. The State workspace produces S1-S10 without direct operator-database access.
5. RBO priorities align with known operator safety stories.
6. The AuditEvidence for confidential reporting and non-delegable acceptance is complete.
7. The working AviaSAFE product never stops working during the merge.
8. A single product story and commercial model exist for customers.

---

# 17. Plain-language glossary

- **SMS** — Safety Management System: how an aviation organisation manages safety.
- **ICAO Annex 19 / Doc 9859 / Doc 10159** — International Civil Aviation Organization safety standards and guidance.
- **ADREP** — ICAO's standard way of classifying occurrences.
- **HFACS** — a method for classifying human and organisational factors in accidents.
- **Nano-Code** — a very granular tagging system for safety conditions (SMS360X).
- **N-HRC** — National High-Risk Categories from Nepal's NASP (AviaSAFE).
- **SPI / SPT** — Safety Performance Indicator (a measure) / Safety Performance Target (a goal).
- **Occurrence / VSR / MOR** — an event / voluntary safety report / mandatory occurrence report.
- **CAN / CAP** — Corrective Action Notice / Corrective Action Plan.
- **Bow-Tie** — a diagram linking threats, a central event, consequences, and barriers.
- **Barrier** — a control that prevents or limits harm.
- **SRM** — Safety Risk Management.
- **PSOE** — a CAAN oversight evaluation method (AviaSAFE).
- **OIP** — Operator Intelligence Pack: the packaged intelligence an operator sends to the State (SMS360X).
- **M14** — SMS360X's State Safety Intelligence Workspace.
- **RBO** — Risk-Based Oversight: prioritising which operators need more attention.
- **SSP / NASP** — State Safety Programme / National Aviation Safety Plan.
- **System of record** — the one system that is authoritative for a given object.
- **RLS (Row-Level Security)** — a database rule that ensures each organisation sees only its own rows.
- **Tenant** — the isolated workspace/data boundary of one operator organisation.

---

# 18. Recommendation summary

1. Combine the two, using **AviaSAFE as the operational base and SMS360X as the intelligence and governance layer** (Option A).
2. Settle the ten SME decisions in Section 14 before any development.
3. Use the OIP as the operator-to-State boundary.
4. Fix AviaSAFE's audit blockers before adding SMS360X's intelligence layer.
5. Define one canonical domain model and one authorization model; never allow duplicate registers or duplicate intelligence.
6. Merge in phases, always keeping a working product.

If those six points are followed, the combined product is genuinely better than either part: it can both run an SMS operationally and produce defensible, traceable State safety intelligence.

---

*End of Convergence Blueprint. This is a decision document, not an implementation plan. No code was written or changed, and no repository files were altered except the relocation of the companion Source Data Catalog report.*
