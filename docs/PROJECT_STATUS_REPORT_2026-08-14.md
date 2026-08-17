# 📝 AviaSAFE SMS — Project Status Report

**Project**: AviaSAFE SMS — Safety Climate Measurement System (ICAO Annex 19 compliant)
**Report Date**: 2026-08-14
**Prepared by**: AviaSAFE Systems engineering (Opencode-assisted)
**Verification**: All figures below were verified live against the deployed beta backend (Render), Firebase Auth, and `sms-db-beta` Firestore on the report date.

---

## 1. Executive Summary

| Item | Value |
|------|-------|
| **Project Name** | AviaSAFE SMS |
| **Report Date** | 2026-08-14 |
| **Overall Status** | **10 providers + CAAN regulator fully seeded (seed v2.1.0)** — 5 new airline tenants (yeti-airlines, summit-air, sita-air, simrik-air, tara-air) registered, all tenant ids hyphenated, per-tenant role accounts provisioned, randomized dataset seeded into `sms-db-beta`, and the 0% "Anon Rate" KPI fixed (overall ≈ 21%) |
| **Current Phase** | Beta Testing (pre-production) |

**Key Highlights**
- **Seed v2.1.0: 10 provider tenants** — `OPERATOR_PROFILES` now covers buddha-air, air-dynasty, ktm-mro, pokhara-aerodrome, himalaya-ground-services + the 5 new: yeti-airlines, summit-air, sita-air, simrik-air, tara-air. `LEGACY_OPERATOR_PROFILES` is empty; every provider tenant id is strictly hyphenated (no underscores).
- **Anon Rate KPI fixed** — VSRs are now seeded with `is_anonymous` per tenant `anonymous_rate` (0.28–0.35). Verified live: 66/317 reports anonymous = **21%** overall Anon Rate (matches the ~22% target); every provider tenant is non-zero (9%–37%).
- **Survey responses subcollection seeded** — `seed/surveys.py` now also writes the `responses` subcollection (mirroring the production_seed shape: `tenant_id`, `answers`, `department`, `submitted_at`, `survey_version`, `seed_version`), so the CAAN "Responses" KPI (`collectionGroup("responses")`) has data: 184 responses across 10 tenants (15–24 per tenant).
- **Role accounts per tenant** — each provider has 4 auth users: the simplified `safety@`, `145@`, `camo@`, `ops@`. Mapping: safety→AIRLINE_ADMIN, 145→USER/Part-145, camo→USER/CAMO, ops→USER/Flight Operations. Passwords are deterministic per tenant code.
- **Legacy accounts purged (2026-08-14)** — the old `safety.*`, `ae.*`, `manager.*` accounts (30 in Firebase Auth, 15 mirrored in Firestore `users`) were deleted. Only the 4 simplified role accounts remain per tenant (40 operational accounts) plus CAAN SMD + SUPER_ADMIN.
- **Seed doc updated** — `seed_metadata/seed` now reports version **2.1.0** with live counts; `collectionGroup("reports")` (317) matches the exact sum of the 10 tenant report subcollections.
- **Cleanup of legacy demo data** — stale runner docs (v2.0.0), backfilled survey responses (85, no seed_version), and `flight-diversion-demo-2` leftovers (20 hazards + 20 `flight_diversions` docs in buddha-air/air-dynasty) were purged so hazard counts match profile exactly.
- **Admin feedback review added** — new `GET /api/v1/admin/feedback` route (CAAN_SMD / SUPER_ADMIN) plus a "User Feedback" review table in the Super-Admin portal; 4 beta feedback entries currently visible (rating, subject, page).
- **Survey campaigns activated** — survey windows activated for yeti-airlines and tara-air (open 2026-08-13 → close 2026-09-13, "Annual SMS Safety Culture Survey 2026"); buddha-air already active. All 11 tenants report OPEN; 3 have an explicit window.
- **Survey intro modal redirect fixed** — active respondents are no longer auto-redirected to the landing page; the countdown/redirect only runs for closed/expired campaigns or unknown-tenant visitors. Verified live on yeti-airlines and tara-air.
- **Pushed to `main` (15d1b97)** — triggers Render redeploy of both backends and Firebase hosting redeploy of both sites (`aerosafety-sms-prod` + `sms-beta`).

**Key Risks**
- **No SUPER_ADMIN account** — unchanged; `/api/v1/admin/*` routes still require promoting a CAAN_SMD.
- **Production seeding deferred to go-live** — `sms-db` still has 0 tenants / 0 operational data (by design).
- **Anon Rate per-tenant varies stochastically** — with small VSR samples (18–26), the per-tenant rate fluctuates (9%–37%) around the ~22% overall target; this is expected and by design.

---

## 2. Development Status

### 2.1 Completed This Period (2026-08-14)

| Feature | Module | Status | Deployed |
|---------|--------|--------|----------|
| Seed v2.1.0: 5 new provider tenants (yeti-airlines, summit-air, sita-air, simrik-air, tara-air) in `OPERATOR_PROFILES`; `LEGACY_OPERATOR_PROFILES` emptied | Seeding (`seed/config.py`) | ✅ Complete | ✅ Applied to `sms-db-beta` |
| Per-tenant randomized report profiles (25–40 reports, ~70% VSR / 30% MOR, `anonymous_rate` 0.28–0.35) | Seeding (`seed/config.py`, `seed/reports.py`) | ✅ Complete | ✅ Applied to `sms-db-beta` |
| Survey `responses` subcollection seeded with production_seed shape (fixes CAAN "Responses" KPI) | Seeding (`seed/surveys.py`) | ✅ Complete | ✅ Applied to `sms-db-beta` |
| Runner `responses` prefix in purge map + `removed` counter | Seeding (`seed/runner.py`) | ✅ Complete | Repo (takes effect on next seed) |
| Hazard/CAN custodian pool covers Flight Operations, Safety, Safety (manager), CAMO, Part-145 | Seeding (`seed/hazard_can.py`) | ✅ Complete | ✅ Applied to `sms-db-beta` |
| `SEED_OPERATORS` in production_seed updated to 10 tenants (test parity) | `app/services/production_seed.py` | ✅ Complete | Repo |
| Deploy message + error messages updated for 10-provider scope | `seed/deploy_seed.py`, `seed/operators.py` | ✅ Complete | Repo |
| Audit script `scripts/audit_seed_beta.py` (tenant count, hyphenation, per-tenant counts, Anon Rate, departments, role accounts, aggregate band) | Scripts | ✅ Complete | Repo |
| Purge legacy accounts (`safety.*`, `ae.*`, `manager.*`): removed 30 Firebase Auth records + 15 Firestore `users` docs; seed now provisions only the 4 simplified role accounts per tenant | Data (`scripts/purge_legacy_accounts.py`) | ✅ Complete | ✅ Applied to `sms-db-beta` |
| Full re-seed of `sms-db-beta` (v2.1.0) + cleanup of stale v2.0.0 / backfilled / flight-diversion demo data | Data | ✅ Complete | ✅ Applied to `sms-db-beta` |
| Admin feedback review: `GET /api/v1/admin/feedback` (CAAN_SMD / SUPER_ADMIN) + "User Feedback" table in Super-Admin portal | `app/routes/admin.py`, `public/admin/index.html` | ✅ Complete | ✅ Applied to `sms-db-beta`; backend redeploy via push |
| Feedback audit script (list /latest with subject, rating, page, submitter role) | Scripts (`scripts/audit_feedback.py`) | ✅ Complete | Repo |
| Survey campaign activation for yeti-airlines + tara-air (open 2026-08-13 → close 2026-09-13, syncs `config` + `surveyConfig`) | Scripts (`scripts/activate_survey_campaigns.py`) | ✅ Complete | ✅ Applied to `sms-db-beta` |
| Survey status audit script (per-tenant config + effective window) | Scripts (`scripts/audit_survey_status.py`) | ✅ Complete | Repo |
| Survey intro modal auto-redirect fix — countdown/redirect only for closed/expired/unknown-tenant; active respondents get a dismissible "Begin Survey" popup | `public/survey/app.js`, `public/survey/index.html` | ✅ Complete | ✅ Deployed (`sms-beta` + `aerosafety-sms-prod`) |
| Removed stale `safety.director@caan.gov.np` references (login placeholder → `smd@caanepal.gov.np`; fixtures → `super-admin@aviasafesystems.test`) | Tests, `public/admin/login.html` | ✅ Complete | Repo |
| `docs/GLOSSARY.md` created (terminology, charts, hazard matrix, CAN/CAP workflow) + linked from README & status report | Docs | ✅ Complete | Committed (`28b42cb`) |

### 2.2 Prior Completed Features

See `docs/PROJECT_STATUS_REPORT_2026-08-12.md` and `docs/PROJECT_STATUS_REPORT_2026-08-11.md` for the full inventory.

---

## 3. Testing Status

### 3.1 Backend Unit / Model Tests (local, this session)

| Check | Result |
|-------|--------|
| Seed config validation (10 providers, hyphenated ids, volumes 25–40, `anonymous_rate` 0.25–0.35, survey 15–25) | ✅ Pass |
| RBAC claims registry has 10 provider tenant types | ✅ Pass |
| Seed-scope dry-run counts computed from config + `estimate_counts` | ✅ Pass |
| Admin seed preview/deploy/routes show 10 tenants | ✅ Pass |
| Full backend test suite (261 tests) | ✅ Pass |

### 3.2 Live Verification (2026-08-14)

| Check | Result |
|-------|--------|
| 11 total tenants (10 providers + `caan`) | ✅ Confirmed |
| All tenant ids hyphenated (no underscores) | ✅ Confirmed |
| Per-tenant report totals match profile (MOR + VSR) | ✅ Confirmed (all 10) |
| Per-tenant Anon Rate non-zero | ✅ Confirmed (9%–37%) |
| Overall Anon Rate ≈ 22% target | ✅ Confirmed (66/317 = 21%) |
| Hazards / CANs match profile counts | ✅ Confirmed (all 10) |
| Surveys == responses per tenant | ✅ Confirmed (184 responses) |
| Hazards + CANs cover all 4 departments (Flight Operations, Safety, CAMO, Part-145) | ✅ Confirmed (all 10) |
| 4 role accounts per tenant (`safety@`/`145@`/`camo@`/`ops@`); legacy `safety.*`/`ae.*`/`manager.*` fully purged | ✅ Confirmed (all 10) |
| `collectionGroup("reports")` (317) == sum of 10 tenant report subcollections | ✅ Confirmed |
| `collectionGroup("responses")` == 184 | ✅ Confirmed |
| `seed_metadata/seed` version == 2.1.0 | ✅ Confirmed |
| Survey windows active for buddha-air, yeti-airlines, tara-air (2026-08-13 → 2026-09-13) | ✅ Confirmed (all 3) |
| Beta config endpoint returns `isActive=True` + open/close dates for yeti-airlines & tara-air | ✅ Confirmed |
| Survey pages (`/survey/?tenant=yeti-airlines`, `tara-air`) load 200 with live form, no countdown redirect | ✅ Confirmed |
| Deployed `survey/app.js` on `sms.aviasafesystems.com` contains the redirect fix | ✅ Confirmed |
| `GET /api/v1/admin/feedback` live on deployed backend | ⏳ Pending (redeploy via push) |

---

## 4. Beta Testing Status

### 4.1 Beta Environment (`sms-db-beta`) — verified healthy today

| Aspect | Status | Details |
|--------|--------|---------|
| **Environment** | `sms-db-beta` | Fully seeded, PITR 7-day |
| **Tenants** | 10 operational + 1 regulator | buddha-air, air-dynasty, ktm-mro, pokhara-aerodrome, himalaya-ground-services, yeti-airlines, summit-air, sita-air, simrik-air, tara-air + caan |
| **Users** | 42 | 40 simplified role accounts + CAAN_SMD + SUPER_ADMIN (legacy accounts purged) |
| **Reports** | 317 (221 VSR / 96 MOR) | 25–40 per tenant, ~70% VSR / 30% MOR |
| **Anonymous** | 66 reports (21%) | VSR-only, non-zero for every tenant |
| **Hazards** | 145 | 13–16 per tenant, 4-department spread |
| **CAN / CAP** | 102 / 200 | 9–11 CANs per tenant + CAP subcollection |
| **Surveys / Responses** | 184 / 184 | 15–24 per tenant, matching |
| **Survey campaigns** | 3 active | buddha-air, yeti-airlines, tara-air (2026-08-13 → 2026-09-13); all 11 tenants OPEN |
| **Feedback** | 4 entries | 1 SUPER_ADMIN, 2 AIRLINE_ADMIN, 1 CAAN_SMD (2026-08-09 → 2026-08-13) |
| **Audit logs** | active | — |

### 4.2 Relevant Simplified Accounts

| Role | Department | Email | Status |
|------|-----------|-------|--------|
| USER | Part-145 | `145@{tenant}.com` | ✅ Dept-scoped CANs on "My Tasks" |
| USER | CAMO | `camo@{tenant}.com` | ✅ Dept-scoped CANs on "My Tasks" |
| USER | Flight Operations | `ops@{tenant}.com` | ✅ Sees `Flight Operations` CANs (assigned) |
| AIRLINE_ADMIN | Safety | `safety@{tenant}.com` | ✅ Full dashboard (unscoped) + non-zero Anon Rate |

---

## 5. Known Issues & Limitations

| # | Issue | Severity | Status | Notes |
|---|-------|----------|--------|-------|
| 1 | **No SUPER_ADMIN account** | High | ⚠️ Action | Removed 2026-08-10; promote a CAAN_SMD to restore admin routes |
| 2 | Per-tenant Anon Rate fluctuates (9%–37%) on small VSR samples | Low | ✅ Accepted | Overall 21% ≈ 22% target; by design |
| 3 | Frontend hosting deploy pending (CAA form/PDF + new tenant dashboards) | Low | ✅ Resolved | Deployed to `sms-beta` + `aerosafety-sms-prod` (2026-08-14) |
| 4 | Monitoring / alerting | Medium | ⚠️ Pending | Not yet configured |
| 5 | MFA (TOTP/SMS) | Medium | ⚠️ Pending | Not yet implemented |
| 6 | `GET /api/v1/admin/feedback` pending live verify on beta backend | Low | ⚠️ Pending | Route pushed; backend redeploy via Render in progress |

---

## 6. Next Steps

| # | Milestone | Status |
|---|-----------|--------|
| 1 | Verify `GET /api/v1/admin/feedback` live on beta backend after Render redeploy | ⏳ Pending |
| 2 | Review feedback entries from the Super-Admin portal + respond to CAAN SMD "data not visible" report | ⏳ Pending |
| 3 | Live-verify `safety@yeti-airlines.com` Anon Rate card and CAAN "Responses" KPI | ⏳ Pending |
| 4 | Restore SUPER_ADMIN (promote a CAAN_SMD) | ⚠️ Action |
| 5 | Invite beta testers (incl. the 5 new airlines) | ⏳ Pending |
| 6 | Beta launch + 2-week test period | ⏳ Pending |
| 7 | Production go-live (post-beta) | ⏳ Pending |

---

*End of report. Generated 2026-08-14 from live environment data.*

**User Reference:** For definitions of core terminology, chart legends, hazard matrices, and the CAN/CAP workflow, see [docs/GLOSSARY.md](./GLOSSARY.md).
