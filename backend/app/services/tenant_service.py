# ============================================================================
# FILE: tenant_service.py
# PATH: backend/app/services/tenant_service.py
# PURPOSE: Persistence layer for per-tenant survey management configuration.
#
# All survey-management fields live in the tenant doc's `config` map:
#   survey_rate_limit   (int)    max daily survey submissions
#   survey_instructions (str)    intro message shown at the top of the survey
#   survey_open_date    (str)    survey start date  (YYYY-MM-DD)
#   survey_close_date   (str)    survey expiry date (YYYY-MM-DD)
#   is_survey_active    (bool)   manual open/close override
#
# A derived camelCase `surveyConfig` map (openDate/closeDate/isActive) is kept
# in sync on every write so legacy readers (the public survey page and the CAAN
# SMS maturity dashboard) keep working unchanged.
# ============================================================================

from datetime import date
from typing import Any, Dict, Optional, Set

from loguru import logger

from app.core.config import settings
from app.firebase import get_db

SURVEY_RATE_LIMIT_OPTIONS = (5, 10, 25, 50, 100)


def _normalize_date(value: Any) -> Optional[str]:
    """Normalize an ISO/date value to a YYYY-MM-DD string.

    Returns:
        - None when the value is omitted (leave the stored field untouched)
        - ""  when an explicit empty string is sent (clear the stored field)
        - "YYYY-MM-DD" when a parseable date/ISO timestamp is provided
    Raises ValueError for unparseable values.
    """
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return ""
    text = str(value).strip()
    candidate = text[:10]
    try:
        date.fromisoformat(candidate)
    except ValueError:
        raise ValueError(f"Invalid survey date: {value!r}")
    return candidate


def build_config_update(
    fields: Dict[str, Any],
    existing_config: Dict[str, Any],
    existing_survey_config: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Merge validated survey-management fields into the tenant config map.

    Semantics per field:
      - survey_rate_limit / survey_instructions: replaced when provided.
      - survey_open_date / survey_close_date: an empty string clears the field,
        None leaves it untouched, otherwise stored as YYYY-MM-DD.
      - is_survey_active: replaced when provided (bool).

    Returns (updated_config, derived_survey_config). Raises ValueError when a
    value fails validation.
    """
    updated = dict(existing_config or {})
    legacy = existing_survey_config or {}
    cleared: Set[str] = set()

    rate_limit = fields.get("survey_rate_limit")
    if rate_limit is not None:
        if rate_limit not in SURVEY_RATE_LIMIT_OPTIONS:
            raise ValueError(
                f"survey_rate_limit must be one of "
                f"{', '.join(str(o) for o in SURVEY_RATE_LIMIT_OPTIONS)}"
            )
        updated["survey_rate_limit"] = rate_limit

    instructions = fields.get("survey_instructions")
    if instructions is not None:
        updated["survey_instructions"] = str(instructions)

    open_field = fields.get("survey_open_date")
    if open_field is not None:
        open_date = _normalize_date(open_field)
        if open_date:
            updated["survey_open_date"] = open_date
        else:
            updated.pop("survey_open_date", None)
            cleared.add("openDate")

    close_field = fields.get("survey_close_date")
    if close_field is not None:
        close_date = _normalize_date(close_field)
        if close_date:
            updated["survey_close_date"] = close_date
        else:
            updated.pop("survey_close_date", None)
            cleared.add("closeDate")

    if updated.get("survey_open_date") and updated.get("survey_close_date"):
        if updated["survey_close_date"] <= updated["survey_open_date"]:
            raise ValueError("survey_close_date must be after survey_open_date")

    active_field = fields.get("is_survey_active")
    if active_field is not None:
        updated["is_survey_active"] = bool(active_field)

    survey_config = _derive_survey_config(updated, legacy, cleared)
    return updated, survey_config


def _derive_survey_config(
    config: Dict[str, Any],
    legacy: Dict[str, Any],
    cleared: Set[str],
) -> Dict[str, Any]:
    """Build the camelCase surveyConfig map from the canonical config map.

    Falls back to legacy surveyConfig values for keys not managed by the last
    update (e.g. an older write that only set survey_rate_limit), unless the
    key was explicitly cleared.
    """
    survey_config: Dict[str, Any] = {}
    if "openDate" not in cleared:
        if "survey_open_date" in config:
            survey_config["openDate"] = config["survey_open_date"]
        else:
            legacy_open = legacy.get("openDate") or legacy.get("open_date")
            if legacy_open:
                survey_config["openDate"] = legacy_open

    if "closeDate" not in cleared:
        if "survey_close_date" in config:
            survey_config["closeDate"] = config["survey_close_date"]
        else:
            legacy_close = legacy.get("closeDate") or legacy.get("close_date")
            if legacy_close:
                survey_config["closeDate"] = legacy_close

    if "isActive" not in cleared:
        if "is_survey_active" in config:
            survey_config["isActive"] = config["is_survey_active"]
        else:
            legacy_active = legacy.get("isActive")
            if legacy_active is not None:
                survey_config["isActive"] = legacy_active

    return survey_config


def save_tenant_config(
    tenant_id: str,
    fields: Dict[str, Any],
    existing_config: Dict[str, Any],
    existing_survey_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate and persist survey-management config for a tenant.

    Writes both the canonical `config` map and the derived `surveyConfig` map.
    Returns the updated config map.
    """
    updated, survey_config = build_config_update(
        fields, existing_config, existing_survey_config
    )

    db = get_db()
    tenant_ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id)
    try:
        tenant_ref.update({"config": updated, "surveyConfig": survey_config})
    except Exception as e:
        logger.error(f"Failed to persist config for tenant {tenant_id}: {e}")
        raise RuntimeError("Failed to persist tenant config")
    return updated
