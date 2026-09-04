"""Check demoairport accounts with correct seeder passwords."""
import sys, io, os
if os.name == "nt":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import requests

API = "https://aviasafe-unified-platform.onrender.com"

# Demo airport accounts with correct seeder password pattern
# From runner.py and seeder.py, the demoairport users follow patterns like:
# ae_demo_2026, safety_demo_2026, camo_demo_2026 etc. for the 4 roles: ae, safety, camo, ops, staff
# The demoairport tenant has: ae, safety, ops, staff (no camo, 145 per config)
# Password pattern: {token}_{shorthand}_2026 where shorthand = "ap" for demoairport

accounts = [
    ("DA-AE", "ae@demoairport.com", "ae_ap_2026"),
    ("DA-Safety", "safety@demoairport.com", "safety_ap_2026"),
    ("DA-CAMO", "camo@demoairport.com", "camo_ap_2026"),
    ("DA-145", "145@demoairport.com", "145_ap_2026"),
    ("DA-OPS", "ops@demoairport.com", "ops_ap_2026"),
    ("DA-STAFF", "staff@demoairport.com", "staff_ap_2026"),
]

results = []
for name, email, pw in accounts:
    try:
        r = requests.post(API + "/api/v1/auth/login",
                          json={"email": email, "password": pw},
                          headers={"Content-Type": "application/json"}, timeout=90)
        ok = r.status_code == 200
        results.append((name, ok, r.status_code))
        status = "PASS" if ok else "FAIL"
        print(f"{status:4s} | {name:8s} | HTTP {r.status_code:3d} | {email} / {pw}")
    except Exception as e:
        results.append((name, False, "EX"))
        print(f"ERROR   | {name:8s} | EXCEPTION | {str(e)[:80]}")

print(f"\n{sum(1 for _, ok, _ in results if ok)}/{len(results)} passed")