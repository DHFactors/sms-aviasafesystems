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

### Pending batches

- Batch 2 — `demo-contract.html`, `portal/index.html`,
  `dashboard/shared/shell.html`.
- Batch 3 — `admin/dashboard.html`, `dashboard/safety-dashboard.html`,
  `dashboard/dept-head-dashboard.html` (requires doc and test updates
  in the same commit).
- Batch 4 (separate queue item) — `aviasdcps.html` and `views/*`.
