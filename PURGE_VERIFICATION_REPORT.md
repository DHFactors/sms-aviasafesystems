# PURGE VERIFICATION REPORT — Phase 1 (Read-Only)

**Date:** 2026-09-17 (UTC) · **Mode:** Read-only (SELECT only; no deletes; no schema/migration/RLS changes)
**Target:** Live Supabase PG (`postgres.bftnwljnpnpniksmalnk…aws-0-ap-southeast-1.pooler.supabase.com:6543`) loaded from `backend/.env DATABASE_URL`. Queries run via `asyncpg` with `statement_cache_size=0` (pgbouncer transaction pooler; prepared statements not supported).

---

## 1. Reset tooling analysis — `backend/scripts/reset_to_virgin.py` (CHECK 1)

### Purpose
Operator-only CLI (no HTTP endpoint) that performs a "full reset to virgin state": it wipes every tenant-scoped operational table, demo-tagged regulator rows, every tenant, every `users` row except the super-admin, and every Firebase Auth user except the super-admin. Dry-run is the default; deletion requires BOTH `--execute --confirm-virgin-reset`. Before deleting it verifies the super-admin exists in both Postgres (`users` row, `tenant_id IS NULL`) and Firebase Auth (by UID), prints before/after counts per table, and writes an audit marker to `backend/logs/reset-virgin-<timestamp>.log`.

### Tables targeted for deletion (PRIMARY_SCOPE + DEPENDENT_SCOPE, aliases expanded)
- `hazards`, `reports`, `cans`, `caps`, `surveys`, `survey_responses`, `flight_diversions`
- `psoe_assessments`, `psoe_findings`, `psoe_responses`* (may-be-absent), `risk_register`
- `spi_calculations`*, `spi_targets`*, `nhrc_calculations`*, `sram_assessments`*
- `barrier_register`, `bow_tie_analyses`, `bow_tie_threats`, `bow_tie_consequences`, `bow_tie_controls`
- `state_risk_categories`, `regulators` (**only** `is_demo = TRUE` rows), `tenants`, `audit_logs`
- DEPENDENT: `corrective_actions`, `safety_deficiencies`, `verifications`, `closures`, `hazard_rca_entries`, `hazard_rca_factors`, `hazard_assessments`, `hazard_capas`, `regulatory_reports`, `state_risk_register`, `caan_reports`, `sms_maturity`
- Plus always: `users` → `DELETE FROM users WHERE uid <> <super_admin_uid>`

### Tables PRESERVED (counts must be unchanged — only reported)
`psoe_questions`, `icao_adrep_taxonomies`*, `hfacs_nanocodes`*, `hazard_adrep_mappings`*, `hazard_hfacs_codes`*, `report_adrep_mappings`*, `report_hfacs_codes`*; additionally all non-demo `regulators` rows are preserved (state authorities such as CAAN are treated as shared reference data).

### Users preserved
Exactly **one**: the super-admin (UID default `hLXs4mvtf5bb1hRSifnh6HuUHpC2`, tenant_id IS NULL). Everything else in `users` is deleted.

### Live DB vs env flag
Operates on the **live DB by default** — it reads `settings.DATABASE_URL` (live Supabase). There is NO safety flag that restricts it to scratch; it can target an alternate DB only via an explicit `--database-url` override. Dry-run / double-confirm flags are the only guards.

### Firebase Auth or PG only
**Both.** Unless `--skip-auth` is passed, it lists Firebase Auth and deletes every user except the super-admin. PG wipe + Auth wipe are separate phases (Auth runs after the DB commit).

### Gaps / caveats found
- `sram_risk_register` is **NOT** in the wipe scope (added in D1 but the script wasn't updated) — if it held rows, a "virgin" reset would leave them behind. (Currently 0 rows.)
- `invites`, `feedback`, `sms_dispatches`, `audit_dispatches` are **NOT** in scope. (Currently 0 / 0 / 0 / 2 rows.)
- `state_risk_categories` is fully deleted by the script, but the live table is empty (0 rows) — nothing is actually lost today.
- **All rows of the only tenant (Sita Air) including its 4 users would be deleted**, because the script treats every tenant and every non-super-admin user as disposable. See Section 2/4 — this is the central safety conflict.

---

## 2. Super admin inventory (CHECK 2)

Query: `SELECT uid, email, role, tenant_id, is_developer FROM users WHERE is_developer = true OR role IN ('SUPER_ADMIN','DEVELOPER')`

```
uid = hLXs4mvtf5bb1hRSifnh6HuUHpC2 | email = ezondiza.dhf@gmail.com | role = SUPER_ADMIN | tenant_id = NULL | is_developer = true
```

Exactly one match. **This is the user that must survive.**

`users` table (14 columns incl. `is_developer`) currently holds **5 rows**:
| uid | email | role | tenant_id |
|---|---|---|---|
| hLXs4mvtf5bb1hRSifnh6HuUHpC2 | ezondiza.dhf@gmail.com | SUPER_ADMIN | NULL |
| 3mvLISnBMxT9ueCINE8Iui3SaDI2 | safety@sitaair.com.np | AIRLINE_ADMIN | 2ec7c30d-…6fc (Sita Air) |
| Wmj5JZ586WPM2CrU9bEXp5QJJCq1 | 145@sitaair.com.np | DEPT_ADMIN | 2ec7c30d-…6fc (Sita Air) |
| 2VR56d4N8Kbv1Lz44IQP4tJCYv33 | ae@sitaair.com.np | AIRLINE_ADMIN | 2ec7c30d-…6fc (Sita Air) |
| ftl9YLsVyVeXLyMM7bit6WvKwzz1 | scratch-20260914a@sitaair.com.np | DEPT_ADMIN | 2ec7c30d-…6fc (Sita Air) |

`users` has **no** `is_demo` column — users are scoped by `tenant_id`, not demo-flagged.

---

## 3. Reference table state (CHECK 3)

| table | rows | is_demo column? | is_demo=true | verdict |
|---|---|---|---|---|
| `psoe_questions` | 21 | **YES (still exists in live)** | **21 / 21** | ⚠️ **FLAG** — live table is demo-seeded, NOT pure reference. Task expectation ("is_demo absent") is false; we removed the ORM mapping only — the live column and all-demo values remain. Purge tooling PRESERVES this table regardless. |
| `state_risk_categories` | 0 | no | — | Empty (nothing to preserve/lose). |
| `icao_adrep_taxonomies` | 15 | no | — | ✅ reference, matches expected 15. |
| `hfacs_nanocodes` | 106 | no | — | ✅ reference, matches expected 106. |
| `hazard_adrep_mappings` | 0 | no | — | empty |
| `hazard_hfacs_codes` | 0 | no | — | empty |
| `report_adrep_mappings` | 0 | no | — | empty |
| `report_hfacs_codes` | 0 | no | — | empty |

**Flag:** `psoe_questions` is seed/demo content in live. If a clean baseline requires genuine reference questions, the seed must be re-imported from the (non-demo) canonical seed data, not preserved from the demo table. Needs a decision.

---

## 4. Demo data inventory (CHECK 4)

`tenants WHERE is_demo=true` → **0 rows**. The only tenant is:

> **Sita Air Ltd** — tenant_id `sita-air`, `is_demo = FALSE`, status ACTIVE, category CONTRACTED, regulator CAAN, real contact (Bhusan Devkota, bdevkota@sitaair.com.np). Created 2026-09-13, delivered per `docs/delivery-workorder-20260914.md`. **This is a live delivered customer, not a demo row** — contradicts the task premise "tenants = 1 demo row".

Rows flagged `is_demo = TRUE` (all scoped to the Sita Air tenant):
| table | is_demo=true | note |
|---|---|---|
| hazards | 21 | |
| reports | 99 | VSR/MOR |
| cans | 16 | |
| caps | 12 | |
| surveys | 204 | |
| survey_responses | 204 | |
| **demo subtotal** | **556** | all under sita-air |

Zero-row tables (is_demo-filtered and/or tenant-scoped): `risk_register` 0, `sram_risk_register` 0, `psoe_assessments` 0, `psoe_findings` 0, `regulators(demo)` 0, `corrective_actions` 0, `safety_deficiencies` 0, `verifications` 0, `closures` 0, `hazard_rca_entries` 0, `hazard_rca_factors` 0, `hazard_assessments` 0, `hazard_capas` 0, `regulatory_reports` 0, `sms_maturity` 0, `sms_dispatches` 0, `invites` 0, `feedback` 0, `flight_diversions` 0, `state_risk_register` 0, `barrier_register` 0, `bow_tie_*` 0.

Tenant-scoped users: **4** (all Sita Air, see Section 2).

**Non-demo test artifacts (not is_demo-tagged, not in any purge scope, flagged for decision):**
- `caan_reports` = 2 rows (Q1/Q2 2026 quarterly summaries, `tenant_id NULL`, `generated_by "mock_user"`) — mock artifacts.
- `audit_dispatches` = 2 rows (`srb-test-reset-air-202609` tenant `test-reset-air`; `srb-sita-air-202609` tenant `sita-air`; both `recipients: []`, dispatched by `system/scheduler`) — test artifacts.
- `regulators` = 1 row (CAAN, `is_demo=FALSE`, `operator_tenant_ids: ["test-reset-air","sita-air"]`) — **reference, must be preserved.**

---

## 5. Firebase Auth inventory (CHECK 5)

Firebase Auth pool: **5 users** — a 1:1 mirror of the Postgres `users` table (all enabled, none disabled):

| uid | email | claims |
|---|---|---|
| hLXs4mvtf5bb1hRSifnh6HuUHpC2 | ezondiza.dhf@gmail.com | role=SUPER_ADMIN, is_developer |
| 3mvLISnBMxT9ueCINE8Iui3SaDI2 | safety@sitaair.com.np | role=AIRLINE_ADMIN, tenant_id=sita-air |
| Wmj5JZ586WPM2CrU9bEXp5QJJCq1 | 145@sitaair.com.np | role=DEPT_ADMIN, tenant_id=sita-air |
| 2VR56d4N8Kbv1Lz44IQP4tJCYv33 | ae@sitaair.com.np | role=AIRLINE_ADMIN, tenant_id=sita-air |
| ftl9YLsVyVeXLyMM7bit6WvKwzz1 | scratch-20260914a@sitaair.com.np | role=DEPT_ADMIN, tenant_id=sita-air |

No orphan Auth-only users beyond the PG set.

---

## 6. Backup state (CHECK 6)

- No repo-local backup/dump script or documented PG dump procedure exists (`backend/scripts/` contains seed/verify/reset tools only).
- `docs/delivery-workorder-20260914.md` rollback plan: "1. Verify backups are current (Supabase); 2. Restore path: identify most recent valid backup" — i.e., platform-level **Supabase managed backups** are the documented restore path.
- `docs/status.md` references only the deprecated Firestore snapshot (`gs://aerosafety-sms-prod-backups/firestore-20260912-062538/`, 30-day retention).
- `ROADMAP.md` RC-6 lists **backups/PITR as a pre-production/pilot item** — i.e., not confirmed-operational for this live DB.

**Whether a Supabase snapshot exists and is <24h old cannot be verified from the repo** — must be confirmed in the Supabase dashboard (or taken) before any write. The report recommends forcing a fresh snapshot in Phase 2 step 2 regardless.

---

## 7. Recommendation: SAFE TO PURGE? — **NO (not as specified)**

Reasoning:
1. **Premise mismatch (blocking):** the live DB does NOT hold "demo data only / tenants = 1 demo row / no production users besides super admin". It holds one **live delivered customer tenant** (Sita Air Ltd, `is_demo=FALSE`, CONTRACTED, 2026-09-14 delivery documented) with **4 real PG users + 4 real Firebase Auth users**, plus a CAAN regulator row referencing it. A full reset (`reset_to_virgin.py`) or a `DELETE FROM users WHERE uid <> super_admin` would delete a paying/customer tenant and its users — irreversible (no confirmed backup).
2. **psoe_questions is not pure reference** in live (21/21 is_demo=true) — contradicts the preserve-as-reference assumption; preserving it keeps demo content.
3. **No confirmed current backup** for the live PG DB (Supabase managed backups assumed, not verified).
4. Tenant-scoped users cannot be demo-filtered (no `is_demo` on `users`) — only the tenant linkage identifies them.

**What is unambiguous and safe to purge:** the 556 `is_demo=true` operational records (after backup); the 2 `caan_reports` mock rows and 2 `audit_dispatches` test rows (flagged, need approval); any Firebase-only orphan users (none currently).

**What MUST be decided first (ambiguous → blocking):** the fate of the Sita Air tenant + its 4 users (PG + Auth). This is a business decision, not a technical one.

---

## 8. What must be resolved before Phase 2

1. **Decide the Sita Air tenant + 4 users fate** — confirm it is (a) to be **preserved** (live customer → only purge the 556 demo-flagged records and mock artifacts, keep tenant/regulator/users) or (b) to be **deleted** (confirm the tenant is actually a disposable pilot/demo despite `is_demo=false`, in which case a full reset is appropriate).
2. **Decide `psoe_questions` handling** — preserve as-is (keeps 21 demo-tagged rows) or re-seed from canonical non-demo reference data post-purge.
3. **Confirm/take a live DB backup** (Supabase snapshot or `pg_dump`) in the last 24h before any write — not verifiable from the repo, so it must be demonstrated in Phase 2 step 2.
4. **Choose the execution path** based on (1): conservative is_demo-filtered purge (keeps tenant) vs `reset_to_virgin.py` (deletes tenant/users) vs a hybrid. If `reset_to_virgin.py` is chosen, first fix its scope gaps (`sram_risk_register`, `invites`, `feedback`, `sms_dispatches`, `audit_dispatches`) so the post-reset state is genuinely virgin.

---

*Phase 1 complete. End of read-only operations. No rows were modified. Awaiting decision/approval before Phase 2.*