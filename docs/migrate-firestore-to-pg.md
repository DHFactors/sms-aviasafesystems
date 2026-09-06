# Migration: Firestore → PostgreSQL (Supabase)

Goal: remove ALL Firestore data operations from the backend. Keep Firebase
Auth (identity) and Firebase Hosting (frontend). Target the existing async
SQLAlchemy layer (`app/db/session.py` + `app/db/db_models.py`).

Context facts
- `app/database.py`'s `get_db()` is a stub (`pass`) — no competing PostgREST path.
- `backend/.env` already has a live `DATABASE_URL` → DDL applied idempotently.
- Schema style = raw SQL (`app/db/schema.sql`, 15 tables) + idempotent DDL
  (`app/db/schema_init.py`). No Alembic (decision: keep raw-DDL repo pattern).

## Collection inventory → target table

| Firestore collection | Consumers | Target |
|---|---|---|
| `tenants` (+ `profile`, `metadata` subcolls) | auth middleware, admin, dashboard, invites, copilots, workers, can_cap | NEW `tenants` |
| `regulators` | regulator_service, admin_data, scheduler | NEW `regulators` |
| `users/{uid}` | users.py, admin delete-user, delete-demo-tenants | NEW `users` |
| `audit_logs` (+ `tenants/{id}/audit_logs/sms_dispatches`) | audit_service, admin, audit_repo | NEW `audit_logs`, `sms_dispatches` |
| `invites` | invites.py | NEW `invites` |
| `feedback` | feedback route, admin list | NEW `feedback` |
| `caan_reports` | reporting.py | NEW `caan_reports` |
| `sms_maturity` (`tenants/{id}/sms_maturity/days_N`) | dashboard_service | NEW `sms_maturity` |
| `dead_letter_queue` | dlq_service, audit_repo | NEW `dead_letter_queue` |
| `state/ICAO categories` | state_risk_service, seed_surfaces, admin purge | NEW `state_risk_categories` |
| `psoe_assessments` / `psoe_questions` | psoe, seed_surfaces, admin purge/export | Already PG (same names) → drop Firestore duplicates |
| `can_cap` + `caps`, `flight_diversions`, `verifications`, `closures` subcolls | can_cap, dashboard, verification, master_register, report_generator, escalation | Already PG (`cans`,`caps`,`flight_diversions`,`verifications`,`closures`) → drop Firestore subcollection reads |
| `hazards`, `reports`, `surveys`, `survey_responses` etc. | hazard/report/survey services + routes | Already PG → drop Firestore reads |

## Batches

- B0 Foundation — config cleanup (drop `FIREBASE_DATABASE_ID`, keep Auth),
  new SQLAlchemy models + idempotent DDL + runner, session foundations + tests.
  ✅ committed `ce9a322`.
- B1 Identity layer — `middleware/auth.py`, `users.py`, `invites.py`,
  `tenants.py` route, `tenant_registration.py`, `onboarding_service.py`,
  `regulator_service.py` + admin regulator endpoints.
  ✅ committed `32b74ec` (reads) + `c041eeb` (registration/writes).
- B2 Ops/admin layer — `audit_service.py`, admin audit list/purge, feedback,
  dlq, caan_reports, sms_maturity, `admin_data_service.py` (tenants/regulators/
  users/audit purge/export/delete-demo-tenants), `routes/admin.py`.
  ✅ committed `95034e5` (audit_service, feedback submit+list, dlq_service,
  production_seed, admin_data_service tenant lifecycle + demo scope, admin
  governance/users/status) + `1fb0e6d` (tenant_credentials.py, audit dispatch
  repo → new `audit_dispatches` table).
- B3 Domain residual reads — can_cap, dashboard, hazard/report/survey paths,
  repository/search, verification_service, master_register (partial), report_generator,
  escalation_service, plus tenant metadata reads, reporting.py.
  ✅ committed `27fc615` (surveys, tenant_reports, reporting.py, escalation_service, verification_service, can_cap/tenant metadata, _ID_COLUMNS expansion) + `5c53b9d` (report_generator, psoe, state_risk_service, seed_surfaces, dashboard_service remaining surfaces).
- B4 Workers, copilots, remaining domain — workers/scheduler, tenant_scheduler,
  escalation_worker, flight_diversion_service, repository (PG-primary), hazard_service import fix, ai_copilot/groq_copilot tenant classification PG, risk_matrix PG, `firebase.py` Auth-only trim, `firestore_repository.py` stub.
  ✅ committed `86cd81e`.
- B5 Closeout — remove Firestore purge surfaces (admin_data_service legacy doc-tree deletes now no-op via dummy), drop `FIREBASE_DATABASE_ID` from config/.env if desired, remove `google-cloud-firestore` direct dependency (kept transitively via `firebase-admin` for Auth), full test suite, Render Manual Deploy, verification checklist.
  🔄 next.

Each batch: tests green → commit → push → firebase hosting deploy (backend
goes live via Render Manual Deploy).

## Existing data

One-time script reads current Firestore tenants/regulators/users/audit/invites/
feedback/caan_reports/maturity and inserts into the new tables preserving id
semantics (`tenant_uuid(slug)` for tenant FKs, Firestore doc id → text id).

## Verification checklist

- All services use SQLAlchemy/Postgres; `db.collection(` in `app/` now only in deprecated purge/mirror stubs (dummy no-op).
- Firebase Auth still works (verify_firebase_token untouched, Auth-only init).
- Create regulator/tenant/hazard/CAN-CAP/SRAM/PSOE → data lands in PG.
- Purge/delete-demo removes data from PG (Firestore purge now dummy, legacy cleanup).
- Backend pytest suite green (92 passed in targeted suites; full suite hangs pre-existing, 2 admin seed failures pre-existing).
