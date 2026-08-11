# Architectural Gaps Register

Tracking the architectural gaps identified during the Part 2 (state-level SSP oversight) review.
Each item carries a `GAP-<n>` identifier. Statuses reflect current implementation as of commit
`1c11f3f` (atomic batch sync + `aggregated_at` staleness).

Legend: ✅ **Resolved** · 🔶 **Partially resolved** · ⏳ **Open**

## Gap #1 — Aggregation Pipeline Scale & Freshness

**Status:** 🔶 Partially resolved (atomicity done; scale pending)

**What was completed (commit `1c11f3f`):**
- `sync_register_from_aggregation` now stages all register writes in a **single Firestore batch**
  and commits once, so the register is never observed partially updated during a sync.
- Every synced entry records `aggregated_at` (UTC ISO); the sync result exposes the same
  timestamp so consumers can detect how stale the register is relative to live tenant data.

**Remaining gap:**
- `aggregate_state_risk` performs a **full on-demand scan** of `collection_group("hazards")`
  and `collection_group("reports")` on every call (`StateRiskService._cross_tenant_hazards` /
  `_cross_tenant_reports`, `backend/app/services/state_risk_service.py`).
- In a high-volume multi-tenant environment this becomes expensive (all docs read per request) and
  the register only reflects data as of the last manual/on-demand sync.

**Recommended path (future):**
- Scheduled/incremental aggregation (e.g. Firebase Scheduler or a periodic worker) that:
  1. Keeps per-tenant or per-category running counters instead of rescanning every record.
  2. Writes only the incremental delta to the register (still via one atomic batch per run).
  3. Propagates an `aggregated_at` "last run" marker so consumers can signal freshness in the UI.

## Gap #2 — Jurisdiction Taxonomy Extensibility

**Status:** ⏳ Open

**Current implementation:**
- ICAO category set is a **hardcoded Python constant** `ICAO_TOP_RISK_CATEGORIES`
  (`backend/app/services/state_risk_service.py`).
- Classification is a **hardcoded exact-code + substring matcher** in `StateRiskService._classify`
  (`backend/app/services/state_risk_service.py`). The seed reference layer
  (`state/icao_top_risks/categories/{category}`) is data-driven for display (name, icao_reference,
  ssp_target), but the classifier and category enumeration are not.

**Impact:**
- Non-ICAO jurisdictions (FAA, EASA) that mandate localized taxonomy (e.g. UAS/drone integration,
  ground-handling variances) cannot be represented: an unrecognized code falls through to `OTHER`
  and a new category requires editing and redeploying backend Python.

**Recommended path (future):**
- Refactor `_classify` into a **data-driven mapping** (e.g. a `state/classifier_rules` collection
  with per-category keyword/code pattern lists) so jurisdictions can extend taxonomy without a
  code change.
- Source the category set from the reference docs (seeded ICAO defaults) rather than the Python
  constant.

## Gap #3 — Tenant-Side Baseline Synchronization (Event Broker)

**Status:** ⏳ Open

**Current implementation:**
- State-level SSP targets flow **downward only at report-generation time**: `report_generator.py`
  reads the persisted register (`risk_reduction_rate`, `ssp_target_avg`) when a tenant report is
  generated.
- There is **no event broker** (no Firebase Cloud Functions, no Pub/Sub, no Firestore triggers;
  confirmed absent — no `functions/` package, no cloudbuild, no trigger wiring).
- When `PUT /register/{id}/ssp-target` updates a state tolerance, tenant safety managers are
  **not notified**; they only observe the change on their next report generation (polling-by-user).

**Impact:**
- Regulatory target changes are not communicated in real time to operators, weakening the
  "state → operator" direction of the SSP feedback loop that Annex 19 expects.

**Recommended path (future):**
- A Firebase Cloud Function triggered by `onWrite`/`onUpdate` on `state/ssp/risk_register/{id}` that:
  1. Reads `contributing_tenants` from the changed entry.
  2. Writes a `notifications` subcollection per affected tenant.
  3. Optionally invalidates/rebuilds cached tenant benchmark data.
- This is net-new infrastructure (functions runtime, deploy target, CORS/REST wiring) and is out of
  the current repo structure until a `functions/` package is introduced.

---

## Priority summary

| Gap | Current state | Priority |
|---|---|---|
| #1 Aggregation scale | 🔶 Atomicity done; full-scan + staleness UI signal pending | High (scale-dependent) |
| #2 Jurisdiction taxonomy | ⏳ Open — degrades gracefully to `OTHER` today | Medium (only blocks second jurisdiction) |
| #3 Tenant notification | ⏳ Open — net-new infrastructure | Medium (SSP feedback loop) |
