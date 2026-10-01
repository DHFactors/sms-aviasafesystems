# _hold/ — parked files pending confirmation

Files in this folder are not part of any live page chain: they are not
reachable from the four dashboard hubs (`safety.html`,
`dashboard/ae-dashboard.html`, `caan.html`, `dashboard/my-tasks.html`),
from the admin surface (`admin/login.html` → `admin/production-setup.html`),
or from any live nav. They are retained here — not deleted — until the
whole chain has been verified end-to-end. Once every system of the chain
is confirmed, this folder can be deleted.

This folder is git-ignored. It does not appear in `git status` and is not
tracked. The files inside it remain in the working tree at their
original relative paths.

## Restoring a file

From the repo root:

```
mv public/_hold/<original-relative-path> public/<original-relative-path>
```

The original relative path is listed below for each entry.

## Inventory

(empty — populated as files are moved here in subsequent commits)
