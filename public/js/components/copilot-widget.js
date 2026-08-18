/* ============================================================================
   FILE: copilot-widget.js
   PATH: public/js/components/copilot-widget.js
   PURPOSE: "Ghanshyam — Executive Safety Copilot" floating chat widget.
            Dark-themed bottom-right toggle + chat modal backed by
            POST /api/v1/copilot/chat (Groq). Self-contained: builds its own
            DOM, so pages only need to load this script (plus /css/copilot-widget.css).
   AUTHOR: AviaSAFE Systems
   =========================================================================== */

(function () {
    'use strict';

    if (window.__CopilotWidgetInit) return;
    window.__CopilotWidgetInit = true;

    var WIDGET_TITLE = 'Ghanshyam — Executive Safety Copilot';
    var WIDGET_SUBTITLE = '50 Years Aviation Leadership | ICAO Annex 19 (3rd Ed.) SMS Guide';

    // Public pages where the copilot runs WITHOUT authentication (guest mode).
    var GUEST_PAGES = ['register.html'];

    function currentPageName() {
        var path = window.location.pathname.split('/').pop();
        return path || '';
    }

    function isGuestPage() {
        return GUEST_PAGES.indexOf(currentPageName()) !== -1;
    }

    // Greeting strictly based on the visitor's local time of day.
    function timeGreeting() {
        var hour = new Date().getHours();
        if (hour < 12) return 'Good morning';
        if (hour < 17) return 'Good afternoon';
        return 'Good evening';
    }

    function welcomeMessage() {
        var intro = isGuestPage()
            ? 'I can help you register your organization: choosing the correct operator ' +
              'classification (Fixed-Wing Airline, Helicopter/Rotary, Part-145 AMO, or Certified ' +
              'Aerodrome), setting up your primary administrator account, and preparing your team ' +
              'invite code.'
            : 'Ask me anything on SMS compliance, hazard reporting (VSR/MOR), 5×5 SRA risk evaluation, ' +
              '5M+1E Fishbone RCA, Human Factors error traps, CAN issuance, or closed-loop CAP resolution.';
        return timeGreeting() + ' and welcome aboard. I am **Ghanshyam** — Executive Safety Copilot.\n\n' + intro;
    }

    function quickSuggestions() {
        if (isGuestPage()) {
            return [
                'How do I register my organization?',
                'Which operator classification should I choose?',
                'What happens after I register?',
                'How do my team members join?'
            ];
        }
        return [
            'Align SMS with ICAO Annex 19 (3rd Edition)',
            'Guide me through a 5M+1E Fishbone RCA',
            'How to evaluate risk in the 5x5 SRA Matrix',
            'Identify Human Factors error traps in this occurrence'
        ];
    }

    var API_BASE =
        (window.APP_CONFIG && window.APP_CONFIG.apiBaseUrl) ||
        window.API_BASE_URL ||
        'https://sms-aviasafesystems-beta.onrender.com';

    var history = [];
    var sending = false;

    function getToken() {
        if (!window.firebase || !firebase.auth || !firebase.auth().currentUser) {
            return Promise.resolve(null);
        }
        return firebase.auth().currentUser.getIdToken().catch(function () { return null; });
    }

    // Page/route detection: send the opened page filename first so the backend
    // can enforce strict per-page scoping in the model's system prompt.
    function pageContext() {
        var parts = [];
        var page = currentPageName();
        if (page && page !== '/') parts.push(page);
        var meta = document.querySelector('meta[name="page-context"]');
        if (meta && meta.content) parts.push(meta.content);
        if (document.title) parts.push(document.title);
        return parts.filter(Boolean).join(' — ').slice(0, 200);
    }

    /* ── Minimal safe markdown renderer (no external deps) ── */
    function escapeHtml(text) {
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function renderMarkdown(text) {
        var lines = escapeHtml(text || '').split(/\r?\n/);
        var html = '';
        var inList = null;
        var para = [];

        function flushPara() {
            if (para.length) {
                html += '<p>' + para.join('<br>') + '</p>';
                para = [];
            }
        }
        function closeList() {
            if (inList) { html += inList === 'ul' ? '</ul>' : '</ol>'; inList = null; }
        }

        lines.forEach(function (raw) {
            var line = raw.trimEnd();
            if (!line.trim()) { flushPara(); closeList(); return; }

            if (/^#{1,3}\s/.test(line)) {
                flushPara(); closeList();
                var level = line.match(/^#{1,3}/)[0].length;
                html += '<h' + level + '>' + inlineFormat(line.replace(/^#{1,3}\s+/, '')) + '</h' + level + '>';
                return;
            }
            if (/^[-*]\s+/.test(line)) {
                flushPara();
                if (inList !== 'ul') { closeList(); html += '<ul>'; inList = 'ul'; }
                html += '<li>' + inlineFormat(line.replace(/^[-*]\s+/, '')) + '</li>';
                return;
            }
            if (/^\d+[.)]\s+/.test(line)) {
                flushPara();
                if (inList !== 'ol') { closeList(); html += '<ol>'; inList = 'ol'; }
                html += '<li>' + inlineFormat(line.replace(/^\d+[.)]\s+/, '')) + '</li>';
                return;
            }
            para.push(line);
        });
        flushPara(); closeList();

        // Inline bold on the assembled (already HTML-escaped) output so user
        // input like "**Ghanshyam**" formats as clean bold rather than raw tags.
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        return html;
    }

    // Escaped-text inline formatter — `**bold**` -> <strong>bold</strong>.
    function inlineFormat(text) {
        return text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    }

    /* ── DOM helpers ── */
    function el(tag, cls, html) {
        var node = document.createElement(tag);
        if (cls) node.className = cls;
        if (html !== undefined) node.innerHTML = html;
        return node;
    }

    function buildWidget() {
        var root = el('div', 'copilot-widget-root');

        var toggle = el('button', 'cpi-toggle');
        toggle.setAttribute('type', 'button');
        toggle.setAttribute('aria-label', 'Open Safety Copilot');
        toggle.innerHTML = '<span class="cpi-icon">💬</span><span class="cpi-label">How Can I Help You?</span><span class="cpi-badge">Copilot</span>';
        root.appendChild(toggle);

        var modal = el('div', 'cpi-modal');
        modal.style.display = 'none';

        var header = el('div', 'cpi-header');
        header.appendChild(el('div', 'cpi-avatar', 'G'));
        var headText = el('div');
        headText.appendChild(el('div', 'cpi-title', WIDGET_TITLE));
        headText.appendChild(el('div', 'cpi-subtitle', WIDGET_SUBTITLE));
        header.appendChild(headText);
        var closeBtn = el('button', 'cpi-close', '✕');
        closeBtn.setAttribute('type', 'button');
        closeBtn.setAttribute('aria-label', 'Close copilot');
        header.appendChild(closeBtn);
        modal.appendChild(header);

        var body = el('div', 'cpi-body');
        var welcome = el('div', 'cpi-welcome');
        welcome.appendChild(el('div', 'cpi-wl-title', WIDGET_TITLE));
        welcome.appendChild(el('div', null, renderMarkdown(welcomeMessage())));
        body.appendChild(welcome);

        var chips = el('div', 'cpi-chips');
        quickSuggestions().forEach(function (q) {
            var chip = el('button', 'cpi-chip', q);
            chip.setAttribute('type', 'button');
            chip.addEventListener('click', function () { sendMessage(q); });
            chips.appendChild(chip);
        });
        body.appendChild(chips);
        modal.appendChild(body);

        var footer = el('div', 'cpi-footer');
        var input = el('textarea');
        input.setAttribute('rows', '1');
        input.setAttribute('placeholder', 'Ask about SMS, RCA, SRA, CAN/CAP…');
        input.setAttribute('maxlength', '2000');
        var sendBtn = el('button', 'cpi-send', 'Send');
        sendBtn.setAttribute('type', 'button');
        footer.appendChild(input);
        footer.appendChild(sendBtn);
        modal.appendChild(footer);

        root.appendChild(modal);
        document.body.appendChild(root);

        /* ── Wiring ── */
        function toggleOpen(open) {
            modal.style.display = open ? 'flex' : 'none';
            toggle.style.display = open ? 'none' : 'flex';
            if (open) input.focus();
        }

        toggle.addEventListener('click', function () { toggleOpen(true); });
        closeBtn.addEventListener('click', function () { toggleOpen(false); });

        function autoGrow() {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 110) + 'px';
        }
        input.addEventListener('input', autoGrow);
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendFromInput();
            }
        });
        sendBtn.addEventListener('click', sendFromInput);

        function sendFromInput() {
            var msg = input.value.trim();
            if (!msg || sending) return;
            input.value = '';
            input.style.height = 'auto';
            sendMessage(msg);
        }

        function appendMsg(text, kind) {
            body.appendChild(el('div', 'cpi-msg ' + kind, kind === 'bot' ? renderMarkdown(text) : escapeHtml(text)));
            body.scrollTop = body.scrollHeight;
        }

        function appendError(msg) {
            body.appendChild(el('div', 'cpi-error', msg));
            body.scrollTop = body.scrollHeight;
        }

        function showTyping() {
            var t = el('div', 'cpi-typing');
            t.innerHTML = '<span></span><span></span><span></span>';
            t.setAttribute('data-cpi-typing', '1');
            body.appendChild(t);
            body.scrollTop = body.scrollHeight;
            return t;
        }

        function hideTyping(node) {
            if (node && node.parentNode) node.parentNode.removeChild(node);
        }

        function sendMessage(msg) {
            if (sending) return;
            sending = true;
            sendBtn.disabled = true;
            appendMsg(msg, 'user');
            history.push({ role: 'user', content: msg });

            var typing = showTyping();

            function handleReply(data) {
                hideTyping(typing);
                sending = false;
                sendBtn.disabled = false;
                var reply = data && (data.reply || data.data && data.data.reply);
                if (reply) {
                    history.push({ role: 'assistant', content: reply });
                    appendMsg(reply, 'bot');
                } else {
                    appendError('The Copilot did not respond. Please try again.');
                }
            }

            function handleError(err) {
                hideTyping(typing);
                sending = false;
                sendBtn.disabled = false;
                appendError('Could not reach the Copilot: ' + (err && err.message ? err.message : 'network error'));
            }

            var bodyPayload = JSON.stringify({
                message: msg,
                page_context: pageContext(),
                history: history.slice(-8)
            });

            if (isGuestPage()) {
                // Public onboarding pages: guest endpoint, no authentication.
                fetch(API_BASE + '/api/v1/copilot/guest/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: bodyPayload
                })
                    .then(function (res) { return res.json().catch(function () { return null; }); })
                    .then(handleReply)
                    .catch(handleError);
                return;
            }

            getToken().then(function (token) {
                if (!token) {
                    hideTyping(typing);
                    sending = false;
                    sendBtn.disabled = false;
                    appendError('Please sign in to use the Safety Copilot.');
                    return;
                }
                return fetch(API_BASE + '/api/v1/copilot/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + token
                    },
                    body: bodyPayload
                })
                    .then(function (res) { return res.json().catch(function () { return null; }); })
                    .then(handleReply);
            }).catch(handleError);
        }

        /* Show the toggle on guest pages regardless of auth; on authenticated
           pages only when a user is signed in. */
        if (window.firebase && firebase.auth) {
            firebase.auth().onAuthStateChanged(function (u) {
                toggle.style.display = isGuestPage() ? 'flex' : (u ? 'flex' : 'none');
            });
        } else if (isGuestPage()) {
            toggle.style.display = 'flex';
        }
    }

    /* Run once the document body exists (safe whether loaded in <head> or at EOF). */
    function init() {
        if (document.body) { buildWidget(); return; }
        document.addEventListener('DOMContentLoaded', buildWidget);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();