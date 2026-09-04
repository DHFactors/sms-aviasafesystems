# Dashboard Rename Plan

> Generated: 2026-09-04

---

## 1. Current Files in `public/dashboard/` (7 files)

| # | Current Filename | Purpose |
|---|---|---|
| 1 | `index.html` | SMS Maturity Dashboard |
| 2 | `ae-dashboard.html` | Accountable Executive Dashboard |
| 3 | `responsible-manager.html` | My Tasks / Responsible Manager |
| 4 | `caan-sms-maturity.html` | CAAN SMS Maturity |
| 5 | `master-register.html` | Master Hazard Register |
| 6 | `nhrc-dashboard.html` | N-HRC KPIs |
| 7 | `spi-dashboard.html` | SPI/SPT Dashboard |

---

## 2. Rename Mapping

| Current Filename | New Filename | Rationale |
|---|---|---|
| `index.html` | `sms-maturity.html` | Descriptive; matches nav label "SMS Maturity" |
| `ae-dashboard.html` | `ae-dashboard.html` | **No change** — already descriptive |
| `responsible-manager.html` | `my-tasks.html` | Matches nav label "My Tasks" |
| `caan-sms-maturity.html` | `caan-sms-maturity.html` | **No change** — already descriptive |
| `master-register.html` | `master-register.html` | **No change** — already descriptive |
| `nhrc-dashboard.html` | `nhrc-kpis.html` | Matches nav label "N-HRC KPIs" |
| `spi-dashboard.html` | `spi-dashboard.html` | **No change** — already descriptive |

**Summary:** 3 files to rename, 4 files unchanged.

---

## 3. Files Requiring Link Updates

### 3a. `/dashboard/index.html` → `/dashboard/sms-maturity.html` (11 references)

| File | Line | Context |
|---|---|---|
| `public/administration.html` | 194 | `{ href: '/dashboard/index.html', label: 'SMS Maturity', ... }` |
| `public/audits/psoe.html` | 261 | `{ href: '/dashboard/index.html', label: 'SMS Maturity', ... }` |
| `public/dashboard/spi-dashboard.html` | 70 | `{ href: '/dashboard/index.html', label: 'SMS Maturity', ... }` |
| `public/dashboard/nhrc-dashboard.html` | 96 | `{ href: '/dashboard/index.html', label: 'SMS Maturity', ... }` |
| `public/dashboard/master-register.html` | 85 | `<a href="/dashboard/index.html" ...>Back to Dashboard</a>` |
| `public/admin/dashboard.html` | 221 | `{ title: "SMS Maturity Dashboard", path: "/dashboard/index.html", ... }` |
| `public/top-hazards.html` | 103 | `{ href: '/dashboard/index.html', label: 'SMS Maturity', ... }` |
| `public/safety.html` | 448 | `{ href: '/dashboard/index.html', label: 'SMS Maturity', ... }` |
| `public/risk-trends.html` | 107 | `{ href: '/dashboard/index.html', label: 'SMS Maturity', ... }` |
| `public/settings/team.html` | 154 | `{ href: '/dashboard/index.html', label: 'SMS Maturity', ... }` |
| `public/js/rbac.js` | 13 | `'module3': { ... href: '/dashboard/index.html' }` |

### 3b. `/dashboard/responsible-manager.html` → `/dashboard/my-tasks.html` (13 references)

| File | Line | Context |
|---|---|---|
| `public/admin/dashboard.html` | 225 | `{ title: "My Tasks", path: "/dashboard/responsible-manager.html", ... }` |
| `public/can_cap/cans.html` | 74 | `<a href="/dashboard/responsible-manager.html" ...>My Tasks</a>` |
| `public/can_cap/caps.html` | 75 | `<a href="/dashboard/responsible-manager.html" ...>My Tasks</a>` |
| `public/dashboard/master-register.html` | 86 | `<a href="/dashboard/responsible-manager.html" ...>My Tasks</a>` |
| `public/js/firebase.js` | 636 | `return '/dashboard/ae-dashboard.html'` *(related routing)* |
| `public/js/firebase.js` | 642 | `if (role === 'DEPT_ADMIN') return '/dashboard/responsible-manager.html'` |
| `public/js/firebase.js` | 646 | `if (department) return '/dashboard/responsible-manager.html'` |
| `public/js/firebase.js` | 770 | `var correctDest = '/dashboard/responsible-manager.html'` |
| `backend/tests/test_rbac_claims.py` | 110 | `return "/dashboard/responsible-manager.html"` |
| `backend/tests/test_rbac_claims.py` | 132 | `== "/dashboard/responsible-manager.html"` |
| `frontend-tests/chunk8_matrix.js` | 52 | `'/dashboard/responsible-manager.html'` |
| `frontend-tests/chunk13_login_routing_verify.js` | 40 | *(ae-dashboard assertion, not this file)* |
| `tests/e2e/phase1_multitenant_verification.py` | 17 | Comment: `/dashboard/responsible-manager.html` |
| `status.md` | 13 | Documentation reference |
| `docs/PROJECT_STATUS_REPORT.md` | 107 | Documentation reference |

### 3c. `/dashboard/nhrc-dashboard.html` → `/dashboard/nhrc-kpis.html` (11 references)

| File | Line | Context |
|---|---|---|
| `public/audits/psoe.html` | 264 | `{ href: '/dashboard/nhrc-dashboard.html', label: 'N-HRC KPIs', ... }` |
| `public/administration.html` | 197 | `{ href: '/dashboard/nhrc-dashboard.html', label: 'N-HRC KPIs', ... }` |
| `public/top-hazards.html` | 106 | `{ href: '/dashboard/nhrc-dashboard.html', label: 'N-HRC KPIs', ... }` |
| `public/dashboard/spi-dashboard.html` | 73 | `{ href: '/dashboard/nhrc-dashboard.html', label: 'N-HRC KPIs', ... }` |
| `public/dashboard/nhrc-dashboard.html` | 1, 99 | Self-reference (comment + nav) |
| `public/risk-trends.html` | 110 | `{ href: '/dashboard/nhrc-dashboard.html', label: 'N-HRC KPIs', ... }` |
| `public/safety.html` | 451 | `{ href: '/dashboard/nhrc-dashboard.html', label: 'N-HRC KPIs', ... }` |
| `public/settings/team.html` | 157 | `{ href: '/dashboard/nhrc-dashboard.html', label: 'N-HRC KPIs', ... }` |
| `public/admin/dashboard.html` | 234 | *(Note: no match found in admin dashboard — verify manually)* |
| `docs/PROJECT_STATUS_REPORT.md` | 33, 175 | Documentation references |
| `status.md` | *(not directly referenced for this file)* | — |

### 3d. `/dashboard/ae-dashboard.html` — **No change needed** (13 references exist but filename stays)

| File | Line | Context |
|---|---|---|
| `public/admin/dashboard.html` | 222 | `{ title: "Accountable Executive Dashboard", path: "/dashboard/ae-dashboard.html", ... }` |
| `public/js/firebase.js` | 636 | `return '/dashboard/ae-dashboard.html'` |
| `frontend-tests/ae_personalization_smoke.js` | 6, 36 | Test assertions |
| `frontend-tests/chunk8_matrix.js` | 32–35 | Test matrix entries |
| `frontend-tests/chunk13_login_routing_verify.js` | 40 | Test assertion |
| `status.md` | 13, 19, 40 | Documentation |
| `docs/archive/PROSPECT_DEMO_GUIDE.md` | 29 | Documentation |

### 3e. `/dashboard/caan-sms-maturity.html` — **No change needed** (4 references, filename stays)

| File | Line | Context |
|---|---|---|
| `public/admin/dashboard.html` | 234 | `{ title: "CAAN SMS Maturity", path: "/dashboard/caan-sms-maturity.html", ... }` |
| `public/caan.html` | 13, 219 | Comment + nav link |
| `public/dashboard/caan-sms-maturity.html` | 3 | Self-reference comment |

### 3f. `/dashboard/master-register.html` — **No change needed** (10 references, filename stays)

| File | Line | Context |
|---|---|---|
| `public/can_cap/caps.html` | 74 | `<a href="/dashboard/master-register.html" ...>Master Hazard Register</a>` |
| `public/can_cap/cans.html` | 73 | `<a href="/dashboard/master-register.html" ...>Master Hazard Register</a>` |
| `public/admin/dashboard.html` | 226 | `{ title: "Master Register", path: "/dashboard/master-register.html", ... }` |
| `public/top-hazards.html` | 82 | `<a href="/dashboard/master-register.html" ...>Master Hazard Register</a>` |
| `public/dashboard/responsible-manager.html` | 89 | `<a href="/dashboard/master-register.html" ...>Master Register</a>` |
| `public/portal/index.html` | 182, 212 | Nav + CTA button |
| `public/hazards/create.html` | 48 | `<a href="/dashboard/master-register.html" ...>Back to Master Hazard Register</a>` |
| `public/hazards/detail.html` | 79 | `<a href="/dashboard/master-register.html" ...>Back to Master Hazard Register</a>` |
| `todos.md` | 13 | Documentation |

### 3g. `/dashboard/spi-dashboard.html` — **No change needed** (11 references, filename stays)

| File | Line | Context |
|---|---|---|
| `public/audits/psoe.html` | 265 | `{ href: '/dashboard/spi-dashboard.html', label: 'SPI/SPT', ... }` |
| `public/administration.html` | 198 | `{ href: '/dashboard/spi-dashboard.html', label: 'SPI/SPT', ... }` |
| `public/dashboard/spi-dashboard.html` | 1, 74 | Self-reference (comment + nav) |
| `public/settings/team.html` | 158 | `{ href: '/dashboard/spi-dashboard.html', label: 'SPI/SPT', ... }` |
| `public/dashboard/nhrc-dashboard.html` | 100 | `{ href: '/dashboard/spi-dashboard.html', label: 'SPI/SPT', ... }` |
| `public/top-hazards.html` | 107 | `{ href: '/dashboard/spi-dashboard.html', label: 'SPI/SPT', ... }` |
| `public/safety.html` | 452 | `{ href: '/dashboard/spi-dashboard.html', label: 'SPI/SPT', ... }` |
| `public/risk-trends.html` | 111 | `{ href: '/dashboard/spi-dashboard.html', label: 'SPI/SPT', ... }` |
| `docs/PROJECT_STATUS_REPORT.md` | 32, 174 | Documentation |

---

## 4. Verification Checklist

### Pre-Rename
- [ ] Back up all 7 dashboard files
- [ ] Confirm no service worker or cache manifests reference these files
- [ ] Confirm Firebase hosting rewrites (if any) don't hardcode these paths
- [ ] Run `git status` to confirm clean working tree

### File Renames (3 operations)
- [ ] `git mv public/dashboard/index.html public/dashboard/sms-maturity.html`
- [ ] `git mv public/dashboard/responsible-manager.html public/dashboard/my-tasks.html`
- [ ] `git mv public/dashboard/nhrc-dashboard.html public/dashboard/nhrc-kpis.html`

### Link Updates — `sms-maturity.html` (11 files)
- [ ] `public/administration.html:194`
- [ ] `public/audits/psoe.html:261`
- [ ] `public/dashboard/spi-dashboard.html:70`
- [ ] `public/dashboard/nhrc-dashboard.html:96` → will be `nhrc-kpis.html:96`
- [ ] `public/dashboard/master-register.html:85`
- [ ] `public/admin/dashboard.html:221`
- [ ] `public/top-hazards.html:103`
- [ ] `public/safety.html:448`
- [ ] `public/risk-trends.html:107`
- [ ] `public/settings/team.html:154`
- [ ] `public/js/rbac.js:13`

### Link Updates — `my-tasks.html` (10 files)
- [ ] `public/admin/dashboard.html:225`
- [ ] `public/can_cap/cans.html:74`
- [ ] `public/can_cap/caps.html:75`
- [ ] `public/dashboard/master-register.html:86`
- [ ] `public/js/firebase.js:642`
- [ ] `public/js/firebase.js:646`
- [ ] `public/js/firebase.js:770`
- [ ] `backend/tests/test_rbac_claims.py:110`
- [ ] `backend/tests/test_rbac_claims.py:132`
- [ ] `frontend-tests/chunk8_matrix.js:52`

### Link Updates — `nhrc-kpis.html` (9 files)
- [ ] `public/audits/psoe.html:264`
- [ ] `public/administration.html:197`
- [ ] `public/top-hazards.html:106`
- [ ] `public/dashboard/spi-dashboard.html:73`
- [ ] `public/dashboard/nhrc-dashboard.html:99` → self-ref in renamed file
- [ ] `public/risk-trends.html:110`
- [ ] `public/safety.html:451`
- [ ] `public/settings/team.html:157`

### Documentation Updates (optional but recommended)
- [ ] `status.md:13`
- [ ] `docs/PROJECT_STATUS_REPORT.md:32,33,107,174,175`
- [ ] `docs/archive/PROSPECT_DEMO_GUIDE.md:29`
- [ ] `frontend-tests/ae_personalization_smoke.js:6,36`
- [ ] `frontend-tests/chunk8_matrix.js:32-35`
- [ ] `frontend-tests/chunk13_login_routing_verify.js:40`
- [ ] `tests/e2e/phase1_multitenant_verification.py:17`
- [ ] `todos.md:13`

### Post-Rename Verification
- [ ] `grep -r "/dashboard/index.html" public/` → 0 results
- [ ] `grep -r "/dashboard/responsible-manager.html" public/` → 0 results
- [ ] `grep -r "/dashboard/nhrc-dashboard.html" public/` → 0 results
- [ ] Confirm all 7 dashboard files load in browser
- [ ] Run frontend tests: `npm test` (or equivalent)
- [ ] Run backend tests: `pytest backend/tests/`
- [ ] Verify Firebase deployment (if applicable)

---

## 5. Total Impact Summary

| Metric | Count |
|---|---|
| Files to rename | 3 |
| Files unchanged | 4 |
| Total link updates (public/) | 30 |
| Total link updates (backend/tests/) | 2 |
| Total link updates (frontend-tests/) | 4 |
| Documentation files to update | 6 |
| **Grand total edits** | **~42** |
