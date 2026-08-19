/**
 * Frontend unit tests for the anti-bot + input-sanity guards
 * (public/js/input_guard.js) shared by login.html / register.html / join.html.
 *
 * Covers the disposable-email blocklist, the honeypot trap logic, and a
 * page-wiring smoke check asserting the three public auth forms actually
 * ship the honeypot field, include input_guard.js and call the guards on
 * submit (the backend equivalents live in backend/tests/test_anti_spam_guardrails.py).
 */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const InputGuard = require('../public/js/input_guard.js');

// ---------------------------------------------------------------------------
// Disposable email blocklist
// ---------------------------------------------------------------------------

function test_disposable_email_blocks() {
    const blocked = [
        'boss@mailinator.com',
        'x@alias.mailinator.com',
        'x@sub.guerrillamail.com',
        'anon@10minutemail.net',
        'temp@yopmail.fr',
        'throw@throwaway.email',
        'alias@getnada.com',
        'tmp@tempmail.com',
    ];
    blocked.forEach((email) => {
        assert.strictEqual(InputGuard.isDisposableEmail(email), true, `blocked ${email}`);
    });
}

function test_disposable_email_case_insensitive() {
    assert.strictEqual(InputGuard.isDisposableEmail('Boss@Mailinator.COM'), true);
    assert.strictEqual(InputGuard.isDisposableEmail('x@YoPMail.com'), true);
}

function test_disposable_email_allows_corporate() {
    const allowed = [
        'safety@summitair.com',
        'smd@caanepal.gov.np',
        'ops@yetiairlines.com',
        'info@aviasafesystems.com',
        '',
        'no-at-sign',
    ];
    allowed.forEach((email) => {
        assert.strictEqual(InputGuard.isDisposableEmail(email), false, `allowed ${email}`);
    });
}

function test_email_domain_helper() {
    assert.strictEqual(InputGuard.emailDomain('Ops@YetiAirlines.com'), 'yetiairlines.com');
    assert.strictEqual(InputGuard.emailDomain('  safety@caanepal.gov.np  '), 'caanepal.gov.np');
}

// ---------------------------------------------------------------------------
// Honeypot trap
// ---------------------------------------------------------------------------

function test_honeypot_trap_filled() {
    const botForm = { elements: { company_website_url: { value: 'http://spam.example.com' } } };
    assert.strictEqual(InputGuard.honeypotTrap(botForm), true, 'filled honeypot must trap');
    assert.strictEqual(InputGuard.honeypotFilled(botForm), true);
}

function test_honeypot_trap_empty_or_missing() {
    assert.strictEqual(InputGuard.honeypotTrap({ elements: { company_website_url: { value: '   ' } } }), false);
    assert.strictEqual(InputGuard.honeypotTrap({ elements: { company_website_url: { value: '' } } }), false);
    assert.strictEqual(InputGuard.honeypotTrap({ elements: {} }), false);
    assert.strictEqual(InputGuard.honeypotTrap(null), false);
    assert.strictEqual(InputGuard.honeypotTrap(undefined), false);
}

function test_honeypot_custom_field_name() {
    const form = { elements: { website: { value: 'x' } } };
    assert.strictEqual(InputGuard.honeypotFilled(form, 'website'), true);
    assert.strictEqual(InputGuard.honeypotFilled(form, 'other'), false);
}

// ---------------------------------------------------------------------------
// Page wiring smoke check
// ---------------------------------------------------------------------------

function test_auth_pages_wired() {
    ['login.html', 'register.html', 'join.html'].forEach((file) => {
        const html = fs.readFileSync(path.join(__dirname, '..', 'public', file), 'utf8');
        assert.ok(html.includes('name="company_website_url"'), `${file} has honeypot field`);
        assert.ok(html.includes('/js/input_guard.js'), `${file} includes input_guard.js`);
        assert.ok(html.includes('honeypotTrap'), `${file} checks the honeypot on submit`);
    });

    ['register.html', 'join.html'].forEach((file) => {
        const html = fs.readFileSync(path.join(__dirname, '..', 'public', file), 'utf8');
        assert.ok(html.includes('isDisposableEmail(email)'), `${file} blocks disposable email`);
    });
}

// ---------------------------------------------------------------------------

function main() {
    test_disposable_email_blocks();
    test_disposable_email_case_insensitive();
    test_disposable_email_allows_corporate();
    test_email_domain_helper();
    test_honeypot_trap_filled();
    test_honeypot_trap_empty_or_missing();
    test_honeypot_custom_field_name();
    test_auth_pages_wired();
    console.log('input-guard: 8 tests passed');
}

main();