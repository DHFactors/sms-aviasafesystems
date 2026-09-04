"""
Phase 1 Login Verification — Live Platform E2E Tests
=====================================================
Tests authentication and role-based redirects on https://sms.aviasafesystems.com
using Playwright (headless Chromium).

Accounts under test:
  1. SUPER_ADMIN  — ezondiza.dhf@gmail.com / AviaSafe-Dev-2026$!
     Expected redirect: /admin/production-setup.html
  2. Fixed-Wing Admin (safety@) — safety@fixedwing.com / safety_fw_2026
     Expected redirect: /safety.html
  3. Fixed-Wing Staff — staff@fixedwing.com / staff_fw_2026
     Expected redirect: /safety.html

Run:
    python tests/e2e/phase1_login_verification.py
"""

import sys
import json
import time
import os
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

# Force UTF-8 output on Windows
if os.name == "nt":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

LIVE_URL = "https://sms.aviasafesystems.com"
LOGIN_URL = f"{LIVE_URL}/login.html"
TIMEOUT_MS = 90_000  # 90s — Render cold-boot can take 30-60s

TESTS = [
    {
        "label": "SUPER_ADMIN",
        "email": "ezondiza.dhf@gmail.com",
        "password": "AviaSafe-Dev-2026$!",
        "expected_role": "SUPER_ADMIN",
        "expected_path": "/admin/production-setup.html",
    },
    {
        "label": "Fixed-Wing Admin (safety@)",
        "email": "safety@fixedwing.com",
        "password": "safety_fw_2026",
        "expected_role": "AIRLINE_ADMIN",
        "expected_path": "/safety.html",
    },
    {
        "label": "Fixed-Wing Staff",
        "email": "staff@fixedwing.com",
        "password": "staff_fw_2026",
        "expected_role": "USER",
        "expected_path": "/safety.html",
    },
]

PASS = 0
FAIL = 0
FAILURES = []


def record(label, ok, detail=""):
    global PASS, FAIL
    mark = "✅ PASS" if ok else "❌ FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(f"{mark} {label} — {detail}")
    print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))


def run_test(page, account):
    label = account["label"]
    print(f"\n{'─'*70}")
    print(f"TEST: {label}")
    print(f"  email: {account['email']}")
    print(f"  expected redirect: {account['expected_path']}")
    print(f"{'─'*70}")

    console_errors = []
    page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
    page.on("pageerror", lambda err: console_errors.append(f"[pageerror] {err.message}"))

    # Navigate to login page
    print("  → Navigating to login page...")
    try:
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=TIMEOUT_MS)
        record(f"{label}: Login page loaded", True, f"title={page.title()}")
    except PwTimeout:
        record(f"{label}: Login page load timed out", False, f"timeout={TIMEOUT_MS}ms")
        return
    except Exception as e:
        record(f"{label}: Login page load error", False, str(e)[:200])
        return

    # Fill form
    print("  → Filling credentials...")
    try:
        email_input = page.locator("#email")
        password_input = page.locator("#password")
        email_input.wait_for(state="visible", timeout=10000)
        email_input.fill(account["email"])
        password_input.fill(account["password"])
        record(f"{label}: Form filled", True)
    except Exception as e:
        record(f"{label}: Form fill failed", False, str(e)[:200])
        return

    # Submit login
    print("  → Submitting login...")
    try:
        page.locator("#loginBtn").click()
    except Exception as e:
        record(f"{label}: Submit click failed", False, str(e)[:200])
        return

    # Wait for redirect (URL change away from login.html)
    print("  → Waiting for redirect...")
    try:
        page.wait_for_function(
            "() => !window.location.pathname.includes('login.html')",
            timeout=TIMEOUT_MS,
        )
        final_url = page.url
        final_path = page.url.replace(LIVE_URL, "").split("?")[0].split("#")[0]
        record(f"{label}: Redirected", True, f"url={final_path}")
    except PwTimeout:
        # Check if error message appeared instead
        try:
            error_text = page.locator("#errorMessage").inner_text(timeout=2000)
            if error_text and error_text.strip():
                record(f"{label}: Redirect failed — error shown", False, f"error='{error_text.strip()}'")
                _dump_console(label, console_errors)
                return
        except Exception:
            pass
        record(f"{label}: Redirect timed out", False, f"still on {page.url}")
        _dump_console(label, console_errors)
        return
    except Exception as e:
        record(f"{label}: Redirect wait error", False, str(e)[:200])
        _dump_console(label, console_errors)
        return

    # Verify final URL path
    record(f"{label}: Final URL path", final_path == account["expected_path"],
           f"expected={account['expected_path']}, got={final_path}")

    # Check for authentication errors in console
    auth_errors = [e for e in console_errors if any(k in e.lower() for k in [
        "auth/", "permission", "unauthorized", "token", "invalid", "expired"
    ])]
    record(f"{label}: No auth console errors", len(auth_errors) == 0,
           f"count={len(auth_errors)}" + (f" errors={auth_errors[:3]}" if auth_errors else ""))

    # Dump all console errors for analysis
    _dump_console(label, console_errors)


def _dump_console(label, errors):
    if errors:
        print(f"  Console errors ({len(errors)}):")
        for e in errors[:10]:
            print(f"    {e}")
    else:
        print("  Console errors: none")


def main():
    print("=" * 70)
    print("  Phase 1 Login Verification — Live Platform E2E")
    print(f"  Target: {LIVE_URL}")
    print(f"  Time: {datetime.utcnow().isoformat()}Z")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu"],
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )

        for account in TESTS:
            page = context.new_page()
            try:
                run_test(page, account)
            except Exception as e:
                record(f"{account['label']}: UNHANDLED EXCEPTION", False, str(e)[:300])
            finally:
                page.close()

        browser.close()

    # Summary
    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    print(f"  PASS: {PASS}   FAIL: {FAIL}")
    if FAILURES:
        print("\n  FAILURES:")
        for f in FAILURES:
            print(f"    {f}")
    print(f"\n  RESULT: {'✅ ALL PASS' if FAIL == 0 else '❌ FAILURES DETECTED'} — {PASS}/{PASS+FAIL} checks passed")
    print(f"{'='*70}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
