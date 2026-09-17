# AviaSAFE Platform — Architectural Discovery Report

Discovered from shipped code, committed migrations, git history and on-disk layout.
Repository: `D:\Projects\aviasafesms` (single monorepo, no git remote configured at scan time).
Compiled date: 2026-09-16. Every statement below cites the file/path it was derived from.

> Purpose: single input for a re-organization into 3 modules
> (A. Survey / SMS Health, B. Hazard & Risk, C. State Regulator / PSOE) plus
> 4 role-scoped dashboards. This report maps what exists and where the seams are,
> and flags every place where a naive re-organization would break something.

---

## 1. Capability inventory

### 1.1 Stack
- Backend: Python FastAPI, async. `backend/app/main.py` (app title "AviaSAFE SMS API — Safety Climate Measurement System - ICAO Annex 19 Compliant", version from `API_VERSION` default `1.0.0`, `backend/app/core/config.py:33`).
- ORM data layer: SQLAlchemy 2.x, asyncpg (async engine, `NullPool`) + a legacy *sync* `pg.py` bridge that serializes through a dedicated bridge loop (`backend/app/db/session.py`, `backend/app/db/runner.py`, `backend/app/db/pg.py`).
- Database: PostgreSQL on Supabase (remote schema snapshot committed as `supabase/migrations/20260830130516_remote_schema.sql`); TRANSACTION pooler on port 6543 for Render (`backend/app/core/config.py:78-85`, `backend/app/db/session.py:10-21`).
- Auth: Firebase (Auth + Identity Toolkit REST for server-side password login; Firestore *removed* from the data plane, B4/phase A-C, `backend/app/firebase.py`, git fe2032b/9a6e1f3/5310192/f788700).
- Cache/rate-limit: Upstash Redis when `REDIS_URL` set, else rate limiting disabled (`backend/app/middleware/rate_limit.py:17-22`).
- AI: Gemini (`AI_MODEL=gemini-2.0-pro-exp-02-05`) for narrative/assessment; Groq (`openai/gpt-oss-120b`) for the Copilot chat widget (`backend/app/core/config.py:116-128`).
- Email: SMTP / SendGrid (config-selectable, default "none"/log) + dedicated Gmail REST dispatcher (OAuth2 refresh token) for registration acknowledgments (`backend/app/core/config.py:204-227`, `services/gmail_dispatcher.py`).
- Contact form: Sender.net REST API v2 (`backend/app/core/config.py:229-237`).
- Scheduler: APScheduler background jobs (`backend/app/core/lifecycle.py` — start_scheduler/stop_scheduler in lifespan, `backend/app/main.py:53-59`).
- Frontend: static HTML+JS (Firebase CDN, Tailwind-style) under `public/` plus a *vestigial* Astro shell (`src/pages/index.astro` only; `astro.config.mjs`). No bundler for the real app — classic `<script>` files.

### 1.2 Backend source layout (on-disk counts)
- `backend/app/main.py` — app assembly, CORS, error envelopes, health endpoints.
- `backend/app/routes/*.py` — 23 top-level routers (listed below).
- `backend/app/api/v1/*.py` — CAAN-oversight sub-API (8 route modules + present-but-unmounted `hazard_analysis.py`), assembled in `backend/app/api/v1/router.py`.
- `backend/app/services/*.py` — 46 services + `__init__.py`.
- `backend/app/models/*.py` — 14 Pydantic models + `__init__.py`.
- `backend/app/schemas/*.py` — 6 inbound/outbound schemas + `__init__.py` (`audit`, `dlq`, `hazard_rca`, `oversight`, `tenant_sms`, `user`).
- `backend/app/middleware/*.py` — `app_check`, `auth`, `rate_limit`, `rbac_middleware`, `tenant_status_cache`.
- `backend/app/core/*.py` — `config`, `cors`, `lifecycle`, `logging`, `metrics`, `perf`, `rbac`, `security`.
- `backend/app/db/*.py` — `db_models` (ORM), `schema.sql`, `session`, `pg`, `pg_query`, `runner`, `ids`, `isolation`, `schema_init`.
- `backend/app/repositories/audit_repo.py` — single repository layer.
- `backend/app/workers/*.py` — `escalation_worker`, `report_worker`, `scheduler`, `tenant_scheduler`.
- `backend/app/data/` — reference datasets incl. `psoe_appendix10.json` and taxonomy CSVs (relocated 2026-09-13, git 76d6342).
- `backend/app/templates/welcome_email.html` — email template.

### 1.3 Frontend layout
- `public/*.html` — 87+ HTML pages, `public/js/*` — 62 classic JS files (subagent inventory, task dr2…; recomputed on disk 2026-09-16).
- `src/pages/index.astro` — only Astro page (monorepo marketing-star merge 2026-07-18, git 9b0fbf9). The Astro layer is effectively unused by the product runtime.
- `firebase.json` / `.firebase/` — legacy Firebase Hosting config retained.

### 1.4 Data / infra layout
- `supabase/migrations/` — 5 committed migrations (see Section 3).
- `scripts/` — migration/ops scripts (incl. `migrate_firestore_to_supabase.py`, `supabase_rls.sql`), legacy pre-A-series scripts deprecated (git d519419).
- `tests/e2e/` — 9 end-to-end scripts; `backend/tests/` — 54 `test_*.py` + `conftest.py`, `pg_bridge.py`.

### 1.5 Authentication & identity
- Firebase ID tokens (RS256) verified server-side; role/tenant come from Firebase custom claims with 3 fallbacks: claims → Postgres `tenants.safety_manager` email lookup → email-domain→slug map (`backend/app/middleware/auth.py:52-77`).
- Roles (canonical + legacy aliases): TENANT_ADMIN (alias AIRLINE_ADMIN), DEPT_ADMIN, SAFETY_OFFICER, STAFF (alias USER), CAAN_SMD, SUPER_ADMIN (`backend/app/core/config.py:14-28`).
- Tenants are multi-tenant isolated by `tenant_id` (deterministic `uuid5('tenant:'+slug)`, `backend/app/db/ids.py`, `db/pg.py _deterministic_tenant_id`, git 1e805ab). SUSPENDED-tenant lock-out is fail-open (`middleware/auth.py:86-90`).

### 1.6 RBAC (module-gated)
- `core/rbac.py` PERMISSIONS: tenant_admin → module1,2,3,settings; safety_manager → 1,2,3; department_head → module2; employee → module2; regulator → module5. MODULE_ENDPOINTS: m1 `/maturity`,`/survey`; m2 `/hazards`,`/sram`,`/cans`,`/caps`,`/reports`; m3 `/safety`,`/dashboard`; m5 `/regulator`,`/industry`,`/aggregation`,`/benchmark`; settings `/settings`,`/admin/tenants` (`backend/app/core/rbac.py:4-28`).
- Middleware maps URL prefix → module; unknown prefixes pass unguarded (`backend/app/middleware/rbac_middleware.py:8-20`, 36-45). Regulator restricted to module5 (54-55).
- Note: PSOE, SPI, N-HRC, state-risk, sdc and copilot are NOT in MODULE_ENDPOINTS → the backend RBAC middleware does not guard them; frontend gates PSOE on tenant `module3` (git e840bad). This backend/frontend module-model mismatch is a seam to preserve or reconcile.

### 1.7 Isolation
- `db/isolation.py:demo_scope()` — `is_demo` stamped on writes and filtered on reads whenever ENVIRONMENT != "production"; `backend/app/main.py` CORS merge in `_allowed_origins()`.
- Destructive admin endpoints return 404 when `DISABLE_DESTRUCTIVE_ENDPOINTS=True` (default) (`core/config.py:190`).

### 1.8 Rate limiting (Upstash Redis)
- Fixed window: vsr_submit 50/day, mor_submit 20/day, survey_submit per-tenant (configurable override), dashboard 500/h, auth_attempts 200/h, register_tenant 5/h, join_team 30/h, invite 20/h, register 10/h, copilot 120/h, sdc_validate 200/h, sdc_ingest 100/h, data_query 600/h (`backend/app/middleware/rate_limit.py:45-59`).
- Sliding window: login_failures (default 20/15min/IP), register_tenant, verify_invite, copilot_guest (`rate_limit.py:72-77`). Precedence: tenant survey_rate_limit config → global (`rate_limit.py:104-106`).

### 1.9 Scheduled jobs
- Weekly SSP dispatch, monthly SMS/SRB tenant dispatch, daily DLQ replay (`main.py:53`, `core/lifecycle.py`), overdue-CAP check endpoint `POST /check-overdue-caps` (`routes/scheduled_jobs.py:36`), worker modules under `workers/`.

### 1.10 Notifications / email
- Welcome email (SMTP/SendGrid), self-service registration acknowledgment (Gmail REST), CAN/CAP notification + overdue job (git c0cf4c5), internal task key `X-Task-Key` shared secret (`core/config.py:183`).

### 1.11 CORS / frontends served
- Canonical origins: sms.aviasafesystems.com, aerosafety-sms-prod.web.app, demo.aviasafesystems.com, smssurvey.gsacharya.com, sms.nac.com.np, ssp.caanepal.gov.np (`main.py:26-34`). Two-layer CORS: CORSMiddleware + ManualCORSMiddleware to guarantee ACAO on real responses and on error envelopes (`core/cors.py`, git 480c92a/1c10b95).

### 1.12 Health/observability
- `/` root, `/health` (db+firebase+commit), `/live`, `/ready` (`main.py:275-328`). Prometheus `/metrics` from `core/metrics.py` (auth-gated — git 200bee5). Perf instrumentation middleware emits `[PERF]` lines + `X-Perf` headers (`core/perf.py`, git 91462bc/a3c6bde); slow-SQL log primitive (`db/pg.py _SLOW_SQL_MS` default 250 ms).

### 1.13 Seed & demo dataset
- Production-format seeding (`services/production_seed.py`, `unified seeder`, `ONBOARDING_HAZARD_SEED`), demo datasets incl. 12-month realistic demo per tenant with 204 SMS-maturity surveys (git 521cb33/a2e4e02), archetype seeding (`services/archetype_scope.py`), beta self-service sandbox with auto-expiry (`core/config.py:194`, `Tenant.is_beta_sandbox`), demo session/analytics endpoints (`routes/demo.py`, prefix `/api/v1/demo`).

### 1.14 Payments/billing
- None. Tenants/regulators carry `subscription_status/start/end`, `module_access`, `is_saas_customer` (Commercial lifecycle toggles only — git 5096db4). No payment processor.

### 1.15 File ingress/outgress
- PDF export: quarterly/annual regulatory reports, PSOE assessment export, regulator dashboard PDF/Excel, tenant SMS/SRB PDFs (`services/pdf_generator.py`, `pdf_canvas.py`, `tenant_pdf_generator.py`, `report_generator.py`). No generic upload endpoints discovered (SDC ingests mapped records via JSON API, not files).

### 1.16 Identity for interop
- Not applicable as a separate service; identity is the Firebase user pool + `uid` on `users` table.

### 1.17 Integration hands-off
- No payment, LLM is internal (Gemini/Groq), no external ticketing/ERP discovered. Contact → Sender.net, feedback → internal `feedback` table (+ Cloudflare Worker history. `feedback.js` targets `/api/v1/feedback`).

---

## 2. Backend route map

Assembled from `backend/app/main.py:223-273` (mount points) + `backend/app/api/v1/router.py` + per-file `@router.*` decorators. Legacy mounts (`include_in_schema=False`) re-serve the same routers under `/api/*`. `P` = canonical prefix, `L` = hidden legacy prefix.

### 2.1 Top-level routers (routes/)
| Router file | Prefix(es) | Methods & paths (line) |
|---|---|---|
| `auth.py` | P `/api/v1/auth`, L `/api/auth` | POST /login, /verify, /register, /refresh, /register-tenant, /invite, /join-team, /join; GET /verify-invite, /invites, /tenant-lookup, /me; PATCH /me |
| `reports.py` | P `/api/v1/reports`, L `/api/reports` | includes `occurrence_reports` (see 2.2) + `reporting` (see 2.2); `reports.py:17-27` |
| `dashboard.py` | P `/api/v1/dashboard`, L `/api/dashboard` | GET /overview, /recent, /risk, /trends, /risk-trends, /hazards, /actions, /master-register, /airline/sms-maturity, /caan/overview, /caan/trends, /caan/risk, /caan/hazards, /caan/survey-maturity, /caan/state, /caan/sms-maturity-assessment, /caan/benchmark, /admin/system, /admin/tenants, /admin/usage |
| `admin.py` | P `/api/v1/admin`, L `/api/admin` | GET/PUT /risk-matrix; POST /setup-claims, /provision-airlines, /fix-tenant-ids, /create-seed-users, /seed-demo-data, /regulators, /tenants, /tenants/bulk, /tenants/check-email, /tasks/check-overdue, /tenants/{tid}/reset-password, /{tid}/send-welcome, /{tid}/status, /{tid}/modules, /regulators/{rid}/status; GET /regulators, /seed/logs, /tenants, /tenants/{tid}/credentials; PATCH /tenants/{tid}, /regulators/{rid}, /users (+ DELETE per cascade deletes, git d5f28c8) |
| `hazards.py` | P `/api/v1/hazards`, L `/api/hazards` | POST / (30), GET / (62), GET /stats (109), GET /{hazard_id} (118), PUT /{hazard_id} (131), PATCH /{hazard_id}/status (153), PATCH /{hazard_id}/assign (167), POST /{hazard_id}/sram/calculate (212), PUT /{hazard_id}/sram/save (246) |
| `can_cap.py` | P `/api/v1/cans`, L `/api/cans` | POST /; GET /; GET /stats; GET /caps; GET /{can_id}; PATCH /{can_id}/status; DELETE /{can_id}; POST /{can_id}/caps; GET /{can_id}/caps; GET /caps/{cap_id}; PATCH /caps/{cap_id}; PATCH /caps/{cap_id}/review; PATCH /caps/{cap_id}/status |
| `verification.py` | P `/api/v1/verification`, L `/api/verification` | POST/GET /hazards/{id}/verifications (22,38); GET /verifications/stats (48); GET /verifications/{vid} (57); POST/GET /hazards/{id}/closure (72,88); PATCH /hazards/{id}/reopen (103) |
| `reporting.py` | P `/api/v1/reporting`, L `/api/reporting`, **also** hidden `/aggregated` under reports | POST/GET /quarterly (182,218), GET /quarterly/{id} (230), GET /quarterly/{id}/export (248), POST/GET /annual (266,301), GET /annual/{id} (313), GET /annual/{id}/export (331) |
| `flight_diversions.py` | P `/api/v1/flight-diversions`, L `/api/flight-diversions` | POST /, GET /, GET /stats, GET /{id}, PATCH /{id}, DELETE /{id}, POST /{id}/link-hazard, DELETE /{id}/link-hazard |
| `state_risk.py` | P `/api/v1/state-risk`, L `/api/state-risk` | GET /register (29), GET /aggregate (47), POST /sync (61), PUT /register/{id}/ssp-target (76) |
| `surveys.py` | P `/api/v1/surveys`, L `/api/surveys` | POST / (149) survey submission (scoring done server-side) |
| `tenants.py` | P `/api/v1/tenants`, L `/api/tenants` | GET /{tid}/config (99), GET /{tid} (145), GET /{tid}/users (175), PUT /{tid}/config (204) |
| `regulators.py` | P `/api/v1/regulators` | GET "" (29), GET /{rid} (42) |
| `contact.py` | P `/api/v1/contact` | POST "" (contact → Sender.net) |
| `feedback.py` | P `/api/v1/feedback` | POST "" (feedback) |
| `copilot.py` | P `/api/v1/copilot` | POST /chat, POST /guest/chat |
| `psoe.py` | P `/api/v1/psoe`, L `/api/psoe` | GET /template (110), GET /assessments (123), POST /assessments (179), GET /assessments/{id} (245), PATCH /assessments/{id} (279), GET /assessments/{id}/export (644, hidden) |
| `demo.py` (`demo as demo_routes`) | `/api/v1/demo` | POST /session/start, /session/action, /session/decision, /analytics/event, /analytics/batch, /accept |
| `sdc.py` | own `prefix="/api/v1/sdc"`, mounted bare (`main.py:266`) | POST /validate (171), POST /ingest (250) — SDC = aviaSDCPS Safety Data ingest into hazards/reports/cans/caps (`routes/sdc.py:1-14`) |
| `data.py` | own `prefix="/api/v1/data"`, mounted bare | POST /query — "Universal Data Query" |
| `scheduled_jobs.py` | bare (`main.py:268`) | POST /check-overdue-caps (36) |
| `regulator_dashboard.py` | `/api/v1/regulator` (`main.py:269`) | GET /industry-averages, /top-hazards, /risk-trends, /risk-register, /benchmark/{tenant_id}, /export/pdf, /export/excel |
| `occurrence_reports.py` | only reachable via `reports.py` (not in `main.py` imports) | POST / (87), POST /mor (115), POST /vsr (175), GET / (225), GET /{report_id} (242), PUT /{report_id}/risk-assessment (259) |

### 2.2 Composite router `reports.py` (sub-inclusions)
`backend/app/routes/reports.py:17-27`:
- `occurrence_reports` included twice: plain (reaches `/api/v1/reports/...`) AND hidden `/occurrences` prefix.
- `reporting` included twice: plain (reaches `/api/v1/reports/quarterly…`) AND hidden `/aggregated` prefix.
⇒ Every VSR/MOR and quarterly/annual route is reachable under two paths; the hidden aliases exist for backward-compat.

### 2.3 `api/v1` router (`backend/app/api/v1/router.py`) — mounted at `/api/v1`
| Module | Prefix | Endpoints (line) |
|---|---|---|
| `state_risk.py` | `/state-risk` | GET /aggregate (19), GET /export-pdf (55), POST /dispatch-email, GET /audit-logs — **collides with `routes/state_risk.py` GET /aggregate (line 47) served first** (routes mounted at `main.py:247`, v1 at `main.py:271`) → the v1 `/aggregate` handler is shadowed dead code |
| `cron.py` | `/cron` | POST /weekly-ssp-dispatch, /dlq/replay/{dlq_id}, /dlq/discard/{dlq_id} |
| `tenant_reports.py` | `/tenants` | GET/POST /monthly-summary, /export-pdf, /dispatch-srb, /audit-logs |
| `endpoints/tenants.py` | `/tenants` | POST /onboard (42) |
| `nhrc.py` | (none) | GET /tenant/{tid}/kpis, /state/kpis, /mapping-rules, /seis/{nhrc}, /contributing-factors/{nhrc} — N-HRC = National High-Risk Categories |
| `spi.py` | (none) | GET /definitions, /tenant/{tid}/values, /tenant/{tid}/status, /tenant/{tid}/trend, /state/values, /state/status, POST /tenant/{tid}/targets — SPI/SPT Safety Performance |
| `endpoints/sram.py` | (none) | POST /bowtie (137), GET /bowtie/{hid} (148), POST /bowtie/{id}/threat (159), /consequence (171), /control (185), POST /risk/calculate (207), /risk/accept (218), GET /barriers (239), /barriers/{hid} (248), PATCH /barriers/{id} (259), GET /risk-register/{tid} (271) — SRAM = Safety Risk Assessment & Mitigation |
| `endpoints/psoe.py` | `/supabase` | GET /questions (138), GET /assessments (152), POST /assessments (169), GET/PUT /assessments/{id} (181,192), POST /assessments/{id}/calculate (205), /complete (217), GET /report (229), POST /assessments/{id}/findings (244), PUT/DELETE /findings/{id} (258,271) — PSOE = Post Safety Oversight Evaluation |
| `hazard_analysis.py` | — | **NOT mounted** (`router.py` does not import it). Routes present: POST "", /{hazard_id}/rca, /{hazard_id}/assessments, /{hazard_id}/capas. Confirmed dead by comment in `services/hazard_service.py` (“the unmounted hazard_analysis router”). |

### 2.4 Health / metrics / roots
`GET|HEAD /`, `GET|HEAD /health`, `/live`, `/ready` (`main.py:275-328`); `metrics_router` `/metrics` (empty prefix, `main.py:273`).

### 2.5 Route-map coverage notes
- 23 top-level routers + 8 active v1 modules + metrics = ~32 router files; ~190 first-party endpoints (before legacy aliases double them).
- Every `*_LEGACY` mount doubles auth, reports, dashboard, admin, hazards, cans, verification, reporting, flight-diversions, state-risk, surveys, tenants, psoe.
- SDC router carries its own absolute prefix (`/api/v1/sdc`) while being mounted without prefix — single-path, safe.
- `routes/tenants.py` GET /{tid} coexists with v1 `/tenants/monthly-summary` etc. under the same prefix — no literal collision because of path shapes, but grouping ambiguity for a re-org.

---

## 3. Data model map

Sources: `backend/app/db/schema.sql` (authoritative intent), `backend/app/db/db_models.py` (ORM), `supabase/migrations/*.sql` (applied DDL). Conventions (schema.sql header): every business table carries mandatory `tenant_id UUID NOT NULL`; composite objects stored as JSONB; `id` = `gen_random_uuid()`.

### 3.1 Core relational tables (schema.sql §1-15 == live remote schema 2026-08-30)
1. **hazards** — hazard_id (text, tenant-unique), function, taxonomy (4-value ICAO), severity/probability/risk_index, priority H/M/L, srm_* flags + sram_data JSONB, status, workflow stamps; `ux_hazards_tenant_id` unique.
2. **reports** (VSR/MOR, unified; report_type voluntary|mandatory) — narrative, occurrence, ICAO ADREP-ish aircraft/engine/flight/casualty fields, human_factors/contributing_factors JSONB, risk_assessment/ai_* JSONB, reporter block, MOR-only block (etops, fdr…).
3. **cans** — CAN per hazard (hazard_id UUID FK hazards.id), issuance block (SM 8.8.2), signature JSONB pair (issued_by/reviewed), `psoe_assessment_id` added later (migration 20260901130000), initial_* risk columns.
4. **caps** — CAP per CAN (FK cans.id), plan fields, CAP template blocks (company/base/finding/file_ref, 5.1(1)-(5) RCA sections), residual_* risk, root_causes/action_items JSONB, rca_method, sram_data, AE escalation block, closing block + signatures (closed_signature, po_/ma_signature in ORM).
5. **surveys** (scored) — answers/question_scores/element_scores JSONB, 4 ICAO pillar scores + overall_sms_maturity + overall_score_pct.
6. **survey_responses** (raw audit copy) — answers JSONB.
7. **corrective_actions** — generic action ledger referencing hazard_id/can_id/event_id (polymorphic).
8. **risk_register** — legacy per-hazard SRM: hazard_id UUID FK hazards.id, srm_date, ultimate_consequence, existing_*/resultant_* severity/probability/index/tolerability. **This is the shape live in the remote schema AND in `models/risk_register.py`.**
9. **safety_deficiencies** — event_id polymorphic, taxonomy_main/type/specific, unsafe_event, priority/severity, status, csd_remarks.
10. **flight_diversions** — diversion per flight, fuel cost/passenger impact/delay, optional hazard link.
11. **verifications** (CAP effectiveness) — hazard_id + cap_id FKs, outcome/evidence, revision.
12. **closures** — hazard closure: lessons_learned/recommendations, approved_by stamps.
13. **state_risk_register** (SSP) — icoc_category, current_risk_index 1-25, tolerability tier, ssp_target/actual, trend, contributing_tenants JSONB, quarter/year.
14. **psoe_assessments** — CAAN Appendix 10: title/status/department/auditor, responses + component_scores JSONB, overall_score_pct/level.
15. **regulatory_reports** — quarterly/annual generated reports: period/year/quarter, summary+data JSONB, file_url.

### 3.2 v2 ICAO/HFACS RCA set (ORM + live remote schema; §F above hazards)
- **hazard_rca_entries** (resource_id business ref, source_type, functional_area, risk_summary/hfacs_summary JSONB), **hazard_rca_factors** (entry_id FK, tier/category/subcategory/nanocode), **hazard_assessments**, **hazard_capas**. These are document-shaped and keyed by `resource_id` (HAZ-…/rca_…/asm_…/capa_…).

### 3.3 SRAM table set (ORM + migration 20260905153000_sram_tables.sql)
- **bow_tie_analyses** (tenant-unique per hazard_id text), **bow_tie_threats**, **bow_tie_consequences** (severity letters A-E), **bow_tie_controls** (preventive|recovery), **barrier_register** (BSV = Barrier Strength Value, 7 element scores), and **risk_register re-declared** in SRAM shape: hazard_id TEXT, bowtie_id FK, probability_current/severity_current/risk_index_current/tolerability_current + resultant (letters A-E), accepted/alarp_justification/review_date.

### 3.4 PSOE sub-tables (ORM + migration 20260905153000_psoe_audit_complete.sql)
- **psoe_questions** (4 components, 21 questions), **psoe_findings** (definition/observation/… finding types, statuses, FK psoe_assessments.id CASCADE).

### 3.5 Domain / migration tables defined only in `db_models.py` (Firestore→PG Batch 0, git ce9a322)
- **tenants** (PK = deterministic uuid5(tenant:slug); slug unique; safety_manager JSONB; module_access/modules JSONB; oversight fields; `data` JSONB bag), **regulators** (operator_tenant_ids JSONB, module_access default all-modules-false, subscription fields), **users** (uid/email unique, role, tenant_id FK tenants.id, department, is_developer), **audit_logs**, **sms_dispatches**, **audit_dispatches**, **invites** (code PK), **feedback**, **caan_reports** (report_id), **sms_maturity** (tenant_id+days unique), **state_risk_categories** (slug PK), **dead_letter_queue** (key unique).
- `caan_reports` therefore EXISTS in the ORM + pg.py registry (`backend/app/db/pg.py:44`) — earlier “referenced-but-undefined” suspicion is refuted; it is simply absent from `schema.sql`.
- **demo_contract_acceptances** — created at runtime by `routes/demo.py` (demo-only CREATE TABLE + INSERT), not in any schema file.

### 3.6 RLS
All 15 core tables + SRAM tables have per-tenant RLS policies `p_<table>_tenant_isolation` (remote_schema 2026-08-30; sram migration adds its own DO-block). Grants: GRANT ALL to anon/authenticated/service_role (broad, but RLS is the gate).

### 3.7 Schema conflict log (subject of Section 9 open questions)
- **risk_register has two incompatible definitions:**
  1. legacy per-hazard SRM (`schema.sql` + `models/risk_register.py` + remote live schema 2026-08-30): `hazard_id UUID NOT NULL REFERENCES hazards`, `existing_*`, `srm_date`, `ultimate_consequence`.
  2. SRAM (`db_models.RiskRegisterEntry` + migration 20260905153000, `CREATE TABLE IF NOT EXISTS`): `hazard_id TEXT`, `bowtie_id FK`, `probability_current/severity_current`…, `accepted`/`alarp_justification`.
  - The SRAM migration silently NO-OPs on any DB that already has the legacy table. SRAM reads/writes use `RiskRegisterEntry` (`services/sram_service.py:452-467`), so **scratch tables created via `create_all` (tests) get SRAM shape; the live 08-30 schema has legacy shape** — runtime column mismatch is probable unless a later uncommitted DDL re-shaped it. MUST verify against the live Supabase DB before treating SRAM as production-safe.
- **caps signatures**: live remote schema has `ae_signature TEXT`, `closed_signature TEXT`; `schema.sql`/ORM use JSONB. Fixed at ORM level 2026-09-07 (git d0fb551) — live table state UNKNOWN.
- **hazards ICAO columns** (function, threat, top_event, flags, dates, taxonomy check) added by migration 20260905090000; present in live schema snapshot 08-30 for `cans`/`caps`/`risk_register` only as far as that snapshot shows; hazard columns arrived via migration (correct order).
- **psoe_questions / psoe_findings / bow_tie_* / barrier_register** exist in ORM + migrations but are absent from `schema.sql` (schema.sql predates them).

### 3.8 Table → module affinity (for re-org)
- Module A (Survey/SMS Health): surveys, survey_responses, sms_maturity, (survey config in tenants.data).
- Module B (Hazard & Risk): hazards, reports (VSR/MOR), cans, caps, verifications, closures, corrective_actions, safety_deficiencies, flight_diversions, risk_register (both shapes!), bow_tie_* + barrier_register, hazard_rca_* set.
- Module C (State Regulator/PSOE): state_risk_register, state_risk_categories, psoe_assessments/questions/findings, regulatory_reports, regulators, caan_reports, audit_dispatches, dead_letter_queue (dispatch machinery).
- Platform/shared: tenants, users, invites, audit_logs, sms_dispatches, feedback.

---

## 4. Module boundary analysis (code → target modules)

Analysis of services files enumerated in Section 1.2 (46 services).

### 4.1 Module A — Survey / SMS Health
- Services: `survey_scoring` (ICAO 4-pillar scoring), `severity_service` (severity auto-assignment), `master_register` (read), `onboarding_service`? (hazard seed — split), survey analytics live in `dashboard_service` (via /airline/sms-maturity), `tenants` config + `/survey` submission.
- Tables: surveys, survey_responses, sms_maturity (+ survey config JSONB on tenants).
- Routing: `routes/surveys.py`, part of `routes/dashboard.py` (`/airline/sms-maturity`, `/trends`), tenant survey config `routes/tenants.py`.

### 4.2 Module B — Hazard & Risk
- Services: `hazard_service` (unmounted-router legacy), `can_cap_service`, `verification_service`, `sram_service`, `srm_engine`, `risk_calculator`, `risk_matrix`, `state_machine` (hazard/CAN/CAP lifecycle), `escalation_service` (+`escalation_worker`), `flight_diversion_service`, `report_service`, `master_register`.
- Routing: hazards, can_cap, verification, occurrence_reports/reporting (composite), flight_diversions, sdc (ingest into this domain), sram (v1), hazard_analysis (unmounted).
- Tables: hazard & risk cluster (3.8 Module B).

### 4.3 Module C — State Regulator / PSOE
- Services: `psoe_service`, `psoe_complete_service`, `state_risk_service`, `spi_service`, `nhrc_service`, `regulator_service`, `aggregation_service`, `report_generator`, `tenant_pdf_generator` (SRB dispatch), `audit_service` + `audit_repo`, `dlq_service`, `gmail_dispatcher`, `email_service` (dispatch channels).
- Routing: `psoe.py` + v1 `endpoints/psoe.py`, `state_risk.py` + v1 `state_risk.py`, `spi.py`, `nhrc.py`, `tenant_reports.py`, `regulator_dashboard.py`, `scheduled_jobs.py`, DSL: v1 `cron.py`.
- Tables: state risk, PSOE, regulatory, dispatch cluster.

### 4.4 Shared / platform (pulled by all three)
- Identity: `login_service`, `users`, `invites`, `tenant_registration`, `tenant_service`, `tenant_credentials`, `onboarding_service`, auth middleware, `tenant_status_cache`, `app_check`.
- Admin/SaaS: `admin_data_service`, `production_seed`, `seed_surfaces`, `tenant_service`, `regulator_service`, archetype scope.
- Cross-cutting: `dashboard_service` (biggest tenant-SMS surface), `ai_copilot`/`gemini`/`groq_copilot`, `metrics_service`, `pg_cache`/`repository`, `db_*` layer.
- **Shared worker pool**: `workers/*` touches B and C (dispatch + escalation + DLQ).

### 4.5 Services that straddle module boundaries (decomposition items)
- `dashboard_service` — feeds tenant dashboard AND CAAN dashboards (`/caan/*`) AND admin usage/system. One service, 3 audiences.
- `admin_data_service` — delete/purge/seed logic enumerates *every* domain table incl. SRAM + state risk + PSOE (`services/admin_data_service.py:1012-1013,1100-1104,1177-1180,1387-1389`). Purge order respects FKs — must own a FK inventory.
- `master_register` — aggregates hazards/cans/caps/verifications across B.
- `aggregation_service` — CAAN-industry aggregation reads B (hazards/reports/CANs) to serve C. One of the top cross-module couplings.
- `metadata/rumour`: `report_service` vs `report_generator` vs `tenant_pdf_generator` — three different "report" abstractions.

---

## 5. Coupling hotspots

1. **`risk_register` two-module tug-of-war** (Section 3.7 #1): legacy per-hazard SRM (hazards module) vs SRAM current/resultant+bowtie (SRAM module) on the SAME table/name. Highest-severity re-org blocker; must be resolved before splitting modules.
2. **Unified `/api/v1/reports` composite** — `occurrence_reports` + `reporting` mounted under reports AND `@/api/v1/reporting` AND hidden prefixes: a single path namespace owned by 3 route files.
3. **Duplicate `/api/v1/state-risk/aggregate`** — `routes/state_risk.py:47` vs `api/v1/state_risk.py:19`; earlier registration wins (`main.py:247` before `main.py:271`), the v1 handler is shadowed. Two parallel "state risk" implementations (`services/state_risk_service.py` classic vs `api/v1/state_risk.py` inline).
4. **Two data-access modes** — async `session_scope()` vs sync `pg.py` bridge (`db/runner.py` loop, `get_bridge_session`). Same service may mix both. Commits c7abba5/0a3fcdc/f4ee77d show deadlock and connection-reuse fixes here — this seam is live and subtle.
5. **RBAC model mismatch** — backend PERMISSIONS uses `/safety`,`/dashboard` for module3 while the frontend gates PSOE on module3 (git e840bad); PSOE/SPI/NHRC/state-risk endpoints are *not* guarded by the RBAC middleware at all. Module split must re-derive permissions per new module.
6. **`demo_scope()` vs `is_demo` columns** — every table with `is_demo` must be filtered by the same rule; SDC ingestion and admin purge rely on enumerating them explicitly (`admin_data_service.py`). Adding tables without `is_demo` breaks purge/scope symmetry.
7. **Frontend ↔ API tight coupling** — public pages call many endpoints directly (see Section 7); renames/moves break un-bundled static JS. Prior incidents: endpoint trailing-slash mismatches (git 33af228), 422 page_size caps (b675104), cold boot retries (36f63f3).
8. **`reports` (VSR/MOR) double duty** — one table feeds: occurrence workflows, dashboard risk heat maps, regulator aggregation, master register, AI analysis. Pervasive join point.
9. **CORS/error envelope coupling** — ManualCORSMiddleware + `_error_body` contract (success/detail/errors/request_id) is depended on by legacy `include_in_schema=False` endpoints and the frontend error parsing.

---

## 6. Test coverage map

### 6.1 Backend unit/integration (`backend/tests/`, 54 `test_*.py` + `conftest.py` + `pg_bridge.py`)
Grouped by target surface:
- **Auth/identity/RBAC**: test_auth, test_self_service_registration, test_identity_pg, test_rbac_claims, test_dept_admin_rbac, test_security_boundaries, test_anti_spam_guardrails, test_seed_beta_config, test_seed_scope.
- **Admin/SaaS lifecycle**: test_admin_credentials, test_admin_export, test_admin_feedback, test_admin_granular_purge, test_admin_seed, test_admin_tenants, test_admin_user_password, test_delete_demo_tenants, test_purge_demo_data, test_purge_unified_demo, test_seed_scope, test_unified_seeder_fix.
- **Hazard/Risk/SRM**: test_hazard_rca, test_risk_assessment_lifecycle, test_risk_matrix, test_srm_engine, test_severity_service, test_escalation_master_register.
- **Reports/occurrences**: test_reporting_scoping, test_master_register_optimization, test_domain_schema.
- **Survey/SMS**: test_surveys, test_survey_scoring, test_tenant_sms.
- **Regulator/CAAN**: test_spi, test_state_risk, test_psoe_models, test_psoe_complete, test_regulators, test_regulator_dashboard, test_tenants_config, test_tenants_users.
- **Foundation/misc**: test_health, test_metrics_service, test_pg_doc_mapping, test_firestore_rules_py, test_archetype_api, test_archetype_scope, test_archetype_seeding, test_demo_session, test_contact, test_copilot, test_copilot_guardrails, test_feedback, test_dashboard_risk_trends, test_gmail_dispatcher.
- Helpers: `conftest.py`, `pg_bridge.py` (test-side schema bootstrap).

### 6.2 E2E + load
- `tests/e2e/` — 9 scripts (subagent inventory, task dr2…). Purge/seed/verification focused (git 0abc43e/8e21bfc).
- `load-tests/` present on disk.
- `scripts/*test*` — 2 helper scripts.

### 6.3 Coverage gaps (observed)
- No tests found for `api/v1/endpoints/sram.py` SRAM accept/register flows, `api/v1/cron.py` dispatch, `api/v1/state_risk.py` (shadowed path), SDC ingest, SPI targets write, PSOE `/supabase` findings, `escalation_worker`, `report_worker`, tenant_scheduler dispatch, `metrics_service` endpoint auth, duplicate-route resolution.

---

## 7. Frontend map

### 7.1 Shape
- 87 HTML + 62 JS files under `public/` (subagent inventory re-checked on disk 2026-09-16). Classic script includes; Firebase CDN v9+; `firebase.js` local bootstrap (cache-busted v=2.1.0/v=4.0.1, git 9f1375f). App Check + Firebase Auth wired client-side with server-side `/api/v1/auth/verify` flow.
- Shared shell: `shell.js`, `nav-config.js` (NAV_CONFIG role-based menu, git 7293a86), `dashboard-utils.js`, `input_guard.js`, `tenant_context.js`, `department_resolver.js`, `demo-prospects.js`, `api_client` exposed on window (git 196509d).
- aviaSDCPS: 13-module SPA architecture (`public/js/views/sdc.js`, git 3b06dfe) — dedicated Safety Data collection UI driving `/api/v1/sdc/*`.

### 7.2 Known landing/beta pages (root `public/`)
- `index.html` — marketing landing (demo modal, contact CTA; ~88 inline JS lines).
- `login.html` (~413 inline JS), `register.html` (~144), `join.html` (~253) — auth/onboarding (email+password, phone, invite code self-onboarding).
- Operationally, commits document: `safety.html` (main operator workspace: hazards/CAN/CAP/AE oversight via real endpoints), `dashboard.html` (deprecated → `dashboard-kpis`/`dashboard-risk-trends`/… split, git 67e6a03), `master-register.html`, `hazard-analysis.html`, `administration.html`, `production-setup.html` (Steps 1-9 SaaS lifecycle), `maturity`/`sms-maturity*`, `caan.html`/`state-*.html` (state regulator), `psoe*.html`, `flight-diversions.html`, MOR report page, survey portals.

### 7.3 Endpoint touch pattern
Pages call `/api/v1/auth|reports|dashboard|cans|caps|hazards|verification|regulator|psoe|state-risk|spi|nhrc|tenants|surveys|sdc|data|copilot|feedback`. Tenant modules gate nav items (module2 → Risk/Hazard, module3 → PSOE per git e840bad); regulator pages restricted to module5.

### 7.4 Frontend seam for re-org
- The 4 role-scoped dashboards map to: (1) employee/guard-submission surfaces (join/login/survey portals), (2) tenant operator (safety/maturity/registers/CAN-CAP-PSOE-for-operator views), (3) CAAN regulator (caan/state/psoe/srb), (4) super-admin (administration/production-setup). Pages are flat-named; nav is config-driven via NAV_CONFIG — re-org must rewrite nav-config + page→API map, not directory layout alone.

---

## 8. Git change signal (last 90 days)

### 8.1 Timeline (single-author front ("ezondiza-dhf") from 2026-08; "TSL-2026" and "houston[bot]" earlier)
- **06-14** houston[bot] “Initial commit from Astro” → **07-18** monorepo merge (SaaS portal → marketing frontend, Astro v5 downgrade).
- **07-16 → 07-30 (TSL-2026)**: Firestore-centric Phase 1-4 (rules repair, ECCAIRS/ADREP MOR-VSR, App Check, Upstash Redis rate limits, security headers, provision endpoints, seed/fix-timestamps debugging), Render deploy, dashboards.
- **08-04 → 08-09**: migrate to Firebase project aerosafety-sms-prod (named DB `sms-db`), CAAN state risk register + survey health, tenant config, self-service registration, department mapping, escalation, master register.
- **08-09 → 08-24**: SMS maturity renaming, master registers, CAN/CAP SMSM 8.8.2 + CAA CAP form + A4 PDF, credentials scheme, Headway security audit (Chunks 9-17, SEC-01..05, storage rules), beta reset/seed scripts, TF="aviaSDCPS" SPA.
- **08-25 → 08-30**: SDC validate/ingest + Universal Data Query, single-domain decommission (betasms), is_demo isolation + Supabase DB models + root-cause routes; remote Supabase schema snapshot committed.
- **08-31 → 09-05**: PSOE→CAN persistent link + HFACS 109, **SRAM module (3453c5d)**, **PSOE Audit Complete (b170625)**, risk_register extend_existing (112c123), Super Admin + unified purge, **Postgres migration waves B0-B5 land on 09-06** (domain tables 09-06: ce9a322 Batch 0; … 95034e5 Batch 2; c041eeb/1fb0e6d/27fc615 Batch 3; 5c53b9d B3; 86cd81e B4; 89a9d10 B5 closeout).
- **09-07 → 09-09**: tenant uuid5 canonical id, JSONB signature fix, module inheritance, 12-month demo seed, nav overhaul, **RBAC Phase 5 (d08ab0a)** + Module-5 regulator dashboard (4579382), performance wave (perf 91462bc→8f03c0c, TTL cache, bridge connection reuse).
- **09-12 → 09-13**: **Firestore removal phases A/B/C** (9a6e1f3 B-remove frontend reads; 5310192 C-deprecate config; f788700 A-series admin user endpoints; fe2032b PG-seed survives; fd6c7bd hardened PG mirror; d7587c8 deployed commit SHA + returned-password regression).

### 8.2 Boundary-change / migration / hardening markers to preserve when re-org'ing
| Commit | Flag |
|---|---|
| 86cd81e / 5c53b9d / 95034e5 / ce9a322 (09-06) | Firestore→Postgres migration waves; domain-tables contract |
| 1e805ab (09-07) | tenants.id = uuid5(tenant:slug) — FK contract for ALL tenant-scoped rows |
| d0fb551 (09-07) | caps signatures JSONB hardening |
| 3453c5d (09-05) | SRAM module (creates bow_tie_*, risk_register SRAM shape) |
| b170625 (09-05) | PSOE Audit complete |
| d08ab0a (09-04) | RBAC phase 5 module layers |
| 9a6e1f3 / 5310192 / f788700 / fe2032b / fd6c7bd (09-12/13) | Firestore removal phases (rollback window until ~10-12) |
| 4579382 / df02f1b (09-04) | Module-5 regulator dashboard + route registration |
| 3755975 (08-31) | SDC validate/ingest + data query |
| 3b06dfe (08-25) | aviaSDCPS 13-module SPA |

### 8.3 Author/velocity
~320 observed commits 06-14→09-13; effectively single-author ("ezondiza-dhf") since 08-04; density peaked during migration+SRAM+PSOE (08-31→09-13). No automated CI config observed in repo tree beyond Firebase hosting workflows implied by git 94e2f5c (GitHub Actions auto-deploy).

---

## 9. Open questions / risks for the reorganization

### 9.1 Confirmed seams requiring a decision BEFORE module split
1. **`risk_register` dual-shape conflict** (3.7 #1): legacy per-hazard SRM vs SRAM registers on the same table name. Verify live DB columns (`\d risk_register`) ; if live is legacy shape, SRAM `/api/v1/sram/risk/accept` and `/risk-register` are currently failing or shadow-writing. Decide the canonical risk-register model for Module B before touching either.
2. **`/api/v1/state-risk/aggregate` duplication**: two implementations; the v1 handler is shadowed. Re-org should delete one (likely the shadowed v1 `state_risk.py`) and keep a single `StateRiskService`.
3. **RBAC/module model misalignment**: backend module3=`/safety,/dashboard` vs frontend module3=PSOE; PSOE/SPI/NHRC/state-risk/sdc/copilot unguarded by middleware. The 3-module re-org must define a *new* permission model (per-module endpoint lists) and wire it, not inherit the current gaps.
4. **Legacy `/api/*` mirrors**: 13 routers still double-mounted. Re-org is the moment to retire them, but the un-bundled frontend still targets some `/api/*` paths — confirm per-page before removal (Section 7.3).
5. **Unmounted `api/v1/hazard_analysis.py` + `services/hazard_service.py`**: dead code that duplicates the hosted `hazards.py` + `hazard_assessments/*` work. Either wire it into Module B or delete it as part of the split.

### 9.2 Data / migration risks
6. **`caan_reports`, `sms_maturity`, `state_risk_categories`, `dead_letter_queue`, `sms_dispatches`, `audit_dispatches`, `users`, `tenants`, `regulators`** exist only as ORM models + (for some) migration scripts, not schema.sql — schema.sql is stale relative to the ORM. A re-org that regenerates DDL must use the ORM as source of truth, or it will drop the domain tables.
7. **startup DDL** (`db/schema_init.py`) and commit 2ee7e55 applied ad-hoc domain DDL at runtime — confirm what runs at boot so a re-org doesn't silently stop it.
8. **Demo isolation symmetry**: purge/seed suites enumerate `is_demo` tables explicitly (`admin_data_service.py`). Adding or dropping tables during re-org must update those lists or purge breaks.
9. **Prepared-statement uniq + bridge connection semantics** (`db/session.py` unique stmt names, `pg.py` single long-lived bridge session) are PgBouncer-aware hacks; do not "busy-refactor" the data layer in the same change as the module split.

### 9.3 Process / coverage risks
10. **No tests for SRAM (v1), cron dispatch, v1 state-risk, SDC, PSOE findings, workers** (Section 6.3). Module extraction without tests will regress these silences.
11. **Single-author velocity + no observed CI config**: risk that a large re-org merge lands untested against live Supabase. Recommend a pre/post migration test on a snapshot of the live schema.
12. **Firestore rollback window**: `FIREBASE_DATABASE_ID` retained "30-day rollback" (config.py:91-95) until ~2026-10-12. Re-org should not be entangled with final Firestore removal (phases A-C in flight as of 09-13).

### 9.4 Explicitly UNKNOWN (needs human/DB input)
13. Live PostgreSQL column shapes for `risk_register`, `caps` signatures (`ae_signature`, `closed_signature`), and `hazards` ICAO columns — requires access to the Supabase DB (or `supabase db diff` output) to confirm whether the 09-05/09-07 migrations actually applied to production.
14. Whether any *other* schema exists outside `supabase/migrations/` (e.g., `scripts/supabase_rls.sql` may diverge from committed migrations).
15. Which `public/*.html` pages are currently routed/canonical vs archival — page list has drifted through nav overhauls (git 7ea001c→ea7e517); needs the human to name the live page set.
16. Exact 3rd-party endpoints for Sender.net and Gmail REST dispatcher keys are env-configured (not secrets in repo) — availability/egress needs ops confirmation.

---

*End of DISCOVERY_REPORT.md. Prepared read-only; no repository files were modified other than this report.*