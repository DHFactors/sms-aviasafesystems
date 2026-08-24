# AviaSAFE SMS — Verified Demo Credentials (sms-db-beta)

> **Generated from `backend/seed/config.py` (source of truth).**
> These are the passwords the seeder (`seed/runner.py --users-only`) writes to Firebase Auth in `sms-db-beta` (`aerosafety-sms-prod`).
> If a login returns *Invalid email or password*, the Auth record is missing or stale — use the fix commands below.

Seed version: see `seed/config.py:SEED_VERSION`
Total operator accounts (from seed): 48 + 6 Saurya (virtual) + 2 CAAN/DEV = 56

## Quick Fix (Summit Air example — same pattern for every account)

```bash
# 1) Ensure the local demo backend has the right DB (backend/.env.demo):
FIREBASE_PROJECT_ID=aerosafety-sms-prod
FIREBASE_DATABASE_ID=sms-db-beta
# 2) Re-seed ONLY the Auth users (idempotent, fixes every demo password):
python -m seed.deploy_seed --users-only --yes        # from backend/  (targets sms-db-beta by default)
# 3) Or fix a single account (no re-seed):
python backend/scripts/fix_summit_air_user.py         # fixes safety@summitair.com
python backend/scripts/fix_summit_air_user.py --all   # fixes ALL 48 operator accounts
```

## Summit Air — why the reported login failed

- **Reported:** `safety@summitair.com` / `SUMMIT-Safety-2026` → *Invalid email or password*
- **Authoritative password (seed/config.py):** `SUMMIT-Safety-2026` ✓ — the documented password **IS correct**.
- **Root cause:** Firebase Auth record missing or overwritten. `BETA_CREDENTIALS_2026-08-08.md` is **stale** (dated 2026-08-08, before the 2026-08-21 simplified scheme). It lists `safety.summit-air@summitair.com.np` with random `TV8x7OL5i9zA0B@k` — that email/password never existed in the simplified seeder. The live `beta-testing-credentials.csv` (current) correctly lists `safety@summitair.com` / `SUMMIT-Safety-2026` and matches the seeder output.
- **Firebase CLI alternative (no Python):**
  ```bash
  firebase auth:export users.json --project aerosafety-sms-prod  # inspect
  # Then via Admin SDK / Console → Authentication → Users → Add user / Reset password
  ```
- **Fix:** `python backend/scripts/fix_summit_air_user.py` (creates/updates `safety-summit-air-001` and verifies via Identity Toolkit REST).

## All Operator Demo Accounts (verified against seeder)

| Tenant | Role | Email | Password | UID | App Role |
|--------|------|-------|----------|-----|----------|
| Air Dynasty Heli Services | Part-145 Maintenance | `145@air-dynasty.com` | `DYNASTY-145-2026` | `145-air-dynasty-001` | USER |
| Air Dynasty Heli Services | CAMO Manager | `camo@air-dynasty.com` | `DYNASTY-CAMO-2026` | `camo-air-dynasty-001` | USER |
| Air Dynasty Heli Services | Operations Manager | `ops@air-dynasty.com` | `DYNASTY-Ops-2026` | `ops-air-dynasty-001` | USER |
| Air Dynasty Heli Services | Safety Manager | `safety@air-dynasty.com` | `DYNASTY-Safety-2026` | `safety-air-dynasty-001` | AIRLINE_ADMIN |
| Buddha Air | Part-145 Maintenance | `145@buddha-air.com` | `BHA-145-2026` | `145-buddha-air-001` | USER |
| Buddha Air | CAMO Manager | `camo@buddha-air.com` | `BHA-CAMO-2026` | `camo-buddha-air-001` | USER |
| Buddha Air | Operations Manager | `ops@buddha-air.com` | `BHA-Ops-2026` | `ops-buddha-air-001` | USER |
| Buddha Air | Safety Manager | `safety@buddha-air.com` | `BHA-Safety-2026` | `safety-buddha-air-001` | AIRLINE_ADMIN |
| Fishtail Air | Part-145 Maintenance | `145@fishtailair.com` | `FISHTAIL-145-2026` | `145-fishtail-air-001` | USER |
| Fishtail Air | Accountable Executive | `ae@fishtailair.com` | `FISHTAIL-AE-2026` | `ae-fishtail-air-001` | AIRLINE_ADMIN |
| Fishtail Air | CAMO Manager | `camo@fishtailair.com` | `FISHTAIL-CAMO-2026` | `camo-fishtail-air-001` | USER |
| Fishtail Air | Operations Manager | `ops@fishtailair.com` | `FISHTAIL-Ops-2026` | `ops-fishtail-air-001` | USER |
| Fishtail Air | Line Pilot | `pilot@fishtailair.com` | `FISHTAIL-Pilot-2026` | `pilot-fishtail-air-001` | USER |
| Fishtail Air | Safety Manager | `safety@fishtailair.com` | `FISHTAIL-Safety-2026` | `safety-fishtail-air-001` | AIRLINE_ADMIN |
| Himalaya Ground Handling | Part-145 Maintenance | `145@himalaya-ground-services.com` | `HGS-145-2026` | `145-himalaya-ground-services-001` | USER |
| Himalaya Ground Handling | CAMO Manager | `camo@himalaya-ground-services.com` | `HGS-CAMO-2026` | `camo-himalaya-ground-services-001` | USER |
| Himalaya Ground Handling | Operations Manager | `ops@himalaya-ground-services.com` | `HGS-Ops-2026` | `ops-himalaya-ground-services-001` | USER |
| Himalaya Ground Handling | Safety Manager | `safety@himalaya-ground-services.com` | `HGS-Safety-2026` | `safety-himalaya-ground-services-001` | AIRLINE_ADMIN |
| Kathmandu MRO Services | Part-145 Maintenance | `145@ktm-mro.com` | `KTM-145-2026` | `145-ktm-mro-001` | USER |
| Kathmandu MRO Services | CAMO Manager | `camo@ktm-mro.com` | `KTM-CAMO-2026` | `camo-ktm-mro-001` | USER |
| Kathmandu MRO Services | Operations Manager | `ops@ktm-mro.com` | `KTM-Ops-2026` | `ops-ktm-mro-001` | USER |
| Kathmandu MRO Services | Safety Manager | `safety@ktm-mro.com` | `KTM-Safety-2026` | `safety-ktm-mro-001` | AIRLINE_ADMIN |
| Pokhara Regional Aerodrome | Part-145 Maintenance | `145@pokhara-aerodrome.com` | `PKR-145-2026` | `145-pokhara-aerodrome-001` | USER |
| Pokhara Regional Aerodrome | CAMO Manager | `camo@pokhara-aerodrome.com` | `PKR-CAMO-2026` | `camo-pokhara-aerodrome-001` | USER |
| Pokhara Regional Aerodrome | Operations Manager | `ops@pokhara-aerodrome.com` | `PKR-Ops-2026` | `ops-pokhara-aerodrome-001` | USER |
| Pokhara Regional Aerodrome | Safety Manager | `safety@pokhara-aerodrome.com` | `PKR-Safety-2026` | `safety-pokhara-aerodrome-001` | AIRLINE_ADMIN |
| Simrik Air | Part-145 Maintenance | `145@simrik-air.com` | `SIMRIK-145-2026` | `145-simrik-air-001` | USER |
| Simrik Air | CAMO Manager | `camo@simrik-air.com` | `SIMRIK-CAMO-2026` | `camo-simrik-air-001` | USER |
| Simrik Air | Operations Manager | `ops@simrik-air.com` | `SIMRIK-Ops-2026` | `ops-simrik-air-001` | USER |
| Simrik Air | Safety Manager | `safety@simrik-air.com` | `SIMRIK-Safety-2026` | `safety-simrik-air-001` | AIRLINE_ADMIN |
| Sita Air | Part-145 Maintenance | `145@sita-air.com` | `SITA-145-2026` | `145-sita-air-001` | USER |
| Sita Air | CAMO Manager | `camo@sita-air.com` | `SITA-CAMO-2026` | `camo-sita-air-001` | USER |
| Sita Air | Operations Manager | `ops@sita-air.com` | `SITA-Ops-2026` | `ops-sita-air-001` | USER |
| Sita Air | Safety Manager | `safety@sita-air.com` | `SITA-Safety-2026` | `safety-sita-air-001` | AIRLINE_ADMIN |
| Summit Air | Part-145 Maintenance | `145@summitair.com` | `SUMMIT-145-2026` | `145-summit-air-001` | USER |
| Summit Air | Accountable Executive | `ae@summitair.com` | `SUMMIT-AE-2026` | `ae-summit-air-001` | AIRLINE_ADMIN |
| Summit Air | CAMO Manager | `camo@summitair.com` | `SUMMIT-CAMO-2026` | `camo-summit-air-001` | USER |
| Summit Air | Operations Manager | `ops@summitair.com` | `SUMMIT-Ops-2026` | `ops-summit-air-001` | USER |
| Summit Air | Line Pilot | `pilot@summitair.com` | `SUMMIT-Pilot-2026` | `pilot-summit-air-001` | USER |
| Summit Air | Safety Manager | `safety@summitair.com` | `SUMMIT-Safety-2026` | `safety-summit-air-001` | AIRLINE_ADMIN |
| Tara Air | Part-145 Maintenance | `145@tara-air.com` | `TARA-145-2026` | `145-tara-air-001` | USER |
| Tara Air | CAMO Manager | `camo@tara-air.com` | `TARA-CAMO-2026` | `camo-tara-air-001` | USER |
| Tara Air | Operations Manager | `ops@tara-air.com` | `TARA-Ops-2026` | `ops-tara-air-001` | USER |
| Tara Air | Safety Manager | `safety@tara-air.com` | `TARA-Safety-2026` | `safety-tara-air-001` | AIRLINE_ADMIN |
| Yeti Airlines | Part-145 Maintenance | `145@yeti-airlines.com` | `YETI-145-2026` | `145-yeti-airlines-001` | USER |
| Yeti Airlines | CAMO Manager | `camo@yeti-airlines.com` | `YETI-CAMO-2026` | `camo-yeti-airlines-001` | USER |
| Yeti Airlines | Operations Manager | `ops@yeti-airlines.com` | `YETI-Ops-2026` | `ops-yeti-airlines-001` | USER |
| Yeti Airlines | Safety Manager | `safety@yeti-airlines.com` | `YETI-Safety-2026` | `safety-yeti-airlines-001` | AIRLINE_ADMIN |
| Saurya Airlines | Safety Manager | `safety@sauryaairlines.com` | `SAU-Safety-2026` | — | AIRLINE_ADMIN |
| Saurya Airlines | CAMO Manager | `camo@sauryaairlines.com` | `SAU-CAMO-2026` | — | USER |
| Saurya Airlines | Part-145 Maintenance | `145@sauryaairlines.com` | `SAU-145-2026` | — | USER |
| Saurya Airlines | Flight Operations | `ops@sauryaairlines.com` | `SAU-Ops-2026` | — | USER |
| Saurya Airlines | Accountable Executive | `ae@sauryaairlines.com` | `SAU-AE-2026` | — | AIRLINE_ADMIN |
| Saurya Airlines | Line Pilot | `pilot@sauryaairlines.com` | `SAU-Pilot-2026` | — | USER |
| CAAN | CAAN SMD | `smd@caanepal.gov.np` | `CAAN-Safety-2026` | — | CAAN_SMD |
| CAAN | Super Admin | `ezondiza.dhf@gmail.com` | `DEV-Aviasafe-2026` | — | SUPER_ADMIN |

### Operator ID reference (for `--tenant-id` scoping)

- `buddha-air` — Buddha Air (airline, buddhaair.com)
- `air-dynasty` — Air Dynasty Heli Services (helicopter-operator, airdynasty.com.np)
- `ktm-mro` — Kathmandu MRO Services (mro, ktm-mro.com)
- `pokhara-aerodrome` — Pokhara Regional Aerodrome (aerodrome, pokhara-aerodrome.com)
- `himalaya-ground-services` — Himalaya Ground Handling (ground-handling, himalaya-ground-services.com)
- `yeti-airlines` — Yeti Airlines (airline, yetiairlines.com)
- `summit-air` — Summit Air (airline, summitair.com)
- `sita-air` — Sita Air (airline, sitaair.com.np)
- `simrik-air` — Simrik Air (helicopter-operator, simrikair.com)
- `tara-air` — Tara Air (airline, taraair.com)
- `fishtail-air` — Fishtail Air (helicopter-operator, fishtailair.com)
- `caan` — Civil Aviation Authority of Nepal (state-regulator, `caanepal.gov.np`)
- `saurya-airlines` — Saurya Airlines (virtual archetype demo — not in OPERATOR_PROFILES, see `beta-testing-credentials.csv`)

### Domains & Tenant Codes (seed/config.py)

| Operator | Domain | Code |
|----------|--------|------|
| air-dynasty | air-dynasty.com | DYNASTY |
| buddha-air | buddha-air.com | BHA |
| fishtail-air | fishtailair.com | FISHTAIL |
| himalaya-ground-services | himalaya-ground-services.com | HGS |
| ktm-mro | ktm-mro.com | KTM |
| pokhara-aerodrome | pokhara-aerodrome.com | PKR |
| simrik-air | simrik-air.com | SIMRIK |
| sita-air | sita-air.com | SITA |
| summit-air | summitair.com | SUMMIT |
| tara-air | tara-air.com | TARA |
| yeti-airlines | yeti-airlines.com | YETI |

### Local Docker Demo — Copilot + CORS

- Frontend on `http://localhost:5005` (`firebase serve`) must reach backend on `http://localhost:8000`.
- Set once in browser console: `localStorage.setItem('aviasafe:localApiBaseUrl','http://localhost:8000')` — `public/js/components/copilot-widget.js:119` now reads it on every request (guest + auth), and `public/js/firebase.js:81` sets `APP_CONFIG.apiBaseUrl` the same way.
- Backend CORS allowlist (`backend/app/main.py:24`, `app/core/cors.py:23`, `app/core/config.py:72`, `.env.demo.example:45`) now includes `http://localhost:5005` and `http://127.0.0.1:5005`.
- Groq: `backend/.env.demo.example:29` now documents `GROQ_API_KEY` as **REQUIRED** for Copilot; `backend/app/services/gemini.py:26` guards `google.generativeai` behind try/except so a missing/deprecated SDK never crashes the Copilot route (degrades to mock analysis).
