# FIRST_ACTION_KPI_VERIFICATION — Timestamps for "registration → first action"

Read-only verification for the AE dashboard KPI "Average days between hazard
registration and first action" + "count of hazards still Received". Input for
the Dashboard Contract. No files were modified. All cites are
`backend/app/...` unless prefixed.

## 1. EXECUTIVE SUMMARY

- **Registration** = `hazards.created_at` (`db_models.py:121-123`, DT tz, NOT
  NULL, default utcnow). No `identified_at`/`confirmed_at` column exists.
- **Prioritization** = `hazards.priority_date` (`db_models.py:111`, nullable) —
  stamped at creation, but **re-stamped on every priority change**
  (`hazard_service.py:461-465`); it is the *last-changed* date, not the first.
  Priority (`H/M/L`, default `M`) and `priority_date` are set in the same
  create write (`hazard_service.py:308,356`), so registration ≈ prioritization
  for most hazards.
- **SRM started** = only `hazards.srm_date` (`db_models.py:103`) exists, and it
  stamps SRM **conducted/saved** (`routes/hazards.py:326-328`), not "started".
  No workspace-open/first-draft timestamp exists.
- **First CAN issued** = `cans.issued_at` (`db_models.py:299`), stamped at issue
  (`can_cap_service.py:449` `or now`); reliable via `MIN(issued_at)` per hazard
  (`cans.hazard_id` FK `db_models.py:289-291`).
- Verdict: `created_at` and `issued_at` fully support the KPI; `priority_date`
  and `srm_date` exist but conflate "last/complete" with "first". No metric
  endpoint exists today.

## 2. TASK FINDINGS

### Task 1 — Registration timestamp
`hazards.created_at` — `DateTime(timezone=True)`, **NOT NULL**, default
`datetime.utcnow` (`db_models.py:121-123`); written as
`created_at=payload.get("created_at") or now` (`hazard_service.py:364`);
indexed `ix_hazards_tenant_created` (`db_models.py:137`). No
`identified_at`/`confirmed_at`/`registration_date` anywhere (grep → 0 hits).
Caveat: overridable from payload (import back-dates).
### Task 2 — Prioritization timestamp
`hazards.priority_date` (`db_models.py:111`) — nullable. Stamped at creation
always: `priority_date=payload.get("priority_date") or now`
(`hazard_service.py:356`). Re-stamped only when priority changes:
`new_priority != row.priority → payload["priority_date"]=now`
(`hazard_service.py:461-465`). → Reflects the **current** priority's date;
first-prioritization date is lost for re-prioritized hazards.
### Task 3 — SRM started timestamp
- `hazards.srm_date` (`db_models.py:103`) — set on Bow-Tie/SRAM **save**:
  `srm_conducted=True, srm_date=now, srm_status="Conducted"`
  (`routes/hazards.py:326-328`; `PUT /{hazard_id}/sram/save`). "Conducted", not
  started.
- `hazards.sram_data` (JSONB `db_models.py:108`) — saved payload (same event).
- `hazards.srm_flag` (Bool `db_models.py:97`) — advisory template flag
  ("requires SRM", `icao_templates.py`), set at create (`hazard_service.py:339`);
  no timestamp.
- Legacy/alt anchors: `risk_register.srm_date` NOT NULL (`db_models.py:1392`);
  `sram_risk_register.created_at` (`db_models.py:1458-1460`) — note its
  `hazard_id` is TEXT, not FK (`db_models.py:1441`).
- `POST /{hazard_id}/sram/calculate` does not persist (`routes/hazards.py:219-220`).
- **No "SRM started" event/column exists.** Closest signal = `srm_date`.
### Task 4 — First CAN issued timestamp
`cans.issued_at` (`db_models.py:299`, nullable) stamped on issuance
(`can_cap_service.py:449`); `cans.created_at` (`db_models.py:336-338`) equals
the same moment (`can_cap_service.py:451`). Query earliest CAN:
`SELECT MIN(issued_at) FROM cans WHERE hazard_id=<uuid> [AND tenant_id=…]
[AND NOT is_demo]`. No such endpoint exists yet.
### Task 5 — Hazard status enum
- Enum `HazardStatus` (`models/hazard.py:7-13`): **Open, Processing, Under
  Review, Pending Closure, Closed, Reopened**.
- DB: `hazards.status` = free Text, NOT NULL, **no check constraint**
  (`db_models.py:110`; no status check in `__table_args__` `:128-139`); default
  `"Open"` at create (`hazard_service.py:311`); `update_status` accepts any
  string (`hazard_service.py:517`; `routes/hazards.py:153-156`).
- Demo pool matches enum (`seed/hazard_can.py:65-68`); stats buckets
  Open/Processing/Under Review/Closed/Reopened (`hazard_service.py:559`).
- v2 ICAO tables use other strings (`"under_assessment"`
  `hazard_service.py:608`, `"pending_implementation"` `:774,783`) — NOT on
  `hazards`.
- Mapping: **Received = Open**; **Processed = Processing / Under Review /
  Pending Closure / Reopened**; **Closed = Closed**. Discrepancy: no literal
  "Received"; unknown/legacy strings (unconstrained) are unmapped — default to
  Processed.
### Task 6 — Existing KPI/metric endpoints (routes/dashboard.py)
- `GET /dashboard/overview` → `data.kpis.avg_closure_days` for **reports**
  (closed: `(updated_at-created_at)/86400`) (`dashboard.py:64-83`;
  `services/metrics_service.py:51-65,81`) — closest existing "days" KPI shape.
- `GET /dashboard/hazards` → hazard **frequency from MOR/survey reports**, not
  the hazards table (`dashboard.py:149-156`; `metrics_service.py:134`).
- No response-time/latency/first-action metric exists. `spi_service.py:219,437`
  reads `created_at`/`closed_at` only.
- Status breakdowns available: `GET /hazards/stats` (`routes/hazards.py:109-114`
  → `hazard_service.py:559-569`) and `GET /can_cap/stats`
  (`routes/can_cap.py:92-101`). Envelope: `{"status","timestamp","data"}`
  (`dashboard.py:26-31`).
### Task 7 — Missing timestamps
✔ `created_at`, ✔ `issued_at` available. ✖ no first-priority date (re-stamp),
✖ no SRM-start (only conducted). Compute today with the four existing
columns; exactness needs schema additions (see §5).
## 3. MAPPING — first-action candidates vs timestamps

| Candidate | Source column | Stamps on | First-action usable |
|---|---|---|---|
| Registration | `hazards.created_at` (`db_models.py:121-123`) | create | ✔ |
| Prioritization set | `hazards.priority_date` (`db_models.py:111`) | create + every change (`hazard_service.py:356,461-465`) | ⚠ last-change, not first |
| SRM started | `hazards.srm_date` (`db_models.py:103`) | SRAM save "Conducted" (`routes/hazards.py:326-328`) | ⚠ conducted, not started |
| First CAN issued | `cans.issued_at` (`db_models.py:299`) | CAN issue (`can_cap_service.py:449`) | ✔ MIN per hazard |
| CAN row created | `cans.created_at` (`db_models.py:336-338`) | CAN issue (`can_cap_service.py:451`) | ✔ same event |
| v2 assessment | `hazard_assessments.assessed_at` (`db_models.py:1175`) | v2 save | ✖ non-`hazards` table |
| legacy SRM | `risk_register.srm_date` (`db_models.py:1392`) | legacy save | ✖ legacy reference |

## 4. RECOMMENDED COMPUTATION

Per non-demo hazard:
```
first_action = LEAST(
      COALESCE(h.priority_date, h.created_at),          -- prioritization set
      COALESCE(h.srm_date,          '+infinity'),        -- SRM conducted (≈ started)
      COALESCE(MIN(c.issued_at),    '+infinity'))       -- cans c.hazard_id = h.id
days = DATE(first_action) - DATE(h.created_at)          -- clamp negatives to 0
avg_kpi  = round(AVG(days),1)   -- hazards WITH a first_action
received = COUNT(*) WHERE h.status='Open'               -- still Received
```
Normal path has `priority_date == created_at`, so the KPI floor ≈ 0 days;
`is_demo=False` filter; guard back-dated imports.

## 5. GAPS — schema additions for exactness
1. **True first-priority date**: `priority_date` is overwritten on change
   (`hazard_service.py:465`) — need `first_priority_at` or a priority audit log.
2. **True SRM start**: add `hazards.sram_started_at` (on a Begin-assessment
   event or first draft save before `srm_status="Conducted"`), or derive from
   the Open→Processing/Under-Review `status_date` transition (lossy).
3. **No FK** between `hazards` and `sram_risk_register` (`hazard_id` = TEXT,
   `db_models.py:1441`) — join by reference string only; not needed for the KPI.
4. Metric must be built (nothing reusable in `dashboard.py`/`metrics_service.py`).

## 6. NOTES FOR THE DASHBOARD CONTRACT
- Envelope: `{"status","timestamp","data"}` (`dashboard.py:26-31`); null-when-
  empty like `avg_closure_days` (`metrics_service.py:81`).
- Shape: `data.kpis.avg_days_registration_to_first_action`, `.hazards_received`,
  `.hazards_total`, `.received_rate`; `days` window param as in existing
  endpoints (`dashboard.py:66,116`). `Received` reuses `GET /hazards/stats`
  `by_status` (`Open`).

## 7. UNKNOWN — REQUIRE HUMAN INPUT
1. Is approximating "SRM started" with `srm_date` (conducted) acceptable, or add
   `sram_started_at`?
2. Exclude hazards whose priority changed (re-stamped `priority_date`), or
   accept the noise?
3. Which statuses count as "Received" — literal `Open` only, or also unmapped
   legacy strings (status is free text)?
4. Do never-actioned hazards belong in the average, or only in `received_count`?
5. Exclude demo hazards (`is_demo`) from the AE KPI (recommended)?