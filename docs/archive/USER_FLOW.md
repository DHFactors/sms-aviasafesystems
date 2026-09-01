# User Flow & Navigation Map

This document traces the end-to-end user journeys through the AviaSAFE SMS Platform (as of v1.0.0),
mapping each on-screen action to the page, JavaScript module, API route, role guard, and Firestore
data it touches. It is the companion to [ARCHITECTURE.md](./ARCHITECTURE.md) and
[API.md](./API.md): where those documents describe *what* exists, this one describes *how a user
actually gets from A to B*.

**Verified against source:** `backend/app/main.py`, `backend/app/routes/*`, `backend/app/middleware/auth.py`,
`public/js/*`, and every page under `public/`.

---

## 1. System at a Glance

```
User ──► Browser ── sms.aviasafesystems.com (Firebase Hosting, static HTML/JS)
              │  Firebase Web SDK v9.22.0 (compat)
              │  auth ▸ getIdToken()  →  Bearer RS256 ID-token
              ▼
        FastAPI ── https://aviasafe-unified-platform.onrender.com
              │  middleware: CORS ▸ SecurityHeaders ▸ RateLimit ▸ RequestLogging
              │  guards: get_current_user / get_tenant_user / get_caan_user /
              │          get_admin_user / get_safety_manager / get_responsible_manager /
              │          get_accountable_executive
              ▼
        Firestore (named DB "sms-db", project aerosafety-sms-prod, us-west1)
              ├─ tenants/{tenant_id}/...        (all tenant data)
              ├─ reports/{report_id}            (legacy flat reports)
              ├─ surveys | surveyResponses      (survey responses — see §15)
              └─ state/icao_top_risks/...       (SSP reference data)
        ┌───── Gemini 2.5 Pro  (AI suggestion only — never authoritative)
        └───── Upstash Redis   (rate-limit buckets)
```

Every tenant-scoped request resolves the tenant from the Firebase ID-token custom claims
(`role`, `tenant_id`). Cross-tenant roles (`CAAN_SMD`, `SUPER_ADMIN`) bypass tenant isolation for
read/aggregate endpoints and pass `tenant_id` explicitly when they want a single airline's view.

---

## 2. Tenants & Roles

| Role | Value | Tenant-bound? | Purpose |
|---|---|---|---|
| User | `USER` | Yes | Submits VSR/MOR, owns CANs/CAPs as responsible manager |
| Airline Admin | `AIRLINE_ADMIN` | Yes | Safety Manager: confirms risk, issues CANs, reviews CAPs, configures risk matrix |
| CAAN SMD | `CAAN_SMD` | No (cross-tenant) | State regulator oversight dashboards, state risk register, state-level reports |
| Super Admin | `SUPER_ADMIN` | No (cross-tenant) | Platform administration, provisioning, admin dashboards |

Defaults (`backend/app/core/config.py`): new users are `USER`; self-registration yields `AIRLINE_ADMIN`;
`CROSS_TENANT_ROLES = ["CAAN_SMD", "SUPER_ADMIN"]`; `SUPER_ADMIN_ROLES = ["SUPER_ADMIN"]`.

A Firestore fallback (`_lookup_tenant_by_email` in `backend/app/middleware/auth.py`) resolves the
tenant when ID-token claims are missing (known Firebase claim-propagation issue): if the caller's
email matches a tenant's `safety_manager.email`, they are treated as that tenant's `AIRLINE_ADMIN`.

---

## 3. Authentication & Session Flow

1. Any page gate runs `firebase.auth().onAuthStateChanged(...)`; with no session it redirects to
   `/login.html` (`public/js/api/client.js:37` redirects, as does each page's own guard).
2. `login.html` → Firebase Auth `signInWithEmailAndPassword`. Tenant is auto-detected from the
   subdomain or `?tenant=` (`public/js/tenant.js`) and the tenant theme is applied via
   `tenant-overrides.css`.
3. Every API call goes through `ApiClient` (`public/js/api/client.js`), which calls
   `user.getIdToken()` and sends `Authorization: Bearer <ID-token>`.
4. Backend `get_current_user` verifies the RS256 token via Firebase Admin SDK
   (`verify_firebase_token`), extracts `uid`, `email`, `role`, `tenant_id`, and normalises
   `tenant_id` (`_` → `-`).
5. Anonymous reporting is a **form field** (`is_anonymous`), not an anonymous session — the user
   must still be authenticated to submit.

**Post-login destination** depends on role (driven by `public/js/dashboard.js` and `shell.js`):

| Role | Landing page |
|---|---|
| `USER` / `AIRLINE_ADMIN` | `/dashboard/` (airline dashboard) |
| `CAAN_SMD` | `/caan.html` |
| `SUPER_ADMIN` | `/admin/index.html` |

---

## 4. Authorization (RBAC) Reference

Guards in `backend/app/middleware/auth.py` — granted roles:

| Guard | Roles allowed |
|---|---|
| `get_current_user` | Any authenticated user |
| `get_tenant_user` | Any authenticated user **with a `tenant_id`** |
| `get_caan_user` | `CAAN_SMD`, `SUPER_ADMIN` |
| `get_admin_user` | `SUPER_ADMIN` only |
| `get_safety_manager` | `AIRLINE_ADMIN` (tenant-bound), `CAAN_SMD`, `SUPER_ADMIN` |
| `get_responsible_manager` | `USER`, `AIRLINE_ADMIN`, `CAAN_SMD`, `SUPER_ADMIN` (tenant-bound unless cross-tenant) |
| `get_accountable_executive` | `AIRLINE_ADMIN` (tenant-bound), `CAAN_SMD`, `SUPER_ADMIN` |

Endpoint → guard mapping (canonical prefixes; legacy `/api/...` mirrors carry identical guards):

| Endpoint (prefix) | Guard |
|---|---|
| `POST/GET /api/v1/reports`, `POST /reports/vsr`, `POST /reports/mor`, `GET /reports` | `get_tenant_user` |
| `PUT /reports/{id}/risk-assessment` | `get_safety_manager` |
| `POST /api/v1/hazards`, `PUT /hazards/{id}`, `PATCH /hazards/{id}/status`, `PATCH /hazards/{id}/assign` | `get_tenant_user` |
| `GET /api/v1/hazards`, `GET /hazards/stats`, `GET /hazards/{id}` | `get_current_user` |
| `POST /api/v1/cans` (issue), `PATCH /cans/{id}/status`, `DELETE /cans/{id}`, `PATCH /caps/{id}/review` | `get_safety_manager` |
| `POST /cans/{id}/caps` (submit CAP), `PATCH /caps/{id}`, `PATCH /caps/{id}/status` | `get_responsible_manager` |
| `GET /api/v1/cans*`, `GET /caps*` | `get_current_user` |
| `POST /api/v1/verification/hazards/{id}/verifications`, `PATCH .../reopen` | `get_safety_manager` |
| `POST /api/v1/verification/hazards/{id}/closure` | `get_accountable_executive` |
| `GET /api/v1/verification*` | `get_current_user` |
| `POST/GET /api/v1/reporting/*` | `get_current_user` (cross-tenant roles may pass `tenant_id`; state-level reports write to `caan_reports`) |
| `GET/PUT /api/v1/admin/risk-matrix` | `get_safety_manager` |
| `POST /api/v1/admin/setup-claims`, `provision-airlines`, `fix-tenant-ids`, `create-seed-users`, `seed-demo-data` | `get_admin_user` (+ `SETUP_SECRET` second factor on provisioning) |
| `GET /api/v1/dashboard/*` | `get_tenant_user` |
| `GET /api/v1/dashboard/caan/*` | `get_caan_user` |
| `GET /api/v1/dashboard/admin/*` | `get_admin_user` |
| `POST/GET /api/v1/flight-diversions`, `PATCH /{id}` | `get_tenant_user` (read: `get_current_user`) |
| `POST/DELETE /flight-diversions/{id}/link-hazard` | `get_safety_manager` |
| `DELETE /flight-diversions/{id}` | `get_admin_user` |
| `GET /api/v1/state-risk/register`, `/aggregate`, `POST /sync` | `get_caan_user` |
| `PUT /api/v1/state-risk/register/{risk_id}/ssp-target` | `get_admin_user` |

---

## 5. Navigation Map (per role)

The sidebar is rendered from `window.SHELL_CONFIG` on each page (`public/js/shell.js`); links differ
per tenant type and role.

| Page | Who sees it | Key actions |
|---|---|---|
| `/dashboard/` | USER, AIRLINE_ADMIN | KPI cards, risk distribution, trends, recent reports, actions summary |
| `/report/vsr.html` | USER, AIRLINE_ADMIN | Submit voluntary safety report |
| `/report/mor.html` | USER, AIRLINE_ADMIN | Submit mandatory occurrence report |
| `/report/detail.html?id=` | USER, AIRLINE_ADMIN | View report + AI suggestions + confirm risk assessment |
| `/hazards/` (index, create, detail, verify, approve_closure) | USER, AIRLINE_ADMIN, CAAN_SMD, SUPER_ADMIN | Full hazard lifecycle |
| `/can_cap/cans.html` → `can_detail.html` → `cap_submit.html` / `cap_review.html` | all roles | CAN/CAP workflow |
| `/flight_diversions/` (index, create, detail) | all roles | Log/link diversions |
| `/reports/` (index, generate, view) | USER, AIRLINE_ADMIN (own tenant); CAAN_SMD, SUPER_ADMIN (any/state) | Quarterly/annual report generation + PDF export |
| `/survey/` | Anonymous (public) | Safety culture survey (POST `/api/v1/surveys`) |
| `/caan.html` | CAAN_SMD, SUPER_ADMIN | Aggregated airline oversight dashboard |
| `/caan-state-risk.html` | CAAN_SMD, SUPER_ADMIN | SSP / state risk register dashboard |
| `/admin/index.html` | SUPER_ADMIN | Provisioning, tenant list, risk-matrix config, platform health |
| `/portal/` | legacy | Retained mock pages (TD-7) — not part of the v1 flow |

---

## 6. Flow A — Voluntary Safety Report (VSR)

**Pages:** `public/report/vsr.html` + `public/js/vsr.js`

1. **About You** — reporter identity, contact, organisation.
2. **Aircraft Details** — type/model, category, registration, make/model.
3. **Flight Details** — phase, type, departure/destination, utilisation.
4. **Occurrence Details** *(mandatory validation)* — date, location, category, severity,
   probability, narrative, factors.
5. **Risk Assessment** — reporter's own severity/probability estimate.
6. **Review & Submit** — good-faith checkbox (`confirmGoodFaith`); submit disabled until checked.

**On submit:**
- `vsr.js:349` → `POST {apiBaseUrl}/api/v1/reports/vsr` with `Authorization: Bearer <ID-token>`.
- Payload sets `report_type: "voluntary"`, defaults `is_anonymous: true`.
- Backend (`routes/reports.py:95`, `get_tenant_user`) creates the report under
  `tenants/{tenant_id}/reports/` (via `get_tenant_collection`), sets `status: "NEW"`,
  `ai_status: "PENDING"`, computes the ICAO risk index from the reporter's severity × probability
  using the tenant's stored thresholds (`risk_matrix` doc), and kicks off Gemini analysis.
- VSR submissions are rate-limited: **50/day** (`vsr_submit`).
- Success → "Report submitted successfully! Reference: {id}".

---

## 7. Flow B — Mandatory Occurrence Report (MOR)

**Pages:** `public/report/mor.html` + `public/js/mor.js`

1. **Reporter Details** — mandatory identity (MOR is never anonymous).
2. **Aircraft Details**
3. **Engine & Propeller** *(optional)*
4. **Flight Details**
5. **People on Board** *(optional)* — crew/passenger counts, injuries.
6. **Occurrence Details**
7. **Occurrence Category & Factors**
8. **Risk Assessment & Submit** — good-faith checkbox ("information is factual").

**On submit:**
- `mor.js:414` → `POST {apiBaseUrl}/api/v1/reports/mor`; `report_type: "mandatory"`,
  `is_anonymous: false`, `reporting_date` stamped server-side.
- Backend (`routes/reports.py:48`) writes to the same tenant `reports` subcollection with the same
  `NEW`/`PENDING` initial state.
- MOR submissions are rate-limited: **20/day** (`mor_submit`).

> **API surface note:** VSR/MOR use the canonical `/api/v1/reports/...` paths, while the
> `ApiClient`-based modules (`hazards.js`, `can_cap.js`, `verification.js`, `flight_diversions.js`,
> `reports.js`, `api/dashboard.js`) currently target the **legacy `/api/...`** prefixes. Both are
> registered on the same routers in `backend/app/main.py`, so they resolve to identical handlers.

---

## 8. Flow C — Report Review & Risk Assessment

**Pages:** `public/report/detail.html` + `public/js/report.js`

1. `report.js:102` → `GET /api/v1/reports/{id}` renders the report.
2. The **ICAO Risk Index** card shows the computed `severity × probability` index and level
   (`report.js:177`): ≤5 Low · ≤9 Medium · ≤15 High · \>15 Very High.
3. The **AI Assistant** card shows Gemini's suggested severity/probability with a clear
   "suggested, not authoritative" disclaimer.
4. A Safety Manager clicks **Confirm Assessment** →
   `report.js:117` → `PUT /api/v1/reports/{id}/risk-assessment`
   (`get_safety_manager`) with `{ severity, probability, notes }`. This is the **official**
   risk assessment that drives hazard classification downstream.
5. `getRiskMatrix()` / `updateRiskMatrix()` (`report.js:141,156`) read/write the tenant's
   `risk_matrix` config via `GET`/`PUT /api/v1/admin/risk-matrix` (also `get_safety_manager`).
   Defaults: `low_max=5, medium_max=9, high_max=15`.

---

## 9. Flow D — Hazard Lifecycle

**Pages:** `public/hazards/{index,create,detail,verify,approve_closure}.html` + `public/js/hazards.js`

`HazardService` (`backend/app/services/hazard_service.py`) stores hazards at
`tenants/{tenant_id}/hazards/{docId}` and generates IDs of the form
`{tenant_code}-HZ-{taxonomy_code}-{seq:02d}-{yy}`.

```
create ──► OPEN ──► PROCESSING ──► UNDER_REVIEW ──► PENDING_CLOSURE ──► CLOSED
                     ▲                                                 │
                     └────────────── REOPENED ◄────────────────────────┘
```

| Step | Page | API call (module) | Guard |
|---|---|---|---|
| Create hazard | `hazards/create.html` | `POST /api/hazards` (`hazards.js:15`) | `get_tenant_user` |
| List / filter / stats | `hazards/index.html` | `GET /api/hazards?status=&priority=&source=&taxonomy=&tenant_id=&search=` · `GET /api/hazards/stats` | `get_current_user` |
| View | `hazards/detail.html` | `GET /api/hazards/{id}` | `get_current_user` |
| Edit | `hazards/detail.html` | `PUT /api/hazards/{id}` | `get_tenant_user` |
| Transition status | `hazards/detail.html` | `PATCH /api/hazards/{id}/status?status=` | `get_tenant_user` |
| Assign | `hazards/detail.html` | `PATCH /api/hazards/{id}/assign?assigned_to=&assigned_to_uid=` | `get_tenant_user` |
| Verify CAP | `hazards/verify.html` | `POST /api/verification/hazards/{id}/verifications` | `get_safety_manager` |
| Approve closure | `hazards/approve_closure.html` | `POST /api/verification/hazards/{id}/closure` | `get_accountable_executive` |

Enums (`backend/app/models/hazard.py`):

- **Status** (enum member → stored value): `OPEN→"Open"`, `PROCESSING→"Processing"`,
  `UNDER_REVIEW→"Under Review"`, `PENDING_CLOSURE→"Pending Closure"`, `CLOSED→"Closed"`,
  `REOPENED→"Reopened"`.
- **Priority** (stored value): `HIGH→"H"`, `MEDIUM→"M"`, `LOW→"L"`.
- **Source (12):** `VSR`, `MOR`, `Quality Audit`, `Safety Inspection`, `Flight Diversion`,
  `CAAN Audit`, `Internal Audit`, `Safety Survey`, `IOR`, `MOC`, `SRM Request`, `Incident`.
- **Taxonomy (7):** `Organizational-Facilities`, `Organizational-Documentation, Processes and
  Procedures`, `Technical`, `Wildlife`, `Human Factors`, `Environmental`, `Other` — the taxonomy
  category feeds the generated hazard ID.

CAAN_SMD / SUPER_ADMIN can filter across tenants by passing `tenant_id` (allowed via
`effective_tenant` resolution in the route).

---

## 10. Flow E — CAN / CAP Workflow

**Pages:** `public/can_cap/{cans,can_detail,cap_submit,cap_review}.html` + `public/js/can_cap.js`

| Step | Page | API call | Guard |
|---|---|---|---|
| Issue CAN | `can_cap/cans.html` (issue modal) | `POST /api/cans` (`can_cap.js:15`) | `get_safety_manager` |
| List / stats | `cans.html` | `GET /api/cans?filters` · `GET /api/cans/stats` | `get_current_user` |
| View CAN + its CAPs | `can_detail.html` | `GET /api/cans/{id}` · `GET /api/cans/{id}/caps` | `get_current_user` |
| Change CAN status | `can_detail.html` | `PATCH /api/cans/{id}/status?status=` | `get_safety_manager` |
| Submit CAP | `cap_submit.html` | `POST /api/cans/{id}/caps` (`can_cap.js:25`) | `get_responsible_manager` |
| Review CAP | `cap_review.html` | `PATCH /api/cans/caps/{id}/review` (`can_cap.js:33`) | `get_safety_manager` |
| Update CAP (content) | `cap_review.html` | `PATCH /api/cans/caps/{id}` | `get_responsible_manager` |
| CAP status change | `cap_review.html` | `PATCH /api/cans/caps/{id}/status?status=` | `get_responsible_manager` |
| Delete CAN | `cans.html` | `DELETE /api/cans/{id}` | `get_safety_manager` |

Verification records (outcome = `ACCEPTED` / `REVISION_REQUIRED` / `INEFFECTIVE` / `OVERDUE`) are
stored in the `verifications` subcollection of the hazard and referenced from the CAP, closing the
loop between flows E and D.

---

## 11. Flow F — Flight Diversions

**Pages:** `public/flight_diversions/{index,create,detail}.html` + `public/js/flight_diversions.js`

| Step | API call | Guard |
|---|---|---|
| Log diversion | `POST /api/flight-diversions` (`flight_diversions.js:13`) | `get_tenant_user` |
| List / stats | `GET /api/flight-diversions?filters` · `GET /api/flight-diversions/stats` | `get_current_user` |
| View / update | `GET /api/flight-diversions/{id}` · `PATCH /api/flight-diversions/{id}` | `get_current_user` / `get_tenant_user` |
| Link to hazard | `POST /api/flight-diversions/{id}/link-hazard?hazard_id=` | `get_safety_manager` |
| Unlink hazard | `DELETE /api/flight-diversions/{id}/link-hazard` | `get_safety_manager` |
| Delete | `DELETE /api/flight-diversions/{id}` | `get_admin_user` |

`detail.html` renders any linked hazard with a "View Hazard" jump-link to
`/hazards/detail.html?id=...`.

---

## 12. Flow G — Safety Survey

**Page:** `public/survey/` (`index.html` + `app.js` + `default_q.js` + `style.css`, public, no login gate)

1. Tenant resolved from `?tenant=` (or hostname route map); unknown tenants see
   the "not found" screen.
2. Renders 23 bilingual (EN/नेपाली) ICAO 4-pillar questions from `MASTER_QUESTIONS`
   in `default_q.js`, with progress tracking and a comments box.
3. On completion the response is POSTed **to the backend survey endpoint**
   `POST /api/v1/surveys` (`app.js:335`), which validates, scores, and persists
   responses server-side. The API base URL is `APP_CONFIG.apiBaseUrl`
   (`https://aviasafe-unified-platform.onrender.com`)
   or derived from the hostname when the config module is not loaded.
4. `/portal/survey/` is a legacy redirect to `/survey/` (preserving `?tenant=`).

> **Note:** the historical classic survey (`public/survey/`, v2.2.0) that wrote responses
> client-side directly to Firestore was replaced by the v3 functional form in this flow.


---

## 13. Flow H — Quarterly / Annual Safety Reports

**Pages:** `public/reports/{index,generate,view}.html` + `public/js/reports.js`

| Step | API call (module) | Notes |
|---|---|---|
| Generate quarterly | `POST /api/reporting/quarterly?year=&quarter=&tenant_id=` (`reports.js:5`) | Non-cross-tenant users are forced to their own tenant; CAAN_SMD/SUPER_ADMIN may pass `tenant_id` or omit for state-level |
| Generate annual | `POST /api/reporting/annual?...` | same semantics |
| List | `GET /api/reporting/quarterly?...` / `GET /api/reporting/annual?...` | |
| View | `GET /api/reporting/quarterly/{id}` / `annual/{id}` | `view.html` renders KPIs, charts, recommendations |
| Export PDF | `GET /api/reporting/{type}/{id}/export` | `ReportGenerator` + `generate_report_pdf` |

Storage: tenant-level reports in `tenants/{tenant_id}/reporting/`; state-level reports (generated by
CAAN_SMD without `tenant_id`) in the top-level `caan_reports` collection. `REPORT_COLLECTION = "reporting"`.

---

## 14. Flow I/J — Dashboards

**Airline dashboard** (`public/dashboard/` + `public/js/api/dashboard.js`, guard `get_tenant_user`):

| Endpoint | Purpose |
|---|---|
| `GET /api/dashboard/overview?days=` | KPI cards (reports, hazards, open CANs, closure rate) |
| `GET /api/dashboard/recent` | Recent reports (paginated) |
| `GET /api/dashboard/risk` | Risk distribution |
| `GET /api/dashboard/trends` | Monthly trends |
| `GET /api/dashboard/hazards` | Hazard frequency by taxonomy |
| `GET /api/dashboard/actions` | Outstanding actions summary |

**CAAN SMD dashboard** (`public/caan.html`, guard `get_caan_user`):

| Endpoint | Purpose |
|---|---|
| `GET /api/dashboard/caan/overview` | Aggregated overview across all tenant airlines |
| `GET /api/dashboard/caan/trends` | Cross-tenant trend lines |
| `GET /api/dashboard/caan/risk` | Cross-tenant risk distribution |
| `GET /api/dashboard/caan/hazards` | Cross-tenant hazard frequency |
| `GET /api/dashboard/caan/survey-maturity` | Survey participation/maturity via `collection_group("surveys")` |
| `GET /api/dashboard/caan/benchmark` | Airline benchmarking (currently placeholder) |

**Platform admin** (`public/admin/index.html`, guard `get_admin_user`):
`GET /api/dashboard/admin/{system,tenants,usage}` for health, tenant listing, and usage analytics.

---

## 15. Flow K — State Risk Register & SSP Aggregation

**Pages:** `public/caan-state-risk.html` + backend `StateRiskService`
(`backend/app/services/state_risk_service.py`)

- Reference data lives at `state/icao_top_risks/categories` (`STATE_RISK_REFERENCE_PATH`); the
  register is a `risk_register` subcollection; each ICAO top-risk category (LOCI, CFIT, RE, RI,
  MAC, …) carries an `ssp_target`.
- `GET /api/v1/state-risk/register?year=&quarter=` → the state register for the period
  (`get_caan_user`).
- `GET /api/v1/state-risk/aggregate?year=&quarter=` → aggregates safety metrics across **all**
  tenants (reports, hazards, risk distributions, closure) and compares actual risk vs SSP targets,
  driving tolerability (`ACCEPTABLE` / `TOLERABLE` / `INTOLERABLE`) and trend
  (`IMPROVING` / `STABLE` / `DETERIORATING`).
- `POST /api/v1/state-risk/sync` re-syncs the register from live data (`get_caan_user`).
- `PUT /api/v1/state-risk/register/{risk_id}/ssp-target` updates an SSP target (`get_admin_user`).

---

## 16. Rate Limiting

`backend/app/middleware/rate_limit.py` (Upstash Redis when `REDIS_URL` is set; in-memory fallback;
global `60 req/min` default). Buckets:

| Bucket | Limit | Applied to |
|---|---|---|
| `vsr_submit` | 50 / day | VSR submission |
| `mor_submit` | 20 / day | MOR submission |
| `survey_submit` | 100 / day | Survey submissions |
| `dashboard` | 500 / hour | Dashboard reads |
| `auth_attempts` | 50 / hour | Login attempts |

---

## 17. Data Model Appendix

**Collections** (all tenant data under `tenants/{tenant_id}/` unless noted):

| Path | Contents |
|---|---|
| `tenants/{tenant_id}/` | Tenant doc (name, ICAO, `safety_manager`, theme) |
| `tenants/{tenant_id}/reports/` | Safety reports (VSR/MOR + generic) |
| `tenants/{tenant_id}/hazards/` | Hazards (id `{tenant_code}-HZ-{taxonomy}-{seq}-{yy}`) |
| `tenants/{tenant_id}/hazards/{id}/verifications/` | CAP verification records |
| `tenants/{tenant_id}/hazards/{id}/closure/` | Closure approval doc (lessons, recommendations) |
| `tenants/{tenant_id}/can_cap/` | Corrective Action Notices (`CAN_COLLECTION = "can_cap"`) |
| `tenants/{tenant_id}/can_cap/{id}/caps/` | Corrective Action Plans (`CAP_SUBCOLLECTION = "caps"`) |
| `tenants/{tenant_id}/flight_diversions/` | Diversion logs (`DIVERSION_COLLECTION = "flight_diversions"`) |
| `tenants/{tenant_id}/reporting/` | Generated quarterly/annual reports |
| `tenants/{tenant_id}/metadata` → doc `risk_matrix` | Per-tenant risk thresholds + severity/probability/labels (`RISK_MATRIX_DOC_PATH = "risk_matrix"`) |
| `reports/` | Legacy flat reports (compat) |
| `caan_reports/` | State-level generated reports |
| `surveyResponses` / `tenants/{id}/responses` | Survey responses (TD-6 path) |
| `state/icao_top_risks/categories` + `risk_register` | SSP reference + state register |

**Composite indexes** (`backend/firestore.indexes.json`): collectionGroup `reports` on
`occurrence_date + created_at`, `report_type + occurrence_date + created_at`,
`severity + occurrence_date + created_at`, `status + occurrence_date + created_at`.

**Key enums:**

- Report: `VOLUNTARY`/`MANDATORY`; status `NEW`/`PROCESSING`/`COMPLETED`/`SUBMITTED`/`FAILED`/`ARCHIVED`;
  AI status `PENDING`/`PROCESSING`/`COMPLETED`/`FAILED`; occurrence type
  `ACCIDENT`/`SERIOUS_INCIDENT`/`INCIDENT`; severity 1–5.
- Hazard: statuses/priorities/sources/taxonomies (see §9).
- Verification outcome: `ACCEPTED`/`REVISION_REQUIRED`/`INEFFECTIVE`/`OVERDUE`.
- State risk: tolerability `ACCEPTABLE`/`TOLERABLE`/`INTOLERABLE`; trend `IMPROVING`/`STABLE`/`DETERIORATING`.

---

## 18. Known Caveats (in scope for this map)

- **Dual API surface:** canonical `/api/v1/...` and legacy `/api/...` both registered on the same
  routers; the `ApiClient`-based JS modules still call the legacy paths while report forms call
  `/api/v1/...` (see §7 note).
- **Survey writes bypass the API** (client-side Firestore, TD-6) — see §12.
- **App Check is not enforced server-side** (TD-12) — public-create endpoints rely on auth +
  rate limiting only.
- **CAAN benchmark and some trend widgets** are placeholders (`caan/benchmark`).
- **Destructive seed/admin endpoints** return 404 in production (`DISABLE_DESTRUCTIVE_ENDPOINTS`).
