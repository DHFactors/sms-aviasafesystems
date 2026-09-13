/* ============================================================================
   FILE: admin.js
   PATH: public/js/admin.js
   PURPOSE: Shared Super-Admin panel helpers — role guard, authenticated API
            calls, setup-key handling, toasts, small DOM utilities.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

(function (global) {
    'use strict';

    // ========================================================================
    // AUTH GUARD — requires SUPER_ADMIN, redirects to /admin/login.html
    // ========================================================================

    async function requireAdmin() {
        await waitForFirebase();
        const user = await getCurrentUser();
        if (!user) {
            global.location.href = '/admin/login.html';
            return null;
        }
        if (user.role !== 'SUPER_ADMIN') {
            global.alert('Access denied. SUPER_ADMIN role required.');
            global.location.href = '/';
            return null;
        }
        return user;
    }

    // ========================================================================
    // API — uses the shared ApiClient (auto token + 401 redirect)
    // ========================================================================

    async function apiGet(path) {
        const data = await ApiClient.get(path);
        if (!data) throw new Error('Request failed');
        return data;
    }

    async function apiPost(path, body) {
        const data = await ApiClient.post(path, body);
        if (!data) throw new Error('Request failed');
        return data;
    }

    async function apiPut(path, body) {
        const data = await ApiClient.put(path, body);
        if (!data) throw new Error('Request failed');
        return data;
    }

    async function apiPatch(path, body) {
        const data = await ApiClient.patch(path, body);
        if (!data) throw new Error('Request failed');
        return data;
    }

    // ========================================================================
    // SETUP KEY — stored in sessionStorage for this tab only (NEVER
    // localStorage). The key is env-prefixed (aviasafe:{env}:setup_key) so
    // beta sessions can never reuse a production setup secret (or vice versa).
    //
    // Idle timeout: the stored key expires after SETUP_KEY_TIMEOUT_MS (15 min
    // default) without mouse/keyboard/scroll activity. It is also cleared when
    // the tab has been hidden for > 5 minutes (short window-switches are
    // harmless). On expiry the key storage is dropped, any visible setup-key
    // inputs are un-prefilled, and a subtle banner asks the user to re-enter.
    // Nothing here changes endpoint signatures / request bodies / routes.
    // ========================================================================

    var SETUP_KEY_STORAGE = (typeof global.window !== 'undefined' && typeof global.window.storageKey === 'function')
        ? global.window.storageKey('setup_key')
        : 'aviasafe_setup_key';
    var SETUP_KEY_TS_STORAGE = SETUP_KEY_STORAGE + '_ts';

    // Default 15 min idle; pages can change it via APP_CONFIG.setupKeyTimeoutMs.
    var SETUP_KEY_TIMEOUT_MS = (
        global.APP_CONFIG && typeof global.APP_CONFIG.setupKeyTimeoutMs === 'number' && global.APP_CONFIG.setupKeyTimeoutMs > 0
    ) ? global.APP_CONFIG.setupKeyTimeoutMs : 15 * 60 * 1000;

    var SETUP_KEY_HIDDEN_CLEAR_MS = 5 * 60 * 1000;
    var setupKeyLastSeen = 0;
    var setupKeyHiddenAt = 0;
    var setupKeyBannerTimer = null;

    function setupKeyUnprefill() {
        // Un-prefill every setup-key input on the page so an expired value can
        // never be silently reused. Tracks only the input's own value; the
        // real secret is validated server-side regardless.
        try {
            var inputs = global.document.querySelectorAll('input[id*="SetupKey"]');
            for (var i = 0; i < inputs.length; i++) inputs[i].value = '';
        } catch (e) { /* DOM not ready */ }
    }

    function setupKeyBanner() {
        try {
            var banner = global.document.getElementById('setupKeyExpiredBanner');
            if (!banner) {
                banner = global.document.createElement('div');
                banner.id = 'setupKeyExpiredBanner';
                banner.style.cssText = 'position:fixed;top:14px;left:50%;transform:translateX(-50%);' +
                    'z-index:9999;background:#fff7ed;border:1px solid #fdba74;color:#9a3412;' +
                    'padding:8px 16px;border-radius:8px;font-size:.85rem;font-weight:600;' +
                    'box-shadow:0 2px 10px rgba(0,0,0,.12);max-width:90vw;text-align:center;';
                global.document.body.appendChild(banner);
            }
            banner.textContent = 'Setup key expired — re-enter to continue';
            banner.style.display = 'block';
            if (setupKeyBannerTimer) clearTimeout(setupKeyBannerTimer);
            setupKeyBannerTimer = setTimeout(function () {
                banner.style.display = 'none';
            }, 6000);
        } catch (e) { /* ignore */ }
    }

    function setupKeyClear(showBanner) {
        try {
            global.sessionStorage.removeItem(SETUP_KEY_STORAGE);
            global.sessionStorage.removeItem(SETUP_KEY_TS_STORAGE);
        } catch (e) { /* storage unavailable */ }
        setupKeyLastSeen = 0;
        setupKeyUnprefill();
        if (showBanner) setupKeyBanner();
    }

    function setupKeyTouch() {
        // Refresh the idle clock only while a key is actually held. Flush the
        // timestamp at most every 5s to avoid writing on every keystroke.
        var now = Date.now();
        var hasKey = false;
        try { hasKey = !!global.sessionStorage.getItem(SETUP_KEY_STORAGE); } catch (e) { return; }
        if (!hasKey) return;
        if (now - setupKeyLastSeen < 5000) return;
        setupKeyLastSeen = now;
        try { global.sessionStorage.setItem(SETUP_KEY_TS_STORAGE, String(now)); } catch (e) { /* ignore */ }
    }

    function setupKeyCheckExpiry() {
        // Active expiry sweep so the key is removed (not merely unusable) as
        // soon as the idle window lapses, even if no action fires.
        var key = '';
        var ts = 0;
        try {
            key = global.sessionStorage.getItem(SETUP_KEY_STORAGE) || '';
            ts = Number(global.sessionStorage.getItem(SETUP_KEY_TS_STORAGE) || 0);
        } catch (e) { return; }
        if (key && (!ts || (Date.now() - ts) > SETUP_KEY_TIMEOUT_MS)) setupKeyClear(true);
    }

    function getSetupKey() {
        try {
            var key = global.sessionStorage.getItem(SETUP_KEY_STORAGE) || '';
            if (!key) return '';
            var ts = Number(global.sessionStorage.getItem(SETUP_KEY_TS_STORAGE) || 0);
            if (!ts || (Date.now() - ts) > SETUP_KEY_TIMEOUT_MS) {
                setupKeyClear(true);
                return '';
            }
            setupKeyLastSeen = ts;
            return key;
        } catch (e) { return ''; }
    }

    function setSetupKey(value) {
        var trimmed = (value || '').trim();
        if (trimmed) {
            try {
                global.sessionStorage.setItem(SETUP_KEY_STORAGE, trimmed);
                global.sessionStorage.setItem(SETUP_KEY_TS_STORAGE, String(Date.now()));
            } catch (e) { /* ignore */ }
            setupKeyLastSeen = Date.now();
        } else {
            setupKeyClear(false);
        }
    }

    function ensureSetupKey() {
        const key = getSetupKey();
        if (key) return key;
        const entered = global.prompt('Enter the admin setup key (SETUP_SECRET) to perform this action:');
        if (!entered) throw new Error('Setup key required');
        setSetupKey(entered);
        return entered.trim();
    }

    // Idle, visibility, and expiry listeners. Bound once; guard for pre-DOM.
    if (typeof global.window !== 'undefined' && typeof global.window.addEventListener === 'function') {
        global.window.addEventListener('mousemove', setupKeyTouch, { passive: true });
        global.window.addEventListener('keydown', setupKeyTouch, { passive: true });
        global.window.addEventListener('mousedown', setupKeyTouch, { passive: true });
        global.window.addEventListener('touchstart', setupKeyTouch, { passive: true });
        global.window.addEventListener('scroll', setupKeyTouch, { passive: true });
        global.window.addEventListener('wheel', setupKeyTouch, { passive: true });

        // Hidden > 5 min => fresh session on re-show. Short switches are kept.
        global.window.addEventListener('visibilitychange', function () {
            var state = global.document && global.document.visibilityState;
            if (state === 'hidden') {
                setupKeyHiddenAt = Date.now();
            } else if (setupKeyHiddenAt && (Date.now() - setupKeyHiddenAt) > SETUP_KEY_HIDDEN_CLEAR_MS) {
                setupKeyHiddenAt = 0;
                setupKeyClear(true);
            } else {
                setupKeyHiddenAt = 0;
            }
        });

        setInterval(setupKeyCheckExpiry, 15000);
    }

    // ========================================================================
    // UI HELPERS
    // ========================================================================

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function toast(message, type) {
        type = type || 'info';
        let container = document.getElementById('toastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toastContainer';
            container.style.cssText = 'position:fixed;top:20px;right:20px;z-index:1000;';
            document.body.appendChild(container);
        }
        const el = document.createElement('div');
        el.style.cssText = 'padding:12px 20px;margin-bottom:10px;border-radius:6px;color:#fff;' +
            'box-shadow:0 2px 10px rgba(0,0,0,0.15);background:' +
            (type === 'success' ? '#34a853' : type === 'error' ? '#ea4335' : '#1a6b8a') + ';';
        el.textContent = message;
        container.appendChild(el);
        setTimeout(function () { el.style.opacity = '0'; el.style.transition = 'opacity 0.4s'; setTimeout(function () { el.remove(); }, 400); }, 4000);
    }

    function fmtDate(value) {
        if (!value) return '—';
        const d = new Date(value);
        if (isNaN(d.getTime())) return '—';
        return d.toLocaleString();
    }

    function initSurveyQrCode(tenantSlug) {
    const qrPreview = document.getElementById('surveyQrPreview');
    const downloadQrBtn = document.getElementById('downloadQrBtn');
    const surveyLinkInput = document.getElementById('surveyLinkInput');
    const copySurveyLinkBtn = document.getElementById('copySurveyLinkBtn');
    const copyEmailBtn = document.getElementById('copyEmailBtn');

    if (!qrPreview || !downloadQrBtn || !surveyLinkInput || !copySurveyLinkBtn || !copyEmailBtn) return;

    const surveyUrl = `${window.location.origin}/survey/index.html?tenant=${tenantSlug}`;

    surveyLinkInput.value = surveyUrl;

    new QRCode(qrPreview, {
        text: surveyUrl,
        width: 160,
        height: 160,
        colorDark: '#0c334d',
        colorLight: '#ffffff',
        correctLevel: QRCode.CorrectLevel.H,
    });

    downloadQrBtn.onclick = function () {
        const qrCanvas = qrPreview.querySelector('canvas');
        if (qrCanvas) {
            const link = document.createElement('a');
            link.download = `${tenantSlug}-safety-survey-qr.png`;
            link.href = qrCanvas.toDataURL('image/png');
            link.click();
        }
    };

    copySurveyLinkBtn.onclick = function () {
        surveyLinkInput.select();
        document.execCommand('copy');
        toast('Link copied to clipboard!', 'success');
    };

    copyEmailBtn.onclick = function () {
        const emailText = `Please participate in our SMS Maturity Assessment survey:\n${surveyUrl}\n\nYour responses support our Safety Management System. Thank you!`;
        surveyLinkInput.value = emailText;
        surveyLinkInput.select();
        document.execCommand('copy');
        toast('Email announcement copied!', 'success');
    };
}

global.AdminUI = {
        requireAdmin: requireAdmin,
        apiGet: apiGet,
        apiPost: apiPost,
        apiPut: apiPut,
        apiPatch: apiPatch,
        getSetupKey: getSetupKey,
        setSetupKey: setSetupKey,
        ensureSetupKey: ensureSetupKey,
        esc: esc,
        toast: toast,
        fmtDate: fmtDate,
        initSurveyQrCode: initSurveyQrCode,
    };
})(window);
