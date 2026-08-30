# AviaSAFE SMS — Closed Beta Demo Accounts

Versioned reference for beta testers. Verified **2026-08-10**.

## Access

| Item | Value |
|------|-------|
| **Beta URL** | https://sms-beta.web.app |
| **Password scheme** | `{TENANT_CODE}-{ROLE}-2026` (see tables below) |
| **Support** | info@aviasafesystems.com |

> The beta runs on an isolated database (`sms-db-beta`) with demo data only. Nothing entered here touches production.

## Operator Accounts — Simplified Role Accounts

Each participating airline has four functional role accounts with the readable
email + password scheme. All are `AIRLINE_ADMIN` for their tenant.

| Airline | Code | Safety | CAMO | Part-145 | Ops |
|---------|------|--------|------|----------|-----|
| Buddha Air | `BHA` | safety@buddha-air.com | camo@buddha-air.com | 145@buddha-air.com | ops@buddha-air.com |
| Yeti Airlines | `YETI` | safety@yeti-airlines.com | camo@yeti-airlines.com | 145@yeti-airlines.com | ops@yeti-airlines.com |
| Summit Air | `SUMMIT` | safety@summit-air.com | camo@summit-air.com | 145@summit-air.com | ops@summit-air.com |
| Sita Air | `SITA` | safety@sita-air.com | camo@sita-air.com | 145@sita-air.com | ops@sita-air.com |
| Air Dynasty Heli Services | `DYNASTY` | safety@air-dynasty.com | camo@air-dynasty.com | 145@air-dynasty.com | ops@air-dynasty.com |
| Simrik Air | `SIMRIK` | safety@simrik-air.com | camo@simrik-air.com | 145@simrik-air.com | ops@simrik-air.com |
| Tara Air | `TARA` | safety@tara-air.com | camo@tara-air.com | 145@tara-air.com | ops@tara-air.com |

**Password for every account above:** `{TENANT_CODE}-{ROLE}-2026`, e.g.
`safety@buddha-air.com` → `BHA-Safety-2026`, `camo@buddha-air.com` →
`BHA-CAMO-2026`, `145@buddha-air.com` → `BHA-145-2026`, `ops@buddha-air.com` →
`BHA-Ops-2026`.

## Legacy Accounts (retained for compatibility)

| Airline | Safety Manager (Admin) | Airline Executive (Admin) | Manager (User) |
|---------|------------------------|---------------------------|----------------|
| Buddha Air | safety.buddha-air@buddhaair.com | ae.buddha-air@buddhaair.com | manager.buddha-air@buddhaair.com |
| Yeti Airlines | safety.yeti-airlines@yetiairlines.com | ae.yeti-airlines@yetiairlines.com | manager.yeti-airlines@yetiairlines.com |
| Summit Air | safety.summit-air@summitair.com.np | ae.summit-air@summitair.com.np | manager.summit-air@summitair.com.np |
| Sita Air | safety.sita-air@sitaair.com.np | ae.sita-air@sitaair.com.np | manager.sita-air@sitaair.com.np |
| Air Dynasty Heli Services | safety.air-dynasty@airdynasty.com.np | ae.air-dynasty@airdynasty.com.np | manager.air-dynasty@airdynasty.com.np |
| Simrik Air | safety.simrik-air@simrikair.com | ae.simrik-air@simrikair.com | manager.simrik-air@simrikair.com |
| Tara Air | safety.tara-air@taraair.com | ae.tara-air@taraair.com | manager.tara-air@taraair.com |

All operator accounts are bound to their airline tenant (role `AIRLINE_ADMIN`
for Safety Manager/Executive and the four role accounts, `USER` for Manager).

## CAAN / Regulatory Accounts

| Account | Email | Role |
|---------|-------|------|
| CAAN SMS Director | director.safety@caan.gov.np | `CAAN_SMD` |
| CAAN SMS Inspector | sms.inspector@caan.gov.np | `CAAN_SMD` |

## What Testers Should Do

1. Log in at https://sms-beta.web.app with the assigned account.
2. Follow the checklist (`docs/BETA_TEST_CHECKLIST.md`) — VSR, hazard registration, risk-matrix, CAPs, rate-limit behavior.
3. Report issues via the feedback form (see invitation email).
4. Use the beta for **testing only** — do not enter real personal data.

## Admin Notes (remove before sharing)

- Simplified role accounts use the readable `{TENANT_CODE}-{ROLE}-2026` password.
- Legacy accounts use the shared password = value of `DEFAULT_SEED_PASSWORD` in
  `backend/.env`. Fill `{SHARED_DEMO_PASSWORD}` above before distributing this
  document if you list them.
- The CAAN super-admin account was removed from the demo set (2026-08-10);
  provisioning/seed routes now require a SUPER_ADMIN provisioned separately.
- If a tester must use Google sign-in, their Google email must be added as `safety_manager.email` on the corresponding tenant doc in `sms-db-beta` (fallback resolution in `backend/app/middleware/auth.py`).
