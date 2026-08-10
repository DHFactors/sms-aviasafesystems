# AviaSAFE SMS — Load Testing

Performance test scenarios for the AviaSAFE SMS API, matching the agreed load
profile. Both **k6** and **Artillery** configs are provided.

## Load profile

| Scenario                     | Concurrent users | Endpoints hit                                      |
|------------------------------|------------------|----------------------------------------------------|
| Report submission            | 100              | `POST /api/reports/vsr` (and `/mor`)               |
| Dashboard viewing            | 50               | `/api/dashboard/{overview,trends,hazards,actions,airline/sms-maturity}` |
| CAAN aggregated viewing      | 10               | `/api/dashboard/caan/*` (7 endpoints)              |

**Success criterion: HTTP response time < 500 ms (p95).**

## Prerequisites

- [k6](https://grafana.com/docs/k6/latest/set-up/install-k6/) (`k6` on PATH)
- [Artillery](https://www.artillery.io/docs/guides/getting-started/installing-artillery) (`npm install -g artillery`)
- Node.js 14.8+ (for `get-token.mjs`)
- A Firebase ID token (minted by `get-token.mjs`) with the right role for each scenario

## 1. Get an auth token

```bash
# Airline scenario (dashboard-view, report-submission):
LOADTEST_TOKEN=$(node load-tests/get-token.mjs safety@tara-air.com 'TARA-Safety-2026')

# CAAN scenario — use a CAAN_SMD / SUPER_ADMIN account instead:
LOADTEST_TOKEN=$(node load-tests/get-token.mjs '<caan-email>' '<caan-password>')
```

Tokens expire after **1 hour** — re-mint before each run.

## 2. Run — k6

```bash
export LOADTEST_BASE_URL=https://sms-aviasafesystems-beta.onrender.com   # optional, defaults to beta

k6 run -e LOADTEST_TOKEN=$LOADTEST_TOKEN load-tests/k6/report-submission.js
k6 run -e LOADTEST_TOKEN=$LOADTEST_TOKEN load-tests/k6/dashboard-view.js
k6 run -e LOADTEST_TOKEN=$LOADTEST_TOKEN load-tests/k6/caan-dashboard.js
```

## 3. Run — Artillery

```bash
artillery run load-tests/artillery/report-submission.yml
artillery run load-tests/artillery/dashboard-view.yml
artillery run load-tests/artillery/caan-dashboard.yml
```

## Configuration reference

| Env var               | k6 usage                              | Artillery usage                        | Default                                   |
|-----------------------|---------------------------------------|----------------------------------------|-------------------------------------------|
| `LOADTEST_TOKEN`      | `-e LOADTEST_TOKEN=...`               | `process.env.LOADTEST_TOKEN` (auto)    | (required)                                |
| `LOADTEST_BASE_URL`   | `-e LOADTEST_BASE_URL=...`            | edit `config.target`                   | `https://sms-aviasafesystems-beta.onrender.com` |
| `LOADTEST_API_KEY`    | (unused)                              | (unused)                               | public web API key (in `get-token.mjs`)   |

## Important operational notes

1. **Rate limiting will throttle report submission.** The backend enforces
   `50 VSR/day` and `20 MOR/day` *per tenant* (and `200 logins/hour`). With 100
   concurrent reporters the tenant correctly returns **HTTP 429** after the
   daily quota. The k6 script splits metrics into `accepted_request_duration`
   (201) and `throttled_request_duration` (429) so a clean pass/fail on the
   p95 criterion is still reported. For a *pure* latency run with no
   throttling, deploy a load-test backend with `REDIS_ENABLED=false` (or no
   `REDIS_URL`), which disables rate limiting.

2. **Submitting reports writes real data and triggers background work.**
   Each accepted report creates a Firestore document, auto-creates a hazard,
   writes an `audit_logs` entry, and queues a Gemini AI analysis background
   task. Load-testing submission:
   - populates the tenant with many test reports/hazards, and
   - consumes **Gemini API quota** (each analysis is a model call).
   Prefer a dedicated load-test tenant, and unset the AI key
   (`AI_API_KEY`/`GEMINI_API_KEY`) on the load-test backend to avoid cost.

3. **Dashboard and CAAN GET endpoints are NOT rate-limited**, so those
   scenarios are clean latency tests and safe to run against beta.

4. **CAAN endpoints need a CAAN_SMD/SUPER_ADMIN token.** An airline token will
   be rejected with 403.

5. **Audit logging is active.** Every request type exercised here also writes
   to `audit_logs` (login, report submitted, hazard created, etc.).

## Reading results

- **k6:** the summary table prints `http_req_duration` p95 per scenario.
  Thresholds fail the run if `p(95) >= 500ms`.
- **Artillery:** the `ensure.p95: 500` block fails the run if the p95 latency
  exceeds 500 ms. Use `--output` to write JSON reports:
  `artillery run --output load-tests/artillery/report.json load-tests/artillery/report-submission.yml`
