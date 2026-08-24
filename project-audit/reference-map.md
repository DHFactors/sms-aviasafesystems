# Reference Map — How Entry Points Reach Files

**Branch:** `audit/checkpoint-2026-08-24`  
**Goal:** For every candidate legacy file, search imports / requires / path refs / Docker COPY / package scripts / route refs / template refs / env refs.

## Entry Points

### Backend
- **Uvicorn entry:** `backend/app/main.py:63` `app = FastAPI(...)` + `Dockerfile:13` `CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}` + `docker-compose.yml:14` `build: context: ./backend` + `render.yaml:6` `startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Config:** `backend/app/core/config.py:9` loads `backend/.env` / `FIREBASE_DATABASE_ID`, `backend/.env.demo.example` for local beta
- **Firebase:** `backend/app/firebase.py:12` `initialize_firebase()` called in `main.py:57` lifespan, used by all services via `get_db()`, `get_tenant_collection()`, `get_cross_tenant_collection()`
- **Routes:** `backend/app/main.py:224` `app.include_router(reports.router, prefix=...)` etc. for 18 routers (`routes/*.py`)
- **Tests:** `backend/tests/conftest.py:4` `from app.main import app`, `package-lock.json` not used by backend

### Frontend
- **Hosting:** `firebase.json:15` `"public": "public"` + rewrites `** -> /index.html` (SPA), `src/pages/index.astro` (Astro marketing page, not the `public/` SPA)
- **JS entry:** `public/js/firebase.js`, `public/js/api/client.js` (ApiClient), `public/js/dashboard.js`, `public/js/tenant_context.js` loaded via `<script src="/js/...">` in `public/*.html`
- **No build:** `package.json:13` `"build": "echo 'No build step required'"` — static files served directly

### Runtime Config
- `firebase.json:3` declares two Firestore DBs: `sms-db` (prod, `firestore.indexes.json`) + `sms-db-beta` (beta, `backend/firestore.indexes.json`) sharing `firestore/firestore.rules`
- `backend/.env` (ignored, `sms-db-beta` for local Docker via `docker-compose.yml:17`), `backend/.env.example` / `.demo.example` templates
- `render.yaml:8` envVars `FIREBASE_DATABASE_ID=sms-db` for prod

### Deployment
- **Docker:** `backend/Dockerfile:5` `COPY requirements.txt` + `COPY . .` (backend context only — root `add_*.py` not copied)
- **Compose:** `docker-compose.yml:14` `context: ./backend` — root one-offs not in image
- **Render:** `backend/render.yaml:4` `dockerfilePath: Dockerfile` + `render.yaml:4` python fallback
- **CI:** `.github/workflows/deploy.yml.disabled` is disabled (`.disabled` suffix), not `deploy.yml` — GitHub ignores it

---

## Search Method

For each root/legacy file `F`:
```bash
git grep -l -- "F"            # imports / requires / path refs
grep -R "F" package.json Dockerfile docker-compose.yml render.yaml firebase.json firestore.rules
grep dynamic loading: `import(` `require(` `fetch(` `collection(` in backend/app and public
git log --follow -- "F"        # history when appears obsolete
```

Result for candidates:

| File | Import / Require hits | Docker COPY | Package script | Route/template ref | Env/config ref | Git history | Verdict |
|---|---|---|---|---|---|---|---|
| `add_cache.py` etc. (28 root `.py`/`.js`) | 0 | No (context `backend/`) | No | No | No | Added 2026-08-24 untracked, one-time `open('public/...')` patches | Unreferenced one-offs |
| `aviasafe_sms_hybrid_landing_page.html` | 0 | No | No | No — `firebase.json:15` only serves `public/` | No | Tracked, no rewrites | Unreferenced |
| `login.html` (root) vs `public/login.html` | 12 hits for string `login.html` but all point to `public/login.html` (served) | No | No | No — root copy not in `firebase.json` public | No | Tracked, duplicate | Root duplicate not served |
| `login_orig.html`/`safety_orig.html` | 0 | No | No | No | No | Tracked, `_orig` suffix | Backup |
| `firebase-debug.log` | 0 | No | No | No | No | Untracked, 59 lines `firebase serve` debug | Generated log |
| `backend/requirements_bak.txt` | 0 | No — `Dockerfile:6` uses `requirements.txt` | No | No | No | Untracked backup, 55 lines `==` vs live `>=` | Duplicate backup |
| `.github/workflows/deploy.yml.disabled` | 0 | No | No | No | No | Untracked, `.disabled` ignored by Actions | Disabled workflow |
| `beta-testing-credentials.csv` / `BETA_CREDENTIALS_*.md` | 6 hits (docs + seed) but `.gitignore:20` ignores them | No | No | No | Not imported (manual) | Untracked, credentials | Secrets (ignored) |
| `backend/_audit_all_tenants.py` | 0 | No (copied via `COPY . .` but not imported) | No | No | No | Untracked diagnostic | Manual tool |
| `backend/_purge_prod_database.py` | 0 | No (copied but not imported) | No | No | No | Untracked, guard `PURGE_SMS_DB` | Destructive tool |
| `backend/add_guards.py` | 0 | No | No | No | No | Untracked | Dev tool |
| `demostart.bat` / `demostop.bat` / `start_demo.bat` | 0 / ref in docs | No | No | No | Docs reference | Tracked/untracked | Local demo helpers |
| `backend/app/**` etc. | >200 hits via `from app.*` | Yes (`COPY . .`) | Indirect | Yes (`include_router`) | Yes (`FIREBASE_DATABASE_ID`) | Tracked since 2026-07-26 | Core runtime |

---

## Dynamic Loading Check

- `backend/app/**/*.py` uses `collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id).collection(...)` — tenant collection name from `config.py`, not filesystem.
- `public/js/**/*.js` uses `ApiClient.get('/api/v1/...')` — routes defined in `backend/app/main.py` routers, not filesystem wildcards.
- No `importlib` wildcard or `glob` that would load root `add_*.py` at runtime.
- No `require('../add_cache')` or `script src="/add_cache.py"` in any public HTML.

## Firestore / Hosting Wildcards

- `firestore.rules:66` `match /tenants/{tenantId}/{document=**}` — path tenant isolation, not file wildcard.
- `firebase.json:23` rewrites `source: "**" -> /index.html` — only `public/` is served, root `login.html` not reachable.
- Wildcard `load` in `app/services/*` via `get_tenant_collection` / `collection_group` — DB-level, not filesystem.

## Environment References

- `backend/app/core/config.py:9` loads `backend/.env` (via `load_dotenv`) — root `*.py` not env-referenced.
- `docker-compose.yml:17` overrides `FIREBASE_DATABASE_ID=sms-db-beta` for local — no root script referenced.
- `render.yaml:15` sets prod `sms-db` — no root script referenced.

## Conclusion

Only `firebase-debug.log`, `backend/requirements_bak.txt`, and `.github/workflows/deploy.yml.disabled` have **zero** references across imports, Docker, package, routes, templates, dynamic loading, and env, **and** are either generated or disabled duplicates. Root one-off `fix_/add_/convert_` scripts also have zero refs but are **not** proven obsolete (they could be manually re-run), so they remain **H**.
