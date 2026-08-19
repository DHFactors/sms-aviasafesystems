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

    // ========================================================================
    // SETUP KEY — stored in sessionStorage for this tab only. The key is
    // env-prefixed (aviasafe:{env}:setup_key) so beta sessions can never reuse
    // a production setup secret (or vice versa).
    // ========================================================================

    var SETUP_KEY_STORAGE = (typeof global.window !== 'undefined' && typeof global.window.storageKey === 'function')
        ? global.window.storageKey('setup_key')
        : 'aviasafe_setup_key';

    function getSetupKey() {
        return global.sessionStorage.getItem(SETUP_KEY_STORAGE) || '';
    }

    function setSetupKey(value) {
        if (value) global.sessionStorage.setItem(SETUP_KEY_STORAGE, value.trim());
        else global.sessionStorage.removeItem(SETUP_KEY_STORAGE);
    }

    function ensureSetupKey() {
        const key = getSetupKey();
        if (key) return key;
        const entered = global.prompt('Enter the admin setup key (SETUP_SECRET) to perform this action:');
        if (!entered) throw new Error('Setup key required');
        setSetupKey(entered);
        return entered.trim();
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
        getSetupKey: getSetupKey,
        setSetupKey: setSetupKey,
        ensureSetupKey: ensureSetupKey,
        esc: esc,
        toast: toast,
        fmtDate: fmtDate,
        initSurveyQrCode: initSurveyQrCode,
    };
})(window);
