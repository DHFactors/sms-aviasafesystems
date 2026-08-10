# Pre-Launch Assurance Status Report — AviaSAFE SSP

**Date:** 2026-08-04
**Scope:** Phases 1–5 of `Software Assurance & Certification Framework.md`
**Targets:** `sms.aviasafesystems.com` (frontend), `aviasafe-unified-platform.onrender.com` (API), Firestore `aerosafety-sms-prod` / `sms-db`
**Tests executed:** 67/67 passing

---

## PHASE 1 — Functional & Test Execution: PASS (with caveat)

| Check | Result | Notes |
|---|---|---|
| Backend unit/integration tests | **PASS** | `67 passed` in 11.66s |
| API responses (live) | **PASS** | `/health`, `/`, CAAN survey-maturity, benchmark, state-risk register/aggregate all 200 |
| Error handling | **PASS** | Consistent envelope `{success, error, detail, errors, request_id}`; unhandled exceptions masked (detail only in DEBUG); 401/403/422/429/404 handled |
| Input validation | **PASS** | Pydantic v2 models with `ge/le` bounds (severity 1–5, probability 1–5, risk-matrix 1–25, year/quarter ranges); 422 with field-level errors |
| RBAC (SUPER_ADMIN / CAAN_SMD / AIRLINE_ADMIN / USER) | **PASS** | Middleware deps `get_admin_user`, `get_caan_user`, `get_tenant_user`, `get_safety_manager`; tested cross-tenant reads, USER→403, CAAN/SM/SA confirm flows |
| Authentication | **PASS w/ warning** | Firebase ID-token Bearer auth; 401→403 mislabeling (HTTPBearer default) |

### Warnings (Phase 1)
- **Unauthenticated `/api/v1/auth/register` self-provisioning (HIGH).** Live probe confirmed an anonymous caller can create an `AIRLINE_ADMIN` account with an arbitrary `tenant_id` (e.g. `buddha-air`). The frontend never calls this endpoint. Today the exploit is partially mitigated because client-side `signInWithPassword` is blocked by an API-key restriction (headless calls return PERMISSION_DENIED), but the endpoint itself grants privileged claims to unauthenticated callers and remains a latent IDOR/cross-tenant vector. **Probe account was created then deleted.**
- No E2E test suite runs in CI; no frontend JS tests (`npm test` is a stub).

---

## PHASE 2 — Code Quality: PASS (maintainability issues, no blockers)

| Tool | Result | Findings |
|---|---|---|
| Bandit (Python security) | **PASS** | 1 MEDIUM (0.0.0.0 bind — expected for Render), 2 LOW bare `try/except/pass` |
| Pyflakes (dead code / smells) | **WARN** | 67 findings, **all unused imports** across routes/models/services (e.g. `reporting.py`, `verification.py`, `can_cap.py`); no undefined names or logic bugs |
| `node --check` (JS) | **PASS** | All 23 JS files parse clean |
| Duplicate code | **WARN** | Every router registered twice (v1 + legacy prefixes) doubling the attack surface; `public/portal/` + `public/survey/` + `public/admin/` are unlinked legacy duplicates of the active `public/js/` stack |

### Recommended remediations
- Prune unused imports (pyflakes list) — low risk, mechanical.
- Remove or archive `public/portal/`, `public/admin/`, legacy API prefixes, and the legacy `survey` directories; each is dead surface that must be maintained and secured.
- Add `ruff`/`flake8` to CI and document tech-debt in GAPS.md.

---

## PHASE 3 — Dependency Security Scan: FAIL (must remediate before release)

### Python (`backend/requirements.txt` via `pip-audit`)
**21 known vulnerabilities in 5 packages.** No Critical; several High.

| Package | Pinned | Vulnerabilities | Severity/Notes |
|---|---|---|---|
| `fastapi` | 0.109.0 | CVE-2024-24762 (ReDoS) | High; only via form-data parsing — **not reachable** (app uses JSON only) |
| `python-multipart` | 0.0.6 | CVE-2024-24762, CVE-2024-53981, CVE-2026-24486, CVE-2026-40347, CVE-2026-53538/9, CVE-2026-53540, CVE-2026-42561, CVE-2026-3036-40 | High; form parsing only — **not reachable** (no `Form()`/`UploadFile` anywhere) |
| `starlette` | 0.35.1 | CVE-2026-48710, CVE-2026-54282/3, CVE-2024-47874, CVE-2025-54121, CVE-2026-48817/8 | High; host-header/url parsing, form DoS — partially reachable (no `request.form()` usage found; host header not used for auth) |
| `protobuf` | 4.25.9 | CVE-2026-0994 (recursion DoS) | High; transitive via firebase/gRPC |
| `python-dotenv` | 1.0.0 | CVE-2026-28684 (symlink write) | Local-only; low exposure |

### JS (`package.json` via `npm audit`)
**11 vulnerabilities (1 critical, 6 high, 4 moderate)** — all in `firebase-admin@^11` transitive deps (`protobufjs-cli` code injection, `uuid`). **Mitigation:** `firebase-admin` is only used by dev/ops scripts under `scripts/`; the production frontend loads the Firebase JS SDK from gstatic CDN. Not in the runtime browser path, but the npm audit must be cleared.

### Recommended remediations
- Upgrade: `fastapi>=0.109.1`, `python-multipart>=0.0.31`, `starlette>=1.3.1` (or `fastapi` latest), `python-dotenv>=1.2.2`, `protobuf>=5.29.6`. Re-run tests after each bump (67-test suite).
- For JS: run `npm audit fix --force` (upgrades to `firebase-admin@14`) or move the 4 scripts to a separate dev-only package.
- **Exit criteria not met** (High vulnerabilities present) → dependency upgrade is a release blocker.

---

## PHASE 4 — Infrastructure & Secret Security: PASS (with gaps)

| Check | Result | Notes |
|---|---|---|
| TLS on `sms.aviasafesystems.com` | **PASS** | Valid cert (Google Trust Services), TLS 1.3, 89 days remaining, HSTS `max-age=31556926` |
| HTTP security headers (API) | **PASS** | HSTS `max-age=31536000; includeSubDomains`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection`, `Referrer-Policy`, `Permissions-Policy` |
| HTTP security headers (frontend) | **WARN** | `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy` set; **no `Content-Security-Policy`**, **no `Permissions-Policy`** |
| CORS | **PASS** | `allow_origins` restricted to prod + localhost; verified disallowed origin gets **no** ACAO header; `allow_credentials=True` with explicit origin list |
| Hardcoded secrets | **PASS** | `backend/.env` git-ignored & untracked; no private keys in tracked source. Firebase **web** API key (`AIzaSyCdC…`) in `firebase.js` is client-side by design (Firebase requires it; authorization enforced via Firestore rules) |
| Secret management | **PASS** | Firebase service-account creds, setup key, seed passwords all env-only; `DISABLE_DESTRUCTIVE_ENDPOINTS=True` in prod |
| Firestore Security Rules | **PASS** | Tenant-isolated reads, CAAN/SUPER_ADMIN-only analytics & state-risk, public-but-immutable responses, default-deny everywhere else. Single canonical rules file (`firestore/firestore.rules`), deployed to `sms-db` |

### Recommended remediations
- Add a `Content-Security-Policy` header (Firebase Hosting `firebase.json` headers block) — this is the main Phase-4 gap given the XSS findings in Phase 5.
- Optionally add `Permissions-Policy` to frontend headers.
- Remove the duplicate `firestore.rules` stub (marked OBSOLETE) to avoid confusion.

---

## PHASE 5 — Application Security / OWASP Top 10: FAIL (High findings)

| OWASP | Assessment | Result |
|---|---|---|
| A01 Broken Access Control | **Stored/self-provisioned admin — HIGH.** Unauthenticated `/auth/register` mints AIRLINE_ADMIN + arbitrary tenant (Phase 1). Legacy `public/portal` email-domain→tenant mapping is NOT an authz bypass (Firestore rules still enforce) but is dead surface | **FAIL** |
| A03 Injection | **SQL/NoSQL injection — PASS.** No SQL; Firestore accessed via typed services; no string-concatenated queries. **Command injection — PASS.** No shell/`os.system` with user input. **XSS — HIGH.** `innerHTML` used in 5 files without escaping user-controlled fields (reports table, hazard register, MOR review, VSR, tenant): `dashboard.js:391` (location/occurrence_type/status), `mor.js:257` (narrative/location/aircraftReg), `vsr.js`, `app.js`. No `escapeHtml()` helper exists | **FAIL** |
| A02 Broken Authentication | Weak password policy (min length only in register); no account lockout (rate limit 50/hr on `/auth/verify` only); Firebase handles hashing/MFA-ready. Seed CAAN password previously found invalid | **WARN** |
| A04 Insecure Design | No MFA, no audit-trail UI, aggregation is on-demand (no persistence) — documented in GAPS.md | **WARN** |
| A05 Misconfiguration | CSP missing on frontend; debug endpoints gated but legacy prefixes double surface; `allow_headers=["*"]` | **WARN** |
| A06 Vulnerable Components | Phase 3 — High/Critical in deps | **FAIL** |
| A07 IDOR | Report/hazard/CAN-CAP scoped by tenant_id server-side; cross-tenant blocked (tested). `/auth/register` tenant_id choice is the exception | **WARN** |
| A09 Logging & Monitoring | Structured `loguru` logging, request IDs, in-memory metrics, `/health`+`/live`+`/ready` probes; **no external error tracking** (Sentry), no persistent metric store, no alerting | **WARN** |
| CSRF | **PASS** — Bearer-token auth (no cookies), so classic CSRF does not apply |
| Rate limiting | **PARTIAL** — Redis-backed on `auth_attempts`, `mor_submit`, `vsr_submit`; in-memory IP limiter (60/min) global; **survey submission is client-direct to Firestore with no server-side limit** (rules allow unauthenticated `create`); `dashboard`/`survey_submit` limits defined but **not applied to any endpoint** | **FAIL** |
| File upload | **PASS** — no upload endpoints in scope |

---

## Overall Status

| Phase | Result |
|---|---|
| Phase 1 — Functional & Test Execution | **PASS** (1 HIGH warning) |
| Phase 2 — Code Quality | **PASS** (maintainability debt) |
| Phase 3 — Dependency Security | **FAIL** (release blocker) |
| Phase 4 — Infrastructure & Secrets | **PASS** (CSP gap) |
| Phase 5 — Application Security | **FAIL** (High findings) |

### Release gate (framework FINAL RELEASE GATE)
Not yet cleared. Remaining blockers before public release:

1. **HIGH — Stored XSS.** Add an `escapeHtml()`/DOM-text renderer for all user fields flowing into `innerHTML` (reports, hazards, CAN/CAP, MOR/VSR review). No-CSP frontend increases the blast radius.
2. **HIGH — Unauthenticated `/auth/register`.** Disable in prod (behind `DISABLE_DESTRUCTIVE_ENDPOINTS` or an admin token) — the frontend does not use it.
3. **HIGH — Vulnerable dependencies.** Upgrade `fastapi`/`python-multipart`/`starlette`/`protobuf`/`python-dotenv`; clear `npm audit`.
4. **MEDIUM — Missing CSP** on the frontend hosting config.
5. **MEDIUM — Rate limiting gaps.** Apply `survey_submit`/`dashboard` limits; consider server-side survey ingestion to bound the public Firestore write path.
6. **LOW — Dead/legacy surface.** Remove `public/portal`, `public/admin`, legacy survey dirs, legacy API prefixes; prune 67 unused imports.
7. **LOW — 401 vs 403.** Configure HTTPBearer to return 401 for missing credentials.
8. **Observability.** Add external error tracking + alerting before GA (Phase 13 dependency).

### Verified-strong areas
- Firestore security rules are tenant-scoped, role-gated, default-deny — well above typical baseline.
- RBAC middleware is consistently applied and covered by tests (67 passing, incl. cross-tenant UAT regressions).
- TLS 1.3 + HSTS + strong headers on the API; CORS locked to allowed origins.
- No secrets in the repository; structured error envelope with request IDs.

*This assessment covers Phases 1–5 of 15. Phases 6–15 (penetration testing, performance, reliability, usability, accessibility, privacy, observability, disaster recovery, production readiness) remain to be executed before the framework's release gate is cleared.*
