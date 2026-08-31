# AviaSAFE — Project Status & Architecture Report

**Date:** 2026-08-31 · **Release:** Single-Database Consolidation + Minimal Clean Seed + PG-backed Survey Dashboards
**Scope:** Beta environment retired · consolidated `sms-db` · 2-airline DEMO seed · Supabase operational layer · dashboard survey analytics on PostgreSQL

---

## 1. Executive Summary

AviaSAFE has completed the **beta → production consolidation**. All
`sms-db-beta` / `aerosafety-sms-beta` references have been removed and the
platform now runs on a **single consolidated database** (`FIREBASE_DATABASE_ID=sms-db`,
project `aerosafety-sms-prod`). The decommissioned beta hosting targets, the
beta CI seed workflow, and the beta CLI guards were deleted; deployment is a
single-service Render Blueprint at the repo root.

The operational environment was reset and reseeded to a **minimal clean state**
for controlled rollout:

* **4 Firestore tenants plus a STATE system tenant**: `buddha-air` (DEMO),
  `yeti-airlines` (DEMO), `caan` (STATE regulator), `system` (STATE internal).
* **6 Firebase Auth users** — 2 per DEMO airline (`safety@` / `ops@`),
  the CAAN Safety Management Division account (`smd@caanepal.gov.np`), and the
  platform super admin. `caan` is scoped to `[buddha-air, yeti-airlines]`.
* **Supabase PostgreSQL operational tables all at 0 rows** (`reports`,
  `hazards`, `hazard_assessments`, `hazard_capas`, `safety_deficiencies`,
  `surveys`, `survey_responses`) — data lands only through the live API.

Tenant records now carry the lifecycle contract (`category` `DEMO|CONTRACTED|STATE`,
`status` `ACTIVE|SUSPENDED|EXPIRED`, `trial_expires_at`) with DEMO tenants seeded
on a 30-day trial. Credentials were renamed to the simplified `{role}@{domain}`
scheme (`safety@…` / `ops@…`, `admin@…` retired), which drives the **email-prefix
role routing** used across dashboards.

The Supabase integration is schema-tracked and reproducible: `config.toml`,
a full remote-schema migration, and the HFACS + ICAO ADREP reference datasets
are versioned. All quality gates are green (**631 backend tests**), and the
latest UI/hotfix releases (survey multi-tenant engine, App Check hardening,
`btn-primary` contrast fix) are deployed to Firebase Hosting.

## 2. System Architecture

```
Westin-prefix role routing (live accounts, email ⇒ role ⇒ surface)
    safety@…  → Safety Manager (AIRLINE_ADMIN)      → /safety.html
    ops@…     → Flight Operations (USER)            → /dashboard/responsible-manager.html
    smd@…     → CAAN SMD (CROSS_TENANT, scoped)     → CAAN aggregate
    super-admin → platform console                  → /administration.html

═══ SINGLE CONSOLIDATED DATABASE (aerosafety-sms-prod / sms-db) ═══
   Firebase Auth  → identity + custom claims (role, tenant_id)
   Firestore      → tenants/, users/, reports/, hazards/, demographics, ...
   Supabase (PG)  → operational tables, tenant-keyed, 0 rows until live
                    traffic (reports, hazards, hazard_assessments,
                    hazard_capas, safety_deficiencies, surveys,
                    survey_responses) — all with tenant_id indexes
   ═══════════════════════════════════════════════════════════════
   Tenant model: category (DEMO|CONTRACTED|STATE) · status
                 (ACTIVE|SUSPENDED|EXPIRED) · trial_expires_at
```

**Tenant isolation** is enforced server-side end-to-end: PG rows are
tenant-keyed, cross-tenant API access is rejected unless the caller
holds a CAAN cross-tenant role, and dashboards filter by tenant. Third-party
cross-tenant reads (e.g. JAL cybersecurity assessments) are scoped explicitly.

**Multi-tenant survey engine** (`public/survey/`): a standalone bilingual
(EN/NE) v4.0.0 survey resolves the tenant from a `?tenant=` parameter or a
hostname mapping (`smssurvey.gsacharya.com`, `sms.nac.com.np`, etc.), enforces
the per-tenant survey window from the tenant doc's `survey_config`, and submits
via `POST /api/v1/surveys/` with the `tenantId` validated against the tenant's
records — responses land keyed to the submitting tenant only.

### Survey analytics on PostgreSQL (single source of truth)

The dashboard survey aggregates previously read **Firestore**
`collection_group("surveys")` / `collection_group("responses")` — collections
the live API no longer writes to — so newly submitted survey responses were
persisted to Supabase but never surfaced on the dashboards. This gap is closed
by making **PostgreSQL the exclusive source of truth for survey analytics**:

* `backend/app/services/dashboard_service.py` now queries the `surveys` and
  `survey_responses` tables directly via `session_scope()`/`select()` —
  scoped by `is_demo == demo_scope()` with the `submitted_at` cutoff applied
  in SQL — through `_survey_docs`, `_survey_responses`, `_PGSurveyDoc`, and
  `_register_all_tenant_slugs`.
* The airline SMS maturity, CAAN survey maturity, CAAN SMS maturity
  assessment, and CAAN state "Survey Responses" counter all flow from the
  same Postgres rows the `POST /api/v1/surveys/` endpoint writes.
* The `submit_survey` route docstring was corrected to describe Postgres
  persistence (scored `surveys` + raw `survey_responses`).
* **Quality gate:** 137 backend tests passing, including new integration
  tests that seed real `Survey` / `SurveyResponse` rows and verify the SQL
  cutoff, slug translation, per-tenant response counting, and regulator
  scoping.
* `backend/scripts/cleanup_firestore_surveys.py` purges the legacy
  `surveys` / `responses` Firestore collections, leaving PostgreSQL (Supabase)
  as the exclusive store.

## 3. Quality Gates

| Gate | Result |
|---|---|
| Backend test suite | **631 / 631 passing** |
| Survey analytics (PG-backed dashboard) suite | **137 passing** (surveys, state/CAAN maturity, regulator scoping, tenant SMS) |
| Survey scoring suite | green |
| Demo/tenant scoping + isolation tests | green |
| Frontend inline-script / sandbox checks (Firebase App Check, tenant context, dashboard, input guard) | green |
| Full-repo `sms-db-beta` sweep | clean (residual refs only in historical/archived docs and tests asserting decommissioned behavior) |
| Seed validation | minimal 4+system tenants · 6 Auth users · CAAN scoped · PG 0 rows |

## 4. Deployment Endpoints

| Surface | URL / Target |
|---|---|
| Hosting (prod) | https://aerosafety-sms-prod.web.app · https://sms.aviasafesystems.com |
| Survey hosting | https://smssurvey.gsacharya.com |
| API (Render) | https://aviasafe-unified-platform.onrender.com |
| Firebase project | `aerosafety-sms-prod` · database `sms-db` |
| Deploy plumbing | root `render.yaml` (single-service, `dockerContext: backend`) · Firebase Hosting |
| Supabase | project ref `bftwNljNpnpniksmalnk` (config.toml tracked; remote schema migration tracked) |

## 5. Operational Notes

* **Logging in**: share `https://sms.aviasafesystems.com/login.html` with the
  tenant's safety (`safety@…`) or operations (`ops@…`) account. Passwords are
  never committed — provision/rotate in Firebase Console or via
  `backend/seed/reset_passwords.py`.
* **Reseeding**: `backend/seed/seeder.py` provides the minimal-reset flow
  (`--reset-minimal`) that purges Firestore/Auth (keeping the protected super
  admin and CAAN SMD accounts) and re-creates the 2 DEMO airlines.
* **Empty PG by design**: operational data is written only through the API, so
  the persisted model is exercised first.
* **Survey campaigns**: tenants control their own window via `survey_open_date` /
  `survey_close_date` / `is_survey_active` on the tenant doc; the page enforces it
  per tenant (no cross-tenant bleed). Survey submissions persist to the Supabase
  `surveys` / `survey_responses` tables, and all survey dashboards read those
  same tables — Postgres is the single source of truth for survey data.

## 6. Known Follow-Ups

* Operator survey hostname map (`public/survey/app.js` `routes`) still maps only
  `sita-air`, `nepal-airlines`, `caan-ops`; the live DEMO tenants use
  `?tenant=buddha-air` / `?tenant=yeti-airlines` links until their own
  subdomains are added.
* Optional: per-employee survey issuance (unique links / `respondentId`) on top
  of the existing tenant-keyed storage if employee-scoped collection is required.
* Legacy Firestore `surveys` / `responses` collections (if any historical docs
  remain) can be purged with `backend/scripts/cleanup_firestore_surveys.py`.
* `data/icao_adrep_taxonomies.csv` is imported to Supabase; keep reference CSVs
  versioned alongside `hfacs_nanocodes.csv`.