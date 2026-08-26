# 📝 AviaSAFE SMS — Project Status Report

**Project**: AviaSAFE SMS — Safety Climate Measurement System (ICAO Annex 19 compliant)
**Report Date**: 2026-08-24
**Prepared by**: AviaSAFE Systems engineering (Opencode-assisted)
**Verification**: Backend suite **558 passed**, frontend UX changes deployed to Firebase Hosting
(prod + beta), Docker demo image built and boot-tested (`/live` OK, `database=sms-db-beta`).

---

## 1. Executive Summary

| Item | Value |
|------|-------|
| **Project Name** | AviaSAFE SMS |
| **Report Date** | 2026-08-24 |
| **Overall Status** | **Latency baseline completed (root causes identified), request-level `[PERF]` instrumentation implemented (not yet pushed to Render), and a fully verified local Docker demo environment targeting `sms-db-beta` delivered. Production/beta Render services untouched and live.** Backend suite: **558 tests passing** |
| **Current Phase** | Beta Testing (pre-production) — RC-4/5/6 remain; performance evidence-gathering before any Render → Cloud Run decision |

**Key Highlights**
- **Latency root-cause analysis (analysis-only)** — Three dominant sources identified from code
  audit: ① Render free-tier cold starts (~15 min sleep; confirmed by retry logic in
  `public/js/api/client.js:109`), ② ~160 unfiltered full-collection Firestore `.get()` scans vs
  ~17 filtered queries (worst: `collection_group()` scans across ALL tenants on CAAN dashboards,
  `dashboard_service.py:522-536`), ③ Gemini/Groq calls with no timeout configured.
- **Region facts settled** — Firestore `sms-db` = `us-west1`; Product Owner confirmed Render
  region = Oregon → already co-located with Firestore. `docs/DEPLOYMENT.md:86` targets Cloud Run
  `us-central1`, which would *add* latency; must be corrected to `us-west1` when migration happens.
- **`[PERF]` timing instrumentation** — New `backend/app/core/perf.py`: one structured log line per
  watched endpoint (`total= uptime= firestore= gemini= groq= redis=`); `uptime` distinguishes cold
  vs warm requests; kill-switch `AVIASAFE_PERF=off`; removal = delete file + one middleware line.
  10 watched endpoints cover dashboards, report intake, hazards, surveys, AI copilot.
- **Deployment-sync gap found** — Local `main` was **ahead of origin/main by 16 commits**; Render
  builds only from GitHub, which is why no `[PERF]` lines appear in Render logs yet (Task 03).
  Push is a pending Product Owner decision (ships instrumentation + queued frontend commits).
- **Local Docker demo environment (one-click)** — `start_demo.bat` builds/runs the FastAPI image
  on `localhost:8000` against **`sms-db-beta`**; frontend override hook
  (`localStorage 'aviasafe:localApiBaseUrl'`) points `firebase serve` traffic at it; canonical CORS
  extended for localhost origins. Boot-verified end-to-end.
- **Secret-leak prevention** — `.env.demo` (real credentials, created from `backend/.env`) was NOT
  covered by `.gitignore`'s `*.env` pattern; explicit ignore entries added and verified via
  `git check-ignore`.
- **Frontend UX hardening shipped to Firebase Hosting (prod + beta)** — Hero "Request Demo" CTA
  converted to `<button>` with inline modal-open JS; silent URL reset for
  `?demo_requested=success`; broken emoji hearts replaced with `&hearts;` entity repo-wide;
  standard-user navigation sealed off `/safety.html` (responsible-manager, master-register, cans,
  caps); KPI decoupled into "Total Actionable Tasks"; standardized 3-line footers appended to the
  four premium dashboards.

---

## 2. Work Completed

### 2.1 This Report Period (2026-08-20 → 2026-08-24)

| Item | Files | Status |
|---|---|---|
| Latency baseline & root-cause report (no code change) | chat deliverable (Task 01) | ✅ Complete |
| `[PERF]` timing middleware + watched endpoint registry | `backend/app/core/perf.py` (new), `backend/app/main.py` | ✅ Complete (`ab78813`) |
| Gemini / Groq / Redis component timers | `backend/app/services/gemini.py`, `groq_copilot.py`, `middleware/rate_limit.py` | ✅ Complete (`ab78813`) |
| Firestore timers on overview / master-register / caan-state | `backend/app/routes/dashboard.py` | ✅ Complete (`ab78813`) |
| Deployment-sync diagnosis (Render vs GitHub) | Task 03 report | ✅ Complete |
| Demo env template (no secrets) | `backend/.env.demo.example` | ✅ Complete (`fed3ed9`) |
| One-click Windows startup script | `start_demo.bat` | ✅ Complete (`fed3ed9`) |
| Canonical CORS: `localhost:3000`, `127.0.0.1:3000` | `backend/app/main.py` | ✅ Complete (`fed3ed9`) |
| Frontend local-API override hook | `public/js/firebase.js` | ✅ Complete (`fed3ed9`) |
| Real demo env targeting `sms-db-beta` + gitignore fix | `backend/.env.demo` (untracked), `.gitignore` | ✅ Complete (local only) |
| Hero CTA `<button>` fix + inline modal JS | `public/index.html` | ✅ Deployed (`a2c0e6b`) |
| Silent URL reset (alert removed) | `public/index.html` | ✅ Deployed (`33c573d`) |
| Footer `&hearts;` entity standardization (7 pages) | `index/privacy/terms/portal/dashboards` | ✅ Deployed (`33c573d`) |
| Standard-user nav sealing (no `/safety.html` links) | `responsible-manager.html`, `master-register.html`, `cans.html`, `caps.html` | ✅ Deployed (`33c573d`) |
| KPI decoupling: "Total Actionable Tasks" | `responsible-manager.html`, `master-register.html` | ✅ Deployed (`33c573d`) |
| 3-line premium footers appended (4 dashboards) | `safety.html`, `caan.html`, `ae-dashboard.html`, `caan-sms-maturity.html` | ✅ Deployed (`33c573d`) |

### 2.2 Pending / Requires Action

- **Push 16 local commits to origin/main** — required before Render receives `[PERF]`
  instrumentation; also ships queued frontend/backend commits. Both Render services will pick it up
  if auto-deploy is enabled (instrumentation is passive + kill-switchable; 558/558 tests pass).
- **Collect cold/warm `[PERF]` measurements** using the Task 02 procedure (Render logs, filter
  `[PERF]`); fill the results table; then decide Cloud Run with evidence.
- **Cloud Run migration decision** — parked deliberately. When pursued: region MUST be `us-west1`
  (fix `DEPLOYMENT.md:86`), `min-instances=1` (~$10–15/mo within GCP credit), secrets via Secret
  Manager; route A (`cloudbuild.yaml`) vs B (native UI deploy) still undecided.
- **Beta reCAPTCHA site key (App Check)** — carried over from 2026-08-19 report; still pending in
  `gap-analysis-ssp` console.
- **Demo-day caveats** — `.env.demo` keeps `DEBUG=True` and
  `DISABLE_DESTRUCTIVE_ENDPOINTS=false` from `.env`; avoid admin destructive actions during the
  live demo against real beta data.

---

## 3. Verification

- `python -m pytest tests/ -q` in `backend/` → **558 passed** (includes instrumentation changes).
- Docker: `aviasafe-demo-api:latest` built (621MB); container boot test → `/live` =
  `{"status":"alive"}`; startup log = `Firebase Admin SDK initialized successfully
  (database=sms-db-beta)`; CORS preflight `OPTIONS` from `http://localhost:3000` →
  `Access-Control-Allow-Origin` echoed correctly.
- Frontend deploys: all UX changes released to both `aerosafety-sms-prod` and `aerosafety-sms-beta`
  hosting targets via Firebase CLI (independent of GitHub/Render state).
- `git check-ignore backend/.env.demo` → ignored (secret-leak path closed).

---

## 4. Next Steps

1. Product Owner decision: **push** the 16-commit local queue to GitHub (activates `[PERF]` on
   Render prod + beta).
2. Run the manual cold/warm measurement procedure; record results table from Render logs.
3. Review measurements → go/no-go on Cloud Run (`us-west1`, `min-instances=1`, cloudbuild.yaml
   route A vs native UI route B) and on the query-pattern remediation work (filtered queries,
   parallel fetches, AI timeouts, gzip).
4. Carry-over: provision beta App Check reCAPTCHA key in `gap-analysis-ssp`.
