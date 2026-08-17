# 📝 AviaSAFE SMS — Project Status Report

**Project**: AviaSAFE SMS — Safety Climate Measurement System (ICAO Annex 19 compliant)
**Report Date**: 2026-08-17
**Prepared by**: AviaSAFE Systems engineering (Opencode-assisted)
**Verification**: All figures below were verified against the committed codebase (HEAD `381db76`), the
backend test suite (280 passed), the frontend Node test suite, and the live beta environment on the
report date.

---

## 1. Executive Summary

| Item | Value |
|------|-------|
| **Project Name** | AviaSAFE SMS |
| **Report Date** | 2026-08-17 |
| **Overall Status** | **Analysis toolkit + demo realism overhaul complete** — 5x5 SRA matrix, 6-category Fishbone RCA, and 1:1 action-item linkage shipped; tenant operational profiles + constraint-based seeder added; subdomain tenant resolver + conditional demo persona switcher + email→department mapping live. Backend suite: **280 tests passing** |
| **Current Phase** | Beta Testing (pre-production) — RC-3 complete; RC-4/5/6 remain |

**Key Highlights**
- **SRA & RCA analysis toolkit (8a00d77, 2026-08-16)** — integrated a reusable ICAO 5x5 Safety Risk
  Assessment (SRA) matrix component (`public/js/risk_matrix.js`), a 6-category Fishbone root-cause
  analysis component (`public/js/fishbone.js`), 1:1 CAN↔action-item linkage in the backend
  (`can_cap_service.py`, `routes/can_cap.py`, `models/can_cap.py`), updated CAN/CAP/issue forms +
  A4 print stylesheet, and a dedicated lifecycle test suite (175 lines).
- **Tenant operational profiles + constraint-based seeder (ac41522, 2026-08-17)** — new
  `TenantOperationalProfile` model + a 629-line registry (`seed/tenant_profiles.py`) giving all
  10 providers a realistic operational footprint (category, fleet, base hub, authorized
  destinations, hazard domains); the seeder now enforces fleet / location / occurrence-domain
  constraints so rotor-wing operators never get fixed-wing routes and trunk jets never land at
  mountain STOL strips. 5 demo reference profiles added for the landing/login demo switcher.
- **Multi-tenant routing, demo switcher, department mapping (381db76, 2026-08-17)** —
  `TenantResolver` (`public/js/tenant_context.js`) resolves subdomain→tenant on the login page,
  with a conditional demo persona selector (Fixed-Wing, Rotary, AMO, Airport, ASSD, FSSD) shown
  only in demo environments; `public/js/department_resolver.js` maps email→department (Part-145,
  CAMO, Flight Ops) and `api/client.js` now sends `X-Tenant-Id` + `X-User-Department` headers.
  Frontend Node test suite added (`frontend-tests/tenant-context.test.js`).
- **Seed baseline stable** — `SEED_VERSION` remains **2.1.0** (10 provider tenants + CAAN regulator;
  all ids hyphenated; 40 simplified role accounts + CAAN_SMD + SUPER_ADMIN).

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
| Frontend Node test suite for tenant context + department resolver | `frontend-tests/tenant-context.test.js` | ✅ Complete (214 lines) | Repo |
| Deploy both hosting targets after routing work | `sms-beta` + `aerosafety-sms-prod` (Firebase Hosting) | ✅ Complete | Live |

### 2.2 Prior Completed Features

- **RC-3 (2026-08-14)** — seed v2.1.0 (10 providers + CAAN), survey campaigns (3 active), admin
  feedback review, survey redirect fix, legacy purge, GLOSSARY.md.
- See `docs/PROJECT_STATUS_REPORT_2026-08-14.md` and `docs/PROJECT_STATUS_REPORT_2026-08-12.md`.

---

## 3. Test Verification

### 3.1 Backend Test Suite (2026-08-17)

| Check | Result |
|-------|--------|
| Full backend test suite (280 tests) | ✅ Pass |
| New `test_risk_assessment_lifecycle.py` (SRA matrix, Fishbone, action linkage) | ✅ Pass |
| New `test_seed_beta_config.py` (tenant profiles, constraints, counts) | ✅ Pass |
| Seed-scope dry-run counts computed from config + `estimate_counts` | ✅ Pass |

### 3.2 Frontend Test Suite

| Check | Result |
|-------|--------|
| `frontend-tests/dashboard.test.js` | ✅ Pass |
| `frontend-tests/tenant-context.test.js` (email mapping, demo env detection, subdomain extraction, prod lock, demo toggle, slug prettify, `applyDepartmentContext`) | ✅ Pass |

---

## 4. Beta Testing Status

### 4.1 Beta Environment (`sms-db-beta`)

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
| **Demo profiles** | 5 | air-dynasty-demo, himalaya-airlines-demo, nepal-aero-maintenance-demo, tia-kathmandu-demo, yeti-tara-demo (login persona selector) |
| **Audit logs** | active | — |

> Note: the beta Firestore dataset was last re-seeded at seed v2.1.0 (2026-08-14). The
> constraint-based seeder and profile registry added in this period affect *future* seeds; a
> re-seed to apply profiles to `sms-db-beta` is a recommended next step (see §6).

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
| 3 | Beta Firestore not yet re-seeded with new tenant profiles / constraints | Low | ⚠️ Pending | Seeder changed in ac41522; re-seed `sms-db-beta` to persist profiles |
| 4 | Monitoring / alerting | Medium | ⚠️ Pending | Not yet configured |
| 5 | MFA (TOTP/SMS) | Medium | ⚠️ Pending | Not yet implemented |
| 6 | Survey 12-element mapping compliance audit (RC-4) | Medium | ⚠️ Pending | Survey now 4-component/12-element aligned (v3.0.0); formal audit outstanding |

---

## 6. Next Steps

| # | Milestone | Status |
|---|-----------|--------|
| 1 | Re-seed `sms-db-beta` to apply tenant operational profiles + constraint-based data | ⏳ Pending |
| 2 | Live-verify demo persona switcher + tenant resolver on `sms-beta` / `sms.aviasafesystems.com` | ⏳ Pending |
| 3 | Promote a CAAN_SMD to SUPER_ADMIN to restore admin routes | ⚠️ Action |
| 4 | RC-4: survey 12-element compliance audit + SMS Maturity dashboard output check | ⏳ Pending |
| 5 | RC-5: CI (lint + pytest + deploy), single `render.yaml`, prune `public/portal` mock code | ⏳ Pending |
| 6 | Invite beta testers (incl. the 5 new airlines) | ⏳ Pending |
| 7 | Beta launch + 2-week test period | ⏳ Pending |
| 8 | Production go-live (post-beta) | ⏳ Pending |

---

*End of report. Generated 2026-08-17 from committed code (HEAD `381db76`) + live environment data.*

**User Reference:** For definitions of core terminology, chart legends, hazard matrices, and the CAN/CAP workflow, see [docs/GLOSSARY.md](./GLOSSARY.md).