# CONNECTION_STABILITY_REPORT.md — Live-Supabase connection instability in the full test suite

Status: READ-ONLY INVESTIGATION (no code changed)
Scope: 12 live-DB test failures observed during the Phase 2 and Phase 3 full-suite runs
Environment: Supabase PostgreSQL via PgBouncer transaction pooler (port 6543), asyncpg 0.31.0

---

## 1. Executive summary

**Root-cause hypothesis: the live-Supabase backend/database is dropping or timing out
long-lived and bursty connections during the ~35-minute full run, and the application's
single long-lived sync "bridge" connection plus the raw live-DB tests have no
end-to-end retry/short-statement protection — so transient pooler/database events
surface as hard test failures. This is an environment/stability issue, not a Phase 3
code regression.**

Evidence:

1. All 12 failing tests **pass in isolation** and in reduced batches
   (`test_risk_assessment_lifecycle.py` alone → 28 passed; `test_safety_comms.py` +
   `test_sms_maturity_cache.py` → 16 passed; a 6-suite reduced batch → 52 passed).
2. The failures share a small set of connection-level errors: `QueryCanceledError`
   (statement timeout, 5×), `InterfaceError: connection is closed`,
   `ConnectionDoesNotExistError: connection was closed in the middle of operation`,
   and one cascading 500 in `reporting.py` caused by the same lost connection.
3. The app deliberately holds **one** permanent bridge connection
   (`session.py:178-204`, `_bridge_conn`) plus per-call NullPool connections
   (`session.py:264`). The permanent bridge socket can be silently severed by the
   pooler/Earth distance under a long run; `pg.py` retries it **once**
   (`pg.py:171-191`) but only for the sync bridge path — the async `session_scope()`
   path (`session.py:264-272`) has **no retry**.
4. There is **no `statement_timeout` / `idle_in_transaction_session_timeout` /
   `command_timeout` configured anywhere** (`config.py` grep → no matches;
   `session.py` `create_async_engine` has no `command_timeout` kwarg, `:125-142`), so a
   slow query can hit the **server-side** statement timeout and cancel the statement
   with no client-side guard.

---

## 2. Task findings

### Task 1 — Connection configuration

**(a) Async engine** (`session.py:114-143`):
- `poolclass=NullPool` (`:131`) — no client-side pooling; one connection per call, closed on return.
- `pool_pre_ping=True` (`:132`).
- **No** `pool_size`, `max_overflow`, `pool_recycle`, `pool_timeout` (irrelevant under NullPool).
- **No** `command_timeout` / `statement_timeout` on the engine or `connect_args` (`:138-141`).
- `echo=settings.DEBUG` (`:127`).

**(b) Sync bridge** (`pg.py` + `session.py`):
- One long-lived session bound to one permanently checked-out connection
  (`session.py:169-175, 178-204`), warmed with `SELECT 1`.
- Every `pg.py` call runs on the dedicated bridge loop (`runner.py:34-47`) and does its
  own `begin()`/commit (`pg.py:162-167`).
- One-shot reconnect on connection-loss errors (`pg.py:171-191`), matched by exception
  name in a fixed allowlist (`ConnectionDoesNotExistError`, `InterfaceError`,
  `ProtocolError`, `AdminShutdownError`, `ConnectionResetError`, `PipeError`,
  `BrokenPipeError`) or `connection_invalidated`.

**(c) Connection-related timeouts**: **none client-side.**
- `config.py` has no `statement_timeout` / `idle_in_transaction_session_timeout` /
  `pool_timeout` / `DB_TIMEOUT` settings (grep at `config.py` → only `DATABASE_URL:92`,
  `REPO_MAX_PAGE_SIZE:140`).
- `create_async_engine` (`session.py:125-142`) sets no `command_timeout`.
- `runner.run()` has a 60 s future timeout (`runner.py:70,97-100`) — this is a wrapper
  timeout, not a DB timeout; a server-side `QueryCanceledError` fires before it.

**(d) Environment variables**: `DATABASE_URL` (`config.py:92`) only.
- `backend/.env`: `postgresql+asyncpg://***@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?pgbouncer=true&sslmode=require`
  → **port 6543 = transaction pooler**; `pgbouncer=true` present.
- `_resolve_async_url` (`session.py:82-110`) converts `sslmode=require`→`ssl=require`,
  **drops** `pgbouncer`/`transaction_mode` (asyncpg rejects them, `:100-101`), and
  appends `prepared_statement_cache_size=0` (`:109`).

**(e) `statement_cache_size=0`**: **Yes** — set in `connect_args` (`session.py:139`) and
`prepared_statement_cache_size=0` as a URL dialect option (`:109`), plus globally-unique
prepared-statement names (`:51-61, 140`). Correct for PgBouncer transaction mode.

### Task 2 — Tests / fixtures holding connections

- `conftest.py` has **no session-scoped DB fixture** and **no session-scoped client**;
  `client` is function-scoped (`conftest.py:14-16`). No fixture holds a connection for
  the whole suite.
- No test holds `engine.connect()` across the suite; tests use `session_scope()` /
  `asyncio.run()` per call. Files with the most DB interactions:
  `test_state_risk.py` (10), `test_sms_maturity_cache.py` (8), `test_hazard_service.py`
  (6), `test_purge_demo_data.py` (5), `tests/_mbb.py` helper (4).
- Two tests use private event loops (`test_app_check_strict.py:50`,
  `test_regulator_dashboard.py:253`) — isolated, not shared.
- **The real "long-held connection" is the app global bridge session**, created on the
  first sync `pg.py` call and never proactively recycled (only recreated on error,
  `pg.py:186-190`) — it lives for the entire 35-minute process.

### Task 3 — Pooler

- **Mode**: transaction pooling (port 6543, `pgbouncer=true`), per `.env` and
  `DISCOVERY_REPORT.md:19` ("TRANSACTION pooler on port 6543 for Render").
- **`pgbouncer=true`**: present in `.env`; **stripped** before asyncpg (`session.py:100`).
- **Documented limits**: the repo asserts NullPool keeps usage "far under Supabase
  free-tier limits" (`session.py:14-15`) but cites no numeric limit. The pooler host is
  Singapore (`aws-0-ap-southeast-1`) — high RTT from the test host, consistent with the
  documented ~1.5-3 s handshake (`pg.py:129-130`, `session.py:192`).
- **Expected vs consumed**: NullPool means peak = in-flight queries; tests are largely
  serial, so connection *count* is unlikely to be the bottleneck. The observed errors
  are *drops/timeouts of existing connections*, not "too many clients".

### Task 4 — Failure pattern

- **Failing set belongs to 3 live-DB files**: `test_risk_assessment_lifecycle.py`
  (7: `test_caan_generates_state_report` + 6 SRA/fishbone tests), `test_safety_comms.py`
  (2), `test_sms_maturity_cache.py` (3). These plus `test_tenant_sms.py` (pre-existing,
  unrelated router-shape).
- **Common trait**: every failing test performs **real Postgres writes/reads** and does
  **not** monkeypatch the DB — they exercise the live connection through the app's own
  `session_scope()` / `pg.py` path. The passing 1107 largely mock the DB or use in-memory
  fakes (`pg_bridge`, `_FakeDB`).
- **Position in run**: failures cluster **mid-to-late**; the 35-min elapsed time and the
  one-more-connection exhaustion/cool-off are consistent with the pooler/database
  reclaiming idle backends (PgBouncer `server_idle_timeout` / Supabase maintenance).
- **Long tests**: `test_risk_assessment_lifecycle.py` (~7 min), `test_sms_maturity_cache.py`
  (~1 min), `test_safety_comms.py` (~1 min). The lifecycle suite's runtime is a large
  fraction of total DB wall-time, maximizing exposure to a dropped backend.

### Task 5 — Is the pooler the bottleneck?

- **Through the pooler**: yes (port 6543, `session.py:99`, `.env`).
- **Retry/reconnect in app code**: only the **sync bridge** (`pg.py:171-191`, one retry)
  and the **nested-bridge** path (`pg.py:155-158`, one retry, `OperationalError` only).
  The **plain async `session_scope()`** (`session.py:264-272`) has **no retry** and is
  what the failing API/endpoint tests exercise. No `InvalidCachedStatementError` handling
  exists (prepared statements are disabled, so not needed).
- **Graceful handling**: partial. `reporting.py:56-79` catches the write failure and
  re-raises `HTTPException(500, "Failed to save report")` — it **does not retry**, so a
  transient drop becomes a permanent 500 (the observed cascading failure).
- **Conclusion**: not a raw connection-count bottleneck; a **transient connection
  drop/timeout** that the async path never retries, causing first-error crashes.

---

## 3. Task 6 — Ranked mitigation options

**Option 3 — Split the full suite into chunks (e.g. by module).**
Effort: S. Risk: low (test-runner change only; no app behavior touched). Impact on gate:
high — each chunk runs < ~8 min, staying under the observed drop window; already how
Phase 3 verified green in reduced batches (191/156 passed). Verdict: **best first move.**

**Option 5 — Reduce per-test connection duration (session reuse / fewer live writes).**
Effort: M. Risk: low-medium (test refactors; keep live-DB coverage). Impact: high —
shrinking long-run exposure addresses the root trigger. Verdict: **complementary.**

**Option 2 — Add retry for transient connection errors in the async path + reporting.**
Effort: S. Risk: low (mirror the existing `pg.py` allowlist in `session_scope()` and
`reporting.py`). Impact: medium-high — converts a drop into a retry rather than a 500.
Verdict: **recommended structural fix (app robustness, not test-only).**

**Option 4 — Use a direct connection (port 5432) or a local/CI Postgres for tests.**
Effort: M. Risk: medium (bypasses the pooler being tested; direct conn has its own
Supabase `max_connections` ceiling; CI-local DB is new infra). Impact: high for
determinism, but changes what's under test. Verdict: good for CI; not for prod parity.

**Option 6 — Configure `server_reset_query` / server-side timeouts.**
Effort: S-M. Risk: medium (server-side setting change; Supabase may not expose it per
project; `statement_timeout` set too low could break legitimately slow queries).
Impact: medium. Verdict: only with a human applying it in Supabase; out of repo scope.

**Option 1 — Increase pool size / tune pooler settings.**
Effort: S. Risk: low but **low relevance** — NullPool already minimizes client
connections; the bottleneck is drops, not count. Impact: low. Verdict: **not indicated.**

**Recommendation order**: Option 3 → Option 5 → Option 2 → Option 4 → Option 6 → Option 1.

---

## 4. Recommended immediate action (1-2 small fixes)

1. **Split the full-suite gate into module chunks** (Option 3). Run e.g.
   `test_risk_assessment_lifecycle` in its own invocation and the remaining live-DB
   suites separately, with the pure/mocked suites in one fast chunk. This is zero-risk
   (test invocations only) and directly removes the >30-min exposure that correlates
   with the drops. Phase 3 already proved the chunks are green.
2. **Add a single transient-error retry to the async DB path** (Option 2): reuse the
   `pg.py:173-183` allowlist in `session_scope()`/`reporting._save_report` so one dropped
   connection retries instead of 500-ing. Small, mirrors existing behavior, improves
   production robustness too.

---

## 5. Recommended structural fix

Unify the connection-loss handling: a small shared `is_transient_conn_error(exc)`
helper used by **both** `pg.py:171-191` and `session_scope()`/write routes, plus an
optional `command_timeout` (e.g. 30 s) on the async engine so a slow query fails fast
and deterministically rather than via the server statement timeout. This makes behavior
identical across the sync bridge and async paths and removes the class of "first drop =
500" failures. (Phase 6/pre-production item.)

---

## 6. UNKNOWN items requiring human input

- **Supabase plan limits** for the project (PgBouncer `default_pool_size`,
  `server_idle_timeout`, DB `max_connections`) — not visible from the repo; needed to
  confirm the "idle backend reclaimed mid-run" hypothesis (Task 3).
- **Whether Supabase performs scheduled maintenance/restarts** during the run window —
  would explain `ConnectionDoesNotExistError`/`AdminShutdownError` and can only be seen
  in the Supabase dashboard/logs.
- **Whether the test host's network path** (Nepal↔Singapore) degrades over a 35-min run —
  RTT/timeout data would confirm the pooler handshake is being severed.
- **Precise server-side `statement_timeout` value** — the 5 `QueryCanceledError`s imply
  one exists; its value is set by Supabase and not in the repo.

---

*End of CONNECTION_STABILITY_REPORT.md (read-only investigation).*
