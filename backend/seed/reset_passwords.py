#!/usr/bin/env python3
"""
Reset per-user passwords for beta testing and write a credentials document.

Applies the simplified 2026-08 credential scheme to the four functional role
accounts per operator (password `{TENANT_CODE}-{ROLE}-2026`), and generates a
unique, strong random password for the CAAN regulator account, then updates
Firebase Auth and writes:

    <project_root>/BETA_CREDENTIALS_YYYY-MM-DD.md   (Markdown table)
    <project_root>/beta-testing-credentials.csv     (flat CSV backup)

Columns (markdown): Tenant | Role | Email | New Password

The credentials document contains real passwords and is intended to be stored
locally or shared securely. It is covered by .gitignore and must NOT be
committed to the repository.
"""

import sys
import csv
import secrets
import string
from datetime import datetime, date, timezone
from pathlib import Path

from loguru import logger

logger.remove()
logger.add(sys.stdout, format="{time:HH:mm:ss} | {level:<7} | {message}", level="INFO")

ROOT = Path(__file__).resolve().parents[2]
OUT_MD = ROOT / f"BETA_CREDENTIALS_{date.today().isoformat()}.md"
OUT_CSV = ROOT / "beta-testing-credentials.csv"

PASSWORD_LENGTH = 16

# Excludes characters that would break a Markdown table (pipe, backslash,
# backtick) while still providing a strong special-character set.
LOWER = string.ascii_lowercase
UPPER = string.ascii_uppercase
DIGITS = string.digits
SPECIALS = "!@#$%^&*()-_=+;:,.?"
ALL = LOWER + UPPER + DIGITS + SPECIALS


def random_password(length: int = PASSWORD_LENGTH) -> str:
    """Return a password with upper, lower, digit and special characters."""
    while True:
        pwd = "".join(secrets.choice(ALL) for _ in range(length))
        if (
            any(c in LOWER for c in pwd)
            and any(c in UPPER for c in pwd)
            and any(c in DIGITS for c in pwd)
            and any(c in SPECIALS for c in pwd)
        ):
            return pwd


def build_user_specs():
    from seed.config import (
        DEMO_USERS,
        OPERATOR_PROFILES,
        roles_for_tenant,
        simplified_email,
        simplified_password,
        CREDENTIAL_TENANT_CODES,
    )

    specs = []

    for u in DEMO_USERS:
        role_label = {
            "SUPER_ADMIN": "Super Admin",
            "CAAN_SMD": "CAAN SMD",
            "AIRLINE_ADMIN": "Admin",
            "USER": "User",
        }.get(u["role"], u["role"])
        specs.append(
            {
                "uid": u["uid"],
                "email": u["email"],
                "full_name": u["full_name"],
                "role": u["role"],
                "role_label": role_label,
                "tenant": "CAAN",
            }
        )

    for profile in OPERATOR_PROFILES:
        op_id = profile["id"]
        tenant_name = profile["name"]
        # Simplified role accounts: {role}@{tenant}.com / {CODE}-{ROLE}-2026
        # (fishtail-air / summit-air additionally get AE + Line Pilot accounts)
        for role in roles_for_tenant(op_id):
            token = role["token"]
            specs.append(
                {
                    "uid": f"{token}-{op_id}-001",
                    "email": simplified_email(token, op_id),
                    "password": simplified_password(token, op_id),
                    "role": role["app_role"],
                    "role_label": f"{role['full_name']}",
                    "tenant": tenant_name,
                }
            )

    return specs


def fetch_user(auth, spec):
    """Fetch the Auth record for a spec, verifying UID exists and email matches."""
    try:
        record = auth.get_user(spec["uid"])
    except Exception as e:
        logger.error(f"FETCH FAILED {spec['email']} ({spec['uid']}): {e}")
        return None

    if record.email and record.email.lower() != spec["email"].lower():
        logger.warning(
            f"EMAIL MISMATCH {spec['uid']}: expected {spec['email']}, "
            f"found {record.email} — using record email"
        )
        spec["email"] = record.email
    return record


def main():
    from app.core.config import settings
    from app.firebase import initialize_firebase, get_auth

    initialize_firebase()
    auth = get_auth()

    specs = build_user_specs()
    logger.info(f"Processing {len(specs)} demo accounts")

    rows = []
    errors = 0
    for spec in specs:
        if fetch_user(auth, spec) is None:
            errors += 1
            continue

        pwd = spec.get("password") or random_password()
        try:
            auth.update_user(spec["uid"], password=pwd)
            rows.append(
                {
                    "tenant": spec["tenant"],
                    "role_label": spec["role_label"],
                    "role": spec["role"],
                    "email": spec["email"],
                    "full_name": spec.get("full_name", ""),
                    "password": pwd,
                }
            )
            logger.info(
                f"Updated {spec['email']} ({spec['role_label']} / {spec['tenant']})"
            )
        except Exception as e:
            errors += 1
            logger.error(f"FAILED {spec['email']} ({spec['uid']}): {e}")

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    write_markdown(rows, generated_at)
    write_csv(rows)

    logger.info(f"Wrote {len(rows)} credentials to {OUT_MD}")
    logger.info(f"Failures: {errors}")
    logger.info("NOTE: OLD shared seed password no longer works for these users.")
    if errors:
        sys.exit(1)


def write_csv(rows):
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["tenant", "role_label", "role", "email", "full_name", "password"],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows, generated_at):
    operator_rows = [r for r in rows if r["tenant"] != "CAAN"]
    caan_rows = [r for r in rows if r["tenant"] == "CAAN"]

    lines = []
    lines.append("# AviaSAFE SMS — Beta Credentials")
    lines.append("")
    lines.append(f"Generated: **{generated_at}**")
    lines.append("")
    lines.append("> **SECURE DOCUMENT** — contains real passwords. Store locally or ")
    lines.append("> share securely. Do **NOT** commit to the repository.")
    lines.append("")
    lines.append("| Login URL | https://sms.aviasafesystems.com |")
    lines.append("| Backend | https://aviasafe-unified-platform.onrender.com |")
    lines.append("")
    lines.append("## Operator Accounts")
    lines.append("")
    lines.append("| Tenant | Role | Email | New Password |")
    lines.append("|--------|------|-------|--------------|")
    for r in operator_rows:
        lines.append(
            f"| {r['tenant']} | {r['role_label']} | `{r['email']}` | `{r['password']}` |"
        )
    lines.append("")
    lines.append("## CAAN / Regulatory Accounts")
    lines.append("")
    lines.append("| Tenant | Role | Email | New Password |")
    lines.append("|--------|------|-------|--------------|")
    for r in caan_rows:
        lines.append(
            f"| {r['tenant']} | {r['role_label']} | `{r['email']}` | `{r['password']}` |"
        )
    lines.append("")
    lines.append(f"Total accounts: {len(rows)}")
    lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
