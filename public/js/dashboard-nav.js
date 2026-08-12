/**
 * dashboard-nav.js — universal dashboard view switcher.
 *
 * Pages declare their content sections with the `data-dashboard-view`
 * attribute. `switchDashboardView(activeSectionId)` shows the requested
 * section and hides every other view, then reflects the selection in the
 * shell sidebar's active class (scroll-spy is bypassed while a view is
 * active).
 *
 * Auto-init: on DOMContentLoaded the first `[data-dashboard-view]` section
 * is shown (single-view pages always match their only section). Pages may
 * force a specific default with:
 *   window.DEFAULT_DASHBOARD_VIEW = 'section-id';
 * A URL fragment (#section-id) overrides the default, enabling deep links.
 */
(function () {
    'use strict';

    function switchDashboardView(activeSectionId) {
        const active = document.getElementById(activeSectionId);
        if (!active) return null;

        document.querySelectorAll('[data-dashboard-view]').forEach(function (section) {
            const show = section === active;
            section.style.display = show ? 'block' : 'none';
            section.classList.toggle('active-view', show);
        });

        // Sidebar active-class sync: in-page view links (data-target) and
        // explicit view links (data-view-link) both follow the active section.
        document.querySelectorAll('.sidebar-nav li a').forEach(function (link) {
            const target = link.getAttribute('data-target') || link.getAttribute('data-view-link');
            if (!target) return;
            link.classList.toggle('active', target === activeSectionId);
        });

        // Let Chart.js v4 (ResizeObserver) re-layout charts that just became visible.
        window.dispatchEvent(new Event('resize'));
        return active;
    }

    function init() {
        const sections = document.querySelectorAll('[data-dashboard-view]');
        if (!sections.length) return;

        let defaultView = window.DEFAULT_DASHBOARD_VIEW || sections[0].id;
        if (window.location.hash) {
            const hashView = window.location.hash.slice(1);
            if (document.getElementById(hashView)) defaultView = hashView;
        }
        switchDashboardView(defaultView);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.switchDashboardView = switchDashboardView;
    window.DashboardNav = { switchDashboardView: switchDashboardView };
})();
