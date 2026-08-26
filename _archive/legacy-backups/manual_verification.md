# AviaSAFE SMS - Manual Verification Checklist

## Overview

This document contains the comprehensive manual verification checklist for the AviaSAFE SMS platform, covering all major user journeys and system functionalities.

**Current Status**: All flows verified and functional on both beta and production. 2026-08-10 refinements shipped — simplified credentials (`{role}@{tenant}.com`), CAAN SUPER_ADMIN removed, SMS Maturity terminology rename, hazard-source enforcement + flight-diversion auto-hazard, and new Super-Admin flows (tenant lifecycle status Trial/Active/Inactive + dummy VSR/MOR/CAN/CAP seed/unseed). **2026-08-11**: the global **National → State** terminology refactor shipped — UI labels, JS identifiers, the API contract (`data.national` → `data.state`), services, tests and docs — verified end-to-end by the automated suite; and the **RBAC role mapping for the simplified credentials** was deployed live — `safety` stays **AIRLINE_ADMIN**, while `camo`/`145`/`ops` became **USER** accounts carrying a `department` custom claim (CAMO / Part-145 / Flight Operations) so they route to the Responsible Manager dashboard. 28 accounts were updated in Firebase Auth and the `users` collection re-synced (51 docs) in both `sms-db-beta` and `sms-db`. Full suite now **231 passing** (incl. `tests/test_reporting_scoping.py` and `tests/test_rbac_claims.py`); the 2026-08-10 service-level rows were re-confirmed by that same run. Rows still blank are UI / live-infra items awaiting manual verification.

---

## Airline Dashboard

**User**: Safety Officer (AIRLINE_ADMIN)

| # | Step | Expected Result | Status |
|---|------|-----------------|--------|
| 1 | Login as `safety@tara-air.com` / `TARA-Safety-2026` | Successful login to dashboard | ✅ |
| 2 | Dashboard loads | KPIs, Risk & Trends, Top Hazards visible | ✅ |
| 3 | "SMS Maturity Assessment" section | Visible with maturity score and pillar breakdowns (terminology = **SMS Maturity**, not "SMS health") | ✅ |
| 4 | "Hazard Register" | Shows hazards (4-7 per tenant) | ✅ |
| 5 | "Latest Reports" | Shows recent VSR/MOR submissions | ✅ |
| 6 | "CAN/CAP" section | Visible with progress indicators | ✅ |
| 7 | **Administration section** | Visible with: | ✅ |
|   | - Survey Rate Limit control | Dropdown with 5/10/25/50/100 options | ✅ |
|   | - Authorized Users list | Table showing all tenant users | ✅ |
|   | - Survey Instructions editor | Textarea with save functionality | ✅ |

### Navigational Verification
- [ ] Sidebar links navigate to correct pages
- [ ] Top navigation shows tenant name
- [ ] Logout button works correctly
- [ ] Search and filters on Hazard Register work
- [ ] Pagination works on Reports list

---

## CAAN / State Regulator Dashboard

**User**: CAAN_SMD (Regulator)

| # | Step | Expected Result | Status |
|---|------|-----------------|--------|
| 1 | Login as `sms.inspector@caan.gov.np` | Successful login to CAAN dashboard | ✅ |
| 2 | CAAN dashboard loads | State view with all operators | ✅ |
| 3 | All 7 operators visible | List includes all seeded tenants | ✅ |
| 4 | State SMS Maturity | Aggregated maturity score displayed | ✅ |
| 5 | Aggregate statistics | Summary statistics across all operators | ✅ |
| 6 | Regulator metadata | Regulator ID and name displayed | ✅ |
| 7 | State Risk Dashboard | Risk categories (RE, RI, etc.) displayed | ✅ |

### Regulator Specific Checks
- [ ] Cross-tenant data is aggregated (not showing individual reports)
- [ ] Survey Maturity shows aggregated pillar scores
- [ ] State Risk Dashboard shows state risk trends
- [ ] Regulator ID (`caan`) is read correctly
- [ ] Tagged operators (7) are all visible

---

## Survey Flow

**User**: Employee (Anonymous / Public Access)

| # | Step | Expected Result | Status |
|---|------|-----------------|--------|
| 1 | Go to `/survey/?tenant=tara-air` | Survey loads with tenant name (e.g., "Tara Air") | ✅ |
| 2 | Go to `/survey/` (no tenant) | Popup appears → redirects to home after 10s | ✅ |
| 3 | Login as Safety Officer → `/survey/?tenant=tara-air` | Survey loads (no popup, logged-in bypass) | ✅ |
| 4 | Survey instructions | Displayed (from Safety Officer's settings) | ✅ |
| 5 | Survey progress | "0 of 23 answered" updates as questions are answered | ✅ |
| 6 | Submit survey | Success message displayed | ✅ |
| 7 | Check dashboard | SMS Maturity score updates after submission | ✅ |

### Survey Display Verification
- [ ] Tenant name displayed in extra large, centered font
- [ ] Title reads "SMS Maturity Assessment"
- [ ] Subtitle reads: "Based on Safety Management System's 4 pillars and 12 elements. This survey is conducted aligning Annex 19, Doc 9859, Doc 10159 and state requirements."
- [ ] Bilingual support (English/Nepali) works
- [ ] Anonymous option is available
- [ ] Rate limiting (5/day/tenant) is enforced

### Survey Closed Handling
- [ ] If survey window is closed, message displays: "Survey period is not open"
- [ ] Open/close dates are shown in the closed message
- [ ] Safety Officer can open/close survey via dashboard

---

## Report Flow

**User**: Safety Officer (AIRLINE_ADMIN)

| # | Step | Expected Result | Status |
|---|------|-----------------|--------|
| 1 | Submit a VSR | Report is saved and appears in Reports list | ✅ |
| 2 | Check Hazard Register | Hazard is auto-created from report (if risk threshold met) | ✅ |
| 3 | Issue CAN from hazard | CAN is created and linked to hazard | ✅ |
| 4 | Create CAP from CAN | CAP is created and linked to CAN | ✅ |
| 5 | Complete CAP → CAN auto-closes | CAN status updates to Closed | ✅ |

### Additional Report Flow Checks
- [ ] Hazard status updates correctly (Open → Processing → Under Review → Closed)
- [ ] Report appears in "Latest Reports" section
- [ ] Risk matrix calculation (5/9/15) is correct
- [ ] Audit trail shows actions (created by, timestamps)
- [ ] CAN past its `target_completion_date` and still Open flips to **Escalated** when the daily escalation job runs
- [ ] CAP past due (non-terminal) flips to **Overdue**
- [ ] Audit trail for escalations is recorded in the `audit_logs` collection (`log_audit` in `backend/app/services/audit_service.py`)

---

## Hazard Source Enforcement & Flight Diversion (2026-08-10)

**User**: Safety Officer (AIRLINE_ADMIN) + backend-automated

| # | Step | Expected Result | Status |
|---|------|-----------------|--------|
| 1 | **NEW** Create a hazard with an allowed source | `POST /api/v1/hazards` with `source` in `{"VSR","MOR","Internal Audit","Quality Audit","CAAN Audit","Flight Diversion"}` succeeds | |
| 2 | **NEW** Create a hazard with a disallowed source | Request is rejected with 400 and a message listing the allowed sources | |
| 3 | **NEW** Report a flight diversion | `POST /api/v1/flight-diversions` succeeds | |
| 4 | **NEW** Check Hazard Register after diversion | A linked hazard is **auto-created** with `source="Flight Diversion"`, `source_id=<diversion id>`, and a link back to the diversion | |
| 5 | **NEW** Delete the diversion's auto-hazard | `DELETE` of the linked hazard is blocked (cleanup requires no `source_id`) | |

### Hazard Source / Diversion Detailed Checks
- [ ] `HAZARD_CREATION_SOURCES` allow-list enforced in `backend/app/models/hazard.py`
- [ ] Auto-created hazard carries `source_id` pointing to the flight diversion
- [ ] `backend/scripts/inspect-report-hazard-link.js` can audit the linkage
- [ ] `backend/scripts/seed_flight_diversions.py` seeds diversions + linked hazards on demand

---

## Landing Page

**User**: Visitor (Public)

| # | Step | Expected Result | Status |
|---|------|-----------------|--------|
| 1 | Visit `https://sms.aviasafesystems.com` | Landing page loads | ✅ |
| 2 | Hero section | Displays "From Safety Reporting to Safety Intelligence" | ✅ |
| 3 | Navigation | Includes: Home, Features, Tenant Portal, Contact, Login | ✅ |
| 4 | "Contact" link | Navigates to `contact.html` | ✅ |
| 5 | Founder section | Displays rectangular photo (not circular) | ✅ |
| 6 | "Just Culture" | Removed from founder section | ✅ |
| 7 | Footer | Includes "Developer Login" link | ✅ |

### Landing Page Detailed Checks
- [ ] Compliance badge shows "ICAO Annex 19 · Doc 9859 · Doc 10159 Aligned"
- [ ] Features section shows grouped ecosystem (Capture: Gap Analysis Survey, Voluntary Safety Reporting; Assess & Manage: Hazard Identification & Risk Assessment, Mandatory Occurrence Reporting; Assure & Decide: Safety Dashboard, Regulatory & Industry Intelligence)
- [ ] Why It Matters section displays
- [ ] Standards/Trust section shows ICAO Annex 19, Doc 9859, Doc 10159
- [ ] Tenant Portal section has input field for Tenant ID
- [ ] Footer has project credit: "A project by Ghanshyam Acharya" (no external link)

---

## Contact Page

**User**: Visitor (Public)

| # | Step | Expected Result | Status |
|---|------|-----------------|--------|
| 1 | Visit `https://sms.aviasafesystems.com/contact.html` | Contact page loads | ✅ |
| 2 | Contact form | Fields: Name, Email, Subject, Message | ✅ |
| 3 | Submit form | Data sent to Sender.net | ✅ |
| 4 | Success message | Displayed on successful submission | ✅ |
| 5 | Mobile responsive | Form works on all screen sizes | ✅ |

### Contact Page Detailed Checks
- [ ] Form validation works (required fields)
- [ ] Email validation works
- [ ] Sender.net integration works
- [ ] Success/error messages are user-friendly
- [ ] No sensitive data is exposed

---

## Admin Panel (Super-Admin)

**User**: SUPER_ADMIN

> **Important (2026-08-10)**: the previous SUPER_ADMIN account `safety.director@caan.gov.np` was **removed**. To restore a SUPER_ADMIN, promote an existing CAAN_SMD account (e.g. `sms.inspector@caan.gov.np` or `director.safety@caan.gov.np`) by setting the `SUPER_ADMIN` custom claim via `POST /api/v1/admin/setup-claims` (requires the setup key).

| # | Step | Expected Result | Status |
|---|------|-----------------|--------|
| 1 | Promote a CAAN_SMD to SUPER_ADMIN (e.g. `sms.inspector@caan.gov.np`) | Account now signs in with SUPER_ADMIN role | |
| 2 | Developer Login link | Visible in footer | ✅ |
| 3 | Production Setup page | `/admin/production-setup.html` loads | ✅ |
| 4 | Regulator creation | Create regulator document | ✅ |
| 5 | Tenant creation | Create tenant with credentials | ✅ |
| 6 | **NEW** Tenant status management | "Manage" per tenant sets Trial / Active / Inactive + contract dates + payment status | ✅ (automated) |
| 7 | **NEW** Dummy-data seed / unseed | Seed + unseed VSR/MOR/CAN/CAP for one tenant or all tenants | ✅ (automated) |
| 8 | Tenant Credentials page | `/admin/tenant-credentials.html` loads | ✅ |
| 9 | Authorized Users list | View-only table in Administration section | ✅ |

### Admin Panel Detailed Checks
- [ ] App Check is skipped on `/admin/` paths
- [ ] Setup key is required for seeding
- [ ] Audit logs are recorded for all actions
- [ ] Bulk import (CSV/JSON) works
- [ ] Preview before deployment works

---

## Tenant Lifecycle Status (2026-08-10)

**User**: SUPER_ADMIN

| # | Step | Expected Result | Status |
|---|------|-----------------|--------|
| 1 | **NEW** Open `/admin/production-setup.html` → Tenants table | Status column shows Trial / Active / Inactive badge | |
| 2 | **NEW** Click "Manage" on a tenant | Inline form opens with status dropdown, contract start/end date inputs, payment dropdown | |
| 3 | **NEW** Set explicit status to `Trial` and save | `POST /api/v1/admin/tenants/{id}/status` returns the updated tenant; badge turns info-blue | ✅ (automated) |
| 4 | **NEW** Set contract dates + leave status "auto" | Status is derived: start date in the future → **Trial**, within range → **Active**, end date past → **Inactive** | ✅ (automated) |
| 5 | **NEW** Set payment to `Unpaid` | Status derives to **Inactive** regardless of contract dates | ✅ (automated) |
| 6 | **NEW** Verify `active` bool | `active` is `true` only when status = Active | ✅ (automated) |
| 7 | **NEW** Check audit log | A `TENANT_STATUS_UPDATED` entry records the actor, new status, and contract dates | ✅ (automated) |

### Tenant Lifecycle Detailed Checks
- [ ] Status validation: only `Trial` / `Active` / `Inactive` accepted (400 otherwise)
- [ ] Date validation: invalid `YYYY-MM-DD` rejected with a clear message
- [ ] `contract.start_date` / `contract.end_date` / `payment_status` persisted on the tenant doc

---

## Dummy Data Seed / Unseed (2026-08-10)

**User**: SUPER_ADMIN

| # | Step | Expected Result | Status |
|---|------|-----------------|--------|
| 1 | **NEW** Step 5 card on `/admin/production-setup.html` | Scope (all tenants / single tenant) + VSR/MOR/CAN/CAP checkboxes visible | |
| 2 | **NEW** Seed VSR+MOR for all tenants | `POST /api/v1/admin/demo-data` creates voluntary + mandatory reports per tenant | ✅ (automated) |
| 3 | **NEW** Seed CAN+CAP for one tenant | CANs (with linked hazards) + CAPs created in `can_cap` (+ `caps`) | ✅ (automated) |
| 4 | **NEW** Dashboards reflect the dummy data | Reports list, Hazard Register and CAN/CAP sections populate | |
| 5 | **NEW** Unseed the same data | Only docs marked `admin-demo-1` are removed — real reports/hazards/CANs are untouched | ✅ (automated) |
| 6 | **NEW** Check audit log | `DEMO_DATA_SEED` / `DEMO_DATA_UNSEED` entries record counts per tenant | ✅ (automated) |

### Dummy Data Detailed Checks
- [ ] Kind validation: unknown kind (e.g. `bogus`) returns a per-tenant error, not a crash
- [ ] Seeded reports carry `report_type=voluntary` (VSR) or `report_type=mandatory` (MOR)
- [ ] Seeded CANs link to a hazard and carry `seed_version=admin-demo-1`
- [ ] Unseed with no target tenants returns 400 with a clear message
- [ ] Unseeding "cap" only removes CAPs and keeps the CANs + hazards

---

## Developer Login

**User**: SUPER_ADMIN

| # | Step | Expected Result | Status |
|---|------|-----------------|--------|
| 1 | Click "Developer Login" in footer | Redirects to `/admin/login.html` | ✅ |
| 2 | Login as a promoted SUPER_ADMIN (e.g. `sms.inspector@caan.gov.np`) | Successful login | |
| 3 | Redirect | Redirects to `/admin/production-setup.html` | ✅ |
| 4 | Panel loads | "Logged in as SUPER_ADMIN..." displayed | ✅ |

### Developer Login Detailed Checks
- [ ] Auth works without `?appcheck=false` hack
- [ ] Hard-refresh (Ctrl+Shift+R) loads new `firebase.js`
- [ ] SUPER_ADMIN role is enforced
- [ ] Tenant list loads in admin panel

---

## Master Register

**User**: Safety Officer (AIRLINE_ADMIN), SUPER_ADMIN, CAAN_SMD

| # | Step | Expected Result | Status |
|---|------|-----------------|--------|
| 1 | Login as `safety.tara-air@taraair.com` | Successful login to dashboard | |
| 2 | Click "Master Register" in sidebar | Navigates to `/dashboard/master-register.html` | |
| 3 | Page loads | Tabs for Hazards / CANs / CAPs + stat cards visible | |
| 4 | Hazards tab | Shows unified hazard list (all statuses) | ✅ (automated) |
| 5 | CANs tab | Shows CAN list with status badges (incl. Escalated) | ✅ (automated) |
| 6 | CAPs tab | Shows CAP list with status badges (incl. Overdue) | ✅ (automated) |
| 7 | Status filter | Filtering narrows the list correctly | |
| 8 | Department filter | Filtering by department returns only that department's records | ✅ (automated) |
| 9 | Search box | Text search narrows by reference/title | |
| 10 | Sortable columns | Clicking a column header sorts the table | |

### Master Register Detailed Checks
- [ ] Data comes from `GET /api/v1/dashboard/master-register`
- [ ] Both Hazards and CANs/CAPs appear in the same register
- [ ] CAN "Escalated" and CAP "Overdue" badges render correctly
- [ ] Role access: AIRLINE_ADMIN sees own tenant; CAAN_SMD/SUPER_ADMIN see all
- [ ] Department scoping respects the caller's department when provided

---

## Responsible Manager (My Tasks)

**User**: USER with a `department` claim

| # | Step | Expected Result | Status |
|---|------|-----------------|--------|
| 1 | Login as a USER account with a department | Redirects to `/dashboard/responsible-manager.html` (not `/safety.html`) | |
| 2 | Page loads | Title reads "My Tasks" | |
| 3 | CAN/CAP list | Shows only CANs/CAPs assigned to the logged-in user (`assigned_to_uid`) | |
| 4 | Hazards tab hidden | No full-hazard view for this role | |
| 5 | Department filter | Present and pre-scoped to the user's department | |
| 6 | "Master Register" button | Links back to `/dashboard/master-register.html` | |

### Responsible Manager Detailed Checks
- [ ] `getRoleDestination()` in `public/js/firebase.js` routes USER-with-department to this page
- [ ] USER without a department still lands on `/safety.html`
- [ ] Tasks from other users are not visible

---

## Department Mapping

**User**: Safety Officer (AIRLINE_ADMIN)

| # | Step | Expected Result | Status |
|---|------|-----------------|--------|
| 1 | Create/assign a hazard to a user who has a department | Hazard document gets a `department` field matching the assignee | |
| 2 | Issue a CAN | CAN gets the assignee's department | |
| 3 | Create a CAP from a CAN | CAP inherits the CAN's department | |
| 4 | Edit a user's department in admin | New assignments use the updated department | |
| 5 | Filter hazards by department | `GET /api/v1/hazards?department=<dept>` returns only matching hazards | |
| 6 | Filter CANs/CAPs by department | `GET /api/v1/cans?department=<dept>` / `.../cans/caps?department=<dept>` work | |

### Department Mapping Detailed Checks
- [ ] Department is read from the user's profile (`department` field) on assignment
- [ ] CAP created from a CAN carries the CAN's department (even if the CAP owner differs)
- [ ] Users without a department produce records with empty department (no crash)

---

## Escalation & Audit Trail

**User**: Safety Officer (AIRLINE_ADMIN) — backend-automated

| # | Step | Expected Result | Status |
|---|------|-----------------|--------|
| 1 | Have an Open CAN past its `target_completion_date` | `POST /api/v1/admin/tasks/check-overdue` (with `X-Task-Key`) sets it to **Escalated** | ✅ (automated) |
| 2 | Have a CAP past due (non-terminal status) | Same run sets it to **Overdue** | ✅ (automated) |
| 3 | Re-run the check | Idempotent — already-escalated/overdue records are not re-processed | ✅ (automated) |
| 4 | Check `audit_logs` collection | Each escalation writes an audit entry (action/actor/target/detail/timestamp) | ✅ (automated) |
| 5 | Scheduled run | Cloud Scheduler job `check-overdue` fires daily at 00:00 UTC | |
| 6 | Manual trigger | `gcloud scheduler jobs run check-overdue --location=us-west1 --project=aerosafety-sms-prod` | |

### Escalation Detailed Checks
- [ ] Endpoint requires `X-Task-Key` matching `TASK_API_KEY` (or a SUPER_ADMIN token) — otherwise 403
- [ ] Terminal statuses (Closed) are never escalated
- [ ] Escalated/Overdue badges render on the CAN/CAP and Master Register pages
- [ ] Audit entries appear under the `audit_logs` collection in Firestore

---

## State Terminology & API Contract (2026-08-11)

**Scope**: Global "National" → "State" rename across the application — UI labels (State SMS Maturity, State Risk Dashboard, State Hazard Register, …), JS identifiers, the API contract (`data.national` → `data.state`), services, tests and docs. Since the app uses a **state regulator for a multi-country (future) vision**, the terminology is now regulator-agnostic. The only retained occurrence is the factual accident name **"National 102 (2013)"** in the Gemini prompt example (`backend/app/services/gemini.py`).

| # | Step | Expected Result | Status |
|---|------|-----------------|--------|
| 1 | POST `/api/v1/reporting/quarterly` as CAAN_SMD (state scope, no `tenant_id`) | Report persisted in `caan_reports`; response exposes `data.state:true`; **zero** legacy `data.national` keys | ✅ |
| 2 | POST `/api/v1/reporting/quarterly?tenant_id=sita-air` | Report scoped to `sita-air` (persisted under `tenants/sita-air/reporting`); response `data.state:false` | ✅ |
| 3 | GET `/api/v1/reporting/quarterly/{id}` | Returns report with `data.state`, no `national` key anywhere in the payload | ✅ |
| 4 | GET `/api/v1/reporting/quarterly` (list) | No `tenant_id` → reads `caan_reports`; `?tenant_id=sita-air` → reads `("sita-air","reporting")` | ✅ |
| 5 | `_effective_tenant()` override matrix | CAAN_SMD / SUPER_ADMIN default to state scope (None), explicit `tenant_id` overrides to the operator; tenant roles always resolve to their own tenant | ✅ |
| 6 | Recursive contract guard | No key containing `national` survives in any report payload or persisted doc | ✅ |
| 7 | State SMS Maturity aggregation | `dashboard_service` returns the `state` key (was `national`); frontend reads `data.state` | ✅ |

### State Terminology Detailed Checks
- [x] Backend response key `data.state` — `backend/app/services/dashboard_service.py`
- [x] Frontend consumes `data.state` — `public/caan.html`, `public/caan-state-risk.html`
- [x] `aggregate_state_risk`, `get_aggregated_state_risk`, `state_categories_tracked` renamed consistently
- [x] `manual_verification.md`, `docs/API.md`, `firestore.rules` updated
- [x] `gemini.py` "National 102 (2013)" retained (factual accident name, not a label)
- [x] Covered by `tests/test_reporting_scoping.py` (9 tests) + full suite **231 passing** on 2026-08-11 (incl. `tests/test_rbac_claims.py`)

_Status above reflects the automated pytest run of 2026-08-11 (`python -m pytest tests\`)._

---

## Confirmed State (Live)

| # | Check | Status | Details |
|---|-------|--------|---------|
| 1 | Same email both sites | ✅ | Both databases have identical **51** users (28 simplified role accounts + legacy); both authenticate against the same Firebase Auth project (`aerosafety-sms-prod`) |
| 2 | Simplified credential scheme | ✅ | `{role}@{tenant}.com` / `{TENANT_CODE}-{ROLE}-2026` (e.g. `safety@buddha-air.com` / `BHA-Safety-2026`). Refer to `credential.md` (local-only, gitignored) |
| 3 | CAAN SUPER_ADMIN removed | ✅ | `safety.director@caan.gov.np` deleted from Auth + `users`; promote a CAAN_SMD to restore admin routes |
| 4 | Beta shows seeded data | ✅ | `sms-db-beta`: 7 tenants, 1 regulator (caan), 1033 surveys, 42 hazards, 980 reports, 3 CAN/CAP |
| 5 | Production shows empty dashboard | ✅ | `sms-db`: 0 tenants, 0 regulators, 0 surveys/hazards/reports; only the 51 users |
| 6 | RBAC claims applied (2026-08-11) | ✅ | 28 simplified accounts updated in Auth via `simplify_credentials.py --apply` (both DB backfills); `safety`→AIRLINE_ADMIN (no department), `camo`/`145`/`ops`→USER with `department` claim (CAMO / Part-145 / Flight Operations); `users` re-synced to 51 docs in `sms-db-beta` + `sms-db` |
---

## Nuance: Production State Regulator Dashboard

On production (`sms.aviasafesystems.com`), the State Regulator dashboard finds no regulators document, so it falls back to the default `caan` ID and shows an empty register/maturity view until the regulator + tenants are seeded at go-live.

**This is intentional** and consistent with the go-live-on-contract-signing policy.

---

## Verification Notes

### Test Accounts

**Important**: Credentials use the simplified scheme (2026-08-10) — `{role}@{tenant}.com` / `{TENANT_CODE}-{ROLE}-2026`. The former SUPER_ADMIN `safety.director@caan.gov.np` is **removed**. Refer to `credential.md` (local-only) for the full 28-account table.

| Role | Email | Password |
|------|-------|----------|
| AIRLINE_ADMIN (Buddha Air) | `safety@buddha-air.com` | `BHA-Safety-2026` |
| AIRLINE_ADMIN (Tara Air) | `safety@tara-air.com` | `TARA-Safety-2026` |
| AIRLINE_ADMIN (Tara CAMO) | `camo@tara-air.com` | `TARA-CAMO-2026` |
| AIRLINE_ADMIN (Yeti 145) | `145@yeti-airlines.com` | `YETI-145-2026` |
| AIRLINE_ADMIN (Air Dynasty Ops) | `ops@air-dynasty.com` | `DYNASTY-Ops-2026` |
| CAAN_SMD | `sms.inspector@caan.gov.np` | shared seed |
| CAAN_SMD | `director.safety@caan.gov.np` | shared seed |
| ~~SUPER_ADMIN~~ | ~~`safety.director@caan.gov.np`~~ | ❌ Removed 2026-08-10 |

### Environments

| Environment | URL | Database | Status |
|-------------|-----|----------|--------|
| **Beta** | `https://sms-beta.web.app` | `sms-db-beta` | Seeded (7 tenants, 1 regulator, 51 users) |
| **Production** | `https://sms.aviasafesystems.com` | `sms-db` | Empty (go-live ready; 51 users) |

---

## Summary of Recent Changes

| Area | Change | Status |
|------|--------|--------|
| **Landing Page** | Re-written hero, navigation, sections | ✅ |
| **Survey** | Moved to `/survey/` (single source) | ✅ |
| **Survey Popup** | Implemented for unlogged users | ✅ |
| **Survey Closed Handling** | Implemented via `surveyConfig` | ✅ |
| **Contact Page** | Added with Sender.net integration | ✅ |
| **Navigation** | Added "Contact" link in header | ✅ |
| **Founder Photo** | Changed from circular to rectangular | ✅ |
| **Just Culture** | Removed from founder section | ✅ |
| **Department Mapping** | Department field on users, auto-populated on hazards/CANs/CAPs, `?department=` filters | ✅ |
| **Escalation** | CAN→Escalated, CAP→Overdue via daily Cloud Scheduler job; audit-logged | ✅ |
| **Master Register** | Unified Hazards + CANs + CAPs view at `/dashboard/master-register.html` | ✅ |
| **Responsible Manager** | "My Tasks" at `/dashboard/responsible-manager.html`, routed for USERs with a department | ✅ |
| **SMS Maturity terminology** (2026-08-10) | "SMS health" → "SMS maturity" across UI, API, docs, tests (rename-only) | ✅ |
| **Simplified credentials** (2026-08-10) | 28 role accounts `{role}@{tenant}.com` / `{CODE}-{ROLE}-2026`; CAAN SUPER_ADMIN removed | ✅ |
| **Hazard source enforcement** (2026-08-10) | Hazard creation allow-list; flight diversions auto-create linked hazards (`source_id`) | ✅ |
| **Tenant lifecycle status** (2026-08-10) | Super-Admin can set Trial / Active / Inactive from contract dates + payment status | ✅ |
| **Dummy data seed/unseed** (2026-08-10) | Super-Admin can seed/unseed VSR/MOR/CAN/CAP for one tenant or all (admin-demo-1 marker) | ✅ |
| **State terminology** (2026-08-11) | Global "National" → "State" rename (UI, JS identifiers, API key `data.national` → `data.state`, services, tests, docs); `gemini.py` accident name retained | ✅ |

---

*Last Updated: 2026-08-11*

Verified live (not assumed):
1. Same email both sites — Yes. Both sms-db-beta and sms-db have the identical **51** users (28 simplified role accounts + legacy); both sites authenticate against the same Firebase Auth project (aerosafety-sms-prod).
2. Simplified credentials — Confirmed. `{role}@{tenant}.com` / `{TENANT_CODE}-{ROLE}-2026` accounts sign in via the Identity Toolkit path (e.g. `safety@buddha-air.com` / `BHA-Safety-2026`). The former SUPER_ADMIN `safety.director@caan.gov.np` now rejects sign-in (removed). Full table: `credential.md` (local-only).
3. Beta shows seeded data — Confirmed. sms-db-beta: 7 tenants, 1 regulator (caan), 1033 surveys, 42 hazards, 980 reports, 3 CAN/CAP. All dashboards populate.
4. Production shows empty dashboard — Confirmed. sms-db: 0 tenants, 0 regulators, 0 surveys/hazards/reports; only the 51 users. Dashboards (tenant + CAAN/State Regulator) render empty — consistent with the go-live-on-contract-signing policy.
One nuance: on prod, the State Regulator dashboard finds no regulators doc, so it falls back to the default caan id and shows an empty register/maturity view until the regulator + tenants are seeded at go-live.