// Capture browser console messages + failed API responses from beta frontend pages.
// Uses headless Chrome DevTools Protocol. No puppeteer dependency.
// Usage:
//   node scripts/firebase/browser-console-check.js <url...>
'use strict';

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const PORT = 9223;

const urls = process.argv.slice(2).length
    ? process.argv.slice(2)
    : [
        'https://sms.aviasafesystems.com/',
        'https://sms.aviasafesystems.com/login.html',
    ];

function wait(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function connectCDP(port) {
    let tries = 0;
    while (tries < 40) {
        try {
            const r = await fetch(`http://127.0.0.1:${port}/json/list`);
            const list = await r.json();
            const page = list.find((t) => t.type === 'page');
            if (page) return page.webSocketDebuggerUrl;
        } catch {
            // ignore, retry
        }
        await wait(500);
        tries++;
    }
    throw new Error('CDP not reachable');
}

async function main() {
    const userData = path.join(process.env.TEMP || '/tmp', 'opencode-chrome-' + Date.now());
    const proc = spawn(CHROME, [
        '--headless=new',
        '--disable-gpu',
        '--no-sandbox',
        '--disable-extensions',
        '--remote-debugging-port=' + PORT,
        '--user-data-dir=' + userData,
        'about:blank',
    ], { stdio: 'ignore' });

    const wsUrl = await connectCDP(PORT);
    const ws = new WebSocket(wsUrl);

    let msgId = 0;
    const pending = new Map();
    const consoleErrors = [];
    const failedResponses = [];
    const events = {};

    function send(method, params) {
        return new Promise((resolve, reject) => {
            const id = ++msgId;
            pending.set(id, { resolve, reject });
            ws.send(JSON.stringify({ id, method, params }));
        });
    }

    ws.addEventListener('message', (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.id && pending.has(msg.id)) {
            const p = pending.get(msg.id);
            pending.delete(msg.id);
            if (msg.error) p.reject(new Error(msg.error.message));
            else p.resolve(msg.result);
            return;
        }
        if (msg.method === 'Runtime.consoleAPICalled') {
            const type = msg.params.type;
            const text = (msg.params.args || []).map((a) => a.value ?? a.description ?? '').join(' ');
            if (type === 'error' || type === 'warning') {
                consoleErrors.push({ type, text: text.slice(0, 300), url: events.currentUrl });
            }
        }
        if (msg.method === 'Runtime.exceptionThrown') {
            const d = msg.params.exceptionDetails;
            const text = d.exception ? (d.exception.description || d.exception.value) : d.text;
            consoleErrors.push({ type: 'exception', text: String(text).slice(0, 400), url: events.currentUrl });
        }
        if (msg.method === 'Network.responseReceived') {
            const r = msg.params.response;
            if (r.status >= 400) {
                failedResponses.push({ status: r.status, url: r.url.slice(0, 160) });
            }
        }
        if (msg.method === 'Page.frameNavigated' && !msg.params.frame.parentId) {
            events.currentUrl = msg.params.frame.url;
        }
    });

    await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej); });

    await send('Runtime.enable');
    await send('Network.enable');
    await send('Page.enable');

    for (const url of urls) {
        consoleErrors.length = 0;
        failedResponses.length = 0;
        console.log(`\n=== ${url} ===`);
        try {
            await send('Page.navigate', { url });
            await wait(9000);
        } catch (e) {
            console.log('navigate error:', e.message);
        }

        const errs = consoleErrors.filter((e) => e.type === 'error' || e.type === 'exception');
        console.log(`Console errors: ${errs.length}`);
        errs.slice(0, 10).forEach((e) => console.log(`  [${e.type}] ${e.text}`));
        console.log(`Console warnings: ${consoleErrors.filter((e) => e.type === 'warning').length}`);
        consoleErrors.filter((e) => e.type === 'warning').slice(0, 5).forEach((e) => console.log(`  [warn] ${e.text}`));
        console.log(`Failed HTTP responses (>=400): ${failedResponses.length}`);
        failedResponses.slice(0, 12).forEach((f) => console.log(`  ${f.status} ${f.url}`));
    }

    try { await send('Browser.close'); } catch {}
    proc.kill();
    try { fs.rmSync(userData, { recursive: true, force: true, maxRetries: 3, retryDelay: 200 }); } catch {}
}

main().catch((e) => { console.error('FATAL', e); process.exit(1); });
