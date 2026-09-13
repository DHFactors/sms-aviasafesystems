# Phase F Report — Reset to Virgin State (FIX 3 / FINAL)

**Date:** 2026-09-12
**Phase F:** operator-only full reset to virgin state — keep exactly one super-admin (Firebase Auth + `users` row, `tenant_id NULL`), wipe every tenant-scoped table and every other Firebase Auth user, leave static reference tables unchanged.
**Status:** COMPLETE — script delivered, scratch-validated, production executed (GO approved), post-reset state independently verified. STOP as instructed; no tenant onboarding performed.

---

## 1. Deliverable

`backend/scripts/reset_to_virgin.py` (CLI-only; no HTTP endpoint)

**Safety gates (all enforced in code):**
1. Dry-run is the default. Deletion requires **both** `--execute` AND `--confirm-virgin-reset`; neither alone does anything (exit 1).
2. Pre-flight gate (aborts unless satisfied): super-admin must exist in Firebase Auth (Admin SDK, by UID) **and** in `users` (single row, `uid = <uid>` and `tenant_id IS NULL`).
3. Prints a before/after count table for every table it clears.
4. Writes audit marker to `backend/logs/reset-virgin-<timestamp>.log` (mode, actor email, actor UID, date, before/after counts).
5. CLI-only. `--skip-auth` skips only the Auth-deletion phase (DB wipe + DB gate still run). `--database-url` overrides the DSN.

**Behavior:**
- DB wipe is one transaction (`SET LOCAL session_replication_role = replica` for FK bypass; falls back to FK-safe ordered deletes if not a superuser); ROLLBACK on any failure.
- Aliases resolved: `barriers` → `barrier_register`; `bowties` → `bow_tie_analyses/threats/consequences/controls`. Tables absent from a schema are introspected via `information_schema.tables` and skipped (e.g. `psoe_responses`, `spi_calculations`, `spi_targets`, `nhrc_calculations`, `sram_assessments` do not exist yet — skipped on both scratch and prod).
- Best-effort serial-sequence reset runs *after* commit in its own autocommit phase (cannot poison the wipe transaction).
- Birth-pool Auth deletion: `auth.list_users().iterate_all()` minus super-admin UID → `auth.delete_user(...)`, failures counted and reported.
- Credentials are masked (DSN sanitized, raw connect errors not printed).

**Fixes applied during validation (scratch-found):**
- Best-effort `pg_get_serial_sequence` error surfaced → transaction kept `ABORT`ed → `commit()` silently rolled back; moved sequence reset out of the wipe transaction (deletes now commit atomically).
- SQLAlchemy `postgresql+asyncpg://` + `?pgbouncer=true` DSN rejected by psycopg2 → URL normalized.
- Connect-failure branch printed the raw DSN (password leak) → sanitized error only.
- Verification block double-reported preserved tables → single preserved-unchanged block, no false "CHECK".

---

## 2. Pre-reset count table (captured by the script BEFORE deleting — production)

| table | count |
|---|---|
| users | 4 |
| tenants | 1 |
| regulators | 1 |
| hazards | 21 |
| reports | 99 |
| cans | 16 |
| caps | 12 |
| surveys | 204 |
| survey_responses | 204 |
| audit_logs | 608 |
| regulatory_reports | 3 |
| caan_reports | 2 |
| flight_diversions / psoe_assessments / psoe_findings / risk_register / barrier_register / bow_tie_* / state_risk_categories / corrective_actions / safety_deficiencies / verifications / closures / hazard_rca_* / hazard_* / state_risk_register / sms_maturity | 0 |

(Requested subset: tenants=1, users=4, hazards=21, reports=99, cans=16, caps=12, surveys=204, audit_logs=608.)

---

## 3. Post-reset verification block (read-only, re-run independently)

```
POST-RESET VERIFICATION (SELECT UNION ALL):
  audit_logs     = 0
  cans           = 0
  caps           = 0
  hazards        = 0
  regulators     = 0
  reports        = 0
  surveys        = 0
  tenants        = 0
  users          = 1
```

Expected: users=1, everything else=0 — **MATCHED.**

---

## 4. Firebase Auth post-reset user list (Admin SDK, read-only)

```
Firebase Auth post-reset user count = 1
  uid=hLXs4mvtf5bb1hRSifnh6HuUHpC2  email=ezondiza.dhf@gmail.com  claims={'role': 'SUPER_ADMIN', 'is_developer': True}
```

Exactly one user, UID `hLXs4mvtf5bb1hRSifnh6HuUHpC2` — **MATCHED.**

---

## 5. Preserved (never touched)

- Firebase Auth user `ezondiza.dhf@gmail.com` (UID `hLXs4mvtf5bb1hRSifnh6HuUHpC2`).
- `users` row for that UID, `tenant_id = NULL`, role `SUPER_ADMIN`, is_developer `true` (verified pre- and post-reset).
- Static reference tables (counts unchanged): `psoe_questions`=21, `icao_adrep_taxonomies`=15, `hfacs_nanocodes`=106, `hazard_adrep_mappings`=0, `hazard_hfacs_codes`=0, `report_adrep_mappings`=0, `report_hfacs_codes`=0.
- Firestore: no action (deprecated; deletion scheduled 2026-10-12 per `docs/PROJECT_STATUS_REPORT.md`).

---

## 6. Execution, audit log, and anomalies

- Execution command (approved GO, no backup requested): `python scripts/reset_to_virgin.py --execute --confirm-virgin-reset` (Firebase Auth phase ACTIVE) → exit 0, `VIRGIN STATE ACHIEVED`; auth: 3 non-super-admin users deleted, `failures=0`.
- Audit marker: **`backend/logs/reset-virgin-20260912-115103.log`** (mode=execute, actor email/UID, date 2026-09-12T11:51:03Z, before/after counts).
- Post-reset app boot: `/health` returns `{"status":"healthy","firebase":"connected","database":"connected",...}` on the virgin production DB.
- Anomalies/notes:
  1. `schema.sql` (scratch replication only) references `reports.is_demo` in `CREATE INDEX idx_reports_tenant_demo` (line 194) but the `reports` CREATE TABLE has no such column — the statement fails on a fresh schema; production unaffected (no DDL re-applied). Flagged for Phase F cleanup, not touched.
  2. `psoe_responses`, `spi_calculations`, `spi_targets`, `nhrc_calculations`, `sram_assessments` have no table in production and were skipped (0 rows; nothing to wipe).
  3. Scratch validation used local Docker Postgres (`--skip-auth`) so the production Firebase Auth pool was never touched during testing; gate pairs (DB row + Auth claims) were verified against production in dry-run before the execute.

---

## 7. Verification summary vs. target end state

| item | target | actual |
|---|---|---|
| users table | 1 (super-admin, tenant_id NULL) | 1 |
| tenants | 0 | 0 |
| regulators | 0 | 0 |
| all other tenant-scoped | 0 | 0 |
| static reference tables | unchanged | unchanged |
| Firebase Auth | 1 (super-admin UID) | 1 |

**Result: target end state achieved and independently re-verified.**
**STOPPING here as instructed — FIX 5 (onboard from virgin) awaits separate approval.**