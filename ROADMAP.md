# Roadmap

Current-state roadmap for the AviaSAFE SMS Platform. Supersedes the earlier "Safety-Health" roadmap
(Supabase/Netlify era). The authoritative status source is
[docs/archive/PROJECT_STATUS_REPORT_05AUG2026.md](./docs/archive/PROJECT_STATUS_REPORT_05AUG2026.md);
the latest dated report is [docs/PROJECT_STATUS_REPORT_2026-08-24.md](./docs/PROJECT_STATUS_REPORT_2026-08-24.md).

## Milestones Reached

| Phase | Status | Notes |
|---|---|---|
| **Feature Development** | ✅ 100% | Survey, VSR/MOR, AI suggestions, dashboards, roles, CAN/CAP, verification, diversions, quarterly/annual reports + PDF |
| **RC-1 — Security Hardening** | ✅ COMPLETE | Env-only secrets, admin auth, debug endpoints closed, fail-closed provisioning |
| **RC-2 — Functional Corrections** | ✅ COMPLETE | Unified risk matrix (5/9/15), thresholds plumbed |
| **RC-3 — Documentation & Operational Readiness** | ✅ COMPLETE | GLOSSARY.md, tenant-guide steps 02/03, deploy docs, seed v2.1.0 (10 providers + CAAN), legacy purge, audit tooling, admin feedback review, survey campaign windows |
| **SRA & RCA Analysis Toolkit** | ✅ COMPLETE | 5x5 Safety Risk Assessment matrix, 6-category Fishbone root-cause analysis, 1:1 action-item linkage to CANs (2026-08-16) |
| **Tenant Operational Profiles** | ✅ COMPLETE | Constraint-based demo seeder (fleet, base hub, authorized destinations, hazard domains) + 5 demo reference profiles (2026-08-17) |
| **Multi-tenant Routing & Demo Switcher** | ✅ COMPLETE | Subdomain→tenant resolver, conditional demo persona switcher, email→department mapping (2026-08-17) |
| **Latency Baseline & Local Demo Environment** | ✅ COMPLETE | `[PERF]` request instrumentation (pending Render push), root-cause analysis (cold starts / unfiltered Firestore scans / AI timeouts), one-click local Docker demo targeting `sms-db-beta` (2026-08-24) |

## Remaining Release-Candidate Phases

- **RC-4 — Charter Re-alignment & Compliance Audit:** Survey is now aligned to the 4 ICAO
  components / 12 elements with a backend scoring endpoint (survey v3.0.0); remaining work is a
  formal compliance audit of the 12-element mapping, the live SMS Maturity dashboard output, and any
  residual functional inaccuracies.
- **RC-5 — Platform Hygiene & Tooling:** remove `public/portal` mock code (TD-7), prune dead code
  (TD-11/TD-13 leftovers), CI (lint + pytest + deploy), single `render.yaml` (TD-8), align
  Firestore indexes (TD-10).
- **RC-6 — Pre-Production / Pilot:** App Check server-side enforcement (TD-12), MFA, backups/PITR,
  audit trail, staging environment, penetration/security review.

## Product Roadmap (post-pilot, charter-gated)

Per the [Product Charter](./docs/archive/PROJECT_CHARTER.md), feature expansion requires explicit approval.
Candidate product work (not committed):

- Monitoring / alerting for SMS maturity thresholds.
- Notifications service (email/portal).
- AI assistant enhancements (evaluation set, per-tenant prompt tuning).
- State-of-the-System reports and SSP effectiveness reporting automation.

*Nothing here is scheduled without approval.*