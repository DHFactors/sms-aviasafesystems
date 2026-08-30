# Installation & Local Development

Guide for setting up the AviaSAFE platform locally for development and testing.

## 1. Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.11+ (3.11.8 pinned in Docker) | Backend runtime |
| Git | any | Clone repository |
| Node.js / npm | 18+ (optional) | Firebase CLI, JS syntax checks |
| Firebase CLI | latest (optional) | Emulator, local hosting, rules deploy |
| Google Cloud / Firebase project | `aerosafety-sms-prod` or your own | Auth, Firestore, App Check |
| Service account JSON | — | Firebase Admin SDK for the backend |

## 2. Clone & structure

```bash
git clone <repo-url> aviasafe-platform
cd aviasafe-platform
```

Key directories: `backend/` (FastAPI service), `public/` (static frontend), `scripts/`
(provisioning), `firestore/` (security rules), `tests/` + `backend/tests/` (tests).

## 3. Backend setup

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate

pip install -r requirements.txt
```

### 3.1 Environment variables

Copy the template and fill it in:

```bash
copy .env.example .env      # Windows
cp .env.example .env        # macOS / Linux
```

The backend loads `backend/.env` automatically (absolute path resolution in
`backend/app/core/config.py`; settings are case-sensitive). Full setting reference:

| Variable | Required | Default | Notes |
|---|---|---|---|
| `FIREBASE_PROJECT_ID` | Yes | — | Firebase project id |
| `FIREBASE_PRIVATE_KEY` | Yes | — | Service-account private key (quoted, `\n` escapes) |
| `FIREBASE_CLIENT_EMAIL` | Yes | — | Service-account client email |
| `GEMINI_API_KEY` / `AI_API_KEY` | No | — | Gemini; mock analysis used when absent |
| `SETUP_SECRET` | For admin ops | — | Second factor for provisioning endpoints |
| `DEFAULT_PROVISION_PASSWORD` | For `/provision-airlines` | — | No hardcoded fallback |
| `DEFAULT_SEED_PASSWORD` | For seed pipeline | — | No hardcoded fallback |
| `ALLOWED_ORIGINS` | No | `https://sms.aviasafesystems.com,https://aerosafety-sms-prod.web.app,https://demo.aviasafesystems.com,http://localhost:3000,http://localhost:8000` | Comma-separated CORS list |
| `DEBUG` | No | `false` | Enables verbose logging |
| `REDIS_URL` | No | empty | Enables Redis rate limiting when set |
| `RATE_LIMIT_PER_MINUTE` | No | `60` | Per-IP limit |
| `DISABLE_DESTRUCTIVE_ENDPOINTS` | No | `true` | Data-destructive admin endpoints return 404 |
| `HOST` / `PORT` / `WORKERS` | No | `0.0.0.0` / `8000` / `1` | Server binding |

> **Never commit `backend/.env`.** It is excluded from the repository. Do not paste real keys into
> documentation or example files.

### 3.2 Firebase Admin SDK credential

The backend uses the service-account **private key + client email + project id** (not a file path).
In production these are provided via the platform env config (see [DEPLOYMENT.md](./DEPLOYMENT.md)).

To use a service-account JSON file locally, you can derive the values:

```bash
# With a serviceAccountKey.json downloaded:
# FIREBASE_PRIVATE_KEY  = contents of "private_key"
# FIREBASE_CLIENT_EMAIL = contents of "client_email"
# FIREBASE_PROJECT_ID   = contents of "project_id"
```

## 4. Run the backend

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Interactive API docs: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health: `http://localhost:8000/health`
- Route count check: `python -c "from app.main import app; print(len(app.routes))"`

> **Note on routes:** the canonical API is under `/api/v1/...`. Legacy `/api/...` aliases also
> exist for backward compatibility and are hidden from OpenAPI docs.

## 5. Seed data

The deterministic, idempotent seed pipeline lives in `backend/seed/` and imports the ICAO
pillars/elements, 20 airline tenants, demo users, and sample VSR/MOR data.

```bash
cd backend
# Requires FIREBASE_* and DEFAULT_SEED_PASSWORD in backend/.env
python -m seed.runner               # seed if not already seeded (idempotent)
python -m seed.runner --dry-run     # show counts without writing
python -m seed.runner --force       # delete and recreate
python -m seed.runner --reports-only
python -m seed.runner --surveys-only
python -m seed.runner --users-only
```

Seed credentials are **env-driven** — there is no hardcoded password in the source
(`backend/seed/config.py` fails closed when `DEFAULT_SEED_PASSWORD` is empty).

## 6. Run the frontend locally

The frontend is static; it expects the deployed Firebase project (Auth/App Check/Firestore).

```bash
firebase serve --only hosting
# open http://localhost:5000
```

For full local emulation (Auth, Firestore, App Check) see the
[Firebase Emulator Suite docs](https://firebase.google.com/docs/emulator-suite). Note that local
emulation requires the frontend `firebase.js` to point at emulator config and the backend
`FIREBASE_*`/App Check to be relaxed — treat this as advanced setup.

## 7. Running tests

See [tests/README.md](../tests/README.md) for the full guide.

```bash
cd backend
python -m pytest tests/ -q          # unit/integration suite (must stay green)
```

## 8. Common issues

| Symptom | Cause / fix |
|---|---|
| `403` on admin endpoints | Missing `SETUP_SECRET` (503) or non-SUPER_ADMIN token (403) |
| Custom claims not applied | Firebase propagation delay; email→tenant fallback kicks in automatically |
| Gemini mock used | `GEMINI_API_KEY`/`AI_API_KEY` unset — expected for offline dev |
| Seed users created with unknown passwords | `DEFAULT_SEED_PASSWORD` not set in env |
| CORS errors from `localhost:3000` | Add the origin to `ALLOWED_ORIGINS` |

## 9. Next steps

- [ARCHITECTURE.md](./ARCHITECTURE.md) — system overview
- [DEPLOYMENT.md](./DEPLOYMENT.md) — production deployment
- [OPERATIONS.md](./OPERATIONS.md) — day-to-day operations
