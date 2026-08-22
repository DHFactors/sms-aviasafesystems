# Security Audit Report — Multi-Tenant Isolation & AI Guardrails

**Standard:** Headway multi-tenant criteria (4 phases) · **Date:** 2026-08-22
**Verdict per phase:** Phase 1 COMPLIANT · Phase 2 COMPLIANT · Phase 3 COMPLIANT (app) / MITIGATED (network egress) · Phase 4 COMPLIANT

---

## Phase 1 — Firestore Rule Data Isolation

**Status: COMPLIANT**

### Rule definitions (`firestore/firestore.rules`)

* Helpers (lines ~9-45): `isAuthenticated`, `isSuperAdmin`, `isCaanSMD`,
  `isAirlineAdmin`, `isCaanInspector()` (CAAN_SMD + forward-compatible
  `CAAN_INSPECTOR` token), `matchesOwnTenantData()`.
* Path-partitioned collections — every allow references the path tenant:
  `/tenants/{tenantId}/metadata|responses|surveys|reports|mor|hazards|can_cap|verification|flight_diversions`.
* **PSOE assessments** (top-level, tenant_id on each doc):

  ```
  match /psoe_assessments/{docId} {
    allow read: if isAuthenticated() &&
      ((isAirlineAdmin() && request.auth.token.tenant_id == resource.data.tenant_id)
       || isCaanInspector());
    allow create, update: if isAuthenticated() && matchesOwnTenantData();
    allow delete: if isSuperAdmin();
  }
  ```

* **Demo sessions** (owner-scoped per spec):

  ```
  match /demo_sessions/{sessionId} {
    function sessionOwner() { return isAuthenticated() &&
      request.auth.uid == resource.data.session_owner_id; }
    allow read:   if sessionOwner();
    allow create: if sessionOwnerNew();
    allow update: if sessionOwner();
    allow delete: if sessionOwner() || isSuperAdmin();
    match /{sub=**} { allow read, write: if false; }   // Admin SDK only
  }
  ```

* `demo_analytics/**`: deny-all to clients (Admin SDK writes only).

### Just Culture identity masking

Firestore rules cannot mask individual fields; masking is enforced in the API
layer before CAAN inspector reads leave the backend:

* `app/services/dashboard_service.py` state aggregations strip/genericise
  anonymous VSR originator fields (`originator_name`,
  `respondent_id`, contact details) and expose only counts/trends.
* Documented inline above both the `responses` collection-group block and the
  reports block ("JUST CULTURE IDENTITY MASKING … applied server-side").

### Client-side query filters eliminated

Every list/read is scoped by PATH (`/tenants/{tenantId}/…`). No rule grants
access because a *query filter* claimed a tenant — path isolation +
`resource.data.tenant_id` comparisons are the only widening mechanisms.

### Tests

| Suite | Result |
|---|---|
| `tests/test_firestore_rules.js` (structural rule-lint) | **33 assertions PASS** |
| `tests/test_archetype_api.py` (route-level scoping) | 7 PASS |
| Full backend suite | 544+ passing |

Covers: cross-tenant read rejection (path tenant ≠ claim → no allow),
unauthenticated rejection (`request.auth != null` gate on every block), demo
session ownership.

---

## Phase 2 — AI Copilot Read-Only Scope

**Status: COMPLIANT**

* Service: `app/services/groq_copilot.py` — imports NO Firestore client, NO
  CAN/CAP/hazard/survey services; its only database touch is a read-only
  `.get()` for tenant classification.
* Route: `app/routes/copilot.py` imports only auth, rate-limit, App Check,
  and the LLM service. No mutation of audit logs, CAN/CAP records, or risk
  matrices.
* Outputs are pure text/JSON chat completions; any state change requires the
  user to separately call authenticated workflow endpoints.

**Tests:** `tests/test_copilot_guardrails.py::test_copilot_service_has_no_database_writes`
and `..._no_mutation_route_imports`.

## Phase 3 — Prompt-Injection Quarantine & Egress

**Status: COMPLIANT (application controls)** · Network egress: MITIGATED (see §4)

* Quarantine wrapper: live user turn is wrapped in
  `<user_report>…</user_report>`; embedded delimiter tokens are neutralised
  to `[tag]` so the wrapper cannot be escaped
  (`groq_copilot.py::quarantine_untrusted`).
* System directive: `INJECTION_DIRECTIVE` prepended to every system prompt —
  instructs the model to treat wrapped content strictly as data and to refuse
  tool calls, URL fetches, credential/system-prompt disclosure, and rule
  changes; flag attempts as injection findings.
* Output contract: text/JSON only; no tool-calling capability exists in the
  integration, so a successful jailbreak cannot itself mutate state.

**Tests:** `test_copilot_guardrails.py::test_user_message_is_quarantined`,
`..._system_prompt_carries_anti_injection_directive`,
`..._injection_payload_stays_inside_quarantine` (hostile payload with an
embedded close-tag confirmed contained).

## Phase 4 — Storage Tenant Isolation

**Status: COMPLIANT**

`storage/storage.rules` (wired via `firebase.json → "storage"`):

```
match /b/{bucket}/o {
  match /tenants/{tenantId}/{allPaths=**} {
    allow read:  if request.auth != null &&
                 (ownTenant(tenantId) || isCaanInspector());
    allow write: if request.auth != null && ownTenant(tenantId) &&
                 request.resource.size < 10 * 1024 * 1024;
    allow delete: if isAuthenticated() &&
                 (ownTenant(tenantId) || isSuperAdmin());
  }
  match /{allPaths=**} { allow read, write: if false; }
}
```

Downloads require Firebase SDK download URLs carrying per-object version
tokens (`alt=media&token=…`) or backend-signed access — object paths alone are
not grantable cross-tenant.

---

## Consolidated Verification Log

| Command | Result |
|---|---|
| `pytest backend/tests/` | **537 → 544 passed** (incl. guardrails/archetype suites) |
| `node tests/test_firestore_rules.js` | 33 assertions PASS |
| `node frontend-tests/check-inline-scripts.js public` | 53/53 |
| `firebase deploy --only hosting,firestore` | released (Chunk 16); storage rules released with Chunk 17 deploy |

## Follow-ups

1. Firestore emulator semantic tests (owner/inspector matrix) — structural
   lint currently gates CI; emulator run documented as next step.
2. Render outbound-IP allowlist / GCP VPC-SC enforcement for the domains in
   `docs/SECURITY_AI_GUARDRAILS.md` §4 (converts MITIGATED → ENFORCED).
3. Rotate any long-lived prospect demo passwords between engagements.
