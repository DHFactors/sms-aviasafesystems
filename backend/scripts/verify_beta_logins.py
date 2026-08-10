#!/usr/bin/env python3
"""
Verify beta login works for at least one account per tenant using the newly
generated passwords from BETA_CREDENTIALS_<date>.md.

Reads the credentials document, picks one account per tenant (preferring the
Safety Manager / Admin account for airlines, and the CAAN accounts), and signs
in through the Firebase Identity Toolkit REST endpoint (same path the web app
uses). No password is printed to the terminal.

Usage:
    python backend/scripts/verify_beta_logins.py [YYYY-MM-DD]
"""

import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
API_KEY = "AIzaSyCdCtUuyOcUIoCBEaiWGbhp6_XwZKHsicc"
AUTH_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"


def load_credentials(date_str):
    path = ROOT / f"BETA_CREDENTIALS_{date_str}.md"
    if not path.exists():
        raise SystemExit(f"credentials document not found: {path}")
    text = path.read_text(encoding="utf-8")

    accounts = []
    for line in text.splitlines():
        m = re.match(r"\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*`(.+?)`\s*\|\s*`(.+?)`\s*\|", line)
        if not m:
            continue
        tenant, role, email, password = m.groups()
        if tenant in ("Login URL", "Backend"):
            continue
        accounts.append(
            {"tenant": tenant, "role": role, "email": email, "password": password}
        )
    return accounts


def pick_verification_set(accounts):
    # Prefer the Safety role account for each airline; include all CAAN.
    selected = {}
    preferred_order = ["Safety Manager", "CAMO Manager", "Part-145 Maintenance",
                       "Operations Manager", "Admin (Safety Manager)",
                       "Reporter (Accountable Executive)", "User (Department Manager)",
                       "Super Admin", "CAAN SMD"]
    for acc in accounts:
        key = acc["tenant"]
        if key == "CAAN":
            # keep every CAAN account so the supervisor accounts get checked
            selected.setdefault(key, []).append(acc)
        else:
            if key not in selected:
                selected[key] = []
            if not any(a["role"] == acc["role"] for a in selected[key]):
                selected[key].append(acc)

    flat = []
    for tenant, accs in selected.items():
        accs.sort(key=lambda a: preferred_order.index(a["role"])
                  if a["role"] in preferred_order else 99)
        if tenant == "CAAN":
            flat.extend(accs)
        else:
            flat.append(accs[0])
    return flat


def sign_in(email, password):
    r = requests.post(
        AUTH_URL,
        json={"email": email, "password": password, "returnSecureToken": True},
        params={"key": API_KEY},
        timeout=30,
    )
    return r


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else "2026-08-08"
    accounts = load_credentials(date_str)
    print(f"Loaded {len(accounts)} accounts from BETA_CREDENTIALS_{date_str}.md")

    checks = pick_verification_set(accounts)
    print(f"Verifying {len(checks)} accounts (one per tenant where possible)\n")

    failures = 0
    verified_tenants = set()
    for acc in checks:
        r = sign_in(acc["email"], acc["password"])
        ok = r.status_code == 200
        if ok:
            verified_tenants.add(acc["tenant"])
            status = "OK"
        else:
            failures += 1
            status = f"FAIL({r.status_code}) {r.text[:150]}"
        print(f"  [{status}] {acc['tenant']:<28} {acc['role']:<34} {acc['email']}")

    print(f"\nVerified tenants ({len(verified_tenants)}): "
          f"{sorted(verified_tenants)}")
    print(f"Failures: {failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
