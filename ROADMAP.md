# Roadmap

Current-state roadmap for the AviaSAFE SMS Platform. Supersedes the earlier "Safety-Health" roadmap
(Supabase/Netlify era). The authoritative status source is
[docs/archive/PROJECT_STATUS_REPORT_05AUG2026.md](./docs/archive/PROJECT_STATUS_REPORT_05AUG2026.md);
the latest dated report is [docs/PROJECT_STATUS_REPORT_2026-08-24.md](./docs/PROJECT_STATUS_REPORT_2026-08-24.md).

## Delivery Notes

> The 12-month demo seed is **synthetic**. It provides a populated demo experience at delivery but is
> **not** a substitute for real customer data. Customers must import their **Master Logsheet** via
> Phase 2B to make the platform authoritative for their operation. Disclose this clearly in the
> delivery scope email.

## Single-Path User Provisioning (Policy — Implemented 2026-09-14)

**Users are always created via Step 3.** There is exactly one way to provision a tenant user:
Production Setup Step 3 (`POST /api/v1/admin/users`, one user at a time).

- The tenant onboarding wizard (`public/admin/tenant-credentials.html`) no longer creates users — it
  is a 5-step tenant-only flow (Tenant Info → Contact → Contract → Review → Done).
- `POST /api/v1/admin/tenants` (`admin_create_tenant`) creates the tenant only; the legacy
  `if data.get("users")` branch was removed.
- `create_tenant_with_credentials` (batch tenant+users) was removed on 2026-09-17
  (see `PASSWORD_RESET_BUG_INVESTIGATION.md`); it no longer exists in the codebase.
- Rationale: a single path is easier to test, monitor, and trust, and matches the real customer
  workflow (create the tenant, then add users one at a time after hand-over).

## Milestones Reached

| Phase | Status | Notes |
|---|---|---|
| **Feature Development** | ✅ 100% | Survey, VSR/MOR, AI suggestions, dashboards, roles, CAN/CAP, verification, diversions, quarterly/annual reports + PDF |
| **RC-1 — Security Hardening** | ✅ COMPLETE | Env-only secrets, admin auth, debug endpoints closed, fail-closed provisioning |
| **RC-2 — Functional Corrections** | ✅ COMPLETE | Unified risk matrix (5/9/15), thresholds plumbed |
| **RC-3 — Documentation & Operational Readiness** | ✅ COMPLETE | GLOSSARY.md, tenant-guide steps 02/03, deploy docs, seed v2.1.0 (10 providers + CAAN), legacy purge, audit tooling, admin feedback review, survey campaign windows |
| **SRA & RCA Analysis Toolkit** | ✅ COMPLETE | 5x5 Safety Risk Assessment matrix, 6-category Fishbone root-cause analysis, 1:1 action-item linkage to CANs (2026-08-16) |
| **Tenant Operational Profiles** | ✅ COMPLETE | Constraint-based demo seeder (fleet, base hub, authorized destinations, hazard domains) + 5 demo reference profiles (2026-08-17) |
| **Multi-tenant Routing & Demo Switcher** | ✅ COMPLETE | Subdomain→tenant resolver, conditional demo persona switcher, email→department mapping (2026-08-17) |
| **Latency Baseline & Local Demo Environment** | ✅ COMPLETE | `[PERF]` request instrumentation (pending Render push), root-cause analysis (cold starts / unfiltered Firestore scans / AI timeouts), one-click local Docker demo targeting `sms-db` (2026-08-24) |

## Remaining Release-Candidate Phases

- **RC-4 — Charter Re-alignment & Compliance Audit:** Survey is now aligned to the 4 ICAO
  components / 12 elements with a backend scoring endpoint (survey v3.0.0); remaining work is a
  formal compliance audit of the 12-element mapping, the live SMS Maturity dashboard output, and any
  residual functional inaccuracies.
- **RC-5 — Platform Hygiene & Tooling:** remove `public/portal` mock code (TD-7), prune dead code
  (TD-11/TD-13 leftovers), CI (lint + pytest + deploy), single `render.yaml` (TD-8), align
  Firestore indexes (TD-10).
- **RC-6 — Pre-Production / Pilot:** App Check server-side enforcement (TD-12), MFA, backups/PITR,
  audit trail, staging environment, penetration/security review.

## Phase 1 — Nav Overhaul (Backlog, Scheduled Post-Pilot)

Role-specific navigation, recorded 2026-09-13 from FIX 5 Phase 1D findings (145@ / sita-air walkthrough).
Not blocking pilot delivery; announced to customers as "coming in the next release."

### Current state
- `shell.js` groups are role-gated at the group level only.
- No item-level gating.
- No distinct nav per role.
- Home links to `safety.html` regardless of role.

### Observed impact (145@ walkthrough)
- DEPT_ADMIN sees **Hazard Management** and **Reporting** — not their job.
- Home from DEPT_ADMIN links to `safety.html` — inaccessible (403).
- Corrective Actions shows **Issue CAN** and **Master Register** — write actions not meant for DEPT_ADMIN.
- AE sees the same nav as the Safety Manager.

### Target state
- Each role has a purpose-built nav (see matrix below).
- Group-level **and** item-level gating.
- Role-aware Home destination:
  - SAFETY → `/safety.html`
  - AE → `/dashboard/ae-dashboard.html`
  - DEPT_ADMIN → `/dashboard/my-tasks.html`
  - CAAN_SMD → `/caan.html`
  - SUPER_ADMIN → `/admin/production-setup.html`

### Role visibility matrix

| Group              | SAFETY | AE        | DEPT_ADMIN | CAAN | SUPER |
|--------------------|--------|-----------|------------|------|-------|
| Dashboard          | ✅     | ✅        | ✅         | ✅   | ✅    |
| Reporting          | ✅     | ❌        | ❌         | ❌   | ✅    |
| Hazard Management  | ✅     | Read-only | ❌         | ❌   | ✅    |
| Risk Assessment    | ✅     | Read-only | ❌         | ❌   | ✅    |
| Corrective Actions | ✅     | Read-only | ✅ dept    | ❌   | ✅    |
| SMS Health         | ✅     | ✅        | ❌         | ✅   | ✅    |
| State Oversight    | ❌     | ❌        | ❌         | ✅   | ✅    |
| Administration     | ✅     | Conditional| ❌         | ❌   | ✅    |

### Implementation
- `NAV_CONFIG` schema extended:
  ```js
  { group, items, visibleTo: ['ROLE1','ROLE2'],
    itemOverrides: { itemId: { visibleTo: [...],
                               readOnly: bool } } }
  ```
- `shell.js` renders per role at login.
- Home destination resolved via `getHomeDestination(role)`.
- Tests cover the matrix.

### Summary decisions
| Item | Decision |
|---|---|
| Reporting group | ❌ Hidden for DEPT_ADMIN (145@) |
| Hazard Management | ❌ Hidden for DEPT_ADMIN (145@) |
| Home destination | Role-aware — DEPT_ADMIN (145@) → `my-tasks.html` |
| Corrective Actions submenu | Refined for DEPT_ADMIN (My Tasks, CAN Register, CAP Register) |
| Issue CAN | Hidden for DEPT_ADMIN (145@) |
| Master Register | Hidden or read-only for DEPT_ADMIN (145@) |
| AE navigation | Distinct AE nav (no longer identical to Safety Manager) |
| Full nav spec | Role-by-role matrix above |
| Backlog | Phase 1 Nav Overhaul |
| Pilot impact | Not blocking — scheduled for post-pilot |

## Phase 1 — Remove `tenant.data.users` Array (Backlog)

Priority: **Medium** — after the delivery stabilizes. Recorded 2026-09-13.

### Context
The tenant row carries a JSONB `users` array (inside the `data` column, `tenants.data->users`) that
duplicates the `users` table. It is a Firestore-era denormalization that survived the migration.

### Impact
- Two sources of truth for user-tenant membership.
- Delete/create paths must update both or drift (today's bug — a delete removed Auth + PG but not
  the array; the re-create refused on the stale array entry).
- Any future user mutation is a candidate for the same class of bug.

### Work
1. Grep for all reads of `tenant.data.users` (backend + frontend).
2. Redirect every read to the `users` table:
   ```sql
   SELECT u.* FROM users u
   JOIN tenants t ON u.tenant_id = t.id
   WHERE t.slug = ?
   ```
3. Stop writing to the array on user create/delete.
4. After a full verification cycle with no writes to the array, drop the `users` key from the
   `data` JSONB (migration).
5. Update models and schemas.

### Effort
~2 days — one source of truth for user-tenant membership; prevents this class of bug permanently.

## Phase 1 — Setup Key Hardening: Server-Issued Short-Lived Tokens (Backlog)

Priority: **HIGH** (Phase 1, foundation). Recorded 2026-09-13. Quick hardening (client idle
timeout for the `sessionStorage` setup key) is shipped in `public/js/admin.js`; this item removes
the static `SETUP_SECRET` from the browser entirely.

### Objective
Eliminate client-side retention of the static setup key. The key is never sent to the browser, so
an XSS or a compromised browser cannot exfiltrate it — the exposure window becomes zero.

### Design
- New `POST /api/v1/admin/setup-token` mints a **15-minute signed token**.
- Exchange the raw `SETUP_SECRET` for the token **exactly once** (SUPER_ADMIN token + setup key
  still required at mint time).
- All ~40 privileged endpoints validate the token instead of the raw key.
- Frontend stores **only the token** (sessionStorage, with the idle timeout already in place).
- Token auto-renews on activity, expires on idle, full teardown on logout.

### Effort
~1–2 days — touches every privileged admin route and page.

## Phase 1 — Welcome Email: Enable Real Delivery (Backlog)

Priority: **Medium** — delivery provider is currently `'none'` (logged, not sent);
new sita-air users received their password only via the one-time on-screen display.
Recorded 2026-09-13.

### Work
1. Configure a real provider (`smtp` / `sendgrid`) for `EMAIL_PROVIDER` in deploy env.
2. Verify `send_welcome_email` path (see `backend/app/services/email_service.py:258`) end-to-end on a stamp user.
3. Fallback UX: if delivery is `'none'`, the Step-3 create page must surface "email will not be sent".

## Phase 1 — Step 3 Create-User: Copy-Password Button (Backlog)

Priority: **Low** — usability. The 14-char generated password is displayed as plain text and must be
hand-typed; a prior incident was traced to a hand-transcription error. Recorded 2026-09-13.

### Work
1. Clipboard API button beside the password on `step3-manage.html` with a visual "copied" confirmation.
2. Keep the one-time display; add a "reveal" toggle if hidden.

## Phase 1 — CI Pipeline: Regression Test Automation (Backlog)

Priority: **MEDIUM** — foundation, not blocking pilot delivery. Recorded 2026-09-13.

### Objective
Run the test suite automatically on every push to `main` and on every PR.

### Design decisions to settle in Phase 1
- **Runner**: GitHub Actions vs Render pre-deploy vs self-hosted.
- **Secrets strategy**: inject the Firebase service account + web API key into the runner
  securely, without committing them to the repo.
- **Live-tests strategy**: keep live-Auth/live-DB tests (e.g. `tests/test_admin_user_password.py`)
  gated behind an explicit env flag so faked tests stay fast and deterministic; live tests run
  only in a trusted environment.
- **Flake policy**: quarantine known-flaky, state-dependent tests so they never block deploys.

### Effort
~1–2 days. The regression test (`tests/test_admin_user_password.py`) already runs locally and
must be run before each commit / milestone until this pipeline exists.

## Phase 1 — Survey Hostname Mapping (Backlog)

Priority: **Low**. Recovered 2026-09-13 from a stale session file. `public/survey/app.js` `routes`
currently maps only `sita-air`, `nepal-airlines`, `caan-ops`.

### Decision to make
- (a) Add new tenant subdomains to the map as they onboard, or
- (b) Standardize on `?tenant=` query params for all surveys.

### Trigger
A tenant outside the current map is onboarded.

### Effort
~1 hour.

## Phase 1 — Repo Hygiene: No Snapshot Files (Convention)

Working-session artifacts (todos snapshots, session logs, chat exports) must **not** be committed to
the repo. Actionable items recovered from such files go into ROADMAP.md; the source files are
deleted after extraction. Recorded 2026-09-13 (artifacts recovered from
`sms360x/sms-aviasafesystems-main-downloaded/todos.md` before folder deletion).

## Phase 3 — Per-Employee Survey Issuance (Enhancement)

Employee-scoped collection with unique per-employee links or `respondentId`, built on top of the
existing tenant-keyed storage. Enables per-employee analytics. **Not required for the pilot.**
Recovered 2026-09-13 from a stale session file.

## Phase 2A — AE Dashboard Redesign

Dependency for Phase 2B. Details TBD (separate backlog item; recorded 2026-09-13).

## Phase 2B — Historical Import (Excel / CSV)

Priority: HIGH — this is the "move from Excel" feature. Recorded 2026-09-13.

### Objective
Let the Safety Manager upload the customer's Master Logsheet (and related sheets) so the
platform contains **real** safety data, not synthetic seed data.

### Deliverables
- Import UI (card on `safety.html` dashboard, leading to `/import/index.html`)
- Sheet-type detection: Master logsheet, Occurrence, Safety Deficiencies, Hazard log,
  Flight diversions, Risk register
- Column-mapping UI (CSV column → platform field)
- Validation (dates, ADREP codes, required fields)
- Dry-run mode (validate only, no writes)
- Import modes: append / replace / skip-duplicates
- Audit-logged (who imported what, when)
- Per-tenant scoping (a tenant imports only its own data)

### Explicit non-goals
- CAN/CAP import (the customer's Excel has no structured CAN/CAP data — these are platform
  outputs, generated going forward)
- Automatic derivation of hazards from VSR/MOR (Phase 3 — Dynamic Barrier Integrity)

### Post-import outcome
- Tenant's hazards, reports, diversions loaded
- CAN/CAP registers start at zero
- From go-live, the platform becomes authoritative
- Leading and lagging indicators compute from real data

### Cross-reference
- Depends on Phase 2A (AE dashboard redesign) being complete
- Feeds Phase 3 (Safety Intelligence) — statistical indicators need real data, not synthetic

## Product Roadmap (post-pilot, charter-gated)

Per the [Product Charter](./docs/archive/PROJECT_CHARTER.md), feature expansion requires explicit approval.
Candidate product work (not committed):

- Monitoring / alerting for SMS maturity thresholds.
- Notifications service (email/portal).
- AI assistant enhancements (evaluation set, per-tenant prompt tuning).
- State-of-the-System reports and SSP effectiveness reporting automation.

*Nothing here is scheduled without approval.*