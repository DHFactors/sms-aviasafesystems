SEED_VERSION = "2.1.0"
SEED_DOC_PATH = "seed_metadata/seed"

SURVEY_COLLECTION = "surveys"
STATE_RISK_REFERENCE_PATH = "state/icao_top_risks/categories"

from app.core.config import settings

# Seed user password is env-driven (DEFAULT_SEED_PASSWORD). Empty when unset so
# seeding fails closed rather than using a hardcoded default.
DEMO_USER_PASSWORD = settings.DEFAULT_SEED_PASSWORD or ""

ICAO_SMS_PILLARS = [
    "safety_policy",
    "safety_risk_management",
    "safety_assurance",
    "safety_promotion",
]

ICAO_SMS_PILLAR_LABELS = {
    "safety_policy": "Safety Policy",
    "safety_risk_management": "Safety Risk Management",
    "safety_assurance": "Safety Assurance",
    "safety_promotion": "Safety Promotion",
}

ICAO_SMS_ELEMENTS = {
    "safety_policy": [
        "management_commitment",
        "safety_accountability",
        "key_safety_personnel",
        "emergency_response_planning",
        "sms_documentation",
    ],
    "safety_risk_management": [
        "hazard_identification",
        "risk_assessment_and_mitigation",
    ],
    "safety_assurance": [
        "safety_performance_monitoring",
        "management_of_change",
        "continuous_improvement",
    ],
    "safety_promotion": [
        "training_and_education",
        "safety_communication",
    ],
}

ICAO_ELEMENT_LABELS = {
    "management_commitment": "Management Commitment and Responsibility",
    "safety_accountability": "Safety Accountability and Responsibilities",
    "key_safety_personnel": "Appointment of Key Safety Personnel",
    "emergency_response_planning": "Coordination of Emergency Response Planning",
    "sms_documentation": "SMS Documentation",
    "hazard_identification": "Hazard Identification",
    "risk_assessment_and_mitigation": "Safety Risk Assessment and Mitigation",
    "safety_performance_monitoring": "Safety Performance Monitoring and Measurement",
    "management_of_change": "Management of Change",
    "continuous_improvement": "Continuous Improvement of the SMS",
    "training_and_education": "Training and Education",
    "safety_communication": "Safety Communication",
}

ALL_ICAO_ELEMENTS = []
for elements in ICAO_SMS_ELEMENTS.values():
    ALL_ICAO_ELEMENTS.extend(elements)

SURVEY_DEPARTMENTS = [
    "Flight Operations",
    "Cabin Crew",
    "Ground Handling",
    "Engineering & Maintenance",
    "Dispatch",
    "Safety & Quality",
    "Training",
    "Management",
    "Flight Safety",
    "Operations Control",
]

# ============================================================================
# 10-Tenant Beta configuration (2026-08-14)
#
# OPERATOR_PROFILES holds the 10 active service-provider tenants of the beta
# set, covering every tenant type (airline, helicopter-operator, mro, aerodrome,
# ground-handling). The former legacy seed operators (yeti-airlines, summit-air,
# sita-air, simrik-air, tara-air) were re-activated and moved into
# OPERATOR_PROFILES; LEGACY_OPERATOR_PROFILES is now empty.
#
# Seeding rules - randomized realistic volumes per provider:
#   vsr_count + mor_count in [25, 40] with ~70% VSR / 30% MOR
#   strict 90:10 VSR anonymity ratio -> ~63% overall Anon Rate
#   survey_count in [15, 25]
#   flight_diversion_count = 10 for airline + helicopter-operator,
#                            0 for mro / aerodrome / ground-handling
# ============================================================================

TENANT_TYPES = {
    "airline",
    "helicopter-operator",
    "mro",
    "aerodrome",
    "ground-handling",
    "state-regulator",
}
BETA_SERVICE_PROVIDER_TYPES = TENANT_TYPES - {"state-regulator"}
FLIGHT_OPERATOR_TYPES = {"airline", "helicopter-operator"}

OPERATOR_PROFILES = [
    {
        "id": "buddha-air",
        "name": "Buddha Air",
        "type": "airline",
        "tenant_type": "airline",
        "icao": "BHA",
        "iata": "U4",
        "country": "Nepal",
        "base": "Kathmandu (KTM/VNKT)",
        "fleet_size": 18,
        "employees": 1200,
        "survey_count": 22,
        "vsr_count": 24,
        "mor_count": 10,
        "hazard_count": 16,
        "can_count": 11,
        "flight_diversion_count": 10,
        "element_scores": {
            "management_commitment": 4.3,
            "safety_accountability": 4.1,
            "key_safety_personnel": 4.2,
            "emergency_response_planning": 4.0,
            "sms_documentation": 4.2,
            "hazard_identification": 3.5,
            "risk_assessment_and_mitigation": 3.7,
            "safety_performance_monitoring": 3.9,
            "management_of_change": 3.8,
            "continuous_improvement": 4.0,
            "training_and_education": 4.0,
            "safety_communication": 3.3,
        },
        "culture_variance": 0.45,
        "culture_description": "Strong Safety Policy and Safety Promotion pillars; Safety Risk Management needs attention",
        "vsr_risk_mean": 0.42,
        "vsr_risk_std": 0.18,
        "mor_risk_mean": 0.55,
        "mor_risk_std": 0.20,
        "anonymous_rate": 0.30,
        "aircraft_types": ["Beechcraft 1900D", "ATR 42-320", "ATR 72-500"],
        "flight_number_prefixes": ["U4-", "BHA-"],
        "routes": ["KTM-PKR", "KTM-SDR", "KTM-BWA", "KTM-JKR", "KTM-BHR", "KTM-TPN", "KTM-DP"],
        "email_domain": "buddhaair.com",
    },
    {
        "id": "air-dynasty",
        "name": "Air Dynasty Heli Services",
        "type": "helicopter-operator",
        "tenant_type": "helicopter-operator",
        "icao": "ADH",
        "iata": "–",
        "country": "Nepal",
        "base": "Kathmandu (KTM/VNKT)",
        "fleet_size": 10,
        "employees": 200,
        "survey_count": 18,
        "vsr_count": 22,
        "mor_count": 10,
        "hazard_count": 14,
        "can_count": 10,
        "flight_diversion_count": 10,
        "element_scores": {
            "management_commitment": 3.6,
            "safety_accountability": 3.4,
            "key_safety_personnel": 3.7,
            "emergency_response_planning": 3.8,
            "sms_documentation": 3.6,
            "hazard_identification": 4.1,
            "risk_assessment_and_mitigation": 4.3,
            "safety_performance_monitoring": 3.5,
            "management_of_change": 3.3,
            "continuous_improvement": 3.2,
            "training_and_education": 3.1,
            "safety_communication": 3.9,
        },
        "culture_variance": 0.45,
        "culture_description": "Excellent Safety Risk Management driven by helicopter terrain demands; Safety Assurance needs development",
        "vsr_risk_mean": 0.50,
        "vsr_risk_std": 0.20,
        "mor_risk_mean": 0.62,
        "mor_risk_std": 0.18,
        "anonymous_rate": 0.32,
        "aircraft_types": ["Airbus AS350 Écureuil", "Bell 407", "Bell 429 GlobalRanger", "Eurocopter EC135"],
        "flight_number_prefixes": ["ADH-"],
        "routes": ["KTM-SYX", "KTM-OGU", "KTM-LUA", "KTM-EBO", "KTM-KEP", "KTM-DP"],
        "email_domain": "airdynasty.com.np",
    },
    {
        "id": "ktm-mro",
        "name": "Kathmandu MRO Services",
        "type": "mro",
        "tenant_type": "mro",
        "icao": "",
        "iata": "",
        "country": "Nepal",
        "base": "Kathmandu (KTM/VNKT)",
        "fleet_size": 0,
        "employees": 180,
        "survey_count": 16,
        "vsr_count": 23,
        "mor_count": 10,
        "hazard_count": 15,
        "can_count": 10,
        "flight_diversion_count": 0,
        "element_scores": {
            "management_commitment": 3.6,
            "safety_accountability": 3.5,
            "key_safety_personnel": 3.7,
            "emergency_response_planning": 3.4,
            "sms_documentation": 3.6,
            "hazard_identification": 3.5,
            "risk_assessment_and_mitigation": 3.8,
            "safety_performance_monitoring": 3.4,
            "management_of_change": 3.3,
            "continuous_improvement": 3.4,
            "training_and_education": 3.6,
            "safety_communication": 3.2,
        },
        "culture_variance": 0.45,
        "culture_description": "Solid maintenance SMS culture; Safety Risk Management leads, Safety Assurance needs attention",
        "vsr_risk_mean": 0.44,
        "vsr_risk_std": 0.19,
        "mor_risk_mean": 0.58,
        "mor_risk_std": 0.20,
        "anonymous_rate": 0.31,
        "aircraft_types": ["Airbus A320 family", "ATR 72", "DHC-6 Twin Otter", "AS350 B3"],
        "flight_number_prefixes": [],
        "routes": ["KTM-VNKT"],
        "email_domain": "ktm-mro.com",
    },
    {
        "id": "pokhara-aerodrome",
        "name": "Pokhara Regional Aerodrome",
        "type": "aerodrome",
        "tenant_type": "aerodrome",
        "icao": "",
        "iata": "",
        "country": "Nepal",
        "base": "Pokhara (PKR/VNPK)",
        "fleet_size": 0,
        "employees": 90,
        "survey_count": 15,
        "vsr_count": 18,
        "mor_count": 8,
        "hazard_count": 13,
        "can_count": 9,
        "flight_diversion_count": 0,
        "element_scores": {
            "management_commitment": 3.4,
            "safety_accountability": 3.3,
            "key_safety_personnel": 3.5,
            "emergency_response_planning": 3.6,
            "sms_documentation": 3.3,
            "hazard_identification": 3.2,
            "risk_assessment_and_mitigation": 3.4,
            "safety_performance_monitoring": 3.3,
            "management_of_change": 3.2,
            "continuous_improvement": 3.1,
            "training_and_education": 3.2,
            "safety_communication": 3.3,
        },
        "culture_variance": 0.45,
        "culture_description": "Emerging aerodrome SMS with strong emergency response planning; hazard identification needs development",
        "vsr_risk_mean": 0.43,
        "vsr_risk_std": 0.19,
        "mor_risk_mean": 0.57,
        "mor_risk_std": 0.20,
        "anonymous_rate": 0.35,
        "aircraft_types": [],
        "flight_number_prefixes": [],
        "routes": ["PKR-VNPK"],
        "email_domain": "pokhara-aerodrome.com",
    },
    {
        "id": "himalaya-ground-services",
        "name": "Himalaya Ground Handling",
        "type": "ground-handling",
        "tenant_type": "ground-handling",
        "icao": "",
        "iata": "",
        "country": "Nepal",
        "base": "Kathmandu (KTM/VNKT)",
        "fleet_size": 0,
        "employees": 120,
        "survey_count": 15,
        "vsr_count": 18,
        "mor_count": 8,
        "hazard_count": 13,
        "can_count": 9,
        "flight_diversion_count": 0,
        "element_scores": {
            "management_commitment": 3.1,
            "safety_accountability": 3.0,
            "key_safety_personnel": 3.2,
            "emergency_response_planning": 3.3,
            "sms_documentation": 2.9,
            "hazard_identification": 3.0,
            "risk_assessment_and_mitigation": 3.1,
            "safety_performance_monitoring": 2.9,
            "management_of_change": 2.8,
            "continuous_improvement": 2.9,
            "training_and_education": 3.0,
            "safety_communication": 2.8,
        },
        "culture_variance": 0.50,
        "culture_description": "Developing ground-handling SMS; Safety Promotion and Assurance need strengthening",
        "vsr_risk_mean": 0.47,
        "vsr_risk_std": 0.20,
        "mor_risk_mean": 0.61,
        "mor_risk_std": 0.19,
        "anonymous_rate": 0.33,
        "aircraft_types": [],
        "flight_number_prefixes": [],
        "routes": ["KTM-VNKT"],
        "email_domain": "himalaya-ground-services.com",
    },
    {
        "id": "yeti-airlines",
        "name": "Yeti Airlines",
        "type": "airline",
        "tenant_type": "airline",
        "icao": "NYT",
        "iata": "YT",
        "country": "Nepal",
        "base": "Kathmandu (KTM/VNKT)",
        "fleet_size": 12,
        "employees": 850,
        "survey_count": 24,
        "vsr_count": 26,
        "mor_count": 11,
        "hazard_count": 16,
        "can_count": 11,
        "flight_diversion_count": 10,
        "element_scores": {
            "management_commitment": 3.8,
            "safety_accountability": 4.2,
            "key_safety_personnel": 3.6,
            "emergency_response_planning": 3.5,
            "sms_documentation": 3.8,
            "hazard_identification": 4.3,
            "risk_assessment_and_mitigation": 4.1,
            "safety_performance_monitoring": 4.0,
            "management_of_change": 3.9,
            "continuous_improvement": 4.2,
            "training_and_education": 4.2,
            "safety_communication": 3.8,
        },
        "culture_variance": 0.50,
        "culture_description": "Strong Safety Risk Management and Safety Assurance following safety transformation",
        "vsr_risk_mean": 0.38,
        "vsr_risk_std": 0.20,
        "mor_risk_mean": 0.52,
        "mor_risk_std": 0.22,
        "anonymous_rate": 0.32,
        "aircraft_types": ["ATR 72-500", "ATR 42-320", "de Havilland DHC-6 Twin Otter"],
        "flight_number_prefixes": ["YT-", "NYT-"],
        "routes": ["KTM-PKR", "KTM-BWA", "KTM-JKR", "KTM-DP", "KTM-SIF", "KTM-TPN", "KTM-LUA"],
        "email_domain": "yetiairlines.com",
    },
    {
        "id": "summit-air",
        "name": "Summit Air",
        "type": "airline",
        "tenant_type": "airline",
        "icao": "SMM",
        "iata": "–",
        "country": "Nepal",
        "base": "Kathmandu (KTM/VNKT)",
        "fleet_size": 8,
        "employees": 350,
        "survey_count": 20,
        "vsr_count": 22,
        "mor_count": 10,
        "hazard_count": 14,
        "can_count": 10,
        "flight_diversion_count": 10,
        "element_scores": {
            "management_commitment": 3.0,
            "safety_accountability": 2.8,
            "key_safety_personnel": 3.1,
            "emergency_response_planning": 3.2,
            "sms_documentation": 3.0,
            "hazard_identification": 3.5,
            "risk_assessment_and_mitigation": 3.8,
            "safety_performance_monitoring": 3.3,
            "management_of_change": 3.2,
            "continuous_improvement": 3.3,
            "training_and_education": 3.1,
            "safety_communication": 3.5,
        },
        "culture_variance": 0.55,
        "culture_description": "Safety Policy pillar needs strengthening; Safety Risk Management is adequate given STOL experience",
        "vsr_risk_mean": 0.48,
        "vsr_risk_std": 0.22,
        "mor_risk_mean": 0.60,
        "mor_risk_std": 0.18,
        "anonymous_rate": 0.31,
        "aircraft_types": ["Dornier Do 228", "Let L-410 Turbolet", "de Havilland DHC-6 Twin Otter"],
        "flight_number_prefixes": ["SMM-"],
        "routes": ["KTM-SIF", "KTM-DP", "KTM-LUA", "KTM-TPN", "KTM-BJP"],
        "email_domain": "summitair.com.np",
    },
    {
        "id": "sita-air",
        "name": "Sita Air",
        "type": "airline",
        "tenant_type": "airline",
        "icao": "SAA",
        "iata": "ST",
        "country": "Nepal",
        "base": "Kathmandu (KTM/VNKT)",
        "fleet_size": 6,
        "employees": 280,
        "survey_count": 18,
        "vsr_count": 24,
        "mor_count": 10,
        "hazard_count": 15,
        "can_count": 11,
        "flight_diversion_count": 10,
        "element_scores": {
            "management_commitment": 3.8,
            "safety_accountability": 3.7,
            "key_safety_personnel": 3.8,
            "emergency_response_planning": 3.7,
            "sms_documentation": 3.9,
            "hazard_identification": 3.9,
            "risk_assessment_and_mitigation": 4.0,
            "safety_performance_monitoring": 3.8,
            "management_of_change": 3.6,
            "continuous_improvement": 3.5,
            "training_and_education": 3.5,
            "safety_communication": 3.7,
        },
        "culture_variance": 0.40,
        "culture_description": "Consistent SMS capability across all pillars with strong hazard awareness",
        "vsr_risk_mean": 0.45,
        "vsr_risk_std": 0.20,
        "mor_risk_mean": 0.58,
        "mor_risk_std": 0.19,
        "anonymous_rate": 0.28,
        "aircraft_types": ["de Havilland DHC-6 Twin Otter", "Dornier Do 228"],
        "flight_number_prefixes": ["ST-", "SAA-"],
        "routes": ["KTM-PKR", "KTM-SIF", "KTM-DP", "KTM-LUA", "KTM-TPN"],
        "email_domain": "sitaair.com.np",
    },
    {
        "id": "simrik-air",
        "name": "Simrik Air",
        "type": "helicopter-operator",
        "tenant_type": "helicopter-operator",
        "icao": "RMK",
        "iata": "–",
        "country": "Nepal",
        "base": "Pokhara (PKR/VNPK)",
        "fleet_size": 7,
        "employees": 150,
        "survey_count": 17,
        "vsr_count": 21,
        "mor_count": 9,
        "hazard_count": 14,
        "can_count": 10,
        "flight_diversion_count": 10,
        "element_scores": {
            "management_commitment": 3.3,
            "safety_accountability": 3.8,
            "key_safety_personnel": 3.5,
            "emergency_response_planning": 3.6,
            "sms_documentation": 3.4,
            "hazard_identification": 3.7,
            "risk_assessment_and_mitigation": 3.9,
            "safety_performance_monitoring": 3.6,
            "management_of_change": 3.5,
            "continuous_improvement": 3.6,
            "training_and_education": 3.5,
            "safety_communication": 3.4,
        },
        "culture_variance": 0.50,
        "culture_description": "Balanced SMS capability with consistent Safety Risk Management; Safety Communication and Policy need attention",
        "vsr_risk_mean": 0.46,
        "vsr_risk_std": 0.21,
        "mor_risk_mean": 0.59,
        "mor_risk_std": 0.20,
        "anonymous_rate": 0.30,
        "aircraft_types": ["Airbus AS350 Écureuil", "Bell 407"],
        "flight_number_prefixes": ["RMK-"],
        "routes": ["PKR-JMO", "PKR-KEP", "PKR-DP", "PKR-SYX", "PKR-MUG"],
        "email_domain": "simrikair.com",
    },
    {
        "id": "tara-air",
        "name": "Tara Air",
        "type": "airline",
        "tenant_type": "airline",
        "icao": "THR",
        "iata": "TP",
        "country": "Nepal",
        "base": "Kathmandu (KTM/VNKT)",
        "fleet_size": 5,
        "employees": 180,
        "survey_count": 19,
        "vsr_count": 23,
        "mor_count": 10,
        "hazard_count": 15,
        "can_count": 11,
        "flight_diversion_count": 10,
        "element_scores": {
            "management_commitment": 3.7,
            "safety_accountability": 3.6,
            "key_safety_personnel": 3.8,
            "emergency_response_planning": 3.7,
            "sms_documentation": 3.6,
            "hazard_identification": 4.2,
            "risk_assessment_and_mitigation": 4.1,
            "safety_performance_monitoring": 3.5,
            "management_of_change": 3.4,
            "continuous_improvement": 3.3,
            "training_and_education": 3.4,
            "safety_communication": 3.5,
        },
        "culture_variance": 0.45,
        "culture_description": "Strong hazard identification and risk management in demanding mountain STOL operations; Safety Promotion needs attention",
        "vsr_risk_mean": 0.47,
        "vsr_risk_std": 0.21,
        "mor_risk_mean": 0.60,
        "mor_risk_std": 0.19,
        "anonymous_rate": 0.29,
        "aircraft_types": ["de Havilland DHC-6 Twin Otter", "Dornier 228"],
        "flight_number_prefixes": ["TP-", "THR-"],
        "routes": ["KTM-LUA", "KTM-IMK", "KTM-JUM", "KTM-DPR", "KTM-TPJ", "KTM-KEP"],
        "email_domain": "taraair.com",
    },
]

# ---------------------------------------------------------------------------
# Archived legacy seed operators. All former legacy operators (yeti-airlines,
# summit-air, sita-air, simrik-air, tara-air) were re-activated and moved into
# OPERATOR_PROFILES on 2026-08-14. The runner now seeds all 10 tenants.
# ---------------------------------------------------------------------------
LEGACY_OPERATOR_PROFILES = []

NEPAL_AIRPORTS = [
    "Kathmandu (VNKT)",
    "Pokhara (VNPK)",
    "Bharatpur (VNBG)",
    "Biratnagar (VNST)",
    "Janakpur (VNJP)",
    "Dhangadhi (VNDH)",
    "Nepalgunj (VNKG)",
    "Siddharthanagar (VNBW)",
    "Simara (VNSI)",
    "Tulsipur (VNSB)",
    "Bajhang (VNBJ)",
    "Bajura (VNBR)",
    "Bhojpur (VNBJ)",
    "Chandragadhi (VNCH)",
    "Darchula (VNDL)",
    "Dolpa (VNDP)",
    "Jomsom (VNJS)",
    "Jumla (VNJL)",
    "Kangel Danda (VNDG)",
    "Langtang (VNLT)",
    "Lukla (VNLK)",
    "Manang (VNMA)",
    "Mugu (VNMU)",
    "Rajbiraj (VNRB)",
    "Ramechhap (VNRM)",
    "Rara (VNRR)",
    "Rukum Salle (VNRK)",
    "Sanfebagar (VNSR)",
    "Simikot (VNSK)",
    "Surkhet (VNSK)",
    "Taplejung (VNTJ)",
    "Thamkharka (VNTH)",
    "Tumlingtar (VNTM)",
]

NEPALI_NAMES = [
    "Rajesh Sharma", "Anita Gurung", "Prakash Thapa", "Sunita Rai",
    "Bishnu KC", "Maya Tamang", "Ramesh Adhikari", "Sita Poudel",
    "Gopal Bhattarai", "Kamala Neupane", "Hari Singh", "Sarita Magar",
    "Krishna Pokharel", "Reema Sharma", "Mohan Shrestha", "Pabitra Thapa",
    "Sagar Karki", "Deepa Acharya", "Nabin Poudel", "Bina Basnet",
    "Dipak Rana", "Kabita Rai", "Rajan Gurung", "Sabita Tamang",
    "Tika Ram Bhandari", "Gita Ghimire", "Umesh Pandey", "Indira Chapagain",
    "Yam Bahadur Chettri", "Laxmi Maharjan", "Bharat Kumar Shah", "Anita Shrestha",
    "Suman Ale Magar", "Radhika Neupane", "Pradip Malla", "Saraswoti Khadka",
    "Tek Bahadur Thapa", "Nirmala Koirala", "Hom Nath Aryal", "Sushila Shrestha",
    "Binod Chaudhary", "Rita Dhakal", "Kedar Nath Ghimire", "Pramila Kandel",
    "Ganesh Acharya", "Shova Bhatta", "Lok Bahadur Basnet", "Mina Thapa",
    "Narayan Silwal", "Chanda Devi Yadav",
]

AIRCRAFT_REGISTRATIONS = {
    "buddha-air": ["9N-AKO", "9N-AKQ", "9N-AKR", "9N-AKS", "9N-AKT", "9N-AKU", "9N-AKV",
                   "9N-AKW", "9N-AKX", "9N-AKY", "9N-AKZ", "9N-ALB", "9N-ALC", "9N-ALD",
                   "9N-ALE", "9N-ALF", "9N-ALG", "9N-ALH"],
    "yeti-airlines": ["9N-ALJ", "9N-ALK", "9N-ALL", "9N-ALM", "9N-ALN", "9N-ALP",
                      "9N-ALQ", "9N-ALR", "9N-ALS", "9N-ALT", "9N-ALU", "9N-ALV"],
    "summit-air": ["9N-AMC", "9N-AMD", "9N-AME", "9N-AMF", "9N-AMG", "9N-AMH", "9N-AMI", "9N-AMJ"],
    "sita-air": ["9N-AMK", "9N-AML", "9N-AMM", "9N-AMN", "9N-AMP", "9N-AMQ"],
    "air-dynasty": ["9N-AMR", "9N-AMS", "9N-AMT", "9N-AMU", "9N-AMV", "9N-AMW", "9N-AMX",
                    "9N-AMY", "9N-AMZ", "9N-ANA"],
    "simrik-air": ["9N-ANB", "9N-ANC", "9N-AND", "9N-ANE", "9N-ANF", "9N-ANG", "9N-ANH"],
    "tara-air": ["9N-APB", "9N-APC", "9N-APD", "9N-APE", "9N-APF"],
}

GENERIC_MOR_OCCURRENCE_TYPES = [
    "Bird Strike",
    "Runway Incursion",
    "System/Component Failure",
    "Abnormal Runway Contact",
    "Powerplant Failure",
    "Weather Encounter",
    "Airborne Conflict",
    "Runway Excursion",
    "Ground Collision",
    "Cabin Safety Event",
    "ATC Operational Incident",
    "Procedural Deviation",
    "Other",
]

VSR_OCCURRENCE_TYPES = [
    "Near Miss",
    "Unsafe Condition",
    "Fatigue",
    "Human Factors",
    "SOP Deviation",
    "Ground Handling",
    "FOD",
    "Weather",
    "Communication",
    "Maintenance Hazard",
    "Ramp Safety",
    "CRM",
    "Dispatch",
    "Training",
    "Cabin Safety",
    "Security",
    "Bird Activity",
    "Other",
]

VSR_NARRATIVE_TEMPLATES = [
    "While conducting {operation} at {location}, I observed {observation}. The {situation} could have led to {consequence}. I believe this hazard exists because {cause}. I recommend {recommendation}.",
    "During {operation} on {date_qualifier}, {subject} was noted to be {condition}. This is a potential safety concern as {reason}. Previous similar instances have been noted {frequency}.",
    "This report concerns {topic}. While {context}, I noticed that {issue}. The contributing factors appear to be {factors}. Corrective action should include {action}.",
    "I am reporting {subject} following the {operation} on {date_qualifier}. The {situation} resulted in {outcome}. No injury occurred but {potential}. This has been reported to {reported_to}.",
]

VSR_NARRATIVE_KEYWORDS = {
    "operation": [
        "pre-flight inspection", "taxi procedure", "approach to landing",
        "passenger boarding", "cargo loading", "maintenance check",
        "fueling operation", "pushback", "de-icing procedure",
        "ground power connection", "walk-around inspection",
    ],
    "location": [
        "gate area", "ramp", "hangar bay", "runway threshold",
        "apron", "maintenance dock", "fuel farm",
    ],
    "observation": [
        "a loose panel on the fuselage", "an oil leak near the engine cowling",
        "inadequate lighting in the cargo hold", "a cracked seat track",
        "debris scattered across the taxiway", "a damaged ground cable",
        "an unsecured access panel",
    ],
    "situation": [
        "situation", "condition", "scenario", "circumstance",
    ],
    "consequence": [
        "a serious incident", "damage to aircraft systems",
        "injury to ground personnel", "a flight delay",
        "an in-flight emergency", "a runway excursion",
        "a ground collision",
    ],
    "cause": [
        "insufficient supervision during night shift",
        "lack of proper training on this equipment",
        "inadequate maintenance procedures",
        "communication breakdown between shifts",
        "fatigue due to extended duty period",
        "pressure to meet departure schedule",
    ],
    "recommendation": [
        "additional training for all relevant staff",
        "revised procedures with clearer guidance",
        "installation of better lighting", "regular inspections of this area",
        "a review of duty hour policies", "improved signage and markings",
    ],
    "date_qualifier": [
        "the morning shift", "last night's operation", "today's first flight",
        "the late evening departure", "the overnight turnaround",
    ],
    "subject": [
        "a ground power unit", "the baggage handling system",
        "the aircraft refueling operation", "a passenger stair truck",
        "the de-icing equipment", "a tow tractor",
    ],
    "condition": [
        "showing signs of hydraulic leakage",
        "operating intermittently with unexpected shutdowns",
        "positioned too close to the wingtip",
        "emitting unusual noise during operation",
        "not properly secured during transit",
    ],
    "reason": [
        "it poses a direct risk to ground staff and aircraft",
        "similar issues have caused incidents at other operators",
        "the condition could worsen during peak operations",
    ],
    "frequency": [
        "regularly", "intermittently over the past month",
        "three times this week alone", "sporadically for several weeks",
    ],
    "topic": [
        "a recurrent cabin pressurization issue",
        "inadequate signage on the apron",
        "fatigue management in the dispatch office",
        "training gaps for new ground staff",
        "communication difficulties between cockpit and cabin crew",
    ],
    "context": [
        "conducting routine operations", "performing the daily inspection",
        "completing the turnaround checklist", "supervising ground operations",
    ],
    "issue": [
        "procedures are not being followed consistently",
        "safety equipment is not readily accessible",
        "communication protocols are unclear",
        "reporting lines are confusing for new staff",
    ],
    "factors": [
        "time pressure and staffing shortages",
        "inadequate supervision and unclear procedures",
        "fatigue and lack of experience",
    ],
    "action": [
        "a review of current procedures", "additional training for all shifts",
        "better communication of safety protocols",
        "a physical modification to the equipment",
    ],
    "outcome": [
        "a hard landing", "a rejected takeoff", "an evasive maneuver",
        "a go-around", "abnormal system indications",
    ],
    "potential": [
        "the potential for a more serious outcome was high",
        "this could have resulted in injury",
        "the risk of recurrence is significant",
    ],
    "reported_to": [
        "the shift supervisor", "the safety department",
        "the station manager", "the duty engineer",
    ],
}

HUMAN_FACTORS_CATEGORIES = [
    "Decision Making Error",
    "Skill-Based Error",
    "Perceptual Error",
    "Fatigue",
    "Complacency",
    "Pressure",
    "Lack of Knowledge",
    "Communication Breakdown",
    "Situational Awareness (Loss of)",
    "Distraction",
    "Workload Management",
    "Procedural Non-Compliance",
]

PHASES_OF_FLIGHT = [
    "Standing", "Taxi", "Takeoff", "Initial Climb",
    "Climb", "Cruise", "Descent",
    "Approach", "Landing", "Go-Around",
]

MOR_NARRATIVE_TEMPLATES = [
    "A mandatory occurrence involving {event_type} occurred during {phase} at {airport}. The aircraft {registration} was operating flight {flight} from {origin} to {destination}. {description}. Damage assessment: {damage}. No fatalities reported. Investigation {investigation_status}.",
    "Reportable occurrence: {event_type} while {operation} on aircraft {registration}. Flight {flight} from {origin} to {destination}. {description}. The {system} was {condition}. Regulatory reference: {regulation}. Final report {report_status}.",
    "Mandatory occurrence report for {event_type}. Operator: {operator}. Aircraft: {registration}. {description}. Actions taken: {actions}. This occurrence is reportable under {regulation}.",
]

MOR_NARRATIVE_KEYWORDS = {
    "event_type": [
        "a bird strike", "a runway incursion", "a technical failure",
        "an engine shutdown in flight", "a hard landing", "a dangerous goods incident",
        "a wildlife strike", "an airspace infringement", "a navigation event",
        "a maintenance occurrence",
    ],
    "phase": [
        "the approach phase", "final approach", "the landing roll",
        "initial climb", "takeoff run", "cruise", "descent",
    ],
    "description": [
        "The flight crew reported a loud bang followed by vibration. Post-flight inspection revealed damage to the leading edge.",
        "Air traffic control issued a go-around after detecting conflicting traffic on the runway. No further issues.",
        "During pre-flight inspection, ground crew observed fluid leaking from the engine nacelle. Engineering was notified.",
        "The aircraft experienced a sudden loss of cabin pressure at FL250. Emergency descent was initiated.",
        "Upon touchdown, the crew felt a severe impact. Subsequent inspection revealed structural deformation.",
        "Ground personnel observed a foreign object on the runway during inspection. Operations were temporarily suspended.",
    ],
    "damage": [
        "Minor damage to aircraft structure", "No structural damage reported",
        "Substantial damage requiring repair", "Cosmetic damage only",
        "Engine damage requiring removal and inspection",
    ],
    "investigation_status": [
        "is ongoing", "has been completed", "is pending",
        "has been referred to the manufacturer",
    ],
    "system": [
        "hydraulic system", "electrical system", "landing gear",
        "engine number one", "engine number two", "avionics bay",
        "pressurization system", "flight control system",
    ],
    "condition": [
        "found to be within normal parameters", "showing signs of wear",
        "operating outside permissible limits", "functioning intermittently",
    ],
    "regulation": [
        "CAR-19 Section 4.2", "CAR-19 Section 5.1", "CAR-19 Appendix A",
        "ICAO Annex 19 Chapter 4", "ICAO Annex 13",
    ],
    "report_status": [
        "pending review", "under investigation", "approved for closure",
        "awaiting additional information",
    ],
    "operation": [
        "conducting a training flight", "operating a scheduled service",
        "performing a positioning flight", "on a cargo rotation",
    ],
    "operator": [
        "Buddha Air", "Yeti Airlines", "Summit Air",
        "Sita Air", "Air Dynasty Heli Services", "Simrik Air",
    ],
    "actions": [
        "Engineering issued a service bulletin",
        "The aircraft was grounded for inspection",
        "A safety bulletin was issued to all crews",
        "Additional maintenance checks were scheduled",
        "The occurrence has been entered into the SMS database",
    ],
}

INVESTIGATION_STATUSES = ["NOT_INVESTIGATED", "INVESTIGATING", "INVESTIGATED", "CLOSED"]

# ============================================================================
# Operational personas (2026) — authentic aviation reporting identities
# ============================================================================

# Strict 90:10 VSR anonymity ratio: 90% of generated VSRs are anonymous
# (originator_name "Anonymous (Confidential VSR)", is_anonymous=True,
# contact_details=None); the remaining 10% are named operational personas.
VSR_ANONYMOUS_RATIO = 0.90
VSR_ANONYMOUS_LABEL = "Anonymous (Confidential VSR)"

# Named VSR originators (each with its operational department). Contact details
# are optional and generated per-report.
VSR_ORIGINATOR_PERSONAS = [
    {"name": "Capt. A. Sharma (Line Captain)", "department": "Flight Operations"},
    {"name": "F/O R. Thapa (First Officer)", "department": "Flight Operations"},
    {"name": "S. Shrestha (Ramp / Turnaround Supervisor)", "department": "Ground Operations"},
    {"name": "K. Gurung (Lead Cabin Crew)", "department": "Cabin Services"},
]

# Mandatory Occurrence Report (MOR) originators — routed exclusively through
# technical and compliance authorities.
MOR_ORIGINATOR_AUTHORITIES = [
    "Quality Assurance (QA) Department",
    "CAMO Technical Services (Airworthiness)",
]

PERSONA_ORGANISATIONS = {
    "buddha-air": "Buddha Air",
    "air-dynasty": "Air Dynasty Heli Services",
    "ktm-mro": "Kathmandu MRO Services",
    "pokhara-aerodrome": "Pokhara Regional Aerodrome",
    "himalaya-ground-services": "Himalaya Ground Handling",
    "yeti-airlines": "Yeti Airlines",
    "summit-air": "Summit Air",
    "sita-air": "Sita Air",
    "simrik-air": "Simrik Air",
    "tara-air": "Tara Air",
}

# CAN issuance authority (Corporate Safety).
CAN_ISSUED_BY = "Corporate Safety Manager (Safety Department)"

# Authentic operational postholders a CAN may be addressed to, as
# (postholder, department) tuples. Rotated across CANs so every postholder is
# represented; also drives the CAP `submitted_by` attribution.
CAN_ASSIGNED_POSTHOLDERS = [
    ("Head of Flight Operations", "Flight Operations"),
    ("Head of Maintenance / CAMO", "CAMO / Engineering"),
    ("Ground Operations Manager", "Ground Operations"),
    ("Cabin Safety Manager", "Cabin Services"),
]

# Fishbone (Ishikawa 5M + Management) categories and their demo root causes.
FISHBONE_CATEGORIES = ["Man", "Machine", "Method", "Medium", "Management", "Material"]

FISHBONE_ROOT_CAUSE_POOL = {
    "Man": [
        "Inadequate crew familiarity with the amended procedure",
        "Fatigue-related attention lapse during night duty",
        "Recurring skill gap on the specific task type",
    ],
    "Machine": [
        "Degraded hydraulic component nearing overhaul limit",
        "Sensor / indicating system drift outside tolerance",
        "Aging component with intermittent uncommanded behaviour",
    ],
    "Method": [
        "Task card does not capture the required inspection step",
        "Outdated SOP inconsistent with the current revision",
        "Missing verification step in the sign-off process",
    ],
    "Medium": [
        "Poor apron lighting during low-visibility turnaround",
        "Uncontrolled weather exposure during ramp operations",
        "Cluttered / congested work environment at the stand",
    ],
    "Management": [
        "Insufficient supervisory oversight of the shift",
        "Inadequate resourcing of the maintenance line",
        "Safety requirements not prioritised under schedule pressure",
    ],
    "Material": [
        "Substandard spare part installed on a prior visit",
        "Incorrect lubricant grade used during servicing",
        "Consumable life not tracked in the inventory system",
    ],
}

# CAP action items are generated per root cause (1:1 via root_cause_id).
FISHBONE_ACTION_TEMPLATES = [
    "Conduct refresher training and competency verification",
    "Replace component and re-verify against the maintenance manual",
    "Revise the SOP / task card and publish the amended revision",
    "Improve the work environment controls (lighting / layout)",
    "Reinforce supervisory oversight and shift resourcing",
    "Review the materials / parts traceability process",
]

DEMO_USERS = [
    {
        "uid": "smd-caan-001",
        "email": "smd@caanepal.gov.np",
        "password": DEMO_USER_PASSWORD,
        "full_name": "CAAN Safety Management Department",
        "organization": "CAAN",
        "role": "CAAN_SMD",
        "tenant_id": "caan",
    },
]

# The single State Regulator authority account for CAAN. `smd@caanepal.gov.np`
# is the sole cross-tenant CAAN account (role CAAN_SMD = state-regulator
# inspector authority, tenant caan). No multi-department CAAN accounts exist.
CAAN_REGULATOR_ACCOUNT = DEMO_USERS[0]

# Accounts that automated reset/unseed runs must NEVER delete: the CAAN SMD
# authority, the legacy super-admin/system identities, and any SUPER_ADMIN.
PROTECTED_ADMIN_ACCOUNTS = {
    "emails": {"smd@caanepal.gov.np"},
    "uids": {"smd-caan-001", "super-admin-001", "system"},
    "roles": {"SUPER_ADMIN"},
}

CAAN_TENANT = {
    "id": "caan",
    "name": "Civil Aviation Authority of Nepal",
    "type": "state_regulator",
    "icao": "CAAN",
    "iata": "",
    "country": "Nepal",
    "base": "Kathmandu (KTM/VNKT)",
    "fleet_size": 0,
    "employees": 0,
    "survey_count": 0,
    "culture_description": "State regulator tenant housing the CAAN SMD account.",
    "aircraft_types": [],
    "routes": [],
    "email_domain": "caanepal.gov.np",
}

OPERATOR_USER_TEMPLATES = {}

# ============================================================================
# Simplified credential scheme (2026-08)
#
# Email:   {role}@{tenant}.com          e.g. safety@buddha-air.com
# Password: {TENANT_CODE}-{ROLE}-2026   e.g. BHA-Safety-2026
#
# The ONLY accounts provisioned per operator are the four functional role
# accounts below (legacy Safety Manager / Accountable Executive / Department
# Manager accounts were removed 2026-08-14).
# ============================================================================

CREDENTIAL_TENANT_CODES = {
    "buddha-air": "BHA",
    "air-dynasty": "DYNASTY",
    "ktm-mro": "KTM",
    "pokhara-aerodrome": "PKR",
    "himalaya-ground-services": "HGS",
    "yeti-airlines": "YETI",
    "summit-air": "SUMMIT",
    "sita-air": "SITA",
    "simrik-air": "SIMRIK",
    "tara-air": "TARA",
}

CREDENTIAL_EMAIL_DOMAINS = {
    "buddha-air": "buddha-air.com",
    "air-dynasty": "air-dynasty.com",
    "ktm-mro": "ktm-mro.com",
    "pokhara-aerodrome": "pokhara-aerodrome.com",
    "himalaya-ground-services": "himalaya-ground-services.com",
    "yeti-airlines": "yeti-airlines.com",
    "summit-air": "summit-air.com",
    "sita-air": "sita-air.com",
    "simrik-air": "simrik-air.com",
    "tara-air": "tara-air.com",
}

SIMPLIFIED_ROLE_ACCOUNTS = [
    {"token": "safety", "password_token": "Safety", "app_role": "AIRLINE_ADMIN",
     "full_name": "Safety Manager", "department": ""},
    {"token": "camo", "password_token": "CAMO", "app_role": "USER",
     "full_name": "CAMO Manager", "department": "CAMO"},
    {"token": "145", "password_token": "145", "app_role": "USER",
     "full_name": "Part-145 Maintenance", "department": "Part-145"},
    {"token": "ops", "password_token": "Ops", "app_role": "USER",
     "full_name": "Operations Manager", "department": "Flight Operations"},
]


def simplified_email(role_token: str, op_id: str) -> str:
    """Return the simplified-format email for a role token + operator id."""
    return f"{role_token}@{CREDENTIAL_EMAIL_DOMAINS[op_id]}"


def simplified_password(role_token: str, op_id: str) -> str:
    """Return the simplified-format password for a role token + operator id."""
    code = CREDENTIAL_TENANT_CODES[op_id]
    pwd_token = next(
        (r["password_token"] for r in SIMPLIFIED_ROLE_ACCOUNTS if r["token"] == role_token),
        role_token,
    )
    return f"{code}-{pwd_token}-2026"


def build_simplified_role_plan():
    """Return the full list of simplified role accounts across all operators.

    One account per SIMPLIFIED_ROLE_ACCOUNTS entry for every OPERATOR_PROFILES
    tenant, carrying the RBAC app_role + department claim used by both the
    Auth-provisioning script and the tests.
    """
    plan = []
    for profile in OPERATOR_PROFILES:
        op_id = profile["id"]
        for role in SIMPLIFIED_ROLE_ACCOUNTS:
            plan.append({
                "op_id": op_id,
                "op_name": profile["name"],
                "token": role["token"],
                "email": simplified_email(role["token"], op_id),
                "password": simplified_password(role["token"], op_id),
                "app_role": role["app_role"],
                "department": role.get("department") or "",
                "full_name": f"{role['full_name']} ({profile['name']})",
                "uid": f"{role['token']}-{op_id}-001",
            })
    return plan
