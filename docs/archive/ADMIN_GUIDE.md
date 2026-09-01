# Administrator Guide

Operational guide for platform administrators (`SUPER_ADMIN`, `CAAN_SMD`, `AIRLINE_ADMIN`).

> End-user and tenant onboarding guidance lives in
> [public/docs/tenant-guide/](../public/docs/tenant-guide/). This document is for operators who
> manage users, tenants, and platform configuration.

## 1. Roles Overview

| Role | Scope | Key capabilities |
|---|---|---|
| `SUPER_ADMIN` | System-wide | Provision airlines, fix tenant ids, risk-matrix defaults, seed/demo operations, claim setup |
| `CAAN_SMD` | Cross-tenant (read + risk confirm) | View any tenant's data, confirm risk assessments |
| `AIRLINE_ADMIN` | Own tenant | Full tenant management, report/hazard/CAN-CAP workflow, risk-matrix config, confirm assessments |
| `USER` | Own tenant | Submit VSR/MOR, view own-tenant dashboards |

Cross-tenant roles are `CAAN_SMD`, `SUPER_ADMIN` (see `CROSS_TENANT_ROLES`). Registration assigns
`AIRLINE_ADMIN` by default.

## 2. Admin API Endpoints

Base: `/api/v1/admin` (canonical) or `/api/admin` (legacy). All require a SUPER_ADMIN ID token;
setup-key endpoints additionally require `X-Setup-Key: <SETUP_SECRET>` (503 when unset).

| Endpoint | Method | Purpose | Setup key |
|---|---|---|---|
| `/setup-claims` | POST | Resolve/create roles & tenant claims for users | No |
| `/provision-airlines` | POST | Create tenants + admin users + CAAN accounts | Yes |
| `/fix-tenant-ids` | POST | Reconcile `_`/`-` tenant-id drift | No |
| `/risk-matrix` | GET | Read default risk matrix thresholds | No |
| `/risk-matrix` | PUT | Set default risk matrix thresholds | Yes |
| `/seed-demo-data` | POST | Destructive re-seed (404 unless disabled) | Yes |
| `/create-seed-users` | POST | Recreate seed users (404 unless disabled) | Yes |

**Important:** `DISABLE_DESTRUCTIVE_ENDPOINTS` defaults to `true`; production returns `404` on the
destructive endpoints. Disable only in non-production.

## 3. Tenant & Risk-Matrix Configuration

- **Risk matrix thresholds** (per-tenant or default): severity/probability 1–5 scale → risk index
  1–25, classified with `low_max` / `medium_max` / `high_max` (default `5/9/15`) into
  `Low | Medium | High | Very High`, with outcomes `Acceptable | Tolerable | Intolerable`.
- Per-tenant stored thresholds in `tenants/{id}/metadata/risk_matrix` are honored by all scoring
  since RC-2. Changing defaults via `/risk-matrix` affects tenants that have not stored their own
  config.
- Tenants are provisioned with the ICAO SMS pillars/elements and a risk matrix config; the survey
  config lives in `tenants/{id}/metadata`.

## 4. Security Responsibilities (Administrators)

- **Never** store or document plaintext credentials. All passwords are env-driven
  (`DEFAULT_PROVISION_PASSWORD`, `DEFAULT_SEED_PASSWORD`, `SETUP_SECRET`).
- Protect `SETUP_SECRET`; rotate it in the platform env config if it leaks.
- Verify a user's role via the Firebase console (Authentication → Users → Claims) when claim
  propagation is suspected.
- Report incidents and security events in the status report and rotate affected secrets.
- Follow the platform's "no secrets in the repo" policy (RC-1 hardening).

## 5. Daily / Weekly Checklist

- [ ] Review `backend/logs/` for 4xx/5xx spikes and auth failures.
- [ ] Check `/metrics` and health endpoints.
- [ ] Verify tenant isolation on one cross-tenant read.
- [ ] Confirm rate-limit config is as intended.
- [ ] Confirm no plaintext credentials exist in docs/repo (grep for known passwords).
- [ ] Record any operational event in the status report under `docs/archive/`.

## 6. Troubleshooting

| Symptom | Likely cause / action |
|---|---|
| Admin endpoint `503` | `SETUP_SECRET` not configured in the environment |
| Admin endpoint `403` | Token is not SUPER_ADMIN; or claims not propagated yet |
| `404` on seed endpoints | `DISABLE_DESTRUCTIVE_ENDPOINTS=true` (expected in production) |
| Risk levels unexpected | Tenant stored a custom risk-matrix config — inspect `tenants/{id}/metadata/risk_matrix` |
| Users can't log in | Check Auth user existence and reset password via Firebase console |
