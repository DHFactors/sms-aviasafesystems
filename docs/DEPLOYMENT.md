# Deployment Guide

How the AviaSAFE platform is deployed and how to deploy it to each environment.

## 1. Current Deployment (as of RC-3)

| Surface | Provider | Location |
|---|---|---|
| Frontend (static site) | Firebase Hosting | `https://aerosafety-sms-prod.web.app` → `https://sms.aviasafesystems.com` (custom domain) |
| Backend API | Render (Docker) | `https://aviasafe-unified-platform.onrender.com` |
| Database | Cloud Firestore (`sms-db`) | Firebase project `aerosafety-sms-prod`, region `us-west1` |
| Auth / App Check | Firebase Auth + App Check (reCAPTCHA v3) | Same project |

**Live production URL: `https://sms.aviasafesystems.com`** (custom domain attached to the Firebase
Hosting site; `https://aerosafety-sms-prod.web.app` remains the default fallback).

OpenAPI docs: `https://aviasafe-unified-platform.onrender.com/docs`

> **Note:** the currently active Render service name is `aviasafe-unified-platform`. Repo deploy
> configs (`render.yaml`, `backend/render.yaml`) declare the service as `aviasafe-api`. Reconciling
> this naming mismatch is tracked in [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md) (TD-8).

## 2. Environment Variables

Required in **every** environment:

| Variable | Where used |
|---|---|
| `FIREBASE_PROJECT_ID` | Backend — Admin SDK |
| `FIREBASE_PRIVATE_KEY` | Backend — Admin SDK (quoted, with `\n` escapes) |
| `FIREBASE_CLIENT_EMAIL` | Backend — Admin SDK |
| `GEMINI_API_KEY` (or `AI_API_KEY`) | Backend — AI suggestions (mock fallback if empty) |
| `SETUP_SECRET` | Backend — admin provisioning endpoints (RC-1) |
| `DEFAULT_PROVISION_PASSWORD` | Backend — `/provision-airlines` |
| `DEFAULT_SEED_PASSWORD` | Backend — seed pipeline |
| `ALLOWED_ORIGINS` | Backend — CORS allow-list |
| `DEBUG` | Backend — set `false` in production |
| `REDIS_URL` | Optional — Redis-backed rate limiting |

Firebase Web config (API key, project id, app id, messaging sender id) lives in
`public/js/firebase.js` for the **web client only**; it is not a backend secret.

## 3. Backend — Render

Two deploy configs exist in the repo (both named `aviasafe-api`):

1. **`backend/render.yaml`** — Docker deploy (used by the current live service):
   - `env: docker`, `dockerfilePath: Dockerfile`, `healthCheckPath: /live`
   - Secrets are wired as `sync: false` (fill in the Render console).
   - `PYTHON_VERSION: 3.11.8`.
2. **`render.yaml`** (repo root) — bare-python deploy (alternative):
   - `workingDir: backend`, `startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

**Deploy steps (Docker path):**
1. Connect the GitHub repo to a new Render **Web Service**.
2. Choose `Docker` runtime; point `dockerfilePath` at `backend/Dockerfile`, `dockerContext` at `backend`.
3. Add the env vars from §2 (mark secrets, don't commit values).
4. Set health check path to `/live`.
5. Deploy. Verify `https://<service>.onrender.com/health` returns healthy and `/docs` loads.

**Rollback:** Render keeps prior deploys — in the service dashboard, choose the previous deploy and
"Rollback". Because all config is env-driven, a rollback to a prior image is sufficient to restore a
known-good state.

## 4. Backend — Google Cloud Run (target / future)

`backend/cloudrun.yaml` defines the target commercial deployment (min 1 / max 10 instances,
CPU-throttling off, `/live` startup + liveness, `/ready` readiness, 300s timeout). **Cloud Run is
not yet the live target**; moving to it is a commercial-phase decision.

```bash
gcloud builds submit backend/ --tag gcr.io/${PROJECT_ID}/aviasafe-api
gcloud run deploy aviasafe-api \
  --image gcr.io/${PROJECT_ID}/aviasafe-api \
  --platform managed --region us-central1 \
  --project ${PROJECT_ID}
```

Set the same env vars as §2 via `gcloud run services update ... --set-env-vars` or Secret Manager.

## 5. Frontend — Firebase Hosting

The same `public/` folder is deployed to **both** hosting sites so beta and production never drift.
The two sites live in **different Firebase projects**, so each must be deployed explicitly:

```bash
# Production — site aerosafety-sms-prod (project aerosafety-sms-prod)
firebase deploy --project aerosafety-sms-prod --only hosting:aerosafety-sms-prod

# Beta — site sms-beta (project gap-analysis-ssp → https://sms-beta.web.app)
firebase deploy --project gap-analysis-ssp --only hosting:sms-beta
```

> **Important:** do **not** run `firebase deploy --only hosting` (without a site target). `firebase.json`
> declares both hosting sites, but `sms-beta` lives in project `gap-analysis-ssp`, so the CLI fails with
> `could not find site "sms-beta"`. Always target the site + project explicitly, and deploy **both** so
> beta and prod stay consistent.

- Hosting DB/API selection is automatic from the hostname in `public/js/firebase.js`: hostnames
  containing `beta` use `sms-db-beta` + the beta Render API; everything else uses `sms-db` + prod API.
- No build step: `public/` is served as-is.
- `firebase.json` routes all requests to `index.html` (SPA rewrite) and caches static assets
  aggressively.

**Rollback:** `firebase hosting:channel:deploy` for staging channels; for production rollback use the
Hosting console "Release history" and promote a previous version.

## 6. Firestore

- Collections are created on first write; no migrations required for the current schema.
- Security rules live in `firestore/firestore.rules` (deployed). Indexes:
  `firestore.indexes.json` (also mirrored under `backend/firestore.indexes.json`).
- Deploy rules/indexes:
  ```bash
  firebase deploy --only firestore:rules
  firebase deploy --only firestore:indexes
  ```
- Backups are **not automated** (see [OPERATIONS.md](./OPERATIONS.md) and
  [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md)).

## 7. Release Procedure

1. `python -m pytest tests/ -q` in `backend/` — must pass.
2. Smoke-check `/live`, `/ready`, `/health`, `/metrics`.
3. Verify one VSR + one MOR submission, dashboard load, and risk-matrix classification on staging.
4. Deploy backend, then frontend. Redeploy rules only when rules change.
5. Record version/commit in the status report.

## 8. Environments

| Environment | Backend | Frontend | Data |
|---|---|---|---|
| Local dev | `uvicorn` on `:8000` | `firebase serve` `:5000` | emulator or live project |
| Staging | Render branch preview / Firebase channel | Firebase preview channel | shared `aerosafety-sms-prod` |
| Production | Render `main` | `sms.aviasafesystems.com` (custom domain) | shared `aerosafety-sms-prod` |

**Known limitation:** no dedicated staging Firestore project exists; staging and production share
`aerosafety-sms-prod`. See [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md).

## 9. Release Log

| Date | Commit | Scope | Environments |
|---|---|---|---|
| 2026-08-07 | `4f71944` | Phases 1–3: per-tenant survey rate-limit control, view-only authorized users list, survey instructions management | Beta + Production |

**Release notes (Phases 1–3, `4f71944`):**

- Backend: `PUT /api/v1/tenants/{tenantId}/config`, `GET /api/v1/tenants/{tenantId}/config` (auth
  optional), `GET /api/v1/tenants/{tenantId}/users`, plus Redis key `rl:survey:{tenantId}:{date}`.
- Frontend: dashboard Administration section (Survey Rate Limit, Survey Instructions, Authorized
  Users); portal survey renders tenant `survey_instructions` at the top.
- Database: `users` collection mirrored from Firebase Auth. Backfilled on beta (`sms-db-beta`) and
  production (`sms-db`): `python scripts/backfill_users.py sms-db-beta | sms-db`.
- **Production tenant policy:** production `sms-db` is intentionally kept empty of tenant documents
  until contracts are signed. Tenant config is validated on beta and the correct `tenants/{id}`
  document (with `config.survey_rate_limit` / `config.survey_instructions`) is replicated to
  production at go-live. Until then, prod `GET /{tenantId}/config` returns `404` and the rate-limit
  resolver uses the `SURVEY_RATE_LIMIT` env default.
