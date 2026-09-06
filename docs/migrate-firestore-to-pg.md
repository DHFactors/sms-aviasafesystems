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
- B1 Identity layer — `middleware/auth.py`, `users.py`, `invites.py`,
  `tenants.py` route, `tenant_registration.py`, `onboarding_service.py`,
  `regulator_service.py` + admin regulator endpoints.
- B2 Ops/admin layer — `audit_service.py`, admin audit list/purge, feedback,
  dlq, caan_reports, sms_maturity, `admin_data_service.py` (tenants/regulators/
  users/audit purge/export/delete-demo-tenants), `routes/admin.py`.
- B3 Domain residual reads — can_cap, dashboard, hazard/report/survey paths,
  repository/search, verification_service, master_register, report_generator,
  escalation_service (point at existing PG, drop Firestore subcollections).
- B4 Workers, copilots, legacy — workers/scheduler, tenant_scheduler,
  escalation_worker, ai_copilot/groq_copilot guard, psoe/state_risk/
  seed_surfaces reference data, `firestore_repository.py` removal,
  `firebase.py` trim to Auth-only, `main.py`, legacy v1 routes
  (`api/v1/tenant_reports.py`, `routes/reporting.py`).
- B5 Migration + closeout — one-time Firestore→PG data migration script,
  remove google-cloud-firestore dependencies from requirements, full test
  suite, deploy, verification checklist.

Each batch: tests green → commit → push → firebase hosting deploy (backend
goes live via Render Manual Deploy).

## Existing data

One-time script reads current Firestore tenants/regulators/users/audit/invites/
feedback/caan_reports/maturity and inserts into the new tables preserving id
semantics (`tenant_uuid(slug)` for tenant FKs, Firestore doc id → text id).

## Verification checklist

- All services use SQLAlchemy/Postgres; zero `db.collection(` in `app/`.
- Firebase Auth still works (verify_firebase_token untouched).
- Create regulator/tenant/hazard/CAN-CAP/SRAM/PSOE → data lands in PG.
- Purge/delete-demo removes data from PG.
- Full backend pytest suite green (excluding known pre-existing failures).