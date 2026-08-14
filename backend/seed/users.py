from loguru import logger

from seed.config import (
    DEMO_USERS,
    OPERATOR_PROFILES,
    SIMPLIFIED_ROLE_ACCOUNTS,
    simplified_email,
    simplified_password,
)


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
    created_users = []

    for user_spec in DEMO_USERS:
        result = create_user(auth, user_spec)
        created_users.append(result)

    for profile in OPERATOR_PROFILES:
        if tenant_ids and profile["id"] not in tenant_ids:
            continue
        op_id = profile["id"]
        op_name = profile["name"]

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
