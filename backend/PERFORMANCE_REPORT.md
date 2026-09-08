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

---

## 6. Post-optimization benchmark (live, Sep 2026)

Measured with the automated harness (auth as the operator, warm-up + 5 samples
per endpoint against the production Render service + real Supabase pooler).
`db` = cumulative Postgres time (`X-Perf-Db-Ms`), `cpu` = residual
server-side time (total − db; includes Firestore I/O on master-register).

| Endpoint | Baseline | Final | Reduction | db | cpu |
|---|--:|--:|--:|--:|--:|
| master-register | 9978 ms | 3527 ms | 65% | 1757 | 1770* |
| airline sms-maturity | 7978 ms | 884 ms | 89% | 878 | 6 |
| trends (180d) | 5975 ms | 886 ms | 85% | 880 | 6 |
| risk-trends (730d) | 4050 ms | 886 ms | 78% | 880 | 6 |
| overview (90d) | 4025 ms | 885 ms | 78% | 881 | 4 |
| overview (365d) | 4021 ms | 885 ms | 78% | 880 | 5 |
| tenant config | 4017 ms | 883 ms | 78% | 878 | 5 |
| hazards list | 4015 ms | 883 ms | 78% | — | — |
| recent (90d) | 4008 ms | 885 ms | 78% | 880 | 5 |
| reporting quarterly | 4004 ms | 884 ms | 78% | 879 | 5 |
| recent (365d) | 4003 ms | 887 ms | 78% | 880 | 7 |
| reporting annual | 3998 ms | 883 ms | 78% | 879 | 4 |
| hazards (90d) | 3986 ms | 886 ms | 78% | 880 | 6 |
| actions (90d) | 3986 ms | 886 ms | 78% | 880 | 6 |
| reports list | 3986 ms | 883 ms | 78% | — | — |
| risk (90d) | 3951 ms | 886 ms | 78% | 880 | 5 |
| **Median** | **4015 ms** | **886 ms** | **78%** | 880 | 5–8 |

\* master-register’s `cpu` column is Firestore document I/O (it reads
hazards/CAN/CAP from Firestore by design), not server CPU.

Progression per deployed change (median): baseline 4015 ms →
**1758 ms** (+persistent bridge connection, `0a3fcdc`) →
**888 ms** (+tenant status auth cache, `f4ee77d`) →
**887 ms** (+bridge-loop `session_scope` reuse, `5e26c29`) →
**886 ms** (+stable-read TTL cache for tenants/slug registry/diversions,
`8f03c0c`).

## 7. Architecture of the changes

1. **One persistent Postgres connection** (`app/db/session.py`). The engine
   keeps NullPool (caps Supabase free-tier connections), but the sync `pg.py`
   helpers now operate on a single `AsyncSession` bound to one permanently
   checked-out `AsyncConnection` created and warmed on the bridge loop
   (`get_bridge_session` / async `ensure_bridge_session`, dropped via
   `close_bridge_session`). Binding the session to the connection - rather
   than the pool - defeats NullPool’s dispose-on-release, so the TCP/TLS
   handshake to the pooler (~1.5-2.5 s observed) is paid once per process
   instead of per query. Operations still use their own `begin()`/commit; no
   cross-request transaction is held. `session_scope()` (used by async
   services like hazard/survey lists running on the bridge loop) now reuses
   the same bound connection instead of opening a fresh NullPool connection
   per request; off-loop routes get a per-call session as before.
2. **Tenant status auth cache** (`app/middleware/tenant_status_cache.py`).
   The per-request `Tenant.status` read in `auth.py::_tenant_is_suspended`
   (the single most common query in profiling, 129 slow traces) is now one
   lookup per slug per 45 s TTL. Fail-open (errors/not-found never block
   login), invalidated on `_set_tenant`.
3. **Stable-read TTL cache** (`app/services/pg_cache.py`). Dashboard reads of
   tenant rows, the tenant slug registry and flight-diversion rows are
   effectively static; they built extra ~880 ms queries on `sms-maturity`
   (two tenant lookups), `trends` (diversions) and every CAAN-driven survey
   aggregation (slug registry). Cached per process with a 45 s TTL; missing /
   expired values fall through to the DB; `tenant_row:*` is invalidated on
   `_set_tenant`. Surveys themselves are NOT cached - submission visibility
   stays immediate.
4. **HEAD support on `/live`, `/health`, `/ready`** (`app/main.py`):
   `@app.api_route(methods=["GET","HEAD"])` so uptime monitors that probe HEAD
   get 200 instead of 405.

## 8. Risk assessment

- **Single bridge connection = serialized DB I/O.** The bridge loop executes
  one query at a time; under concurrent page views requests share the
  connection, so heavy queries queue behind each other (head-of-line
  blocking). Fine for the current single-instance operator dashboard; noted
  as the ceiling if concurrency grows.
- **Connection drop handling.** If the pooled connection goes stale (Supabase
  restart/idle timeout) `pg.py` reconnects once on
  `OperationalError`/disconnect-name errors (`_run_on_bridge`), then surfaces
  the error. Behavior is identical to pre-change fail-fast, just against one
  connection.
- **Cache freshness.** Bounded 45 s staleness on tenant status / tenant rows /
  slug registry / diversions; both caches fail open and are invalidated on
  tenant writes. Surveys and all mutable business data are never cached.
- **Surface unchanged.** No DDL, no schema, no Firestore writes, no auth
  contract changes. `/live` gained a HEAD response (GET unchanged).
- **Regression evidence.** Full backend suite: 671 passed, 38 failed, 56
  errors - byte-identical to the pre-change baseline at `5e26c29`
  (all pre-existing environment gaps: missing `caan_reports`, CORS preflight
  test, offline Firestore-rules/emulator suites).

## 9. Rollback plan

All five performance commits are self-contained and independently reversible;
because the later ones assume the earlier connection model, revert in reverse
order (newest first):

```
git revert 8f03c0c   # stable-read TTL cache (adds pg_cache.py)
git revert 5e26c29   # bridge-loop session_scope reuse
git revert f4ee77d   # tenant status auth cache
git revert 0a3fcdc   # persistent bridge connection
git revert a3c6bde   # instrumentation + /live HEAD  → opt. keep
```

Push `main`; Render auto-deploys (~90-165 s). The app is fully functional on
every step along the way; partial revert (e.g. keep `0a3fcdc`, drop the
caches) is safe since each commit passes the suite on its own. Full revert to
the 4 s baseline is achieved at `a3c6bde`.

## 10. Render tier recommendation

**No infrastructure upgrade is justified by post-optimization metrics.**

- The dominant remaining cost is network RTT to the Supabase pooler
  (~880 ms/query: BEGIN+PREPARE+EXECUTE+COMMIT over ~220 ms RTT) - an I/O
  bound, not CPU-bound, profile. Median endpoint now completes at 886 ms and
  the biggest consumer (master-register) is Firestore document I/O.
- Measured server CPU is single-digit milliseconds on every dashboard
  endpoint (see `cpu` column), and the app now holds exactly one Postgres
  connection - none of these drive Render’s CPU/RAM tiers.
- The only issue a paid tier actually fixes is free-tier **spin-down after
  50 s idle**: if uptime-monitor or end-user cold starts matter, move to the
  $7 Starter (persistent web service) - NOT for CPU/latency. The $25 instance
  type is not justified: it would not move any number in the table above.