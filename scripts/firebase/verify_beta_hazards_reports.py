"""Live-verify GET /api/v1/hazards and /api/v1/reports against the BETA backend
after the data backfill + serializer normalization fix."""
import sys
import json
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.core.config import settings

API = "https://sms-aviasafesystems-beta.onrender.com"
API_KEY = "AIzaSyCdCtUuyOcUIoCBEaiWGbhp6_XwZKHsicc"
FIREBASE_AUTH_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=" + API_KEY


def mint_id_token(uid, claims):
    import firebase_admin
    from firebase_admin import credentials, auth as admin_auth

    if not firebase_admin._apps:
        cred = credentials.Certificate({
            "type": "service_account",
            "project_id": settings.FIREBASE_PROJECT_ID,
            "private_key": settings.FIREBASE_PRIVATE_KEY.replace("\\n", "\n"),
            "client_email": settings.FIREBASE_CLIENT_EMAIL,
            "token_uri": settings.FIREBASE_TOKEN_URI,
        })
        firebase_admin.initialize_app(cred, {"projectId": settings.FIREBASE_PROJECT_ID})
    custom = admin_auth.create_custom_token(uid, claims)
    custom = custom.decode() if isinstance(custom, bytes) else custom
    r = requests.post(FIREBASE_AUTH_URL, json={"token": custom, "returnSecureToken": True}, timeout=30)
    r.raise_for_status()
    return r.json()["idToken"]


def check(label, resp):
    ok = resp.status_code == 200
    body = ""
    try:
        body = resp.json()
        if isinstance(body, list):
            body = f"[{len(body)} items] first: {json.dumps(body[0], default=str)[:220] if body else 'empty'}"
        else:
            body = json.dumps(body, default=str)[:220]
    except Exception:
        body = resp.text[:220]
    print(f"  [{'OK' if ok else 'FAIL'}] {label} -> {resp.status_code} {body}")
    return ok


print(f"Beta backend: {API}")
tokens = {
    "buddha": mint_id_token("sm-buddha-air-001", {"role": "AIRLINE_ADMIN", "tenant_id": "buddha-air"}),
    "sita": mint_id_token("sm-sita-air-001", {"role": "AIRLINE_ADMIN", "tenant_id": "sita-air"}),
    "caan": mint_id_token("caan-smd-001", {"role": "CAAN_SMD", "tenant_id": None}),
}
print("Tokens minted:", {k: len(v) for k, v in tokens.items()})

results = []
for name, token in tokens.items():
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    for path in ("/api/v1/hazards", "/api/v1/reports"):
        try:
            r = requests.get(API + path, headers=headers, timeout=60)
        except Exception as e:
            print(f"  [ERR] {name} {path}: {e}")
            continue
        results.append(check(f"{name} {path}", r))

print(f"\n{sum(results)}/{len(results)} checks passed")
