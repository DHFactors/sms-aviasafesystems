"""Verify SUPER_ADMIN lands on a functional production-setup page."""
import sys, io, os
if os.name == "nt":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

LIVE = "https://sms.aviasafesystems.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, ignore_https_errors=True)
    page = ctx.new_page()

    errors = []
    page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"[pageerror] {e.message}"))

    # Login
    page.goto(LIVE + "/login.html", wait_until="networkidle", timeout=90000)
    page.locator("#email").fill("ezondiza.dhf@gmail.com")
    page.locator("#password").fill("AviaSafe-Dev-2026$!")
    page.locator("#loginBtn").click()
    page.wait_for_function("() => !window.location.pathname.includes('login.html')", timeout=120000)

    final = page.url
    path = final.replace(LIVE, "")
    print(f"Landed on: {path}")

    # Wait for page to fully render
    page.wait_for_load_state("networkidle", timeout=30000)
    import time; time.sleep(3)

    # Check page content
    title = page.title()
    print(f"Page title: {title}")

    # Check for access denied or error messages
    body_text = page.locator("body").inner_text(timeout=5000)
    has_access_denied = "access denied" in body_text.lower() or "unauthorized" in body_text.lower()
    has_setup = "production setup" in body_text.lower() or "step" in body_text.lower()
    print(f"Contains 'access denied': {has_access_denied}")
    print(f"Contains setup content: {has_setup}")

    if errors:
        print(f"\nJS errors ({len(errors)}):")
        for e in errors[:10]:
            print(f"  {e}")
    else:
        print("JS errors: none")

    browser.close()
