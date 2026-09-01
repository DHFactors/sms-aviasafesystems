# Architecture

This document describes the current implementation of the AviaSAFE SMS Platform (as of RC-3).

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend — Firebase Hosting (sms.aviasafesystems.com)            │
│  public/ — static HTML/CSS/JS (Firebase Web SDK v9 compat)       │
│    ┌───────────────────────────────────────────────────────┐     │
│    │ firebase.js → App Check (reCAPTCHA v3) → Auth → ApiClient │  │
│    └───────────────────────────────────────────────────────┘     │
└───────────────────────────────┬─────────────────────────────────┘
                                │ HTTPS — Bearer ID-token (RS256 JWT)
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Backend — FastAPI (Render; target Cloud Run)                    │
│  ┌───────────┐  ┌──────────┐  ┌────────────┐  ┌─────────────┐  │
│  │ Middleware│→ │ Routes   │→ │ Services   │→ │ Firestore   │  │
│  │ auth, rate│  │ 9 routers│  │ 12 modules │  │ (nam5)      │  │
│  └───────────┘  └──────────┘  └────────────┘  └─────────────┘  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Gemini 2.5 Pro (AI suggestion — never authoritative)     │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Upstash Redis (rate limiting, optional)                  │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

- **All tenant data** lives under `/tenants/{tenant_id}/` in Firestore; tenant isolation is
  enforced both in the API and in Firestore security rules.
- **Two API surfaces:** the canonical `/api/v1/...` routes and legacy `/api/...` aliases (hidden
  from OpenAPI) retained for backward compatibility.
- **AI is an assistant only:** it suggests severity/probability; the Safety Manager confirms the
  official `risk_assessment`.

## 2. Technology Stack

| Layer | Technology | Version / Notes |
|---|---|---|
| Frontend | HTML5, CSS3, Vanilla JS | Firebase Web SDK v9.22.0 (compat) |
| Backend | Python + FastAPI + Uvicorn | Python 3.11, FastAPI 0.109.0 |
| Database | Cloud Firestore (`sms-db`) | Firebase project `aerosafety-sms-prod`, location `us-west1` |
| Auth | Firebase Authentication | Email/password; ID-token JWT (RS256) |
| Authorization | Firebase custom claims | `role`, `tenant_id`; 4 roles |
| App Check | reCAPTCHA v3 | Client-side, auto-refresh |
| AI | Google Gemini | `gemini-2.0-pro-exp-02-05`, prompt v2.0 |
| Rate limiting | Upstash Redis + in-memory | 60 req/min per IP default |
| Reports/PDF | ReportLab + ReportGenerator | Placeholder fallback included |
| Deployment | Firebase Hosting + Render (Docker) | Cloud Run target |

## 3. Backend Structure

```
backend/app/
├── main.py            # FastAPI app factory, middleware stack, router registration
├── core/config.py     # pydantic-settings; all env-driven settings
├── core/metrics.py    # Prometheus-style counters (record_ai_result, etc.)
├── firebase.py        # Admin SDK init, get_db(), token verification, collection helpers
├── middleware/
│   ├── auth.py        # Bearer verification + role guard dependencies
│   ├── rate_limit.py  # Redis + in-memory rate limiter
│   └── security_headers.py
├── models/            # Pydantic schemas (report, hazard, can_cap, verification, …)
├── routes/            # auth, reports, hazards, cans, verification, reporting,
│                      #   flight_diversions, dashboard, admin
└── services/          # repository, report_service, hazard_service, can_cap_service,
                       #   verification_service, flight_diversion_service, report_generator,
                       #   dashboard_service, metrics_service, gemini, risk_matrix,
                       #   pdf_generator
```

### Services (12 modules)

| Service | Purpose |
|---|---|
| `Repository` | Firestore query builder, pagination, in-memory cache (60s TTL) |
| `MetricsService` | KPI, trend, risk-distribution calculations |
| `DashboardService` | Role-aware orchestration for airline/CAAN/admin dashboards |
| `ReportService` | VSR/MOR create, retrieve, AI analysis trigger, risk-assessment confirm |
| `HazardService` | Hazard register CRUD + status workflow; auto-created from reports |
| `CanCapService` | Corrective Action Notice / Corrective Action Plan lifecycle |
| `VerificationService` | Hazard verification, closure, reopening |
| `FlightDiversionService` | Diversion CRUD + hazard linking |
| `ReportGenerator` | Quarterly/annual safety report generation + PDF |
| `Gemini` | AI analysis (taxonomy, summary, suggested severity/probability) |
| `RiskMatrix` | ICAO 5×5: `severity × probability → risk index → risk level / outcome` |
| `PDFGenerator` | ReportLab export with placeholder fallback |

## 4. Middleware Stack (execution order)

1. **SecurityHeadersMiddleware** — HSTS, `nosniff`, `X-Frame-Options: DENY`, XSS protection,
   Referrer-Policy, Permissions-Policy.
2. **RateLimitMiddleware** — 60 req/min per IP (in-memory); Redis-backed per-tenant limits on
   auth/report endpoints when `REDIS_URL` is set.
3. **RequestLoggingMiddleware** — request UUID, method/path/status/duration, authenticated user.

## 5. Authentication & Authorization

See [docs/SECURITY.md](./SECURITY.md) for the full model. Summary:

- **Verify:** Firebase Admin SDK `verify_id_token()` (RS256).
- **Role resolution:** custom claims from the token; fallback to Firestore tenant lookup when
  claims have not propagated (known Firebase propagation delay).
- **Tenant normalization:** `_` → `-` in `tenant_id` to reconcile seed vs provisioned data.
- **Guard dependencies** (`middleware/auth.py`): `get_current_user`, `get_tenant_user`,
  `get_caan_user`, `get_admin_user` (SUPER_ADMIN), `get_safety_manager`,
  `get_responsible_manager`, `get_accountable_executive`.

### Roles

| Role | Scope | Notes |
|---|---|---|
| `SUPER_ADMIN` | System-wide | CAAN top-level director; admin endpoints |
| `CAAN_SMD` | Cross-tenant (read + risk confirm) | Regulator / SSP inspectorate |
| `AIRLINE_ADMIN` | Own tenant | Safety manager functions, risk matrix config |
| `USER` | Own tenant (submit/report) | Basic reporter; cannot override assessments |

## 6. Data Model (Firestore)

All tenant data is isolated under `/tenants/{tenant_id}/`:

| Collection | Purpose | Write access |
|---|---|---|
| `metadata/{doc}` | Tenant info, survey config, risk matrix config | SUPER_ADMIN |
| `responses/{id}` | Survey responses | Public create; immutable |
| `reports/{id}` | VSR **and** MOR reports | Public/authenticated create; tenant update |
| `hazards/{id}` | Hazard register | Tenant create/update |
| `can_cap/{id}` | CAN / CAP records | Tenant create/update |
| `verification/{doc}` | Hazard verifications & closures | Tenant create/update |
| `flight_diversions/{doc}` | Diversion records | Tenant create/update |

Root collections: `analytics/{doc}`, `public_responses/{doc}`, `users/{uid}`.

> **Note:** `reports/` holds both VSR and MOR (discriminated by `report_type`). A legacy
> `tenants/{t}/mor/` path is still matched by security rules but is not written by the current
> backend.

### Risk matrix

The ICAO 5×5 matrix is computed (`risk_index = severity × probability`, 1–25), classified with
tenant-configurable thresholds (default `low_max=5, medium_max=9, high_max=15`), and stored per
tenant in `tenants/{t}/metadata/risk_matrix`. Since RC-2 the stored thresholds are honored by all
scoring (reports, hazards, AI-suggested assessment, risk outcome). See
`backend/app/services/risk_matrix.py`.

## 7. Frontend Structure

- `public/js/firebase.js` — Firebase init, App Check activation, auth helpers.
- `public/js/api/client.js` — `ApiClient` singleton; auto-injects ID token; 401 → login redirect.
- Per-module JS: `vsr.js`, `mor.js`, `reports.js`, `report.js`, `hazards.js`, `can_cap.js`,
  `verification.js`, `flight_diversions.js`, `dashboard.js`, `dashboard-utils.js`, `tenant.js`.
- Static pages under `public/` with an SPA rewrite to `index.html`; aggressive asset caching.

## 8. Design Patterns

- **Multi-tenancy:** tenant-scoped Firestore paths + custom-claim RBAC (API and rules).
- **Repository pattern:** caching (60s TTL) and cursor pagination for dashboard queries.
- **Background AI:** report submission enqueues `run_ai_analysis` via FastAPI `BackgroundTasks`.
- **Fail-closed secrets:** admin endpoints return 503 until `SETUP_SECRET` is configured; seed and
  provisioning scripts fail fast when required env vars are absent.
- **Dual API prefixes:** `/api/v1` canonical; `/api` legacy aliases (hidden from OpenAPI).

## 9. Design Decisions (from the Product Charter)

- Only three data sources (Survey, VSR, MOR).
- Survey measures SMS capability; VSR reveals operational hazards; MOR captures reportable
  occurrences.
- AI suggests; the organization (Safety Manager) confirms official assessments.
- No investigation management, no standalone CAPA system, no OEI integration.
