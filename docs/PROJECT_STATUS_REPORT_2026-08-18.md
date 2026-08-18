# 📝 AviaSAFE SMS — Project Status Report

**Project**: AviaSAFE SMS — Safety Climate Measurement System (ICAO Annex 19 compliant)
**Report Date**: 2026-08-18
**Prepared by**: AviaSAFE Systems engineering (Opencode-assisted)
**Verification**: All figures below were verified against the committed codebase (HEAD `63fc583`), the
backend test suite (**358 passed**), the frontend Node test suite, and the live beta environment
(`https://betasms.aviasafesystems.com`) on the report date.

---

## 1. Executive Summary

| Item | Value |
|------|-------|
| **Project Name** | AviaSAFE SMS |
| **Report Date** | 2026-08-18 |
| **Overall Status** | **Ghanshyam Executive Safety Copilot live in guest mode on the register / join / login pages with a defensive model fallback, plus a platform-wide Dark/Light theme switcher** — guest copilot pinned to the beta backend and returning live Groq answers; model hardened against invalid/deprecated config (allowlist validation + automatic 400/404 retry to `openai/gpt-oss-120b`); dark-mode controller + stylesheet wired into all 47 public HTML pages with a header toggle on the landing page. Backend suite: **358 tests passing** |
| **Current Phase** | Beta Testing (pre-production) — RC-3 complete; RC-4/5/6 remain |

**Key Highlights**
- **Guest Safety Copilot on self-service pages (2026-08-18)** — the Ghanshyam copilot widget now runs
  unauthenticated on `register.html`, `join.html` and `login.html`, each with page-specific greetings
  and quick-suggestion chips (org registration / team invite codes & roles / sign-in troubleshooting,
  tenant selection & password resets). Guest requests resolve to `/api/v1/copilot/guest/chat` pinned to
  the beta backend (`sms-aviasafesystems-beta.onrender.com`) so the public pages never 404.
- **Defensive model guard (2026-08-18, `cb7b9ff`)** — `resolve_groq_model()` validates
  `GROQ_MODEL`/env against a curated allowlist (`gpt-oss-120b`, `gpt-oss-20b`, `qwen3.6-27b`,
  `allam-2-7b`); unrecognised/deprecated values log a warning and fall back to the proven production
  model. If an allowlisted model is still rejected by Groq (HTTP 400/404 `model_not_found`), `chat()`
  retries once with the fallback before ever degrading to the offline reply.
- **Dark/Light theme switcher across all 47 pages (2026-08-18, `f1d66a7`)** — `theme-toggle.js`
  applies the `dark` class pre-render (no flash), persists to localStorage with OS-preference fallback,
  auto-injects a toggle into headers (floating button on headerless pages), recolours Chart.js canvases,
  and follows dynamic shell headers. `theme.css` flips design-system surface/border/muted tokens plus
  functional-page and copilot-widget light variants; the landing page uses Tailwind `darkMode:'class'`
  with `dark:` variants throughout. Toggle moved into the landing header's right action cluster
  (`619a671`).
- **Copilot reliability fixes (2026-08-17 → 08-18)** — pinned `groq>=0.11.0` + `httpx>=0.27.0,<0.28.0`
  (resolves the `proxies` keyword error), lazy reusable Groq client keyed by `(api_key, Groq)` with
  `threading.Lock`, `asyncio.to_thread` in async routes, bottom-most exception logging, and the model
  switched to `openai/gpt-oss-120b` after discovering the key's Groq plan exposes no llama-3.x models.
- **Self-service onboarding + landing + login polish (2026-08-17 → 08-18)** — self-service tenant
  registration (`/register.html`), real-time invite-code verification and least-privilege team
  onboarding (`/join.html`), hybrid landing page (`index.html`), brand/deep-teal token migration for
  admin/shell/copilot styles, reserved-subdomain tenant detection, and a streamlined login page
  (active tenant name in the header, subtitle now "Safety Data to Safety Intelligence").

---

## 2. Work Completed

### 2.1 This Report Period (2026-08-17 → 2026-08-18)

| Item | Files | Status | Location |
|---|---|---|---|
| Copilot persona + Groq integration (Ghanshyam, ICAO grounding) | `backend/app/services/groq_copilot.py`, `app/routes/copilot.py` | ✅ Complete | Repo |
| Time-based salutation + strict per-page scoping + guest mode for registration | `public/js/components/copilot-widget.js`, `backend/app/services/groq_copilot.py` | ✅ Complete | Repo |
| Groq client init + error-logging fixes (env-key client, explicit status logging) | `backend/app/services/groq_copilot.py` | ✅ Complete (`f78a178`) | Repo |
| Guest chat pinned to beta backend (prevents 404 on prod) | `public/js/components/copilot-widget.js` | ✅ Complete (`53cd131`) | Repo |
| Model → `openai/gpt-oss-120b` (llama-3.x unavailable on plan) | `backend/app/services/groq_copilot.py`, `app/core/config.py`, `backend/.env` | ✅ Complete (`6eb5178`) | Repo |
| Lazy reusable Groq client + async `to_thread` routes + dependency pins | `backend/app/services/groq_copilot.py`, `app/routes/copilot.py`, `backend/requirements.txt` | ✅ Complete (`02528d6`, `d58322c`) | Repo |
| **Guest widget on join.html + login.html + page-specific guidance** | `public/join.html`, `public/login.html`, `public/js/components/copilot-widget.js` | ✅ Complete (`cb7b9ff`) | Repo |
| **Defensive model guard** — allowlist validation + 400/404 retry fallback | `backend/app/services/groq_copilot.py`, `backend/tests/test_copilot.py` | ✅ Complete (`cb7b9ff`) | Repo |
| **Dark/Light theme switcher (47 pages)** — controller, stylesheet, wiring | `public/js/theme-toggle.js`, `public/css/theme.css`, all 47 `public/**/*.html` | ✅ Complete (`f1d66a7`) | Repo |
| Landing page Tailwind `darkMode:'class'` + `dark:` variants | `public/index.html` | ✅ Complete (`f1d66a7`) | Repo |
| Copilot widget light-mode variant | `public/css/copilot-widget.css` | ✅ Complete (`f1d66a7`) | Repo |
| Theme toggle repositioned into right header actions | `public/index.html` | ✅ Complete (`619a671`) | Repo |
| Login subtitle → "Safety Data to Safety Intelligence" (static + JS fallback) | `public/login.html` | ✅ Complete (`63fc583`) | Repo |
| Self-service tenant registration + team onboarding | `public/register.html`, `public/join.html`, backend auth routes | ✅ Complete (`c1a4869`) | Repo |
| Real-time invite-code verification + onboarding safeguards | `public/join.html`, backend `verify-invite` / `tenant-lookup` | ✅ Complete (`f554ef0`) | Repo |
| Hybrid landing page (hero + capabilities + dual beta onboarding) | `public/index.html` | ✅ Complete (`9c4a0cc`, `9487c5d`) | Repo |
| Brand/deep-teal design-token migration (admin, shell, copilot, print) | `public/css/*.css` | ✅ Complete (`ad86cd3`) | Repo |
| Login cleanup — active tenant header, streamlined footer, reserved-subdomain detection | `public/login.html`, `public/js/tenant_context.js` | ✅ Complete (`66d4a1c`, `d0edd97`, `7e8c571`) | Repo |
| Deploy both hosting targets after copilot + theme work | `sms-beta` (Firebase Hosting) + backend (Render auto) | ✅ Complete | Live |

### 2.2 Prior Completed Features

- **RC-3 (2026-08-14 → 08-17)** — seed v2.2.0, universal CAAN oversight (12 providers), tenant
  classification model, 50-account provisioning.
- See `docs/PROJECT_STATUS_REPORT_2026-08-17.md`, `docs/PROJECT_STATUS_REPORT_2026-08-14.md` and
  earlier dated reports.

---

## 3. Test Verification

### 3.1 Backend Test Suite (2026-08-18)

| Check | Result |
|-------|--------|
| Full backend test suite | ✅ **358 passed** |
| Copilot tests (persona, page-scoping, guest chat, context injection, offline fallback, sanitisation) | ✅ Pass |
| Model-guard tests — known-model accept, unknown-model fallback, unset-model default, 400/404 retry with fallback model, offline when fallback also fails | ✅ Pass (5 new) |
| Existing suites (auth, tenant, reports, hazards, CAN/CAP, seeding, risk lifecycle, classification) | ✅ Pass |

### 3.2 Frontend Test Suite

| Check | Result |
|-------|--------|
| `frontend-tests/dashboard.test.js` | ✅ Pass |
| `frontend-tests/tenant-context.test.js` (email mapping, classification-aware dept mapping, demo env detection, subdomain extraction, prod lock) | ✅ Pass |
| `node --check` on modified JS (`copilot-widget.js`, `theme-toggle.js`) | ✅ Pass |

### 3.3 Live Verification (2026-08-18)

| Check | Result |
|-------|--------|
| `POST /api/v1/copilot/guest/chat` (login page context) on beta backend | ✅ HTTP 200, real Groq reply (no offline fallback) |
| `/join.html`, `/login.html` serve widget stylesheet + `copilot-page-context` meta + widget script | ✅ HTTP 200 |
| `/css/theme.css`, `/js/theme-toggle.js`, dark variants on landing | ✅ HTTP 200, deployed |
| Frontend Node suite after all changes | ✅ Pass |

---

## 4. Beta Testing Status

### 4.1 Beta Environment (`sms-db-beta`)

| Aspect | Status | Details |
|--------|--------|---------|
| **Environment** | `sms-db-beta` | Fully seeded, PITR 7-day |
| **Tenants** | 12 operational + 1 regulator | buddha-air, air-dynasty, ktm-mro, pokhara-aerodrome, himalaya-ground-services, yeti-airlines, summit-air, sita-air, simrik-air, tara-air, caan-fssd, caan-assd + caan |
| **Users (Firebase Auth)** | 50 | 1 SUPER_ADMIN + 1 CAAN_SMD + 48 simplified role accounts (12 tenants × 4) |
| **Reports / Hazards / CAN / CAP** | as of 08-17 | 317 reports, 145 hazards, 102 CAN / 200 CAP |
| **Surveys / Responses** | 184 / 184 | 15–24 per tenant, matching |
| **Survey campaigns** | 3 active | buddha-air, yeti-airlines, tara-air (→ 2026-09-13) |
| **Demo profiles** | 5 | login persona selector |
| **Public copilot** | live (guest) | register / join / login — beta backend, Groq-backed |

> Firestore seed documents for the two new directorates (caan-fssd, caan-assd) land when the backend
> re-seeds at v2.2.0 (Render auto-rebuild on push). Auth provisioning is complete and verified.

### 4.2 Relevant Simplified Accounts

| Role | Department | Email | Status |
|------|-----------|-------|--------|
| USER | Part-145 | `145@{tenant-domain}` | ✅ Dept-scoped CANs on "My Tasks" |
| USER | CAMO | `camo@{tenant-domain}` | ✅ Dept-scoped CANs on "My Tasks" |
| USER | Flight Operations | `ops@{tenant-domain}` | ✅ Sees `Flight Operations` CANs |
| AIRLINE_ADMIN | Safety | `safety@{tenant-domain}` | ✅ Full dashboard + non-zero Anon Rate |
| CAAN_SMD | SMD | `smd@caanepal.gov.np` | ✅ Universal regulator dashboard (all 12 providers) |

---

## 5. Known Issues & Limitations

| # | Issue | Severity | Status | Notes |
|---|-------|----------|--------|-------|
| 1 | Copilot model availability on the Groq plan (no llama-3.x) | High | ✅ Resolved | Moved to `openai/gpt-oss-120b`; allowlist + 400/404 retry guard added |
| 2 | Guest chat 404 on production backend (route only on beta) | Medium | ✅ Resolved | Guest requests pinned to the beta backend |
| 3 | Groq client init failure (`proxies` keyword with httpx 0.28 / groq 0.9) | High | ✅ Resolved | Pins `groq>=0.11.0`, `httpx>=0.27.0,<0.28.0` |
| 4 | Firestore seed docs for caan-fssd / caan-assd pending v2.2.0 re-seed | Low | ⚠️ Pending | Auth accounts live; Firestore data lands on re-seed |
| 5 | Monitoring / alerting | Medium | ⚠️ Pending | Not yet configured |
| 6 | MFA (TOTP/SMS) | Medium | ⚠️ Pending | Not yet implemented |
| 7 | Survey 12-element mapping compliance audit (RC-4) | Medium | ⚠️ Pending | Survey 4-component/12-element aligned (v3.0.0); formal audit outstanding |

---

## 6. Next Steps

| # | Milestone | Status |
|---|-----------|--------|
| 1 | Re-seed `sms-db-beta` at v2.2.0 to persist caan-fssd / caan-assd Firestore data + profiles | ⏳ Pending |
| 2 | Re-run `scripts/audit_seed_beta.py` (13 tenants / 12 providers) against live DB | ⏳ Pending |
| 3 | Live-verify demo persona switcher + tenant resolver + FSSD/ASSD logins | ⏳ Pending |
| 4 | RC-4: survey 12-element compliance audit + SMS Maturity dashboard output check | ⏳ Pending |
| 5 | RC-5: CI (lint + pytest + deploy), single `render.yaml`, prune `public/portal` mock code | ⏳ Pending |
| 6 | Invite beta testers (incl. the 12 providers) | ⏳ Pending |
| 7 | Beta launch + 2-week test period | ⏳ Pending |
| 8 | Production go-live (post-beta) | ⏳ Pending |

---

*End of report. Generated 2026-08-18 from committed code (HEAD `63fc583`) + live environment data.*

**User Reference:** For definitions of core terminology, chart legends, hazard matrices, and the CAN/CAP workflow, see [docs/GLOSSARY.md](./GLOSSARY.md).