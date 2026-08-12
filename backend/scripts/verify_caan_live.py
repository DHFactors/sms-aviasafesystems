# ============================================================================
# FILE: verify_caan_live.py
# PATH: backend/scripts/verify_caan_live.py
# PURPOSE: One-off live verification: mints a custom token for a CAAN_SMD seed
#          user via the Admin SDK, exchanges it for an ID token, then calls the
#          live /api/v1/dashboard/caan/survey-maturity and /api/v1/state-risk/*
#          endpoints to confirm they return data (not 403).
# AUTHOR: AviaSAFE Systems
# ============================================================================

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
import firebase_admin
from firebase_admin import credentials, auth as admin_auth

from app.core.config import settings

API = "https://aviasafe-unified-platform.onrender.com"


def init_admin():
    if firebase_admin._apps:
        return
    cred = credentials.Certificate({
        "type": "service_account",
        "project_id": settings.FIREBASE_PROJECT_ID,
        "private_key": settings.FIREBASE_PRIVATE_KEY.replace('\\n', '\n'),
        "client_email": settings.FIREBASE_CLIENT_EMAIL,
        "token_uri": settings.FIREBASE_TOKEN_URI,
    })
    firebase_admin.initialize_app(cred)


def main():
    init_admin()

    # CAAN_SMD seed user from seed/config.py (smd@caanepal.gov.np / smd-caan-001)
    uid = "smd-caan-001"
    custom = admin_auth.create_custom_token(uid, {"role": "CAAN_SMD", "tenant_id": "caan"})
    custom = custom.decode() if isinstance(custom, bytes) else custom

    api_key = "AIzaSyCdCtUuyOcUIoCBEaiWGbhp6_XwZKHsicc"
    r = requests.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={api_key}",
        json={"token": custom, "returnSecureToken": True},
        timeout=60,
    )
    r.raise_for_status()
    id_token = r.json()["idToken"]
    headers = {"Authorization": f"Bearer {id_token}"}
    print(f"Minted CAAN_SMD token (uid={uid})")

    for method, path in [
        ("GET", "/api/v1/dashboard/caan/survey-maturity"),
        ("GET", "/api/v1/dashboard/caan/benchmark"),
        ("GET", "/api/v1/state-risk/register?year=2026&quarter=3"),
        ("GET", "/api/v1/state-risk/aggregate?year=2026&quarter=3"),
    ]:
        try:
            resp = requests.request(method, API + path, headers=headers, timeout=90)
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            if method == "GET" and path == "/api/v1/dashboard/caan/survey-maturity":
                print(f"{method} {path} -> {resp.status_code}")
                print("  survey-maturity raw:", json.dumps(body, default=str)[:1500])
                continue
            if method == "GET" and path == "/api/v1/dashboard/caan/benchmark":
                print(f"{method} {path} -> {resp.status_code}")
                keys = list(body.keys()) if isinstance(body, dict) else []
                bd = body.get("data", {}) if isinstance(body, dict) else {}
                print("  benchmark keys:", keys)
                print("  anon_rate:", bd.get("anonymous_reporting_rate"),
                      "| total_reporters:", bd.get("total_reporters"),
                      "| industry_anon_rate:", bd.get("industry_anon_rate"),
                      "| ssp_target_avg:", bd.get("ssp_target_avg"),
                      "| ssp_actual_avg:", bd.get("ssp_actual_avg"))
                continue
            summary = body
            if isinstance(body, dict):
                keys = list(body.keys())
                if "operators" in body:
                    summary = {"status": body.get("status"), "operators": len(body["operators"]),
                               "state_overall": body.get("state", {}).get("overall_sms_maturity"),
                               "state_responses": body.get("state", {}).get("response_count")}
                elif "risks" in body:
                    summary = {"status": body.get("status"), "count": body.get("count"),
                               "first": (body["risks"][0] if body.get("risks") else None)}
                else:
                    summary = {"keys": keys}
            print(f"{method} {path} -> {resp.status_code} {summary}")
        except Exception as e:
            print(f"{method} {path} -> ERROR {e}")


if __name__ == "__main__":
    main()
