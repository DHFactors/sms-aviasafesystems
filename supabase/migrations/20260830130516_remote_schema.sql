


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";





SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."cans" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "can_reference" "text" NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "hazard_id" "uuid" NOT NULL,
    "title" "text" NOT NULL,
    "description" "text" NOT NULL,
    "required_action" "text" NOT NULL,
    "issued_by" "text" NOT NULL,
    "issued_by_uid" "text" NOT NULL,
    "issued_at" timestamp with time zone,
    "target_completion_date" timestamp with time zone,
    "assigned_to" "text" NOT NULL,
    "assigned_to_uid" "text" NOT NULL,
    "department" "text",
    "priority" "text" NOT NULL,
    "status" "text" NOT NULL,
    "copies_to" "text",
    "requested_function" "text",
    "addressed_function" "text",
    "initial_severity" integer,
    "initial_probability" integer,
    "initial_risk_index" integer,
    "initial_risk_level" "text",
    "initial_risk_outcome" "text",
    "initial_tolerability_tier" "text",
    "initial_sra" "jsonb",
    "classification_type" "text",
    "classification_level" "text",
    "created_by" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "is_demo" boolean DEFAULT false NOT NULL,
    CONSTRAINT "cans_initial_probability_check" CHECK ((("initial_probability" >= 1) AND ("initial_probability" <= 5))),
    CONSTRAINT "cans_initial_risk_index_check" CHECK ((("initial_risk_index" >= 1) AND ("initial_risk_index" <= 25))),
    CONSTRAINT "cans_initial_severity_check" CHECK ((("initial_severity" >= 1) AND ("initial_severity" <= 5))),
    CONSTRAINT "cans_priority_check" CHECK (("priority" = ANY (ARRAY['High'::"text", 'Medium'::"text", 'Low'::"text"])))
);


ALTER TABLE "public"."cans" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."caps" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "cap_reference" "text" NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "can_id" "uuid" NOT NULL,
    "action_plan" "text" NOT NULL,
    "timeline" "text" NOT NULL,
    "resources_required" "text",
    "implementation_plan" "text",
    "department" "text",
    "target_completion_date" timestamp with time zone NOT NULL,
    "submitted_by" "text" NOT NULL,
    "submitted_by_uid" "text" NOT NULL,
    "submitted_at" timestamp with time zone,
    "status" "text" NOT NULL,
    "reviewed_by" "text",
    "reviewed_by_uid" "text",
    "reviewed_at" timestamp with time zone,
    "review_comments" "text",
    "revision_deadline" timestamp with time zone,
    "company_name" "text",
    "base_location" "text",
    "area_system_of_interest" "text",
    "finding_number" "text",
    "file_ref" "text",
    "factual_review" "text",
    "rca" "text",
    "short_term_ca" "text",
    "long_term_ca" "text",
    "implementation_timeline" "text",
    "managerial_approval" "jsonb",
    "caa_acceptance" "jsonb",
    "residual_severity" integer,
    "residual_probability" integer,
    "residual_risk_index" integer,
    "residual_risk_level" "text",
    "residual_risk_outcome" "text",
    "residual_tolerability_tier" "text",
    "residual_sra" "jsonb",
    "root_causes" "jsonb",
    "action_items" "jsonb",
    "rca_method" "text",
    "sram_data" "jsonb",
    "escalated_to_ae" boolean,
    "escalated_by" "text",
    "escalated_at" timestamp with time zone,
    "escalation_reason" "text",
    "ae_signature" "text",
    "ae_signed_at" timestamp with time zone,
    "ae_review_interval_days" integer,
    "ae_review_date" timestamp with time zone,
    "sag_sign" "text",
    "sag_signed_by" "text",
    "sag_signed_at" timestamp with time zone,
    "manager_approval" "text",
    "ca_acceptance" "text",
    "process_owner" "text",
    "manager_confirmation" "text",
    "closing_remarks" "text",
    "closed_by" "text",
    "closed_at" timestamp with time zone,
    "closed_signature" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "is_demo" boolean DEFAULT false NOT NULL,
    CONSTRAINT "caps_ae_review_interval_days_check" CHECK ((("ae_review_interval_days" >= 1) AND ("ae_review_interval_days" <= 365))),
    CONSTRAINT "caps_rca_method_check" CHECK (("rca_method" = ANY (ARRAY['bow_tie'::"text", 'fishbone'::"text"]))),
    CONSTRAINT "caps_residual_probability_check" CHECK ((("residual_probability" >= 1) AND ("residual_probability" <= 5))),
    CONSTRAINT "caps_residual_risk_index_check" CHECK ((("residual_risk_index" >= 1) AND ("residual_risk_index" <= 25))),
    CONSTRAINT "caps_residual_severity_check" CHECK ((("residual_severity" >= 1) AND ("residual_severity" <= 5)))
);


ALTER TABLE "public"."caps" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."closures" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "hazard_id" "uuid" NOT NULL,
    "lessons_learned" "text",
    "recommendations" "text",
    "approval_notes" "text",
    "approved_by" "text" NOT NULL,
    "approved_by_uid" "text" NOT NULL,
    "approved_at" timestamp with time zone NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."closures" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."corrective_actions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "hazard_id" "uuid",
    "can_id" "uuid",
    "event_id" "uuid",
    "title" "text" NOT NULL,
    "description" "text" NOT NULL,
    "action_plan" "text" NOT NULL,
    "priority" "text" DEFAULT 'Medium'::"text" NOT NULL,
    "assigned_to" "text",
    "assigned_to_uid" "text",
    "assigned_by" "text",
    "assigned_at" timestamp with time zone,
    "target_completion_date" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "reviewed_by" "text",
    "reviewed_at" timestamp with time zone,
    "review_comments" "text",
    "status" "text" NOT NULL,
    "remarks" "text",
    "created_by" "text",
    "updated_by" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "corrective_actions_priority_check" CHECK (("priority" = ANY (ARRAY['High'::"text", 'Medium'::"text", 'Low'::"text"])))
);


ALTER TABLE "public"."corrective_actions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."flight_diversions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "diversion_id" "text" NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "date" timestamp with time zone NOT NULL,
    "flight_number" "text" NOT NULL,
    "aircraft_registration" "text" NOT NULL,
    "sector_from" "text" NOT NULL,
    "sector_to" "text" NOT NULL,
    "diverted_to" "text" NOT NULL,
    "reason" "text" NOT NULL,
    "reason_details" "text",
    "captain" "text",
    "first_officer" "text",
    "air_hostess" "text",
    "description" "text" NOT NULL,
    "additional_fuel_cost" numeric(12,2),
    "passenger_impact" integer,
    "delay_minutes" integer,
    "remarks" "text",
    "status" "text" NOT NULL,
    "hazard_id" "uuid",
    "hazard_link_url" "text",
    "created_by" "text",
    "updated_by" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."flight_diversions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."hazard_assessments" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "entry_id" "uuid" NOT NULL,
    "resource_id" "text" NOT NULL,
    "assessment_type" "text",
    "severity" "jsonb",
    "probability" "jsonb",
    "risk_index" "text",
    "tolerability" "text",
    "assessed_by" "text",
    "assessed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."hazard_assessments" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."hazard_capas" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "entry_id" "uuid" NOT NULL,
    "resource_id" "text" NOT NULL,
    "status" "text",
    "implemented_at" timestamp with time zone,
    "verified_by" "text",
    "data" "jsonb",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."hazard_capas" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."hazard_rca_entries" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "resource_id" "text" NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "title" "text" NOT NULL,
    "description" "text" NOT NULL,
    "source_type" "text" NOT NULL,
    "source_reference_id" "text",
    "functional_area" "text" NOT NULL,
    "status" "text" DEFAULT 'under_assessment'::"text" NOT NULL,
    "risk_summary" "jsonb",
    "hfacs_summary" "jsonb",
    "identified_by" "jsonb",
    "assigned_owner" "jsonb",
    "target_completion_date" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "closed_at" timestamp with time zone
);


ALTER TABLE "public"."hazard_rca_entries" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."hazard_rca_factors" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "entry_id" "uuid" NOT NULL,
    "resource_id" "text" NOT NULL,
    "tier" integer,
    "category" "text",
    "subcategory" "text",
    "nanocode" "text",
    "definition" "text",
    "contributing_narrative" "text",
    "order_sequence" integer,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."hazard_rca_factors" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."hazards" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "hazard_id" "text" NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "title" "text" NOT NULL,
    "description" "text" NOT NULL,
    "source" "text" NOT NULL,
    "source_id" "text" NOT NULL,
    "source_url" "text",
    "adrep_category" "text",
    "occurrence_type" "text",
    "taxonomy" "text" NOT NULL,
    "taxonomy_specific" "text",
    "consequence" "text",
    "severity" integer,
    "probability" integer,
    "risk_index" integer,
    "risk_level" "text",
    "risk_outcome" "text",
    "tolerability_tier" "text",
    "priority" "text" NOT NULL,
    "recommended_action" "text",
    "corrective_action" "text",
    "assigned_to" "text",
    "assigned_to_uid" "text",
    "department" "text",
    "srm_conducted" boolean DEFAULT false NOT NULL,
    "srm_date" timestamp with time zone,
    "srm_status" "text",
    "analysis_mode" "text" DEFAULT 'FISHBONE_ONLY'::"text" NOT NULL,
    "sram_data" "jsonb",
    "status" "text" NOT NULL,
    "follow_up_date" timestamp with time zone,
    "closed_at" timestamp with time zone,
    "closed_by" "text",
    "remarks" "text",
    "created_by" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "is_demo" boolean DEFAULT false NOT NULL,
    CONSTRAINT "hazards_priority_check" CHECK (("priority" = ANY (ARRAY['H'::"text", 'M'::"text", 'L'::"text"]))),
    CONSTRAINT "hazards_probability_check" CHECK ((("probability" >= 1) AND ("probability" <= 5))),
    CONSTRAINT "hazards_severity_check" CHECK ((("severity" >= 1) AND ("severity" <= 5)))
);


ALTER TABLE "public"."hazards" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."psoe_assessments" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "title" "text" NOT NULL,
    "status" "text" DEFAULT 'draft'::"text" NOT NULL,
    "department" "text",
    "scope" "text",
    "auditor_name" "text",
    "assessor_email" "text",
    "assessment_date" timestamp with time zone,
    "template_version" "text" NOT NULL,
    "responses" "jsonb" NOT NULL,
    "component_scores" "jsonb",
    "overall_score_pct" double precision,
    "overall_level" "text",
    "notes" "text",
    "created_by" "text",
    "created_by_uid" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "is_demo" boolean DEFAULT false NOT NULL
);


ALTER TABLE "public"."psoe_assessments" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."regulatory_reports" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "report_type" "text" NOT NULL,
    "period" "text" NOT NULL,
    "year" integer NOT NULL,
    "quarter" integer,
    "status" "text" NOT NULL,
    "summary" "jsonb",
    "data" "jsonb",
    "generated_at" timestamp with time zone,
    "generated_by" "text",
    "file_url" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "is_demo" boolean DEFAULT false NOT NULL,
    CONSTRAINT "regulatory_reports_quarter_check" CHECK ((("quarter" >= 1) AND ("quarter" <= 4))),
    CONSTRAINT "regulatory_reports_report_type_check" CHECK (("report_type" = ANY (ARRAY['quarterly'::"text", 'annual'::"text"])))
);


ALTER TABLE "public"."regulatory_reports" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."reports" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "report_type" "text" NOT NULL,
    "status" "text" NOT NULL,
    "ai_status" "text" DEFAULT 'PENDING'::"text" NOT NULL,
    "narrative" "text" NOT NULL,
    "location" "text" NOT NULL,
    "occurrence_date" timestamp with time zone NOT NULL,
    "is_anonymous" boolean DEFAULT false NOT NULL,
    "flight_number" "text",
    "aircraft_registration" "text",
    "occurrence_type" "text",
    "severity" "text",
    "investigation_status" "text",
    "severity_level" integer,
    "probability_level" integer,
    "risk_index" integer,
    "risk_level" "text",
    "risk_assessment" "jsonb",
    "ai_suggested_assessment" "jsonb",
    "ai_analysis" "jsonb",
    "occurrence_class" "text",
    "latitude" double precision,
    "longitude" double precision,
    "country" "text",
    "aircraft_make" "text",
    "aircraft_model" "text",
    "aircraft_serial_number" "text",
    "operator" "text",
    "operator_icao" "text",
    "aircraft_category" "text",
    "engine_make" "text",
    "engine_model" "text",
    "engine_serial_number" "text",
    "flight_phase" "text",
    "flight_type" "text",
    "departure_airport" "text",
    "destination_airport" "text",
    "aircraft_utilisation_hours" double precision,
    "aircraft_utilisation_cycles" integer,
    "crew_count" integer,
    "passenger_count" integer,
    "fatal_injuries" integer,
    "serious_injuries" integer,
    "minor_injuries" integer,
    "occurrence_category" "text",
    "human_factors" "jsonb",
    "contributing_factors" "jsonb",
    "investigation_agency" "text",
    "reporter_name" "text",
    "reporter_role" "text",
    "reporter_email" "text",
    "reporter_phone" "text",
    "reporter_organisation" "text",
    "reporting_date" timestamp with time zone,
    "etops" boolean DEFAULT false NOT NULL,
    "propeller_make" "text",
    "propeller_model" "text",
    "call_sign" "text",
    "organisation_comments" "text",
    "manufacturer_advised" boolean DEFAULT false NOT NULL,
    "fdr_data_retained" boolean DEFAULT false NOT NULL,
    "created_by" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "is_demo" boolean DEFAULT false NOT NULL,
    CONSTRAINT "reports_probability_level_check" CHECK ((("probability_level" >= 1) AND ("probability_level" <= 5))),
    CONSTRAINT "reports_report_type_check" CHECK (("report_type" = ANY (ARRAY['voluntary'::"text", 'mandatory'::"text"]))),
    CONSTRAINT "reports_severity_level_check" CHECK ((("severity_level" >= 1) AND ("severity_level" <= 5)))
);


ALTER TABLE "public"."reports" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."risk_register" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "hazard_id" "uuid" NOT NULL,
    "srm_date" timestamp with time zone NOT NULL,
    "ultimate_consequence" "text" NOT NULL,
    "existing_severity" integer,
    "existing_probability" integer,
    "existing_risk_index" integer,
    "existing_risk_tolerability" "text",
    "resultant_severity" integer,
    "resultant_probability" integer,
    "resultant_risk_index" integer,
    "resultant_risk_tolerability" "text",
    "status" "text" NOT NULL,
    "follow_up_date" timestamp with time zone,
    "date_completed" timestamp with time zone,
    "remarks" "text",
    "concerned_department" "text",
    "created_by" "text",
    "updated_by" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "risk_register_existing_probability_check" CHECK ((("existing_probability" >= 1) AND ("existing_probability" <= 5))),
    CONSTRAINT "risk_register_existing_severity_check" CHECK ((("existing_severity" >= 1) AND ("existing_severity" <= 5))),
    CONSTRAINT "risk_register_resultant_probability_check" CHECK ((("resultant_probability" >= 1) AND ("resultant_probability" <= 5))),
    CONSTRAINT "risk_register_resultant_severity_check" CHECK ((("resultant_severity" >= 1) AND ("resultant_severity" <= 5)))
);


ALTER TABLE "public"."risk_register" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."safety_deficiencies" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "event_id" "uuid",
    "source" "text" NOT NULL,
    "hazard_code" "text",
    "description" "text" NOT NULL,
    "taxonomy_main" "text",
    "taxonomy_type" "text",
    "taxonomy_specific" "text",
    "unsafe_event" "text",
    "identified_hazard" "text",
    "priority" "text",
    "severity" "text",
    "assigned_to" "text",
    "assigned_to_uid" "text",
    "assigned_by" "text",
    "assigned_at" timestamp with time zone,
    "follow_up_date" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "status" "text" NOT NULL,
    "remarks" "text",
    "csd_remarks" "text",
    "created_by" "text",
    "updated_by" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "safety_deficiencies_priority_check" CHECK (("priority" = ANY (ARRAY['H'::"text", 'M'::"text", 'L'::"text"]))),
    CONSTRAINT "safety_deficiencies_severity_check" CHECK (("severity" = ANY (ARRAY['Low'::"text", 'Medium'::"text", 'High'::"text", 'Critical'::"text"])))
);


ALTER TABLE "public"."safety_deficiencies" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."state_risk_register" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "icoc_category" "text" NOT NULL,
    "description" "text" NOT NULL,
    "icao_reference" "text",
    "current_risk_index" integer,
    "tolerability" "text" NOT NULL,
    "tolerability_tier" "text",
    "level" "text",
    "ssp_target" double precision,
    "actual_ssp_value" double precision,
    "risk_reduction_rate" double precision,
    "trend" "text" NOT NULL,
    "contributing_tenants" "jsonb",
    "quarter" integer,
    "year" integer,
    "updated_by" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "is_demo" boolean DEFAULT false NOT NULL,
    CONSTRAINT "state_risk_register_current_risk_index_check" CHECK ((("current_risk_index" >= 1) AND ("current_risk_index" <= 25))),
    CONSTRAINT "state_risk_register_quarter_check" CHECK ((("quarter" >= 1) AND ("quarter" <= 4)))
);


ALTER TABLE "public"."state_risk_register" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."survey_responses" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "respondent_id" "text",
    "answers" "jsonb" NOT NULL,
    "department" "text",
    "employee_category" "text",
    "years_experience" "text",
    "language_used" "text",
    "submitted_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "survey_version" "text" NOT NULL,
    "is_demo" boolean DEFAULT false NOT NULL
);


ALTER TABLE "public"."survey_responses" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."surveys" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "submitted_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "respondent_id" "text",
    "department" "text",
    "employee_category" "text",
    "years_experience" "text",
    "language_used" "text",
    "survey_version" "text" NOT NULL,
    "seed_version" "text",
    "answers" "jsonb" NOT NULL,
    "question_scores" "jsonb",
    "element_scores" "jsonb",
    "safety_policy" integer,
    "safety_risk_management" integer,
    "safety_assurance" integer,
    "safety_promotion" integer,
    "overall_sms_maturity" integer,
    "overall_score_pct" numeric(5,2),
    "is_demo" boolean DEFAULT false NOT NULL,
    CONSTRAINT "surveys_overall_sms_maturity_check" CHECK ((("overall_sms_maturity" >= 1) AND ("overall_sms_maturity" <= 5))),
    CONSTRAINT "surveys_safety_assurance_check" CHECK ((("safety_assurance" >= 1) AND ("safety_assurance" <= 5))),
    CONSTRAINT "surveys_safety_policy_check" CHECK ((("safety_policy" >= 1) AND ("safety_policy" <= 5))),
    CONSTRAINT "surveys_safety_promotion_check" CHECK ((("safety_promotion" >= 1) AND ("safety_promotion" <= 5))),
    CONSTRAINT "surveys_safety_risk_management_check" CHECK ((("safety_risk_management" >= 1) AND ("safety_risk_management" <= 5)))
);


ALTER TABLE "public"."surveys" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."verifications" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "tenant_id" "uuid" NOT NULL,
    "hazard_id" "uuid" NOT NULL,
    "cap_id" "uuid" NOT NULL,
    "outcome" "text" NOT NULL,
    "comments" "text",
    "evidence" "jsonb",
    "verified_by" "text" NOT NULL,
    "verified_by_uid" "text" NOT NULL,
    "verification_date" timestamp with time zone NOT NULL,
    "revision_deadline" timestamp with time zone,
    "revision_notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."verifications" OWNER TO "postgres";


ALTER TABLE ONLY "public"."cans"
    ADD CONSTRAINT "cans_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."caps"
    ADD CONSTRAINT "caps_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."closures"
    ADD CONSTRAINT "closures_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."corrective_actions"
    ADD CONSTRAINT "corrective_actions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."flight_diversions"
    ADD CONSTRAINT "flight_diversions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."hazard_assessments"
    ADD CONSTRAINT "hazard_assessments_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."hazard_capas"
    ADD CONSTRAINT "hazard_capas_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."hazard_rca_entries"
    ADD CONSTRAINT "hazard_rca_entries_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."hazard_rca_factors"
    ADD CONSTRAINT "hazard_rca_factors_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."hazards"
    ADD CONSTRAINT "hazards_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."psoe_assessments"
    ADD CONSTRAINT "psoe_assessments_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."regulatory_reports"
    ADD CONSTRAINT "regulatory_reports_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."reports"
    ADD CONSTRAINT "reports_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."risk_register"
    ADD CONSTRAINT "risk_register_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."safety_deficiencies"
    ADD CONSTRAINT "safety_deficiencies_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."state_risk_register"
    ADD CONSTRAINT "state_risk_register_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."survey_responses"
    ADD CONSTRAINT "survey_responses_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."surveys"
    ADD CONSTRAINT "surveys_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."verifications"
    ADD CONSTRAINT "verifications_pkey" PRIMARY KEY ("id");



CREATE INDEX "idx_cans_tenant_demo" ON "public"."cans" USING "btree" ("tenant_id", "is_demo");



CREATE INDEX "idx_caps_tenant_demo" ON "public"."caps" USING "btree" ("tenant_id", "is_demo");



CREATE INDEX "idx_hazards_tenant_demo" ON "public"."hazards" USING "btree" ("tenant_id", "is_demo");



CREATE INDEX "idx_psoe_assessments_tenant_demo" ON "public"."psoe_assessments" USING "btree" ("tenant_id", "is_demo");



CREATE INDEX "idx_regulatory_reports_tenant_demo" ON "public"."regulatory_reports" USING "btree" ("tenant_id", "is_demo");



CREATE INDEX "idx_reports_tenant_demo" ON "public"."reports" USING "btree" ("tenant_id", "is_demo");



CREATE INDEX "idx_state_risk_register_tenant_demo" ON "public"."state_risk_register" USING "btree" ("tenant_id", "is_demo");



CREATE INDEX "idx_survey_responses_tenant_demo" ON "public"."survey_responses" USING "btree" ("tenant_id", "is_demo");



CREATE INDEX "idx_surveys_tenant_demo" ON "public"."surveys" USING "btree" ("tenant_id", "is_demo");



CREATE INDEX "ix_cans_hazard" ON "public"."cans" USING "btree" ("tenant_id", "hazard_id");



CREATE INDEX "ix_cans_tenant" ON "public"."cans" USING "btree" ("tenant_id");



CREATE INDEX "ix_cans_tenant_assignee" ON "public"."cans" USING "btree" ("tenant_id", "assigned_to");



CREATE INDEX "ix_cans_tenant_status" ON "public"."cans" USING "btree" ("tenant_id", "status");



CREATE INDEX "ix_caps_can" ON "public"."caps" USING "btree" ("tenant_id", "can_id");



CREATE INDEX "ix_caps_tenant" ON "public"."caps" USING "btree" ("tenant_id");



CREATE INDEX "ix_caps_tenant_status" ON "public"."caps" USING "btree" ("tenant_id", "status");



CREATE INDEX "ix_closures_tenant" ON "public"."closures" USING "btree" ("tenant_id");



CREATE INDEX "ix_closures_tenant_hazard" ON "public"."closures" USING "btree" ("tenant_id", "hazard_id");



CREATE INDEX "ix_corrective_actions_can" ON "public"."corrective_actions" USING "btree" ("tenant_id", "can_id");



CREATE INDEX "ix_corrective_actions_hazard" ON "public"."corrective_actions" USING "btree" ("tenant_id", "hazard_id");



CREATE INDEX "ix_corrective_actions_tenant" ON "public"."corrective_actions" USING "btree" ("tenant_id");



CREATE INDEX "ix_corrective_actions_tenant_assignee" ON "public"."corrective_actions" USING "btree" ("tenant_id", "assigned_to");



CREATE INDEX "ix_corrective_actions_tenant_status" ON "public"."corrective_actions" USING "btree" ("tenant_id", "status");



CREATE INDEX "ix_flight_diversions_hazard" ON "public"."flight_diversions" USING "btree" ("tenant_id", "hazard_id");



CREATE INDEX "ix_flight_diversions_tenant" ON "public"."flight_diversions" USING "btree" ("tenant_id");



CREATE INDEX "ix_flight_diversions_tenant_date" ON "public"."flight_diversions" USING "btree" ("tenant_id", "date");



CREATE INDEX "ix_flight_diversions_tenant_status" ON "public"."flight_diversions" USING "btree" ("tenant_id", "status");



CREATE INDEX "ix_hazard_assessments_tenant" ON "public"."hazard_assessments" USING "btree" ("tenant_id");



CREATE INDEX "ix_hazard_capas_tenant" ON "public"."hazard_capas" USING "btree" ("tenant_id");



CREATE INDEX "ix_hazard_rca_entries_tenant" ON "public"."hazard_rca_entries" USING "btree" ("tenant_id");



CREATE INDEX "ix_hazard_rca_factors_tenant" ON "public"."hazard_rca_factors" USING "btree" ("tenant_id");



CREATE INDEX "ix_hazards_tenant" ON "public"."hazards" USING "btree" ("tenant_id");



CREATE INDEX "ix_hazards_tenant_assignee" ON "public"."hazards" USING "btree" ("tenant_id", "assigned_to");



CREATE INDEX "ix_hazards_tenant_created" ON "public"."hazards" USING "btree" ("tenant_id", "created_at");



CREATE INDEX "ix_hazards_tenant_status" ON "public"."hazards" USING "btree" ("tenant_id", "status");



CREATE INDEX "ix_psoe_assessments_tenant" ON "public"."psoe_assessments" USING "btree" ("tenant_id");



CREATE INDEX "ix_psoe_assessments_tenant_date" ON "public"."psoe_assessments" USING "btree" ("tenant_id", "assessment_date");



CREATE INDEX "ix_psoe_assessments_tenant_status" ON "public"."psoe_assessments" USING "btree" ("tenant_id", "status");



CREATE INDEX "ix_regulatory_reports_tenant" ON "public"."regulatory_reports" USING "btree" ("tenant_id");



CREATE INDEX "ix_regulatory_reports_tenant_created" ON "public"."regulatory_reports" USING "btree" ("tenant_id", "created_at");



CREATE INDEX "ix_regulatory_reports_tenant_period" ON "public"."regulatory_reports" USING "btree" ("tenant_id", "report_type", "year", "quarter");



CREATE INDEX "ix_regulatory_reports_tenant_status" ON "public"."regulatory_reports" USING "btree" ("tenant_id", "status");



CREATE INDEX "ix_reports_tenant" ON "public"."reports" USING "btree" ("tenant_id");



CREATE INDEX "ix_reports_tenant_aircraft" ON "public"."reports" USING "btree" ("tenant_id", "aircraft_registration");



CREATE INDEX "ix_reports_tenant_created" ON "public"."reports" USING "btree" ("tenant_id", "created_at");



CREATE INDEX "ix_reports_tenant_occdate" ON "public"."reports" USING "btree" ("tenant_id", "occurrence_date");



CREATE INDEX "ix_reports_tenant_status" ON "public"."reports" USING "btree" ("tenant_id", "status");



CREATE INDEX "ix_risk_register_tenant" ON "public"."risk_register" USING "btree" ("tenant_id");



CREATE INDEX "ix_risk_register_tenant_hazard" ON "public"."risk_register" USING "btree" ("tenant_id", "hazard_id");



CREATE INDEX "ix_risk_register_tenant_srmdate" ON "public"."risk_register" USING "btree" ("tenant_id", "srm_date");



CREATE INDEX "ix_risk_register_tenant_status" ON "public"."risk_register" USING "btree" ("tenant_id", "status");



CREATE INDEX "ix_safety_deficiencies_tenant" ON "public"."safety_deficiencies" USING "btree" ("tenant_id");



CREATE INDEX "ix_safety_deficiencies_tenant_assignee" ON "public"."safety_deficiencies" USING "btree" ("tenant_id", "assigned_to");



CREATE INDEX "ix_safety_deficiencies_tenant_status" ON "public"."safety_deficiencies" USING "btree" ("tenant_id", "status");



CREATE INDEX "ix_state_risk_register_tenant" ON "public"."state_risk_register" USING "btree" ("tenant_id");



CREATE INDEX "ix_state_risk_register_tenant_period" ON "public"."state_risk_register" USING "btree" ("tenant_id", "year", "quarter");



CREATE INDEX "ix_survey_responses_tenant" ON "public"."survey_responses" USING "btree" ("tenant_id");



CREATE INDEX "ix_survey_responses_tenant_date" ON "public"."survey_responses" USING "btree" ("tenant_id", "submitted_at");



CREATE INDEX "ix_surveys_tenant" ON "public"."surveys" USING "btree" ("tenant_id");



CREATE INDEX "ix_surveys_tenant_date" ON "public"."surveys" USING "btree" ("tenant_id", "submitted_at");



CREATE INDEX "ix_surveys_tenant_dept" ON "public"."surveys" USING "btree" ("tenant_id", "department");



CREATE INDEX "ix_verifications_tenant" ON "public"."verifications" USING "btree" ("tenant_id");



CREATE INDEX "ix_verifications_tenant_cap" ON "public"."verifications" USING "btree" ("tenant_id", "cap_id");



CREATE INDEX "ix_verifications_tenant_date" ON "public"."verifications" USING "btree" ("tenant_id", "verification_date");



CREATE INDEX "ix_verifications_tenant_hazard" ON "public"."verifications" USING "btree" ("tenant_id", "hazard_id");



CREATE UNIQUE INDEX "ux_cans_tenant_ref" ON "public"."cans" USING "btree" ("tenant_id", "can_reference");



CREATE UNIQUE INDEX "ux_caps_tenant_ref" ON "public"."caps" USING "btree" ("tenant_id", "cap_reference");



CREATE UNIQUE INDEX "ux_flight_diversions_tenant_ref" ON "public"."flight_diversions" USING "btree" ("tenant_id", "diversion_id");



CREATE UNIQUE INDEX "ux_hazard_rca_entries_tenant" ON "public"."hazard_rca_entries" USING "btree" ("tenant_id", "resource_id");



CREATE UNIQUE INDEX "ux_hazards_tenant_id" ON "public"."hazards" USING "btree" ("tenant_id", "hazard_id");



ALTER TABLE ONLY "public"."cans"
    ADD CONSTRAINT "cans_hazard_id_fkey" FOREIGN KEY ("hazard_id") REFERENCES "public"."hazards"("id");



ALTER TABLE ONLY "public"."caps"
    ADD CONSTRAINT "caps_can_id_fkey" FOREIGN KEY ("can_id") REFERENCES "public"."cans"("id");



ALTER TABLE ONLY "public"."closures"
    ADD CONSTRAINT "closures_hazard_id_fkey" FOREIGN KEY ("hazard_id") REFERENCES "public"."hazards"("id");



ALTER TABLE ONLY "public"."corrective_actions"
    ADD CONSTRAINT "corrective_actions_can_id_fkey" FOREIGN KEY ("can_id") REFERENCES "public"."cans"("id");



ALTER TABLE ONLY "public"."corrective_actions"
    ADD CONSTRAINT "corrective_actions_hazard_id_fkey" FOREIGN KEY ("hazard_id") REFERENCES "public"."hazards"("id");



ALTER TABLE ONLY "public"."flight_diversions"
    ADD CONSTRAINT "flight_diversions_hazard_id_fkey" FOREIGN KEY ("hazard_id") REFERENCES "public"."hazards"("id");



ALTER TABLE ONLY "public"."hazard_assessments"
    ADD CONSTRAINT "hazard_assessments_entry_id_fkey" FOREIGN KEY ("entry_id") REFERENCES "public"."hazard_rca_entries"("id");



ALTER TABLE ONLY "public"."hazard_capas"
    ADD CONSTRAINT "hazard_capas_entry_id_fkey" FOREIGN KEY ("entry_id") REFERENCES "public"."hazard_rca_entries"("id");



ALTER TABLE ONLY "public"."hazard_rca_factors"
    ADD CONSTRAINT "hazard_rca_factors_entry_id_fkey" FOREIGN KEY ("entry_id") REFERENCES "public"."hazard_rca_entries"("id");



ALTER TABLE ONLY "public"."risk_register"
    ADD CONSTRAINT "risk_register_hazard_id_fkey" FOREIGN KEY ("hazard_id") REFERENCES "public"."hazards"("id");



ALTER TABLE ONLY "public"."verifications"
    ADD CONSTRAINT "verifications_cap_id_fkey" FOREIGN KEY ("cap_id") REFERENCES "public"."caps"("id");



ALTER TABLE ONLY "public"."verifications"
    ADD CONSTRAINT "verifications_hazard_id_fkey" FOREIGN KEY ("hazard_id") REFERENCES "public"."hazards"("id");



ALTER TABLE "public"."cans" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."caps" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."closures" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."corrective_actions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."flight_diversions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."hazards" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "p_cans_tenant_isolation" ON "public"."cans" TO "authenticated" USING (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid")) WITH CHECK (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid"));



CREATE POLICY "p_caps_tenant_isolation" ON "public"."caps" TO "authenticated" USING (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid")) WITH CHECK (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid"));



CREATE POLICY "p_closures_tenant_isolation" ON "public"."closures" TO "authenticated" USING (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid")) WITH CHECK (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid"));



CREATE POLICY "p_corrective_actions_tenant_isolation" ON "public"."corrective_actions" TO "authenticated" USING (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid")) WITH CHECK (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid"));



CREATE POLICY "p_flight_diversions_tenant_isolation" ON "public"."flight_diversions" TO "authenticated" USING (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid")) WITH CHECK (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid"));



CREATE POLICY "p_hazards_tenant_isolation" ON "public"."hazards" TO "authenticated" USING (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid")) WITH CHECK (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid"));



CREATE POLICY "p_psoe_assessments_tenant_isolation" ON "public"."psoe_assessments" TO "authenticated" USING (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid")) WITH CHECK (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid"));



CREATE POLICY "p_regulatory_reports_tenant_isolation" ON "public"."regulatory_reports" TO "authenticated" USING (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid")) WITH CHECK (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid"));



CREATE POLICY "p_reports_tenant_isolation" ON "public"."reports" TO "authenticated" USING (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid")) WITH CHECK (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid"));



CREATE POLICY "p_risk_register_tenant_isolation" ON "public"."risk_register" TO "authenticated" USING (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid")) WITH CHECK (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid"));



CREATE POLICY "p_safety_deficiencies_tenant_isolation" ON "public"."safety_deficiencies" TO "authenticated" USING (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid")) WITH CHECK (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid"));



CREATE POLICY "p_state_risk_register_tenant_isolation" ON "public"."state_risk_register" TO "authenticated" USING (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid")) WITH CHECK (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid"));



CREATE POLICY "p_survey_responses_tenant_isolation" ON "public"."survey_responses" TO "authenticated" USING (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid")) WITH CHECK (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid"));



CREATE POLICY "p_surveys_tenant_isolation" ON "public"."surveys" TO "authenticated" USING (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid")) WITH CHECK (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid"));



CREATE POLICY "p_verifications_tenant_isolation" ON "public"."verifications" TO "authenticated" USING (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid")) WITH CHECK (("tenant_id" = ((("auth"."jwt"() -> 'app_metadata'::"text") ->> 'tenant_id'::"text"))::"uuid"));



ALTER TABLE "public"."psoe_assessments" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."regulatory_reports" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."reports" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."risk_register" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."safety_deficiencies" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."state_risk_register" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."survey_responses" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."surveys" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."verifications" ENABLE ROW LEVEL SECURITY;




ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";


GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";





































































































































































GRANT ALL ON TABLE "public"."cans" TO "anon";
GRANT ALL ON TABLE "public"."cans" TO "authenticated";
GRANT ALL ON TABLE "public"."cans" TO "service_role";



GRANT ALL ON TABLE "public"."caps" TO "anon";
GRANT ALL ON TABLE "public"."caps" TO "authenticated";
GRANT ALL ON TABLE "public"."caps" TO "service_role";



GRANT ALL ON TABLE "public"."closures" TO "anon";
GRANT ALL ON TABLE "public"."closures" TO "authenticated";
GRANT ALL ON TABLE "public"."closures" TO "service_role";



GRANT ALL ON TABLE "public"."corrective_actions" TO "anon";
GRANT ALL ON TABLE "public"."corrective_actions" TO "authenticated";
GRANT ALL ON TABLE "public"."corrective_actions" TO "service_role";



GRANT ALL ON TABLE "public"."flight_diversions" TO "anon";
GRANT ALL ON TABLE "public"."flight_diversions" TO "authenticated";
GRANT ALL ON TABLE "public"."flight_diversions" TO "service_role";



GRANT ALL ON TABLE "public"."hazard_assessments" TO "anon";
GRANT ALL ON TABLE "public"."hazard_assessments" TO "authenticated";
GRANT ALL ON TABLE "public"."hazard_assessments" TO "service_role";



GRANT ALL ON TABLE "public"."hazard_capas" TO "anon";
GRANT ALL ON TABLE "public"."hazard_capas" TO "authenticated";
GRANT ALL ON TABLE "public"."hazard_capas" TO "service_role";



GRANT ALL ON TABLE "public"."hazard_rca_entries" TO "anon";
GRANT ALL ON TABLE "public"."hazard_rca_entries" TO "authenticated";
GRANT ALL ON TABLE "public"."hazard_rca_entries" TO "service_role";



GRANT ALL ON TABLE "public"."hazard_rca_factors" TO "anon";
GRANT ALL ON TABLE "public"."hazard_rca_factors" TO "authenticated";
GRANT ALL ON TABLE "public"."hazard_rca_factors" TO "service_role";



GRANT ALL ON TABLE "public"."hazards" TO "anon";
GRANT ALL ON TABLE "public"."hazards" TO "authenticated";
GRANT ALL ON TABLE "public"."hazards" TO "service_role";



GRANT ALL ON TABLE "public"."psoe_assessments" TO "anon";
GRANT ALL ON TABLE "public"."psoe_assessments" TO "authenticated";
GRANT ALL ON TABLE "public"."psoe_assessments" TO "service_role";



GRANT ALL ON TABLE "public"."regulatory_reports" TO "anon";
GRANT ALL ON TABLE "public"."regulatory_reports" TO "authenticated";
GRANT ALL ON TABLE "public"."regulatory_reports" TO "service_role";



GRANT ALL ON TABLE "public"."reports" TO "anon";
GRANT ALL ON TABLE "public"."reports" TO "authenticated";
GRANT ALL ON TABLE "public"."reports" TO "service_role";



GRANT ALL ON TABLE "public"."risk_register" TO "anon";
GRANT ALL ON TABLE "public"."risk_register" TO "authenticated";
GRANT ALL ON TABLE "public"."risk_register" TO "service_role";



GRANT ALL ON TABLE "public"."safety_deficiencies" TO "anon";
GRANT ALL ON TABLE "public"."safety_deficiencies" TO "authenticated";
GRANT ALL ON TABLE "public"."safety_deficiencies" TO "service_role";



GRANT ALL ON TABLE "public"."state_risk_register" TO "anon";
GRANT ALL ON TABLE "public"."state_risk_register" TO "authenticated";
GRANT ALL ON TABLE "public"."state_risk_register" TO "service_role";



GRANT ALL ON TABLE "public"."survey_responses" TO "anon";
GRANT ALL ON TABLE "public"."survey_responses" TO "authenticated";
GRANT ALL ON TABLE "public"."survey_responses" TO "service_role";



GRANT ALL ON TABLE "public"."surveys" TO "anon";
GRANT ALL ON TABLE "public"."surveys" TO "authenticated";
GRANT ALL ON TABLE "public"."surveys" TO "service_role";



GRANT ALL ON TABLE "public"."verifications" TO "anon";
GRANT ALL ON TABLE "public"."verifications" TO "authenticated";
GRANT ALL ON TABLE "public"."verifications" TO "service_role";









ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";































