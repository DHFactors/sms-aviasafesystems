# Known Limitations & Technical Debt

Tracking register for the AviaSAFE platform as of RC-3. Each item maps to a `TD-<n>` identifier used
in `docs/archive/PROJECT_STATUS_REPORT_05AUG2026.md` (the authoritative register).

Legend: ✅ **Resolved** · 🔶 **Partially resolved** · ⏳ **Open**

## 1. Technical Debt (TD) Register

| ID | Item | Status | Notes |
|---|---|---|---|
| TD-1 | Admin surface had no Firebase auth + hardcoded secret | ✅ | RC-1: `SETUP_SECRET` env + SUPER_ADMIN ID-token guard; fail-closed 503 |
| TD-2 | Plaintext credentials in repo/docs | 🔶 | RC-1 purged source; RC-3 purges docs. All passwords now env-driven |
| TD-3 | Open debug endpoints (`/check-data`, `/debug-verify`) | ✅ | RC-1 closed |
| TD-4 | `PUT /risk-matrix` crash | ✅ | RC-1 fixed |
| TD-5 | Risk-matrix thresholds not plumbed; hazards/reports disagreed | ✅ | RC-2: single canonical scheme, stored thresholds honored everywhere |
| TD-6 | Survey not aligned to charter (4 components / 12 elements) | ⏳ | Live survey still non-compliant; Phase 6A re-alignment pending |
| TD-7 | `public/portal` mock code | ⏳ | Hygiene removal pending |
| TD-8 | No CI/CD; two `render.yaml` configs; service-name mismatch | ⏳ | Single authoritative manifest + CI (pytest) planned |
| TD-9 | (spare) | — | — |
| TD-10 | Firestore indexes camelCase vs snake_case drift | ⏳ | `firestore.indexes.json` vs `backend/firestore.indexes.json`; align to queries |
| TD-11 | Dead code / unused imports | 🔶 | RC-1/RC-2 pruned several (e.g., `classify_risk` import, dead `get_icao_*`) |
| TD-12 | Public-create spam surface (`responses`, `reports`, `public_responses`) | ⏳ | Server-side App Check + rate limiting decision pending |
| TD-13 | Legacy risk fields / dead functions | 🔶 | RC-2 removed `get_icao_level_from_string`, `get_icao_probability_from_likelihood`; legacy report fields remain for compatibility |
| TD-14 | (spare) | — | — |
| TD-15 | `seed_metadata.seeded_at` stored as ISO string; misc leftovers | 🔶 | RC-2 fixed `risk_matrix_config.updated_at` (Timestamp); `seeded_at` ISO remains |
| TD-16 | (spare) | — | — |
| TD-17 | Tenant-guide steps 02/03 manifests empty | ✅ | RC-3 authored steps 02 & 03 |

## 2. Security Limitations (see [SECURITY.md](./SECURITY.md))

- **MFA not enforced** — Firebase email/password only.
- **App Check not enforced server-side** — Firestore rules require attestation, but the FastAPI
  service does not call `verifyAppCheckToken`.
- **No automated dependency scanning / SAST / penetration test.**
- **No PII minimization or data-retention policy documented.**
- **No structured audit trail** (e.g., who confirmed which risk assessment).

## 3. Operational Limitations

- **No automated Firestore backups / PITR** configured — manual operator action required.
- **Shared staging/production Firestore project** — no dedicated staging environment.
- **Cloud Run is target-only**; current deployment is Render + Firebase Hosting.
- **Rate limiting** defaults to 60 req/min/IP in-memory; Redis-backed limits only when `REDIS_URL`
  is set (per-tenant policies not yet implemented).

## 4. Functional Limitations

- **AI suggestions are heuristic** — Gemini prompt/thresholds are informational; official
  `risk_assessment` is always the human-confirmed value. No evaluation set for AI accuracy.
- **Legacy risk fields** (`risk_score` 0–1, `severity`, `likelihood`, `consequence`) coexist with
  canonical `severity_level`/`probability_level`/`risk_index`/`risk_level` for compatibility;
  consumers should prefer the canonical fields.
- **No notifications service** (email/portal alerts) is implemented.
- **Survey maturity metrics** are not yet charter-compliant (TD-6) — the SMS Maturity component scores
  should be treated as interim until re-alignment.
- **`public/docs/tenant-guide` is served as static docs**, not dynamic onboarding UI.

## 5. Planned Work (next phases)

- **Phase 6A (RC-4 candidate):** Survey re-alignment to 4 components / 12 elements + backend API
  (TD-6).
- **Platform hygiene (RC-5):** TD-7, TD-11, TD-13 leftovers.
- **Release tooling (RC-5):** CI (lint + pytest + deploy), single `render.yaml` (TD-8), index
  alignment (TD-10).
- **Server-side App Check / spam control (TD-12).**

Nothing above is scheduled for RC-3 itself — RC-3 is documentation & operational readiness only.
