# Phase F — Firestore removal cleanup tracker

Target: **2026-10-31**. All items below are intentional, documented deferrals
from the A-series Firestore-removal work. Nothing here is blocking; each item
is a candidate for `Phase F` once its pre-conditions are met.

See `test-results/known-failures.md` for resolved items and the live failure
baseline.

---

## 1. regulator_dashboard + aggregation_service rewiring — DONE

- ✅ `2026-09-12` (A7): `aggregation_service.py` reads Postgres directly
  (`pg.fetch_all` on `hazards` + `surveys`, `Tenant` discovery, `demo_scope()`
  filter, `tenant_uuid()` mapping). No `FirestoreRepository`/`repository.query`
  calls remain.
- ✅ `routes/regulator_dashboard.py`: dropped `get_repository()` + the
  `AbstractRepository = Depends(get_repository)` injection on all 7 endpoints;
  handlers construct `AggregationService()` directly. Response shapes
  unchanged.
- ✅ Covered by `tests/test_regulator_dashboard.py` (10 tests). Full suite
  810 passed / 0 failed (both A8 runs).

## 2. FirestoreRepository + abstract_repository — DELETED

- ✅ `2026-09-12` (A7): every data method promoted to `raise NotImplementedError`.
- ✅ `2026-09-12` (A8): `app/db/firestore_repository.py` and
  `app/db/abstract_repository.py` deleted (zero importers after hazard_service
  compat removal). Class + module fully gone.

## 3. app/database.py get_db — DELETED

- ✅ `2026-09-12` (A8): `backend/app/database.py` deleted outright (zero
  importers confirmed A4 + re-verified A8).

## 4. firebase.py stubs — VERIFIED RAISING; mirror branches are residual

- ✅ All four firebase data helpers (`get_db`, `get_tenant_collection`,
  `get_cross_tenant_collection`, `get_tenant_metadata`) already raise
  `NotImplementedError` (A1 pattern) — verified A8, no warn-once bodies remain.
- Residual live importers (keep stubs, do NOT promote further — per A8): the
  best-effort FS-mirror branches that catch the raise and degrade. These are
  Phase F "delete outright" candidates (not stub conversions):
  - `app.firebase.get_db` importers (17 sites): routes/admin.py,
    routes/dashboard.py (`load_cap_overlays`), routes/demo.py, routes/feedback.py,
    routes/reporting.py, repositories/audit_repo.py, services/admin_data_service.py
    (`_purge_firestore_or_none`), services/ai_copilot.py, services/audit_service.py,
    services/dlq_service.py, services/groq_copilot.py, services/production_seed.py,
    services/risk_matrix.py, services/tenant_registration.py (`_registration_db`),
    services/tenant_credentials.py, middleware/rate_limit.py,
    workers/tenant_scheduler.py (shim).
  - `app.firebase.get_tenant_collection` importers (2 sites): routes/reporting.py,
    services/risk_matrix.py.
  - `app.firebase.get_cross_tenant_collection` / `get_tenant_metadata`: ZERO live
    importers (only pg_query.py defines its own same-named builders).

## 5. Dead-code deletion — DONE

- ✅ `2026-09-12` (A8): `services/cap_service.py` (CAPService),
  `services/can_service.py` (CANService), `services/hazard_report_service.py`
  (HazardReportService), `services/maturity_scoring_service.py`
  (MaturityScoringService) all deleted. Zero importers re-verified immediately
  before deletion.

## 6. hazard_service FirestoreRepository compat default — REMOVED

- ✅ `2026-09-12` (A8): the `FirestoreRepository()` compat construction
  (formerly lines 234–235) and the try/except import block removed from
  `services/hazard_service.py` (`repository` injection param retained for
  backward compatibility, PG is used directly; class now deleted anyway).

## 7. New A8 candidates (cosmetic, non-blocking)

- `core/metrics.py` `_firestore_latency` gauge + `record_firestore_latency`
  and the `_perf_timed("firestore")` labels in `routes/dashboard.py` are inert
  metric instrumentation (nothing feeds them meaningfully). No Firestore
  dependency — optional cosmetic rename/removal at Phase F.
- Verify dependency list no longer pins `google-cloud-firestore` (import count
  across app is zero as of A8).