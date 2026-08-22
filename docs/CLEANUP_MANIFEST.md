# Cleanup Manifest — Chunk 17 (2026-08-22)

Safe project cleanup performed before release. Core seed templates, test
suites, and the prospect dictionary (`public/js/demo-prospects.js`,
`backend/seed/prospect_registry.py`) were explicitly excluded from cleanup.

## Deleted Files

| File | Reason |
|---|---|
| `session-ses_fefc.md` (repo root) | Orphaned AI-session scratch log; obsolete |
| `backend/_chunk8_verify.py` | Session scratch verifier (checks now live in `scripts/validate_seasonal_seed.py`) |
| `backend/_dbg_tenants.py` | Temporary debug script (timezone flake investigation) |
| `backend/_verify_distribution.py` | Temporary post-seed distribution check (superseded by `validate_seasonal_seed.py`) |

Earlier in-session scratch files were removed at creation time and never
tracked: `_patch_credentials.py`, `_patch_fishbone_help.py`,
`_patch_ae_ctx.py`, `_dbg2.py`–`_dbg4.py`, `_plan_preview.py`, `_rescope.py`,
`frontend-tests/_chunk4_smoke.js`, `frontend-tests/_chunk5_smoke.js`,
`frontend-tests/_chunk8_matrix.js`.

## Retained (Reviewed, Not Orphaned)

| Path | Reason to keep |
|---|---|
| `frontend-tests/chunk10_survey_contract.mjs` | Permanent 31-question contract regression test |
| `frontend-tests/chunk12_registry_verify.js` | Prospect registry completeness regression test |
| `frontend-tests/chunk13_login_routing_verify.js` | Login routing + mirroring context regression test |
| `frontend-tests/ae_personalization_smoke.js` | AE dashboard personalization + reference scanner regression test |
| `BETA_CREDENTIALS_*.md` (local only) | Gitignored credential dumps — retained locally, never committed |

## Security Sanitation Result

* `.gitignore` covers `.env`, `.env.local`, `*.pem`, `*serviceAccount*.json`
  (verified via `git check-ignore`).
* `BETA_CREDENTIALS_2026-08-08.md` confirmed untracked/local-only.
* Repository-wide scan found **no** tracked private keys
  (`BEGIN PRIVATE KEY`), service-account JSON files, or production passwords.
  The only literal credentials are demo-seed constants documented in
  `docs/PROSPECT_DEMO_GUIDE.md` (prospect AE accounts provisioned per
  engagement).
