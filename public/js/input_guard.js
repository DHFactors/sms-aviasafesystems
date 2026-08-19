/**
 * Frontend anti-bot + input-sanity helpers for the public auth & intake forms.
 *
 * Shared by login.html / register.html / join.html. Kept dependency-free and
 * UMD-wrapped so the exact same logic is unit-tested in Node
 * (frontend-tests/input-guard.test.js) and runs in the browser.
 *
 *   isDisposableEmail(email)  - disposable / temporary mail domain check
 *                               (mirrors backend/app/services/tenant_registration.py)
 *   isConsumerWebmail(email)  - consumer webmail (gmail/outlook/yahoo/…) check
 *   validateCorporateEmail()  - allowlist-aware corporate-email validator
 *   honeypotTrap(form)        - hidden honeypot "company_website_url" field;
 *                               when a bot fills it the submission is aborted
 *                               silently without revealing the trap.
 */
(function (root, factory) {
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = factory();
    } else {
        root.InputGuard = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    // Name of the hidden honeypot field used on the public auth forms. The
    // value must match the `name="..."` attribute of the honeypot input.
    var HONEYPOT_FIELD = 'company_website_url';

    // Disposable / temporary email providers. Keep in sync with
    // DISPOSABLE_EMAIL_DOMAINS in backend/app/services/tenant_registration.py.
    var DISPOSABLE_EMAIL_DOMAINS = [
        'mailinator.com',
        'tempmail.com',
        'tempmail.net',
        'temp-mail.org',
        'temp-mail.io',
        'guerrillamail.com',
        'guerrillamail.net',
        'guerrillamail.org',
        'guerrillamail.biz',
        'guerrillamail.info',
        'grr.la',
        '10minutemail.com',
        '10minutemail.net',
        'yopmail.com',
        'yopmail.fr',
        'yopmail.net',
        'yopmail.org',
        'throwawaymail.com',
        'throwaway.email',
        'maildrop.cc',
        'getnada.com',
        '33mail.com',
        'trashmail.com',
        'mailnesia.com',
        'spamgourmet.com',
        'disposablemail.com',
        'mailtemp.net'
    ];

    function emailDomain(email) {
        var addr = String(email == null ? '' : email).trim().toLowerCase();
        var at = addr.lastIndexOf('@');
        return at === -1 ? addr : addr.slice(at + 1);
    }

    function isDisposableEmail(email) {
        var domain = emailDomain(email);
        if (!domain) return false;
        if (DISPOSABLE_EMAIL_DOMAINS.indexOf(domain) !== -1) return true;
        for (var i = 0; i < DISPOSABLE_EMAIL_DOMAINS.length; i++) {
            var blocked = DISPOSABLE_EMAIL_DOMAINS[i];
            if (domain.length > blocked.length && domain.lastIndexOf('.' + blocked) === domain.length - blocked.length - 1) {
                return true;
            }
        }
        return false;
    }

    // Admin / developer test addresses that bypass the corporate-email
    // restriction. Keep in sync with ADMIN_EMAIL_ALLOWLIST in
    // backend/app/services/tenant_registration.py.
    var ALLOWED_TEST_EMAILS = [
        'ghanshyamacharya@outlook.com'
    ];

    // Consumer webmail providers treated as non-corporate. Keep in sync with
    // CONSUMER_WEBMAIL_DOMAINS in backend/app/services/tenant_registration.py.
    var CONSUMER_WEBMAIL_DOMAINS = [
        'gmail.com', 'googlemail.com',
        'yahoo.com', 'yahoo.co.uk', 'ymail.com',
        'outlook.com', 'hotmail.com', 'live.com', 'msn.com',
        'icloud.com', 'me.com', 'mac.com',
        'aol.com',
        'protonmail.com', 'proton.me',
        'zoho.com',
        'mail.com', 'gmx.com', 'gmx.net'
    ];

    function isAdminAllowlisted(email) {
        var addr = String(email == null ? '' : email).trim().toLowerCase();
        return ALLOWED_TEST_EMAILS.indexOf(addr) !== -1;
    }

    function isConsumerWebmail(email) {
        var domain = emailDomain(email);
        if (!domain) return false;
        if (CONSUMER_WEBMAIL_DOMAINS.indexOf(domain) !== -1) return true;
        for (var i = 0; i < CONSUMER_WEBMAIL_DOMAINS.length; i++) {
            var blocked = CONSUMER_WEBMAIL_DOMAINS[i];
            if (domain.length > blocked.length && domain.lastIndexOf('.' + blocked) === domain.length - blocked.length - 1) {
                return true;
            }
        }
        return false;
    }

    // Corporate-email validation for self-service registration. Allowlisted
    // admin/dev addresses always pass; disposable and consumer webmail domains
    // are rejected.
    function validateCorporateEmail(email) {
        if (isAdminAllowlisted(email)) {
            return { valid: true };
        }
        if (isDisposableEmail(email) || isConsumerWebmail(email)) {
            return { valid: false };
        }
        return { valid: true };
    }

    // True when the honeypot field is filled (a bot), false for clean humans.
    function honeypotFilled(form, fieldName) {
        if (!form) return false;
        var name = fieldName || HONEYPOT_FIELD;
        var field = null;
        try {
            field = form.elements ? form.elements[name] : null;
        } catch (e) { /* unknown field name */ }
        if (!field) return false;
        var value = (field.value != null ? field.value : '').trim();
        return value.length > 0;
    }

    // Convenience wrapper for form submit handlers: returns true when the
    // submission should be silently aborted (trap sprung).
    function honeypotTrap(form) {
        return honeypotFilled(form);
    }

    return {
        HONEYPOT_FIELD: HONEYPOT_FIELD,
        DISPOSABLE_EMAIL_DOMAINS: DISPOSABLE_EMAIL_DOMAINS,
        CONSUMER_WEBMAIL_DOMAINS: CONSUMER_WEBMAIL_DOMAINS,
        ALLOWED_TEST_EMAILS: ALLOWED_TEST_EMAILS,
        emailDomain: emailDomain,
        isDisposableEmail: isDisposableEmail,
        isAdminAllowlisted: isAdminAllowlisted,
        isConsumerWebmail: isConsumerWebmail,
        validateCorporateEmail: validateCorporateEmail,
        honeypotFilled: honeypotFilled,
        honeypotTrap: honeypotTrap
    };
}));