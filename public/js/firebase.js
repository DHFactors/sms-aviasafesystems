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

// Strict beta/production configuration (2026-08). Both environments use the
// aerosafety-sms-prod Firebase project. Beta reads the isolated sms-db-beta
// named Firestore database and the beta Render backend; production uses the
// default sms-db database and the production backend. This keeps beta traffic
// entirely inside aerosafety-sms-prod while still isolating beta data in its
// own named database.
//
// Detection order (first match wins):
//   1. ?env=beta  or  ?beta=1                 (manual/temporary override)
//   2. localStorage "aviasafe_env" === "beta" (persisted override for testing)
//   3. window.__APP_ENV__ === "beta"          (deploy-time injected flag)
//   4. hostname contains "beta"               (e.g. betasms.aviasafesystems.com,
//                                              sms-beta.web.app, *-beta.onrender.com)
//   5. localhost / 127.0.0.1                  (local development)
// Anything else — sms.aviasafesystems.com, www.sms.aviasafesystems.com, tenant
// subdomains (*.aviasafesystems.com) and *.web.app hosts — is PRODUCTION.
function detectBetaEnvironment() {
    if (typeof window === 'undefined') return false;
    try {
        const params = new URLSearchParams(window.location.search);
        if (params.get('env') === 'beta' || params.get('beta') === '1') return true;
        if (window.localStorage && window.localStorage.getItem('aviasafe_env') === 'beta') return true;
    } catch (e) { /* ignore */ }
    if (window.__APP_ENV__ === 'beta') return true;
    const h = window.location.hostname || '';
    if (h.indexOf('beta') !== -1) return true;
    if (h === 'localhost' || h === '127.0.0.1') return true;
    return false;
}
const IS_BETA_ENV = detectBetaEnvironment();

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

const BETA_CONFIG = {
    apiKey: "AIzaSyCdCtUuyOcUIoCBEaiWGbhp6_XwZKHsicc",
    authDomain: "aerosafety-sms-prod.firebaseapp.com",
    projectId: "aerosafety-sms-prod",
    storageBucket: "aerosafety-sms-prod.firebasestorage.app",
    messagingSenderId: "527947363983",
    appId: "1:527947363983:web:4b736b6d1d50dd9b7a22fa",
    databaseId: "sms-db-beta",
    appCheckSiteKey: "6LeCcWwtAAAAAFK2Y3hwxjO3pHGX6xaFxFIzF6Jv"
};

const firebaseConfig = IS_BETA_ENV ? BETA_CONFIG : PROD_CONFIG;

// Per-environment reCAPTCHA v3 site key for App Check, sourced from the active
// Firebase config. Both environments share the same key registered on
// aerosafety-sms-prod.
const RECAPTCHA_SITE_KEY = firebaseConfig.appCheckSiteKey || '';

// Centralized application configuration (single source of truth)
const APP_CONFIG = {
    apiBaseUrl: IS_BETA_ENV
        ? 'https://sms-aviasafesystems-beta.onrender.com'
        : 'https://aviasafe-unified-platform.onrender.com',
    environment: IS_BETA_ENV ? 'beta' : 'production',
    recaptchaSiteKey: RECAPTCHA_SITE_KEY,
    pagination: { defaultPageSize: 20, maxPageSize: 100 },
};

// Environment-prefixed storage keys. Cross-environment data must never leak:
// beta state (demo tenant, setup key, persisted user) stays in a `aviasafe:beta:*`
// namespace, production in `aviasafe:prod:*`.
function storageKey(name) {
    return 'aviasafe:' + (IS_BETA_ENV ? 'beta' : 'prod') + ':' + String(name);
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
// the sms-db / sms-db-beta named databases this project uses. To fix that we
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

function initAppCheck() {
    if (typeof firebase === 'undefined' || !firebase.appCheck) return;
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('appcheck') === 'false') {
        console.log('ℹ️ App Check skipped via ?appcheck=false');
        return;
    }
    if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
        console.log('ℹ️ App Check skipped (localhost)');
        return;
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
    try {
        firebase.appCheck().activate(new firebase.appCheck.ReCaptchaV3Provider(RECAPTCHA_SITE_KEY), true);
        console.log('✅ App Check activated');
    } catch (e) {
        console.warn('⚠️ App Check activation failed:', e);
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
        initAppCheck();
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
    if (role === 'AIRLINE_ADMIN') return 'Corporate Safety Department';
    if (dept === 'CAMO') return 'CAMO Department';
    if (dept === 'Part-145') return 'Part-145 Maintenance Department';
    if (dept === 'Flight Operations') return 'Flight Operations Department';
    return dept || '';
}
window.getDepartmentLabel = getDepartmentLabel;

// ============================================================================
// ROLE-BASED ROUTING — where should a signed-in user land after login?
// ============================================================================

function getRoleDestination(user) {
    var role = (user && user.role) || 'USER';
    if (role === 'SUPER_ADMIN') return '/admin/production-setup.html';
    if (role === 'CAAN_SMD') return '/caan.html';
    if (role === 'USER') {
        var claims = (user && (user.claims || {})) || {};
        var department = claims.department || (user && user.department) || '';
        if (department) return '/dashboard/responsible-manager.html';
        return '/safety.html';
    }
    return '/safety.html';
}

function redirectByRole(user) {
    window.location.href = getRoleDestination(user);
}

console.log('📦 firebase.js loaded');