/* ============================================================================
   FILE: empty-state.js
   PATH: public/dashboard/shared/empty-state.js
   PHASE: P4-1 (Wave 1 — shared empty state treatment)
   PURPOSE: Consistent empty / loading / error / permission treatments for
            all four dashboards (DASHBOARD_CONTRACT.md §6).
   API:
     window.EmptyState = {
       noData(title, subtitle, ctaLabel, ctaUrl),
       noModule(moduleName, helpText),
       noPermission(requiredRole),
       loading(message),
       error(message, retryFn),
     }
   Each renderer returns an HTML string AND, when given a container element
   as the last argument, paints it (e.g. noData(t, s, l, u, container)).
   Copy conventions:
     §6  — null/array-empty responses render a neutral message (EIP `None`,
           `avg_closure_days` null).
     §9  — module-off copy: Title "This module is not enabled",
           Subtitle "Contact your tenant administrator to enable X.",
   NOTE: No build step. UMD-wrapped for Node unit tests. retryFn is wired
     via a delegated click handler when a container is painted in the
     browser; in Node (no DOM) the HTML includes a retry button only.
   ============================================================================ */
(function (root, factory) {
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = factory();
    } else {
        root.EmptyState = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    function escHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function lastArgIsContainer(args) {
        var last = args[args.length - 1];
        return last && typeof last === 'object' && ('innerHTML' in last) ? last : null;
    }

    function paint(container, html, retryFn) {
        if (!container) return html;
        container.innerHTML = html;
        if (typeof retryFn === 'function' && container.querySelector) {
            var btn = container.querySelector('[data-es-retry]');
            if (btn) {
                if (btn.addEventListener) btn.addEventListener('click', retryFn);
                else btn.onclick = retryFn;
            }
        }
        return html;
    }

    function shell(title, subtitle, illus, ctaHtml) {
        return '<div class="dash-empty" role="status">' +
            '<div class="dash-empty-illus" aria-hidden="true">' + illus + '</div>' +
            '<p class="dash-empty-title">' + escHtml(title) + '</p>' +
            (subtitle ? '<p class="dash-empty-sub">' + escHtml(subtitle) + '</p>' : '') +
            (ctaHtml || '') +
            '</div>';
    }

    function ctaHtml(label, url) {
        if (!label) return '';
        return '<a class="dash-btn dash-btn-primary" href="' + escHtml(url || '#') + '">' +
            escHtml(label) + '</a>';
    }

    // Neutral no-data state (§6). EIP-when-zero renders the literal `None`
    // via the caller passing title 'None' — supported explicitly.
    function noData(title, subtitle, ctaLabel, ctaUrl, container) {
        container = lastArgIsContainer(arguments) || null;
        var html = shell(
            title || 'No data',
            subtitle || 'Nothing to show for this period.',
            '📭',
            ctaHtml(ctaLabel, ctaUrl)
        );
        return paint(container, html);
    }

    // Module-flag-off state (§9). Exact contract copy.
    function noModule(moduleName, helpText, container) {
        container = lastArgIsContainer(arguments) || null;
        var name = moduleName || 'This module';
        var help = helpText ||
            ('Contact your tenant administrator to enable ' + name + '.');
        var html = shell(
            'This module is not enabled',
            help,
            '🧩',
            ctaHtml('Back to Dashboard', '/safety.html')
        );
        return paint(container, html);
    }

    function noPermission(requiredRole, container) {
        container = lastArgIsContainer(arguments) || null;
        var html = shell(
            'Access restricted',
            'This view requires the ' + (requiredRole || 'authorized') +
            ' role. Contact your tenant administrator if you need access.',
            '🔒',
            ctaHtml('Back to Dashboard', '/safety.html')
        );
        return paint(container, html);
    }

    function loading(message, container) {
        container = lastArgIsContainer(arguments) || null;
        var html = '<div class="dash-overlay-text" role="status" aria-live="polite">' +
            '<div class="dash-spinner" aria-hidden="true"></div>' +
            escHtml(message || 'Loading…') + '</div>';
        return paint(container, html);
    }

    function error(message, retryFn, container) {
        container = lastArgIsContainer(arguments) || null;
        var html = '<div class="dash-error-box" role="alert">' +
            '<strong>Something went wrong.</strong> ' +
            escHtml(message || 'Please try again.') +
            (typeof retryFn === 'function'
                ? ' <button type="button" class="dash-btn dash-btn-small" data-es-retry>Retry</button>'
                : '') +
            '</div>';
        return paint(container, html, typeof retryFn === 'function' ? retryFn : null);
    }

    return {
        noData: noData,
        noModule: noModule,
        noPermission: noPermission,
        loading: loading,
        error: error,
    };
}));
