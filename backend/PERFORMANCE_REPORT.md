# AviaSAFEsms Backend — Performance Analysis & Instrumentation

Scope: all dashboard endpoints, with focus on `overview`, `recent`, `risk`,
`trends`, `risk-trends`, `hazards`, `actions`, `master-register`, `tenants`,
`regulators`, state-level (`caan/*`) and `reporting/quarterly` (tenant config).

Method: static analysis of the request path (routes -> services -> pg.py ->
bridge loop -> asyncpg) plus an index audit of `db_models.py`. Live timing is
collected with the new instrumentation described in section 1.

---

## 1. Instrumentation (added)

### 1.1 Per-request DB timing (`app/db/pg.py`)

Every `pg.*` call (see `_record_db`, `pg.py:67`) now:

- accumulates a per-request query count and cumulative DB wall time into the
  request's perf context (`db_calls`, `db_ms`);
- logs a slow-query line when a single call exceeds `AVIASAFE_SLOW_SQL_MS`
  (default **250 ms**).

```
[PERF] slow_sql op=fetch_all table=reports dur=1843ms
```

`fetch_by` funnels through `fetch_all`, so it is counted once, not twice.

### 1.2 Endpoint-level timing for every path (`app/core/perf.py`)

`PerfTimingMiddleware` now installs the timing context on **every** request
(previously only watched endpoints), so the `pg.py` wrapper reports for all
paths, not just the ten watched ones.

- Watched endpoints still log on every request.
- All other endpoints log only when they cross a threshold
  (`AVIASAFE_PERF_SLOW_MS`, default **1000 ms**) on total or cumulative DB time
  — unsupervised endpoints become visible exactly when they miss the 1 s budget.

```
[PERF] GET /api/v1/dashboard/caan/state status=200 total=1843ms uptime=52s queries=14 db=412ms
```

Env knobs: `AVIASAFE_PERF=off` (silence all), `AVIASAFE_PERF_SLOW_MS`,
`AVIASAFE_SLOW_SQL_MS`. No business logic touched; call sites report via the
existing `note_current()`/`timed()`, now joined by `note_count()`.

### 1.3 How to use it on production

1. Deploy (backend auto-deploys on push to `main`).
2. Reproduce the slowest user actions (open overview, CAAN state, regulator
   pages, Hazards, SMS maturity).
3. Grep Render logs for `[PERF] slow_sql` (pinpoints the individual queries) and
   `[PERF]` (endpoint totals + `queries=`/`db=`, plus `uptime=` to separate
   cold starts from steady-state latency).

---

## 2. Endpoint-by-endpoint findings

### 2.1 `GET /api/v1/dashboard/overview` — highest KPI risk (>1 s candidate)

- Route `routes/dashboard.py:64` -> `DashboardService.get_airline_overview`
  (`services/dashboard_service.py:105`).
- Reads **every report row** for the tenant window via
  `ReportRepository.get_all_in_range` (`services/repository.py:157`), then runs
  three full-list passes in memory: `MetricsService.calculate_kpis`,
  `calculate_ai_kpis`, `calculate_org_kpis` (`services/metrics_service.py:25,
  185, 226`). Aggregate cost scales linearly with report volume.
- Before this change the date window was applied in Python *after* fetching
  every tenant row — a full scan bounded only by `tenant_id` index, with rows
  discarded in app code (`repository.py:193-206`).
- N+1-adjacent: every other dashboard card endpoint (`/risk`, `/trends`,
  `/hazards`, `/actions`) performs its **own** `get_all_in_range`, so a page
  open bursts several identical full-window fetches. The in-process cache
  (`repository.py:110`, TTL `REPO_CACHE_TTL_SECONDS`) only helps when filters
  match exactly.

### 2.2 `GET /api/v1/dashboard/recent` — linear pagination (>1 s candidate)

- Route `routes/dashboard.py:98` -> `get_recent_reports`
  (`dashboard_service.py:346`) -> `ReportRepository.query_reports`
  (`repository.py:113`).
- `query_reports` calls `get_all_in_range` (full window) then slices and builds
  the cursor **in Python** (`repository.py:116-151`). `total`, `total_pages`
  and `has_next` all derive from `len(all_items)`, so there is no `LIMIT/OFFSET`
  or SQL `COUNT(*)`; cost grows with the whole window, not page size.

### 2.3 `GET /risk`, `/trends`, `/risk-trends`, `/hazards`, `/actions`

- Routes `routes/dashboard.py:114, 124, 134, 149, 159`; each does its own
  full-window `get_all_in_range` plus a Python aggregation pass.
- Wait-pattern for these is keyed on the same `(tenant_id, created_at)`
  shape; now bounded by the pushed date predicates (2.7).

### 2.4 CAAN state and cross-tenant reads — heaviest queries in the app

- `_caan_filter` (`dashboard_service.py:1092`) builds a **cross-tenant**
  filter: tenant_id=None, cross_tenant=True.
- `get_all_in_range` then falls back to `PgReport.is_demo == demo_scope()`
  (`repository.py:180-183`) — a scan of the entire reports table across every
  tenant, date-filtered in Python (pre-pushdown) or by `created_at >= ...`
  (post-pushdown).
- **No existing index leads with `(is_demo, created_at)`** (all report indexes
  are tenant-led, `db_models.py:255-259`), so CAAN state/overview/benchmark
  single requests can seq-scan the table.
- `get_caan_state` (`dashboard_service.py:507`) additionally resolves the
  tenant slug per report row (`_tid_to_slug`, `dashboard_service.py:565`) —
  an N+1 pattern across every report in the state view.

### 2.5 Hazards

- `HazardService` list reads are tenant-bounded via
  `ix_hazards_tenant_status` / `ix_hazards_tenant_created`
  (`db_models.py:134-136`) — healthy. Hot spots are the **join-resolution**
  loops in master register (`/master-register`, `routes/dashboard.py:169`)
  that look up CAN -> CAP and hazard -> CAN references per row; mitigated by a
  batch `collection_group` read in the Firestore path (test
  `test_cap_batch_no_n_plus_one`) but note it still does one count per type.

### 2.6 Tenants, regulators, tenant config

- `GET /api/v1/admin.../tenants` (Super Admin, `routes/admin.py:389`):
  tenant rows enumerated from Firestore, then
  `_postgres_tenant_counts` (`services/production_seed.py:494`) issues **five
  sequential `GROUP BY tenant_id` queries** — one per table
  (`hazards, reports, cans, caps, surveys`) over a single connection
  (`production_seed.py:517-529`). Correct but slow; combinable into one
  `UNION ALL` query.
- Regulators list (`routes/regulators.py:43`) resolves regulator record +
  its operator tenants per regulator — an N+1 loop over
  `operator_tenant_ids_for_regulator` (`services/regulator_service.py:41`).
- Tenant config endpoint (`GET /api/v1/tenants/{tenant_id}`, added earlier)
  is a single `pg.fetch_by(Tenant, "slug", ...)` — cheap.

### 2.7 Reporting / quarterly (tenant config)

- `routes/reporting.py:122-140`: CAAN report listing filters by
  `CaanReport.data["report_type"].astext == report_type` — a **JSONB path
  predicate with no GIN index** (`caan_reports` only has `tenant_id` and
  `created_at` single-column indexes, `db_models.py:1625-1626`), forcing a
  seq scan of the JSON bag.

---

## 3. Cross-cutting problems

### 3.1 Blocking code / event-loop stalls

- `pg.py` helpers are **synchronous wrappers** that hop onto the bridge loop
  via `runner.run(...)` with a **60 s timeout** (`app/db/runner.py`). During a
  wait, the request's worker cannot interleave; long queries serialize on the
  bridge. Anything slow here directly adds wall time.
- **NullPool** (`app/db/session.py:116-133`): every query opens and closes a
  TCP/SSL connection to Supabase (port 6543). Latency floor of ~20-80 ms per
  query just for connect+TLS, stacked per query. `pool_pre_ping` adds another
  round trip per acquire. This is *deliberate* (caps Supabase free-tier
  connections, cross-loop safe) but it dominates request latency on
  multi-query dashboards.
- `pg.update` performs a **double read**: `fetch_by` then the SQL `UPDATE`
  merge (`pg.py:240-272`).

### 3.2 Sequential database calls

- Admin tenants: 5 sequential `GROUP BY` (3.1-adjacent; see 2.6).
- SMS maturity: cache `_read_sms_maturity` fetch then `_write_sms_maturity`
  upsert on miss (`dashboard_service.py:895-917`) — two round trips.
- Survey maturity: sequential fetches of `Survey`, `SurveyResponse` (and
  hazards) before aggregation (`dashboard_service.py:778, 816`).
- Overview: 1 DB call + 3 CPU passes (not sequential DB, but see 2.1).

### 3.3 N+1 query patterns

- CAAN state tenant-slug resolution per report row (`dashboard_service.py:565`).
- Regulator list: regulator -> operators per row (`regulators.py:43`).
- Master register: CAN -> CAP / hazard references per row
  (`routes/dashboard.py:169`, `can_cap_service.py:498-501`).

### 3.4 Missing / weak indexes

| Table | Need | Why |
|---|---|---|
| `reports` | `(is_demo, created_at)` | All cross-tenant CAAN reads (2.4) seq-scan today |
| `caan_reports` | GIN on `data` JSONB | `reporting.py:126` JSONB predicate (2.7) |
| `sms_maturity` | `(tenant_id, days)` | cache read `dashboard_service.py:897` is single-column tenant today |
| `users` | `(tenant_id, role)` | team listings filter by both |

Everything else on the core tables is already covered: reports
`(tenant_id, created_at|status|occurrence_date)`, hazards/cans/caps
`(tenant_id, status|assignee)`, surveys/survey_responses `(tenant_id,
submitted_at)`, flight_diversions, psoe_assessments, regulatory_reports all
have their tenant-led composities (`db_models.py` index audit).

---

## 4. Optimizations

### 4.1 Shipped in this change set

1. **SQL date-range pushdown** — `ReportRepository.get_all_in_range`
   now emits `created_at/occurrence_date/updated_at >= / <=` when a typed sort
   column is used (`services/repository.py:193-204`). Tenant-scoped reads that
   once full-scanned the tenant and date-filtered in Python now hit
   `ix_reports_tenant_created` / `index reports_tenant_occdate`. This is the
   biggest single win and touches every dashboard endpoint via
   `_base_filter`/`_caan_filter`.
2. **Instrumentation layer** (section 1) — the measurement substrate needed to
   prove the remaining work in production.

### 4.2 Proposed (ranked by expected ROI)

1. **Add the three missing indexes** (run once in Supabase SQL editor, or via a
   schema-init migration):

   ```sql
   CREATE INDEX IF NOT EXISTS idx_reports_demo_created
     ON reports (is_demo, created_at);
   CREATE INDEX IF NOT EXISTS idx_caan_reports_data_gin
     ON caan_reports USING gin (data jsonb_path_ops);
   CREATE INDEX IF NOT EXISTS ix_sms_maturity_tenant_days
     ON sms_maturity (tenant_id, days);
   ```

2. **SQL-side page + count for `/recent`** — replace `get_all_in_range`-then-
   slice with a `LIMIT/OFFSET` query plus `COUNT(*)` (respecting the same
   isolation scope), killing the linear pagination cost.
3. **Column projection for metrics** — the overview/trends passes only need a
   handful of fields; add a select-projection variant of `get_all_in_range`
   instead of shipping the full `JSONB data`/`ai_analysis` blobs to RAM.
4. **Combine the five tenant-count GROUP BYs** into one `UNION ALL`
   (`production_seed.py:517-529`) and resolve regulator operator sets with a
   single batched read instead of per-row lookups.
5. **Connection reuse** — long-term, run one `session_scope()` per request and
   share the session with the bridge loop (or move reads onto the async SQL
   session used by the newer `*_async` services), rather than NullPool-per-
   query. Measure first (4.1 instrumentation) — the connect+TLS floor is the
   dominant constant once queries are index-bound.

---

## 5. Verification

- Regression: `tests/test_health.py` gained
  `test_repository_pushes_date_range_into_sql` and
  `test_repository_date_pushdown_respects_sort_column`. Full targeted run
  (repo/dashboard/metrics/pg suites): **45 passed, 6 pre-existing failures**
  (5x `test_reporting_scoping.py` require a local `caan_reports` table that
  does not exist; 1x `test_health.py` CORS preflight needs a browser origin —
  identical failures on the pre-change baseline).
- Production: after deploy, apply the DDL in 4.2.1 then re-run the slowest
  actions and diff the `[PERF]` lines (expect `queries=` / `db=` and
  per-endpoint `total=` to drop; `slow_sql` lines should disappear).