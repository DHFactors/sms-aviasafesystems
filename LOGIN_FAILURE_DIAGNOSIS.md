# LOGIN_FAILURE_DIAGNOSIS.md — Production login "App Check token required"

Date: 2026-09-23. Commit d412dd4 deployed to aerosafety-sms-prod.web.app.
Mode: read-only diagnosis. No code changed.

## 1. Executive summary (ranked root causes)

1. **reCAPTCHA key domain registration (most likely).** Deployed code is
   correct (verified byte-for-byte below). Locally, init succeeds but
   Google's `recaptcha/api2/clr` returns **400 for unregistered origins**,
   `getToken()` resolves null, no header is sent, backend strict-check
   rejects. If `aerosafety-sms-prod.web.app` is not registered for key
   `6LeCc…F6Jv` (owner only confirmed `sms.aviasafesystems.com`), the
   owner testing on the **web.app URL fails exactly this way**.
2. **Test on the wrong host.** Owner reported testing at
   `aerosafety-sms-prod.web.app`; the registered production domain is
   `sms.aviasafesystems.com`. Same code, different Google verdict.
3. **Client environment.** Private-window tracking prevention or an
   ad-blocker killing `google.com/recaptcha` also yields null token →
   same 403. Check console for `[AppCheck]` lines to distinguish.
4. **Password is a red herring (for now).** The form shows the backend's
   `detail` verbatim: 403 shows "App Check token required", 401 shows
   "Invalid email or password" — distinct strings. The owner sees the
   403 string, so Firebase Auth **never evaluated the password**.
   `DEV-Aviasafe-2026` correctness is UNKNOWN until App Check passes.

## 2. Part A — deployed code verification

- `GET aerosafety-sms-prod.web.app/js/firebase.js` → 200.
  `VERSION: 2.0.2`, `DATE REVISED: 2026-09-23`, `hasModularApi`,
  `hasCompatApi`, `Initialized successfully (compat API)` all present.
  Matches commit d412dd4.
- `GET aerosafety-sms-prod.web.app/login.html` → 200.
  `firebase-app-check-compat.js` tag present **before** `/js/firebase.js`.
  Matches. No deploy mismatch.

## 3. Part B — header attachment (public/*.js)

- `X-Firebase-AppCheck` senders: `login.html:204-206`
  (`getAppCheckHeader`, awaited), `register.html:314-316`,
  `join.html:237-239`, `js/components/copilot-widget.js:435-437`.
- `getAppCheckToken` defined once: `js/firebase.js:348`, exposed `:372`.
- Login client **does** attach the header — but only when the token is
  non-null. Null token (init failed / Google refused) → header omitted,
  not forged. Failure mode (b): token null at send time.

## 4. Part C — login.html request trace

`loginForm submit` → `signIn(email, password)` → `fetch(getApiBaseUrl()
+ '/api/v1/auth/login', { headers: {Content-Type} + await
getAppCheckHeader() })`. Base URL = `APP_CONFIG.apiBaseUrl` =
`https://aviasafe-unified-platform.onrender.com` (Render backend).
Token awaited before send. No AdminUI/ApiClient wrapper on this page.

## 5. Part D — backend enforcement

- `POST /api/v1/auth/login` (`routes/auth.py:68-72`) uses
  `verify_app_check_strict`. Missing header → **403
  `{"detail": "App Check token required"}`** (`middleware/app_check.py:70-74`).
  Present-but-invalid → 401 "App Check verification failed".
- Strict also on auth.py:154,436; lenient (`verify_app_check`) on
  :239,291,389,502. Owner's message proves the H3 strict build is live
  on Render. Enforcement must NOT be weakened.

## 6. Part E — password vs App Check

- 403 → form shows backend detail: **"App Check token required"**.
- 401 → form shows: **"Invalid email or password"** (auth.py:95).
- 404/429/5xx → dedicated messages (service unavailable / rate limited).
- Strings are distinct, so the owner's report = App Check gate fired
  first (FastAPI dependency runs before credential check). Password
  `DEV-Aviasafe-2026` was never tested — verdict UNKNOWN. (Also note the
  5-failures/15-min per-IP lockout on this endpoint.)

## 7. Part F — reCAPTCHA config

- Key in code: `appCheckSiteKey: "6LeCcWwtAAAAAFK2Y3hwxjO3pHGX6xaFxFIzF6Jv"`
  (`js/firebase.js:30`), wired to `RECAPTCHA_SITE_KEY` (:40) and
  `APP_CONFIG.recaptchaSiteKey` (:46). No overrides anywhere.
- Repo documents canonical hosts (`sms.aviasafesystems.com`,
  `aerosafety-sms-prod.web.app`, …) for CORS, but **nothing documents
  which domains are registered in the reCAPTCHA admin console for this
  key**. Registration cannot be verified from code.

## 8. Next step to unblock login (owner, ~5 min, browser only)

1. Open `https://sms.aviasafesystems.com/login.html` (the registered
   domain — NOT the web.app URL), DevTools → Console.
2. If console shows `[AppCheck] Initialized successfully (compat API)`:
   attempt login, check the POST carries `X-Firebase-AppCheck`, report
   the status. 200/401 here settles it (401 then means password).
3. If console shows a reCAPTCHA/`recaptcha-error` line or no header is
   sent on the registered domain either: open reCAPTCHA admin for key
   `6LeCc…F6Jv` and register **both** `sms.aviasafesystems.com` and
   `aerosafety-sms-prod.web.app`, then retry.
4. Do not retest passwords until step 2 shows a non-403 status.

UNKNOWN items: reCAPTCHA admin domain list; correctness of
`DEV-Aviasafe-2026`; owner's exact console output on the web.app host.

---

## Resolution (2026-09-25)

The production login failure was caused by **four compounding bugs**,
each of which masked the next. No single fix would have resolved the
issue — the diagnosis required peeling back each layer in sequence.

### Layer 1 — Frontend used a legacy reCAPTCHA v3 key
- `public/js/firebase.js` referenced the legacy key
  `6LeCcWwtAAAAAFK2Y3hwxjO3pHGX6xaFxFIzF6Jv`
- Firebase App Check was configured for **reCAPTCHA Enterprise
  (Fraud Defense)**, not legacy v3
- Mismatch → all App Check token requests returned 400 Bad Request

**Fix:** Created a new Enterprise score-based key (`6LdPWs0t...`) with
the correct domain allow-list, linked it in Firebase App Check, and
updated `firebase.js` to reference it.

### Layer 2 — Frontend silently dropped the App Check token
- `public/login.html` used a "best-effort" pattern that returned `{}`
  when `getAppCheckToken()` resolved null
- The login POST was sent without the `X-Firebase-AppCheck` header
- The backend returned 403 "App Check token required"

**Fix:** `getAppCheckToken()` now retries once on null and logs the
failure reason. `login.html` blocks the submit with a visible error
if the token is unavailable instead of silently dropping it.

### Layer 3 — Loguru `%s` placeholders silently swallowed the error
- `backend/app/middleware/app_check.py:57` and the lenient path at
  line 107 used `logger.warning("... %s", e)` with **loguru**
- Loguru uses `{}` formatting; the `%s` was printed literally and the
  exception `e` was discarded
- Same bug in `backend/app/services/spi_service.py:605`
- This made every failed verification look identical in logs, hiding
  the real error for days

**Fix:** Changed `%s` → `{}` in the three affected loguru calls.
Stdlib `logging` calls (e.g. in `main.py` diagnostic block) were left
alone because stdlib logging does support `%s`.

### Layer 4 — Backend called a non-existent SDK method
- `backend/app/middleware/app_check.py` called
  `firebase_admin.app_check.verify_app_check_token(token)`
- That method **does not exist** in the Firebase Admin Python SDK
- The correct method is `firebase_admin.app_check.verify_token(token)`
- Every verification raised `AttributeError`, caught by the surrounding
  `except Exception`, and returned 401 "App Check verification failed"

**Fix:** Changed the method name to `verify_token` (code line plus the
header comment referencing it). After this fix, the token was accepted
and login succeeded.

### Diagnostic technique that broke the deadlock
After three cleanup deploys still produced identical error messages,
a **temporary diagnostic block** was added to `backend/app/main.py`
(commit `41c0b84`) that logged, at startup:
- The absolute path of the loaded `app_check.py`
- Its SHA256 hash
- The literal source line containing "App Check verification failed"

This proved the container loaded the correct code, isolating the
remaining problem to a **runtime** layer (logging format) rather than
a deployment or source layer. Once loguru was fixed, the real error
("module has no attribute verify_app_check_token") became visible
immediately.

The diagnostic block was removed in commit `0719c4f` after resolution.

### Postmortem notes
- **Loguru vs stdlib formatting is a silent trap.** Any stdlib-style
  `logger.warning("...%s", x)` passed to loguru will print `%s`
  literally and discard the argument. When adding loguru calls, always
  use `{}` placeholders.
- **Silent failure paths hide root causes.** The frontend's "if token
  is truthy, attach header; else do nothing" pattern masked the
  original error for hours. Failing loud (or blocking the submit) would
  have surfaced the issue far faster.
- **Firebase Admin SDK method names are easy to get wrong.** Verify
  against `dir(firebase_admin.app_check)` when writing new verification
  code. The correct method is `verify_token`, not
  `verify_app_check_token`.
- **Four compounding bugs is rare but possible.** When a fix reveals a
  new error rather than resolving the issue, keep peeling — do not
  assume the first fix "didn't work."
