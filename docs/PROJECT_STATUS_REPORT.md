# AviaSAFE — Project Status & Architecture Report

**Date:** 2026-08-22 · **Release:** Virtual Tenant Mirroring + Survey v4.0.0
**Scope:** Chunks 1–16 implemented and deployed · Chunk 17 (cleanup/docs) this report.

---

## 1. Executive Summary

AviaSAFE now ships a complete **prospect demonstration platform** built on
Virtual Tenant Mirroring: instead of duplicating data per operator, two master
archetype datasets (`demo-fixed-wing`, `demo-rotary-wing`) carry a full
365-day seasonal SMS history — hazards, corrective-action notices (CANs),
corrective-action plans (CAPs), Bow-Tie SRM barrier data, PSOE audits, and
baseline survey scoring — while each of the **20 prospect Accountable
Executives** sees the same master data re-branded with their own company,
executive name, fleet, base, and IATA reference codes.

Alongside the demo platform, the production survey engine was upgraded to the
**v4.0.0 contract — 31 bilingual questions scored across the 12 ICAO SMS
elements with proportional normalization** — fully backward-compatible with
the 23-question v3.0.0 submissions.

All sixteen implementation chunks are complete; quality gates are green
(537 backend tests, 53/53 inline-script checks), and both Firebase Hosting
targets plus the Firestore ruleset (now enforcing demo session isolation)
are deployed.

## 2. System Architecture

```
Prospect AE (ae@{operator})                      CAAN SMD (smd@caanepal.gov.np)
        │ login → archetypeId claim                       │
        ▼                                                 ▼
┌─────────────────────────────┐            ┌──────────────────────────────┐
│ ae-dashboard.html           │            │ caan.html aggregate          │
│ window.DEMO_CONTEXT         │◄───────────│ regulators/caan              │
│ localStorage(demo_context)  │   union    │ operator_tenant_ids (13)     │
└──────────────┬──────────────┘            └──────────────┬───────────────┘
               │ ?archetypeId=demo-* (safe fallback)      │
               ▼                                          ▼
   ═══════════ MASTER ARCHETYPE TENANTS (immutable from client) ═══════════
   tenants/demo-fixed-wing   (FW-HZ/FW-CAN/FW-CAP refs, ATR/STOL pools)
   tenants/demo-rotary-wing  (RW-HZ/RW-CAN/RW-CAP refs, HEMS/mountain pools)
   tenants/caan              (state regulator)
   ════════════════════════════════════════════════════════════════════════
               ▲ session overlays only (demo_sessions/*, 24h TTL)
   Prospect decisions never touch masters — enforced by API guard +
   firestore.rules (demo_sessions/** & demo_analytics/** deny-all to clients).
```

**Master archetypes**

| Tenant | Kind | Mirror profile | Volume (365d seasonal) |
|---|---|---|---|
| `demo-fixed-wing` | Fixed-wing (ATR/turboprop/STOL) | buddha-air shape | ~158–168 hazards · 31 CANs · 67 CAPs |
| `demo-rotary-wing` | Rotary-wing (HEMS/mountain) | fishtail-air shape | ~156–167 hazards · 27 CANs · 56 CAPs |

Seasonal engine: Jan–May pre-monsoon (8–12 haz/mo), Jun–Aug monsoon surge
(15–20, deeper barrier degradation, higher severity), Sep–Nov festive peak
(12–16), Dec recovery — scaled by operator workforce, annual floor 52.

**Supporting systems**: `caanepal` state-regulator tier aggregates both
archetypes *and* the 11 live operators through `regulators/caan`
(`operator_tenant_ids` union-merged). Survey v4 adds elements E1–E12 with
proportional normalization and the CAAN Appendix 10 weighted composite
(Policy 10 / SRM 40 / Assurance 30 / Promotion 20).

## 3. Quality Gates

| Gate | Result |
|---|---|
| Backend test suite | **537 / 537 passing** |
| Frontend inline-script checker | **53 / 53 passing** |
| Survey scoring (Chunk 9 suite) | 14 / 14 |
| Archetype API scoping tests | 7 / 7 |
| Demo session isolation tests | 7 / 7 |
| Seasonal seed validation | 122 / 122 checks |
| Registry contract (20 operators) | verified |
| Login-routing matrix (6 accounts) | verified |
| Personalization + formatter smoke | verified |

## 4. Deployment Endpoints

| Surface | URL / Target |
|---|---|
| Hosting (beta) | https://sms-beta.web.app · https://aerosafety-sms-beta.web.app |
| Hosting (prod) | https://aerosafety-sms-prod.web.app · https://sms.aviasafesystems.com |
| API (beta, Render) | https://aviasafe-unified-platform.onrender.com |
| API (prod, Render) | https://aviasafe-unified-platform.onrender.com |
| Firestore rules | `firestore/firestore.rules` (released with Chunk 16 deploy) |
| Backend repo hook | Render auto-deploy on push (see §6) |

## 5. Operational Guide — Running an AE Demonstration

Full playbook: [`docs/PROSPECT_DEMO_GUIDE.md`](PROSPECT_DEMO_GUIDE.md).

Quick sequence:
1. Provision/rotate the prospect's `ae@…` password in Firebase Console.
2. Share `https://sms-beta.web.app/login.html` (or tenant portal URL).
3. The executive lands on their branded governance dashboard.
4. Optional sales mode: append **`?demo=true`** → floating Quick-Switch
   toolbar (Buddha Air ↔ Fishtail Air) + subtle "🔬 Demo Environment" badge.
5. Decisions made during the demo persist for 24 h in the isolated session
   ledger (`demo_sessions/{session_id}/decisions`) — masters stay pristine.
6. Telemetry lands in `demo_analytics/{ae-email}/events` for follow-up scoring.

## 6. Known Follow-Ups

* Render service picks up backend changes (Chunks 6–7 API layer) on the next
  push-triggered deploy — verify after this release.
* Prospect AE Auth users are provisioned per engagement (Firebase Console or
  Admin SDK); passwords are never committed.
* `backend/remove_caan.py`-style one-off scripts were removed in Chunk 17;
  keep scratch tooling out of the repository root.
