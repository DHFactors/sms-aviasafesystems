# AviaSAFE — Project Status & Architecture Report

**Date:** 2026-09-01 · **Release:** Safety Performance Framework — SPI/SPT + N-HRC dashboards · DEMO data platform
**Scope:** Consolidated `sms-db` · DEMO operator platform (4 tenants) · full seeders CLI · SPI/SPT & N-HRC API + dashboards · UAT sweep · Render auto-deploy

---

## 1. Executive Summary

AviaSAFE runs on a **single consolidated database** (`FIREBASE_DATABASE_ID=sms-db`,
project `aerosafety-sms-prod`) with one Render Blueprint deploy. The platform now
ships a **fully seeded DEMO operator environment** alongside the state/regulator
surfaces:

* **4 Firestore tenants**: `fixedwing` (DEMO airline), `rotarywing` (DEMO
  helicopter operator), `demoairport` (DEMO aerodrome), `demostate` (STATE).
* **Seeded operational data (idempotent)** — Postgres (Supabase) holds the
  Hazard/Report/CAN/CAP registers; Firestore holds diversions, PSOE assessments,
  and the SSP (state safety program) reference store:
  * Postgres: **hazards 26, reports 10, cans 6, caps 6** (survey responses 1).
  * Firestore: **tenants 4, flight_diversions 7** (fixedwing 3 · rotarywing 2 ·
    demoairport 2 · demostate 0), **SSP 29** (spis 8 + risk_register 14 + nhrcs 7),
    **PSOE 6** (3 demo assessments + 3 legacy production audits).
  * Seeding is reproducible via a single CLI: `python -m seeders.cli --all`
    (dry-run today: **87 created, 0 skipped, 0 errors**).
* **New safety-performance layer** on the `/api/v1` API:
  * **SPI/SPT** (`/api/v1/spi/*`) — 8 ICAO-compliant Safety Performance
    Indicators (leading + lagging) computed from live registers, with per-tenant
    values/status/trend, state aggregation, and adjustable targets.
  * **N-HRC** (`/api/v1/nhrc/*`) — National High-Risk Category KPI aggregates
    for the 7 ICAO categories (CFIT, LOC-I, MAC, RE, RI, ARC, WS).
  * Operator dashboards `/dashboard/spi-dashboard.html` and
    `/dashboard/nhrc-dashboard.html`, wired into the shell navigation across all
    operator-facing pages.
* **Data source of truth for diversions is Firestore** (`tenants/{tid}/flight_diversions`),
  matching the app's operational `flight_diversion_service`; the Postgres
  `flight_diversions` table is no longer read (deprecated for reads).
* The **pre-UAT verification sweep** is green at the API/data level and the
  current backend is **live on Render** (auto-deploy from `main`,
  commit `82b4cc6`).

## 1a. Recent Work (Aug 2026)

Completed, committed, and deployed in the previous cycle (report of 2026-08-31):

* **Priority 1–6 safety-workflow fixes** — AE banner fix, SDCPS mobile
  hamburger, SDC validate/ingest + universal data query endpoints, report
  generation aligned to the backend contract, survey open/close window
  enforcement, and CAN/CAP email notifications with an overdue-check job.
* **Localhost cleanup** — every `localhost`/`127.0.0.1` runtime reference
  removed across frontend and backend.
* **Unified Super Admin Dashboard** (`/admin/dashboard.html`) — SUPER_ADMIN-gated
  console consolidating Test Portal, Tenant Management, Production Setup,
  Audit Log, and Dummy Data.
* **HFACS catalog to 109 nanocodes** (ACT/PRECOND/SUPER/ORG tiers) wired into
  the hazard-analysis dropdown.
* **PSOE → CAN persistent link** (`psoe_assessment_id`) and the **archived-flag
  fix on reopen** (`VerificationService.reopen_hazard`).

## 1b. Recent Work (Sep 2026)

Completed, committed (`82b4cc6` pushed to `origin/main`), and **live on Render**
(this cycle):

* **Seeding platform (Task 22 / Chunk 7)** — `backend/seeders/` is a full,
  idempotent, dry-run-capable seeding suite: `runner.py` (orchestration +
  summary), `cli.py` (`--all / --module / --unseed / --dry-run`), and eight
  seeders — tenants, hazards, reports, CAN/CAP, PSOE, SSP, diversions, survey
  reference. `seed_manager.bat` convenience wrapper. A tracked Supabase
  migration adds the CAN `psoe_assessment_id` column.
* **N-HRC engine (Task 23)** — `models/nhrc.py`, `services/nhrc_service.py`
  (sync facade over Postgres), `api/v1/nhrc.py` registered under `/api/v1`;
  SSP seeder writes the 7 N-HRC references to Firestore `state/ssp/nhrcs/{code}`.
  Validated: 35 state-risk/N-HRC tests pass.
* **SPI/SPT framework (Task 25)** — `models/spi.py` (SPI, SPITarget,
  SPICalculation), `services/spi_service.py`, `api/v1/spi.py` (7 routes under
  `/api/v1/spi`). Eight SPIs computed from the live registers with
  direction-aware status (`lower_is_better` for diversion/occurrence) and
  calendar-month trend buckets. Safety culture falls back to a deterministic
  demo score when surveys are absent.
* **Dashboards + navigation (Tasks 24/25 UI)** — `nhrc-dashboard.html` and
  `spi-dashboard.html` (with CSS/JS) use the standard `SHELL_CONFIG` + auth-gate
  pattern; N-HRC and SPI/SPT nav items added to all operator-facing pages
  (`safety`, `risk-trends`, `top-hazards`, `administration`, `settings/team`,
  `audits/psoe`, and both dashboards). CAAN/state-facing pages intentionally
  untouched.
* **HFACS JSON correction** — `hfacs_nanocodes.json` had a 5-line `//` comment
  header that broke both `json.load` and the browser `fetch().json()` at
  `hazard-analysis.js:67`; header removed → valid JSON, **109 codes, 0 dupes**.
* **Diversion rate reads Firestore (UAT fix)** — `spi_service.py` now computes
  `diversion_rate` from `tenants/{tid}/flight_diversions` via
  `FlightDiversionService` (state view aggregates minus `demostate`). The
  Postgres `flight_diversions` query was removed. Verified through the live
  API: fixedwing **3.0** · rotarywing **2.0** · demoairport **2.0** ·
  demostate **0.0** · state **7.0**.
* **Pre-UAT verification sweep** — services import cleanly, seeders report
  **87 created / 0 errors**, DB counts match the target exactly, HFACS 109
  loads, navigation present with no duplicates, and all API routes respond 200.
  Live endpoints previously 404 (`/api/v1/nhrc/*`, `/api/v1/spi/*`) are now
  green after the Render **auto-deploy** from `main`.

## 2. System Architecture

```
Westin-prefix role routing (live accounts, email ⇒ role ⇒ surface)
    safety@…  → Safety Manager (AIRLINE_ADMIN)      → /safety.html
    ops@…     → Flight Operations (USER)            → /dashboard/responsible-manager.html
    smd@…     → CAAN SMD (CROSS_TENANT, scoped)     → CAAN aggregate
    super-admin → platform console                  → /administration.html

═══ SINGLE CONSOLIDATED DATABASE (aerosafety-sms-prod / sms-db) ═══
   Firebase Auth  → identity + custom claims (role, tenant_id)
   Firestore      → tenants/{tid}/flight_diversions (source of truth),
                    psoe_assessments, state/ssp/{spis,risk_register,nhrcs}
   Supabase (PG)  → operational registers, tenant-keyed: hazards, reports,
                    cans, caps, surveys, survey_responses, state risk
   ═══════════════════════════════════════════════════════════════
   Tenant model: fixedwing · rotarywing · demoairport · demostate
```

**Tenant isolation** is enforced server-side end-to-end: PG rows are
tenant-keyed, cross-tenant API access is rejected unless the caller holds a
CAAN cross-tenant role (`CROSS_TENANT_ROLES = ["CAAN_SMD", "SUPER_ADMIN"]`),
and dashboards filter by tenant.

**SPI/SPT service** (`backend/app/services/spi_service.py`) loads a single
Postgres snapshot per call (hazards, reports as VSR/MOR, CANs/CAPs, surveys)
and merges **Firestore diversions** into that snapshot, so per-tenant values,
status, previous-month and monthly trend series all read one consistent view:

* `SPI_DEFINITIONS` — 8 SPIs (hazard id, VSR, diversion, risk reduction,
  MOR occurrence, CAN closure, CAP closure, safety culture) with
  target/warning/alert thresholds per indicator.
* Status is direction-aware (`_LOWER_IS_BETTER = {DIVERSION_RATE, OCCURRENCE_RATE}`);
  trend series are calendar-month bucketed.
* Sync facade (`_load_snapshot` → `run(_load_snapshot_async)`) matches the
  N-HRC / CAN-CAP service pattern.

## 3. Quality Gates

| Gate | Result |
|---|---|
| SPI suite (`tests/test_spi.py`) | **18 / 18 passing** (models, status/trend logic, closure rates, Firestore diversion rates, API routes) |
| State-risk / N-HRC / risk-matrix regression | **56 / 56 passing** (test_state_risk 35 + test_risk_matrix 21) |
| UAT API smoke (`scripts/run_uat_smoke.py`) | **8 / 8 passing** (/health, state-risk agg + PDF, tenant SMS summary + PDF, weekly SSP cron, audit logs) |
| Live Render API | `/health` 200 (firebase + database connected); `/api/v1/nhrc/*`, `/api/v1/spi/*` 200 |
| Seeder CLI dry-run | **87 created, 0 skipped, 0 errors** |
| DB counts | PG hazards 26 · reports 10 · cans 6 · caps 6; Firestore tenants 4 · diversions 7 · SSP 29 · PSOE 6 |
| HFACS catalog | **109 codes, 0 duplicates**, valid JSON (fetch-parseable) |
| Navigation | N-HRC + SPI/SPT items on all operator pages, no duplicates |
| Baseline (Aug 31) | 631 backend tests passing |

## 4. Deployment Endpoints

| Surface | URL / Target |
|---|---|
| Hosting (prod) | https://aerosafety-sms-prod.web.app · https://sms.aviasafesystems.com |
| Survey hosting | https://smssurvey.gsacharya.com |
| API (Render) | https://aviasafe-unified-platform.onrender.com |
| Firebase project | `aerosafety-sms-prod` · database `sms-db` |
| Deploy plumbing | root `render.yaml` (`autoDeploy: true`, `healthCheckPath: /live`, `dockerContext: backend`) |
| Supabase | project ref `bftwNljNpnpniksmalnk` (config.toml tracked; remote schema migration tracked) |
| Deployed commit | `82b4cc6` (feat(spi): fix diversion rate to read from Firestore) |

## 5. Operational Notes

* **Logging in**: share `https://sms.aviasafesystems.com/login.html` with the
  demo tenant accounts. Passwords are never committed — provision/rotate in
  Firebase Console or via `backend/seed/reset_passwords.py`.
* **Seeding / reseeding**: `python -m seeders.cli --all` (from `backend/`)
  seeds the 4-tenant demo platform idempotently; add `--dry-run` to preview,
  `-m <module>` for a single seeder, `-u` to unseed. Human bypass:
  `seed_manager.bat`.
* **New dashboards**: `/dashboard/spi-dashboard.html` (SPI/SPT) and
  `/dashboard/nhrc-dashboard.html` (N-HRC KPIs) follow the standard
  `SHELL_CONFIG` + auth-gate + `ApiClient` pattern and are reachable from the
  sidebar on every operator page.
* **Diversion data**: authored and read exclusively in
  `tenants/{tid}/flight_diversions` (Firestore). The Postgres
  `flight_diversions` table still exists in the schema for rollback but is not
  read by any service.
* **Empty SPIs are meaningful**: with all seeded diversions/CANs dated inside
  the current month, diversion status is `alert` (rate 3.0 vs 0.5 target,
  lower-is-better) and closure rates are 0% — an honest, mixed-status demo.
* **Manual UAT outstanding**: visual/browser verification of the two new
  dashboards (charts, status badges, nav) on the live host.

## 6. Known Follow-Ups

* Operator survey hostname map (`public/survey/app.js` `routes`) still maps only
  `sita-air`, `nepal-airlines`, `caan-ops`; the demo tenants use
  `?tenant=fixedwing|rotarywing|demoairport` links until their subdomains are added.
* Optional: per-employee survey issuance (unique links / `respondentId`) on top
  of the existing tenant-keyed storage if employee-scoped collection is required.
* State-level SPI surfaces for CAAN (operator breakdown across all four demo
  tenants on the state/CAAN pages) have not been built yet — the operator
  SPI/SPT dashboard is the current deliverable.
* `data/icao_adrep_taxonomies.csv` is imported to Supabase; keep reference CSVs
  versioned alongside `hfacs_nanocodes.csv`.
* Legacy Firestore `surveys` / `responses` collections (if any historical docs
  remain) can be purged with `backend/scripts/cleanup_firestore_surveys.py`.