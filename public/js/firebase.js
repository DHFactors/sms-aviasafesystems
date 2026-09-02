/* ============================================================================
   FILE: firebase.js
   PATH: public/js/firebase.js
   VERSION: 2.0.0
   DATE CREATED: 2026-07-26
   DATE REVISED: 2026-07-26
   PURPOSE: Firebase client SDK initialization.
            Loads Firebase SDK dynamically and initializes services.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

// ============================================================================
// FIREBASE CONFIGURATION
// ============================================================================

// Single consolidated environment (2026): the whole platform runs against the
// `sms-db` named Firestore database in the aerosafety-sms-prod project. The
// former isolated `sms-db-beta` environment (and its beta host detection) has
// been decommissioned — every host uses the same config.
const IS_BETA_ENV = false;

const PROD_CONFIG = {
    apiKey: "AIzaSyCdCtUuyOcUIoCBEaiWGbhp6_XwZKHsicc",
    authDomain: "aerosafety-sms-prod.firebaseapp.com",
    projectId: "aerosafety-sms-prod",
    storageBucket: "aerosafety-sms-prod.firebasestorage.app",
    messagingSenderId: "527947363983",
    appId: "1:527947363983:web:4b736b6d1d50dd9b7a22fa",
    databaseId: "sms-db",
    appCheckSiteKey: "6LeCcWwtAAAAAFK2Y3hwxjO3pHGX6xaFxFIzF6Jv"
};

const firebaseConfig = PROD_CONFIG;

// Per-environment reCAPTCHA v3 site key for App Check, sourced from the active
// Firebase config. Both environments share the same key registered on
// aerosafety-sms-prod.
const RECAPTCHA_SITE_KEY = firebaseConfig.appCheckSiteKey || '';

// Centralized application configuration (single source of truth)
const APP_CONFIG = {
    apiBaseUrl: 'https://aviasafe-unified-platform.onrender.com',
    environment: 'production',
    recaptchaSiteKey: RECAPTCHA_SITE_KEY,
    pagination: { defaultPageSize: 20, maxPageSize: 100 },
};

// Environment-prefixed storage keys. Data written on one host must never leak
// into another tenant's view; the `aviasafe:prod:*` namespace is the single
// live namespace.
function storageKey(name) {
    return 'aviasafe:prod:' + String(name);
}
function storageGet(name, storage) {
    try { return (storage || window.localStorage).getItem(storageKey(name)); }
    catch (e) { return null; }
}
function storageSet(name, value, storage) {
    try { (storage || window.localStorage).setItem(storageKey(name), String(value)); }
    catch (e) { /* ignore */ }
}
function storageRemove(name, storage) {
    try { (storage || window.localStorage).removeItem(storageKey(name)); }
    catch (e) { /* ignore */ }
}

window.APP_CONFIG = APP_CONFIG;
window.API_BASE_URL = APP_CONFIG.apiBaseUrl;
window.__FIREBASE_CONFIG__ = firebaseConfig;
window.storageKey = storageKey;
window.storageGet = storageGet;
window.storageSet = storageSet;
window.storageRemove = storageRemove;

// ============================================================================
// DYNAMIC LOADING OF FIREBASE SDK
// ============================================================================

function loadFirebaseSDK() {
    return new Promise((resolve, reject) => {
        // Check if Firebase is already loaded
        if (typeof firebase !== 'undefined' && firebase.initializeApp) {
            resolve(firebase);
            return;
        }

        // Load Firebase App SDK
        const scriptApp = document.createElement('script');
        scriptApp.src = 'https://www.gstatic.com/firebasejs/9.22.0/firebase-app-compat.js';
        scriptApp.async = true;
        scriptApp.onload = function() {
            // Load Firestore SDK
            const scriptFirestore = document.createElement('script');
            scriptFirestore.src = 'https://www.gstatic.com/firebasejs/9.22.0/firebase-firestore-compat.js';
            scriptFirestore.async = true;
            scriptFirestore.onload = function() {
                // Load Auth SDK
                const scriptAuth = document.createElement('script');
                scriptAuth.src = 'https://www.gstatic.com/firebasejs/9.22.0/firebase-auth-compat.js';
                scriptAuth.async = true;
                scriptAuth.onload = function() {
                    // Load App Check SDK
                    const scriptAppCheck = document.createElement('script');
                    scriptAppCheck.src = 'https://www.gstatic.com/firebasejs/9.22.0/firebase-app-check-compat.js';
                    scriptAppCheck.async = true;
                    scriptAppCheck.onload = function() {
                        // Load Storage SDK (optional)
                        const scriptStorage = document.createElement('script');
                        scriptStorage.src = 'https://www.gstatic.com/firebasejs/9.22.0/firebase-storage-compat.js';
                        scriptStorage.async = true;
                        scriptStorage.onload = function() {
                            initializeFirebase();
                            initAppCheck();
                            resolve(firebase);
                        };
                        scriptStorage.onerror = function() {
                            initializeFirebase();
                            initAppCheck();
                            resolve(firebase);
                        };
                        document.head.appendChild(scriptStorage);
                    };
                    scriptAppCheck.onerror = function() {
                        // App Check is optional
                        const scriptStorage = document.createElement('script');
                        scriptStorage.src = 'https://www.gstatic.com/firebasejs/9.22.0/firebase-storage-compat.js';
                        scriptStorage.async = true;
                        scriptStorage.onload = function() {
                            initializeFirebase();
                            resolve(firebase);
                        };
                        scriptStorage.onerror = function() {
                            initializeFirebase();
                            resolve(firebase);
                        };
                        document.head.appendChild(scriptStorage);
                    };
                    document.head.appendChild(scriptAppCheck);
                };
                scriptAuth.onerror = function() {
                    // Auth is optional, still resolve
                    initializeFirebase();
                    resolve(firebase);
                };
                document.head.appendChild(scriptAuth);
            };
            scriptFirestore.onerror = function() {
                // Firestore is optional, still resolve
                initializeFirebase();
                resolve(firebase);
            };
            document.head.appendChild(scriptFirestore);
        };
        scriptApp.onerror = function() {
            reject(new Error('Failed to load Firebase SDK'));
        };
        document.head.appendChild(scriptApp);
    });
}

function initializeFirebase() {
    if (typeof firebase !== 'undefined' && firebase.initializeApp) {
        try {
            // Check if already initialized
            if (!firebase.apps || firebase.apps.length === 0) {
                firebase.initializeApp(firebaseConfig);
                console.log('✅ Firebase initialized successfully');
            } else {
                console.log('ℹ️ Firebase already initialized');
            }
        } catch (error) {
            console.warn('Firebase initialization error:', error);
        }
    } else {
        console.warn('⚠️ Firebase SDK not available');
    }
}

// ============================================================================
// INITIALIZE SERVICES
// ============================================================================

let auth = null;
let db = null;

// ============================================================================
// NAMED DATABASE BINDING
// ============================================================================
// The compat SDK's firebase.firestore() always resolves to the "(default)"
// database and silently ignores a databaseId argument, so it can never reach
// the sms-db named database this project uses. To fix that we
// pull the modular Firestore from the app container using the database
// identifier, wrap it in the compat Firestore class, and route the namespace
// factory — and therefore every page's firebase.firestore() call — to it.
// This keeps db.collection(...), collectionGroup(...) and all compat firestore
// calls working against the correct database.

var _compatFirestoreFactory = null;
var _namedDbCache = {};

function getNamedFirestore(appCompat, databaseId) {
    if (_namedDbCache.hasOwnProperty(databaseId)) return _namedDbCache[databaseId];
    var container = appCompat._delegate.container;
    var modDb = container.getProvider('firestore').getImmediate({ identifier: databaseId });
    // Borrow a real persistence provider from a default compat instance so
    // enablePersistence() keeps working on the wrapped instance.
    var defaultCompat = _compatFirestoreFactory(appCompat);
    var compatDb = new _compatFirestoreFactory.Firestore(appCompat, modDb, defaultCompat._persistenceProvider);
    _namedDbCache[databaseId] = compatDb;
    return compatDb;
}

function patchFirestoreFactory() {
    if (_compatFirestoreFactory) return; // already patched
    _compatFirestoreFactory = firebase.firestore;
    var originalFactory = _compatFirestoreFactory;
    function factory(appArg, databaseIdArg) {
        var app = appArg || firebase.app();
        var dbId = databaseIdArg || firebaseConfig.databaseId;
        return getNamedFirestore(app, dbId);
    }
    for (var key in originalFactory) {
        if (typeof originalFactory[key] !== 'undefined') {
            factory[key] = originalFactory[key];
        }
    }
    firebase.firestore = factory;
}

// Ensure the Auth compat library is present before initServices() tries to
// call firebase.auth(). Some pages load only the App + Firestore compat SDKs,
// or load firebase.js before the auth-compat <script> has finished — calling
// firebase.auth() in that window throws "firebase.auth is not a function".
// Best-effort: load auth-compat dynamically when missing, then always resolve
// (auth stays null if the CDN script fails, never blocking the page).
function loadAuthCompatIfNeeded() {
    return new Promise(function (resolve) {
        if (typeof firebase === 'undefined') { resolve(); return; }
        if (typeof firebase.auth === 'function') { resolve(); return; }
        var script = document.createElement('script');
        script.src = 'https://www.gstatic.com/firebasejs/9.22.0/firebase-auth-compat.js';
        script.async = true;
        script.onload = function () { resolve(); };
        script.onerror = function () { resolve(); };
        document.head.appendChild(script);
    });
}

function initServices() {
    return loadAuthCompatIfNeeded().then(function () {
        if (typeof firebase !== 'undefined' && firebase.apps && firebase.apps.length > 0) {
            try {
                if (typeof firebase.auth === 'function') {
                    auth = firebase.auth();
                } else {
                    console.warn('⚠️ Firebase Auth SDK not available on this page — auth disabled.');
                }
                if (typeof firebase.firestore === 'function') {
                    patchFirestoreFactory();
                    db = getNamedFirestore(firebase.app(), firebaseConfig.databaseId);
                } else {
                    console.warn("Firestore SDK not available on this page.");
                }
                console.log('✅ Firebase services initialized');
            } catch (error) {
                console.warn('Error initializing Firebase services:', error);
            }
        } else {
            console.warn('⚠️ Cannot initialize services - Firebase not available');
        }
    });
}

// ============================================================================
// APP CHECK
// ============================================================================

function initAppCheckSafe(app) {
  try {
    const siteKey = RECAPTCHA_SITE_KEY || window.RECAPTCHA_SITE_KEY || "";
    // Only attempt App Check if an explicit site key exists
    if (!siteKey || siteKey === "YOUR_RECAPTCHA_SITE_KEY") {
      console.warn("[AppCheck] No valid reCAPTCHA site key found; bypassing App Check.");
      // Clear any stored throttle timestamp from prior runs
    clearAppCheckThrottle();
    return null;
  }

    const appCheck = initializeAppCheck(app, {
      provider: new ReCaptchaV3Provider(siteKey),
      isTokenAutoRefreshEnabled: false // Prevent continuous 403 retry spam
    });
    return appCheck;
  } catch (err) {
    console.warn("[AppCheck] Safe fallback activated; proceeding without App Check:", err);
    // Clear any stored throttle timestamp on failure
    clearAppCheckThrottle();
    return null;
  }
}

// Attach to window for global access
window.initAppCheckSafe = initAppCheckSafe;

// Clear any stored throttling timestamp from localStorage/sessionStorage
function clearAppCheckThrottle() {
  // Clear any stored throttling timestamp from localStorage/sessionStorage
  const keys = ["firebase:app-check", "app-check-throttle", "fb_app_check"];
  for (const key of keys) {
    try {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    } catch (e) { /* Ignore storage errors in incognito/private windows */ }
  }
  // Also attempt IndexedDB cleanup if available
  if (typeof indexedDB !== "undefined") {
    try {
      const dbRequest = indexedDB.deleteDatabase("firebase-app-check");
      dbRequest.onsuccess = () => { /* Database deleted successfully */ };
    } catch (e) { /* IndexedDB not available or error */ }
  }
}

// Attach to window for global access
window.clearAppCheckThrottle = clearAppCheckThrottle;

function initAppCheck() {
    if (typeof firebase === 'undefined' || !firebase.appCheck) return;
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('appcheck') === 'false') {
        console.log('ℹ️ App Check skipped via ?appcheck=false');
        return;
    }
    // Attempt safe App Check initialization — never blocks Auth/Firestore
    try {
        initAppCheckSafe(firebase.app());
    } catch (e) {
        console.warn("App Check initialization error, continuing gracefully:", e);
    }
    // Admin pages are SUPER_ADMIN + SETUP_SECRET gated; the reCAPTCHA provider
    // must not be able to break their auth requests.
    if (window.location.pathname.indexOf('/admin/') === 0) {
        console.log('ℹ️ App Check skipped (admin pages)');
        return;
    }
    if (!RECAPTCHA_SITE_KEY || RECAPTCHA_SITE_KEY.length < 20) {
        console.warn('⚠️ App Check skipped — no reCAPTCHA site key configured for this environment (' +
            APP_CONFIG.environment + '). Register one in the Firebase console (Security > App Check).');
        return;
    }
}

// Resolve a fresh App Check token (or null when App Check is unavailable) so
// public pages can attach it as X-Firebase-AppCheck to backend requests.
// Always resolves: a reCAPTCHA stall or failure (private windows, test
// browsers) must degrade to null instead of blocking the network dispatch.
function getAppCheckToken(timeoutMs) {
    var limit = timeoutMs || 3000;
    if (typeof firebase === 'undefined' || !firebase.appCheck || !firebase.appCheck().getToken) {
        return Promise.resolve(null);
    }
    return new Promise(function (resolve) {
        var settled = false;
        var done = function (value) {
            if (settled) return;
            settled = true;
            resolve(value ? value : null);
        };
        try {
            firebase.appCheck().getToken(true)
                .then(function (tokenResult) {
                    done(tokenResult && tokenResult.token ? tokenResult.token : null);
                })
                .catch(function () { done(null); });
        } catch (e) {
            done(null);
        }
        setTimeout(function () { done(null); }, limit);
    });
}
window.getAppCheckToken = getAppCheckToken;

// ============================================================================
// LOAD AND INITIALIZE
// ============================================================================

// Auto-initialize when loaded
(function() {
    // Check if Firebase is already available (from CDN in HTML)
    if (typeof firebase !== 'undefined' && firebase.initializeApp) {
        initializeFirebase();
        // Use safe App Check initialization — never blocks Auth/Firestore
        initAppCheckSafe(firebase.app());
        initServices().then(function() {
            window.firebase = firebase;
            window.auth = auth;
            window.db = db;
            console.log('✅ Firebase loaded from CDN');
        });
    } else {
        // Load dynamically
        loadFirebaseSDK()
            .then(function() {
                return initServices();
            })
            .then(function() {
                // Clear any stored throttle timestamp on fresh load
                clearAppCheckThrottle();
                window.firebase = firebase;
                window.auth = auth;
                window.db = db;
                console.log('✅ Firebase loaded dynamically');
            })
            .catch(function(error) {
                console.warn('⚠️ Firebase load failed:', error.message);
                window.firebase = null;
                window.auth = null;
                window.db = null;
            });
    }
})();

// ============================================================================
// SHARED AUTH HELPERS (used by all pages)
// ============================================================================

function waitForFirebase() {
    return new Promise(function(resolve) {
        if (typeof firebase !== 'undefined' && firebase.auth) {
            resolve();
            return;
        }
        var check = setInterval(function() {
            if (typeof firebase !== 'undefined' && firebase.auth) {
                clearInterval(check);
                resolve();
            }
        }, 30);
        setTimeout(function() {
            clearInterval(check);
            resolve();
        }, 10000);
    });
}

async function getCurrentUser() {
    await waitForFirebase();
    return new Promise(function(resolve) {
        var settled = false;
        var unsubscribe = null;
        var settle = function(value) {
            if (settled) return;
            settled = true;
            if (unsubscribe) {
                try { unsubscribe(); } catch (e) { /* ignore */ }
            }
            resolve(value);
        };
        try {
            if (typeof firebase === 'undefined' || !firebase.auth) {
                settle(null);
                return;
            }
            unsubscribe = firebase.auth().onAuthStateChanged(async function(user) {
                if (settled) return;
                if (!user) return; // not signed in — let the timeout settle(null)
                try {
                    // Forced refresh can stall on App Check / reCAPTCHA or a
                    // cold network. Never block here: `settle` is guarded by a
                    // hard timeout below so the page can never hang on the
                    // "Checking ... access" gate.
                    var tokenResult = await user.getIdTokenResult(true);
                    var claims = (tokenResult && tokenResult.claims) || {};
                    settle({
                        uid: user.uid,
                        email: user.email,
                        role: claims.role || 'USER',
                        tenantId: claims.tenant_id || null,
                        claims: claims
                    });
                } catch (error) {
                    settle(null);
                }
            });
        } catch (error) {
            settle(null);
            return;
        }
        setTimeout(function() {
            settle(null);
        }, 8000);
    });
}

// ============================================================================
// DEPARTMENT LABEL — maps a user's role + custom claims to the department name
// shown in the central header banner (hero subtitle, below the tenant title).
// The user's email stays visible ONLY in the top-right header menu next to the
// Logout button; it is never displayed in the hero.
// ============================================================================

function getDepartmentLabel(claims) {
    var role = (claims && claims.role) || 'USER';
    var dept = (claims && claims.department) || '';
    if (role === 'CAAN_SMD') return 'State Aviation Safety Oversight';
    if (role === 'AIRLINE_ADMIN' || role === 'TENANT_ADMIN') return 'Corporate Safety Department';
    if (dept === 'CAMO') return 'CAMO Department';
    if (dept === 'Part-145') return 'Part-145 Maintenance Department';
    if (dept === 'Flight Operations') return 'Flight Operations Department';
    return dept || '';
}
window.getDepartmentLabel = getDepartmentLabel;

// ============================================================================
// ROLE-BASED ROUTING — where should a signed-in user land after login?
// ============================================================================

// ── Virtual Tenant Mirroring (demo-prospects.js integration) ────────────────
// public/js/demo-prospects.js must be included BEFORE this file on routing
// pages (login.html). All lookups are lazy so load order cannot throw.

function _demoProspects() {
    return (typeof window !== 'undefined' && window.DEMO_PROSPECTS) ? window.DEMO_PROSPECTS : null;
}

function _isAeEmail(email) {
    var e = String(email || '').toLowerCase();
    return e.indexOf('ae@') === 0 || e.indexOf('ae.') === 0;
}

function _isProspectAe(email) {
    if (!_isAeEmail(email)) return false;
    var dp = _demoProspects();
    return dp ? !!dp.getArchetypeId(email) : true; // unregistered ae@ still routes as AE
}

var DEMO_CONTEXT_STORAGE_KEY = 'demo_context';       // refined spec key
var DEMO_CONTEXT_LEGACY_KEY = 'demoContext';         // pre-referral fallback
var AE_ARCHETYPE_STORAGE_KEY = 'aeArchetypeId';

function _writeDemoContextStorage(json) {
    try {
        localStorage.setItem(DEMO_CONTEXT_STORAGE_KEY, json);
        localStorage.setItem(DEMO_CONTEXT_LEGACY_KEY, json);
        localStorage.setItem(AE_ARCHETYPE_STORAGE_KEY, ctx_archetype_of(json));
    } catch (e) { /* non-fatal */ }
}
function ctx_archetype_of(json) {
    try { return (JSON.parse(json) || {}).archetypeId || ''; } catch (e) { return ''; }
}

/**
 * Resolve the Virtual Tenant Mirroring context for a signed-in AE:
 * reads the email, looks up PROSPECT_REGISTRY, persists the context to
 * window.DEMO_CONTEXT + localStorage, and binds the reference formatter to
 * the prospect's IATA code.
 * Accepts either a bare email string or a user-like object ({email}).
 * @param {string|{email?:string}} userLike
 * @returns {object|null} { archetypeId, companyName, aeName, fleetType,
 *                         baseLocation, iataCode, email }
 */
function resolveTenantContext(userLike) {
    var dp = _demoProspects();
    var email = String(
        (typeof userLike === 'string') ? userLike : ((userLike && userLike.email) || '')
    ).toLowerCase();

    var prospect = dp ? dp.getProspectByEmail(email) : null;
    var archetypeId = prospect ? prospect.archetypeId
        : (_isAeEmail(email) ? 'demo-fixed-wing' : null); // defensive fallback

    if (!archetypeId) return null;

    var ctx = {
        archetypeId: archetypeId,
        companyName: (prospect && prospect.companyName) || 'Accountable Executive Demo',
        aeName: (prospect && prospect.aeName) || 'Accountable Executive',
        fleetType: (prospect && prospect.fleetType) || '',
        baseLocation: (prospect && prospect.baseLocation) || '',
        iataCode: (prospect && prospect.iataCode) || 'AE',
        email: email,
    };

    window.DEMO_CONTEXT = ctx;
    _writeDemoContextStorage(JSON.stringify(ctx));

    // Initialize the reference formatter with the prospect's IATA code.
    window.formatReference = function (refString, iataCode) {
        var code = iataCode || ctx.iataCode;
        if (!refString) return refString || '';
        if (!code) return refString;
        return String(refString).replace(/^(FW|RW)-/, code.trim().toUpperCase() + '-');
    };
    return ctx;
}

/** Stored context (survives navigation), or null. Reads both storage keys. */
function getStoredDemoContext() {
    try {
        var raw = localStorage.getItem(DEMO_CONTEXT_STORAGE_KEY) ||
                  localStorage.getItem(DEMO_CONTEXT_LEGACY_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
}

/**
 * Reference formatter convenience — uses the active DEMO_CONTEXT IATA code
 * unless an explicit code is passed.
 */
function formatReference(refString, iataCode) {
    var ctx = window.DEMO_CONTEXT || getStoredDemoContext() || {};
    var dp = _demoProspects();
    if (dp && dp.formatReference) return dp.formatReference(refString, iataCode || ctx.iataCode);
    var code = (iataCode || ctx.iataCode || '').trim().toUpperCase();
    if (!code || !refString) return refString || '';
    return String(refString).replace(/^(FW|RW)-/, code + '-');
}

window.resolveTenantContext = resolveTenantContext;
window.formatReference = formatReference;
window.getStoredDemoContext = getStoredDemoContext;

function getRoleDestination(user) {
    var role = (user && user.role) || 'USER';
    if (role === 'SUPER_ADMIN') return '/admin/production-setup.html';
    if (role === 'CAAN_SMD') return '/caan.html';
    // Accountable Executive accounts (ae@{domain}) get the executive
    // governance dashboard — top-level SMS oversight per ICAO Annex 19 /
    // Doc 10159. Safety Managers (safety@) keep the operational workspace.
    if (role === 'AIRLINE_ADMIN' || role === 'TENANT_ADMIN') {
        var email = ((user && user.email) || '').toLowerCase();
        if (_isAeEmail(email)) {
            // Resolve + persist the mirroring context BEFORE the dashboard
            // loads so panels render with the prospect's branding/formatter.
            try { resolveTenantContext({ email: email }); } catch (e) { /* non-fatal */ }
            return '/dashboard/ae-dashboard.html';
        }
    }
    if (role === 'USER') {
        var claims = (user && (user.claims || {})) || {};
        var department = claims.department || (user && user.department) || '';
        if (department) return '/dashboard/responsible-manager.html';
        return '/safety.html';
    }
    return '/safety.html';
}

// ── Role-class toggle for element visibility ───────────────────────────────
// Drives CSS (e.g. `body.role-safety .operational { display:none }`) by adding
// a profile class to <body> once auth resolves. Operational/departmental
// logins (ops@, camo@, 145, pilot@) become `role-operational` and keep
// operational-only controls; safety-management accounts (safety@, airline/tenant
// admins, CAAN/SUPER) become `role-safety` and hide them. Runs centrally on
// every page that loads this file -- no page-specific hardcoding.
function isSafetyManagementRole(email, role) {
    var e = String(email || '').toLowerCase();
    if (e.indexOf('safety@') === 0) return true;
    var r = String(role || '').toUpperCase();
    if (r === 'SUPER_ADMIN' || r === 'CAAN_SMD') return true;
    // Accountable Executives (ae@) are AIRLINE_ADMIN but sit on the executive
    // governance surface, not the operational workspaces, so keep them operational.
    if (r === 'AIRLINE_ADMIN' || r === 'TENANT_ADMIN') {
        return !(e.indexOf('ae@') === 0 || e.indexOf('ae.') === 0);
    }
    return false;
}
window.isSafetyManagementRole = isSafetyManagementRole;

function initRoleClassToggle() {
    function apply(user) {
        try {
            var body = document.body;
            if (!body) return;
            body.classList.remove('role-safety', 'role-operational');
            var email = (user && user.email) || '';
            var claims = (user && user.claims) || {};
            var role = claims.role || (user && user.role) || 'USER';
            body.classList.add(isSafetyManagementRole(email, role)
                ? 'role-safety'
                : 'role-operational');
        } catch (e) { /* never block auth */ }
    }
    if (typeof firebase !== 'undefined' && firebase.auth) {
        try { firebase.auth().onAuthStateChanged(apply); } catch (e) { /* ignore */ }
    }
}
if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initRoleClassToggle);
    } else {
        initRoleClassToggle();
    }
}

// ── Auth-state sync for tenant + mirroring contexts ────────────────────────
// 1) Keeps sessionStorage demo tenant in sync with the signed-in user's
//    actual tenant_id (fixes safety.html showing air-dynasty-demo when logged
//    in as safety@fishtailair.com). 2) Keeps DEMO_CONTEXT fresh for AEs.
if (typeof firebase !== 'undefined' && firebase.auth) {
    try {
        firebase.auth().onAuthStateChanged(function (u) {
        try {
            // Tenant sync: on sign-in, pin sessionStorage to the user's tenant;
            // on sign-out, clear it so the next persona can't inherit it.
            if (typeof TenantResolver !== 'undefined' && TenantResolver.syncDemoTenantWithAuth) {
                if (u) {
                    // Need claims for tenant_id — fetch async, but also set a
                    // best-effort sync from cached __AUTH_TENANT_ID if available
                    u.getIdTokenResult(false).then(function (tr) {
                        var tenantId = (tr.claims && (tr.claims.tenant_id || tr.claims.tenantId)) || null;
                        var role = tr.claims && tr.claims.role;
                        TenantResolver.syncDemoTenantWithAuth({ tenantId: tenantId, tenant_id: tenantId, role: role, claims: tr.claims });
                        try { window.__AUTH_TENANT_ID = tenantId || null; } catch (e2) {}
                    }).catch(function () {
                        // Fallback: if token fetch fails, at least don't keep stale demo tenant
                    });
                } else {
                    // Signed out — exhaustive clear
                    if (TenantResolver.clearTenantSession) TenantResolver.clearTenantSession();
                    else if (TenantResolver.clearDemoTenant) TenantResolver.clearDemoTenant();
                    try {
                        window.__AUTH_TENANT_ID = null;
                        // Copilot session counters must not survive logout
                        var ck = (typeof storageKey === 'function' ? storageKey('copilot_message_count') : 'aviasafe_copilot_message_count');
                        sessionStorage.removeItem(ck);
                        sessionStorage.removeItem('aviasafe_copilot_message_count');
                        sessionStorage.removeItem('aviasafe:beta:copilot_message_count');
                        sessionStorage.removeItem('aviasafe:prod:copilot_message_count');
                    } catch (e2) {}
                }
            }
        } catch (e) { /* never block auth */ }
        try {
            if (u && _isProspectAe(u.email)) {
                resolveTenantContext({ email: u.email });
            } else if (!u || !_isAeEmail(u.email)) {
                window.DEMO_CONTEXT = null;
                localStorage.removeItem(DEMO_CONTEXT_STORAGE_KEY);
                localStorage.removeItem(DEMO_CONTEXT_LEGACY_KEY);
                localStorage.removeItem(AE_ARCHETYPE_STORAGE_KEY);
            }
        } catch (e) { /* storage errors are non-fatal */ }
        });
    } catch (err) { /* never let the auth hook break page load */ }
}

// ── Quick-Switch Demo Toolbar (?demo=true) ──────────────────────────────────
// Floating prospect switcher for sales demos. Enabled only when ?demo=true is
// present (persisted for the browser session); hidden for all other sessions.
function initDemoToolbar() {
    try {
        var params = new URLSearchParams(window.location.search);
        if (params.get('demo') === 'true') sessionStorage.setItem('demoToolbar', '1');
        if (sessionStorage.getItem('demoToolbar') !== '1') return;

        var dp = _demoProspects();
        if (!dp) return;
        var options = [
            { key: 'ae@buddha-air.com', label: 'Buddha Air — ATR 72 Fleet (Fixed-Wing)' },
            { key: 'ae@fishtailair.com', label: 'Fishtail Air — H125 Fleet (Rotary-Wing)' },
        ];

        var wrap = document.createElement('div');
        wrap.id = 'demoToolbar';
        wrap.style.cssText = 'position:fixed;bottom:14px;right:14px;z-index:9999;display:flex;' +
            'align-items:center;gap:0.45rem;background:#081f33;color:#fff;padding:0.5rem 0.7rem;' +
            'border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,0.35);font-family:Inter,Arial,sans-serif;';
        wrap.innerHTML = '<span style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.5px;color:#8fa8bd;">Demo</span>';

        var sel = document.createElement('select');
        sel.style.cssText = 'background:#123a5c;color:#fff;border:1px solid rgba(255,255,255,0.3);' +
            'border-radius:6px;padding:0.3rem 0.5rem;font-size:0.78rem;';
        options.forEach(function (o) {
            var opt = document.createElement('option');
            opt.value = o.key;
            opt.textContent = o.label;
            sel.appendChild(opt);
        });

        var current = getStoredDemoContext();
        if (current && current.email) sel.value = current.email.toLowerCase();

        sel.addEventListener('change', function () {
            var fromCtx = getStoredDemoContext() || {};
            var ctx = resolveTenantContext({ email: sel.value });
            if (!ctx) return;
            // Analytics: archetype switch signal (Chunk 7).
            try {
                document.dispatchEvent(new CustomEvent('demoSwitch', { detail: {
                    from: fromCtx.archetypeId || null,
                    to: ctx.archetypeId || null,
                    fromCompany: fromCtx.companyName || null,
                    toCompany: ctx.companyName || null,
                    timestamp: new Date().toISOString(),
                }}));
            } catch (e) { /* non-fatal */ }
            // Preferred: live re-fetch + re-format on AE dashboards that
            // expose a refresh hook; fallback to a full reload elsewhere.
            if (typeof window.__aeRefresh === 'function') {
                try { window.__aeRefresh(); } catch (e) { window.location.reload(); }
            } else {
                window.location.reload();
            }
        });

        wrap.appendChild(sel);
        document.body.appendChild(wrap);

        // Demo-mode indicator: subtle badge in the top-right header area
        // (falls back to a fixed corner chip when no header is present).
        var enabledAt = parseInt(sessionStorage.getItem('demoEnabledAt') || '0', 10);
        if (!enabledAt) {
            enabledAt = Date.now();
            sessionStorage.setItem('demoEnabledAt', String(enabledAt));
        }
        var expiresAt = enabledAt + 8 * 3600 * 1000; // 8-hour demo session
        var expiresLabel = new Date(expiresAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        var indicatorText = '\uD83D\uDD2C Demo Environment \u2014 Simulated Data \u00B7 expires ' + expiresLabel;

        var host = document.querySelector('.nav .nav-actions');
        if (host) {
            var badge = document.createElement('span');
            badge.className = 'badge badge-subtle-secondary';
            badge.id = 'demoModeIndicator';
            badge.title = 'Session expires ' + expiresLabel;
            badge.style.cssText = 'font-size:0.75rem;opacity:0.85;background:#f1f5f9;color:#94a3b8;' +
                'border:1px solid #e2e8f0;border-radius:999px;padding:0.25rem 0.7rem;';
            badge.textContent = indicatorText.replace(' \u00B7 expires ' + expiresLabel, '');
            host.insertBefore(badge, host.firstChild);
        } else {
            var chipEl = document.createElement('div');
            chipEl.id = 'demoModeIndicator';
            chipEl.style.cssText = 'position:fixed;top:14px;right:14px;z-index:9998;background:#f1f5f9;' +
                'color:#94a3b8;border:1px solid #e2e8f0;border-radius:999px;padding:0.25rem 0.7rem;' +
                'font-size:0.66rem;font-family:Inter,Arial,sans-serif;';
            chipEl.textContent = indicatorText;
            document.body.appendChild(chipEl);
        }
    } catch (e) { /* toolbar is cosmetic — never block the page */ }
}

if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initDemoToolbar);
    } else {
        initDemoToolbar();
    }
}

function redirectByRole(user) {
    window.location.href = getRoleDestination(user);
}

console.log('📦 firebase.js loaded');