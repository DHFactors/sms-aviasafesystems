"""Check rate limiting + super admin API login (isolated, after rate window)."""
import requests, io, os, sys, time
if os.name == "nt":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

API = "https://aviasafe-unified-platform.onrender.com"

# Super admin isolated check (separate from the tenant .test ones that hit 422,
# which also count toward rate limiting)
r = requests.post(API + "/api/v1/auth/login",
                  json={"email": "ezondiza.dhf@gmail.com", "password": "AviaSafe-Dev-2026$!"},
                  headers={"Content-Type": "application/json"},
                  timeout=90)
print(f"super_admin direct API: HTTP {r.status_code}")
print(r.text[:400])