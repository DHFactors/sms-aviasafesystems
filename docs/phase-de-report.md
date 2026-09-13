# Phase D/E Report — Docs Update + Residual `sms-db` Usage Decision

**Date:** 2026-09-12
**Phase D:** current-state docs → Postgres-only data plane + Firebase Auth only for identity; add Firestore Deprecation section.
**Phase E:** findings + recommendations (NO edits/deletions) for `docker-compose.yml` and Firestore seed/scripts utilities.
**Status:** D complete (5 files edited, verified). E reported — awaiting decision before any file is touched.

---

## 1. Phase D — Docs diff (applied)

D1 — `docs/PROJECT_STATUS_REPORT.md`
- Added new **`## Firestore Deprecation`** section (immediately after the header):
  - Deprecation date **2026-09-12**
  - Backup snapshot `gs://aerosafety-sms-prod-backups/firestore-20260912-062538/`
  - Retention 30 days
  - Scheduled deletion **2026-10-12** unless rollback required
  - Deferred cleanup → `docs/phase-f-cleanup.md`
- Exec summary: "single consolidated database (sms-db)" → **PostgreSQL (Supabase) data plane**; seeded-data bullets now attribute tenants / diversions / SSP / PSOE to Postgres (no Firestore).
- Data-plan architecture diagram rewritten to **"DATA PLANE (Postgres-only; Firebase Auth for identity)"** with an inline "(Firestore sms-db deprecated 2026-09-12 — no runtime reads)" note.
- Diversions: "source of truth is Firestore" → **Postgres `flight_diversions` table** (matches `FlightDiversionService` reading `pg.fetch_all(FlightDiversion)`).
- SPI/SPT bullet: dropping "merges Firestore diversions" wording.
- DB-counts row, deployment-endpoints row ("Firebase project · database sms-db" → "Auth only; sms-db deprecated 2026-09-12"), operational notes, and legacy-surveys purge bullet updated to the deferred-runbook wording.

D2 — other current-state docs (all describe Postgres-only stores now):
| File | Change |
|---|---|
| `README.md` | L44 `Database` row → PostgreSQL (Supabase) operational registers; Firebase Auth only for identity. L82-83 `firestore/` + `firestore.indexes.json` directory listings annotated `(legacy; deprecated 2026-09-12)`. |
| `backend/PERFORMANCE_REPORT.md` | L261-262 "includes Firestore I/O on master-register" → measured on Postgres data plane (Firestore reads removed 2026-09-12). L284-285 master-register `cpu` Firestore-doc-I/O claim → Postgres register reads. |
| `public/docs/tenant-guide/01-getting-started/1.0-overview.md` | L89 "loads from live Firestore" → "loads from the backend API / live database (no mock data)". |
| `status.md` | L6 "single consolidated sms-db Firestore + Supabase Postgres" → "Postgres (Supabase) data plane; Firebase Auth only for identity (Firestore deprecated 2026-09-12)". |

Left untouched (by design): `docs/archive/*`, `docs/migrate-firestore-to-pg-mapping-step2.md`, `ROADMAP.md`, `todos.md`, `session 10092026.md`, `docs/GLOSSARY.md`, phase B/C report files — historical records. `docs/PROJECT_STATUS_REPORT.md` L4 scope line kept as-is (phase-rollup phrasing with a non-UTF8 separator byte).

Docs do not run code paths — no import-time impact.

---

## 2. Phase E(a) — `docker-compose.yml` + adjacent config findings

`docker-compose.yml` (tracked) — local-dev container only (service `api`, `ENVIRONMENT=development`, no `.github/workflows` in repo → not CI):
- **L17 `- FIREBASE_DATABASE_ID=sms-db`** is still **active**.
- With `app.firebase.get_db()` now raising (A8), a local `docker compose up` container degrades at the same debug branch points as the server tests, but boots fine (`/health` 200). The var itself is unused by runtime code.

**Newly surfaced by the full-repo grep (out of C's 5-file scope):**
- **`firebase.json` L4** `"database": "sms-db"` — the `firestore` deploy block (rules + indexes) still targets `sms-db`. This is a *deploy* config for the legacy ruleset, not runtime code. The backup snapshot means rules/indexes are archived; keep the block during the rollback window only if we want the ability to redeploy rules to `sms-db`.
- **`backend/.env.demo` L42 `FIREBASE_DATABASE_ID=sms-db`** — **still active**, and this file was **not in C's 5-file scope**. It is **NOT tracked** (gitignore `**/.env.demo`, `.gitignore:8`) — carries real secrets, local/demo copy only. Anyone running the old demo env would still target `sms-db`.

### E(a) recommendation (no edits applied)
1. `docker-compose.yml` L17 → comment it out with the same phase-C style deprecation label (30-day window), keeping the env file deprecation story consistent for local dev. Safe: no runtime code reads it.
2. `backend/.env.demo` L42 → same comment-only treatment (untracked local file; apply locally like `backend/.env` was). Flag as a **C-scope gap**.
3. `firebase.json` `firestore` block → **keep until 2026-10-12** (rollback safety); delete/replace in phase F with the archived `sms-db` ruleset if deletion goes ahead. No runtime impact.

---

## 3. Phase E(b) — Firestore seed/scripts inventory + reachability

### 3.1 Inventory (files referencing `sms-db` / Firestore writes, standalone CLI/dev tools)

| Group | Files | Reachable from `backend/app`? |
|---|---|---|
| `backend/seed/*.py` legacy Firestore seeder | `deploy_seed.py` (`DB_ID="sms-db"`), `seeder.py`, `unseed.py` (`BETA_DB_ID="sms-db"`), `runner.py` (L152 `from app.firebase import get_db`) | **No** (CLI-only; not imported by `seeders/` or `app/`) |
| `backend/scripts/*.py` Firestore utilities | `activate_survey_campaigns`, `backfill_hazards` (`DEFAULT_DB="sms-db"`), `backfill_sms_maturity`, `backfill_users`, `cleanup_firestore_surveys`, `fix_summit_air_user`, `generate_tenant_details`, `seed_caan_demo_data`, `seed_flight_diversions`, `seed_psoe_baselines`, `seed_uat_data`, `simplify_credentials`, `validate_seasonal_seed`, `verify_date_distribution`, `wipe_tenant_data` | **No** (standalone) |
| `scripts/migrate_firestore_to_supabase.py` | one-shot Firestore→PG migration tool (`DEFAULT_DATABASE="sms-db"`) | **No** (already executed migration) |
| `scripts/firebase/*` admin diagnostics | `cleanup_users.py`, `list_tenants.py`, `repro-500.py`, `db-probe.js`, `inspect-hazards.js`, `inspect-report-hazard-link.js`, `dump-junk-hazards.js`, `cleanup-junk-hazards.js`, `seed-extra-hazards.js` | **No** (dev/cli) |
| `scripts/seed/seed_demo_hazards.py` | safety-gated beta demo seed (`FIRESTORE_DATABASE_ID != "sms-db"` → abort) | **No** |
| `tests/e2e/live_validation.py` | manual live-validator that **writes to sms-db**; not collected by pytest (810 suite unaffected) | **No** (manual script) |
| `backend/_audit_all_tenants.py`, `backend/_purge_prod_database.py` | one-time diagnostics using `firestore.Client(database="sms-db")` | **No** |
| `backend/seed/config.py` | **pure constants** (`FLIGHT_OPERATOR_TYPES`) imported by `dashboard_service.py` | **SAFE** — keep |

### 3.2 Scope escalation (REQUIRED report, per E(b) rule: reachable → STOP and report)

- **`backend/scripts/seed/unified_seeder.py::seed_tenant_hazards` IS reachable from a production API path**:
  - `backend/app/api/v1/endpoints/tenants.py` (L21) → `onboard_tenant` (`app/services/onboarding_service.py` L76-97) → `from scripts.seed.unified_seeder import seed_tenant_hazards` (L80), called with `target="both"`.
  - At runtime `app.firebase.get_db()` raises `NotImplementedError` (A8) → onboarding catches and logs **"Onboarding hazard seed failed"** (degraded, non-fatal). Because `target="both"` hits the Firestore branch first, the **Postgres hazard seed is also skipped** for new tenants — a silent data gap since A1/A8.
  - **Recommendation (flag only, no edit):** (1) short-term — flip `unified_seeder` to `target="postgres"` default (or remove the Firestore branch) so onboarding actually seeds hazards into PG; (2) long-term — retire the script under phase F and let onboarding seed PG hazards directly. Until (1) is decided, new tenant onboarding silently skips hazard seeding. This is a real functional gap, outside the D/E mandate to decide separately.

### 3.3 E(b) recommendation (no edits/deletions)
- After 2026-10-12 (post rollback window): move the unreachable Firestore tools to `backend/legacy_firestore_tools/` (or delete): `backend/seed/*` Firestore seeder, the 15 `backend/scripts/*` Firestore utilities, `scripts/firebase/*`, `scripts/seed/seed_demo_hazards.py`, `backend/_*` diagnostics, and `tests/e2e/live_validation.py`.
- **Keep** `backend/seed/config.py` (pure constants) and the `seeders/` package (current CLI) untouched.
- **Update** `frontend-tests/firebase-appcheck-verify.js` (L63-85) — still asserts `__FIREBASE_CONFIG__.databaseId === 'sms-db'`, which phase B removed from `firebase.js`; stale manual test, not in the pytest suite.
- Keep `docs/migrate-firestore-to-pg-mapping-step2.md` + `docs/archive/*` as historical records.

---

## 4. Verification (post-edits)

- **Boot:** uvicorn on :8765 → `INFO: Application startup complete`, `Uvicorn running`; `/health` → **200** `{"status":"healthy","firebase":"connected","database":"connected","service":"AviaSAFE SMS API","version":"1.0.0"}`.
- **Full suite:** `python -m pytest -p no:cacheprovider -q --tb=short` → **810 passed, 16 warnings in 0:09:01**. Docs-only changes, no runtime impact; no new warnings.
- **Full-repo `sms-db` grep — classification (211 actionable hits; +~287 in `backend/logs/aviasafe.json`, `backend/scripts/logs/*`, `docs/archive/*`, `session 10092026.md`, all historical):**

| Class | Files | Hits | Action |
|---|---|---|---|
| Active config (decision) | `docker-compose.yml:17`, `firebase.json:4`, `backend/.env.demo:42` (untracked) | 3 | E(a) → comment/keep-per-window (see §2) |
| Comment-only (phase C applied) | `render.yaml`, `backend/.env`, `.env.example`, `.env.demo.example`, `app/core/config.py` | 9 | none — done |
| Docs (current-state deprecation notes) | `docs/PROJECT_STATUS_REPORT.md`, `ROADMAP.md` | 5 | none — written in D |
| Historical migration/phase reports | `docs/migrate-firestore-to-pg-mapping-step2.md`, `docs/phase-b-cleanup-report.md`, `docs/phase-c-cleanup-report.md` | ~20 | leave (record) |
| Stale JS comments | `public/js/aviasdcps-api.js` + `views/{home,occurrence,hazard,sdc,spis}.js` (`@target sms-db`) | 6 | comment-only; clean in later sweep |
| **Unreachable** Firestore tools | `backend/seed/*`, `backend/scripts/*` (15), `scripts/migrate_firestore_to_supabase.py`, `scripts/firebase/*`, `scripts/seed/seed_demo_hazards.py`, `tests/e2e/live_validation.py`, `backend/_*.py` | ~130 | E(b) → legacy-folder/delete after 2026-10-12 |
| **Reachable (escalation)** | `backend/scripts/seed/unified_seeder.py` via `onboarding_service.py` → `tenants.py` | ~3 | §3.2 — separate decision |
| Logs / backups / credentials (artifacts) | `backend/logs/aviasafe.json`, `backend/scripts/logs/*`, `scripts/firebase/backups/*`, `final_credential.txt` (untracked) | ~35 | leave; purge with cleanup |
| Stale test file | `frontend-tests/firebase-appcheck-verify.js` (asserts `databaseId==='sms-db'`, now absent) | 3 | update in later phase |

---

## 5. Open decisions for the user

1. **E(a):** comment `docker-compose.yml:17` now? Apply same to `backend/.env.demo:42`?
2. **E(b):** after 2026-10-12, move unreachable Firestore tools to `backend/legacy_firestore_tools/` or delete them?
3. **Escalation:** fix `unified_seeder` onboarding path (`target="postgres"` / remove Firestore branch) so new-tenant hazard seeding isn't silently skipped?
4. `firebase.json` Firestore rules block: delete with phase F, or keep for rollback-emergency until deletion?

**No edits or deletions were made to docker-compose / seed / scripts / firebase.json in this phase — STOP per plan before phase F.**