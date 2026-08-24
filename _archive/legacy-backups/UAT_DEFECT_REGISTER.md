# UAT Defect Register — RC-4 (Independent Verification & Validation)

Phase: RC-4 (User Acceptance Testing)
Status codes: `Open` · `Fix Applied` · `Fixed / Verified` · `Verified (No Fix)` · `Deferred` · `Documented Limitation`

Evidence sources: static code analysis (repo `main` working tree), local regression suite
(`backend/tests/`, 40 tests), and non-destructive probes against the live deployment
(`https://aviasafe-unified-platform.onrender.com`).

---

## UAT-001 — CAAN_SMD / SUPER_ADMIN cannot confirm risk assessments across tenants (documented feature broken)

- **Severity:** Critical
- **Status:** Fixed / Verified
- **Classification:** Verified Defect
- **Description:** The documented CAAN capability is "cross-tenant read + risk confirm" (docs/ADMIN_GUIDE.md:14, docs/API.md:31, docs/OPERATIONS.md:10). `PUT /api/v1/reports/{id}/risk-assessment` calls `ReportService.confirm_risk_assessment`, which resolves the report with `get_tenant_collection(self.tenant_id, ...)` where `self.tenant_id = user["tenant_id"]`. CAAN_SMD / SUPER_ADMIN users have **no tenant claim** (backend/seed/config.py:633, 642, 651), so `tenant_id` is `None`, and `firebase.get_tenant_collection(None, ...)` → `db.collection("tenants").document(None)` → Firestore generates a **new random document id on every call** → the report is never found → CAAN confirm fails.
- **Steps to reproduce:** Login as CAAN SMD (`sms.inspector@caan.gov.np`, role CAAN_SMD, no tenant). Submit a report as an airline admin. `PUT /api/v1/reports/{report_id}/risk-assessment` with CAAN token → "Report not found" (400).
- **Expected behaviour:** CAAN_SMD (State regulator) can confirm/override a risk assessment on any airline's report (cross-tenant).
- **Actual behaviour:** Report lookup targets a phantom random tenant path; confirm fails with 400 ("Report not found"). The report is never updated.
- **Root cause:** `ReportService.confirm_risk_assessment` (backend/app/services/report_service.py:239-289) and `routes/reports.py:173` assume a tenant-scoped user. The cross-tenant read branches used by `get_reports`/`get_report_by_id` (report_service.py:114, 134) were never applied to the write/confirm path. `firebase.get_tenant_collection` (backend/app/firebase.py:58-60) has no guard for `tenant_id=None`.
- **Affected files:** backend/app/services/report_service.py:239-289; backend/app/routes/reports.py:162-175; backend/app/firebase.py:58-60.
- **Masked by tests:** backend/tests/test_risk_assessment_lifecycle.py:184-185 assigns `CAAN_SMD_TOKEN` a `tenant_id: "test_airline"`, so `test_caan_smd_can_confirm_risk_assessment` (line 478) exercises only the tenant-scoped path. In production the claim is absent.
- **Fix:** Resolve the report via `collection_group` (`__name__` equality) when the caller is a cross-tenant role, and update through the resolved document reference; use the report's own tenant for thresholds.

## UAT-002 — CAAN cross-tenant CAN/CAP read path is partial; CAP lists / latest-CAP / stats return empty or wrong data

- **Severity:** High
- **Status:** Fixed / Verified
- **Classification:** Verified Defect
- **Description:** Documented CAAN UAT step: "Verify CAN/CAP data accessible across tenants" (UAT scenario set, formerly docs/UAT_READINESS.md). `list_cans`/`get_can`/stats have cross-tenant branches, but:
  - `latest_cap` attachment re-scopes to the **caller's** tenant: `CanCapService.get_can` (can_cap_service.py:115) calls `self._caps_collection(doc.id)` which rebuilds the path from `self.tenant_id` (`None` for CAAN) instead of the CAN document's own reference → latest_cap silently missing.
  - `list_caps` (can_cap_service.py:299) has **no** cross-tenant branch → `[]` for CAAN.
  - `get_cap`/`get_cap_stats` iterate cross-tenant CANs but read CAP subcollections via `self._caps_collection(...)` (can_cap_service.py:332, 448) → wrong path → empty.
- **Expected behaviour:** CAAN_SMD can list CANs/CAPs and stats across all tenants with latest-CAP populated.
- **Actual behaviour:** CAAN sees CANs but no CAPs, no latest-CAP, and CAP stats of 0.
- **Root cause:** Sub-collection access is tenant-scoped instead of being resolved from the parent document reference (`doc.reference.collection("caps")`). Additionally, `GET /cans/{can_id}/caps` declared `response_model=List[CAPResponse]` while returning subset dicts from `_to_cap_list_item` (missing required `action_plan`, `timeline`, `submitted_by_uid`) → the endpoint always failed response validation (500). This was surfaced by the regression test and fixed to `List[dict]`.
- **Affected files:** backend/app/services/can_cap_service.py:100-128, 297-322, 324-342, 437-462; backend/app/routes/can_cap.py:122-131.
- **Fix:** Use `doc.reference.collection(CAP_SUBCOLLECTION)` in read paths; add a cross-tenant branch to `list_caps`; correct the `list_caps` response model.

## UAT-003 — Any authenticated `USER` can read/generate another tenant's reports via `?tenant_id=` (authorization bypass)

- **Severity:** High
- **Status:** Fixed / Verified
- **Classification:** Verified Defect
- **Description:** In `routes/reporting.py`, `effective_tenant = tenant_id or user.get("tenant_id")`. Only `AIRLINE_ADMIN` is forced back to their own tenant; the guard is `get_current_user` (any authenticated user). A plain `USER` can call `POST /api/v1/reporting/quarterly?tenant_id=other-airline` (or `annual`, and the list endpoints) and the `ReportGenerator` aggregates that tenant's hazards/CANs (report_generator.py:19-58) → cross-tenant data exposure; the generated report is also written into the other tenant's `reporting` sub-collection (pollution). A `USER` without a tenant can write into the shared `caan_reports` collection.
- **Expected behaviour:** Only CAAN_SMD/SUPER_ADMIN may select a tenant; all other roles are bound to their own tenant (or rejected).
- **Actual behaviour:** USER can override the tenant and access arbitrary operators' safety data.
- **Root cause:** Missing role check on the `tenant_id` query parameter (reporting.py:37,40,83,86,193,196,239,242).
- **Affected files:** backend/app/routes/reporting.py.
- **Fix:** Restrict `tenant_id` override to `CROSS_TENANT_ROLES`; reject generation when no tenant is resolvable for non-cross-tenant roles.

## UAT-004 — Anonymous survey submission is blocked by a client/rules schema mismatch

- **Severity:** High
- **Status:** Fixed / Verified (code + rules aligned)
- **Classification:** Verified Defect
- **Description:** The survey client writes to `tenants/{tenantId}/responses` with a payload that sets `airline_id` but **never `tenantId`** (public/portal/survey/app.js:256-280). The active Firestore rules require `request.resource.data.tenantId == tenantId` for create (firestore/firestore.rules:61-66) → the rule evaluates false → anonymous survey submission is denied. The anonymous survey is a core ICAO SMS function.
- **Expected behaviour:** Anonymous employees can submit a survey response to their airline's tenant.
- **Actual behaviour:** `addDoc(collection(db, "tenants", activeTenantId, "responses"), payload)` is rejected by the rules (PERMISSION_DENIED).
- **Root cause:** Field-name mismatch between client payload (`airline_id`) and rules (`tenantId`).
- **Affected files:** public/portal/survey/app.js:256-280; firestore/firestore.rules:61-66.
- **Note:** Whether the deployed project uses these exact rules could not be verified without project credentials; the mismatch is definite in the repository.
- **Fix:** Send `tenantId` in the client payload and accept `airline_id` in the rule (defensive both ways).

## UAT-005 — Live deployment runs an un-hardened build: admin provisioning endpoints lack bearer authentication

- **Severity:** Critical (production deployment)
- **Status:** **CLOSED / PASSED** (2026-08-05). Step 3 live validation (Part 1–4, `tests/e2e/live_validation.py`) verified against the production backend: CORS/origin security 10/10, auth & auth-gating 13/13 (admin POSTs 403 without token, legacy `/check-data`, `/migrate-seed-data`, `/auth/debug-verify` all 404), risk-matrix engine 10/10 (canonical 5/9/15 mapping), data audit & persistence 9/9 with writes confirmed directly in named database **`sms-db`** (us-west1); automated regression 67/67. History: RC-5.5 (02 Aug 2026) independently verified the live build STILL ran the pre-hardening code (the RC-1→RC-5 hardening was never committed, so any Render deploy from committed history reproduced the vulnerable build). The repository-side hardening, custom-domain frontend deployment, backend re-deploy (admin `security: HTTPBearer`, legacy paths 404), migration to `aerosafety-sms-prod`, and `sms-db` database wiring are now **COMPLETE and live-verified**. UAT-005 is formally closed.
- **Classification:** Verified Defect (build/deployment drift) + Documentation Gap (repo is fine, HEAD was not)

### RC-5.5 re-verification evidence (02 Aug 2026)
- Live OpenAPI: admin POST `setup-claims`/`provision-airlines`/`fix-tenant-ids`/`seed-demo-data`/`create-seed-users` → `"security": null` (RC-5 candidate: `[{"HTTPBearer":[]}]`).
- Legacy endpoints live on prod: `/api/v1/admin/check-data`, `/api/v1/admin/migrate-seed-data`, `/api/v1/auth/debug-verify` (absent in RC-5 candidate).
- No-token `POST /api/v1/admin/setup-claims` (empty body) → **422 body-validation** (auth NOT enforced; hardened build returns 403 before body validation).
- `POST /api/v1/admin/seed-demo-data`/`create-seed-users` → **422, not 404** — `DISABLE_DESTRUCTIVE_ENDPOINTS` gate absent; destructive endpoints are alive and functional with the public hardcoded `SETUP_SECRET`.
- `git show HEAD:backend/app/routes/admin.py` → `SETUP_SECRET = "aviasafe-e2e-setup-2026"` hardcoded; `if req.setup_key != SETUP_SECRET:` (no bearer auth); `/check-data` + `/migrate-seed-data` defined. `git show HEAD:backend/app/routes/auth.py` → `/debug-verify` defined.
- Frontend Hosting: `https://gap-analysis-ssp.web.app` returns "Site Not Found" (no hosting release; `hosting:channel:list` reports no channels for site). Custom domains `sms.`/`app.aviasafesystems.com` have no DNS. Live backend CORS allows only `https://gap-analysis-ssp.web.app` (unreachable).
- **Conclusion:** UAT-005 NOT closed. Correction requires (1) committing the RC-1→RC-5 working-tree changes, (2) re-deploying the backend from the committed candidate, (3) redeploying the frontend to Firebase Hosting. (RC-5.5 live-deployment evidence; UAT-005 since CLOSED/PASSED.)
- **Description:** Non-destructive probe: `POST /api/v1/admin/seed-demo-data` and `/provision-airlines` with **no Authorization header** and a wrong setup key return `403 Invalid setup key` — i.e., the endpoint body executes without any Firebase token. Live OpenAPI shows `"security": null` for these operations, while the same repo code generates `"security": [{"HTTPBearer": []}]`. The repo's **uncommitted working tree** adds `Depends(get_admin_user)` to all provisioning endpoints (backend/app/routes/admin.py:115,178,271,302,320); the deployed image predates that hardening (git HEAD admin.py has only `req.setup_key != SETUP_SECRET`).
- **Expected behaviour:** Admin endpoints require a SUPER_ADMIN Firebase ID token (as in the repo working tree).
- **Actual behaviour:** Production admin endpoints are protected only by the shared `SETUP_SECRET`.
- **Root cause:** Deployment/build drift — the live image is built from pre-hardening history.
- **Affected files (repo, already fixed):** backend/app/routes/admin.py.
- **Fix:** Redeploy the repository build. Not a code defect in the current working tree; cannot be corrected by a code change here. Also: `HEAD` uses a plain `!=` compare of the setup key (timing side-channel) — already fixed in the working tree via `secrets.compare_digest`.

## UAT-006 — PDF export returns a non-PDF placeholder (reportlab missing from dependencies)

- **Severity:** Medium (blocks the Reporting → Export UAT scenario; documented as known limitation)
- **Status:** Fixed / Verified
- **Classification:** Documented Limitation (UAT scenario set, formerly docs/UAT_READINESS.md; docs/KNOWN_LIMITATIONS.md) + environment defect
- **Description:** `pdf_generator.py` falls back to `_placeholder_pdf` (plain UTF-8 text) when `reportlab` is unavailable (pdf_generator.py:24-26, 227-245). `reportlab` is **not** in backend/requirements.txt and is not installed → every export endpoint (reporting.py:150-184, 306-340) returns text bytes labelled `application/pdf`; PDF readers cannot open the file.
- **Expected behaviour:** Exported quarterly/annual reports are valid PDFs.
- **Actual behaviour:** Downloading a report yields a file that fails to open as PDF.
- **Root cause:** Missing dependency declaration.
- **Affected files:** backend/requirements.txt; backend/app/services/pdf_generator.py (code already supports reportlab when present).
- **Fix:** Add `reportlab` to requirements.txt.

## UAT-007 — Cross-tenant roles can reach CAN/CAP, verification/closure and diversion-link write endpoints and silently corrupt data into phantom tenant documents

- **Severity:** High
- **Status:** Fixed / Verified
- **Classification:** Verified Defect
- **Description:** `get_safety_manager`, `get_responsible_manager` and `get_accountable_executive` allow `CROSS_TENANT_ROLES` (auth.py:125, 141, 157). CAN/CAP writes (`user["tenant_id"]` → None: can_cap.py:23,85,98,113,152,167,181), verification/closure writes (verification.py:14-16, 28-33, 76-82, 105-110), and diversion link/unlink (flight_diversions.py:105,118) then construct services with `tenant_id=None`, so Firestore `.document(None)` generates a new random id per call → writes land in phantom tenant documents that no one can ever read. This is silent data loss rather than an error. It is inconsistent with the Firestore rules, which permit CAAN read-only on these paths (firestore.rules:113-121, 127-133).
- **Expected behaviour:** Users without a tenant cannot write to these workflows (403), matching the documented role matrix ("CAAN_SMD: read + risk confirm" only).
- **Actual behaviour:** CAAN can invoke these endpoints and data is written to unreachable random tenant documents.
- **Root cause:** Guards allow cross-tenant roles on write endpoints that lack cross-tenant write support.
- **Affected files:** backend/app/routes/can_cap.py, backend/app/routes/verification.py, backend/app/routes/flight_diversions.py.
- **Fix:** Reject requests without a tenant on these write endpoints (403), preserving the existing role checks.

## UAT-008 — Test suite masks cross-tenant defects

- **Severity:** Medium
- **Status:** Fixed / Verified
- **Classification:** Verified Defect (test integrity)
- **Description:** (a) The CAAN/SUPER_ADMIN token mocks carry a `tenant_id` (test_risk_assessment_lifecycle.py:183-185) unlike production claims; (b) `_CollectionGroupMock.get()` always returns `[]` (line 149-150), so cross-tenant behaviour is never exercised. Together they let `test_caan_smd_can_confirm_risk_assessment` pass while the production path (UAT-001) is broken.
- **Affected files:** backend/tests/test_risk_assessment_lifecycle.py.
- **Fix:** Model production claims (`tenant_id=None` for CAAN/SUPER_ADMIN); make the collection-group mock traverse tenant sub-collections; add cross-tenant regression tests.

## UAT-009 — Public Swagger UI and OpenAPI schema exposed on the live deployment

- **Severity:** Low
- **Status:** Verified (No Fix) — recommendation only
- **Classification:** Documentation / hardening gap
- **Description:** `GET /docs` and `GET /openapi.json` return 200 unauthenticated on live, exposing the full API surface (including admin endpoints and query semantics) to unauthenticated clients.
- **Expected behaviour:** Disabled (or restricted) in a production environment.
- **Root cause:** FastAPI `docs_url`/`openapi_url` left at defaults in production config.
- **Fix (recommendation):** Set `docs_url=None, openapi_url=None` when `DEBUG=False`, or protect them.

## UAT-010 — `getCurrentUser()` resolves `null` after a silent 5-second timeout

- **Severity:** Low
- **Status:** Verified (No Fix) — recommendation only
- **Classification:** Verified Defect (UX robustness)
- **Description:** `public/js/firebase.js:271-277` — if `onAuthStateChanged` has not emitted a signed-in user within 5 s, the promise resolves `null`; a signed-out visitor is therefore treated as "no user" after a 5 s wait (the callback returns early for signed-out users, line 254). No error is surfaced.
- **Recommendation:** Resolve the current signed-in state promptly for signed-out users and log/handle the timeout distinctly.

## UAT-011 — `/login.html?tenant=` parameter is unused outside the `aviasafesystems` host

- **Severity:** Low
- **Status:** Verified (No Fix) — recommendation only
- **Classification:** Documentation / UI gap
- **Description:** `public/login.html:265-277` only reads the `tenant` query parameter when the host matches the deployment domain, so tenant pre-selection is silently ignored on other hosts.
- **Recommendation:** Fall back to a tenant selector or explicit error when the parameter is provided but the host is not trusted.

## UAT-012 — Closure uses the last verification in list order without sorting

- **Severity:** Medium
- **Status:** Deferred
- **Classification:** Verified Defect (data-integrity risk)
- **Description:** `VerificationService.create_closure` (verification_service.py:163-169) uses `verifications[-1]` to enforce the "latest outcome must be Accepted" rule, but Firestore `get()` does not guarantee insertion order → an older verification may be treated as latest.
- **Expected behaviour:** The closure gate should use the most recent verification by `created_at`.
- **Affected files:** backend/app/services/verification_service.py:163-169.
- **Fix (recommendation):** Order by `created_at` DESC and take the first document. Deferred (not blocking UAT; low reproduction likelihood with current data volumes).

---

## Not-yet-verified candidates (from code review; not registered as defects)

- Dashboard CAAN/admin scoping details; report/timestamp edge cases; survey duplicate-submission prevention; MOR hazard auto-creation. These require additional evidence and are recorded here for completeness.

---

## Defect Register Summary (final)

| ID | Severity | Status | Classification | Fixed in |
|----|----------|--------|----------------|----------|
| UAT-001 | Critical | Fixed / Verified | Verified Defect | backend/app/services/report_service.py |
| UAT-002 | High | Fixed / Verified | Verified Defect | backend/app/services/can_cap_service.py, backend/app/routes/can_cap.py |
| UAT-003 | High | Fixed / Verified | Verified Defect | backend/app/routes/reporting.py |
| UAT-004 | High | Fixed / Verified | Verified Defect | public/portal/survey/app.js, firestore/firestore.rules |
| UAT-005 | Critical (deployment) | **CLOSED / PASSED** (2026-08-05) | Build/deployment drift — RC-1→RC-5 fixes never committed; live = HEAD `4e306ce` (now re-deployed from committed candidate) | Repository fix + backend re-deploy + frontend deploy + `sms-db` wiring COMPLETE; Step 3 live validation 42/42 + regression 67/67 |
| UAT-006 | Medium | Fixed / Verified | Documented limitation + env defect | backend/requirements.txt |
| UAT-007 | High | Fixed / Verified | Verified Defect | routes/can_cap.py, routes/verification.py, routes/flight_diversions.py |
| UAT-008 | Medium | Fixed / Verified | Verified Defect (test integrity) | backend/tests/test_risk_assessment_lifecycle.py |
| UAT-009 | Low | Verified (No Fix) | Hardening gap | docs/Operational (recommendation) |
| UAT-010 | Low | Verified (No Fix) | UX robustness | public/js/firebase.js (recommendation) |
| UAT-011 | Low | Verified (No Fix) | UI/doc gap | public/login.html (recommendation) |
| UAT-012 | Medium | Deferred | Data-integrity risk | verification_service.py (recommendation) |

**Fixed & verified: 8** · **Verified, no code fix (deployment/recommendation): 3** · **Deferred: 1**

Regression: 40/40 baseline tests pass before fixes; **46/46** pass after fixes (40 original + 6 new cross-tenant/authorization regression tests).
