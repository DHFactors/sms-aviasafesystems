/* ============================================================================
   FILE: feedback.js
   PATH: public/js/feedback.js
   VERSION: 2.0.0
   PURPOSE: Lightweight in-product feedback widget. Adds a floating
            "Send Feedback" button + modal that routes feedback to the
            Cloudflare Worker at aviasafe-contact-form.ghanshyamacharya.workers.dev
            which emails support@aviasafesystems.com. Collects an optional
            1-5 rating, user email, tenant name, and page context.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

(function (global) {
    'use strict';

    // ============================================================
    // Cloudflare Worker endpoint
    // ============================================================
    var FEEDBACK_API = 'https://aviasafe-contact-form.ghanshyamacharya.workers.dev/api/send-feedback';

    var STYLE_ID = 'feedbackWidgetStyle';
    var HOST_ID = 'feedbackWidgetHost';

    // ============================================================
    // Helpers: get user email + derive tenant name
    // ============================================================
    function getUserEmail() {
        if (typeof global.getUserEmail === 'function') return global.getUserEmail();
        var email = localStorage.getItem('userEmail') ||
                    sessionStorage.getItem('userEmail') ||
                    (document.querySelector('#shellUser') || {}).textContent ||
                    (document.querySelector('.user-email') || {}).textContent ||
                    '';
        email = (email || '').trim();
        return email || 'Anonymous';
    }

    function getTenantName() {
        if (typeof global.airlineNameFromEmail === 'function') {
            return global.airlineNameFromEmail(getUserEmail());
        }
        var email = getUserEmail();
        if (email && email.indexOf('@') !== -1 && email !== 'Anonymous') {
            var domain = email.split('@')[1];
            if (domain) {
                var name = domain.split('.')[0];
                return name.charAt(0).toUpperCase() + name.slice(1);
            }
        }
        return 'Unknown';
    }

    // ============================================================
    // Main submit function
    // ============================================================
    async function submitFeedback(data) {
        var payload = {
            email: getUserEmail(),
            tenant: getTenantName(),
            rating: data.rating || 0,
            subject: data.subject || 'No subject',
            message: data.message || '',
            page: global.location.href,
            date: new Date().toISOString(),
            userAgent: navigator.userAgent
        };

        var response = await fetch(FEEDBACK_API, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        var result = await response.json();

        if (response.ok && result.success) {
            return { success: true, message: result.message || 'Feedback sent!' };
        } else {
            throw new Error(result.error || 'Failed to send feedback');
        }
    }

    global.submitFeedback = submitFeedback;

    // ============================================================
    // Widget CSS
    // ============================================================
    var CSS = '\
        #feedbackWidgetHost .feedback-fab {\
            position: fixed;\
            right: 1.25rem;\
            bottom: 1.25rem;\
            z-index: 9990;\
            display: inline-flex;\
            align-items: center;\
            gap: 0.5rem;\
            padding: 0.65rem 1.1rem;\
            border: none;\
            border-radius: 999px;\
            background: #1a6b8a;\
            color: #fff;\
            font-size: 0.85rem;\
            font-weight: 600;\
            cursor: pointer;\
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.18);\
            transition: background 0.15s ease;\
        }\
        #feedbackWidgetHost .feedback-fab:hover { background: #0b2a42; }\
        #feedbackWidgetHost .feedback-modal {\
            position: fixed;\
            inset: 0;\
            z-index: 9991;\
            display: none;\
            align-items: center;\
            justify-content: center;\
            background: rgba(15, 23, 42, 0.55);\
        }\
        #feedbackWidgetHost .feedback-modal.open { display: flex; }\
        #feedbackWidgetHost .feedback-card {\
            width: min(440px, calc(100vw - 2rem));\
            background: #fff;\
            border-radius: 12px;\
            padding: 1.5rem;\
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.3);\
        }\
        #feedbackWidgetHost .feedback-card h3 {\
            margin: 0 0 0.25rem;\
            font-size: 1.1rem;\
            color: #0f172a;\
        }\
        #feedbackWidgetHost .feedback-card .feedback-sub {\
            margin: 0 0 1rem;\
            font-size: 0.8rem;\
            color: #64748b;\
        }\
        #feedbackWidgetHost .feedback-card label {\
            display: block;\
            font-size: 0.8rem;\
            font-weight: 600;\
            color: #334155;\
            margin: 0.75rem 0 0.25rem;\
        }\
        #feedbackWidgetHost .feedback-card input,\
        #feedbackWidgetHost .feedback-card textarea,\
        #feedbackWidgetHost .feedback-card select {\
            width: 100%;\
            padding: 0.5rem 0.7rem;\
            border: 1px solid #cbd5e1;\
            border-radius: 6px;\
            font-size: 0.9rem;\
            box-sizing: border-box;\
        }\
        #feedbackWidgetHost .feedback-card .feedback-actions {\
            display: flex;\
            justify-content: flex-end;\
            gap: 0.5rem;\
            margin-top: 1.25rem;\
        }\
        #feedbackWidgetHost .feedback-btn {\
            border: none;\
            border-radius: 6px;\
            padding: 0.5rem 1rem;\
            font-size: 0.85rem;\
            font-weight: 600;\
            cursor: pointer;\
        }\
        #feedbackWidgetHost .feedback-btn-primary { background: #1a6b8a; color: #fff; }\
        #feedbackWidgetHost .feedback-btn-primary:hover { background: #0b2a42; }\
        #feedbackWidgetHost .feedback-btn-cancel { background: #f1f5f9; color: #334155; }\
        #feedbackWidgetHost .feedback-msg {\
            margin-top: 0.75rem;\
            font-size: 0.85rem;\
            color: #15803d;\
        }\
        #feedbackWidgetHost .feedback-msg.error { color: #b91c1c; }\
        #feedbackWidgetHost .feedback-stars { font-size: 1.4rem; cursor: pointer; }\
        #feedbackWidgetHost .feedback-stars span { color: #cbd5e1; transition: color 0.1s; }\
        #feedbackWidgetHost .feedback-stars span.active { color: #f59e0b; }';

    function injectStyle() {
        if (document.getElementById(STYLE_ID)) return;
        var style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = CSS;
        document.head.appendChild(style);
    }

    function openModal() {
        var modal = document.getElementById('feedbackModal');
        if (modal) modal.classList.add('open');
    }

    function closeModal() {
        var modal = document.getElementById('feedbackModal');
        if (modal) modal.classList.remove('open');
        var msg = document.getElementById('feedbackMsg');
        if (msg) {
            msg.textContent = '';
            msg.className = 'feedback-msg';
        }
    }

    function bindStars(containerId) {
        var container = document.getElementById(containerId);
        if (!container) return function () { return 0; };
        var value = 0;
        container.querySelectorAll('span').forEach(function (star, idx) {
            star.addEventListener('click', function () {
                value = idx + 1;
                container.querySelectorAll('span').forEach(function (s, i) {
                    s.classList.toggle('active', i <= idx);
                });
            });
        });
        return function () { return value; };
    }

    async function submit() {
        var subject = document.getElementById('feedbackSubject').value.trim();
        var message = document.getElementById('feedbackMessage').value.trim();
        var rating = global.__feedbackRating ? global.__feedbackRating() : 0;
        var msgEl = document.getElementById('feedbackMsg');

        if (!subject || !message) {
            msgEl.textContent = 'Please provide a subject and message.';
            msgEl.className = 'feedback-msg error';
            return;
        }

        msgEl.textContent = 'Sending...';
        msgEl.className = 'feedback-msg';

        try {
            var result = await submitFeedback({
                rating: rating,
                subject: subject,
                message: message
            });

            if (result.success) {
                msgEl.textContent = result.message || 'Thank you — your feedback has been recorded.';
                msgEl.className = 'feedback-msg';
                document.getElementById('feedbackSubject').value = '';
                document.getElementById('feedbackMessage').value = '';
                global.__feedbackRating = bindStars('feedbackStars');
                setTimeout(closeModal, 1600);
            } else {
                throw new Error(result.error || 'Unexpected response');
            }
        } catch (err) {
            msgEl.textContent = 'Could not send feedback: ' + (err.message || 'unknown error') +
                '. Please email support@aviasafesystems.com';
            msgEl.className = 'feedback-msg error';
        }
    }

    function buildWidget() {
        if (document.getElementById(HOST_ID)) return;

        var host = document.createElement('div');
        host.id = HOST_ID;

        var fab = document.createElement('button');
        fab.className = 'feedback-fab';
        fab.innerHTML = '<i class="fas fa-comment-dots"></i> Send Feedback';
        fab.addEventListener('click', openModal);
        host.appendChild(fab);

        var modal = document.createElement('div');
        modal.className = 'feedback-modal';
        modal.id = 'feedbackModal';

        var card = document.createElement('div');
        card.className = 'feedback-card';
        card.innerHTML =
            '<h3><i class="fas fa-comment-dots"></i> Feedback on Safety Intelligence</h3>' +
            '<p class="feedback-sub">Help us improve the platform. Reviewed quarterly.</p>' +
            '<label>Rating (optional)</label>' +
            '<div class="feedback-stars" id="feedbackStars">' +
                '<span>&#9733;</span><span>&#9733;</span><span>&#9733;</span><span>&#9733;</span><span>&#9733;</span>' +
            '</div>' +
            '<label for="feedbackSubject">Subject</label>' +
            '<input id="feedbackSubject" type="text" maxlength="200" placeholder="e.g. SSM Risk Trends" />' +
            '<label for="feedbackMessage">Message</label>' +
            '<textarea id="feedbackMessage" rows="4" maxlength="3000" placeholder="What worked well? What should change?"></textarea>' +
            '<div id="feedbackMsg" class="feedback-msg"></div>' +
            '<div class="feedback-actions">' +
                '<button class="feedback-btn feedback-btn-cancel" onclick="document.getElementById(\'feedbackModal\').classList.remove(\'open\')">Cancel</button>' +
                '<button class="feedback-btn feedback-btn-primary" onclick="window.__feedbackSubmit()">Send</button>' +
            '</div>';
        modal.appendChild(card);
        modal.addEventListener('click', function (e) {
            if (e.target === modal) closeModal();
        });
        host.appendChild(modal);
        document.body.appendChild(host);

        global.__feedbackRating = bindStars('feedbackStars');
        global.__feedbackSubmit = submit;
    }

    function init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function () {
                injectStyle();
                buildWidget();
            });
        } else {
            injectStyle();
            buildWidget();
        }
    }

    global.initFeedbackWidget = init;
})(window);