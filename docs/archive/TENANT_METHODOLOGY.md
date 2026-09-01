# Tenant Methodology — Revision Spec

**Status**: DRAFT (for review — no code changed yet)
**Author**: AviaSAFE Systems engineering
**Date**: 2026-08-12
**Scope**: Tenant type taxonomy, canonical tenant doc schema, and the provisioning workflow. Implemented only after this spec is approved.

---

## 1. Context & Goal

The current model treats tenants as airlines: the seed profiles carry ad-hoc aircraft-operation strings
(`"Scheduled Airline"`, `"STOL Cargo"`, `"Helicopter"`, `"STOL Passenger/Cargo"`) and the admin creation
form (`public/admin/production-setup.html` Step 2) captures no type at all. Production has 0 tenants; the
platform must be ready to onboard real service providers beyond airlines (MROs, aerodromes, ground handlers).

**Goal for beta**: exactly **one (1) tenant of each tenant type** exercising the platform, so every module
(SMS maturity survey, hazard/risk, CAN/CAP, department workflows) is validated against each organization kind.

## 2. Tenant Type Taxonomy

A single canonical enum. IDs are stable, lowercase, hyphenated. `label` is display text.

| `tenant_type` | Label | Example | Has operational data |
|---|---|---|---|
| `airline` | Airline | buddha-air, yeti-airlines | ✅ |
| `helicopter-operator` | Helicopter Operator | air-dynasty, simrik-air | ✅ |
| `mro` | MRO / CAMO (Part-145) | *(new)* | ✅ |
| `aerodrome` | Aerodrome Operator | *(new)* | ✅ |
| `ground-handling` | Ground Handling | *(new)* | ✅ |
| `state-regulator` | State Civil-Aviation Authority | caan | ❌ (special) |

Notes:
- The five service-provider types are the beta population; `state-regulator` is the existing CAAN tenant
  and is lifecycle-managed alongside operators but carries no operational data.
- The old seed strings map to the enum as follows (see §7 migration):
  `"Scheduled Airline"` → `airline`, `"STOL Cargo"` / `"STOL Passenger/Cargo"` → `airline`,
  `"Helicopter"` → `helicopter-operator`, `"state_regulator"` → `state-regulator`.
- **Decision needed**: STOL operators are fixed-wing air carriers, so they map to `airline` today. If
  cargo-only operators (summit-air) should be distinguishable, add a future `cargo` type — not required for beta.
- `tenant_type` is stored as the field `type` on the tenant doc (kept for compatibility) **and** mirrored
  as `tenant_type` (explicit, documented, and returned by the admin API). Both are written together to avoid
  a rename ripple; see §5.

## 3. Canonical Tenant Document Schema

Single schema for every tenant in `tenants/{id}`. All paths that create a tenant write the same shape:
`seed/operators.py` (seed), `app/services/production_seed.py:create_tenant` (admin single),
`app/services/tenant_credentials.py:create_tenant_with_credentials` (admin + users), and the lifecycle
updater `app/services/admin_data_service.py:update_tenant_status`.

### 3.1 Canonical fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `tenant_id` / `id` | string | ✅ | lowercase `[a-z0-9-]+` (existing `_validate_id`) |
| `name` | string | ✅ | organization name |
| `type` | string (enum §2) | ✅ | kept for compatibility |
| `tenant_type` | string (enum §2) | ✅ | explicit, canonical |
| `icao` | string | type-dep | operator types only (`airline`, `helicopter-operator`); blank for MRO/aerodrome/ground-handling |
| `iata` | string | type-dep | operators only, may be `""` |
| `country` | string | ✅ | default `Nepal` |
| `country_code` | string | — | ISO-2 (`NP`); optional, used by regulator scoping |
| `base` | string | type-dep | base location (airline/helo: base airport; mro: facility; aerodrome: the aerodrome; ground-handling: base airport) |
| `regulator_id` | string | ✅ | the overseeing State Regulator (e.g. `caan`) |
| `active` | bool | ✅ | derived from `status` (`Active` → true) |
| `status` | string | ✅ | `Trial` / `Active` / `Inactive` (see §4) |
| `payment_status` | string | — | `Paid` / `Unpaid` |
| `contract` | object | — | `{ start_date: "YYYY-MM-DD", end_date: "YYYY-MM-DD" }` |
| `contact` | object | — | `{ name, email, phone }` |
| `safety_manager` | object | — | `{ name, email, uid }` |
| `users` | array | — | credential metadata (never passwords): `[{email, role, uid, full_name, department, status, created_at, last_login}]` |
| `audit` | object | ✅ | `{ created_by, created_at, last_modified_by, last_modified_at }` |
| `created_at` | datetime | ✅ | UTC |
| `updated_at` | datetime | ✅ | UTC |
| `status_updated_at` / `status_updated_by` | — | — | written by lifecycle updater |
| `config` | object | — | per-tenant config incl. `survey_rate_limit`, `survey_instructions` |
| `survey_config` | object | — | legacy; merged into `config` on read |
| `seed_version` | string | — | seed/backfill marker |
| `sms_profile` | string | — | culture description (display) |

### 3.2 Type-specific optional block

| Field | Applies to | Notes |
|---|---|---|
| `fleet_size` | `airline`, `helicopter-operator` | number of aircraft |
| `employees` / `org_size` | all providers | `org_size` preferred; keep `employees` for display compat |
| `aircraft_types` | `airline`, `helicopter-operator`, `mro` | mro: approved type ratings |
| `routes` | `airline`, `helicopter-operator` | route network |
| `email_domain` | all providers | used by simplified credential scheme |
| `certification` | `mro`, `aerodrome`, `ground-handling` | e.g. Part-145 approval ref / aerodrome licence ref |

Unused fields must be **omitted** (not empty strings) so the schema stays honest per type.

### 3.3 Validation rules (backend)

Enforced in `production_seed.create_tenant` (single source of truth):
- `tenant_type` must be one of the enum §2.
- `type` is derived from `tenant_type` automatically; callers may not set them inconsistently.
- For `state-regulator`: no `icao`/`iata`/`fleet_size`/`routes`; `regulator_id` must be its own id or absent.
- For `mro`/`aerodrome`/`ground-handling`: `icao`/`iata`/`fleet_size`/`aircraft_types`/`routes` are rejected
  if present (they are operator-only), `base` is required.
- For `airline`/`helicopter-operator`: `base` and `icao` recommended (warning, not error).

## 4. Lifecycle / Status Methodology (unchanged behavior, documented)

Keep the existing `derive_tenant_status` rules from `app/services/admin_data_service.py`:
explicit `status` wins; `Unpaid` → `Inactive`; past `end_date` → `Inactive`; future `start_date` → `Trial`;
otherwise `Active`. `active` is always derived from `status`. No change to this logic in this revision.

## 5. Provisioning Workflow Revision

### 5.1 Admin creation (`public/admin/production-setup.html` Step 2)

- Add a required **Tenant Type** dropdown (`tenant_type`), values from §2, default `airline`.
- Conditional fields: when type is `mro`/`aerodrome`/`ground-handling`, show `base` + optional `certification`,
  hide `ICAO`/`IATA`; when `airline`/`helicopter-operator`, show `ICAO`/`IATA` + optional `fleet_size`.
- Bulk CSV header becomes:
  `tenant_id,name,tenant_type,icao,country,base,regulator_id,certification`
  (`tenant_type` required; existing header `icao,country,regulator_id` still accepted with
  `tenant_type` defaulting to `airline` for back-compat).
- `TenantCreate` model (`backend/app/routes/admin.py:382`) gains `tenant_type: Optional[str] = None`
  (default `airline` when absent) and passes through to `create_tenant`.

### 5.2 Seed plan (`production_seed.SEED_OPERATORS` + `deploy_seed`)

- `SEED_OPERATORS` gains `"tenant_type"` on each entry; the preview table shows a **Type** column.
- `deploy_seed` writes both `type` and `tenant_type` on every tenant tag.
- The demo-data seed/unseed tooling (`admin_data_service`) is type-agnostic and unchanged, but its
  `_DEPARTMENTS` list is extended to cover new types (see §6).

### 5.3 Admin list (`list_tenants_admin`)

- Include `tenant_type` (and `type`) in each returned row; the Existing Tenants table in
  `production-setup.html` renders a **Type** column.

### 5.4 Tenant API

- `GET /api/v1/tenants/{id}/config` and `GET /api/v1/tenants/{id}/users` unchanged.
- `GET /api/v1/admin/tenants` response rows now include `tenant_type`.
- Add optional `?tenant_type=` filter to `GET /api/v1/admin/tenants` (SUPER_ADMIN) to support
  type-scoped provisioning checks.

## 6. RBAC / Department Alignment

- Custom claims are unchanged (`role` + `tenant_id` + optional `department`). `department` is a free string,
  so no schema change is required.
- Simplified role accounts (`seed/config.py:SIMPLIFIED_ROLE_ACCOUNTS`) currently cover
  `safety`, `camo`, `145`, `ops` — natural fit for `airline`, `helicopter-operator`, and `mro`.
- **Beta-only extension**: add two role tokens for the new types so each beta tenant has a working
  Responsible-Manager account:
  - `ground-ops` → department `Ground Operations` (ground-handling)
  - `airport-ops` → department `Airport Operations` (aerodrome)
- This is additive; the existing 4 tokens keep their exact emails/passwords.

## 7. Migration & Backfill (existing beta tenants)

One-time backfill script (pattern: `backend/scripts/backfill_sms_maturity.py`):
- For every doc in `tenants` where `tenant_type` is missing, derive it from the old `type` per §2 mapping.
- For `state-regulator` (`caan`) keep as-is.
- Dry-run + `--db` selection, idempotent, audited via `TENANT_TYPE_BACKFILL`.

Mapping (old `type` → new `tenant_type`):

| Old `type` (seed) | New `tenant_type` |
|---|---|
| `Scheduled Airline` | `airline` |
| `STOL Cargo` | `airline` |
| `STOL Passenger/Cargo` | `airline` |
| `Helicopter` | `helicopter-operator` |
| `state_regulator` | `state-regulator` |

## 8. Beta Seeding Plan — 1 tenant of each type

| `tenant_type` | Tenant | Action |
|---|---|---|
| `airline` | buddha-air | existing → backfill |
| `helicopter-operator` | air-dynasty | existing → backfill |
| `mro` | **new** `ktm-mro` — "Kathmandu MRO Services" | create (Part-145 / CAMO) |
| `aerodrome` | **new** `pokhara-aerodrome` — "Pokhara Regional Aerodrome" | create |
| `ground-handling` | **new** `himalaya-ground-services` — "Himalaya Ground Handling" | create |
| `state-regulator` | caan | existing → keep |

- The three new tenants get full seed data (surveys/hazards/reports) via the type-aware seed plan and
  demo-data tooling, and simplified accounts (existing 4 tokens + 2 new).
- **Decision needed**: keep the other existing operators (yeti-airlines, summit-air, sita-air, simrik-air,
  tara-air — all → `airline`/`helicopter-operator`) in beta as additional samples (recommended: they carry
  the 1,033 seeded surveys the dashboards aggregate), or trim beta to exactly the six rows above.
  Trimming would require re-seeding fewer tenants and is reversible.

## 9. Testing

- Backend: extend `tests/test_admin_seed.py` — `tenant_type` validation per type (operator-only fields
  rejected for mro/aerodrome/ground-handling), backfill mapping, admin list type filter.
- Backend: `tests/test_admin_credentials.py` — tenant+users creation carries `tenant_type`.
- Frontend: `node frontend-tests/dashboard.test.js` unaffected; manual check of Step 2 conditional fields.

## 10. Implementation Checklist (ordered)

1. `TENANT_TYPES` enum + validation in `app/services/production_seed.py` (write `type` + `tenant_type`).
2. `TenantCreate.tenant_type` in `app/routes/admin.py`; pass-through in `create_tenant` /
   `create_tenant_with_credentials`.
3. Backfill script `backend/scripts/backfill_tenant_types.py` (dry-run + apply, §7) + run against `sms-db`.
4. `list_tenants_admin` returns `tenant_type` + `?tenant_type=` filter.
5. `public/admin/production-setup.html`: Step 2 type dropdown + conditional fields; bulk CSV header;
   Existing Tenants **Type** column; tenant-credentials page shows type.
6. `seed/config.py`: `SIMPLIFIED_ROLE_ACCOUNTS` += `ground-ops`, `airport-ops`;
   `CREDENTIAL_TENANT_CODES`/`CREDENTIAL_EMAIL_DOMAINS` += new tenants; `OPERATOR_PROFILES` += 3 new
   profiles with `tenant_type`.
7. `seed/operators.py` + `production_seed.py` write `tenant_type`; preview shows Type column.
8. Seed the 3 new tenants in `sms-db` (surveys/hazards/reports/CAN/CAP) + simplified accounts.
9. Run backend suite (target 231+ passing), update `manual_verification.md`, update
   `docs/API.md` (§3.11 + admin §) and the next status report.

## 11. Open Decisions for Review

1. Keep or trim the extra existing beta operators (§8) — recommend **keep**.
2. `icao`/`iata` optional-for-new-types vs strictly rejected — recommend **rejected** (with per-type validation).
3. Add `ground-ops` / `airport-ops` role tokens now (§6) — recommend **yes** for the new beta tenants.
4. Future `cargo` type separate from `airline` — recommend **defer** (not needed for beta).

*End of spec.*
