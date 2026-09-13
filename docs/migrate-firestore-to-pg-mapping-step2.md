# Migration Step 2 — Firestore → Postgres Mapping

Source of truth: live read of `aerosafety-sms-prod` / `sms-db` (read-only,
see Note on snapshot). Snapshot of the same DB taken `2026-09-12T00:40:42Z` at
`gs://aerosafety-sms-prod-backups/firestore-20260912-062538/` (verified, complete).

## Scope of live data

Only **two** root collections contain documents. All other collections named in
`docs/migrate-firestore-to-pg.md` (`tenants`, `regulators`, `invites`, `feedback`,
`caan_reports`, `sms_maturity`, `dead_letter_queue`, subcollections, etc.) have
**zero live documents** in prod — their data is already in Postgres or was purged.

| Collection | Document count |
|---|---|
| `audit_logs` | 131 |
| `users` | 1 |
| **Total** | **132** |

Snapshot `output-0` contains 133 record entities; the ±1 delta vs the live count
is within the snapshot-time window (2026-09-06 00:xx) and must be reconciled in
Step 4 (count match by collection). No subcollections exist under any document
(recursive enumeration returned empty).

---

## 1. `users` (1 document — shape consistent)

Doc id = the uid (`hLXs4mvtf5bb1hRSifnh6HuUHpC2`).

| Field | Type | Present | Notes |
|---|---|---|---|
| `uid` | string | 1/1 | equals doc id |
| `email` | string | 1/1 | (redacted in samples) |
| `display_name` | string | 1/1 | |
| `role` | string | 1/1 | `SUPER_ADMIN` |
| `tenant_id` | string | 1/1 | `"system"` (slug, not a real tenant) |
| `department` | string | 1/1 | empty string `""` |
| `is_developer` | bool | 1/1 | `true` |
| `last_login` | timestamp | 1/1 | |
| `created_at` | timestamp | 1/1 | |
| `updated_at` | timestamp | 1/1 | |

Redacted sample:

```json
{
  "_doc": "hLXs4mvtf5bb1hRSifnh6HuUHpC2",
  "created_at": "2026-08-26T13:03:44.231Z",
  "display_name": "Ezondiza DHF (System Developer)",
  "email": "<redacted>",
  "is_developer": true,
  "last_login": "2026-09-05T13:39:50.756Z",
  "role": "SUPER_ADMIN",
  "tenant_id": "system",
  "uid": "hLXs4mvtf5bb1hRSifnh6HuUHpC2",
  "updated_at": "2026-09-05T14:15:22.410Z"
}
```

No nested maps/arrays, no subcollections.

### Mapping → `users` (backend/app/db/db_models.py:1490)

| Firestore | Postgres `users` | Handling |
|---|---|---|
| `uid` | `uid` | direct |
| `email` | `email` | direct |
| `display_name` | `display_name` | direct |
| `role` | `role` | direct |
| `tenant_id` (`"system"`) | `tenant_id` | **edge case:** `"system"` is not a real tenant slug; `users.tenant_id` is a nullable UUID FK to `tenants.id`. Store `NULL` (flag in `data`/`metadata_json` style bag if a system UID marker is needed). |
| `department` (`""`) | `department` | store as-is, or normalize empty string → `NULL` for consistency with other rows (recommend `NULL`). |
| `is_developer` | `is_developer` | direct |
| `last_login` | `last_login` | direct |
| `created_at` | `created_at` | direct |
| `updated_at` | `updated_at` | direct |
| — | `id` | generate uuid4 |
| — | `phone`, `phone_verified` | absent → default `NULL` / `false` |

No new columns/tables required for this collection.

---

## 2. `audit_logs` (131 documents — shape INCONSISTENT)

Two distinct shapes coexist:

- **Shape A — demo-purge records (61 docs):** `action`, `timestamp` (string),
  `created_at`, `result`, `detail`, `target`, `actor:{uid,email}`.
- **Shape B — governance/LOGIN records (70 docs):** `action`, `timestamp`
  (timestamp), `metadata` (map), `tenant_id`, `target_type`, `target_id`,
  `request_id`, `user` (email), `ip` (always null).

### Field inventory

| Field | Present | Type(s) | Consistency |
|---|---|---|---|
| `action` | 131/131 | string | constant |
| `timestamp` | 131/131 | **string (61) + timestamp (70)** | mixed type — see edge case |
| `created_at` | 61/131 | timestamp | only shape A |
| `result` | 61/131 | string | only shape A (`"success"`) |
| `detail` | 61/131 | string | only shape A |
| `target` | 61/131 | string | shape A (`"all"`/`"none"`) |
| `actor` | 61/131 | map `{uid: string, email: string}` | only shape A |
| `metadata` | 70/131 | map: empty `{}` (28) or `{by_uid: string, status: string}` (42) | shape B |
| `tenant_id` | 70/131 | null (28) or string (42) | shape B |
| `target_type` | 70/131 | null (28) or string (42) | shape B |
| `target_id` | 70/131 | null (28) or string (42) | shape B |
| `user` | 70/131 | string (email) | shape B |
| `request_id` | 70/131 | string | shape B |
| `ip` | 70/131 | null (all 70) | always null |
| `target_type`/`target_id` collision | — | both `"tenant"`/`"acme-air"` for the 42 governance records | |

Distinct `action` values: `DEMO_DATA_PURGE` (58), `LOGIN` (28),
`TENANT_GOVERNANCE_STATUS_UPDATED` (42), `TENANTS_DEMO_DELETED` (1),
`STATE_RISK_DEMO_PURGED` (1), `DEMO_DATA_PURGE_FIRESTORE` (1).
Distinct `tenant_id`/`target_type`/`target_id`: `acme-air` / `tenant` / `acme-air` (42 docs).
`user` emails in shape B: `<redacted>` (28 × `safety@…summitair.com`, 42 × `super-admin@…aviasafesystems.com`).
`timestamp` range 2026-09-06T03:59 → 07:10Z; `created_at` range 2026-09-06T02:56 → 05:40Z.

Redacted sample (shape A):

```json
{
  "_doc": "04DHgTLQhG1oZakvFM8E",
  "action": "DEMO_DATA_PURGE",
  "timestamp": "2026-09-06T04:01:54.907884Z",
  "created_at": "2026-09-06T04:01:54.907884Z",
  "result": "success",
  "detail": "Purged 78 demo records across 26 tables",
  "target": "all",
  "actor": { "uid": "u1", "email": "<redacted>" }
}
```

Redacted sample (shape B):

```json
{
  "_doc": "<id>",
  "action": "TENANT_GOVERNANCE_STATUS_UPDATED",
  "timestamp": "2026-09-06T05:00:00Z",
  "metadata": { "by_uid": "<uid>", "status": "ACTIVE" },
  "tenant_id": "acme-air",
  "target_type": "tenant",
  "target_id": "acme-air",
  "user": "<redacted-email>",
  "request_id": "<uuid>",
  "ip": null,
  "target_type": "tenant",
  "target_id": "acme-air"
}
```

### Mapping → `audit_logs` (backend/app/db/db_models.py:1518)

| Firestore | Postgres `audit_logs` | Handling |
|---|---|---|
| `action` | `action` | direct |
| `timestamp` (string **or** timestamp) | `created_at` | normalize: parse ISO string → timestamptz; or use `created_at` when present. `timestamp` == `created_at` in shape A; use it as `created_at`. |
| `created_at` | `created_at` | fallback when `timestamp` absent |
| `result` | `result` | direct |
| `detail` | `detail` | direct |
| `target` | `target` | direct |
| `actor` map | `actor` | **nested handling:** `actor` column is `Text`. Store `actor.uid` (stable id) as `actor`; fold `actor.email` into `metadata_json: {"actor_email": …}`. |
| `user` (email) | `actor` / `metadata_json` | when `actor` map absent but `user` present (shape B): store nothing to `actor`, record `metadata_json: {"user_email": …}`. |
| `metadata` map | `metadata_json` | direct (JSONB), preserving `by_uid`/`status`. Merge with `actor_email`/`user_email` keys above. |
| `tenant_id` | `tenant_id` | direct (Text column — keep slug `acme-air` as-is; do NOT UUID-ize: audit tenant_id is a slug string). |
| `target_type` | `target_type` | direct |
| `target_id` | `target_id` | direct |
| `request_id` | `request_id` | direct |
| `ip` | `ip` | direct (all null today) |
| — | `id` | generate uuid4 |

No new columns/tables required. **Recommended consolidation rule for the email
fields** (shape A `actor.email` vs shape B `user`): write all into
`metadata_json` under reserved keys (`actor_email`, `user_email`) so the email is
never lost and `actor` stays a clean id/text column.

---

## 3. Edge cases

1. **`users.tenant_id = "system"`** — not a real tenant; FK is nullable. Store `NULL`, keep a marker in `users` (email/display name already identify the system account). Do not fabricate a `tenants` row.
2. **`audit_logs.timestamp` mixed type** — 61 string + 70 timestamp. Both are ISO-8601 with zone; single normalization path required; verify parse on all 131 before import (Step 4 check: no null `created_at`).
3. **Duplicate-ish identity in shape B** — `user`, `tenant_id`, `target_type=tenant`, `target_id=acme-air` overlap. Keep all as-is; no join logic at import.
4. **Empty-string `department`** — decide `""` vs `NULL`; recommend `NULL` for uniform Postgres text semantics.
5. **`metadata` is `{}` for 28 shape-B docs** — JSONB `'{}'` matches `DEFAULT_JSONB`; fine.
6. **Snapshot vs live ±1** — live 132 docs vs 133 snapshot records; reconcile exact counts per collection during Step 4 verification against the snapshot file, then re-verify against PG after import.
7. **PII in audit logs** — `actor.email` / `user` contain emails; import tool must not log them; doc samples redacted above.
8. **`audit_logs.tenant_id` is a Text slug** (`acme-air`) in Firestore **and** in `audit_logs` PG model — no UUID conversion (unlike `users`).

## 4. Verification criteria (for Step 4)

- `users`: exactly 1 row; `uid` = `hLXs4mvtf5bb1hRSifnh6HuUHpC2`; `role` = `SUPER_ADMIN`; `tenant_id` IS NULL; `is_developer` = true; `created_at`/`updated_at` match source timestamps.
- `audit_logs`: exactly 131 rows (or snapshot count if ±1 resolves to 131/132); `action` distribution matches counts above (58/28/42/1/1/1); no row has null `created_at`; `metadata_json` for the 42 governance rows contains `by_uid`/`status`; every shape-A row has `actor` != null and `metadata_json->>'actor_email'` present; slug-valued columns (`tenant_id`, `target_id`, `target_type`) preserved verbatim (e.g., `acme-air`/`tenant`).
- Spot-check 10–20 rows field-by-field against the Firestore source (both shapes represented).
- FK integrity: new `audit_logs`/`users` rows reference nothing that a later-imported table needed (no cross-table FK in this scope — `users.tenant_id` is NULL).
- Idempotency: rerunning the importer yields `ON CONFLICT DO NOTHING` with no duplicates (uses `users.uid` unique and `audit_logs.id` uuid4 — for rerun-safety, seed import idempotency key).

## 5. Import ordering

Both collections are independent (no FK dependencies — `users.tenant_id` NULL).
Recommended order:

1. `users` (least rows, defines the only system account).
2. `audit_logs` (131 rows; independent).
3. Verification pass (Section 4).

No parent-before-child ordering constrains this scope since no Firestore docs
reference other collections by FK.

---

### Note on the snapshot vs live read

This inventory was produced with a read-only Firestore SDK load (AD-user token,
datastore read-only scope) against the live database right after Step 1. The
Step 1 snapshot covers the same collections and is the point-in-time source that
Step 4 will reconcile against. Raw snapshot binary (`output-0`, 53,832 B, 133
records) is GCS-export internal format, not public `Write` protos; parse of live
SDK confirmed the collection/doc shape above.