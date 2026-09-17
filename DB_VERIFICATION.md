# DB_VERIFICATION.md — Live Supabase schema verification

Connection: `DATABASE_URL` from `backend/.env` (psycopg2, `postgresql://postgres.bftnwljnpnpniksmalnk:***@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require`, `pgbouncer=true` param dropped for psycopg2).
Mode: READ-ONLY. Only `SELECT`/`information_schema`/`pg_*` catalog queries ran. No DDL, no migrations, no writes.
Verified: 2026-09-16.

---

## Check 1 — Live shape of `risk_register`

Query 1: `SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name='risk_register' ORDER BY ordinal_position`

| column_name | data_type | is_nullable |
|---|---|---|
| id | uuid | NO |
| tenant_id | uuid | NO |
| hazard_id | uuid | NO |
| srm_date | timestamp with time zone | NO |
| ultimate_consequence | text | NO |
| existing_severity | integer | YES |
| existing_probability | integer | YES |
| existing_risk_index | integer | YES |
| existing_risk_tolerability | text | YES |
| resultant_severity | integer | YES |
| resultant_probability | integer | YES |
| resultant_risk_index | integer | YES |
| resultant_risk_tolerability | text | YES |
| status | text | NO |
| follow_up_date | timestamp with time zone | YES |
| date_completed | timestamp with time zone | YES |
| remarks | text | YES |
| concerned_department | text | YES |
| created_by | text | YES |
| updated_by | text | YES |
| created_at | timestamp with time zone | NO |
| updated_at | timestamp with time zone | NO |
| is_demo | boolean | YES |

Query 2: `SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='risk_register'::regclass`

| conname | pg_get_constraintdef |
|---|---|
| risk_register_existing_probability_check | CHECK (((existing_probability >= 1) AND (existing_probability <= 5))) |
| risk_register_existing_severity_check | CHECK (((existing_severity >= 1) AND (existing_severity <= 5))) |
| risk_register_hazard_id_fkey | FOREIGN KEY (hazard_id) REFERENCES hazards(id) |
| risk_register_pkey | PRIMARY KEY (id) |
| risk_register_resultant_probability_check | CHECK (((resultant_probability >= 1) AND (resultant_probability <= 5))) |
| risk_register_resultant_severity_check | CHECK (((resultant_severity >= 1) AND (resultant_severity <= 5))) |

**Conclusions:**
- Live shape = **legacy SRM** (22 columns): `hazard_id UUID NOT NULL` FK → `hazards(id)`, `existing_*/resultant_*`, `srm_date`, `ultimate_consequence`. Matches `db/schema.sql` + `models/risk_register.py` + the 2026-08-30 remote schema snapshot.
- **No SRAM columns present**: no `bowtie_id`, no `probability_current`/`severity_current`/`probability_resultant`/`severity_resultant`, no `accepted`, no `alarp_justification`. The SRAM `CREATE TABLE IF NOT EXISTS` migration (20260905153000) was a no-op on prod, as suspected.
- Constraints: PRIMARY KEY (id), FK hazard_id → hazards(id), and CHECKs 1–5 on existing_*/resultant_* severity/probability. No unique constraints other than the PK. No constraints reference `bowtie_id` or any SRAM column.

---

## Check 2 — Live shape of `caps` signatures

Query: `SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name='caps' ORDER BY ordinal_position` (filtered to signature columns relevant to this check; full column list in raw notes)

| column_name | data_type | is_nullable |
|---|---|---|
| po_signature | jsonb | YES |
| ma_signature | jsonb | YES |
| ae_signature | jsonb | YES |
| closed_signature | jsonb | YES |

(complementary per-number signature columns also present as text/scalars: `po_signature_name`, `po_signature_timestamp`, `po_signature_image_url`, `po_signature_hash`, `po_signature_verified`, and the same block for `ma_signature`.)

**Conclusions:**
- Live `ae_signature`, `closed_signature`, `po_signature`, `ma_signature` are all **jsonb** → **live matches the ORM (JSONB)**, contradicts the 2026-08-30 remote-schema snapshot (`ae_signature TEXT`, `closed_signature TEXT`). That snapshot line is stale; the 2026-09-07 JSONB hardening (git d0fb551) is present in production.

---

## Check 3 — Live shape of `hazards` (ICAO columns)

Query: `SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name='hazards' ORDER BY ordinal_position` (filtered to ICAO/flag/date columns)

| column_name | data_type | is_nullable |
|---|---|---|
| taxonomy | text | NO |
| taxonomy_specific | text | YES |
| function | text | NO |
| threat | text | YES |
| top_event | text | YES |
| corrective_action_flag | boolean | NO |
| srm_flag | boolean | NO |
| priority_date | timestamp with time zone | YES |
| status_date | timestamp with time zone | YES |

**Conclusions:**
- Columns added by migration `20260905090000_hazard_icao_alignment` are **all present in live**: `function`, `threat`, `top_event`, `corrective_action_flag`, `srm_flag`, `priority_date`, `status_date` → the migration applied to production.
- `taxonomy` and `taxonomy_specific` exist. `taxonomy_main` and `taxonomy_type` do **NOT** exist. `hazard_flag` does **NOT** exist (no such column on `hazards`).
- (Full hazards list additionally shows `adrep_category`, `occurrence_type`, `analysis_mode` columns consistent with the generated hazards form.)

---

## Check 4 — Domain tables existence

Query: `SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('caan_reports','sms_maturity','state_risk_categories','dead_letter_queue','sms_dispatches','audit_dispatches','users','tenants','regulators','bow_tie_analyses','bow_tie_threats','bow_tie_consequences','bow_tie_controls','barrier_register','hazard_rca_entries','hazard_rca_factors','hazard_assessments','hazard_capas','psoe_questions','psoe_findings')`

| table_name | status |
|---|---|
| caan_reports | EXISTS |
| sms_maturity | EXISTS |
| state_risk_categories | EXISTS |
| dead_letter_queue | EXISTS |
| sms_dispatches | EXISTS |
| audit_dispatches | EXISTS |
| users | EXISTS |
| tenants | EXISTS |
| regulators | EXISTS |
| bow_tie_analyses | EXISTS |
| bow_tie_threats | EXISTS |
| bow_tie_consequences | EXISTS |
| bow_tie_controls | EXISTS |
| barrier_register | EXISTS |
| hazard_rca_entries | EXISTS |
| hazard_rca_factors | EXISTS |
| hazard_assessments | EXISTS |
| hazard_capas | EXISTS |
| psoe_questions | EXISTS |
| psoe_findings | EXISTS |

**Conclusion:** All 20 domain tables **EXIST** in the live `public` schema (10 additional non-queried tables also present, shown by the RLS scan: `hazard_adrep_mappings`, `hazard_hfacs_codes`, `report_adrep_mappings`, `report_hfacs_codes`, `icao_adrep_taxonomies`, `hfacs_nanocodes`).

---

## Check 5 — RLS enabled status

Query: `SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public' ORDER BY tablename`

| tablename | rowsecurity |
|---|---|
| audit_dispatches | false |
| audit_logs | true |
| barrier_register | true |
| bow_tie_analyses | true |
| bow_tie_consequences | true |
| bow_tie_controls | true |
| bow_tie_threats | true |
| caan_reports | false |
| cans | true |
| caps | true |
| closures | true |
| corrective_actions | true |
| dead_letter_queue | false |
| feedback | true |
| flight_diversions | true |
| hazard_adrep_mappings | true |
| hazard_assessments | true |
| hazard_capas | true |
| hazard_hfacs_codes | true |
| hazard_rca_entries | true |
| hazard_rca_factors | true |
| hazards | true |
| hfacs_nanocodes | true |
| icao_adrep_taxonomies | true |
| invites | true |
| psoe_assessments | true |
| psoe_findings | true |
| psoe_questions | true |
| regulators | true |
| regulatory_reports | true |
| report_adrep_mappings | true |
| report_hfacs_codes | true |
| reports | true |
| risk_register | true |
| safety_deficiencies | true |
| sms_dispatches | false |
| sms_maturity | false |
| state_risk_categories | false |
| state_risk_register | true |
| survey_responses | true |
| surveys | true |
| tenants | true |
| users | true |
| verifications | true |

**Conclusions:**
- RLS is **enabled (true)** on the core domain tables: hazards, reports, cans, caps, verifications, closures, corrective_actions, safety_deficiencies, flight_diversions, surveys, survey_responses, risk_register, state_risk_register, psoe_assessments/questions/findings, regulatory_reports, bow_tie_*, barrier_register, hazard_rca_*, hazard_assessments, hazard_capas, and the reference/lookup tables (icao_adrep_taxonomies, hfacs_nanocodes, adrep/hfacs mappings), plus tenants, users, regulators, invites, feedback, audit_logs.
- RLS is **disabled (false)** on 6 tables: `caan_reports`, `sms_maturity`, `state_risk_categories`, `dead_letter_queue`, `sms_dispatches`, `audit_dispatches`.

---

## Notes / unexpected findings (quoted from DB, no inference)
- The 2026-08-30 `remote_schema.sql` snapshot IS stale w.r.t. live for `caps` signatures (live jsonb). It is accurate for `risk_register` (legacy SRM shape).
- SRAM tables (bow_tie_*, barrier_register) DO exist in live with RLS true — the only element of the 20260905153000 migration that created anything; its `risk_register` branch was a no-op.
- Six additional tables not present in `schema.sql`, `db_models.py`, or the 5 supabase migrations appear in live with RLS true: `hazard_adrep_mappings`, `hazard_hfacs_codes`, `report_adrep_mappings`, `report_hfacs_codes`, `icao_adrep_taxonomies`, `hfacs_nanocodes`.

---

*End of DB_VERIFICATION.md. Read-only audit; no repository or database modifications performed.*