# AviaSAFE SMS - File Structure & Routing Reference

## Application Overview

| Metric | Count |
|--------|-------|
| **Total HTML Files** | 35 |
| **Frontend Pages** | 34 |
| **Backend Templates** | 1 (Jinja2) |
| **Routing** | File-based (static hosting) |

---

## Complete File Structure

### Root Pages
```
public/
├── index.html                          # Landing page
├── login.html                          # Tenant login page
├── safety.html                         # Safety Officer dashboard
├── caan.html                           # CAAN regulator dashboard
└── caan-state-risk.html                # CAAN State Risk dashboard
```

### Admin Pages
```
public/admin/
├── index.html                          # Admin panel home
├── login.html                          # Developer login
├── production-setup.html               # Super-Admin seeding panel
└── tenant-credentials.html             # Tenant credentials management
```

### Survey Pages
```
public/survey/
├── index.html                          # Safety Culture Survey (functional, v3.0.0)
├── app.js                              # Survey runtime + POST /api/v1/surveys
├── default_q.js                        # MASTER_QUESTIONS (23 bilingual questions)
└── style.css                           # Survey stylesheet

public/portal/
├── index.html                          # Portal home
└── survey/
    └── index.html                      # Legacy redirect → /survey/ (v3.1.1)
```

### Portal Dashboards
```
public/portal/dashboards/
├── safety.html                         # Safety Officer dashboard (portal)
└── caan.html                           # CAAN dashboard (portal)
```

### Hazard Management
```
public/hazards/
├── index.html                          # Hazard Register (list)
├── create.html                         # Create hazard
├── detail.html                         # Hazard detail view
├── verify.html                         # Verify hazard
└── approve_closure.html                # Approve hazard closure
```

### Flight Diversions
```
public/flight_diversions/
├── index.html                          # Flight Diversions list
├── create.html                         # Create diversion
└── detail.html                         # Diversion detail view
```

### CAN/CAP Management
```
public/can_cap/
├── cans.html                           # CAN Register
├── caps.html                           # CAP Register
├── can_detail.html                     # CAN detail view
├── cap_submit.html                     # Submit CAP
└── cap_review.html                     # Review CAP
```

### Report Management
```
public/report/
├── vsr.html                            # Voluntary Safety Report form
├── mor.html                            # Mandatory Occurrence Report form
└── detail.html                         # Report detail view

public/reports/
├── index.html                          # Reports list
├── generate.html                       # Generate report
└── view.html                           # View report
```

### Dashboard
```
public/dashboard/
└── index.html                          # Main dashboard (Airline)
```

### Backend Templates
```
backend/app/templates/
└── welcome_email.html                  # Jinja2 template for welcome email
```

---

## Routing Map (File-Based)

| URL Path | File Served | Purpose |
|----------|-------------|---------|
| `/` | `index.html` | Landing page |
| `/login.html` | `login.html` | Tenant login |
| `/safety.html` | `safety.html` | Safety Officer dashboard |
| `/caan.html` | `caan.html` | CAAN dashboard |
| `/caan-state-risk.html` | `caan-state-risk.html` | State Risk dashboard |
| `/admin/` | `admin/index.html` | Admin panel home |
| `/admin/login.html` | `admin/login.html` | Developer login |
| `/admin/production-setup.html` | `admin/production-setup.html` | Seeding panel |
| `/admin/tenant-credentials.html` | `admin/tenant-credentials.html` | Tenant credentials |
| `/survey/` | `survey/index.html` | Safety Culture Survey (functional, POST `/api/v1/surveys`) |
| `/portal/` | `portal/index.html` | Portal home |
| `/portal/survey/` | `portal/survey/index.html` | Redirect → `/survey/` |
| `/portal/dashboards/safety.html` | `portal/dashboards/safety.html` | Portal safety dashboard |
| `/portal/dashboards/caan.html` | `portal/dashboards/caan.html` | Portal CAAN dashboard |
| `/hazards/` | `hazards/index.html` | Hazard Register |
| `/hazards/create.html` | `hazards/create.html` | Create hazard |
| `/hazards/detail.html` | `hazards/detail.html` | Hazard detail |
| `/hazards/verify.html` | `hazards/verify.html` | Verify hazard |
| `/hazards/approve_closure.html` | `hazards/approve_closure.html` | Approve closure |
| `/flight_diversions/` | `flight_diversions/index.html` | Diversions list |
| `/flight_diversions/create.html` | `flight_diversions/create.html` | Create diversion |
| `/flight_diversions/detail.html` | `flight_diversions/detail.html` | Diversion detail |
| `/can_cap/cans.html` | `can_cap/cans.html` | CAN Register |
| `/can_cap/caps.html` | `can_cap/caps.html` | CAP Register |
| `/can_cap/can_detail.html` | `can_cap/can_detail.html` | CAN detail |
| `/can_cap/cap_submit.html` | `can_cap/cap_submit.html` | Submit CAP |
| `/can_cap/cap_review.html` | `can_cap/cap_review.html` | Review CAP |
| `/report/vsr.html` | `report/vsr.html` | VSR form |
| `/report/mor.html` | `report/mor.html` | MOR form |
| `/report/detail.html` | `report/detail.html` | Report detail |
| `/reports/` | `reports/index.html` | Reports list |
| `/reports/generate.html` | `reports/generate.html` | Generate report |
| `/reports/view.html` | `reports/view.html` | View report |
| `/dashboard/` | `dashboard/index.html` | Airline dashboard |

---

## Firebase Hosting Rewrite Rule

```json
// firebase.json
{
  "hosting": {
    "rewrites": [
      {
        "source": "**",
        "destination": "/index.html"
      }
    ]
  }
}
```

**Behavior**: Any unknown path falls back to `/index.html` (SPA routing).

---

## Page Categories

| Category | Count | Files |
|----------|-------|-------|
| **Root Pages** | 5 | index, login, safety, caan, caan-state-risk |
| **Admin Pages** | 4 | index, login, production-setup, tenant-credentials |
| **Survey Pages** | 2 | survey/index, portal/index, portal/survey/index (redirect) |
| **Portal Dashboards** | 2 | portal/dashboards/safety, portal/dashboards/caan |
| **Hazards** | 5 | index, create, detail, verify, approve_closure |
| **Flight Diversions** | 3 | index, create, detail |
| **CAN/CAP** | 5 | cans, caps, can_detail, cap_submit, cap_review |
| **Reports** | 6 | vsr, mor, detail, reports/index, generate, view |
| **Dashboard** | 1 | dashboard/index |

---

## Authentication-Protected Routes

| Category | Pages |
|----------|-------|
| **Requires Auth** | All except `/`, `/login.html`, `/admin/login.html` |
| **Requires AIRLINE_ADMIN** | `/safety.html`, `/hazards/*`, `/can_cap/*`, `/report/*`, `/reports/*`, `/dashboard/` |
| **Requires CAAN_SMD** | `/caan.html`, `/caan-state-risk.html` |
| **Requires SUPER_ADMIN** | `/admin/*` |

---

## Developer Notes

| Item | Note |
|------|------|
| **Routing** | File-based; no client-side routing library |
| **Fallback** | All unknown paths → `/index.html` |
| **Auth Pages** | Login pages are public; all others require auth |
| **Admin Pages** | All require SUPER_ADMIN role |
| **Portal** | Separate portal structure for tenant-specific views |

---

*Last Updated: August 2026*
