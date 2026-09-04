"""Check remaining accounts: demoairport + CAAN_SMD."""
import sys, io, os, time
if os.name == "nt":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import requests

API = "https://aviasafe-unified-platform.onrender.com"
time.sleep(8)  # wait for rate limiter reset

# Demo airport accounts
da = [
    ("DA-AE", "ae@demoairport.com", "ae_demo_2026"),
    ("DA-Safety", "safety@demoairport.com", "safety_demo_2026"),
    ("DA-Ops", "ops@demoairport.com", "ops_demo_2026"),
    ("DA-Staff", "staff@demoairport.com", "staff_demo_2026"),
]

# CAAN_SMD (from env or default)
caan_name = "CAAN-SMD"
caan_email = "smd@caanepal.gov.np"
caan_pw = os.environ.get("AVIASAFE_PW_CAAN", "AviationSafe2026!")

all_accts = da + [(caan_name, caan_email, caan_pw)]

for name, email, pw in all_accts:
    try:
        r = requests.post(API + "/api/v1/auth/login",
                          json={"email": email, "password": pw},
                          headers={"Content-Type": "application/json"}, timeout=90)
        ok = r.status_code == 200
        preview = r.text[:100] if not ok else ""
        status = "PASS" if ok else "FAIL"
        print(f"{status:4s} | {name:12s} | HTTP {r.status_code:3d} | {email}")
    except Exception as e:
        print(f"ERROR   | {name:12s} | EXCEPTION | {str(e)[:80]}")