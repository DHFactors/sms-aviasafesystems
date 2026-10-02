# _hold/ — parked files pending confirmation

Files in this folder are not part of any live page chain: they are not
reachable from the four dashboard hubs (`safety.html`,
`dashboard/ae-dashboard.html`, `caan.html`, `dashboard/my-tasks.html`),
from the admin surface (`admin/login.html` → `admin/production-setup.html`),
or from any live nav. They are retained here — not deleted — until the
whole chain has been verified end-to-end. Once every system of the chain
is confirmed, this folder can be deleted.

This folder is git-ignored, with one exception: this README is tracked
so the folder's purpose is documented in `git log`. The parked HTML
files inside it are ignored and do not appear in `git status`. They
remain in the working tree at their original relative paths.

## Restoring a file

From the repo root:

```
mv public/_hold/<original-relative-path> public/<original-relative-path>
```

The original relative path is listed below for each entry.

## Inventory

### Batch 1 — moved 2026-10-01

Each entry lists the file's original path in `public/`, the batch it was
moved in, and the reason it was parked.

- `hazards/index.html` — Batch 1 — reachable only from
  `public/admin/dashboard.html`, itself a Batch 3 candidate. No live
  inbound. Superseded by `hazard-analysis.html` per the live nav.
- `hazards/create.html` — Batch 1 — reachable only from
  `public/admin/dashboard.html`, itself a Batch 3 candidate. No live
  inbound. Referenced in `SCHEMA_RECONCILIATION_PLAN.md:265` (advisory
  only, no functional dependency).
- `test-portal.html` — Batch 1 — no inbound. Redirect stub to the
  deprecated `admin/dashboard.html`. Superseded by the
  `admin/login.html` → `admin/production-setup.html` entry path.
- `portal/survey/index.html` — Batch 1 — no inbound. Legacy path
  redirect stub to `/survey/`, which is the live survey path. File's own
  header records the consolidation.

### Batch 2 — moved 2026-10-01

- `demo-contract.html` — Batch 2 — no inbound in `public/**`. Only
  reference is a comment in `backend/app/routes/demo.py:190`; the
  demo acceptance flow writes to a `demo_contract_acceptances` table
  and does not require the page to be reachable.
- `portal/index.html` — Batch 2 — only inbound is
  `public/hazards/index.html:67`, itself a Batch 3 candidate. The
  `portal/` folder is documented in `README.md:81` as a live surface;
  that reference becomes stale once this move lands and is queued for
  a later doc-hygiene pass.
- `dashboard/shared/shell.html` — Batch 2 — only inbound is a comment
  in `public/dashboard/safety-dashboard.html:87`, itself a Batch 3
  candidate. The sibling files `shell.js`, `module-flag.js`, and
  `shell.css` in the same folder remain in place.

### Batch 3 — moved 2026-10-02

- `admin/dashboard.html` — Batch 3 — <title> already marked
  [DEPRECATED → Production Setup]; meta-refresh at :20 and
  firebase.json:20-22 both redirect /admin/dashboard.html to
  /admin/production-setup.html. The redirect is URL-pattern-based, so
  it survives the file move.
- `dashboard/safety-dashboard.html` — Batch 3 — Wave 2 / P4-2
  contract-defined page, superseded by /safety.html. No live inbound.
- `dashboard/dept-head-dashboard.html` — Batch 3 — Wave 3 / P4-3
  contract-defined page, superseded by /dashboard/my-tasks.html. No
  live inbound. Live router (firebase.js:671) already routes DEPT_ADMIN
  to my-tasks.html.
- `frontend-tests/test_dept_head_dashboard.js` — Batch 3 — reads
  dept-head-dashboard.html from disk; parked alongside the page it
  tests. Not in CI (package.json:14 does not reference it).
- `frontend-tests/test_safety_dashboard.js` — Batch 3 — reads
  safety-dashboard.html from disk; parked alongside the page it tests.
  Not in CI (package.json:14 does not reference it).

### Batch 4 — moved 2026-10-02

- `aviasdcps.html` — Batch 4 — the project's origin, the Annex 19
  data-collection shell. Loads `public/js/aviasdcps-router.js`, which
  fetch()es templates from `views/`. Not in any live chain; not
  linked from any SMS-app page. The firebase.json rewrites for
  `/aviasdcps` and `/aviasdcps/**` are URL-pattern-matched and are
  unaffected by the file move; requests to those paths now fall
  through to `/index.html` via the catch-all rewrite.
- `views/*` — Batch 4 — fifteen template files fetched by
  `aviasdcps.html` via `aviasdcps-router.js`. None is reachable as a
  navigated page. The router file `public/js/aviasdcps-router.js` is
  intentionally not moved; it may be loaded by pages outside this
  batch and is left in place.

### Pending batches

(none — Project E is complete)
