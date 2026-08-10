# Roadmap

Current-state roadmap for the AviaSAFE SMS Platform. Supersedes the earlier "Safety-Health" roadmap
(Supabase/Netlify era). The authoritative status source is
[docs/archive/PROJECT_STATUS_REPORT_05AUG2026.md](./docs/archive/PROJECT_STATUS_REPORT_05AUG2026.md).

## Milestones Reached

| Phase | Status | Notes |
|---|---|---|
| **Feature Development** | ✅ 100% | Survey, VSR/MOR, AI suggestions, dashboards, roles, CAN/CAP, verification, diversions, quarterly/annual reports + PDF |
| **RC-1 — Security Hardening** | ✅ COMPLETE | Env-only secrets, admin auth, debug endpoints closed, fail-closed provisioning |
| **RC-2 — Functional Corrections** | ✅ COMPLETE | Unified risk matrix (5/9/15), thresholds plumbed, 40 tests green |
| **RC-3 — Documentation & Operational Readiness** | 🔄 In progress | This phase |

## Remaining Release-Candidate Phases

- **RC-4 — Charter Re-alignment:** Survey refactor to 4 components / 12 elements with backend API
  (TD-6); resolve remaining functional inaccuracies.
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
