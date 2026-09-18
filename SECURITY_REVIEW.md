# AviaSAFE SMS — Pre-Production Security Review

**Date:** 2026-09-18
**Scope:** `D:\Projects\aviasafesms` (backend FastAPI, `public/` static frontend, Firebase config/rules, deploy config). Read-only review; no code was modified.
**Method:** static inspection of auth dependencies, router mounts, secret literals, SQL construction, CORS/headers, container/deploy config. Claims are anchored to `path:line`. Secrets are redacted (first 4 / last 2 chars).

---

## Executive Summary

The platform has solid bones: explicit CORS allow-lists (no wildcard), parameterized SQLAlchemy queries, gitignored real env files, tenant-scoped lookups on most config endpoints, and App Check/Firebase ID-token plumbing. However, the **authorization model is applied per-route and inconsistently**, and several routers rely on the caller supplying a tenant identifier with no identity check.

Three issues should block production:

1. **An unauthenticated, internet-reachable endpoint can provision a tenant and an admin account** (`POST /api/v1/tenants/onboard`), because it self-supplies the invitation key.
2. **The production invitation key has a hardcoded, guessable default** that is not overridden in any deploy/config file, so the public self-service registration gate is effectively open.
3. **Multiple unauthenticated / under-authorized data APIs** expose or allow cross-tenant access to safety KPI, risk and aggregate data (`/api/v1/nhrc/*`, `/api/v1/spi/*`, `/api/v1/regulator/*`).

Severity counts: **CRITICAL 2 · HIGH 3 · MEDIUM 10 · LOW/INFO 8**.

---

## Positive Controls (verified, keep)

- Real env files are gitignored and untracked: `backend/.env`, `backend/.env.demo` (`.gitignore:10-12`; `git ls-files` confirms only `*.example` tracked).
- No `-----BEGIN PRIVATE KEY-----` / `AKIA…` / `sk-…` / `ghp_…` / `ya29.` production secrets in tracked files; `.env.example` contains placeholders only (`backend/.env.example:1-13`).
- CORS is an explicit allow-list with credentials, never `*` (`backend/app/core/cors.py:56-84`, `backend/app/main.py:70-93`).
- No f-string/string-concatenated SQL found; queries use SQLAlchemy ORM/bound params (`backend/app/db/*.py`); the universal query endpoint binds expression params and forces `tenant_id` from the user (`backend/app/routes/data.py:294-316`).
- Tenant config endpoints enforce caller-tenant match (`_require_tenant_admin` / `_require_tenant_viewer`, `backend/app/routes/tenants.py:65-96`).
- Admin destructive endpoints require `SUPER_ADMIN` + `SETUP_SECRET` (`backend/app/routes/admin.py:1806-1810`, `2050-2054`; `_verify_admin_setup` at `94-107`).

---

## CRITICAL

### C1 — Unauthenticated tenant+admin provisioning
`POST /api/v1/tenants/onboard` has **no authentication dependency** and calls `onboard_tenant` (`backend/app/api/v1/endpoints/tenants.py:42-57`). That service passes the configured key itself: `beta_access_key=settings.BETA_ACCESS_KEY` (`backend/app/services/onboarding_service.py:71`), which satisfies the production gate at `backend/app/services/tenant_registration.py:338`. The router is mounted at `/api/v1` (`backend/app/api/v1/router.py:8,17`; `backend/app/main.py:271`).
**Impact:** anyone on the internet can create a tenant, a Firebase Auth admin user with a chosen password, and seed data — no key, invite, or identity required.

### C2 — Hardcoded default production access key
`BETA_ACCESS_KEY: str = "AVIA…26"` (`backend/app/core/config.py:196`) is the exact value compared for the production self-service gate (`backend/app/services/tenant_registration.py:338`). It is **not set** in `render.yaml` (no `BETA_ACCESS_KEY` entry) nor in `backend/.env`. Combined with C1, the "invitation only" gate is fully bypassable using the published default.
**Impact:** unauthenticated tenant/account creation via `/onboard` and via public registration (`backend/app/routes/auth.py:149,233`).

---

## HIGH

### H1 — Unauthenticated SPI & N-HRC tenant data APIs
All routes in `backend/app/api/v1/nhrc.py` and `backend/app/api/v1/spi.py` have no auth dependency, e.g. `GET /api/v1/nhrc/tenant/{tenant_id}/kpis` (`nhrc.py:19-25`), `GET /api/v1/spi/tenant/{tenant_id}/values|status|trend` (`spi.py:27-65`), and `POST /api/v1/spi/tenant/{tenant_id}/targets` (`spi.py:98-108`). Mounted via `router.py:18-19`.
**Impact:** cross-tenant (IDOR) read of safety-performance data with no credentials; unauthenticated write path for targets.

### H2 — Regulator dashboard lacks regulator role check
Every endpoint in `backend/app/routes/regulator_dashboard.py:26-93` depends on `get_current_user` (any authenticated tenant role), not `get_caan_user`. `tenant_ids` is caller-controlled (`lines 11-21`), and `_default_tenant_ids` defaults to several tenants.
**Impact:** any authenticated airline user can read other operators' aggregated risk/benchmark data at `/api/v1/regulator/*`.

### H3 — App Check is optional, not enforced
`verify_app_check` returns immediately when the header is absent and only rejects a *present-but-invalid* token (`backend/app/middleware/app_check.py:36-60`); `verify_app_check_lenient` continues on invalid (`63-93`). It guards public auth/intake endpoints (`auth.py:72,154,436`).
**Impact:** bot/forged-client protection is best-effort only; public endpoints (login, register, tenant lookup, guest copilot) are effectively un-attested.

---

## MEDIUM

### M1 — Token revocation not checked
`auth.verify_id_token(token, check_revoked=False)` (`backend/app/firebase.py:105`). Disabled/revoked users keep access until token expiry (`JWT_EXPIRES_IN` 3600, `config.py:113`).

### M2 — Global rate limiter is per-proxy and mis-signals
`RateLimitMiddleware` keys on `request.client.host` (`backend/app/core/security.py:27`), which behind Render is the proxy address (the Redis limiter correctly parses `x-forwarded-for` at `backend/app/middleware/rate_limit.py:347-353`). It also raises `HTTPException` from middleware (`security.py:34`), which is outside the app exception handlers (`main.py:166`) and will surface as 500 rather than 429. State is in-memory per instance.

### M3 — Rate limiting fails open
When Redis is unavailable/disabled, `rate_limit` returns the handler unprotected (`backend/app/middleware/rate_limit.py:225,234`). `_tenant_survey_limit` still calls the removed Firestore `get_db()` (`rate_limit.py:322`), so per-tenant survey caps silently fall back.

### M4 — Internal task key exposed via query string
`_verify_task_key` reads `Query(..., alias="taskKey")` and compares with `!=` (`backend/app/api/v1/cron.py:16-21`). Query strings land in access logs/proxies; comparison is not constant-time (contrast `secrets.compare_digest` at `backend/app/routes/admin.py:118`).

### M5 — RBAC / tenant-isolation middleware never registered
`RBACMiddleware` (`backend/app/middleware/rbac_middleware.py:71-73`) is not imported or added in `backend/app/main.py` (no references). The module-permission and cross-tenant guardrails in it are dead code; all authorization depends on per-route dependencies.

### M6 — Insecure hazard-write router (unmounted)
`backend/app/api/v1/hazard_analysis.py:24-70` creates hazards/RCA/assessments/CAPAs using only an `X-Tenant-Id` header and a spoofed `safety@{tenant}.com.np` identity — no auth. It is currently **not mounted** (`backend/app/services/hazard_service.py:14`), so it is latent/dead code that must not be re-enabled as-is.

### M7 — `DISABLE_DESTRUCTIVE_ENDPOINTS` is a no-op
Defined (`backend/app/core/config.py:190`) but referenced nowhere (grep finds only the definition). It implies a safety switch that does not exist; destructive admin routes rely solely on `SUPER_ADMIN` + `SETUP_SECRET`.

### M8 — Container hardening gaps
`backend/Dockerfile:1,13`: base image `python:3.11-slim` not digest-pinned, no `USER` (runs as root), no `HEALTHCHECK`.

### M9 — Unpinned dependencies
`backend/requirements.txt` uses unbounded `>=` for every package with no lockfile/hashes. Builds are not reproducible and silently take latest (supply-chain/regression risk).

### M10 — Missing CSP / deprecated header
`SecurityHeadersMiddleware` sets HSTS, XCTO, XFO, Referrer-Policy, Permissions-Policy (`backend/app/core/security.py:11-20`) but **no Content-Security-Policy**, and includes deprecated `X-XSS-Protection`. HSTS is also emitted unconditionally (including non-HTTPS local dev).

---

## LOW / INFO

- **L1** Firebase Web API key `AIza…cc` hardcoded in `backend/app/core/config.py:101`, `public/js/firebase.js:24`, load/e2e scripts and deprecated scripts. By-design public, but must be referrer-restricted and backed by App Check.
- **L2** Server-side login lockout (`auth.py:68-97`) is bypassable because the SPA can call Identity Toolkit directly with the public key; the 5/15-min window only guards this endpoint.
- **L3** Public contact form forwards to Sender.net with no auth (`backend/app/routes/contact.py:93-133`); abuse/mail-relay risk (mitigated only by M2/M3).
- **L4** `/health` discloses Firebase/DB/commit status (`backend/app/main.py:301-314`).
- **L5** JWT config is dead/conflicting: `config.py:111-113` (RS256) vs `render.yaml:70-75` (HS256, JWT_SECRET); auth actually uses Firebase ID tokens.
- **L6** Firestore rule `match /tenants/{tenantId} { allow read: if isAuthenticated(); }` (`firestore/firestore.rules:67`) permits any authenticated read of any tenant doc. Firestore is removed from the data plane, but ensure the ruleset is undeployed.
- **L7** `GET /api/v1/auth/tenant-lookup` reveals org name + department codes to anyone knowing an invite code (`auth.py:430-462`).
- **L8** Dead/misleading artifacts: `DISABLE_DESTRUCTIVE_ENDPOINTS` (M7), `rbac_middleware` (M5), `hazard_analysis` router (M6), `workers/escalation_worker.check_overdue_cans` (never called).

---

## Task-Aligned Findings

**Task 1 — Secrets / hardcoded credentials.** No live private keys or cloud credentials committed. Public Firebase web API key hardcoded extensively (L1). Real secrets live only in gitignored `backend/.env` (positive). No secrets in `.env.example`.

**Task 2 — Access / beta keys.** C2 (hardcoded `BETA_ACCESS_KEY` default) and C1 (self-supplied key on `/onboard`). Admin `SETUP_SECRET` and task keys are env-only and fail closed when unset (`admin.py:101-107`, `cron.py:18-19`).

**Task 3 — Authentication coverage.** Unauthenticated: `nhrc.py`, `spi.py`, `endpoints/tenants.py:onboard`, `contact.py` (by design), `demo.py:/accept` (by design), `surveys.py` (optional by design). All other routers use per-route deps (H1, C1).

**Task 4 — Authorization / roles.** `regulator_dashboard.py` uses `get_current_user` instead of `get_caan_user` (H2). RBAC middleware unused (M5). Admin routes correctly gated (`admin.py:1806-1810,2050-2054`).

**Task 5 — Tenant isolation / injection.** No SQL injection found; `data.py` binds params and pins `tenant_id`. IDOR surfaces: `nhrc`/`spi` (H1), `regulator_dashboard` (H2). `tenants.py` config/read paths are scoped (positive).

**Task 6 — App Check / sessions.** App Check optional (H3); `check_revoked=False` (M1).

**Task 7 — Transport / CORS / headers.** CORS allow-list correct (positive). Missing CSP (M10). HSTS unconditional (L4/M10).

**Task 8 — Destructive/admin endpoints.** Require `SUPER_ADMIN` + `SETUP_SECRET`; `DISABLE_DESTRUCTIVE_ENDPOINTS` no-op (M7). Task-key path uses query string (M4).

**Task 9 — Frontend / AI / integrations.** Public Firebase key (L1); guest copilot public with lenient App Check (`copilot.py:96-101`); contact-form relay (L3).

**Task 10 — Deployment / container / dependencies.** Root container, unpinned base image (M8); unpinned deps (M9); Beta key absent from `render.yaml` (C2); dead JWT config (L5).

---

## Remediation Order

1. **C1** — Add an auth dependency to `/api/v1/tenants/onboard` (require `SUPER_ADMIN`, or a server-verified invite code supplied by the caller — never self-supplied), and add `@rate_limit`.
2. **C2** — Remove the hardcoded default (`config.py:196`); make `BETA_ACCESS_KEY` required/secrets-backed and fail closed when unset in production; set it in `render.yaml` (sync: false).
3. **H1/H2** — Add `get_current_user`/`get_caan_user` (and explicit tenant-role checks) to `nhrc.py`, `spi.py`, and every `regulator_dashboard.py` route; validate `tenant_ids` against the caller.
4. **H3/M1** — Enforce App Check (reject absent tokens) on sensitive public endpoints; set `check_revoked=True` (or add a revocation check on sensitive actions).
5. **M2/M3/M4** — Fix client-IP derivation in the global limiter, return proper 429s, fail closed (or alert) when Redis is down, move the task key to a header and use constant-time compare.
6. **M5/M6/M7** — Delete or wire up `rbac_middleware`; delete the unmounted `hazard_analysis.py` or add real auth before mounting; enforce `DISABLE_DESTRUCTIVE_ENDPOINTS` or remove it.
7. **M8/M9/M10** — Non-root container + pinned base + healthcheck; pin/lock dependencies; add CSP; conditional HSTS.
8. **L1–L8** — Restrict the Firebase web key, document the lockout limitation, harden the contact form, trim `/health`, remove dead JWT config, undeploy stale Firestore rules.

---

## Human-Decision Items

- **Intended public surface:** Which of `nhrc`/`spi`/`regulator` endpoints are meant to be public vs. tenant- or regulator-only? (drives H1/H2 fix shape)
- **Registration model:** Should `/onboard` be SUPER_ADMIN-only, or invite-code-gated for enterprise? (drives C1 design)
- **App Check rollout:** Is reCAPTCHA App Check provisioned for production? If yes, switch to strict enforcement; if no, that is the prerequisite. (H3)
- **`hazard_analysis.py`:** delete as dead code, or an unreleased Module B path to secure? (M6)
- **Firestore rules:** confirms the Firebase project still has Firestore disabled; if not, the L6 read rule must be fixed/deployed-for-off.
