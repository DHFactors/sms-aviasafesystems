# Move Manifest — Safely Segregated Files

**Branch:** `audit/checkpoint-2026-08-24`  
**Archive root:** `_archive/unrelated/` (preserves original directory structure)  
**Policy:** Only **G — High confidence** files are moved via `git mv`. All **H** files stay. No deletions.

| # | Original path | Proposed archive path | Reason | Confidence | Rollback command |
|---|---|---|---|---|---|
| 1 | `firebase-debug.log` | `_archive/unrelated/firebase-debug.log` | Generated debug log from `firebase-tools` (`firebase serve --only hosting`); 59 lines, contains ephemeral tokens, not tracked (`git ls-files` untracked), not imported (`git grep` 0 hits), not in Docker context (`backend/Dockerfile` context is `backend/`), recreated on next `firebase serve`. Listed as temporary. | **High** | `git mv _archive/unrelated/firebase-debug.log firebase-debug.log` |
| 2 | `backend/requirements_bak.txt` | `_archive/unrelated/backend/requirements_bak.txt` | Backup duplicate of `backend/requirements.txt` (55 vs 57 lines; `==` pins vs live `>=`); `Dockerfile:6` `COPY requirements.txt` and `render.yaml:5` `pip install -r backend/requirements.txt` only use live file; `git grep requirements_bak` 0 hits; untracked, not referenced by `docker-compose.yml` or `package.json`. `COPY . .` would otherwise bloat image. | **High** | `git mv _archive/unrelated/backend/requirements_bak.txt backend/requirements_bak.txt` |
| 3 | `.github/workflows/deploy.yml.disabled` | `_archive/unrelated/.github/workflows/deploy.yml.disabled` | Disabled GitHub Action (`.disabled` extension ignored by Actions loader which only loads `*.yml`); original `deploy.yml` was tracked then renamed; no reference in `render.yaml`, `firebase.json`, or `Dockerfile`; `git grep deploy.yml.disabled` 0 hits; `git ls-files` shows untracked. Safe to archive, original workflow not used (Render hosts API, Firebase Hosting hosts static). | **High** | `git mv _archive/unrelated/.github/workflows/deploy.yml.disabled .github/workflows/deploy.yml.disabled` |

**Total to move:** 3 files.  
**Total retained:** 473 files (including 28 root one-off scripts now classified **H** and left in place).

## Safety Notes

- **No env/secrets moved:** `backend/.env`, `backend/.env.demo`, `*.env`, `*-sa.json`, `beta-testing-credentials.csv` are ignored and remain.
- **No app code/config moved:** `backend/app/**`, `public/**`, `firebase.json`, `firestore.rules`, `render.yaml`, `docker-compose.yml`, tests, seed, docs stay.
- **Root patch scripts (`add_*.py`, `fix_*.py`, `convert_*.py`, `replace_*.py`, `find_*.py`, `count_*.py`, `quick_check.py`, `verify_fix.py`, `check_*.py`, `apply_guards.py`, `fix_modal.js`, `login_orig.html`, `safety_orig.html`, `aviasafe_sms_hybrid_landing_page.html`) are **H** — zero refs but uncertain manual utility, so **not moved**.
- Uses `git mv` to preserve history and allow `git diff` review before commit.
- Archive preserves directory structure (`backend/` etc. nested).

## Commands to Execute (after audit approval)

```bash
git checkout audit/checkpoint-2026-08-24
mkdir -p _archive/unrelated/.github/workflows _archive/unrelated/backend
git mv firebase-debug.log _archive/unrelated/firebase-debug.log
git mv backend/requirements_bak.txt _archive/unrelated/backend/requirements_bak.txt
git mv .github/workflows/deploy.yml.disabled _archive/unrelated/.github/workflows/deploy.yml.disabled
git status
git diff --cached --stat
# Validate (Step 7) — run before commit:
#   pytest, npm build, docker build, compose up, health check
```

## Rollback (per file or all)

```bash
# Single file
git mv _archive/unrelated/firebase-debug.log firebase-debug.log
git mv _archive/unrelated/backend/requirements_bak.txt backend/requirements_bak.txt
git mv _archive/unrelated/.github/workflows/deploy.yml.disabled .github/workflows/deploy.yml.disabled

# All at once (from branch root)
git mv _archive/unrelated/firebase-debug.log ./ && git mv _archive/unrelated/backend/requirements_bak.txt backend/ && git mv _archive/unrelated/.github/workflows/deploy.yml.disabled .github/workflows/
# Or restore entire checkpoint branch:
git reset --hard audit/checkpoint-2026-08-24
# Or if already committed, revert:
git log --oneline -3   # find commit hash
git revert <commit-hash>
```

## Validation Gate

Do not commit until Step 7 passes: backend tests, frontend build, `docker build backend`, `docker compose config`, `curl http://localhost:8000/live` health check. If any fail, restore affected file immediately and update `file-classification.md` to H.

No deletions — all moves are reversible via `git mv`.
