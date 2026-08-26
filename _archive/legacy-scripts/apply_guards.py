#!/usr/bin/env python3
import os, glob

GUARD = """\n# ============================================================================
# HARD PRODUCTION GUARD: sms-db is virgin production DB only
# -----------------------------------------------------------------------------
# CRITICAL: Seeding into sms-db (Production) is permanently prohibited.
# This guard raises RuntimeError if any script erroneously targets sms-db.
# -----------------------------------------------------------------------------
import os
PROD_DB_ID = "sms-db"
DB_DEFAULT = os.environ.get("SEED_DB", "sms-db-beta")
if DB_DEFAULT == PROD_DB_ID:
    raise RuntimeError(
        "CRITICAL GUARD: \"sms-db\" is the Production database and must remain "
        "virgin (zero dummy data, zero archetype records). "
        "Seeding dummy data into sms-db is permanently prohibited. "
        "Use SEED_DB=sms-db-beta or pass --database sms-db-beta explicitly."
    )
# -----------------------------------------------------------------------------"""

search_dirs = [os.path.join("backend", "seed"), os.path.join("backend", "scripts")]
scripts = []
for d in search_dirs:
    full = os.path.join(".", d)
    if os.path.isdir(full):
        scripts.extend(glob.glob(os.path.join(full, "*.py")))

print(f"Found {len(scripts)} scripts")

for sp in scripts:
    fn = os.path.basename(sp)
    if "_purge" in fn:
        print(f"  {fn}: SKIP")
        continue
    with open(sp, "r") as f:
        c = f.read()
    if "CRITICAL GUARD" in c:
        print(f"  {fn}: already guarded")
        continue
    lines = c.split("\n")
    idx = 0
    for i in range(25):
        s = lines[i].strip()
        if not s or s.startswith("#"):
            idx = i + 1
        else:
            break
    new_lines = lines[:idx] + [GUARD.strip()] + lines[idx:]
    with open(sp, "w") as f:
        f.write("\n".join(new_lines))
    print(f"  {os.path.basename(sp)}: GUARD APPLIED")

print("\nDone.")
" > apply_guards.py

python apply_guards.py 2>&1