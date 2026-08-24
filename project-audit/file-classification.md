# File Classification — AviaSAFE SMS

**Branch:** `audit/checkpoint-2026-08-24`  
**Date:** 2026-08-24  
**Scope:** Recursive inventory excluding `node_modules`, `.venv`, `__pycache__`, `.pytest_cache`, `build`, `dist`, `.firebase`, `.git`  
**Inventory:** `project-audit/file-inventory.csv` (476 files)

## Categories

- **A — Core application runtime** — Imported by `backend/app/main.py`, routers, services, middleware; required at import/startup.
- **B — Required configuration/deployment** — `Dockerfile`, `docker-compose.yml`, `render.yaml`, `firebase.json`, `firestore.*`, `.firebaserc`, `requirements.txt`, `package.json`, `astro.config.mjs`, `tailwind.config.mjs`, `tsconfig.json`, env examples.
- **C — Frontend assets, templates, static** — `public/**`, `src/**`, `storage/**` served via Firebase Hosting.
- **D — Tests and development tools** — `backend/tests/**`, `frontend-tests/**`, `load-tests/**`, `tests/**`, `scripts/**`, `backend/scripts/**`, `backend/seed/**`, `functions/**`.
- **E — Project documentation and analysis** — `README.md`, `ROADMAP.md`, `docs/**`, `*.md` analysis reports.
- **F — Generated artifacts or temporary files** — logs, caches, debug outputs (e.g., `firebase-debug.log`) that are recreated on tool run.
- **G — Obsolete/unrelated — high confidence only** — No import, no config, no Docker COPY, no route/template reference, and git history shows one-off or duplicate. Only these are moved.
- **H — Uncertain — leave in place** — No evidence of use, but age/name alone is insufficient; manually executed utilities, backup copies, or docs that could be manually invoked. Preserve.

**Safety rule:** H files stay in place even if unreferenced. Only G with `High` confidence is archived.

---

## Bulk Classification (by directory)

| Path pattern | Category | Evidence | Referenced by | Risk if moved | Action | Confidence |
|---|---|---|---|---|---|---|
| `backend/app/**` (197 files: `main.py`, `routes/*.py`, `services/*.py`, `core/*.py`, `middleware/*`, `models/*`, `firebase.py`, `database.py`, `data/psoe_appendix10.json`) | **A** | Imported via `app.main:app`, `from app.firebase import *`, `from app.services.*` | `backend/app/main.py:15-17` routers/services, `Dockerfile:9` `COPY . .`, tests `backend/tests/conftest.py:4` | **Critical** — app fails to import/start, auth/tenant isolation breaks | Retain | High |
| `backend/requirements.txt`, `backend/.env.example`, `backend/.env.demo.example` | **B** | `Dockerfile:6` `COPY requirements.txt`, `docker-compose.yml:12` `env_file`, `render.yaml:5` `pip install -r backend/requirements.txt` | Docker/Render | Critical — build fails | Retain | High |
| `backend/render.yaml`, `render.yaml`, `docker-compose.yml`, `Dockerfile` | **B** | Deployment entry points; `PORT` binding, `FIREBASE_DATABASE_ID` | `render.yaml:5`, `backend/Dockerfile:13` `uvicorn ... --port ${PORT:-8000}` | Critical — deploy fails | Retain | High |
| `firebase.json`, `firestore.rules`, `firestore.indexes.json`, `backend/firestore.indexes.json`, `.firebaserc`, `.github/workflows/deploy.yml.disabled` | **B** | `firebase.json:3` Firestore DBs/hosting rewrites, `firestore.rules:66` tenant isolation | `firebase deploy` | High — security/hosting breaks if `firestore.rules` moved | Retain (except disabled workflow, see G) | High |
| `package.json`, `package-lock.json`, `astro.config.mjs`, `tailwind.config.mjs`, `tsconfig.json` | **B** | `package.json:6` scripts `dev/build/test`, `tailwind.config.mjs` | `npm run build`, Astro | High — build fails | Retain | High |
| `public/**` ( ~180 files: `public/login.html`, `public/js/firebase.js`, `public/dashboard/**`, `public/js/api/client.js`, `public/js/dashboard.js`, `public/caan.html`, etc.) | **C** | `firebase.json:15` `"public": "public"` hosting, rewrites `** -> /index.html`, `public/js/firebase.js:810` tenant context | Browser, Firebase Hosting | Critical — UI 404 | Retain | High |
| `src/**` (`src/styles/global.css`, `src/layouts/BaseLayout.astro`, `src/pages/index.astro`) | **C** | `astro.config.mjs` Astro pages | `npm run build` dist | Medium | Retain | High |
| `backend/tests/**`, `frontend-tests/**`, `tests/**`, `load-tests/**` | **D** | `backend/tests/conftest.py:4` `from app.main import app`, `package.json:14` `test: node frontend-tests/dashboard.test.js` | CI, `pytest` | High — tests fail | Retain | High |
| `backend/seed/**`, `backend/scripts/**`, `scripts/**`, `functions/**` | **D** | Manual seeding/migration; `backend/seed/config.py` referenced by `app/services/dashboard_service.py:22` via `seed.config` | `python -m seed`, operators | Medium | Retain | High |
| `README.md`, `ROADMAP.md`, `UAT_DEFECT_REGISTER.md`, `manual_verification.md`, `opencode_design_system_plan.md`, `docs/**` (30+ docs) | **E** | Project documentation, not imported | Humans | Low | Retain | High |
| `backend/.env`, `backend/.env.demo`, `backend/aerosafety-sms-prod-sa.json`, `beta-testing-credentials.csv`, `BETA_CREDENTIALS_*.md` | **E/F** (secrets ignored) | `.gitignore:2` `*.env`, `17` `*-sa.json`, `20` `beta-testing-credentials.csv` — untracked, never committed | Local dev only | Critical if deleted (secrets) | Retain (ignored) | High |
| `firebase-debug.log` | **F** | Generated by `firebase-tools` `firebase serve` | `firebase.json` hosting emulator, `.gitignore:48` not listed but tool-generated | None | Archive (G candidate) | High |
| `backend/requirements_bak.txt` | **F/G** | Duplicate backup of `requirements.txt` with `==` pins vs `>=` in live file; `Dockerfile:6` uses `requirements.txt` only | None — `git grep requirements_bak` no hits | None — Docker COPY `. .` would copy it unnecessarily | Archive (G) | High |
| Root one-off patch scripts (`add_*.py`, `fix_*.py`, `convert_*.py`, `replace_*.py`, `find_*.py`, `count_*.py`, `quick_check.py`, `verify_fix.py`, `check_*.py`, `apply_guards.py`, `fix_modal.js`) | **H** | `git grep` found **no refs**; content is one-time `open('public/...').write()` patches (e.g., `add_cache.py:4` hardcodes `public/login.html`). Not imported, not in Docker context for root (Docker context is `backend/`), not in `package.json` scripts, not in `firebase.json` | No runtime consumer identified | **Low if archived** (no import) but **uncertain** — could be manually re-run for future patches; historical value as patch log | **Retain in place (H)** | Low |
| `login.html`, `login_orig.html`, `safety_orig.html` at repo root (duplicates of `public/login.html`) | **H** | `git grep login_orig` no refs; root `login.html` not in `firebase.json:15` public dir (`public/` only). `public/login.html` is served. Root copies appear to be backups before modal/footer fixes | `public/login.html` is canonical | Low — moving root copy won't affect hosting, but could confuse future diffs | Retain (H) — conservative | Medium |
| `aviasafe_sms_hybrid_landing_page.html` at root | **H** | No refs (`git grep` none), not in `public/` nor `firebase.json` rewrites | None | Low | Retain (H) | Medium |
| `demostart.bat`, `demostop.bat`, `start_demo.bat` | **B/D** | Local Docker demo helpers; `demostart.bat` referenced by `docs/PROJECT_STATUS_REPORT_2026-08-24.md:3` and `backend/.env.demo.example:7` `start_demo.bat` | Developer workflow | Low | Retain | High |
| `backend/_audit_all_tenants.py`, `backend/_purge_prod_database.py`, `backend/add_guards.py`, `backend/scripts/fix_summit_air_user.py` | **D** (dev/diagnostic, potentially destructive) | Not imported in `app/main.py`; manually invoked `python backend/_audit_all_tenants.py`; `_purge_prod_database.py:1` has guard `PURGE_SMS_DB` prompt | Operator manual | **High if removed** — purge guard is safety mechanism even if unused | Retain | High |
| `.github/workflows/deploy.yml.disabled` | **G** | Disabled workflow (`*.disabled` extension, not `*.yml`); GitHub ignores it. Original `deploy.yml` tracked then renamed. `git ls-files` shows untracked, no reference in `firebase.json` or `render.yaml` | None — GitHub Actions only loads `*.yml` | None | Archive (G) | High |

---

## Detailed Classification — Root-Level Files (candidates for G/H)

| Path | Category | Evidence | Referenced by | Risk if moved | Recommended action | Confidence |
|---|---|---|---|---|---|---|
| `add_cache.py` | **H** | `git grep add_cache.py` no hits; content patches `public/login.html` cache-buster (already no-op; public files have no `?v=2.1`) | None | Low | **Retain** (historical patch log) | Low |
| `add_cache_buster.py` | **H** | No refs; duplicates `add_cache.py` logic | None | Low | Retain | Low |
| `add_cursor_pointer.py` | **H** | No refs; `open('public/...')` patch for cursor | None | Low | Retain | Low |
| `add_modal_script.py` | **H** | No refs; `open('public/...')` modal script injection | None | Low | Retain | Low |
| `apply_guards.py` | **H** | Pipelines guard injection for `backend/seed/*.py`; not in `package.json` nor Docker | None | Low | Retain | Low |
| `check_and_deploy.py` | **H** | No refs; appears to be deploy verification helper | None | Low | Retain | Low |
| `check_modal.py` | **H** | No refs; checks `public/` modal DOM | None | Low | Retain | Low |
| `convert_button.py` / `convert_button2.py` | **H** | No refs; `open('public/index.html')` a→button conversion (already applied in `public/index.html`) | None | Low | Retain | Low |
| `count_footers.py` / `find_footer.py` / `replace_footer.py` / `replace_footer2.py` | **H** | No refs; footer text standardization scripts (git log shows footer fix already shipped `a2c0e6b`) | None | Low | Retain | Low |
| `fix_button.py`, `fix_cache.py`, `fix_close_button.py`, `fix_css.py`, `fix_cursor.py`, `fix_hero_button.py`, `fix_modal.js`, `fix_modal_responsive.py`, `fix_responsive.py` | **H** | No refs; one-time UI hotfixes (git history `3a703cf fix(footer)` already merged) | None | Low | Retain | Low |
| `quick_check.py`, `verify_fix.py` | **H** | No refs; ad-hoc verification scripts | None | Low | Retain | Low |
| `login.html` (root) | **H** | Duplicate of `public/login.html`; not in `firebase.json:15` `public` dir; `git grep login.html` hits many public files but root copy not the served one | `public/login.html` is canonical | Low | Retain (avoid confusion with served file) | Medium |
| `login_orig.html` / `safety_orig.html` | **H** | No refs; `_orig` backup suffix suggests pre-patch snapshot | None | Low | Retain | Medium |
| `aviasafe_sms_hybrid_landing_page.html` | **H** | No refs; standalone landing page not in `firebase.json` rewrites; not in `public/` | None | Low | Retain | Medium |
| `demostart.bat` / `demostop.bat` / `start_demo.bat` | **B** | `start_demo.bat` referenced by `backend/.env.demo.example:7` and docs | Developer | High if moved | Retain | High |
| `firebase-debug.log` | **F→G** | Generated by `firebase-tools` (`firebase serve --only hosting`); 59 lines, debug output with tokens; `.gitignore` does not list it but `logs/` is ignored; `git grep firebase-debug` no runtime refs | `firebase` CLI | **None** — regenerates on next `firebase serve` | **Archive** | **High** |
| `backend/requirements_bak.txt` | **G** | Backup duplicate of `backend/requirements.txt` (55 vs 57 lines, `==` vs `>=` pins); `Dockerfile:6` `COPY requirements.txt` only; `git grep requirements_bak` no hits; `render.yaml:5` `pip install -r backend/requirements.txt` | None | **None** — Docker would otherwise copy duplicate | **Archive** | **High** |
| `.github/workflows/deploy.yml.disabled` | **G** | Disabled GitHub Action (`.disabled` extension ignored by Actions); `git ls-files` untracked; no reference in `render.yaml` or `firebase.json` | None | **None** — Actions not loaded | **Archive** | **High** |
| `beta-testing-credentials.csv`, `BETA_CREDENTIALS_2026-08-08.md`, `DEMO_CREDENTIALS_VERIFIED.md`, `Survey Questions*.pdf/txt` | **E** | Credentials/docs, some ignored via `.gitignore:20` but `DEMO_CREDENTIALS_VERIFIED.md` untracked docs | Humans | Low | Retain | High |
| `backend/_audit_all_tenants.py` | **D** | Diagnostic audit (20-tenant verification matrix), not imported; manually run `python backend/_audit_all_tenants.py` | Operator manual | Medium — loss of audit tool | Retain | High |
| `backend/_purge_prod_database.py` | **D** | Destructive purge with guard `PURGE_SMS_DB`; not imported | Operator manual (dangerous) | **Critical if misused, but high risk if deleted** | Retain | High |
| `backend/add_guards.py` | **D** | Guard injection utility for seed scripts | Developer | Low | Retain | High |
| `backend/aerosafety-sms-prod-sa.json` | **F** (secret) | Service account key, ignored via `*. -sa.json` in `.gitignore:17` | Local dev auth | Critical if committed | Retain (ignored) | High |

**Summary counts:**  
- A: ~197 files (backend/app core)  
- B: ~15 files (Docker/Render/Firebase/Package)  
- C: ~190 files (public/src/storage + static)  
- D: ~65 files (tests + seed + scripts)  
- E: ~40 files (docs + credential exports)  
- F: 2 generated (log, backup)  
- **G: 3 files high-confidence** (log, backup, disabled workflow) — **only these are moved**  
- H: 28 files (root one-off patches + orig backups) — **leave in place**

Confidence notes: All G files have `no refs` via `git grep` + not in Docker COPY context (root scripts) or `requirements.txt` (backup) or GitHub Actions loader (disabled). All H files have `no refs` too but are kept due to uncertainty — age/name alone is insufficient, and they could be manually invoked.
