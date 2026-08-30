# 📝 AviaSAFE SMS — Project Status Report

**Project**: AviaSAFE SMS — Safety Climate Measurement System (ICAO Annex 19 compliant)
**Report Date**: 2026-08-19
**Prepared by**: AviaSAFE Systems engineering (Opencode-assisted)
**Verification**: Backend suite **370 passed** (baseline 358 + 12 new), frontend Node suites
(`tenant-context`, `dashboard-render`) passing, all modified JS/HTML parse-validated via Node `vm.Script`.

---

## 1. Executive Summary

| Item | Value |
|------|-------|
| **Project Name** | AviaSAFE SMS |
| **Report Date** | 2026-08-19 |
| **Overall Status** | **Beta/production guardrails implemented: production registration gated by enterprise access code, beta self-service tenants tagged as sandbox, rate limiting tightened, App Check token verification added, and the copilot given a hard aviation-safety boundary with prompt-injection rejection.** Backend suite: **370 tests passing** |
| **Current Phase** | Beta Testing (pre-production) — RC-3 complete; RC-4/5/6 remain |

**Key Highlights**
- **Production registration gate (2026-08-19)** — self-service tenant registration is now by
  invitation only on production (`settings.ENVIRONMENT=production`, the default): a valid enterprise
  access code (admin-issued invite key) is mandatory, otherwise `403`. The beta keeps the optional
  access key and tags every self-service tenant `{ "is_beta_sandbox": true, "auto_expire_days": 30 }`.
- **Tighter rate limiting** — Redis-backed buckets for the public endpoints: `register_tenant`
  10/hr/IP, `join_team` 30/hr/IP, legacy `register` 10/hr/IP; `verify-invite` and `tenant-lookup`
  also rate-limited; `copilot` (incl. guest) 120/hr/IP.
- **App Check verification** — new `app/middleware/app_check.py` verifies `X-Firebase-AppCheck`
  tokens server-side on register/join/verify/lookup/guest-chat (invalid tokens → 401). Clients
  activate reCAPTCHA v3 on `register.html`/`join.html`; the **beta reCAPTCHA site key is a pending
  console action** in `gap-analysis-ssp` (graceful skip until provisioned).
- **Copilot safety boundary** — `groq_copilot.py` rejects prompt-injection attempts outright and
  redirects clearly off-topic queries (poems, recipes, coding, etc.) before any model call, unless
  the query also references an aviation-safety topic.
- **Frontend environment isolation** — `firebase.js` now carries dual configs: beta routes to the
  isolated `gap-analysis-ssp` project (`sms-db-beta`), production to `aerosafety-sms-prod` (`sms-db`).
  Env detection fixed (`sms.aviasafesystems.com` is now correctly production). Storage keys are
  env-prefixed (`aviasafe:{beta|prod}:*`). Login enforces production tenant-membership on
  tenant-scoped subdomains.
- **Docs** — `BETA_ENVIRONMENT.md` rewritten for the isolation migration; `DEPLOYMENT.md` /
  `OPERATIONS.md` updated for per-project Firestore, the `ENVIRONMENT` var, and the beta stack.

---

## 2. Work Completed

### 2.1 This Report Period (2026-08-19)

| Item | Files | Status |
|---|---|---|
| `ENVIRONMENT` setting (prod default) | `backend/app/core/config.py` | ✅ Complete |
| Production access-code gate + beta sandbox tagging | `backend/app/services/tenant_registration.py` | ✅ Complete |
| Rate-limit buckets + wiring (legacy `/register`, `/tenant-lookup`) | `backend/app/middleware/rate_limit.py`, `backend/app/routes/auth.py` | ✅ Complete |
| App Check header verification dependency | `backend/app/middleware/app_check.py` | ✅ New |
| App Check wired into register/join/verify/lookup/guest-chat | `backend/app/routes/auth.py`, `backend/app/routes/copilot.py` | ✅ Complete |
| Copilot topic + injection boundary (pre-model rejection) | `backend/app/services/groq_copilot.py` | ✅ Complete |
| Backend tests (+12: gating, sandbox tags, boundary) | `backend/tests/test_self_service_registration.py`, `backend/tests/test_copilot.py` | ✅ 370 passed |
| Dual prod/beta Firebase configs + fixed env detection + storage helpers | `public/js/firebase.js` | ✅ Complete |
| Env-prefixed storage keys | `public/index.html`, `public/js/tenant_context.js`, `public/js/admin.js` | ✅ Complete |
| Per-env reCAPTCHA + `getAppCheckToken` helper | `public/js/firebase.js` | ✅ Complete |
| Production registration gate UI + App Check header on submit | `public/register.html` | ✅ Complete |
| App Check headers on verify/lookup/join calls | `public/join.html` | ✅ Complete |
| Production tenant-membership verification on login | `public/login.html` | ✅ Complete |
| Stale `sms.aviasafesystems.com → beta` rules removed | `public/register.html`, `public/join.html`, `public/js/components/copilot-widget.js` | ✅ Complete |
| Docs for isolation + guardrails | `docs/BETA_ENVIRONMENT.md`, `docs/DEPLOYMENT.md`, `docs/OPERATIONS.md` | ✅ Complete |

### 2.2 Pending / Requires Action

- **Beta reCAPTCHA site key (App Check)** — register in the `gap-analysis-ssp` console (Security >
  App Check) and paste into `public/js/firebase.js` `BETA_CONFIG`/`APP_CONFIG.recaptchaSiteKey`.
- **Beta Render env** — point the `sms-aviasafesystems-beta` service at `gap-analysis-ssp`:
  `FIREBASE_PROJECT_ID=gap-analysis-ssp`, gap-analysis-ssp SA creds, `FIREBASE_DATABASE_ID=sms-db-beta`,
  `ENVIRONMENT=beta`, updated `ALLOWED_ORIGINS`.
- **Deploy** — backend (Render) + frontend to `sms-beta` (project `gap-analysis-ssp`) and
  `aerosafety-sms-prod`; then verify end-to-end.
- Known issue #4 remains: missing `caan-fssd` / `caan-assd` Firestore tenant docs (pre-existing;
  same on source; pending v2.2.0 re-seed).

---

## 3. Verification

- `python -m pytest --rootdir=. -q` in `backend/` → **370 passed**.
- `node frontend-tests/tenant-context.test.js` → passed; `node frontend-tests/dashboard.test.js` →
  4 passed.
- All modified `public/**/*.js` and inline HTML `<script>` blocks parse cleanly via Node `vm.Script`.
- Migration integrity previously verified: `backend/scripts/migrate_beta_db.py --verify` = 2,233/2,233.

---

## 4. Next Steps

1. Commit the guardrails work on `feat/betasms-self-service` (and `main`).
2. Redeploy backend (Render) with `ENVIRONMENT` set per environment.
3. Provision the beta App Check reCAPTCHA key in `gap-analysis-ssp`.
4. Deploy frontend and verify `sms.aviasafesystems.com` (production, invite-only registration)
   end-to-end.