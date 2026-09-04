"""List the current emails bound to the generic demo tenant uids in Firebase Auth."""
import os, io, sys
if os.name == "nt":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.abspath("."))

from app.core.config import settings  # noqa
from app.firebase import initialize_firebase, get_auth  # noqa

initialize_firebase()
auth = get_auth()

uids = []
for tid in ("fixedwing", "rotarywing", "demoairport"):
    for token in ("ae", "safety", "camo", "145", "ops", "staff", "smd"):
        uids.append(f"{token}-{tid}-001")

print(f"Querying {len(uids)} candidate uids...")
for uid in uids:
    try:
        rec = auth.get_user(uid)
        print(f"  {uid:24s} -> {rec.email}")
    except Exception as e:
        code = getattr(e, "code", type(e).__name__)
        print(f"  {uid:24s} -> NOT FOUND ({code})")
