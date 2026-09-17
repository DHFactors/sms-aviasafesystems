# Delivery Work Order — 2026-09-14 (Sita Air Delivery Day)

SCOPE: Prepare for and support the Sita Air delivery. Do NOT
start Phase 1 work until delivery is confirmed accepted.

## Morning — Delivery Prep

### Task 1 — Deploy verification
- Read /health from production
- Confirm status=healthy, firebase=connected, database=connected
- Record the commit SHA
- Compare to local HEAD on main
- Report both values and whether they match

### Task 2 — Sita Air tenant sanity check
- Verify sita-air tenant row: name, regulator, is_demo=false
- Verify 4 users: super-admin, safety@, ae@, 145@sitaair.com.np
- Verify all three tenant users have correct roles and tenant_id claims
- Verify Auth pool state (should be exactly 4)
- Verify seed counts: 80 VSR, 19 MOR, 16 hazards, 16 CAN, 12 CAP, 204 surveys
- Verify DLQ = 0
- Report each value

### Task 3 — Login page reachability
- Confirm https://sms.aviasafesystems.com/login.html returns 200
- Confirm the three target landing pages return 200 (unauth, so gated pages redirect — record the redirect status, not a 500)
- Report status codes

## Mid-Morning — Delivery Support

### Task 4 — Stand by for delivery confirmation
- User will send the Sita Air delivery email
- User will deliver credentials via secure channel
- User will monitor for response
- If user reports any login failure, be ready to:
  - Diagnose via Firebase Auth state
  - Check password hash mismatch by testing signInWithPassword
  - Reset password via Admin SDK if needed
  - Report findings immediately

### Task 5 — Prepare rollback plan (in case of critical issue)
- If a critical issue arises during delivery, document the rollback steps:
  1. Verify backups are current (Supabase)
  2. Restore path: identify the most recent valid backup
  3. Communication template for the customer
- Do NOT execute rollback unless user explicitly requests. Report the plan only.

## Afternoon — Delivery Confirmation

### Task 6 — Monitor and report
- If user reports customer confirmation, log it:
  - Date/time of delivery email
  - Customer response (if any)
  - Any issues raised
  - Resolution (if any)
- Commit the delivery note to docs/status.md or a new file docs/delivery-log.md

### Task 7 — Prepare Phase 1 kickoff (do NOT start)
- Review ROADMAP.md Phase 1 items
- Prepare a proposed sequence for Phase 1 work:
  - 1A — Audit log table + writes
  - 1B — Tenant context middleware
  - 1C — Scoped query builder
  - 1D — Two-flag purge rule
  - 1E — Postgres RLS
  - + — Nav overhaul
  - + — tenant.data.users array removal
  - + — CI pipeline
  - + — Setup token refactor
  - + — Welcome email integration
- Report the proposed sequence and estimated timeline
- Await user approval before starting any Phase 1 work

## Constraints

- Do NOT start Phase 1 work today. Delivery first.
- Do NOT modify production data without user approval.
- Do NOT share credentials or passwords.
- Do NOT push any code changes today unless fixing a critical delivery blocker.
- Report at each task completion; await next instruction.
- If any task fails, stop and report; do not work around silently.

## Delivery Log (fill in as the day progresses)

```
  Delivery email sent:          [time]
  Credentials delivered via:    [channel]
  Customer response received:   [time / none yet]
  Issues raised:                [list / none]
  Issues resolved:              [list / none]
  Delivery accepted:            [yes/no/pending]
```