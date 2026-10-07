<!--
AUTHORITATIVE COPY.
Location: D:\Projects\aviasafesms\docs\step0\Confirmation_Analysis.md
Original (historical): D:\Projects\Project_Step0_Confirmation_Analysis.md
Copied: 2026-10-07
Edits must be made here, not in the original.
-->

# Step 0 Confirmation Analysis

Technical evidence to confirm or revise the signed Step 0 decisions for the Unified Product Vision v1.0.

Status: Read-only analysis — SME decision required. No code, no migrations, no Step 1 work.
Date: 2026-10-07
Scope: `D:\Projects\aviasafesms` (analysis target), `D:\Projects\sms360x` (read-only reference).
Signed decisions under review (per instruction): G4 = keep Firebase Auth and layer an effective-dated membership model; G10 = deterministic slug as the single tenant key; G3 = one canonical `risk_register` shape.

Method note: counts below are files with at least one match, produced by recursive file search in the repo on disk. Every claim cites a path. Where the on-disk Step 0 record disagrees with the stated precondition, it is flagged in Section 4.

---

## 1. G4 — Identity & Membership Evidence

### (a) Inventory of Firebase Auth dependencies

**Backend auth core (the funnel).** Almost all token verification passes through one function.

| Path | What it does | Centrality |
|---|---|---|
| `backend/app/firebase.py:17-18` | Imports `firebase_admin`, `credentials`, `auth` | core |
| `backend/app/firebase.py:27-54` | `initialize_firebase()` — builds service-account cert from `FIREBASE_PROJECT_ID/PRIVATE_KEY/CLIENT_EMAIL/TOKEN_URI` | core |
| `backend/app/firebase.py:73-76` | `get_auth()` returns `firebase_admin.auth` | core |
| `backend/app/firebase.py:103-120` | `verify_firebase_token()` → `auth.verify_id_token(token, check_revoked=True)` (`:105`) | core |
| `backend/app/firebase.py:123-124` | `is_firebase_ready()` | core |
| `backend/app/firebase.py:127-137` | `create_custom_claims()` → `auth.update_user(uid, custom_claims=...)` (`:132`) | core |
| `backend/app/main.py:16,66` | `initialize_firebase()` in app lifespan | core |
| `backend/app/core/config.py:107-128` | Firebase project/key/client-email config + hardcoded web API key at `:120` | core |
| `backend/requirements.txt:15` | `firebase-admin>=6.6.0` | core |
| `backend/app/firebase.py:57-100` | Firestore accessors raise `NotImplementedError` (data plane removed; Auth-only) | edge (legacy stubs) |

Direct `firebase_admin` importers in `backend/app` = **5 files**: `middleware/app_check.py`, `services/tenant_credentials.py`, `services/tenant_registration.py`, `services/users.py`, `firebase.py`. Files importing `app.firebase` (the wrapper) = **24** (e.g. `middleware/auth.py:21`, `middleware/rbac_middleware.py`, `routes/auth.py`, `routes/admin.py`, `services/login_service.py`, `main.py`).

**App Check (a second Firebase dependency independent of Auth).** `backend/app/middleware/app_check.py:31-33` uses `firebase_admin.app_check.verify_token`; three dependencies (`verify_app_check`, `_strict`, `_lenient`, `:36-108`) guard registration/self-service routes (`routes/auth.py:233,286,315,436,502`). `backend/app/core/cors.py:41` allows the `X-Firebase-AppCheck` header.

**Frontend.** The Firebase SDK is loaded and driven from `public/js/firebase.js` (config at `:31-41`, dynamic SDK load at `:87-172`, App Check at `:250-385`, `getCurrentUser` at `:473-520`, claim reads at `:499,773-777,827-829`). The following counts are direct evidence of breadth:
- Files under `public/` referencing `firebase.auth`, `getIdToken`, or `onAuthStateChanged`: **49**.
- Files under `public/` referencing the SDK (`firebase.js` / `firebase-app` / `firebase-auth`): **67**.
- HTML pages reading auth state or tokens (`onAuthStateChanged`/`getIdToken`/`getIdTokenResult`): **29**.
- Token attachment for API calls: `public/js/api/client.js:31-55` (`_getToken` → `getIdToken()`), plus page-level callers (`public/js/mor.js:418`, `public/js/vsr.js:350`, `public/js/report.js:7,100,115,139,154`, `public/js/shell.js:267,1083-1084`).

**Login flow is backend-minted custom tokens.** `backend/app/services/login_service.py:41-75` calls Firebase Identity Toolkit (`accounts:signInWithPassword`) and `get_auth().create_custom_token`; `backend/app/routes/auth.py:98` returns the `custom_token`; `public/login.html:289` calls `signInWithCustomToken`.

**Config / deploy / secrets.** `firebase.json:1-129`, `.firebaserc:1-7`, `render.yaml:8-10,41-53`, `backend/.env:22`, `backend/aerosafety-sms-prod-sa.json:6`, `.github/workflows/deploy-hosting.yml` (uses `secrets.FIREBASE_TOKEN`), `scripts/firebase/*` (Node + Python Admin SDK), `package.json:39` (`firebase-admin`).

### (b) Every place identity is read

- **Token decode / claims read:** `backend/app/middleware/auth.py:124` (`verify_firebase_token`), `:133` `email`, `:134` `role`, `:135` `tenant_id`, `:136` `department`, `:149` `uid`; returns a `claims` dict at `:148-155`.
- **A second decode path:** `backend/app/middleware/rbac_middleware.py:74` (`verify_firebase_token`), reads `uid`/`email`/`role`/`tenant_id` at `:80-83`.
- **Admin route decode:** `backend/app/routes/admin.py:110-137` (`verify_task_auth` — task key or SUPER_ADMIN Firebase token); `routes/auth.py:125-147` (`/verify`).
- **Role guards (read `role`/`tenant_id`):** `middleware/auth.py:158-267` — `get_tenant_user`, `get_caan_user`, `get_admin_user`, `get_safety_manager`, `get_responsible_manager`, `get_accountable_executive`.
- **Route surface:** **32** files under `backend/app` import `app.middleware.auth`; the heaviest consumers are `routes/admin.py` (43 `Depends`), `routes/dashboard.py` (21), `routes/can_cap.py` (16), `routes/hazards.py` (16), `api/v1/endpoints/psoe.py` (14), `api/v1/endpoints/sram.py` (12), `api/v1/spi.py` (12).
- **Frontend identity reads:** `public/js/firebase.js:473-520`, `public/login.html:494-577`, `public/js/api/client.js:31-55`, `public/js/rbac.js:79-104`, `public/js/tenant_context.js` (claim-derived tenant), plus the 29 HTML pages listed above.
- **Postgres mirror:** `backend/app/db/schema_init.py:186-200` (`CREATE TABLE users (uid TEXT PRIMARY KEY, ... role, tenant_id, department, claims JSONB)`); ORM `backend/app/db/db_models.py:2183-2223` (`UserProfile`, `uid` unique, `tenant_id` FK → `tenants.id`); PK map `backend/app/db/pg.py:42` (`"users": "uid"`).

### (c) Estimate: migrate to Supabase Auth

- **Files to rewrite (backend):** the auth core and all token-issuing/verifying paths — `app/firebase.py` (verify, custom claims, user create), `middleware/auth.py`, `middleware/rbac_middleware.py`, `middleware/app_check.py`, `routes/auth.py`, `routes/admin.py`, `services/login_service.py`, `services/users.py`, `services/tenant_credentials.py`, `services/tenant_registration.py`, `core/config.py`, `main.py` (~12 files), touching the 32 files that consume the auth dependencies only if their `Depends` contract changes (it need not).
- **Files to rewrite (frontend):** `public/js/firebase.js` plus the 49 files that call `firebase.auth`/`getIdToken`/`onAuthStateChanged`, and App Check call sites (`public/js/firebase.js:250-385`).
- **Tests to update:** 7 backend files patch `verify_firebase_token`; 33 backend test files use `dependency_overrides[get_current_user]`; 39 reference Firebase/auth patterns; 6 `frontend-tests/` files stub `firebase`.
- **Data migration for existing users:** identity is mirrored in `users.uid` (Firebase uid string). Firebase Auth stores passwords as scrypt hashes; carrying them to Supabase Auth requires an export/import of hashes or a forced password reset. Custom claims (`role`, `tenant_id`) are Firebase-specific and must be re-issued. App Check (reCAPTCHA Enterprise) is Firebase-specific and has no drop-in Supabase equivalent; it must be replaced or dropped.
- **Risk to live operators:** high — a credential-migration or forced-reset event, a coordinated frontend release, and an App Check swap, all at once. `backend/app/firebase.py:105` verifies with `check_revoked=True`, so token issuance/revocation semantics change with the provider.

### (d) Estimate: keep Firebase and layer the membership model

- **New tables needed:** a `memberships` table (subject = Firebase `uid`; `scope_type` = operator/regulator/state; `scope_id`; `role_key`; `effective_from`/`effective_to`; `status`) and a role reference table. No membership/roles table exists today (searches find none; the only related structures are `users.role` and the unique AE-per-tenant index `supabase/migrations/20260920090000_users_one_ae_per_tenant.sql`).
- **What stays untouched:** `verify_firebase_token` (`backend/app/firebase.py:103`), `get_current_user` (`middleware/auth.py:120`), and every one of the 32 route files that consume the guards — provided the membership resolver returns the same `{role, tenant_id, ...}` dict the guards already expect.
- **New code needed:** a membership-resolution service that maps a Firebase `uid` to one active membership per request, then feeds `resolve_user_context` (`middleware/auth.py:60-86`); an admin surface to manage effective-dated memberships; an optional claims refresh path (`create_custom_claims`, `firebase.py:127-137`).
- **Firebase limitations that bound the model:** custom claims are coarse and size-capped and only refresh when a token is refreshed, so effective-dated history, multiple simultaneous memberships, and single-active-context selection cannot live in the token — they must be resolved from the membership table server-side (with the caching pattern already used at `middleware/tenant_status_cache`). This is a design cost, not a blocker: the current model already falls back to DB lookups (`middleware/auth.py:28-49,95-117`).

### (e) Summary — which is cheaper

Keeping Firebase and layering the membership model is materially cheaper — on the order of 5–10× less code change — and carries far lower operational risk, because it is additive (one membership table + resolver + admin UI) while leaving the verify path, the 32 consuming route files, and the 49-file frontend auth surface intact. Migrating to Supabase Auth rewrites the entire provider surface on both tiers, forces a live-operator credential/App Check cutover, and re-keys custom claims. The one thing the keep-Firebase path cannot do is put the full membership model in the token; it must resolve membership from the database per request, which the current architecture already does for tenant fallbacks.

---

## 2. G10 — Tenant Key Evidence

### (a) AviaSAFE tenant key structure

**The key is mixed: the slug is the human/identity key, and a deterministic `uuid5('tenant:'+slug)` is the storage key.**

| Element | Path | Type / value |
|---|---|---|
| `tenants.id` | `backend/app/db/db_models.py:2112`; `backend/app/db/schema_init.py:120` | `UUID PRIMARY KEY` = `uuid5('tenant:'+slug)` (comment `schema_init.py:120`) |
| `tenants.slug` | `db_models.py:2114`; `schema_init.py:122` | `TEXT NOT NULL UNIQUE` — the human key |
| `tenants.tenant_id` | `db_models.py:2113`; `schema_init.py:121` | `TEXT` — legacy slug copy; backfilled `tenant_id = slug` (`schema_init.py:164`) |
| slug→uuid derivation | `backend/app/db/ids.py:53-55` (`tenant_uuid`), `:58-62` (`register_tenant`); `backend/app/db/pg.py:194-209` (`_deterministic_tenant_id`); `pg.py:40` (`"tenants": "slug"`) | deterministic |
| claims carry the slug | `backend/app/firebase.py:131` (`create_custom_claims`); `middleware/auth.py:135`; `services/tenant_credentials.py:93` | slug |
| email-domain → slug map | `backend/app/services/tenant_service.py:33-53`; `backend/app/middleware/auth.py:80-84`; `public/js/tenant_context.js:32-100` | slug |

**Operational `tenant_id` columns are UUID** (from `supabase/migrations/20260830130516_remote_schema.sql` and `20260905153000_sram_tables.sql`): `cans:55`, `caps:98`, `closures:173`, `corrective_actions:191`, `flight_diversions:224`, `hazard_assessments:256`, `hazards:335`, `psoe_assessments:383`, `regulatory_reports:410`, `reports:434`, `risk_register:510`, `safety_deficiencies:543`, `state_risk_register:578`, `survey_responses:607`, `surveys:625`, `verifications:657`, and the SRAM tables `bow_tie_analyses:23` … `sram_risk_register` (`20260916120000_sram_risk_register.sql:16`).

**Legacy TEXT `tenant_id` columns hold the raw slug** (`backend/app/db/schema_init.py`): `users.tenant_id TEXT` (`:191`, ORM says UUID — see drift below), `audit_logs` (`:211`), `sms_dispatches` (`:223`), `audit_dispatches` (`:234`), `invites` (`:249`), `feedback` (`:263`), `caan_reports` (`:275`). Documented ORM/DDL drift: `db_models.py:2195-2197` (`UserProfile.tenant_id` Uuid FK) vs `schema_init.py:191` (`TEXT`); the ORM comment at `db_models.py:2186-2189` states the intent is uuid5 FK "NOT the slug".

**RLS predicate** (`scripts/supabase_rls.sql:37-38`, materialized at `supabase/migrations/20260830130516_remote_schema.sql:1129`; generated at `backend/app/db/schema_init.py:395-398`):
`USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid)`. The `caan_reports` policy omits the `::uuid` cast because that column is TEXT slug (`schema_init.py:888-893`).

**Confirmed: the human key is a slug** (`fixedwing`, `rotarywing`, `demoairport`, `demostate`, `buddha-air`, `caan` — `backend/seed/config.py:119`, `backend/app/db/ids.py:19-24`, `public/js/tenant_context.js:32-100`). No integer keys anywhere.

### (b) SMS360X tenant key structure

- `governance.tenants` (`D:\Projects\sms360x\supabase\migrations\20261006110352_initial_sms360x_schema_v1.sql:40-53`): `id UUID PRIMARY KEY` (caller-supplied), `operator_id UUID NOT NULL REFERENCES governance.operators(id)`, `name TEXT NOT NULL`, `UNIQUE (operator_id, name)`. **No slug or code column on the tenant.**
- Human-readable codes exist only on parents: `governance.states.code TEXT UNIQUE` (`:14`), `governance.regulators.code TEXT UNIQUE` (`:23`), `governance.operators.code TEXT UNIQUE` (`:32`).
- Every tenant reference is UUID: `governance.user_memberships.tenant_id UUID REFERENCES governance.tenants(id)` (`:121`); import (`:139,152,181`); safety (`top_events:268` … `hazard_barriers:581`); performance (`spis:596`, `safety_objectives:616`, `spts:643`). TypeScript mirrors this as `tenantId: string` (`types/sms360x.ts`).
- RLS resolves tenant to a UUID from membership, never from a hostname/slug: `supabase/migrations/20261007110000_task033c_rls_helpers.sql:60-71` (`sms360x_current_tenant_id() RETURNS uuid`); policies use `tenant_id = public.sms360x_current_tenant_id()` (`20261007110100_task033c_rls_policy_migration.sql`, e.g. `:335-338`). `lib/auth/operating-context-resolver.ts:119-126` normalizes UUIDs and treats subdomains as routing only (`docs/ADR-008` — subdomains are "never security authority").
- **Confirmed: SMS360X is UUID-only.**

### (c) Cost comparison — slug vs UUID

| Dimension | Standardise on slug | Standardise on UUID |
|---|---|---|
| AviaSAFE data migration | Low. The storage id is already `uuid5`-derived from the slug (`ids.py:53-55`), so it can be recomputed; no operational rows are re-keyed. Work is reconciling the TEXT-slug legacy columns (`users`, `audit_logs`, `caan_reports`, `invites`, `feedback`, dispatches) and the `db_models.py:2195` vs `schema_init.py:191` drift. | High. Every place the slug is the identity must move to an opaque UUID: auth claims (`firebase.py:131`), email-domain maps (`tenant_service.py:33-53`, `middleware/auth.py:80-84`, `public/js/tenant_context.js:32-100`), seeder `OPERATOR_PROFILES[].id` (`seed/config.py:119`), subdomain routing. Breaks the deterministic-slug property. |
| AviaSAFE RLS rewrite | Low. Policies already cast the JWT claim `::uuid`; a slug claim can be resolved to the derived UUID (`scripts/supabase_rls.sql:37-38`). | Medium. Same predicate shape, but the claim/authority source changes and all slug→uuid fallbacks must be replaced. |
| AviaSAFE app-code rewrite | Low–Medium (drift cleanup). | High (identity-resolution rewrite). |
| SMS360X data migration | Low. DEV schema only, no runtime data (`docs/PROJECT-STATUS.md`); add a `slug`/`code` to `governance.tenants` and backfill. | None (already UUID). |
| SMS360X RLS rewrite | Low. Keep UUID internally; add a slug→id lookup for the boundary. | None. |
| SMS360X app-code rewrite | Low. Importers already carry `tenantId` strings (`lib/import/import-orchestrator.ts:285-307`). | None. |
| Risk to live operators | Low. Preserves current login, claims, and subdomain routing. | High. Coordinated claim/routing cutover for a live product. |

### (d) Summary — which scheme is cheaper

Standardising on the slug is cheaper for the combined product, by roughly an order of magnitude of change, because AviaSAFE's human identity layer is already slug-based and its UUID is merely a deterministic derivation of the slug (`ids.py:53-55`), whereas SMS360X's UUID default would force AviaSAFE to rewrite auth claims, email/subdomain resolution, seeders, and frontend routing to opaque values. One caveat the SME must settle because it changes the answer: "single tenant key" can mean (i) the **identity/boundary key** (slug) with the deterministic `uuid5` retained as a derived internal storage id — which is essentially what AviaSAFE already does and is the low-cost path — or (ii) the **data-plane FK key** (SMS360X's UUID), which would re-key AviaSAFE's identity layer. The evidence favours keeping slug-as-identity + derived-uuid-as-storage; the decision of which layer the "single key" governs is the SME's.

---

## 3. G3 — Risk Register Dual-Shape Evidence

### (a) The two current shapes

**Original defect form:** SRAM re-declared a table named `risk_register` with `CREATE TABLE IF NOT EXISTS` (`supabase/migrations/20260905153000_sram_tables.sql:102-142`), which silently no-op'd on production because the legacy table already existed — while the ORM model was SRAM-shaped. This is documented at `DB_VERIFICATION.md:51-53`, `DISCOVERY_REPORT.md:200-203`, and `SCHEMA_DRIFT_REPORT.md:88-123`. The reconciliation plan D1 split the name into two tables.

**LEGACY shape — `public.risk_register`** (`supabase/migrations/20260830130516_remote_schema.sql:508-535`; copy at `backend/app/db/schema.sql:459-495`):
- Columns: `id uuid PK gen_random_uuid()`, `tenant_id uuid NOT NULL`, `hazard_id uuid NOT NULL FK → hazards(id)` (`remote_schema.sql:1096-1097`), `srm_date timestamptz NOT NULL`, `ultimate_consequence text NOT NULL`, `existing_severity int`, `existing_probability int`, `existing_risk_index int`, `existing_risk_tolerability text`, `resultant_severity int`, `resultant_probability int`, `resultant_risk_index int`, `resultant_risk_tolerability text`, `status text NOT NULL`, `follow_up_date timestamptz`, `date_completed timestamptz`, `remarks text`, `concerned_department text`, `created_by text`, `updated_by text`, `created_at`, `updated_at`; plus a live-only `is_demo` (per `DB_VERIFICATION.md:37`).
- Constraints: PK `id` (`remote_schema.sql:741-742`); four CHECKs `existing_severity/probability` and `resultant_severity/probability` each 1–5 (`:531-534`).
- Indexes: `ix_risk_register_tenant`, `_tenant_hazard`, `_tenant_srmdate`, `_tenant_status` (`:959-971`); RLS `p_risk_register_tenant_isolation` (`:1165`).

**SRAM shape — `public.sram_risk_register`** (`supabase/migrations/20260916120000_sram_risk_register.sql:14-58`, extended by `20260918090200_module_b_sram_risk_register.sql:14-52`; boot mirror `backend/app/db/schema_init.py:317-362,446-479`):
- Columns: `id uuid PK`, `tenant_id uuid NOT NULL`, `bowtie_id uuid FK → bow_tie_analyses(id)`, `hazard_id text NOT NULL` (business ref, no FK), `hazard_title text`, `probability_current int NOT NULL`, `severity_current int NOT NULL`, `risk_index_current int NOT NULL`, `tolerability_current text NOT NULL`, `probability_resultant int`, `severity_resultant int`, `risk_index_resultant int`, `tolerability_resultant text`, `status text NOT NULL DEFAULT 'open'`, `accepted boolean NOT NULL DEFAULT false`, `alarp_justification text`, `accepted_by uuid`, `accepted_on timestamptz`, `review_date timestamptz`, `is_demo boolean DEFAULT true`, `created_at`, `updated_at`; Module B adds `process_by`, `process_signed_at`, `initial_authority`, `resultant_authority`, `consequence_id uuid FK → bow_tie_consequences(id)`.
- Constraints: CHECKs severity/probability 1–5 and index 1–25 (`20260916120000...:37-45`); unique `ux_sram_risk_register_tenant_hazard` then `(tenant_id, hazard_id, consequence_id)` (`20260918090200...`); RLS `p_sram_risk_register_tenant_isolation`.

The shape families differ in **linkage** (legacy `hazard_id` is a UUID FK; SRAM `hazard_id` is text), **naming** (`existing_*`/`resultant_*` vs `*_current`/`*_resultant`), and **depth** (SRAM is bow-tie/consequence-scoped with acceptance signatures).

### (b) Models for each shape

- LEGACY: ORM `RiskRegisterLegacyEntry` (`backend/app/db/db_models.py:1449-1495`; check constants `:1301-1316`); Pydantic `backend/app/models/risk_register.py` (`RiskRegisterCreate/Update/Response` etc., `:7-57`) — **orphaned**, no importers.
- SRAM: ORM `SramRiskRegisterEntry` (`db_models.py:1498-1563`; check constants `:1317-1344`); Pydantic request/response in `backend/app/api/v1/endpoints/sram.py` (`RiskCalculation:72`, `RiskAcceptance:81`, `ProcessSignature:89`) and `SramSaveRequest` (`backend/app/models/hazard.py:182`).
- Pre-D1 the two were a single SRAM-shaped `RiskRegisterEntry` (`SCHEMA_DRIFT_REPORT.md:67,90`).

### (c) Consumers

- **SRAM shape (active):** `backend/app/services/sram_service.py` (imports `SramRiskRegisterEntry:30`; writes `:418,444-512,527,559,671-686`); `backend/app/api/v1/endpoints/sram.py` (`POST /sram/risk/calculate:213`, `/accept:241`, `/process-sign:224`, `GET /sram/risk-register/{tenant_id}:294`); `backend/app/routes/hazards.py:454-584` (save, calls `sync_consequence_register_rows:553`); `backend/app/routes/dashboard.py:350` (AE queue); `public/js/sram.js:327-394`; `public/risk-register/index.html:141,176-190`; `public/sram/index.html:611-633`; tests `backend/tests/test_hazard_service.py:24,102,249-254`, `test_domain_schema.py:194-239`, `test_purge_demo_data.py:37,137`, `test_ae_queue_api.py:41-50`, `test_ae_kpi_api.py:46`.
- **LEGACY shape (dormant):** no active read/write path. Only bookkeeping/tests — `backend/app/services/admin_data_service.py:60,1107,1393,1186` (purge, demo count, export list); `backend/scripts/seed_demo_data.py:397`; `backend/scripts/reset_to_virgin.py:82-83,152-153`; tests `test_admin_export.py:50`, `test_purge_demo_data.py:35`. `MODULE_B_CONTRACT.md:448-455` records it as "dormant legacy register … no longer written".
- **Not consumers:** `spi_service.py` reads hazards/reports/cans/caps/surveys only (`:493-551`); `state_risk_service.py` uses the Module C `state_risk_register` (`:18,117-348`); `srm_engine.py` is a pure calculation engine with no DB access.
- **Live data:** both tables are **empty**. `SCHEMA_DRIFT_REPORT.md:67` (risk_register 0 rows), `PURGE_VERIFICATION_REPORT.md:99` (`risk_register 0`, `sram_risk_register 0`), `SCHEMA_RECONCILIATION_PLAN.md:28`.

### (d) Proposed canonical schema

Recommendation-free framing, then the proposal:

- **Observation that must be surfaced to the SME:** CAAN maps two separate clauses — §2.3.5 "Risk Register" (the legacy per-hazard SRM register, `COMPLIANCE_MATRIX.md:110`) and §2.3.6.4 "Risk Matrix" (the SRAM/bow-tie register). `MODULE_B_CONTRACT.md:576-578` (Decision 3) explicitly says keep both in parallel, while the Convergence Blueprint §7 lists "Risk" as one object. So the two tables may be **two distinct regulatory objects**, not one object in two shapes. D1 already resolved the *name collision*; the remaining question is whether the objects are genuinely distinct.
- **If they are one object** (adopt the Blueprint's one-canonical-shape intent): canonical shape = the SRAM shape (`sram_risk_register`) as the single live risk register, because it is the only one with active consumers and carries the bow-tie/consequence linkage and acceptance signatures CAAN §2.3.6 requires. Columns: identity (`id uuid`, `tenant_id uuid`), linkage (`bowtie_id`, `consequence_id`, `hazard_id` — promote to UUID FK for consistency), current/resultant risk (`probability_current/resultant`, `severity_current/resultant`, `risk_index_current/resultant`, `tolerability_current/resultant`), lifecycle (`status`, `accepted`, `alarp_justification`, `accepted_by`, `accepted_on`, `review_date`), signatures (`process_by`, `process_signed_at`, `initial_authority`, `resultant_authority`), and audit (`is_demo`, `created_at`, `updated_at`). Consumers that must change: the legacy bookkeeping list in `admin_data_service.py`, `seed_demo_data.py`, `reset_to_virgin.py`, and tests `test_admin_export.py` / `test_purge_demo_data.py`; the orphaned Pydantic module `models/risk_register.py` should be retired.
- **If they are two objects:** keep both tables, but fix the shared-name/typing drift so the defect cannot recur: rename the legacy table to an explicit name (e.g. per-hazard SRM register), make legacy `hazard_id` a UUID FK consistent with SRAM, and document the object boundary in the canonical model.

### (e) Migration strategy (prose)

- **Row mapping:** none needed for correctness — both tables are empty (`PURGE_VERIFICATION_REPORT.md:99`). If any demo/staging rows exist, map legacy `existing_*` → `*_current` and legacy `resultant_*` → `*_resultant`, and derive `risk_index` = severity × probability (the SRAM rule in `sram_service`/`srm_engine`). Legacy `ultimate_consequence`/`concerned_department` have no SRAM equivalent and would need a home if retained.
- **Switchover sequencing (keep the live product working):** (1) declare the canonical shape; (2) repoint the dormant-shape bookkeeping consumers (`admin_data_service`, seed/reset scripts, tests) at the canonical table; (3) if retiring legacy, keep the table read-only for one release cycle before dropping it; (4) leave the SRAM write path (`sram_service`, `/sram/*`, `hazards.py` save) untouched throughout.
- **Rollback:** because no data moves, rollback is reverting the consumer repoints; the legacy table remains until the end of the retention cycle, then drop.
- **A noted discrepancy to fix while here:** `PURGE_VERIFICATION_REPORT.md:35` says `sram_risk_register` is not in wipe scope, but `reset_to_virgin.py:83,153` now includes it — the report is stale.

### (f) Summary — work size

The unification is **small and low-risk for data** (both tables empty, no row migration), but it is **not purely mechanical**: D1 has already separated the tables, so the residual work is (i) consumer cleanup for the dormant legacy register and (ii) an SME decision that the evidence shows is still open — whether CAAN §2.3.5 and §2.3.6.4 are one object or two. That decision is a Step 0/schema item, so G3 unification should be treated as a **Step 2 hygiene item**, with only the consumer bookkeeping eligible to start in Step 1.

---

## 4. Summary: Which signed decisions are confirmed, which are challenged

**Precondition discrepancy (report first):** the instruction states the Step 0 Decision Record is signed and G4/G10/G3 are recorded, but the file on disk (`D:\Projects\Project_Step0_Decision_Record.md`) is marked "For SME sign-off — no development until signed" (`:5`), its decision column is blank for every gate (`:39-49`), and the signature block is empty (`:57-61`). This analysis therefore treats the decisions as *stated* by the instruction, not as evidenced by the signed record. The SME should reconcile the record before acting.

| Decision | Verdict | Basis |
|---|---|---|
| G4 — keep Firebase Auth + membership layer | **Confirmed on cost; one limitation to accept** | Additive change (one membership table + resolver + admin UI) vs. rewriting ~12 backend auth files, 49 frontend files, replacing App Check, and migrating live credentials. Firebase cannot hold the full effective-dated model in custom claims, so membership must be resolved from the DB per request — the architecture already does this for tenant fallbacks. |
| G10 — deterministic slug as the single key | **Confirmed, with a scope caveat** | AviaSAFE already uses slug-as-identity with a deterministic `uuid5` storage key, so standardising on slug is low-cost; UUID would re-key AviaSAFE's identity layer. Caveat: "single key" must be defined as the identity/boundary key (slug, storing derived `uuid5`) vs. the data-plane FK key (SMS360X UUID), because the two interpretations yield different costs. |
| G3 — one canonical `risk_register` shape | **Challenged** | The evidence shows the "dual shape" is now two separate tables (D1), both empty, and they may map to two distinct CAAN clauses (§2.3.5 Risk Register vs §2.3.6.4 Risk Matrix); `MODULE_B_CONTRACT.md:576-578` already decides to keep both. The SME must decide whether they are one object (retire legacy, adopt SRAM as canonical) or two objects (keep both, fix the drift). No data migration is required either way. |

**What the SME must decide next (if anything):**
1. Reconcile the unsigned Step 0 record (or confirm the decisions are recorded elsewhere).
2. G10 scope: does "single tenant key" govern the identity/boundary layer (slug) or the data-plane FK layer (UUID)? The slug recommendation is confirmed only under the identity-layer reading.
3. G3 object count: are CAAN §2.3.5 and §2.3.6.4 one risk object or two? This determines whether the legacy `risk_register` is retired or renamed.
4. G4 limitation acceptance: confirm that membership resolution will be a per-request DB lookup (with caching) rather than a claim, since Firebase custom claims cannot carry effective-dated memberships.
