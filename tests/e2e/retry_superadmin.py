"""Retry SUPER_ADMIN login now that Render should be warm."""
import sys, io, os
if os.name == "nt":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

LIVE = "https://sms.aviasafesystems.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, ignore_https_errors=True)
    page = ctx.new_page()

    all_console = []
    page.on("console", lambda m: all_console.append(f"[{m.type}] {m.text}"))
    page.on("pageerror", lambda e: all_console.append(f"[pageerror] {e.message}"))

    print("Loading login page (warm server)...")
    page.goto(LIVE + "/login.html", wait_until="networkidle", timeout=90000)
    print(f"Login page title: {page.title()}")

    page.locator("#email").fill("ezondiza.dhf@gmail.com")
    page.locator("#password").fill("AviaSafe-Dev-2026$!")
    print("Submitting login...")
    page.locator("#loginBtn").click()

    try:
        page.wait_for_function(
            "() => !window.location.pathname.includes('login.html')",
            timeout=120000,
        )
        print(f"SUCCESS: Redirected to {page.url}")
    except Exception:
        err = page.locator("#errorMessage").inner_text(timeout=3000)
        print(f"BLOCKER: Error shown: {err}")
        print(f"Still on: {page.url}")

    if all_console:
        print(f"\nConsole ({len(all_console)} messages):")
        for c in all_console[:20]:
            print(f"  {c}")
    browser.close()
