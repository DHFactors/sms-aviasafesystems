#!/usr/bin/env python3
import os, glob

GUARD_TEXT = """# ============================================================================
# HARD PRODUCTION GUARD: sms-db is virgin production DB only
# -----------------------------------------------------------------------------
# CRITICAL: Seeding into sms-db (Production) is permanently prohibited.
# This guard raises RuntimeError if any script erroneously targets sms-db.
# -----------------------------------------------------------------------------
import os
PROD_DB_ID = 'sms-db'
DB_DEFAULT = os.environ.get('SEED_DB', 'sms-db-beta')
if DB_DEFAULT == PROD_DB_ID:
    raise RuntimeError(
        'CRITICAL GUARD: "sms-db" is the Production database and must remain '
        'virgin (zero dummy data, zero archetype records). '
        'Seeding dummy data into sms-db is permanently prohibited. '
        'Use SEED_DB=sms-db-beta or pass --database sms-db-beta explicitly.'
    )
# -----------------------------------------------------------------------------"""

dirs = [r'backend\seed', r'backend\scripts']

for d in dirs:
    files = glob.glob(os.path.join(d, '*.py'))
    print(f'{d}: {len(files)} files')
    for f in files:
        path = os.path.join(d, f)
        with open(path, 'r') as fh:
            content = fh.read()
        if 'CRITICAL GUARD' in content:
            print(f'  {os.path.basename(f)}: already guarded')
        else:
            lines = content.split('\n')
            insert_idx = 0
            for i in range(min(20, len(lines))):
                line = lines[i].strip()
                if not line or line.startswith('#'):
                    insert_idx = i + 1
                else:
                    break
            
            new_lines = lines[:insert_idx] + [GUARD_TEXT.strip()] + lines[insert_idx:]
            new_content = '\n'.join(new_lines)
            
            with open(path, 'w') as fh:
                fh.write(new_content)
            print(f'  {os.path.basename(f)}: GUARD ADDED')

print('\nAll done. Verify guards with: python -c "from seed.runner import main" (should raise if SEED_DB=sms-db)')