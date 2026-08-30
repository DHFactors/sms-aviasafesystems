from loguru import logger

from seed.config import (
    DEMO_USERS,
    DEVELOPER_ACCOUNT,
    OPERATOR_PROFILES,
    roles_for_tenant,
    simplified_email,
    simplified_password,
)


def create_user(auth, user_spec: dict) -> dict:
    uid = user_spec["uid"]
    password = user_spec.get("password")
    sync_password = bool(user_spec.get("sync_password")) and bool(password)
    try:
        existing = auth.get_user(uid)
        logger.info(f"User already exists: {user_spec['email']}, updating claims")
        user_record = existing
        if sync_password:
            # Provisioned bootstrap accounts (e.g. the developer super-admin)
            # always have their password re-synced so a stale Auth password can
            # never lock the owner out.
            auth.update_user(uid, password=password)
            logger.info(f"Password re-synced for existing user: {user_spec['email']}")
    except Exception:
        try:
            user_record = auth.create_user(
                uid=uid,
                email=user_spec["email"],
                password=password,
                display_name=user_spec["full_name"],
                email_verified=True,
            )
            logger.info(f"Created user: {user_spec['email']} ({user_spec['role']})")
        except auth.EmailAlreadyExistsError:
            # The email is already bound to a different uid in this Auth pool
            # (e.g. a prior run without a forced uid). Adopt the existing record
            # so re-seeding stays idempotent instead of failing.
            user_record = auth.get_user_by_email(user_spec["email"])
            uid = user_record.uid
            logger.warning(
                f"Adopted existing account by email {user_spec['email']} "
                f"(uid {uid}) — updating claims/password"
            )
            if sync_password:
                auth.update_user(uid, password=password)

    claims = {"role": user_spec["role"]}
    if user_spec.get("tenant_id"):
        claims["tenant_id"] = user_spec["tenant_id"]
    if user_spec.get("department"):
        claims["department"] = user_spec["department"]
    if user_spec.get("is_developer"):
        claims["is_developer"] = True

    auth.set_custom_user_claims(uid, claims)

    return {
        "uid": uid,
        "email": user_spec["email"],
        "role": user_spec["role"],
        "tenant_id": user_spec.get("tenant_id"),
        "department": user_spec.get("department"),
        "is_developer": bool(user_spec.get("is_developer")),
        "full_name": user_spec["full_name"],
    }


def create_all_users(auth, tenant_ids=None) -> list:
    created_users = []

    for user_spec in DEMO_USERS:
        result = create_user(auth, user_spec)
        created_users.append(result)

    # Developer / Super-Admin bootstrap account — always provisioned regardless
    # of tenant scoping (cross-tenant owner account).
    created_users.append(create_user(auth, dict(DEVELOPER_ACCOUNT)))

    for profile in OPERATOR_PROFILES:
        if tenant_ids and profile["id"] not in tenant_ids:
            continue
        op_id = profile["id"]
        op_name = profile["name"]

        # Simplified role accounts: {role}@{tenant}.com / {CODE}-{ROLE}-2026
        # (fishtail-air / summit-air additionally get AE + Line Pilot accounts)
        for role in roles_for_tenant(op_id):
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
