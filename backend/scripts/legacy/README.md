# Legacy Scripts — Do Not Run

These scripts pre-date the A-series migration (2026-09-12)
that removed Firestore from the data plane. They are
retained for historical reference only.

**Do not run any script in this folder.** They may:
- Write to Firestore (deprecated; get_db() now raises)
- Reference tenants that no longer exist
- Use schemas that have changed
- Perform one-time migrations already applied

## Superseded by

| Legacy script | Superseded by |
|---------------|---------------|
| _audit_all_tenants_DEPRECATED.py | No replacement — Firestore-era diagnostic; 20-tenant registry retired |
| activate_survey_campaigns_DEPRECATED.py | No replacement — yeti-airlines/tara-air tenants retired |
| audit_feedback_DEPRECATED.py | No replacement — feedback Postgres-backed |
| audit_survey_status_DEPRECATED.py | No replacement — survey windows read from Postgres tenants.data |
| backfill_hazards_DEPRECATED.py | seed/unified_seeder.py (Postgres hazards) |
| backfill_sms_maturity_DEPRECATED.py | No replacement — one-time rename already applied |
| backfill_users_DEPRECATED.py | app.services.users.backfill_users_from_auth / upsert_user_doc (Postgres users mirror) |
| cleanup_firestore_surveys_DEPRECATED.py | No replacement — Firestore gone; surveys/survey_responses Postgres-only |
| fix_summit_air_user_DEPRECATED.py | No replacement — summit-air tenant retired |
| generate_tenant_details_DEPRECATED.py | No replacement — metric sources now Postgres |
| list_generic_users_DEPRECATED.py | No replacement — generic demo uids retired |
| migrate_audit_logs_DEPRECATED.py | No replacement — audit_logs shape in schema_init |
| migrate_emails_test_to_com_DEPRECATED.py | No replacement — .test emails retired |
| migrate_hazard_ids_to_function_format_DEPRECATED.py | No replacement — hazards born in function format |
| migrate_jsonb_defaults_DEPRECATED.py | No replacement — jsonb defaults in schema_init |
| migrate_tenant_ids_DEPRECATED.py | No replacement — schema_init provisions uuid5 tenant ids |
| purge_auth_pool_DEPRECATED.py | No replacement — auth pool superseded |
| seed_caan_demo_data_DEPRECATED.py | No replacement — CAAN demo state via unified seeder / Postgres |
| seed_flight_diversions_DEPRECATED.py | No replacement — flight_diversions Postgres table |
| seed_psoe_baselines_DEPRECATED.py | No replacement — psoe_assessments Postgres table |
| seed_uat_data_DEPRECATED.py | No replacement — UAT fixtures superseded by phase checks + unified seeder |
| simplify_credentials_DEPRECATED.py | No replacement — onboarding + create_user_for_tenant supersede |
| validate_seasonal_seed_DEPRECATED.py | No replacement — seed checks against Postgres |
| verify_beta_logins_DEPRECATED.py | No replacement — beta credential artifacts retired |
| wipe_tenant_data_DEPRECATED.py | reset_to_virgin.py (regulator-preserving PG demo reset) |

## Deletion schedule

Reviewed on 2027-03-13. Any script unreferenced by that
date will be deleted.