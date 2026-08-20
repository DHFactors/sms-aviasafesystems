/* ============================================================================
   FILE: help-drawer.js
   PATH: public/js/help-drawer.js
   PURPOSE: Zero-dependency slide-over contextual help drawer.
            - Triggered by [data-help-topic] elements or a persistent help button.
            - Loads /data/help/{topic}.json on demand (in-memory cache).
            - Renders Overview, Method & Scoring Rules, CAR-19 / Appendix 10
              Mapping and Worked Example sections from the JSON.
            - Closes on Escape, backdrop click, or the close button.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */
(function () {
    'use strict';

    if (window.HelpDrawer) {
        return;
    }

    var HELP_CACHE = {};
    var drawerEl = null;
    var backdropEl = null;
    var bodyEl = null;
    var titleEl = null;
    var subtitleEl = null;
    var closeBtnEl = null;
    var isOpen = false;
    var currentTopic = null;
    var lastTrigger = null;

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function defaultTopic() {
        var meta = document.querySelector('meta[name="help-drawer-topic"]');
        if (meta && meta.content) {
            return meta.content.trim();
        }
        var first = document.querySelector('[data-help-topic]');
        if (first) {
            return first.getAttribute('data-help-topic');
        }
        return null;
    }

    function buildDom() {
        if (drawerEl) {
            return;
        }
        backdropEl = document.createElement('div');
        backdropEl.className = 'help-drawer-backdrop';
        backdropEl.setAttribute('aria-hidden', 'true');

        drawerEl = document.createElement('aside');
        drawerEl.className = 'help-drawer';
        drawerEl.setAttribute('role', 'dialog');
        drawerEl.setAttribute('aria-modal', 'true');
        drawerEl.setAttribute('aria-label', 'Contextual help');
        drawerEl.innerHTML =
            '<div class="help-drawer-header">' +
            '  <div class="help-drawer-heading">' +
            '    <div class="help-drawer-title"></div>' +
            '    <div class="help-drawer-subtitle"></div>' +
            '  </div>' +
            '  <button type="button" class="help-drawer-close" aria-label="Close help">✕</button>' +
            '</div>' +
            '<div class="help-drawer-body"></div>';

        titleEl = drawerEl.querySelector('.help-drawer-title');
        subtitleEl = drawerEl.querySelector('.help-drawer-subtitle');
        bodyEl = drawerEl.querySelector('.help-drawer-body');
        closeBtnEl = drawerEl.querySelector('.help-drawer-close');

        closeBtnEl.addEventListener('click', close);
        backdropEl.addEventListener('click', close);

        document.body.appendChild(backdropEl);
        document.body.appendChild(drawerEl);
    }

    function renderParagraphs(container, items) {
        if (!items) {
            return;
        }
        if (!Array.isArray(items)) {
            items = [items];
        }
        items.forEach(function (text) {
            var el = document.createElement('p');
            el.className = 'help-drawer-p';
            el.innerHTML = escapeHtml(text);
            container.appendChild(el);
        });
    }

    function renderBullets(container, items) {
        if (!items || !items.length) {
            return;
        }
        var ul = document.createElement('ul');
        ul.className = 'help-drawer-ul';
        items.forEach(function (text) {
            var li = document.createElement('li');
            li.innerHTML = escapeHtml(text);
            ul.appendChild(li);
        });
        container.appendChild(ul);
    }

    function renderTable(container, table) {
        if (!table || !table.headers || !table.rows || !table.headers.length) {
            return;
        }
        var tbl = document.createElement('table');
        tbl.className = 'help-drawer-table';
        var thead = document.createElement('thead');
        var headRow = document.createElement('tr');
        table.headers.forEach(function (header) {
            var th = document.createElement('th');
            th.innerHTML = escapeHtml(header);
            headRow.appendChild(th);
        });
        thead.appendChild(headRow);
        tbl.appendChild(thead);
        var tbody = document.createElement('tbody');
        table.rows.forEach(function (row) {
            var tr = document.createElement('tr');
            row.forEach(function (cell) {
                var td = document.createElement('td');
                td.innerHTML = escapeHtml(cell);
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        tbl.appendChild(tbody);
        container.appendChild(tbl);
    }

    function renderSection(container, section, defaultTitle) {
        if (!section) {
            return;
        }
        var hasContent = Boolean(
            (section.paragraphs && section.paragraphs.length) ||
            (section.bullets && section.bullets.length) ||
            (section.table && section.table.headers && section.table.headers.length) ||
            (section.tiers && section.tiers.headers && section.tiers.headers.length)
        );
        if (!hasContent) {
            return;
        }
        var sec = document.createElement('section');
        sec.className = 'help-drawer-section';
        var heading = document.createElement('h2');
        heading.innerHTML = escapeHtml(section.title || defaultTitle);
        sec.appendChild(heading);
        renderParagraphs(sec, section.paragraphs);
        renderBullets(sec, section.bullets);
        renderTable(sec, section.table);
        renderTable(sec, section.tiers);
        container.appendChild(sec);
    }

    function render(data) {
        titleEl.textContent = data.title || 'Help';
        subtitleEl.textContent = data.subtitle || '';
        bodyEl.innerHTML = '';

        var overview = document.createElement('section');
        overview.className = 'help-drawer-section';
        var oh = document.createElement('h2');
        oh.innerHTML = 'Overview';
        overview.appendChild(oh);
        renderParagraphs(overview, data.overview);
        bodyEl.appendChild(overview);

        renderSection(bodyEl, data.method, 'Method & Scoring Rules');
        renderSection(bodyEl, data.mapping, 'CAR-19 / Appendix 10 Mapping');
        renderSection(bodyEl, data.example, 'Worked Example');

        bodyEl.scrollTop = 0;
    }

    function show() {
        buildDom();
        document.body.classList.add('help-drawer-open');
        backdropEl.classList.add('open');
        drawerEl.classList.add('open');
        isOpen = true;
        lastTrigger = document.activeElement;
        if (closeBtnEl) {
            closeBtnEl.focus();
        }
    }

    function close() {
        if (!isOpen) {
            return;
        }
        document.body.classList.remove('help-drawer-open');
        backdropEl.classList.remove('open');
        drawerEl.classList.remove('open');
        isOpen = false;
        currentTopic = null;
        if (lastTrigger && typeof lastTrigger.focus === 'function') {
            lastTrigger.focus();
        }
    }

    function open(topic) {
        if (!topic) {
            topic = defaultTopic();
        }
        if (!topic) {
            return;
        }
        show();
        currentTopic = topic;
        titleEl.textContent = 'Help';
        subtitleEl.textContent = '';
        bodyEl.innerHTML = '<p class="help-drawer-p">Loading help…</p>';

        if (HELP_CACHE[topic]) {
            render(HELP_CACHE[topic]);
            return;
        }

        fetch('/data/help/' + encodeURIComponent(topic) + '.json', {
            headers: { 'Accept': 'application/json' }
        })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('HTTP ' + response.status);
                }
                return response.json();
            })
            .then(function (data) {
                HELP_CACHE[topic] = data;
                if (currentTopic === topic) {
                    render(data);
                }
            })
            .catch(function () {
                if (currentTopic !== topic) {
                    return;
                }
                bodyEl.innerHTML =
                    '<p class="help-drawer-error">Could not load help for "' +
                    escapeHtml(topic) + '". Please try again.</p>';
            });
    }

    function ensureToggleButton() {
        var topic = defaultTopic();
        if (!topic) {
            return;
        }
        var existing = document.querySelector('.help-drawer-toggle');
        if (existing) {
            return;
        }
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'help-drawer-toggle';
        button.setAttribute('aria-haspopup', 'dialog');
        button.innerHTML =
            '<span class="help-drawer-toggle-icon">?</span>' +
            '<span class="help-drawer-toggle-label">Help</span>';
        button.addEventListener('click', function () {
            open();
        });
        document.body.appendChild(button);
    }

    document.addEventListener('click', function (event) {
        var trigger = event.target.closest ? event.target.closest('[data-help-topic]') : null;
        if (trigger) {
            event.preventDefault();
            open(trigger.getAttribute('data-help-topic'));
        }
    });

    document.addEventListener('keydown', function (event) {
        if (isOpen && event.key === 'Escape') {
            close();
        }
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', ensureToggleButton);
    } else {
        ensureToggleButton();
    }

    window.HelpDrawer = {
        open: open,
        close: close,
        isOpen: function () {
            return isOpen;
        }
    };
})();
