# OVERDUE_MODEL_VERIFICATION — Overdue across Hazards and CAPs

Companion to MODULE_B_CONTRACT.md (verified before Chunk 2c). Read-only
verification of how "overdue" is modeled today, distinguishing **hazard
overdue** (CAAN §2.2 H=24h / M=7d / L=15d), **CAP overdue** (monitoring
status), and **CAP escalation** (AE sign-off flow). No files were modified.

## 1. EXECUTIVE SUMMARY

**Hazard overdue — NOT MODELED.** The `hazards` table has no `overdue` column
(`backend/app/db/db_models.py:64-139`; verified live columns
`DB_VERIFICATION.md:79-89`), no worker scans hazards against the §2.2
24h/7d/15d timeline, and nothing derives overdue from `priority_date` or
`follow_up_date`. The only hazard-overdue code is `verification_service.py:123`,
which **fires** (an API caller can submit a verification outcome `Overdue`) but
is a **silent no-op**: `pg.update` (`pg.py:110-147`) drops the unknown `overdue`
key via `pg._split_doc` (`pg.py:250-284`) because no such column (nor a JSONB
`data` bag) exists on `Hazard` — so only `updated_at` is written. Live code,
broken effect.

**CAP overdue — modeled as a persisted STATUS.** A CAP becomes overdue by having
its `status` (Text column, `db_models.py:400`) set to the enum value `"Overdue"`
(`mmodels` `backend/app/models/can_cap.py:55`). Set automatically by the daily
tenant scan `check_tenant_overdue` (`escalation_service.py:88-114`, wired at
`routes/admin.py:808-822`) when `target_completion_date` has passed and status is
not `Completed`/`Overdue`. It is a monitoring/follow-up state, NOT an escalation.
The "days overdue" figure is **computed on the fly** for reminder emails only
(`email_service.days_overdue` `email_service.py:364`, `:623-628`) — never
stored, never shown in the register. The register shows `Overdue` as a status
badge (`public/can_cap/caps.html:85,178-183`); stats bucket it
(`can_cap_service.py:1088`).

**CAP escalation — separate from overdue.** There is no literal "EIP" state
anywhere (grep `EIP` → 0 hits). Escalation to the Accountable Executive is a
boolean + sign-off block: `escalated_to_ae`/`escalated_by`/`escalated_at`/
`escalation_reason` + `ae_signature`/`ae_signed_at`/`ae_review_date`
(`db_models.py:437-444`), set manually by a reviewer (`can_cap_service.py`
`review_cap` `:957-963`, `:1000-1009`). It is independent of CAP status; an
escalated CAP keeps its status (`In Progress`, `Overdue`, …). The automated scan
only escalates **CANs** (status → `Escalated`), never CAPs. This matches the
platform owner: overdue CAPs are flagged for monitoring, not escalated.

## 2. TASK FINDINGS

### TASK 1 — Stray overdue write at verification_service.py:123
a. **Code** (`verification_service.py:122-124`):
```python
        elif outcome == "Overdue":
            pg.update(Hazard, "id", haz_uuid, {"overdue": True, "updated_at": now})
            logger.warning(f"Hazard {hazard_id} marked overdue (escalation)")
```
b. **Trigger/chain:** API caller submits outcome `"Overdue"` — safety-manager
route `POST /hazards/{hazard_id}/verifications` (`routes/verification.py:22,26`)
→ `create_verification` (`verification_service.py:58`) → `pg.upsert` (verification
rows, `:95`) → branch `:122-124`. Enum reality: `VerificationOutcome.OVERDUE`
(`models/verification.py:11`), so the branch is reachable.
c. **Target model/column:** keyed on the Hazard row UUID (`_resolve_hazard`,
`:24-28`); `overdue` is not a `Hazard` column (`db_models.py:64-139`) and
`Hazard` has no JSONB `data` column (only `sram_data` `:108`), so `_split_doc`
discards the key silently.
d. **Live DB:** `overdue` absent from verified live `hazards` columns
(`DB_VERIFICATION.md:79-89`); no migration/`*.sql` creates it.
e. **Verdict:** LIVE code path, NO-OP effect — only `updated_at` written; the
warning log misstates the result. Intended behavior (flag the hazard overdue on
an `Overdue` verification outcome) is unimplemented.

### TASK 2 — CAP overdue modeling
a. **Columns** (`db_models.py:378-472`): `target_completion_date` (DateTime,
NOT NULL, `:393-395`), `status` (Text, NOT NULL, `:400`), `submitted_at` `:399`,
`reviewed_at` `:403`, `revision_deadline` `:405-407`, `closed_by`/`closed_at`
`:454-455`; escalation block `:437-444`. **No `overdue`/`overdue_at`/`due_date`/
`deadline` column** (the Firestore-era `due_date` string lives only in the dead
worker's comment, `workers/escalation_worker.py:45-46`).
b. **Overdue = a status value.** `CAPStatus` enum (`models/can_cap.py:50-56`):
`In Progress`, `Under Review`, `Completed`, `Revision Required`, `Overdue`.
Stored as text. A reviewer can also set it manually (`CAPReview.status:
CAPStatus`, `models/can_cap.py:277-280`).
c. **Setter (automatic):** daily scan `check_tenant_overdue`
(`escalation_service.py:45-122`): CAP branch `:88-114` — status not in
`CAP_TERMINAL_STATUSES={"Completed","Overdue"}` (`:31`) and
`target_completion_date` passed → persist `status="Overdue"` (`:97`) + audit
`CAP_OVERDUE` (`:98-109`). Wired: `POST /api/v1/admin/tasks/check-overdue`
(`routes/admin.py:808-822`). Live in prod per overnight audit actions
(`PASSWORD_RESET_BUG_INVESTIGATION.md:128`).
d. **Days overdue computed on the fly** for the reminder-email job only:
`POST /api/v1/jobs/check-overdue-caps` (`routes/scheduled_jobs.py:36-47`) →
`email_service.py:623-628` via `days_overdue` (`:364`). Not stored; not in list.
e. **Dead sibling:** `workers/escalation_worker.py:14 check_overdue_cans`
(Firestore-oriented; writes `overdue_at` `:73`, another non-column) is never
imported anywhere — dead code.

### TASK 3 — CAP escalation vs overdue
a. **Manual, flag-based:** `review_cap` (`can_cap_service.py:917-1016`)
copies `escalated_to_ae`/`escalated_by`/`escalation_reason` from payload
(`:957-959`); stamps `escalated_at` when escalated (`:1000-1001`); AE sign-off
writes `ae_signature`/`ae_signed_at`/`ae_review_date` from
`ae_review_interval_days` (`:1005-1009`). Payload fields `CAPFormFields`
(`models/can_cap.py:149-159`); endpoint `routes/can_cap.py:296`.
b. **No dependency on overdue.** Nothing in the AE flow checks CAP status; an
escalated CAP keeps its status, and an `Overdue` CAP is never auto-escalated
(scan CAP branch only flips status).
c. **"EIP" state:** none. Automated `Escalated` status is CAN-only
(`CANStatus.ESCALATED`, `models/can_cap.py:47`; scan `escalation_service.py:68-86`).

### TASK 4 — CAN-CAP register view
a. **Lists return raw `status`:** CAP `GET /api/v1/caps` (`routes/can_cap.py:104-138`)
→ `list_all_caps` (`can_cap_service.py:806-833`, status filter `:832-833`);
CAN `GET /api/v1/cans` (`routes/can_cap.py:48-89`).
b. **`Overdue` is displayed as a status:** `public/can_cap/caps.html` Status
column `:85`, badge `c.status` `:178-183`, filter fed by `stats.caps.by_status`
`:202-205`; `cap_review.html:427` treats `Completed`/`Revision Required`/`Overdue`
as reviewed states. Stats: `get_cap_stats` incl. `Overdue` bucket
(`can_cap_service.py:1088-1094`); surfaced at `GET /api/v1/stats`
(`routes/can_cap.py:92-101`).
c. **No days-overdue column** in any register/list view; days-overdue exists
only inside the email reminder (`email_service.py:364,628`).
d. **Register pages:** `public/can_cap/cans.html`, `public/can_cap/caps.html`,
`public/can_cap/can_detail.html`, `public/can_cap/cap_review.html`.

### TASK 5 — Hazard overdue modeling
a. **Columns:** `priority_date` `db_models.py:111`, `status_date` `:112`,
`follow_up_date` `:113`, `srm_date` `:103`, `closed_at` `:114` — no overdue/
deadline column (`db_models.py:64-139`).
b. **Not computed:** §2.2 H=24h/M=7d/L=15d logic absent from the codebase.
`priority_date` is only stamped on create/priority-change (`hazard_service.py:356,
461-465`); `follow_up_date` is client/seeder-set (`:358`).
c. **No scheduler/worker for hazards:** daily tasks are CAP/CAN-scoped only —
`/api/v1/admin/tasks/check-overdue` (CAN→Escalated, CAP→Overdue) and
`/api/v1/jobs/check-overdue-caps` (CAP emails) (`routes/admin.py:808`,
`scheduled_jobs.py:36`; scope `DISCOVERY_REPORT.md:72`). The SMS tenant report's
`overdue_capas` derives from CAP status at read time (`tenant_scheduler.py:180,
205`), not hazards. Sole hazard-overdue code = the Task 1 no-op.

### TASK 6 — Seed/demo behavior
No seed sets an `Overdue` status/flag on hazards or CAPs:
- `seed/runner.py:383` — Module A survey-response comment ("One finding
  overdue"); textual, not a state.
- `seeders/reports/report_seeder.py:85-89` — sample occurrence-report text
  ("inspection overdue"); AD-compliance scenario, not a state.
- `seed/hazard_can.py:739-743` — seeded CANs may carry `escalated_to_ae=True`
  (AE-escalation flag, unrelated to overdue).

## 3. TASK 7 — RECONCILIATION

| Concept | Storage | Computation | Trigger | Display |
|---|---|---|---|---|
| **Hazard overdue** | NOT modeled; only `priority_date`/`follow_up_date`/`status` (`db_models.py:110-114`) | NOT computed (§2.2 absent) | Manual-only: verification outcome `"Overdue"` (`verification_service.py:122-124`) — live, no-op | None (no indicator in hazard list/register) |
| **CAP overdue** | Persisted status `"Overdue"` in `caps.status` (Text `db_models.py:400`; enum `models/can_cap.py:55`) | `target_completion_date < now` (`escalation_service.py:88-114`); `days_overdue` for emails (`email_service.py:364`) | Daily scan `POST /admin/tasks/check-overdue` (`routes/admin.py:808-822`), or manual review | Status badge + filter + stats (`caps.html:85,178-183,202-205`; `can_cap_service.py:1088`); days-overdue NOT displayed |
| **CAP escalation** | Flag+sign-off block (`db_models.py:437-444`) | None (no deadline math) | Manual `review_cap` (`can_cap_service.py:957-963,1000-1009`) | CAP detail/review UI fields; no dedicated status |
| **CAN escalation** | Status `"Escalated"` (`models/can_cap.py:47`) | `target_completion_date < now` (`escalation_service.py:68-86`) | Same daily scan (CAN branch) | CAN register status column |

**Cross-cutting facts**
- `pg._split_doc` (`pg.py:250-284`) silently discards write keys not present as
  columns — the root cause of the Task 1 no-op (and it would also discard a
  would-be `overdue_at` on CAPs; only models with a JSONB `data` column absorb
  extras — neither `Hazard` nor `Cap` has one).
- Overdue ≠ escalation, confirmed in code for all four concepts; matches the
  platform owner's description of Module B (§2.2 follow-up) vs CAP overdue
  (monitoring) vs CAP escalation (AE sign-off, EIP-like but no "EIP" state).

## 4. RECOMMENDED CLARIFICATIONS FOR CHUNK 2c SCHEMA NOTES
1. **Distinguish the three concepts in the contract** (they are separate in
   code and should stay separate): hazard overdue = §2.2 24h/7d/15d timeline;
   CAP overdue = monitoring status `"Overdue"`; CAP escalation = `escalated_to_ae`
   flag + AE sign-off block. Do not merge §2.5 CAP deadlines with the AE flow.
2. **Hazard overdue is unmodeled today — Chunk 2c must decide its storage.**
   Recommended (aligned with §2.2 and SN1/SN3): add a real hazard-overdue state
   (e.g. derived from `priority_date` + tier at read time, or persisted
   `overdue_since`), NOT the current no-op.
3. **Resolve the `verification_service.py:123` no-op in the contract scope:**
   either remove the branch or implement it against the new hazard-overdue state.
   It currently writes a non-existent column (guaranteed silent drop).
4. **Keep CAP `"Overdue"` as a monitoring status**, not an escalation; a
   register "days overdue" column is optional display sugar, currently absent.
5. **Keep CAP AE escalation orthogonal to status** and separate from Module B's
   §2.3.3 risk-acceptance signature (two different acceptance mechanisms).

## 5. UNKNOWN / OPEN ITEMS
- Whether CAP `"Overdue"` should be terminal (it currently is, per
  `CAP_TERMINAL_STATUSES` `escalation_service.py:31`) or clearable by review.
- Whether the owner wants a hazard overdue indicator in the Module B hazard
  list/register (none exists today) and whether overdue should auto-escalate.
- Whether the `"Overdue"` verification outcome should instead mark the related
  CAP overdue rather than the hazard.
- Whether to keep `workers/escalation_worker.py` (dead, legacy Firestore) — code
  removal or rewiring.
- Whether to persist `days_overdue` vs keeping it computed in the email job.