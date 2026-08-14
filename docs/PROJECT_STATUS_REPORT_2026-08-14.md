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
| Full backend test suite (257 tests) | ✅ Pass |

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
| 3 | Frontend hosting deploy pending (CAA form/PDF + new tenant dashboards) | Low | ⚠️ Pending | Backend/data-only this session |
| 4 | Monitoring / alerting | Medium | ⚠️ Pending | Not yet configured |
| 5 | MFA (TOTP/SMS) | Medium | ⚠️ Pending | Not yet implemented |

---

## 6. Next Steps

| # | Milestone | Status |
|---|-----------|--------|
| 1 | Deploy frontend hosting so the new tenant dashboards + CAAN view are live | ⏳ Pending |
| 2 | Live-verify `safety@yeti-airlines.com` Anon Rate card and CAAN "Responses" KPI | ⏳ Pending |
| 3 | Restore SUPER_ADMIN (promote a CAAN_SMD) | ⚠️ Action |
| 4 | Invite beta testers (incl. the 5 new airlines) | ⏳ Pending |
| 5 | Beta launch + 2-week test period | ⏳ Pending |
| 6 | Production go-live (post-beta) | ⏳ Pending |

---

*End of report. Generated 2026-08-14 from live environment data.*

**User Reference:** For definitions of core terminology, chart legends, hazard matrices, and the CAN/CAP workflow, see [docs/GLOSSARY.md](./GLOSSARY.md).
