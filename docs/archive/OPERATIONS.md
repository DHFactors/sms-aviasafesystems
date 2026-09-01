# Operations Manual

Day-to-day operations, administration, monitoring, and recovery for the AviaSAFE platform.

## 1. Roles & Who Does What

| Role | Typical operator | Operations responsibilities |
|---|---|---|
| `SUPER_ADMIN` | CAAN top-level director / platform owner | Provision airlines, fix tenant ids, risk-matrix defaults, seed demo data, claim setup |
| `CAAN_SMD` | Regulator / SSP inspectorate | Cross-tenant read, confirm risk assessments on behalf of the State |
| `AIRLINE_ADMIN` | Airline safety manager | Manage own-tenant reports, hazards, CAN/CAP, risk-matrix config, users |
| `USER` | Airline reporter | Submit VSR/MOR, view own-tenant data |

## 2. User Management

### 2.1 Registration

- Public registration creates an account with role `AIRLINE_ADMIN` (the tenant is derived from the
  registrant's email domain).
- Claim propagation can lag by a few seconds; the API falls back to an email→tenant lookup in that
  window (see [SECURITY.md](./SECURITY.md)).

### 2.2 Provisioning airlines (SUPER_ADMIN)

`POST /api/v1/admin/provision-airlines` — requires a SUPER_ADMIN ID token **and** `SETUP_SECRET`:

```bash
curl -X POST https://<host>/api/v1/admin/provision-airlines \
  -H "Authorization: Bearer <SUPER_ADMIN_ID_TOKEN>" \
  -H "X-Setup-Key: <SETUP_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"password": "<DEFAULT_PROVISION_PASSWORD>"}'
```

Creates the tenant(s), admin users, and CAAN cross-tenant accounts. If `SETUP_SECRET` is unset, the
endpoint returns `503` (fail-closed).

### 2.3 Fix tenant IDs

`POST /api/v1/admin/fix-tenant-ids` — reconciles `_` vs `-` tenant-id normalization drift
(SUPER_ADMIN only).

### 2.4 Other admin endpoints

See [API.md](./API.md) — `admin` router. Data-destructive endpoints
(`/seed-demo-data`, `/create-seed-users`) return `404` when `DISABLE_DESTRUCTIVE_ENDPOINTS=true`
(default), as set in production.

## 3. Monitoring & Health

| Endpoint | Purpose |
|---|---|
| `/health` | Basic liveness (process up) |
| `/live` | Liveness probe (used by Render / Cloud Run) |
| `/ready` | Readiness probe (dependency checks) |
| `/metrics` | Prometheus-style counters (AI results, request counts) |

Request logging middleware emits per-request records (UUID, method, path, status, duration, user).
Backend logs use **loguru** and are written to `backend/logs/`.

### `/metrics` details

`GET /metrics` is **admin-only** — it requires a Firebase ID token for an admin/SUPER_ADMIN user
(via `get_admin_user`). Without it the endpoint returns `401 {"success":false,"error":"Not authenticated"}`.
Verified against the unified backend service (`aviasafe-unified-platform`).

```bash
curl -H "Authorization: Bearer <ADMIN_ID_TOKEN>" \
  https://aviasafe-unified-platform.onrender.com/metrics
```

Exposed metrics (source: `backend/app/core/metrics.py`):

| Metric | Type | Notes |
|---|---|---|
| `requests_total{method,path,status}` | counter | Per-route request counts by status |
| `request_duration_ms{route,le}` | histogram | Buckets: 5,10,25,50,100,250,500,1000,2500,5000 ms |
| `ai_requests_total` / `ai_failures_total` | counter | Gemini AI call outcomes |
| `ai_success_rate_percent` | gauge | Derived success rate |
| `firestore_latency_avg_ms` / `firestore_latency_p99_ms` | gauge | Rolling window of last 1000 samples |

All metrics are **in-memory, per-instance**, and reset on restart (fine for the single-instance
deployment).

**Gaps / suggested additions:**

| Suggested metric | Why |
|---|---|
| `auth_failures_total` / `auth_success_total` | Monitor failed logins (brute-force / lockout risk) |
| `rate_limited_total{limit_type}` | Track 429s per Redis limit (auth, VSR, survey, MOR, dashboard) |
| `error_rate_percent` (4xx/5xx) | Overall health trend (currently derivable only by summing `requests_total`) |
| `redis_connected` / `rate_limit_disabled` gauge | Detect silent Redis failure / rate limiting off |
| `firestore_ops_total{op,status}` | Firestore success/error counts, not just latency |
| `requests_in_flight` gauge, `uptime_seconds` | Basic liveness/load signals |
| `process_rss_bytes` / CPU | Resource monitoring (requires `psutil`) |

## 4. Rate Limiting

- Default: **60 requests/minute per IP** (in-memory).
- When `REDIS_URL` is set, limits are Redis-backed and can be per-tenant on sensitive endpoints.
- On rate-limit breach clients receive `429`; raised thresholds and per-tenant policies are a
  tuning decision for the operator.

## 5. Backup & Disaster Recovery

**Current state (honest):**
- **No automated Firestore backups or PITR** are configured. Firestore by default retains a
  snapshot only via Google Cloud Backup/PITR settings, which must be enabled by an operator.
- **Recommended action (outstanding):** enable Firestore Backups (or PITR at minimum) for
  `aerosafety-sms-prod`; see [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md).

**Recovery steps if data is lost:**
1. Restore the most recent Firestore backup to the same project (or re-seed from
   `backend/seed` for the demo dataset).
2. Verify Auth user records still resolve (Auth is separate from Firestore; recreate users via
   `provision-airlines`/`create-seed-users` as needed).
3. Confirm security rules and indexes are the deployed versions.

## 6. TLS / CORS / Domains

- All client traffic is HTTPS (Firebase Hosting + Render managed TLS).
- CORS allow-list is `ALLOWED_ORIGINS` (default includes the Hosting origin and local dev ports).
- If you add a custom domain, add it to `ALLOWED_ORIGINS` and the Hosting custom-domain setup.

## 7. Common Operations Playbook

| Situation | Action |
|---|---|
| Backend unhealthy | Check `backend/logs/`, `/health`; verify Firestore creds; Render logs; rollback deploy (§DEPLOYMENT). |
| User can't sign in | Verify Auth user exists; re-send email/password reset; check custom claims propagation. |
| Cross-tenant data appears | Check `tenant_id` normalization (`/fix-tenant-ids`); verify token claims; audit rules. |
| Rate-limit spam | Adjust `RATE_LIMIT_PER_MINUTE` or enable Redis-backed policy. |
| App Check rejections | Verify web app key (reCAPTCHA v3) in Firebase console matches `public/js/firebase.js`. |
| Demo data needed | `python -m seed.runner --force` (backend) — destructive, staging only. |
| Incident / security event | Document in status report; rotate affected secrets; review Firestore rules. |

## 8. Change Management

- All functional/architectural changes require approval (Product Charter governance rule).
- Every change must keep `python -m pytest tests/ -q` green.
- Record changes + current commit in the status report under `docs/archive/`.

## 9. Monitoring (day-to-day)

Consolidated from the former `docs/BETA_MONITORING_GUIDE.md` (2026-08-06) — kept as ongoing
monitoring for the production environment; see [DEPLOYMENT.md](./DEPLOYMENT.md) for the stack.

**Surfaces:**
- Hosting: `https://sms.aviasafesystems.com`
- Backend: `https://aviasafe-unified-platform.onrender.com` (Render service `aviasafe-unified-platform`)
- Firestore: `sms-db` (project `aerosafety-sms-prod`, us-west1)
- Redis: Upstash `aviasafe-redis`

### 9.1 Daily — Render Logs

In the Render dashboard, open **aviasafe-unified-platform → Logs**.

**After each deploy (startup), confirm:**
```
Firebase Admin SDK initialized successfully (database=sms-db)
Connected to Upstash Redis        <- only after the first rate-limited request
```
- `database=sms-db` must match — if it says anything else, the wrong database is wired.
- If `Redis unavailable, rate limiting disabled` appears, Redis is down or misconfigured.

**Daily greps:**

| Grep for | Meaning | Action if unexpected |
|----------|---------|----------------------|
| `'status': 429` | Rate limiter working | Too many 429s → check which limit type is being hit |
| `'path': '/api/v1/auth/verify', 'status': 401` | Failed login attempts | Count them; a spike suggests brute-force or tester credential issue |
| `'status': 5` (500s) | Server errors | **P0** — investigate immediately |
| `Redis unavailable` | Rate limiting disabled | Check `REDIS_URL` / Upstash status |
| `Request warning` | Any 4xx | Review by path; most are expected (invalid token probes) |

Useful counts (last 24h):
```
grep -c "status': 429"          # total 429s
grep -c "auth/verify', 'status': 401"   # total failed logins
```

### 9.2 Weekly — Firestore Usage (`sms-db`)

No `gcloud firestore documents` command exists — use the Firestore REST API or the Firebase console:

```bash
TOKEN=$(gcloud auth print-access-token)
curl -H "Authorization: Bearer $TOKEN" \
  "https://firestore.googleapis.com/v1/projects/aerosafety-sms-prod/databases/sms-db/documents/<collection>?pageSize=1000"
```
- Console: `https://console.firebase.google.com/project/aerosafety-sms-prod/firestore/data/sms-db`
- Top-level collections: `tenants`, `reports`, `hazards`, `can_cap`, `reporting`, `flight_diversions`,
  `caan_reports`, `state`, `metadata`. Survey responses live under each tenant:
  `tenants/{tenant_id}/surveys` (collection group).
- **Caveat:** `pageSize` caps at 1000 docs/call — follow `nextPageToken` to paginate.
- `docs/BETA_TEST_CHECKLIST.md` previously noted there was **no** `audit_logs` collection. As of 2026-08-08 an
  `audit_logs` top-level collection **does** exist: `log_audit` (`backend/app/services/audit_service.py`) writes
  every audit action there, and the escalation job appends entries for each CAN/CAP escalation. The checklist's
  "audit trail" check covers both the CAP/hazard status history inside `can_cap`/`hazards` documents **and** the
  `audit_logs` collection entries.

### 9.3 Weekly — Auth Failures via Redis

Failed logins tracked per-IP in Redis as `rl:auth_attempts:ip:<ip>:<period>`.

```bash
redis-cli -u $UPSTASH_REDIS_URL --tls KEYS 'rl:auth_attempts:ip:*'
```
- A key with a **high count** (e.g. >150) = one IP hammering login → likely brute-force.
- **Reset is hourly** (UTC hour boundary) via TTL.
- Correlate with Render logs: the matching `401` bursts on `/api/v1/auth/verify`.

### 9.4 Escalation Triggers

| Signal | Severity | Owner action |
|--------|----------|--------------|
| HTTP 500s on any endpoint | **P0** | Stop tester invites, investigate immediately |
| Wrong Firestore database in logs (not `sms-db`) | **P0** | Verify env vars on Render |
| Redis unavailable (rate limiting off) | P1 | Check `REDIS_URL`, Upstash console |
| Single IP saturating auth limit | P1 | Block IP at edge / notify tester if legit |
| Growth anomalies (e.g. 10× reports in one week) | P2 | Review whether a tester misused the tool |

**Where to get help:** backend logs (Render → aviasafe-unified-platform → Logs); Firestore (Firebase
console → aerosafety-sms-prod → Firestore → sms-db); Redis (Upstash console → aviasafe-redis);
`gcloud.cmd` at `C:\Users\CEO-LAPTOP\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin`.
