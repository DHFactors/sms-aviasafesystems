from loguru import logger

from seed.config import (
    DEMO_USERS,
    OPERATOR_PROFILES,
    NEPALI_NAMES,
    DEMO_USER_PASSWORD,
    SIMPLIFIED_ROLE_ACCOUNTS,
    simplified_email,
    simplified_password,
)
from seed.generator import SeededRandom


def create_user(auth, user_spec: dict) -> dict:
    try:
        existing = auth.get_user(user_spec["uid"])
        logger.info(f"User already exists: {user_spec['email']}, updating claims")
        user_record = existing
    except Exception:
        user_record = auth.create_user(
            uid=user_spec["uid"],
            email=user_spec["email"],
            password=user_spec["password"],
            display_name=user_spec["full_name"],
            email_verified=True,
        )
        logger.info(f"Created user: {user_spec['email']} ({user_spec['role']})")

    claims = {"role": user_spec["role"]}
    if user_spec.get("tenant_id"):
        claims["tenant_id"] = user_spec["tenant_id"]
    if user_spec.get("department"):
        claims["department"] = user_spec["department"]

    auth.set_custom_user_claims(user_spec["uid"], claims)

    return {
        "uid": user_spec["uid"],
        "email": user_spec["email"],
        "role": user_spec["role"],
        "tenant_id": user_spec.get("tenant_id"),
        "department": user_spec.get("department"),
        "full_name": user_spec["full_name"],
    }


def create_all_users(auth, tenant_ids=None) -> list:
    rng = SeededRandom(seed=42)
    created_users = []

    for user_spec in DEMO_USERS:
        result = create_user(auth, user_spec)
        created_users.append(result)

    for profile in OPERATOR_PROFILES:
        if tenant_ids and profile["id"] not in tenant_ids:
            continue
        op_id = profile["id"]
        domain = profile["email_domain"]
        op_name = profile["name"]

        sm_name = f"{rng.choice(NEPALI_NAMES)}"
        sm_uid = f"sm-{op_id}-001"
        sm_user = {
            "uid": sm_uid,
            "email": f"safety.{op_id}@{domain}",
            "password": DEMO_USER_PASSWORD,
            "full_name": sm_name,
            "organization": profile["name"],
            "role": "AIRLINE_ADMIN",
            "tenant_id": op_id,
        }
        created_users.append(create_user(auth, sm_user))

        ae_name = f"{rng.choice(NEPALI_NAMES)}"
        ae_uid = f"ae-{op_id}-001"
        ae_user = {
            "uid": ae_uid,
            "email": f"ae.{op_id}@{domain}",
            "password": DEMO_USER_PASSWORD,
            "full_name": ae_name,
            "organization": profile["name"],
            "role": "AIRLINE_ADMIN",
            "tenant_id": op_id,
        }
        created_users.append(create_user(auth, ae_user))

        mgr_name = f"{rng.choice(NEPALI_NAMES)}"
        mgr_uid = f"mgr-{op_id}-001"
        mgr_user = {
            "uid": mgr_uid,
            "email": f"manager.{op_id}@{domain}",
            "password": DEMO_USER_PASSWORD,
            "full_name": mgr_name,
            "organization": profile["name"],
            "role": "USER",
            "tenant_id": op_id,
        }
        created_users.append(create_user(auth, mgr_user))

        # Simplified role accounts: {role}@{tenant}.com / {CODE}-{ROLE}-2026
        for role in SIMPLIFIED_ROLE_ACCOUNTS:
            token = role["token"]
            role_user = {
                "uid": f"{token}-{op_id}-001",
                "email": simplified_email(token, op_id),
                "password": simplified_password(token, op_id),
                "full_name": f"{role['full_name']} ({op_name})",
                "organization": op_name,
                "role": role["app_role"],
                "tenant_id": op_id,
                "department": role.get("department") or "",
            }
            created_users.append(create_user(auth, role_user))

    logger.info(f"Seeded {len(created_users)} users total")
    return created_users
