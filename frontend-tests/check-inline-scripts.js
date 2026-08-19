'use strict';
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync } = require('child_process');
const root = process.argv[2] || '.';
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'inline-check-'));
const htmlFiles = [];
(function walk(dir) {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        if (e.name === 'node_modules' || e.name === '.git') continue;
        const p = path.join(dir, e.name);
        if (e.isDirectory()) walk(p);
        else if (e.name.endsWith('.html')) htmlFiles.push(p);
    }
})(root);
let bad = 0;
let total = 0;
for (const file of htmlFiles.sort()) {
    const html = fs.readFileSync(file, 'utf8');
    const re = /<script([^>]*)>([\s\S]*?)<\/script>/gi;
    let m;
    let idx = 0;
    while ((m = re.exec(html)) !== null) {
        const attrs = m[1] || '';
        const code = m[2] || '';
        if (/src\s*=/.test(attrs)) continue;
        if (!code.trim()) continue;
        const isModule = /type\s*=\s*["']module["']/i.test(attrs);
        const ext = isModule ? 'mjs' : 'js';
        const f = path.join(tmp, `${path.basename(file)}-${idx}.${ext}`);
        fs.writeFileSync(f, code);
        total++;
        try {
            execFileSync(process.execPath, ['--check', f], { stdio: 'pipe' });
        } catch (e) {
            bad++;
            console.log('SYNTAX ERROR in ' + file + ' script #' + idx + (isModule ? ' (module)' : ''));
            console.log(String(e.stderr || '').trim().split('\n').slice(0, 6).join('\n'));
        }
        idx++;
    }
}
console.log('Checked inline scripts: ' + total + ', failures: ' + bad);
process.exit(bad ? 1 : 0);
