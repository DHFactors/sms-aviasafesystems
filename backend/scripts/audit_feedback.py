#!/usr/bin/env python3
"""Audit the Firestore `feedback` collection in the configured database."""

import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from datetime import datetime

from app.firebase import initialize_firebase, get_db

initialize_firebase()
db = get_db()

docs = sorted(
    db.collection("feedback").stream(),
    key=lambda d: (d.to_dict() or {}).get("created_at") or datetime.min,
)

print("FEEDBACK COLLECTION COUNT:", len(docs))
print("=" * 110)
for d in docs:
    x = d.to_dict() or {}
    ts = x.get("created_at")
    ts_s = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
    subj = (x.get("subject") or "")[:60]
    msg = (x.get("message") or "").replace("\n", " ")[:100]
    print(
        f"[{ts_s}] {x.get('email')} role={x.get('role')} "
        f"tenant={x.get('tenant_id')} page={x.get('page')} "
        f"rating={x.get('rating')} status={x.get('status')}"
    )
    print(f"   SUBJECT: {subj}")
    print(f"   MESSAGE: {msg}")