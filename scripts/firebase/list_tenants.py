"""List tenants in sms-db-beta."""
import os, sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import firebase_admin
from firebase_admin import credentials, firestore

env = {}
for line in Path(Path(__file__).resolve().parents[2] / "backend" / ".env").read_text(encoding="utf-8").splitlines():
    m = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.*)$", line)
    if m and not line.strip().startswith("#"):
        v = m.group(2)
        if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
            v = v[1:-1]
        env[m[1]] = v

cred = credentials.Certificate({
    "type": "service_account",
    "project_id": env["FIREBASE_PROJECT_ID"],
    "private_key": env["FIREBASE_PRIVATE_KEY"].replace("\\n", "\n"),
    "client_email": env["FIREBASE_CLIENT_EMAIL"],
    "token_uri": env.get("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
})
app = firebase_admin.initialize_app(cred, name="list_tenants")
db = firestore.client(app, database_id="sms-db-beta")

for t in db.collection("tenants").stream():
    d = t.to_dict()
    name = d.get("name") or d.get("display_name") or d.get("icao") or ""
    counts = {}
    for sub in ("hazards", "reports", "responses"):
        try:
            counts[sub] = len(list(t.reference.collection(sub).limit(10).get()))
        except Exception as e:
            counts[sub] = f"err:{e}"
    print(f"{t.id:24s} {str(name):20s} {counts}")
firebase_admin.delete_app(app)
