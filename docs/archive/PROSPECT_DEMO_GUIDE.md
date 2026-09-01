# Prospect Demo Guide — Virtual Tenant Mirroring

> **Audience:** AviaSAFE sales / success team running AE demonstrations.
> **Last updated:** 2026-08-21 · Seed 2.4.0 · Chunks 1–8 complete.

---

## 1. How It Works

Prospect Accountable Executives log in with their dedicated `ae@` account. At
login the router resolves the account's **archetype** and persists a mirroring
context (`window.DEMO_CONTEXT` + `localStorage`):

| Archetype | Dataset | Reference prefix |
|---|---|---|
| `demo-fixed-wing` | ATR / turboprop / STOL operations (168 hazards, 32 CANs) | `FW-HZ-####-26`, `FW-CAN-####-26`, `FW-CAP-####-26` |
| `demo-rotary-wing` | Mountain / HEMS helicopter operations (167 hazards, 30 CANs) | `RW-HZ-####-26`, `RW-CAN-####-26`, `RW-CAP-####-26` |

Both datasets carry the **full 365-day seasonal distribution** (pre-monsoon →
monsoon surge → festive peak → winter recovery) with realistic lifecycle aging:
old records are closed with verified residual SRAs, recent records are active.

**Masters are never modified during demos.** Every AE action (risk acceptance,
escalation decision) writes to an isolated 24-hour session overlay
(`demo_sessions/{session_id}/…`) that is merged on display only.

## 2. Login Credentials (20 Operators)

All accounts: role `AIRLINE_ADMIN`, routed to `/dashboard/ae-dashboard.html`.
Passwords are set per engagement in the Firebase Console
(project `aerosafety-sms-prod`) — rotate before each demo cycle.

### Fixed-Wing Group (`demo-fixed-wing`)

| Email | Company | Fleet | Base | IATA |
|---|---|---|---|---|
| ae@buddha-air.com | Buddha Air *(Mr. Birendra Basnet)* | ATR 72-500/ATR 42-320 | Tribhuvan Intl (VNKT) | BA |
| ae@yetiairlines.com | Yeti Airlines | ATR 72-500 | Kathmandu (VNKT) | YT |
| ae@shreeairlines.com | Shree Airlines | ATR 72-500 | Kathmandu (VNKT) | SH |
| ae@simrikair.com | Simrik Air | ATR 72-500 | Kathmandu (VNKT) | SM |
| ae@sauryaairlines.com | Saurya Airlines | ATR 72-500 | Kathmandu (VNKT) | SA |
| ae@taraair.com | Tara Air | Dornier 228 (STOL) | Kathmandu/Nepalgunj | TA |
| ae@summitair.com | Summit Air | ATR 72-500 | Kathmandu (VNKT) | SU |
| ae@kailashair.com | Kailash Air | Dornier 228 | Nepalgunj (VNJG) | KA |
| ae@mountainair.com | Mountain Air | Dornier 228 | Kathmandu (VNKT) | MT |
| ae@airdynasty.com | Air Dynasty | ATR 72-500 | Kathmandu (VNKT) | AD |

### Rotary-Wing Group (`demo-rotary-wing`)

| Email | Company | Fleet | Base | IATA |
|---|---|---|---|---|
| ae@fishtailair.com | Fishtail Air | H125 (AS350 B3e) | Kathmandu Heliport | FA |
| ae@manangair.com | Manang Air | H125 | Kathmandu Heliport | MA |
| ae@altitudeair.com | Altitude Air | H125/Bell 206 | Kathmandu Heliport | AL |
| ae@prabhuheli.com | Prabhu Helicopter | H125 | Kathmandu Heliport | PH |
| ae@simrikheli.com | Simrik Helicopter | H125 | Kathmandu Heliport | SH |
| ae@kailashheli.com | Kailash Helicopter | Bell 206 | Kathmandu Heliport | KH |
| ae@mountainheli.com | Mountain Helicopter | H125 | Kathmandu Heliport | MH |
| ae@fishtailheli.com | Fishtail Helicopter | H125 | Kathmandu Heliport | FH |
| ae@airvip.com | Air VIP | H125 | Kathmandu Heliport | AV |
| ae@eagleheli.com | Eagle Helicopter | H125 | Kathmandu Heliport | EH |

## 3. Suggested 10-Minute Demo Script

1. **Login (0:00)** — land on the branded *Accountable Executive Dashboard*;
   note company name in header/title, welcome line, fleet & base badge.
2. **Situational banner (0:30)** — SMS health (GREEN = Suitable & Operating),
   intolerable/high exposure, escalations pending, SPI trajectory,
   Doc 10159 precursor confidence (hover for the weighted breakdown).
3. **SMS Maturity panel (1:30)** — live PSOE score, four CAAN Appendix 10
   pillars (10/40/30/20), one-click **Appendix 10 PDF export** — "proof of
   regulatory readiness your inspector will ask for".
4. **Systemic Risk panel (3:00)** — intolerable vs high counts, overdue
   tracker, MTTC, 5×5 residual heatmap — "your exposure at a glance".
5. **Escalation queue (4:00)** — accept an escalated CAP or walk through the
   formal **risk-acceptance modal** (typed signature + review interval);
   highlight that masters stay untouched — decisions live in an isolated
   session ledger.
6. **Safety Intelligence (5:30)** — leading vs lagging KPIs, reporting culture
   vitality (VSR:MOR > 3:1 target), 12-month trajectory with CAR-19 alert
   limits, What-If mitigation sliders ("what happens to precursor risk if we
   clear these overdue CAPs?").
7. **Departmental matrix + governance roster (7:30)** — comparative postholder
   health and the CAR-19 compliance badge.
8. **Quick-Switch (9:00)** — flip between Fixed-Wing and Rotary-Wing datasets
   live to show breadth across operation types.

## 4. Quick-Switch Toolbar

* Append **`?demo=true`** to any page URL while logged in as an AE — a floating
  switcher appears bottom-right (persists for the browser session).
* Options: **Buddha Air (Fixed-Wing)** ↔ **Fishtail Air (Rotary-Wing)**.
* Switching re-resolves the mirroring context, re-fetches data, re-applies
  reference formatting (`FW-…` ⇄ `FA-…` / `BA-…`) and re-brands the UI — no
  reload needed on the dashboard.
* Sessions without `?demo=true` never see the toolbar.

## 5. Analytics

Every demo interaction lands in Firestore under `demo_analytics/{ae-email}/events`
(written by the backend; clients cannot read/write it directly):

`login_time`, `session_duration`, `pages_viewed`, `time_per_panel`,
`features_used`, `decisions_made`, `simulator_uses`, `exports_triggered`,
`switch_event`.

**Access:** Firebase Console → Firestore → `demo_analytics` → select the AE
email, or export via `gcloud firestore export`. Events carry timestamps and
payloads suitable for post-demo follow-up scoring.

## 6. Standard Tenants — Fallback Behavior (Unaffected)

* Only `ae@*` accounts registered in `PROSPECT_REGISTRY` activate mirroring.
* All other roles keep their existing routes: `safety@` → `/safety.html`,
  `145@`/`camo@` → responsible-manager view, `smd@caanepal.gov.np` → `/caan.html`.
* Data endpoints honor `archetypeId` **only** when it starts with the reserved
  `demo-` prefix; every other value falls back to the caller's own tenant, so
  cross-operator access remains impossible.
* CAP review endpoints hard-block writes to `demo-*` tenants — master archetype
  data stays immutable from both UI and API paths.
* The CAAN oversight list unions real operators with the two archetypes
  (13 tenants); removing a demo later is a single document edit away.

## 7. Operational Notes

* Re-seed archetypes anytime:
  `cd backend && python -m seed.runner --archetypes demo-fixed-wing,demo-rotary-wing,caanepal --force`
  (add `$env:FIREBASE_DATABASE_ID='sms-db'` for the beta database).
* Validate integrity:
  `python backend/scripts/validate_seasonal_seed.py --database sms-db`.
* Local fast iteration uses `--preset dev`; full staging uses `--preset full`.
* Support contact: `info@aviasafesystems.com`.
