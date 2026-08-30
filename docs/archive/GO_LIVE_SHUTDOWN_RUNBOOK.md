# AviaSAFE SMS — Go-Live & Beta Shutdown Runbook

Versioned reference. Verified **2026-08-06**.

## 1. Production Cleanup (Completed)

Production Firestore `sms-db` was wiped to a **clean, zero-tenant slate** ahead of commercial launch.

| Scope | Documents deleted |
|-------|-------------------|
| Tenant documents + all subcollections (reports / surveys / metadata) | 1,323 |
| State reference (`state/icao_top_risks/...`) | 26 |
| Seed metadata (`seed_metadata/seed`) | 1 |
| **Total** | **1,350** |

Verified post-cleanup via Firestore REST API:

```
sms-db        tenants : 0 docs, seed_metadata : 0 docs, state : 0 docs
sms-db-beta   tenants : 7 docs (untouched)
```

Firebase Auth users (24) were **kept** — Auth is project-wide and still required for beta login. No real operators exist yet; they will be provisioned by the admin after agreements are signed.

## 2. Cleanup Error Encountered & Resolution

- **Symptom:** first cleanup pass (one `delete()` call per document) crashed partway with `google.api_core.exceptions.RetryError: Timeout of 60.0s exceeded ... 503 Stream removed (WSARecv: Connection reset)`. Roughly one tenant was removed before the failure (6 → 5).
- **Root cause:** a long-running recursive per-document delete over thousands of documents over-ran the gRPC stream and hit a server-side connection reset.
- **Resolution:** rewrote cleanup to (a) enumerate all document references first, (b) delete in **batched commits (400 writes/batch)** sorted children-before-parents, and (c) retry each chunk with exponential backoff. The batched run completed cleanly and deleted the remaining 1,350 documents.
- **Lesson:** use batched writes (not per-document calls) for large Firestore deletions.

## 3. Current State — Production vs Beta

| Component | Production (commercial) | Beta (testing) |
|-----------|-------------------------|----------------|
| Hosting | `sms.aviasafesystems.com` (DNS + hosting domain connected) / `aerosafety-sms-prod.web.app` | `https://sms-beta.web.app` (site `sms-beta`, project `gap-analysis-ssp`) |
| Backend | `https://aviasafe-unified-platform.onrender.com` | `https://aviasafe-unified-platform.onrender.com` |
| Firestore | `sms-db` — **0 tenants (empty, clean slate)** | `sms-db-beta` — 7 tenants (demo data) |
| Redis | Not used | Upstash `aviasafe-redis` (rate limiting) |
| Auth users | 24 (shared project-wide) | 24 (shared project-wide) |
| Health | `{"status":"healthy","firebase":"connected",...}` | `live` endpoint OK |

Frontend routing (`public/js/firebase.js`) picks the environment by hostname: `beta` → `sms-db-beta` + beta backend; otherwise → `sms-db` + prod backend.

## 4. Beta Accounts

See `docs/BETA_TESTERS.md` for the full demo account list (7 airlines x 3 roles + 3 CAAN/regulatory accounts). All use the shared demo password (`DEFAULT_SEED_PASSWORD` in `backend/.env`), last reset 2026-08-06.

## 5. Go-Live Sequence (Commercial Launch)

1. **Live URL:** `sms.aviasafesystems.com` is already connected (DNS + Firebase Hosting domain). `ALLOWED_ORIGINS` already includes it.
2. **Post-agreement provisioning:** admin creates real operators/tenants in `sms-db` (currently empty) via the admin provisioning endpoints (`/provision-airlines`, `/create-seed-users`, `/setup-claims`) or direct Firestore writes. Do **not** use the demo seed for production.
3. **Auth users:** decide fate of the 24 demo users (recommend disabling/removing them before opening to real operators, since they are shared project-wide).
4. **Release smoke test:** log in with a provisioned real account at `sms.aviasafesystems.com`, submit a VSR, verify risk-matrix calculation and CAP flow.

## 6. Beta Shutdown Sequence (After Launch)

Do **not** shut down the beta until testers have completed the feedback window.

1. **Archive `sms-db-beta`** (optional): Firestore export before deletion. PITR is enabled with 7-day retention.
2. **Delete `sms-db-beta`** database.
3. **Delete the beta Render service** `sms-aviasafesystems-beta`.
4. **Delete the `sms-beta` hosting site** in project `gap-analysis-ssp`; delete that project too if it is used only for beta hosting.
5. **Delete/stop Upstash `aviasafe-redis`** (beta-only).
6. **Remove `https://sms-beta.web.app`** from `ALLOWED_ORIGINS`.
7. **Clean up demo auth users** (24) once no longer needed.

## 7. Verification Commands

```bash
# Production backend health
curl https://aviasafe-unified-platform.onrender.com/health
# -> {"status":"healthy","firebase":"connected","service":"AviaSAFE SMS API","version":"1.0.0"}

# Beta backend liveness
curl https://aviasafe-unified-platform.onrender.com/live

# Production DB must show zero tenants
gcloud firestore databases list --project=aerosafety-sms-prod
# (query tenants collection: 0 docs)

# Beta hosting deploy (site lives in gap-analysis-ssp)
firebase deploy --only hosting:sms-beta --project gap-analysis-ssp
```

## Related Documents

- `docs/BETA_TESTERS.md` — demo accounts for testers
- `docs/BETA_ENVIRONMENT.md` — beta environment setup
- `docs/archive/BETA_MONITORING_GUIDE.md` — monitoring during beta (now §9 of `docs/OPERATIONS.md`)
- `docs/BETA_TEST_CHECKLIST.md` — tester checklist
