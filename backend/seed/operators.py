import sys
from datetime import datetime, timedelta, timezone
from typing import Optional
from loguru import logger

from seed.config import (
    OPERATOR_PROFILES,
    CAAN_TENANT,
    SEED_VERSION,
    BETA_SERVICE_PROVIDER_TYPES,
)
from seed.generator import SeededRandom, generate_timestamp
from app.services.risk_matrix import _default_matrix_config, RISK_MATRIX_DOC_PATH

# Tenant access-model fields on the tenant record:
#   category          DEMO | CONTRACTED | STATE
#   status            ACTIVE | SUSPENDED | EXPIRED
#   trial_expires_at  ISO timestamp; set 30 days from creation for DEMO tenants.
TENANT_TRIAL_DAYS = 30


def create_tenant(db, profile: dict) -> dict:
    from app.core.config import settings
    tenant_id = profile["id"]
    tenant_ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id)
    tenant_doc = tenant_ref.get()

    now = datetime.now(timezone.utc)

    tenant_type = profile.get("tenant_type", profile["type"])
    tenant_code = profile.get("icao") or profile["id"].split("-")[0].upper()

    category = profile.get("category", "DEMO")
    status = profile.get("status", "ACTIVE")
    trial_expires_at = None
    if category == "DEMO":
        trial_expires_at = (now + timedelta(days=TENANT_TRIAL_DAYS)).isoformat()

    tenant_data = {
        "name": profile["name"],
        "type": tenant_type,
        "icao": profile["icao"],
        "iata": profile.get("iata", ""),
        "country": profile["country"],
        "base": profile["base"],
        "fleet_size": profile["fleet_size"],
        "employees": profile["employees"],
        "survey_count": profile["survey_count"],
        "sms_profile": profile["culture_description"],
        "aircraft_types": profile["aircraft_types"],
        "routes": profile["routes"],
        "email_domain": profile["email_domain"],
        "category": category,
        "status": status,
        "trial_expires_at": trial_expires_at,
        "created_at": now,
        "updated_at": now,
        "seed_version": SEED_VERSION,
        "active": True,
    }

    if not tenant_doc.exists:
        tenant_ref.set(tenant_data)
        logger.info(f"Created tenant: {profile['name']} ({tenant_id})")
    else:
        tenant_ref.update(tenant_data)
        logger.info(f"Updated tenant: {profile['name']} ({tenant_id})")

    info_data = {
        "tenant_name": profile["name"],
        "tenant_type": tenant_type,
        "icao_code": profile["icao"],
        "iata_code": profile.get("iata", ""),
        "base_airport": profile["base"],
        "fleet_size": profile["fleet_size"],
        "employee_count": profile["employees"],
        "safety_culture_index": None,
        "last_survey_date": None,
        "total_reports": 0,
        "registration": f"CAR-19/{tenant_code}/{SEED_VERSION}",
        "seed_version": SEED_VERSION,
    }

    info_ref = tenant_ref.collection(settings.FIREBASE_COLLECTION_METADATA).document(
        settings.FIREBASE_DOCUMENT_INFO
    )
    info_ref.set(info_data, merge=True)

    risk_matrix_ref = tenant_ref.collection(settings.FIREBASE_COLLECTION_METADATA).document(
        RISK_MATRIX_DOC_PATH
    )
    risk_matrix_config = _default_matrix_config()
    risk_matrix_config["updated_by"] = "seed"
    risk_matrix_config["updated_at"] = now
    risk_matrix_ref.set(risk_matrix_config, merge=True)

    from seed.tenant_profiles import write_tenant_profiles

    write_tenant_profiles(db, [tenant_id])

    return tenant_id


def create_all_tenants(db, tenant_ids=None, profiles=None) -> list:
    from app.core.config import settings

    # Full-set mode (default) enforces service-provider type coverage and
    # purges legacy tenants; explicit profiles (virtual archetypes) do not.
    is_full_set = profiles is None and not tenant_ids

    if profiles is None:
        profiles = [p for p in OPERATOR_PROFILES
                    if not tenant_ids or p["id"] in tenant_ids]

    if is_full_set:
        profile_types = {p["tenant_type"] for p in profiles}
        missing_types = BETA_SERVICE_PROVIDER_TYPES - profile_types
        if missing_types:
            raise RuntimeError(
                f"OPERATOR_PROFILES is missing tenant types: {sorted(missing_types)}"
            )

    tenant_ids_out = []
    for profile in profiles:
        tid = create_tenant(db, profile)
        tenant_ids_out.append(tid)
    logger.info(f"Seeded {len(tenant_ids_out)} tenants")

    if is_full_set:
        purge_legacy_tenants(db)
    return tenant_ids_out


def purge_legacy_tenants(db) -> list:
    """Delete archived legacy tenant docs so the beta DB matches the profiles.

    Only docs whose id is in LEGACY_OPERATOR_PROFILES are removed (with their
    subcollections); active providers and the CAAN regulator are never touched.
    """
    from app.core.config import settings

    from seed.config import LEGACY_OPERATOR_PROFILES

    legacy_ids = {p["id"] for p in LEGACY_OPERATOR_PROFILES}
    removed = []
    tenants_coll = db.collection(settings.FIREBASE_COLLECTION_TENANTS)
    for doc in tenants_coll.get():
        if doc.id not in legacy_ids:
            continue
        _delete_collection_docs(db, doc.reference)
        doc.reference.delete()
        removed.append(doc.id)
    if removed:
        logger.warning(f"Purged legacy tenants from DB: {sorted(removed)}")
    return removed


def _delete_collection_docs(db, doc_ref) -> None:
    """Recursively delete all subcollections of a document."""
    for coll in doc_ref.collections():
        for subdoc in coll.get():
            _delete_collection_docs(db, subdoc.reference)
            subdoc.reference.delete()


def create_caan_tenant(db) -> str:
    """Create the CAAN state-regulator tenant doc in the `tenants` collection.

    The CAAN SMD account belongs to this tenant (tenant_id="caan"), so the
    tenant doc is lifecycle-managed alongside operators.
    """
    from app.core.config import settings
    tenant_id = CAAN_TENANT["id"]
    tenant_ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id)
    tenant_doc = tenant_ref.get()

    now = datetime.now(timezone.utc)
    tenant_data = {
        "name": CAAN_TENANT["name"],
        "type": CAAN_TENANT["type"],
        "icao": CAAN_TENANT["icao"],
        "iata": CAAN_TENANT.get("iata", ""),
        "country": CAAN_TENANT["country"],
        "base": CAAN_TENANT["base"],
        "fleet_size": CAAN_TENANT["fleet_size"],
        "employees": CAAN_TENANT["employees"],
        "survey_count": CAAN_TENANT["survey_count"],
        "sms_profile": CAAN_TENANT["culture_description"],
        "aircraft_types": CAAN_TENANT["aircraft_types"],
        "routes": CAAN_TENANT["routes"],
        "email_domain": CAAN_TENANT["email_domain"],
        "category": "STATE",
        "status": "ACTIVE",
        "trial_expires_at": None,
        "created_at": now,
        "updated_at": now,
        "seed_version": SEED_VERSION,
        "active": True,
    }

    if not tenant_doc.exists:
        tenant_ref.set(tenant_data)
        logger.info(f"Created CAAN regulator tenant ({tenant_id})")
    else:
        tenant_ref.update(tenant_data)
        logger.info(f"Updated CAAN regulator tenant ({tenant_id})")

    info_data = {
        "tenant_name": CAAN_TENANT["name"],
        "tenant_type": CAAN_TENANT["type"],
        "icao_code": CAAN_TENANT["icao"],
        "iata_code": CAAN_TENANT.get("iata", ""),
        "base_airport": CAAN_TENANT["base"],
        "fleet_size": CAAN_TENANT["fleet_size"],
        "employee_count": CAAN_TENANT["employees"],
        "safety_culture_index": None,
        "last_survey_date": None,
        "total_reports": 0,
        "registration": f"CAR-19/{CAAN_TENANT['icao']}/{SEED_VERSION}",
        "seed_version": SEED_VERSION,
    }

    info_ref = tenant_ref.collection(settings.FIREBASE_COLLECTION_METADATA).document(
        settings.FIREBASE_DOCUMENT_INFO
    )
    info_ref.set(info_data, merge=True)

    risk_matrix_ref = tenant_ref.collection(settings.FIREBASE_COLLECTION_METADATA).document(
        RISK_MATRIX_DOC_PATH
    )
    risk_matrix_config = _default_matrix_config()
    risk_matrix_config["updated_by"] = "seed"
    risk_matrix_config["updated_at"] = now
    risk_matrix_ref.set(risk_matrix_config, merge=True)

    return tenant_id


def create_system_tenant(db) -> str:
    """Create the platform `system` tenant doc owning the Super Admin account.

    Treated as a STATE-category tenant (platform operator, not a trial): no
    trial_expires_at. Idempotent merge.
    """
    from app.core.config import settings

    tenant_id = "system"
    tenant_ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id)

    now = datetime.now(timezone.utc)
    tenant_data = {
        "name": "AviaSAFE Systems",
        "type": "system",
        "category": "STATE",
        "status": "ACTIVE",
        "trial_expires_at": None,
        "active": True,
        "created_at": now,
        "updated_at": now,
        "seed_version": SEED_VERSION,
    }
    tenant_ref.set(tenant_data, merge=True)
    logger.info(f"Created system tenant ({tenant_id})")
    return tenant_id


def create_regulator_scoping(db, operator_ids: Optional[list] = None) -> dict:
    """Wire the CAAN State Regulator doc + tenant tags that scope cross-tenant
    aggregations (SMS maturity, state risk).

    Writes:
      * `regulators/caan` with `operator_tenant_ids` = the active provider ids
      * `regulator_id="caan"` + `country="NP"` tags on each operator tenant and
        on the CAAN tenant itself

    Idempotent and merge-only; never touches operator data.
    """
    from app.core.config import settings

    if not operator_ids:
        operator_ids = [p["id"] for p in OPERATOR_PROFILES]

    now = datetime.now(timezone.utc)
    ref = db.collection(settings.FIREBASE_COLLECTION_REGULATORS).document("caan")

    # Union-merge: virtual archetype tenants ADD themselves to the oversight
    # set without evicting the real operators (and vice versa).
    try:
        snap = ref.get()
        existing = (snap.to_dict() or {}) if getattr(snap, "exists", True) else {}
    except Exception:
        existing = {}
    current_ids = set(existing.get("operator_tenant_ids") or [])
    merged_ids = sorted(current_ids | set(operator_ids))

    ref.set({
        "id": "caan",
        "type": "state_regulator",
        "name": CAAN_TENANT["name"],
        "short_name": "CAAN",
        "country": "NP",
        "country_name": "Nepal",
        "domain": "ssp.caanepal.gov.np",
        "operator_tenant_ids": merged_ids,
        "active": True,
        "updated_at": now,
    }, merge=True)

    for tid in list(merged_ids) + [CAAN_TENANT["id"]]:
        db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tid).set({
            "regulator_id": "caan",
            "country": "NP",
            "active": True,
        }, merge=True)

    logger.info(f"Regulator scoping applied: caan oversees {merged_ids}")
    return {"regulator_id": "caan", "operator_tenant_ids": merged_ids}
