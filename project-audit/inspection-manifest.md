# Inspection Manifest — seed.py and Active Schemas (sms-db-beta reset)

**Date:** 2026-08-24  
**Branch:** `feature/beta-reset-seed`  
**Script under test:** `backend/scripts/setup_two_tenants_beta.py` (dry-run)  
**Source files inspected:** `backend/seed/*.py`, `backend/scripts/seed.py` (via `backend/seed/runner.py`), `backend/app/firebase.py`, `backend/app/models/*.py`, `backend/app/services/*.py`, `firestore/firestore.rules`, `firestore.indexes.json`

## 1. Collections and subcollections written by seed.py

| Collection / subcollection | Written by | File:line | Document ID / key | Tenant path example | Top-level? |
|---|---|---|---|---|---|
| `tenants` | `seed/operators.py:131` `db.collection(tenants).document(tid).set` | `operators.py:131`, `production_seed.py:210` | `tenant_id` slug (deterministic, e.g. `fishtail-air`, `vnkt-airport`) | `tenants/fishtail-air` | Top-level |
| `tenants/{tid}/metadata/info` | `seed/operators.py:69` `tenant_ref.collection(metadata).document(info)` | `operators.py:69`, `app/firebase.py:74` | `info` (FIREBASE_DOCUMENT_INFO) | `tenants/fishtail-air/metadata/info` | Sub |
| `tenants/{tid}/metadata/profile` | `seed/tenant_profiles.py:42` `tenants/{tid}/profile/{PROFILE_DOC_ID}` | `tenant_profiles.py:42` | `profile` | `tenants/fishtail-air/metadata/profile` (legacy) / `tenants/{tid}/profile` | Sub |
| `tenants/{tid}/metadata/risk_matrix` | `seed/operators.py:74` `risk_matrix` | `operators.py:74` | `risk_matrix` | `tenants/fishtail-air/metadata/risk_matrix` | Sub |
| `tenants/{tid}/reports` | `seed/reports.py:319` `tenant_ref.collection(reports).add` | `reports.py:319`, `app/services/report_service.py` | Auto-ID, `report_type` field | `tenants/fishtail-air/reports/{reportId}` | Sub |
| `tenants/{tid}/hazards` | `seed/hazard_can.py:814` `tenant_ref.collection("hazards").document(doc_id)` | `hazard_can.py:814`, `app/services/hazard_service.py:36` | `haz_<tid>_<hash>` deterministic | `tenants/fishtail-air/hazards/haz_...` | Sub |
| `tenants/{tid}/can_cap` | `seed/hazard_can.py:857` `tenant_ref.collection("can_cap").document(can_doc_id)` | `hazard_can.py:857`, `app/services/can_cap_service.py:37` | `can_<tid>_...` deterministic | `tenants/fishtail-air/can_cap/can_...` | Sub |
| `tenants/{tid}/can_cap/{can_id}/caps` | `seed/hazard_can.py:896` `can_ref.collection("caps").document(cap_doc_id)` | `hazard_can.py:896`, `app/services/can_cap_service.py:40` | `cap_<tid>_...` deterministic | `tenants/fishtail-air/can_cap/{can}/caps/{cap}` | Nested |
| `tenants/{tid}/flight_diversions` | `scripts/seed_flight_diversions.py` `tenant_ref.collection("flight_diversions").add` | `seed_flight_diversions.py:??`, `app/services/flight_diversion_service.py` | Auto-ID, `diversion_id` | `tenants/fishtail-air/flight_diversions/{id}` | Sub |
| `tenants/{tid}/surveys` | `seed/surveys.py:104` `tenant_ref.collection("surveys")` | `surveys.py:104`, `app/routes/surveys.py:72` | Auto-ID | `tenants/fishtail-air/surveys/{id}` | Sub |
| `tenants/{tid}/responses` | `seed/surveys.py:108` `collection("responses")` | `surveys.py:108`, `app/routes/surveys.py:74` | Auto-ID | `tenants/fishtail-air/responses/{id}` | Sub |
| `tenants/{tid}/verification` | `app/services/verification_service.py` `tenants/{tid}/verification` | `verification_service.py` | Auto-ID | `tenants/fishtail-air/verification/{id}` | Sub |
| `tenants/{tid}/audit_logs` (if exists as subcollection) | Check shows **top-level** `audit_logs` in `app/services/audit_service.py:51` `db.collection("audit_logs")` — tenant subcollection `audit_logs` not confirmed, will be checked for existence before purge | `audit_service.py:51` | N/A | `tenants/{tid}/audit_logs` (not confirmed) | Unproven |
| `tenants/{tid}/notifications` | **No evidence** — `Select-String notifications` 0 hits in `backend/app/**/*.py` | — | — | `tenants/{tid}/notifications` (guessed, not confirmed) | **Not purged** |
| `psoe_assessments` | `seed/runner.py:478` `db.collection("psoe_assessments").document(tid)` | `runner.py:478`, `app/routes/psoe.py:45` | `tid` (tenant_id) | `psoe_assessments/fishtail-air` | Top-level |
| `audit_logs` | `app/services/audit_service.py:51` `db.collection("audit_logs").add` | `audit_service.py:51`, `production_seed.py:97` | Auto-ID | `audit_logs/{id}` | Top-level |
| `feedback` | `app/routes/feedback.py:69` `db.collection("feedback").add` | `feedback.py:69` | Auto-ID | `feedback/{id}` | Top-level |
| `regulators` | `seed/operators.py:238` `db.collection(regulators).document("caan")` | `operators.py:238` | `caan` | `regulators/caan` | Top-level |
| `caan_reports` | `app/routes/reporting.py:83` `db.collection("caan_reports").add` | `reporting.py:83` | Auto-ID | `caan_reports/{id}` | Top-level |
| `state/ssp/risk_register` | `seed/state_risk.py:19` `db.collection(STATE).document(...).collection(categories)` | `state_risk.py:19` | Auto-ID | `state/ssp/risk_register/{id}` | Top-level-ish |

**No `rca` top-level collection** — RCA is embedded: `hazards.sram_data`, `can_cap.initial_sra`, `can_cap/caps.residual_sra` (`app/models/hazard.py:119` `sram_data`, `can_cap.py:182`). No `cans`/`caps` top-level (guarded `firestore.rules:244` `allow read, write: if false` for `/hazards/{id}`, `/cans/{id}`).

## 2. Legacy tenant IDs (from `backend/seed/config.py:90` OPERATOR_PROFILES and `backend/seed/operators.py` and `production_seed.py:41` SEED_OPERATORS)

- `buddha-air`, `air-dynasty`, `ktm-mro`, `pokhara-aerodrome`, `himalaya-ground-services`, `yeti-airlines`, `summit-air`, `sita-air`, `simrik-air`, `tara-air`, `fishtail-air` (11 active beta tenants)
- Virtual archetypes: `demo-fixed-wing`, `demo-rotary-wing`
- New beta tenants in this task: `fishtail-air` (existing, will be reset), `vnkt-airport` (new AERODROME, not in legacy list)

## 3. Deterministic document IDs / keys (from `backend/seed/hazard_can.py:814` and `seed/reports.py`)

- Hazard: `haz_<tid>_<hash>` or `haz_<tid>_<8char>` deterministic per tenant+seed
- Hazard `hazard_id`: `FI-HZ-001-26` pattern (`app/services/hazard_service.py:19` `generate_hazard_id`)
- CAN: `can_<tid>_<hash>`, `can_reference: CAN-001`
- CAP: `cap_<tid>_<hash>`, `cap_reference: CAN-001-CAP-001`
- Report: Auto-ID, but `report_type` field deterministic
- Survey: Auto-ID

## 4. Document paths (examples)

- `tenants/fishtail-air`
- `tenants/fishtail-air/metadata/info`
- `tenants/fishtail-air/hazards/haz_fishtail-air_abc123`
- `tenants/fishtail-air/can_cap/can_fishtail-air_def456`
- `tenants/fishtail-air/can_cap/can_fishtail-air_def456/caps/cap_fishtail-air_ghi789`
- `tenants/fishtail-air/flight_diversions/auto_xyz`
- `tenants/vnkt-airport/hazards/haz_vnkt-airport_...`

## 5. Required fields and data types (from Pydantic models)

- **Hazard** (`app/models/hazard.py:143`): `title: str(3-200)`, `description: str(>=10)`, `source: HazardSource`, `source_id: str`, `taxonomy: HazardTaxonomy`, `priority: HazardPriority`, `status: HazardStatus`, `department: Optional[str]`, `tenant_id: str`, `created_at: datetime`, `updated_at: datetime`, `severity/probability: int 1-5`
- **CAN** (`app/models/can_cap.py:182`): `can_reference: str`, `hazard_id: str`, `title, description, department, priority, status, assigned_to, target_completion_date: datetime, tenant_id: str, created_at`
- **CAP** (`can_cap.py:212`): `cap_reference, can_id, department, action_plan, status, created_at, tenant_id, can_reference`
- **Report** (`app/models/report.py`): `report_type, status, hazards, created_at, tenant_id`
- **Flight Diversion** (`app/models/flight_diversion.py`): `diversion_id, reason, department, tenant_id`
- **Survey/Response**: `surveys` and `responses` subcollections

## 6. Tenant metadata paths (PRESERVED)

- `tenants/{tid}` (doc with `tenant_id, name, organization_type, active`)
- `tenants/{tid}/metadata/info` (FIREBASE_DOCUMENT_INFO)
- `tenants/{tid}/metadata/profile` and `tenants/{tid}/profile` (operational profile)
- `tenants/{tid}/metadata/risk_matrix`
- `regulators/caan` (top-level, not tenant-specific)

## 7. Protected taxonomy, blueprint, template paths (PRESERVED)

- `tenants/{tid}/metadata/*` (all)
- `app/data/psoe_appendix10.json` (local template, not Firestore)
- `firestore.rules`, `firestore.indexes.json`, `backend/firestore.indexes.json` (files, not data)
- `seed/config.py` OPERATOR_PROFILES (code, not data)

## 8. Top-level collections written by seed.py (disposable vs protected)

- **Disposable (seed-owned, purge allowed in beta):** `psoe_assessments` (seed/runner.py:478), `audit_logs` (if proven top-level seed, but in this repo audit_logs is top-level via service — **not proven seed-owned**, so **preserve** unless proven), `feedback` (not seeded), `caan_reports` (not seeded in beta). **Decision:** Only purge tenant subcollections listed in Table 1; top-level `psoe_assessments` is **preserved** for this task unless explicitly proven disposable — script will not purge top-level collections except `psoe_assessments` if tenant-specific and explicitly listed as seed-owned.
- **Protected (never purge):** `tenants`, `regulators`, `state/ssp/risk_register`, `firestore.rules`, `firestore.indexes.json`

**Decision rule:** If a collection cannot be proven seed-owned or protected, stop and report instead of deleting (implemented as existence check before purge; `notifications` not purged).
