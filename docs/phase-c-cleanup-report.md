# C — Config Cleanup Report (Firestore env deprecation)

**Scope (per instructions):** comment out `FIREBASE_DATABASE_ID` / `FIREBASE_DATABASE_URL` in the
config surface; annotate the config.py constant as deprecated while keeping it defined; update
render.yaml header. **Not touched:** Supabase, Firebase Auth, any service code, seed/scripts,
docker-compose, docs.

---

## 1. Diff per file

### 1.1 `backend/.env` (untracked / gitignored, edited in place)
```diff
 FIREBASE_CLIENT_EMAIL=firebase-adminsdk-fbsvc@aerosafety-sms-prod.iam.gserviceaccount.com
-FIREBASE_DATABASE_URL=https://aerosafety-sms-prod.firebaseio.com
+# DEPRECATED (phase C, 2026-09-12): Firestore named database — Firestore is no
+# longer read by the backend (Auth-only). Kept commented for 30-day rollback.
+# Do not delete.
+# FIREBASE_DATABASE_URL=https://aerosafety-sms-prod.firebaseio.com

...
-FIREBASE_DATABASE_ID=sms-db
+# DEPRECATED (phase C, 2026-09-12): FIREBASE_DATABASE_ID is ignored (Auth-only;
+# Firestore removed). Kept commented for 30-day rollback. Do not delete.
+# FIREBASE_DATABASE_ID=sms-db
```
All `FIREBASE_PROJECT_ID` / `FIREBASE_PRIVATE_KEY` / `FIREBASE_CLIENT_EMAIL` kept active.

### 1.2 `backend/.env.example`
```diff
 FIREBASE_CLIENT_EMAIL=
-# Firestore named database (leave empty for (default)). Production uses sms-db.
-FIREBASE_DATABASE_ID=sms-db
+# DEPRECATED (phase C, 2026-09-12): Firestore named database (sms-db) — no
+# longer used (Auth-only). Kept commented for 30-day rollback. Do not delete.
+# FIREBASE_DATABASE_ID=sms-db
```
> Note: this file's working-tree diff also contains a pre-existing (A-phase, not C)
> unrelated hunk — an uncommented `ALLOWED_ORIGINS` example gains two extra origins.
> Left untouched.

### 1.3 `backend/.env.demo.example`
```diff
 FIREBASE_PROJECT_ID=<FILL_ME>
-# Demo targets the production database (single consolidated sms-db).
-FIREBASE_DATABASE_ID=sms-db
+# DEPRECATED (phase C, 2026-09-12): Firestore named database (sms-db) — no
+# longer used (Auth-only). Kept commented for 30-day rollback. Do not delete.
+# FIREBASE_DATABASE_ID=sms-db
```

### 1.4 `backend/app/core/config.py`
```diff
-    # Deprecated: Firestore named database (sms-db) — no longer used after
-    # B4 Auth-only trim (app/firebase.py no longer creates a Firestore client).
-    # Kept for env backward-compat; ignored.
+    # Deprecated (phase C, 2026-09-12): Firestore named database (sms-db) — no
+    # longer used after B4 Auth-only trim (app/firebase.py no longer creates a
+    # Firestore client). Kept for env backward-compat and 30-day rollback;
+    # ignored at runtime. Do NOT delete yet.
     FIREBASE_DATABASE_ID: Optional[str] = None
```
Constant remains **defined** (per spec) so residual references cannot crash import; its
value is `None` when the env var is absent. An earlier deprecation note already existed
from B4; C dates and hardens it.

### 1.5 `render.yaml`
```diff
 # Deploys the unified AviaSAFE API as one Docker web service. There is no
-# separate beta service: the platform runs against the consolidated `sms-db`
-# Firestore named database in the `aerosafety-sms-prod` project.
+# separate beta service.
+#
+# FIRESTORE DEPRECATION (phase C, 2026-09-12): the platform no longer reads the
+# Firestore named database `sms-db` (Auth-only). FIREBASE_DATABASE_URL and
+# FIREBASE_DATABASE_ID are commented out below; values stay in the dashboard for
+# 30-day rollback. All FIREBASE_AUTH_* keys remain active.
 ...
-      # ── Firebase Admin SDK (aerosafety-sms-prod / sms-db) ─────────────────
+      # ── Firebase Admin SDK (Auth-only; Firestore deprec. phase C 2026-09) ──
       - key: FIREBASE_PROJECT_ID
         sync: false
       - key: FIREBASE_PRIVATE_KEY
         sync: false
       - key: FIREBASE_CLIENT_EMAIL
         sync: false
-      - key: FIREBASE_DATABASE_URL
-        sync: false
-      - key: FIREBASE_DATABASE_ID
-        value: sms-db
+      # DEPRECATED (phase C, 2026-09-12): Firestore named database — no longer
+      # read (Auth-only). Kept commented for 30-day rollback. Do not delete.
+      # - key: FIREBASE_DATABASE_URL
+      #   sync: false
+      # - key: FIREBASE_DATABASE_ID
+      #   value: sms-db
```
All Auth env keys (`FIREBASE_PROJECT_ID` / `FIREBASE_PRIVATE_KEY` / `FIREBASE_CLIENT_EMAIL`)
and every other service key remain **active**.

---

## 2. Boot log excerpt (uvicorn startup)
```
INFO:     Started server process [8212]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8765 (Press CTRL+C to quit)
```
`GET /health` → **200** `{"status":"healthy","firebase":"connected","database":"connected","service":"AviaSAFE SMS API","version":"1.0.0"}`

## 3. Suite result
`python -m pytest -p no:cacheprovider -q --tb=short` → **810 passed, 0 failed, 16 warnings** in 0:09:51.

## 4. grep before/after — `sms-db` / `FIREBASE_DATABASE_*`

### 4.1 Active env assignments within the 5 in-scope files
| File | Before | After |
|---|---|---|
| `backend/.env` | `FIREBASE_DATABASE_URL` (L23), `FIREBASE_DATABASE_ID=sms-db` (L42) active | both commented |
| `backend/.env.example` | `FIREBASE_DATABASE_ID=sms-db` (L11) active | commented |
| `backend/.env.demo.example` | `FIREBASE_DATABASE_ID=sms-db` (L18) active | commented |
| `backend/app/core/config.py` | constant + deprecation note | constant kept, note dated (per spec) |
| `render.yaml` | `FIREBASE_DATABASE_URL` (L44), `FIREBASE_DATABASE_ID` (L46) active keys | both commented, header updated |

After C: **zero active `FIREBASE_DATABASE_*` env assignments** in the config surface; every
remaining `sms-db` token in these files is a comment, and the one active `config.py` reference
is the intentionally-retained constant.

### 4.2 Residual `sms-db` tokens OUTSIDE the 5-file scope (unchanged, reported for decision)
- `backend/scripts/*`, `backend/seed/*`, `backend/_audit_all_tenants.py`,
  `backend/_purge_prod_database.py` — standalone Firestore-admin seed/backfill utilities that
  legitimately target `sms-db`. These are not config and not service runtime code; left
  untouched per scope discipline.
- `docker-compose.yml` — `FIREBASE_DATABASE_ID=sms-db` env (L17) remains active; file was not
  in C's 5-file scope.
- `docs/archive/*`, `docs/*.md`, `session 10092026.md` — documentation/archival notes.

Recommend: decide during D/E whether these operational utilities/docker-compose env survive
Firestore removal or get their own cleanup task.

## 5. STOP — awaiting approval to proceed to D
C config cleanup complete and verified. Nothing beyond the 5 files was modified; B commit
`9a6e1f3` landed; C changes are uncommitted pending your commit instruction.