# AviaSAFE SMS Platform

A multi-tenant aviation **Safety Management System (SMS) intelligence platform** for Nepal,
aligned with **ICAO Annex 19**, **ICAO Doc 9859**, and **CAAN CAR-19**.

> **Status:** Released as production **v1.0.0**. See
> [docs/archive/PROJECT_STATUS_REPORT_05AUG2026.md](./docs/archive/PROJECT_STATUS_REPORT_05AUG2026.md) for the
> release record and [docs/archive/PROJECT_CHARTER.md](./docs/archive/PROJECT_CHARTER.md) for the product charter.

---

## Overview

The platform collects three core data sources and answers two questions per audience:

| Data source | Measures | Framework |
|---|---|---|
| **Safety Culture Survey** | SMS capability (4 components / 12 elements) | ICAO Annex 19, Doc 9859, CAR-19 |
| **Voluntary Safety Reporting (VSR)** | Operational hazards, before they become accidents | ICAO ADREP / ICAO taxonomy |
| **Mandatory Occurrence Reporting (MOR)** | Reportable occurrences | ICAO taxonomy |

| Audience | Question |
|---|---|
| **Airlines (Service Providers)** | *How mature is our SMS? What are our highest operational risks?* |
| **CAAN (State)** | *How mature is each operator's SMS? What are the highest operational risks across the industry? How effective is the SSP over time?* |

Supporting modules extend the core flows: Hazard Register, Corrective Action Notices & Plans
(CAN/CAP), Verification & Closure, Flight Diversions, Quarterly/Annual Reports with PDF export, and
an AI assistant (Gemini) that *suggests* severity/probability — never authoritatively overrides the
Safety Manager.

Per the [Product Charter](./docs/archive/PROJECT_CHARTER.md): this is **not** an investigation management
system, CAPA system, QMS, ERP, OEI, or enterprise risk platform. No feature expansion without
approval.

---

## Technology Stack

| Layer | Technology | Notes |
|---|---|---|
| Frontend | HTML5 / CSS3 / Vanilla JS (Firebase Web SDK v9 compat) | No build step; served by Firebase Hosting |
| Backend | Python 3.11, FastAPI, Uvicorn | `backend/` |
| Database | Cloud Firestore (`sms-db`, us-west1) | Firebase project `aerosafety-sms-prod` |
| Auth | Firebase Authentication (email/password) + ID-token JWT (RS256) | Custom claims for RBAC |
| App Check | Firebase App Check with reCAPTCHA v3 | Client-side enforcement |
| AI | Google Gemini (`gemini-2.0-pro-exp-02-05`) | Optional; mock fallback built in |
| Rate limiting | Upstash Redis + in-memory fallback | Per-IP + per-endpoint |
| Hosting (current) | Firebase Hosting (frontend), Render (backend) | Prototype |
| Hosting (target) | Firebase Hosting (Blaze) + Google Cloud Run | Commercial |

Live endpoints:

- Frontend: `https://sms.aviasafesystems.com` (custom domain) / `https://aerosafety-sms-prod.web.app`
- Backend API: `https://aviasafe-unified-platform.onrender.com`
- OpenAPI docs: `https://aviasafe-unified-platform.onrender.com/docs`

---

## Repository Structure

```
├── backend/                  # FastAPI service
│   ├── app/
│   │   ├── core/             # config (env settings), metrics
│   │   ├── middleware/       # auth guards, rate limiting, security headers
│   │   ├── models/           # Pydantic request/response models
│   │   ├── routes/           # API routers (auth, reports, hazards, cans, dashboard, admin, …)
│   │   ├── services/         # business logic (report, hazard, can_cap, metrics, gemini, …)
│   │   └── firebase.py       # Firebase Admin SDK wiring + token verification
│   ├── seed/                 # deterministic, idempotent seed data pipeline
│   ├── tests/                # pytest unit/integration suite
│   ├── Dockerfile
│   ├── cloudrun.yaml         # target Cloud Run deployment
│   ├── render.yaml           # Render Blueprint (Docker)
│   └── requirements.txt
├── public/                   # Firebase Hosting static site
│   ├── *.html                # landing, login, dashboards, forms
│   ├── js/                   # firebase init, ApiClient, per-module logic
│   ├── docs/tenant-guide/    # tenant onboarding docs (docs-as-code)
│   └── portal/               # tenant portal pages (real Firebase auth)
├── firestore/                # Firestore security rules
├── firestore.indexes.json    # deployed composite indexes (camelCase)
├── scripts/                  # provisioning + Firebase admin scripts
├── tests/e2e/                # E2E scripts against the live API
├── docs/                     # project documentation (see index below)
├── firebase.json             # Firebase CLI / Hosting config
└── render.yaml               # Render Blueprint (bare python)
```

> **Deployment note:** there are two Render configs — root `render.yaml` (bare python) and
> `backend/render.yaml` (Docker). RC-3 documents both; reconciling to a single authoritative
> manifest is tracked in `docs/KNOWN_LIMITATIONS.md` (TD-8).

---

## Documentation Index

| Area | Document |
|---|---|
| Project overview / architecture | [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) |
| Installation & local development | [docs/INSTALLATION.md](./docs/INSTALLATION.md) |
| Deployment guide | [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) |
| Operations manual | [docs/OPERATIONS.md](./docs/OPERATIONS.md) |
| Administrator guide | [docs/ADMIN_GUIDE.md](./docs/ADMIN_GUIDE.md) |
| User glossary & dashboard reference | [docs/GLOSSARY.md](./docs/GLOSSARY.md) |
| API reference | [docs/API.md](./docs/API.md) |
| Security | [docs/SECURITY.md](./docs/SECURITY.md) |
| Testing | [tests/README.md](./tests/README.md) |
| Known limitations / tech debt | [docs/KNOWN_LIMITATIONS.md](./docs/KNOWN_LIMITATIONS.md) |
| Product charter | [docs/archive/PROJECT_CHARTER.md](./docs/archive/PROJECT_CHARTER.md) |
| Status & roadmap | [docs/archive/PROJECT_STATUS_REPORT_05AUG2026.md](./docs/archive/PROJECT_STATUS_REPORT_05AUG2026.md), [docs/PROJECT_STATUS_REPORT_2026-08-24.md](./docs/PROJECT_STATUS_REPORT_2026-08-24.md), [ROADMAP.md](./ROADMAP.md) |
| Demo walkthrough | [docs/archive/DEMO_GUIDE.md](./docs/archive/DEMO_GUIDE.md) |
| File structure & routing | [docs/FILE_STRUCTURE.md](./docs/FILE_STRUCTURE.md) |
| Tenant onboarding | [public/docs/tenant-guide/](./public/docs/tenant-guide/) |
| UAT evidence | [UAT_DEFECT_REGISTER.md](./UAT_DEFECT_REGISTER.md) |

---

## Quick Start

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # then fill in Firebase credentials
uvicorn app.main:app --reload --port 8000

# 2. Tests
python -m pytest tests/ -q

# 3. Frontend (static)
firebase serve --only hosting
```

See [docs/INSTALLATION.md](./docs/INSTALLATION.md) for prerequisites, environment variables,
Firebase setup, and local emulation.

---

## Contributing & Governance

- No architectural or functional expansion without explicit approval (see
  [docs/archive/PROJECT_CHARTER.md](./docs/archive/PROJECT_CHARTER.md) Governance Rule).
- All changes must keep `python -m pytest tests/ -q` green.
- Do not commit secrets. All credentials and API keys are environment-driven.

---

*AviaSAFE Systems — a project by Ghanshyam Acharya*
