# AviaSAFE SMS — Beta Monitoring Guide

Operational monitoring for the closed-beta period (see `docs/BETA_ENVIRONMENT.md` for the stack).

**Beta surfaces:**
- Hosting: `https://sms-beta.web.app`
- Backend: `https://aviasafe-unified-platform.onrender.com` (Render service `aviasafe-unified-platform`)
- Firestore: `sms-db-beta` (project `aerosafety-sms-prod`, us-west1)
- Redis: Upstash `aviasafe-redis`

---

## 1. Daily — Render Beta Logs

In the Render dashboard, open **sms-aviasafesystems-beta → Logs**.

### 1.1 After each deploy (startup)
Confirm the service initialized correctly:

```
Firebase Admin SDK initialized successfully (database=sms-db-beta)
Connected to Upstash Redis        <- only after the first rate-limited request
```

- `database=sms-db-beta` must match — if it says `sms-db`, the wrong database is wired.
- If `Redis unavailable, rate limiting disabled` appears, Redis is down or misconfigured → investigate before inviting testers further.

### 1.2 Daily greps
| Grep for | Meaning | Action if unexpected |
|----------|---------|----------------------|
| `'status': 429` | Rate limiter working | Too many 429s → check which limit type is being hit |
| `'path': '/api/v1/auth/verify', 'status': 401` | Failed login attempts | Count them; a spike suggests a brute-force attempt or tester credential issue |
| `'status': 5` (500s) | Server errors | **P0** — investigate immediately |
| `Redis unavailable` | Rate limiting disabled | Check `REDIS_URL` / Upstash status |
| `Request warning` | Any 4xx | Review by path; most are expected (invalid token probes) |

Useful count (last 24h of logs):
```
grep -c "status': 429"          # total 429s
grep -c "auth/verify', 'status': 401"   # total failed logins
```

---

## 2. Weekly — Firestore Usage Count (`sms-db-beta`)

Count documents per collection to track beta usage and growth. There is **no `gcloud firestore documents` command** — use the Firestore REST API (via a gcloud access token) or the Firebase console:

```bash
# REST API — count/list documents in a collection (replace <collection>)
TOKEN=$(gcloud auth print-access-token)
curl -H "Authorization: Bearer $TOKEN" \
  "https://firestore.googleapis.com/v1/projects/aerosafety-sms-prod/databases/sms-db-beta/documents/<collection>?pageSize=1000"

# Firestore console
#   https://console.firebase.google.com/project/aerosafety-sms-prod/firestore/data/sms-db-beta
```

**Top-level collections** (verified in `backend/`):

| Collection | Purpose |
|------------|---------|
| `tenants` | Organizations |
| `reports` | VSR / safety reports |
| `hazards` | Hazard register |
| `can_cap` | Corrective Action Plans |
| `reporting` | Generated report artifacts |
| `flight_diversions` | Diversion events |
| `caan_reports` | CAAN-level reports |
| `state` | State/SSP data (subcollections: `ssp/risk_register`, `icao_reference_document/categories`) |
| `metadata` | System metadata |

**Survey responses** live as a collection group `surveys` under each tenant:
`tenants/{tenant_id}/surveys` — query with a collection-group query or list per tenant.

> **Note on the checklist:** `docs/BETA_TEST_CHECKLIST.md` historically referenced an `audit_logs` collection when **no such collection existed**. As of 2026-08-08 an `audit_logs` top-level collection **does** exist (`log_audit` in `backend/app/services/audit_service.py`, including escalation events). The "audit trail" check now covers both the CAP/hazard status history stored inside the `can_cap` / `hazards` documents **and** the `audit_logs` collection entries.

**Counting caveat:** `pageSize` returns at most 1000 documents per call. For large collections, follow the response `nextPageToken` to paginate, or use the Firebase console (query count) for an exact figure.

---

## 3. Weekly — Auth Failures via Redis Rate-Limit Logs

Failed logins are tracked per-IP in Redis as `rl:auth_attempts:ip:<ip>:<period>`. Their counters tell you who is hitting the login limit.

```bash
# redis-cli (Upstash): list auth-attempt keys and counts
redis-cli -u $UPSTASH_REDIS_URL --tls KEYS 'rl:auth_attempts:ip:*'

# Python (redis-py):
#   for each key, GET returns the count; TTL shows time until the hourly reset
```

Interpretation:
- A single key with a **high count** (e.g., >150) is one IP hammering login → likely brute-force or an automated probe; watch it.
- **Reset is hourly** (UTC hour boundary). Keys disappear/reset automatically via TTL.
- Correlate with Render logs: the matching `401` bursts on `/api/v1/auth/verify` should come from that same IP.
- Normal tester activity across the beta should stay far below the 200/hour per-IP ceiling; sustained saturation is a red flag.

---

## 4. Escalation Triggers

| Signal | Severity | Owner action |
|--------|----------|--------------|
| HTTP 500s on any beta endpoint | **P0** | Stop tester invites, investigate immediately |
| `sms-db-beta` missing from logs / `sms-db` in use | **P0** | Verify beta env vars on Render |
| Redis unavailable (rate limiting off) | P1 | Check `REDIS_URL`, Upstash console |
| Single IP saturating auth limit | P1 | Block IP at edge / review firewall, notify tester if legit |
| Growth anomalies (e.g., 10× reports in one week) | P2 | Review whether a tester misused the tool |

## 5. Where to Get Help

- Backend logs: Render → **sms-aviasafesystems-beta → Logs**
- Firestore: Firebase console → **aerosafety-sms-prod → Firestore → sms-db-beta**
- Redis: Upstash console → **aviasafe-redis**
- `gcloud` on this machine is not on PATH — use:
  `C:\Users\CEO-LAPTOP\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd`
