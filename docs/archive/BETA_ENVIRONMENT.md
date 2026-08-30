# AviaSAFE SMS — Beta Environment Setup Notes

Versioned reference for the closed-beta environment. Verified **2026-08-18** (full beta isolation migration).

## Overview

The beta is a **fully isolated environment** in its own Firebase project. Beta traffic can never touch production data — separate Firebase project, separate Auth pool, separate Firestore database, separate frontend configuration.

| Component | Beta | Production |
|-----------|------|------------|
| **Hosting** | `https://sms.aviasafesystems.com` (site `sms-beta`, project `gap-analysis-ssp`) | `https://sms.aviasafesystems.com` / `aerosafety-sms-prod.web.app` |
| **Firebase project** | `gap-analysis-ssp` (projectNumber `817614332543`) | `aerosafety-sms-prod` (projectNumber `527947363983`) |
| **Backend** | `https://aviasafe-unified-platform.onrender.com` | `https://aviasafe-unified-platform.onrender.com` |
| **Firestore** | `sms-db` (native, us-west1, PITR 7d, project `gap-analysis-ssp`) | `sms-db` (native, us-west1, project `aerosafety-sms-prod`) |
| **Auth pool** | `gap-analysis-ssp` (50 seeded users, 2,233 migrated docs) | `aerosafety-sms-prod` |
| **Redis** | Upstash `aviasafe-redis` (rate limiting) | Not used |

Frontend routing (`public/js/firebase.js`) selects the config by environment:
- **Beta** (`sms.aviasafesystems.com`, `sms-beta.web.app`, any host containing `beta`, localhost): `gap-analysis-ssp` client config, `databaseId: "sms-db"`, `apiBaseUrl: "https://aviasafe-unified-platform.onrender.com"`, `environment: "beta"`.
- **Production** (everything else, including `sms.aviasafesystems.com` and tenant subdomains `*.aviasafesystems.com`): `aerosafety-sms-prod` client config, `databaseId: "sms-db"`, `apiBaseUrl: "https://aviasafe-unified-platform.onrender.com"`, `environment: "production"`.

## Isolation Migration (2026-08-18)

Previously the beta Firestore database (`sms-db`) lived inside the **production** project (`aerosafety-sms-prod`), sharing its Auth pool. Completed migration:

1. Created `sms-db` in `gap-analysis-ssp` (us-west1, native, PITR 7d).
2. Deployed Firestore rules + indexes: `firebase deploy --only firestore:sms-db --project gap-analysis-ssp`.
3. Copied **2,233 documents** (tenants incl. nested subcollections, users, audit_logs, regulators, feedback, seed_metadata) via `backend/scripts/migrate_beta_db.py`; `--verify` reports 2,233/2,233 with 0 missing / 0 extra / 0 checksum mismatch.
4. Purged 63 legacy Auth accounts from the `gap-analysis-ssp` pool and re-provisioned the 50-user seed (`backend/scripts/purge_auth_pool.py` + `python -m seed.deploy_seed --users-only --yes`). Audit (`backend/scripts/audit_seed_beta.py`) passes all data + provisioning checks.
5. Beta Firebase **web** config (in `public/js/firebase.js` `BETA_CONFIG`): apiKey `AIzaSyAhvyNyLyqRWidGIkk-by3J9bJ5xtSFTdc`, authDomain `gap-analysis-ssp.firebaseapp.com`, projectId `gap-analysis-ssp`, storageBucket `gap-analysis-ssp.firebasestorage.app`, messagingSenderId `817614332543`, appId `1:817614332543:web:01224a312e8478b24d554a`.

## Security Guardrails (deployed with the isolation work)

- **Registration gating** (`backend/app/services/tenant_registration.py` + `settings.ENVIRONMENT`):
  - Production requires the enterprise access code (`BETA_ACCESS_KEY`) — self-service registration is by invitation only (403 otherwise).
  - Beta keeps the optional access key and tags every self-service tenant with `{ "is_beta_sandbox": true, "auto_expire_days": 30 }`.
- **Rate limiting** (`backend/app/middleware/rate_limit.py`, Redis): `register_tenant` 10/hr/IP, `join_team` 30/hr/IP, `register` 10/hr/IP, `verify-invite`/`tenant-lookup` 200/hr/IP, `copilot` (incl. guest) 120/hr/IP.
- **App Check** (`backend/app/middleware/app_check.py`): `X-Firebase-AppCheck` tokens are verified server-side on register/join/verify/lookup/guest-chat. Clients activate reCAPTCHA v3 on `register.html`/`join.html` via `public/js/firebase.js`; the **beta reCAPTCHA site key is not yet provisioned** — register it in the `gap-analysis-ssp` console (Security > App Check) and paste into `BETA_CONFIG`/`APP_CONFIG.recaptchaSiteKey`.
- **Copilot boundary** (`backend/app/services/groq_copilot.py`): prompt-injection and out-of-scope queries are rejected in code before any model call.

## Firestore PITR — Verified Retention (sms-db, gap-analysis-ssp)

Verified with:

```
gcloud firestore databases describe --database=sms-db --project=gap-analysis-ssp
```

Key output:

```
pointInTimeRecoveryEnablement: POINT_IN_TIME_RECOVERY_ENABLED
versionRetentionPeriod: 604800s        # = 7 days
locationId: us-west1
type: FIRESTORE_NATIVE
```

**Result:** PITR is enabled with a **7-day retention** (`versionRetentionPeriod: 604800s`) — the maximum; no change required.

### Reference: forcing 7-day retention (not needed, documented for completeness)

```
gcloud firestore databases update --database=sms-db --project=gap-analysis-ssp --enable-pitr --retention-duration=7d
```

## Deployment Notes

- Beta hosting site `sms-beta` lives in **`gap-analysis-ssp`**, production site in **`aerosafety-sms-prod`**. Deploy each separately:
  - Beta: `firebase deploy --only hosting:sms-beta --project gap-analysis-ssp`
  - Prod: `firebase deploy --only hosting:aerosafety-sms-prod --project aerosafety-sms-prod`
- Beta Render service (`sms-aviasafesystems-beta`) env vars — **REQUIRED for the isolated project**:
  - `FIREBASE_PROJECT_ID=gap-analysis-ssp`
  - `FIREBASE_CLIENT_EMAIL` / `FIREBASE_PRIVATE_KEY` = the `gap-analysis-ssp` service-account (key file `backend/gap-analysis-ssp-sa.json`, gitignored)
  - `FIREBASE_DATABASE_ID=sms-db`
  - `ENVIRONMENT=beta`
  - `REDIS_URL` (Upstash), `ALLOWED_ORIGINS` (must include `https://sms.aviasafesystems.com` and `https://sms-beta.web.app`), `GROQ_API_KEY`, `GEMINI_API_KEY`, `DEBUG=false`
- Firestore rules/indexes are per-project now: `firebase deploy --only firestore:sms-db --project gap-analysis-ssp` for beta; `--project aerosafety-sms-prod` for production.

## Verification Commands

```bash
# Backend liveness
curl https://aviasafe-unified-platform.onrender.com/live

# Firestore PITR state (beta project)
gcloud firestore databases describe --database=sms-db --project=gap-analysis-ssp

# Migration integrity (from backend/, with gap-analysis-ssp SA env)
python scripts/migrate_beta_db.py --verify

# Seed/data-structure audit against the isolated beta DB
python scripts/audit_seed_beta.py

# Redis rate-limit keys (from a machine with redis access)
# expect rl:<type>:<tenant|ip>:<period> keys while active
```

## Related Documents

- `docs/BETA_TEST_CHECKLIST.md` — tester checklist
- `docs/BETA_INVITATION_TEMPLATE.md` — tester invitation email
- `docs/FEEDBACK_FORM_STRUCTURE.md` — feedback form fields