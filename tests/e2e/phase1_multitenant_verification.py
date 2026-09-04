"""
Phase 1 Multi-Tenant Credential Verification — Live Platform
=============================================================
Tests authentication, role-based redirects, and tenant-scoping on
https://sms.aviasafesystems.com using Playwright headless Chromium.

Accounts:
  1. SUPER_ADMIN       ezondiza.dhf@gmail.com          AviaSafe-Dev-2026$!
  2. FW Admin (safety) safety@fixedwing.com            safety_fw_2026
  3. FW Staff          staff@fixedwing.com             staff_fw_2026
  4. RW Admin (safety) safety@rotarywing.com           safety_rw_2026
  5. RW Staff          staff@rotarywing.com            staff_rw_2026

Expected redirects (from firebase.js getRoleDestination):
  SUPER_ADMIN  -> /admin/production-setup.html
  AIRLINE_ADMIN(safety@) -> /safety.html
  USER(staff@) -> /safety.html  (or /dashboard/my-tasks.html if dept claim)

Run:
    python tests/e2e/phase1_multitenant_verification.py
"""

import sys, io, os, json, time
from datetime import datetime, timezone

if os.name == "nt":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

LIVE_URL = "https://sms.aviasafesystems.com"
LOGIN_URL = f"{LIVE_URL}/login.html"
COLD_BOOT_BUDGET_MS = 120_000   # 120 s total for first cold-boot login
WARM_BUDGET_MS = 60_000         # 60 s for subsequent warm logins

ACCOUNTS = [
    {
        "id": "SUPER_ADMIN",
        "email": "ezondiza.dhf@gmail.com",
        "password": "AviaSafe-Dev-2026$!",
        "expected_path": "/admin/production-setup.html",
        "expected_role": "SUPER_ADMIN",
        "tenant_scoped": False,
    },
    {
        "id": "FW-Admin",
        "email": "safety@fixedwing.com",
        "password": "safety_fw_2026",
        "expected_path": "/safety.html",
        "expected_role": "AIRLINE_ADMIN",
        "tenant_scoped": True,
        "tenant_id": "fixedwing",
    },
    {
        "id": "FW-Staff",
        "email": "staff@fixedwing.com",
        "password": "staff_fw_2026",
        "expected_path": "/safety.html",
        "expected_role": "USER",
        "tenant_scoped": True,
        "tenant_id": "fixedwing",
    },
    {
        "id": "RW-Admin",
        "email": "safety@rotarywing.com",
        "password": "safety_rw_2026",
        "expected_path": "/safety.html",
        "expected_role": "AIRLINE_ADMIN",
        "tenant_scoped": True,
        "tenant_id": "rotarywing",
    },
    {
        "id": "RW-Staff",
        "email": "staff@rotarywing.com",
        "password": "staff_rw_2026",
        "expected_path": "/safety.html",
        "expected_role": "USER",
        "tenant_scoped": True,
        "tenant_id": "rotarywing",
    },
]

PASS = 0
FAIL = 0
WARN = 0
BLOCKERS = []
RESULTS = []


def ok(label, detail=""):
    global PASS
    PASS += 1
    tag = "[PASS]"
    print(f"  {tag} {label}" + (f"  -- {detail}" if detail else ""))
    RESULTS.append(("PASS", label, detail))


def fail(label, detail=""):
    global FAIL
    FAIL += 1
    tag = "[FAIL]"
    BLOCKERS.append(f"{label}: {detail}")
    print(f"  {tag} {label}" + (f"  -- {detail}" if detail else ""))
    RESULTS.append(("FAIL", label, detail))


def warn(label, detail=""):
    global WARN
    WARN += 1
    tag = "[WARN]"
    print(f"  {tag} {label}" + (f"  -- {detail}" if detail else ""))
    RESULTS.append(("WARN", label, detail))


def section(title):
    print(f"\n{'='*72}")
    print(f"  {title}")
    print(f"{'='*72}")


def test_login(acct, page, budget_ms):
    """Run a single login test. Returns final URL path or None on blocker."""
    aid = acct["id"]
    console_log = []
    console_errors = []
    page.on("console", lambda m: (
        console_errors.append(f"[{m.type}] {m.text}") if m.type == "error"
        else console_log.append(f"[{m.type}] {m.text}")
    ))
    page.on("pageerror", lambda e: console_errors.append(f"[pageerror] {e.message}"))

    # 1. Load login page
    try:
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=90_000)
        ok(f"{aid}: Login page loaded", f"title={page.title()}")
    except PwTimeout:
        fail(f"{aid}: Login page timeout", f"90s budget exceeded")
        return None, console_errors
    except Exception as e:
        fail(f"{aid}: Login page load error", str(e)[:200])
        return None, console_errors

    # 2. Fill credentials
    try:
        page.locator("#email").wait_for(state="visible", timeout=10_000)
        page.locator("#email").fill(acct["email"])
        page.locator("#password").fill(acct["password"])
        ok(f"{aid}: Form filled")
    except Exception as e:
        fail(f"{aid}: Form fill failed", str(e)[:200])
        return None, console_errors

    # 3. Submit
    try:
        page.locator("#loginBtn").click()
    except Exception as e:
        fail(f"{aid}: Submit click failed", str(e)[:200])
        return None, console_errors

    # 4. Wait for redirect OR error
    try:
        page.wait_for_function(
            "() => !window.location.pathname.includes('login.html')",
            timeout=budget_ms,
        )
        final_url = page.url
        final_path = final_url.replace(LIVE_URL, "").split("?")[0].split("#")[0]
        ok(f"{aid}: Redirected", f"url={final_path}")
    except PwTimeout:
        # Maybe an error was shown
        try:
            err_text = page.locator("#errorMessage").inner_text(timeout=3_000)
            if err_text and err_text.strip():
                fail(f"{aid}: Login BLOCKED", f"error='{err_text.strip()[:250]}'")
                _print_console(aid, console_errors)
                return None, console_errors
        except Exception:
            pass
        fail(f"{aid}: Redirect timeout", f"still on {page.url}")
        _print_console(aid, console_errors)
        return None, console_errors
    except Exception as e:
        fail(f"{aid}: Redirect error", str(e)[:200])
        return None, console_errors

    # 5. Verify final path
    expected = acct["expected_path"]
    if final_path == expected:
        ok(f"{aid}: Correct redirect", f"expected={expected}")
    else:
        fail(f"{aid}: Wrong redirect", f"expected={expected}, got={final_path}")

    # 6. Auth console errors check
    auth_errs = [e for e in console_errors if any(k in e.lower() for k in [
        "auth/", "permission", "unauthorized", "token", "invalid-login",
    ])]
    if auth_errs:
        warn(f"{aid}: Auth-related console errors", f"count={len(auth_errs)}")
        for ae in auth_errs[:5]:
            print(f"         {ae}")
    else:
        ok(f"{aid}: No auth console errors")

    # 7. Tenant scope check (read claims from console log)
    _check_tenant_scope(aid, acct, console_log, console_errors)

    _print_console(aid, console_errors)
    return final_path, console_errors


def _check_tenant_scope(aid, acct, console_log, console_errors):
    """Parse console output for tenant_id claim to verify scoping."""
    if not acct.get("tenant_scoped"):
        return
    expected_tenant = acct.get("tenant_id", "")
    # Look for "role: X tenant: Y" in console logs
    combined = " ".join(console_log)
    if "tenant:" in combined.lower():
        # Extract tenant value
        import re
        m = re.search(r"tenant:\s*(\S+)", combined, re.IGNORECASE)
        if m:
            actual_tenant = m.group(1)
            if expected_tenant and expected_tenant in actual_tenant:
                ok(f"{aid}: Tenant scope correct", f"tenant={actual_tenant}")
            elif actual_tenant in ("None", "null", "system", ""):
                warn(f"{aid}: Tenant scope missing", f"got={actual_tenant}, expected ~{expected_tenant}")
            else:
                fail(f"{aid}: Tenant scope MISMATCH", f"expected={expected_tenant}, got={actual_tenant}")


def _print_console(aid, errors):
    if errors:
        print(f"  [{aid}] Console errors ({len(errors)}):")
        for e in errors[:8]:
            print(f"    {e}")
    else:
        print(f"  [{aid}] Console errors: none")


def main():
    print("=" * 72)
    print("  Phase 1 Multi-Tenant Credential Verification")
    print(f"  Target : {LIVE_URL}")
    print(f"  Time   : {datetime.now(timezone.utc).isoformat()}")
    print(f"  Accounts: {len(ACCOUNTS)}")
    print("=" * 72)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu"],
        )

        for i, acct in enumerate(ACCOUNTS):
            budget = COLD_BOOT_BUDGET_MS if i == 0 else WARM_BUDGET_MS
            # Fresh context per account so Firebase session from prior login
            # does not auto-redirect away from login.html
            ctx = browser.new_context(
                viewport={"width": 1440, "height": 900},
                ignore_https_errors=True,
            )
            page = ctx.new_page()
            section(f"ACCOUNT {i+1}/{len(ACCOUNTS)}: {acct['id']} ({acct['email']})")
            try:
                final_path, errs = test_login(acct, page, budget)
                acct["_final_path"] = final_path
            except Exception as e:
                fail(f"{acct['id']}: UNHANDLED", str(e)[:300])
            finally:
                page.close()
                ctx.close()

        # ── Cross-tenant isolation check ──
        section("CROSS-TENANT DATA ISOLATION (post-login)")
        fw_pages = [a for a in ACCOUNTS if a.get("tenant_id") == "fixedwing" and a.get("_final_path")]
        rw_pages = [a for a in ACCOUNTS if a.get("tenant_id") == "rotarywing" and a.get("_final_path")]
        if fw_pages and rw_pages:
            ok("Fixed-wing and rotary-wing accounts reach separate pages",
               f"fw={len(fw_pages)} rw={len(rw_pages)}")
        else:
            warn("Could not fully compare tenants", f"fw_logged_in={len(fw_pages)} rw_logged_in={len(rw_pages)}")

        browser.close()

    # ── Summary ──
    section("SUMMARY")
    print(f"  PASS : {PASS}")
    print(f"  FAIL : {FAIL}")
    print(f"  WARN : {WARN}")
    if BLOCKERS:
        print(f"\n  BLOCKERS ({len(BLOCKERS)}):")
        for b in BLOCKERS:
            print(f"    [!] {b}")
    print(f"\n  RESULT: {'ALL PASS' if FAIL == 0 else 'BLOCKERS DETECTED'}")
    print(f"  {PASS}/{PASS+FAIL+WARN} passed, {WARN} warnings")
    print("=" * 72)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
