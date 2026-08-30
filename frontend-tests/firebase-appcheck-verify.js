const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC = fs.readFileSync(path.resolve(__dirname, '../public/js/firebase.js'), 'utf8');
const BETA_KEY = '6LeCcWwtAAAAAFK2Y3hwxjO3pHGX6xaFxFIzF6Jv';
let activatedProvider = null;

function makeFirebaseStub() {
    activatedProvider = null;
    const appCheckInstance = {
        activate(provider) { activatedProvider = provider; },
        getToken(force) {
            if (activatedProvider === null) throw new Error('App Check not activated');
            return Promise.resolve({ token: 'beta-token-123' });
        }
    };
    const appCheck = function () { return appCheckInstance; };
    appCheck.ReCaptchaV3Provider = class { constructor(key) { this.key = key; } };
    const app = { _delegate: { container: { getProvider() { return { getImmediate() { return {}; } }; } } } };
    return {
        initializeApp(config) { app.config = config; },
        apps: [],
        app() { return app; },
        auth() { return {}; },
        appCheck
    };
}

function run(hostname) {
    const loc = { hostname, pathname: '/register.html', search: '' };
    const sandbox = {
        location: loc,
        window: {
            location: loc,
            localStorage: { getItem() { return null; } },
        },
        document: { createElement() { return { appendChild() {} }; }, head: { appendChild() {} } },
        initializeAppCheck(app, opts) { activatedProvider = opts && opts.provider; return {}; },
        ReCaptchaV3Provider: class { constructor(key) { this.key = key; } },
        console,
        Promise,
        URLSearchParams,
        setTimeout,
        clearTimeout,
        setInterval,
        clearInterval
    };
    sandbox.window.window = sandbox.window;
    sandbox.globalThis = sandbox;
    const stub = makeFirebaseStub();
    sandbox.firebase = stub;
    sandbox.window.firebase = stub;
    const ctx = vm.createContext(sandbox);
    vm.runInContext(SRC, ctx);
    return ctx.window;
}

function assert(cond, msg) { if (!cond) { console.error('FAIL: ' + msg); process.exitCode = 1; } else { console.log('PASS: ' + msg); } }

(async () => {
    // The former beta host now resolves to the same consolidated config: the
    // sms-db named database in aerosafety-sms-prod. No separate BETA_CONFIG is
    // emitted (the isolated sms-db-beta environment is decommissioned).
    const betaWin = run('sms-beta.web.app');
    assert(betaWin.firebase.app().config === betaWin.__FIREBASE_CONFIG__, 'host picks the unified config');
    assert(betaWin.__FIREBASE_CONFIG__.projectId === 'aerosafety-sms-prod', 'config project = aerosafety-sms-prod');
    assert(betaWin.__FIREBASE_CONFIG__.databaseId === 'sms-db', 'consolidated database = sms-db');
    assert(JSON.stringify(betaWin.__FIREBASE_CONFIG__).indexOf('gap-analysis-ssp') === -1, 'config contains no gap-analysis-ssp reference');
    assert(betaWin.__FIREBASE_CONFIG__.appCheckSiteKey === BETA_KEY, 'appCheckSiteKey set');
    assert(activatedProvider && activatedProvider.key === BETA_KEY, 'App Check provider activated with shared key');
    assert(betaWin.APP_CONFIG.recaptchaSiteKey === BETA_KEY, 'APP_CONFIG.recaptchaSiteKey = shared key');
    const token = await betaWin.getAppCheckToken();
    assert(token === 'beta-token-123', 'getAppCheckToken() resolves');

    const localWin = run('localhost');
    assert(localWin.APP_CONFIG.environment === 'production', 'localhost uses the production environment');
    assert(localWin.APP_CONFIG.recaptchaSiteKey === BETA_KEY, 'localhost uses the shared key in APP_CONFIG');
    assert(activatedProvider === null, 'localhost skips App Check activation (reCAPTCHA unavailable on localhost)');
    const localToken = await localWin.getAppCheckToken();
    assert(localToken === null, 'getAppCheckToken() returns null on localhost (App Check inactive)');

    const prodWin = run('sms.aviasafesystems.com');
    assert(prodWin.__FIREBASE_CONFIG__.projectId === 'aerosafety-sms-prod', 'prod config = aerosafety-sms-prod');
    assert(prodWin.__FIREBASE_CONFIG__.databaseId === 'sms-db', 'prod database = sms-db');
    assert(prodWin.APP_CONFIG.recaptchaSiteKey === BETA_KEY, 'prod key set (shared key)');

    console.log('\nDone.');
})();