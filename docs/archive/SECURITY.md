# Security Documentation

This document describes the **actual** security model implemented as of RC-3. It intentionally
corrects older claims (MFA, AES-256 at rest, RLS) that do not match this implementation.

## 1. Threat Model (brief)

- **Client-impersonation:** an attacker registering a fake tenant/user and reading others' data.
- **Privilege escalation:** a normal user gaining cross-tenant or admin access.
- **Secret exposure:** committed credentials, misconfigured env, plaintext passwords in docs.
- **Data integrity:** tampering with immutable survey responses or deleting reports.
- **Availability:** rate-limit abuse, unauthenticated public-write abuse.

## 2. Authentication

- **Firebase Authentication** (email/password). The web client signs in and obtains an ID token
  (RS256 JWT). **MFA is not enforced** at this time — this is a documented limitation.
- Backend verifies tokens via the **Firebase Admin SDK** (`verify_id_token`); no manual JWT parsing.
- Token expiry/refresh handled by the SDK client; `/api/v1/auth/verify` validates, `/refresh`
  exchanges a refresh token.
- Role/tenant come from **custom claims** (`role`, `tenant_id`). Because claim propagation can lag,
  the backend falls back to an email→tenant lookup (`_lookup_tenant_by_email`) so users are not
  locked out immediately after provisioning. Re-login applies claims.

## 3. Authorization (RBAC)

Four roles enforced in `backend/app/middleware/auth.py` and mirroring Firebase rules:

| Role | Tenant scope | Admin/risk actions |
|---|---|---|
| `SUPER_ADMIN` | All tenants | Admin endpoints, setup-key-protected provisioning, destructive ops |
| `CAAN_SMD` | Read all tenants | Confirm risk assessments (State) |
| `AIRLINE_ADMIN` | Own tenant | Full tenant workflow, risk-matrix config, confirm assessments |
| `USER` | Own tenant | Submit/read own-tenant reports |

Guard dependencies: `get_current_user`, `get_tenant_user`, `get_caan_user`, `get_admin_user`,
`get_safety_manager`, `get_responsible_manager`, `get_accountable_executive`. Cross-tenant roles
are configurable (`CROSS_TENANT_ROLES`).

**Tenant normalization:** `tenant_id` is normalized `_`→`-` to reconcile seed/provisioned data;
`POST /api/v1/admin/fix-tenant-ids` repairs historic drift.

## 4. App Check

- **Firebase App Check** with the **reCAPTCHA v3** provider is activated client-side in
  `public/js/firebase.js` (auto-refresh enabled).
- Firestore security rules require App Check attestation for all Firestore requests.
- **Limitation:** App Check enforcement is not enabled on the backend API path (the FastAPI service
  does not call `verifyAppCheckToken`). Enforcement on API calls is planned (see
  [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md)).

## 5. Firestore Security Rules

`firestore/firestore.rules` (rules_version `2`). Helpers: `isAuthenticated`, `isSuperAdmin`,
`isCaanSMD`, `isAirlineAdmin`, `getTenantId`, `isOwnTenant`, `isAdminOrCaan`.

| Path | Read | Write |
|---|---|---|
| `/tenants/{tenantId}` | authenticated | create/update/delete: SUPER_ADMIN only |
| `/tenants/{tenantId}/metadata/{doc=**}` | owned-tenant or admin/CAAN | SUPER_ADMIN only |
| `/tenants/{tenantId}/responses/{id}` | owned-tenant or admin/CAAN | **create only**; update/delete denied (immutable audit trail) |
| `/tenants/{tenantId}/reports/{id}` | owned-tenant or admin/CAAN | create (tenant self); update: owned-tenant or SUPER_ADMIN; delete denied |
| `/tenants/{tenantId}/mor/{id}` | owned-tenant or admin/CAAN | create/update: owned-tenant or SUPER_ADMIN; delete denied |
| `/tenants/{tenantId}/hazards/{id}` | owned-tenant or admin/CAAN | create/update: owned-tenant or SUPER_ADMIN; delete: SUPER_ADMIN |
| `/tenants/{tenantId}/can_cap/{id}` | owned-tenant or admin/CAAN | create/update: owned-tenant or SUPER_ADMIN; delete: SUPER_ADMIN |
| `/tenants/{tenantId}/verification/{doc=**}` | owned-tenant or admin/CAAN | create/update: owned-tenant or SUPER_ADMIN; delete: SUPER_ADMIN |
| `/tenants/{tenantId}/flight_diversions/{doc=**}` | owned-tenant or admin/CAAN | create/update: owned-tenant or SUPER_ADMIN; delete: SUPER_ADMIN |
| `/analytics/{doc=**}` | CAAN_SMD or SUPER_ADMIN | SUPER_ADMIN only |
| `/public_responses/{doc=**}` | SUPER_ADMIN | **create by anyone**; update/delete SUPER_ADMIN |
| `/users/{uid}` | self or SUPER_ADMIN | self or SUPER_ADMIN |

Rules are enforced at the Firestore layer (defense in depth) and the backend additionally
enforces tenant scoping per route.

## 6. Secret Management & Environment

- **All backend secrets are environment-driven** (`backend/.env` locally; platform env config in
  production). RC-1 removed hardcoded credentials.
- Admin endpoints are **fail-closed**: they return `503` if `SETUP_SECRET` is not set, and a
  SUPER_ADMIN ID token is always required — the key alone never grants access.
- `DEFAULT_PROVISION_PASSWORD` / `DEFAULT_SEED_PASSWORD` have **no hardcoded fallback**; seed runs
  fail when absent.
- **No plaintext passwords may appear in docs/repo.** RC-3 replaced credential-bearing guides
  (DEMO_GUIDE, ONBOARDING_CREDENTIALS, WELCOME_EMAIL, UAT_READINESS, PROJECT_STATUS) with
  placeholders/env references.
- The web client's Firebase config in `public/js/firebase.js` is **public by design** (API key,
  project id, app id). Do not move these to the backend as secrets.
- `SETUP_SECRET` must be rotated if leaked.

## 7. Transport & Headers

- All traffic HTTPS (Firebase Hosting + Render managed TLS).
- `SecurityHeadersMiddleware` sets: HSTS, `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, XSS protection, Referrer-Policy, Permissions-Policy.
- CORS allow-list via `ALLOWED_ORIGINS` (default: Hosting origin + local dev ports). Note: local
  dev origin `http://localhost:3000` is permitted — review before production if undesired.

## 8. Data Protection

- **At rest:** Cloud Firestore (Google-managed encryption at rest). The older "AES-256" claim refers
  to Google's default encryption, not a custom scheme.
- **Surveys:** immutable after creation (rules deny update/delete) — audit-trail guarantee.
- **Reports:** append-only (delete denied); correction is via update.
- **No PII minimization or retention policy is yet documented** — outstanding (see
  [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md)).

## 9. Rate Limiting & Abuse

- Default `RATE_LIMIT_PER_MINUTE: 60` per IP (in-memory). Redis-backed per-tenant when `REDIS_URL`
  is configured.
- `429` on breach. Public-write surfaces (survey responses, `/public_responses`) are the main abuse
  vectors; monitor them.

## 10. Audit & Logging

- Request middleware logs UUID/method/path/status/duration/user; loguru to `backend/logs/`.
- No structured audit-trail (who-confirmed-what) storage exists yet — outstanding.

## 11. Security Verification & Known Gaps

**Implemented & verified (RC-1/RC-2):**
- Admin endpoints fail-closed (503 without `SETUP_SECRET`; 404 destructive when disabled).
- Plaintext passwords purged from source; env-driven provisioning/seed.
- Firestore rules restrict write paths and deny delete on immutable collections.
- 40 backend tests (incl. RBAC/tenant-scoping and risk-matrix classification).

**Known gaps (tracked in KNOWN_LIMITATIONS.md):**
- MFA not enforced.
- App Check not enforced on backend API calls.
- No automated dependency/vuln scanning or penetration test.
- No PII retention policy; no structured audit trail.
- Shared staging/production Firestore.
