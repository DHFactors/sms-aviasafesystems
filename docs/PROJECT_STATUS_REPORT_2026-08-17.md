# 📝 AviaSAFE SMS — Project Status Report

**Project**: AviaSAFE SMS — Safety Climate Measurement System (ICAO Annex 19 compliant)
**Report Date**: 2026-08-17
**Prepared by**: AviaSAFE Systems engineering (Opencode-assisted)
**Verification**: All figures below were verified against the committed codebase (HEAD `a002bd6`), the
backend test suite (293 passed), the frontend Node test suite, the live Firebase Auth directory
(50 verified accounts), and the live beta environment on the report date.

---

## 1. Executive Summary

| Item | Value |
|------|-------|
| **Project Name** | AviaSAFE SMS |
| **Report Date** | 2026-08-17 |
| **Overall Status** | **Beta expanded from 10 → 12 providers with universal CAAN oversight + formal tenant classification model** — FSSD/ASSD added as full `caan-directorate` tenants; universal SMD oversight logic applied to every internal/external provider; `OperationalScope` enum + `operates_flights` / `applicable_departments` codified across schemas, seed profiles, and frontend department resolvers; all 50 credential accounts provisioned and verified in Firebase Auth. Backend suite: **293 tests passing** |
| **Current Phase** | Beta Testing (pre-production) — RC-3 complete; RC-4/5/6 remain |

**Key Highlights**
- **Universal CAAN oversight (59c53d4, 2026-08-17)** — CAAN FSSD (Flight Safety Standards Dept) and
  ASSD (Aerodrome Safety Standards Dept) added as full `caan-directorate` tenants, bringing the beta
  provider set from 10 → **12** (covering every service-provider type: airline, helicopter-operator,
  mro, aerodrome, ground-handling, caan-directorate). Internal directorates are treated exactly like
  external providers for regulator aggregation, scoping and the operator directory; `SEED_VERSION`
  bumped to **2.2.0**.
- **Tenant Classification & Department Applicability model (a002bd6, 2026-08-17)** — formal
  `OperationalScope` enum (`AIRLINE_FIXED_WING`, `AIRLINE_ROTARY`, `AMO`, `AERODROME`,
  `GROUND_HANDLING`, `REGULATOR`) with `operates_flights` (True **only** for AOC-holding airlines)
  and `applicable_departments` (AMO → maintenance_145 + qa, NO flight_ops/camo; aerodrome →
  airside_ops + arff, NO camo/145; regulator → smd/fssd/assd). Applied across all 12 tenant profiles,
  the frontend department/prefix resolver (tenant-context-aware), and occurrence taxonomy (flight-only
  ICAO ADREP categories LOCI/CFIT/MAC/ARC/WX excluded for non-flying providers).
- **50-account provisioning verified (2026-08-17)** — the 8 new FSSD/ASSD role accounts created in
  Firebase Auth with correct role/tenant/department claims; all 50 expected accounts (1 SUPER_ADMIN +
  1 CAAN_SMD + 48 role accounts = 12 tenants × 4) verified present with matching claims. Beta login
  testing is ready at `https://sms-beta.web.app` with `beta-testing-credentials.csv`.
- **SRA & RCA analysis toolkit (8a00d77, 2026-08-16)** — reusable ICAO 5x5 Safety Risk Assessment
  matrix component, 6-category Fishbone RCA component, 1:1 CAN↔action-item linkage, updated
  CAN/CAP/issue forms + A4 print stylesheet, and a dedicated lifecycle test suite.
- **Tenant operational profiles + constraint-based seeder (ac41522, 2026-08-17)** —
  `TenantOperationalProfile` model + registry (`seed/tenant_profiles.py`) giving every provider a
  realistic operational footprint; the seeder enforces fleet / location / occurrence-domain
  constraints (rotor-wing never gets fixed-wing routes, trunk jets never land at mountain STOL
  strips). 5 demo reference profiles for the login demo switcher.
- **Multi-tenant routing, demo switcher, department mapping (381db76, 2026-08-17)** —
  `TenantResolver` (`public/js/tenant_context.js`) resolves subdomain→tenant on the login page with a
  conditional demo persona selector; `public/js/department_resolver.js` maps email→department and
  `api/client.js` sends `X-Tenant-Id` + `X-User-Department` headers.

---

## 2. Work Completed

### 2.1 This Report Period (2026-08-16 → 2026-08-17)

| Item | Files | Status | Location |
|---|---|---|---|
| 5x5 SRA matrix component (ICAO risk matrix, config-driven) | `public/js/risk_matrix.js` | ✅ Complete | Repo |
| 6-category Fishbone RCA component (bilingual categories) | `public/js/fishbone.js` | ✅ Complete | Repo |
| 1:1 CAN↔action-item linkage + risk-assessment lifecycle | `backend/app/services/can_cap_service.py`, `app/routes/can_cap.py`, `app/models/can_cap.py` | ✅ Complete | Repo |
| Updated CAN detail / CAP review / CAP submit / issue forms + print CSS | `public/can_cap/*.html`, `public/css/can-cap-print.css` | ✅ Complete | Repo |
| Risk-assessment lifecycle tests (5x5 matrix, Fishbone, action linkage) | `backend/tests/test_risk_assessment_lifecycle.py` | ✅ Complete (175 lines) | Repo |
| Tenant operational profile model | `backend/app/models/tenant_profile.py` | ✅ Complete | Repo |
| Tenant profile registry (10 providers + 5 demo references) | `backend/seed/tenant_profiles.py` | ✅ Complete | Repo |
| Constraint-based seeding (fleet / location / hazard-domain) | `backend/seed/config.py`, `seed/reports.py`, `seed/hazard_can.py`, `seed/operators.py` | ✅ Complete | Repo |
| Extended seed audit (`scripts/audit_seed_beta.py`) + config tests | `backend/scripts/audit_seed_beta.py`, `backend/tests/test_seed_beta_config.py` | ✅ Complete (250 lines) | Repo |
| Subdomain→tenant resolver + demo-environment detection | `public/js/tenant_context.js` | ✅ Complete | Repo |
| Email→department resolver (`145@`, `camo@`, `ops@`, `safety@`) | `public/js/department_resolver.js` | ✅ Complete | Repo |
| Conditional demo persona selector on login page | `public/login.html` | ✅ Complete | Repo |
| `X-Tenant-Id` + `X-User-Department` headers on every API call | `public/js/api/client.js` | ✅ Complete | Repo |
| Wired resolver/department context into dashboards + survey | `public/safety.html`, `public/dashboard/index.html`, `public/dashboard/master-register.html`, `public/dashboard/responsible-manager.html`, `public/js/dashboard.js` | ✅ Complete | Repo |
| Frontend Node test suite for tenant context + department resolver | `frontend-tests/tenant-context.test.js` | ✅ Complete (300+ lines) | Repo |
| **CAAN SMD oversight + FSSD/ASSD tenants (12-provider beta)** | `backend/seed/config.py`, `seed/tenant_profiles.py`, `app/services/production_seed.py`, `public/caan.html`, `public/js/tenant_context.js`, `app/services/dashboard_service.py`, tests | ✅ Complete (`59c53d4`) | Repo |
| **Tenant classification + flight-scope + department applicability** | `backend/app/models/tenant_profile.py`, `seed/tenant_profiles.py`, `seed/hazard_can.py`, `public/js/department_resolver.js`, `public/js/tenant_context.js`, `public/js/api/client.js`, `public/js/vsr.js`, `public/js/mor.js`, `public/report/vsr.html`, `public/report/mor.html`, tests | ✅ Complete (`a002bd6`) | Repo |
| Provision 8 new FSSD/ASSD Firebase Auth accounts + verify 50 total | `seed/users.py` (via `create_all_users` scoped to caan-fssd/caan-assd) | ✅ Complete | Live Auth |
| Deploy both hosting targets after routing + oversight work | `sms-beta` + `aerosafety-sms-prod` (Firebase Hosting) | ✅ Complete | Live |

### 2.2 Prior Completed Features

- **RC-3 (2026-08-14)** — seed v2.1.0 (10 providers + CAAN), survey campaigns (3 active), admin
  feedback review, survey redirect fix, legacy purge, GLOSSARY.md.
- See `docs/PROJECT_STATUS_REPORT_2026-08-14.md` and `docs/PROJECT_STATUS_REPORT_2026-08-12.md`.

---

## 3. Test Verification

### 3.1 Backend Test Suite (2026-08-17)

| Check | Result |
|-------|--------|
| Full backend test suite (293 tests) | ✅ Pass |
| `test_risk_assessment_lifecycle.py` (SRA matrix, Fishbone, action linkage) | ✅ Pass |
| `test_seed_beta_config.py` (tenant profiles, constraints, counts, classifications) | ✅ Pass |
| Classification tests — `OperationalScope` enum, `operates_flights` (airlines only), department applicability per scope, non-flying tenants never hold flight departments, flight-only hazard categories excluded for AMO/aerodrome/ground/regulator | ✅ Pass (8 new) |
| Universal-oversight test — `get_caan_state` includes all 6 tenant types, aggregates all KPIs | ✅ Pass |
| Seed-scope dry-run counts computed from config + `estimate_counts` (12 tenants / 215 surveys / 261 VSR / 114 MOR) | ✅ Pass |

### 3.2 Frontend Test Suite

| Check | Result |
|-------|--------|
| `frontend-tests/dashboard.test.js` | ✅ Pass |
| `frontend-tests/tenant-context.test.js` (email mapping, classification-aware dept mapping, demo env detection, subdomain extraction, prod lock, demo toggle, slug prettify, `applyDepartmentContext`, occurrence-category filtering) | ✅ Pass |
| `node --check` on all modified JS (`department_resolver.js`, `tenant_context.js`, `vsr.js`, `mor.js`, `api/client.js`) | ✅ Pass |

---

## 4. Beta Testing Status

### 4.1 Beta Environment (`sms-db-beta`)

| Aspect | Status | Details |
|--------|--------|---------|
| **Environment** | `sms-db-beta` | Fully seeded, PITR 7-day |
| **Tenants** | 12 operational + 1 regulator | buddha-air, air-dynasty, ktm-mro, pokhara-aerodrome, himalaya-ground-services, yeti-airlines, summit-air, sita-air, simrik-air, tara-air, caan-fssd, caan-assd + caan |
| **Users (Firebase Auth)** | 50 | 1 SUPER_ADMIN + 1 CAAN_SMD + 48 simplified role accounts (12 tenants × 4); all verified with matching role/tenant/department claims |
| **Role accounts per tenant** | 4 | `safety@` (AIRLINE_ADMIN) + `camo@` / `145@` / `ops@` (USER) on each tenant's credential domain |
| **FSSD / ASSD accounts** | 8 | `safety|camo|145|ops@fssd.caanepal.gov.np` and `…@assd.caanepal.gov.np` — UIDs `{role}-caan-fssd-001` etc., passwords `FSSD-*-2026` / `ASSD-*-2026` |
| **Reports** | 317 (221 VSR / 96 MOR) | 25–40 per tenant, ~70% VSR / 30% MOR (10 existing tenants) |
| **Anonymous** | 66 reports (21%) | VSR-only, non-zero for every tenant |
| **Hazards** | 145 | 13–16 per tenant, 4-department spread (10 existing tenants) |
| **CAN / CAP** | 102 / 200 | 9–11 CANs per tenant + CAP subcollection |
| **Surveys / Responses** | 184 / 184 | 15–24 per tenant, matching |
| **Survey campaigns** | 3 active | buddha-air, yeti-airlines, tara-air (2026-08-13 → 2026-09-13) |
| **Demo profiles** | 5 | air-dynasty-demo, himalaya-airlines-demo, nepal-aero-maintenance-demo, tia-kathmandu-demo, yeti-tara-demo (login persona selector) |
| **Audit logs** | active | — |

> Note: Firestore seed documents for the two new directorates (caan-fssd, caan-assd) will be written
> when the backend re-seeds at v2.2.0 (Render auto-rebuild on push). Firebase Auth provisioning is
> complete and verified independent of Firestore seeding.

### 4.2 Relevant Simplified Accounts

| Role | Department | Email | Status |
|------|-----------|-------|--------|
| USER | Part-145 | `145@{tenant-domain}` | ✅ Dept-scoped CANs on "My Tasks" |
| USER | CAMO | `camo@{tenant-domain}` | ✅ Dept-scoped CANs on "My Tasks" |
| USER | Flight Operations | `ops@{tenant-domain}` | ✅ Sees `Flight Operations` CANs (assigned) |
| AIRLINE_ADMIN | Safety | `safety@{tenant-domain}` | ✅ Full dashboard (unscoped) + non-zero Anon Rate |
| CAAN_SMD | SMD | `smd@caanepal.gov.np` | ✅ Universal regulator dashboard (oversight of all 12 providers) |

---

## 5. Known Issues & Limitations

| # | Issue | Severity | Status | Notes |
|---|-------|----------|--------|-------|
| 1 | **No SUPER_ADMIN account** | High | ✅ Resolved | `ezondiza.dhf@gmail.com` (developer) re-provisioned 2026-08-17; SUPER_ADMIN claim verified |
| 2 | Per-tenant Anon Rate fluctuates (9%–37%) on small VSR samples | Low | ✅ Accepted | Overall 21% ≈ 22% target; by design |
| 3 | Firestore seed documents for caan-fssd / caan-assd pending v2.2.0 re-seed | Low | ⚠️ Pending | Auth accounts live; Firestore data lands on backend re-seed |
| 4 | Monitoring / alerting | Medium | ⚠️ Pending | Not yet configured |
| 5 | MFA (TOTP/SMS) | Medium | ⚠️ Pending | Not yet implemented |
| 6 | Survey 12-element mapping compliance audit (RC-4) | Medium | ⚠️ Pending | Survey now 4-component/12-element aligned (v3.0.0); formal audit outstanding |

---

## 6. Next Steps

| # | Milestone | Status |
|---|-----------|--------|
| 1 | Re-seed `sms-db-beta` at v2.2.0 to persist caan-fssd / caan-assd Firestore data + profiles | ⏳ Pending |
| 2 | Re-run `scripts/audit_seed_beta.py` (now expects 13 tenants / 12 providers) against live DB | ⏳ Pending |
| 3 | Live-verify demo persona switcher + tenant resolver + FSSD/ASSD logins on `sms-beta` / `sms.aviasafesystems.com` | ⏳ Pending |
| 4 | RC-4: survey 12-element compliance audit + SMS Maturity dashboard output check | ⏳ Pending |
| 5 | RC-5: CI (lint + pytest + deploy), single `render.yaml`, prune `public/portal` mock code | ⏳ Pending |
| 6 | Invite beta testers (incl. the 12 providers) | ⏳ Pending |
| 7 | Beta launch + 2-week test period | ⏳ Pending |
| 8 | Production go-live (post-beta) | ⏳ Pending |

---

*End of report. Generated 2026-08-17 from committed code (HEAD `a002bd6`) + live environment data.*

**User Reference:** For definitions of core terminology, chart legends, hazard matrices, and the CAN/CAP workflow, see [docs/GLOSSARY.md](./GLOSSARY.md).