/* ============================================================================
   FILE: sdps_router.js
   PATH: public/sdps/sdps_router.js
   VERSION: 1.0.0
   PURPOSE: Client-side hash router for the SDPS workspace.
            Toggles section visibility without full page reloads.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

(function (global) {
    'use strict';

    var ROUTES = [
        { id: 'home',              hash: '#home',              label: 'Home',              icon: 'fa-house',               title: 'Home' },
        { id: 'load-from-sdc',     hash: '#load-from-sdc',     label: 'Load from SDC',     icon: 'fa-cloud-arrow-down',    title: 'Load from SDC' },
        { id: 'hazard',            hash: '#hazard',            label: 'Hazard',            icon: 'fa-triangle-exclamation', title: 'Hazard Register' },
        { id: 'hazard-analysis',   hash: '#hazard-analysis',   label: 'Hazard Analysis',   icon: 'fa-chart-pie',           title: 'Hazard Analysis' },
        { id: 'occurrence',        hash: '#occurrence',        label: 'Occurrence',        icon: 'fa-plane-arrival',       title: 'Occurrence Register' },
        { id: 'occurrence-analysis', hash: '#occurrence-analysis', label: 'Occurrence Analysis', icon: 'fa-chart-line',      title: 'Occurrence Analysis' },
        { id: 'hrc',               hash: '#hrc',               label: 'High Risk Categories', icon: 'fa-exclamation-triangle', title: 'High Risk Categories' },
        { id: 'data',              hash: '#data',              label: 'Data',              icon: 'fa-table',               title: 'Data Management' },
        { id: 'spis',              hash: '#spis',              label: 'SPIs and SPTs',     icon: 'fa-gauge-high',          title: 'SPIs and SPTs' },
        { id: 'taxonomy',          hash: '#taxonomy',          label: 'Taxonomy',          icon: 'fa-sitemap',             title: 'Taxonomy' },
        { id: 'tools',             hash: '#tools',             label: 'Tools',             icon: 'fa-wrench',              title: 'Tools' },
        { id: 'preferences',       hash: '#preferences',       label: 'Preferences',       icon: 'fa-cog',                 title: 'Preferences' },
        { id: 'generate-report',   hash: '#generate-report',   label: 'Generate Report',   icon: 'fa-file-pdf',            title: 'Generate Report' },
        { id: 'about',             hash: '#about',             label: 'About',             icon: 'fa-info-circle',         title: 'About' },
    ];

    var DEFAULT_ROUTE = 'home';
    var currentRoute = null;
    var viewCallbacks = {};

    function getRouteFromHash() {
        var hash = window.location.hash.replace(/^#/, '') || DEFAULT_ROUTE;
        for (var i = 0; i < ROUTES.length; i++) {
            if (ROUTES[i].id === hash || ROUTES[i].hash === '#' + hash) return ROUTES[i];
        }
        return null;
    }

    function navigate(routeId) {
        var route = null;
        for (var i = 0; i < ROUTES.length; i++) {
            if (ROUTES[i].id === routeId) { route = ROUTES[i]; break; }
        }
        if (!route) return;

        if (currentRoute && currentRoute.id === routeId) return;

        // Hide all views
        var views = document.querySelectorAll('[data-view]');
        for (var v = 0; v < views.length; v++) {
            views[v].style.display = 'none';
        }

        // Show target view
        var target = document.getElementById('sdps-view-' + route.id);
        if (target) target.style.display = 'block';

        // Update sidebar active state
        var links = document.querySelectorAll('.sdps-sidebar-nav li a');
        for (var l = 0; l < links.length; l++) {
            var isActive = links[l].getAttribute('data-route') === route.id;
            links[l].classList.toggle('active', isActive);
        }

        // Update header title
        var titleEl = document.getElementById('sdpsHeaderTitle');
        if (titleEl) titleEl.textContent = route.title;

        // Update hash without triggering hashchange
        if (window.location.hash !== route.hash) {
            history.pushState(null, '', route.hash);
        }

        currentRoute = route;

        // Fire route callback
        if (viewCallbacks[route.id]) {
            try { viewCallbacks[route.id](); } catch (e) { console.error('[SDPS Router] callback error:', e); }
        }
    }

    function onRoute(routeId, callback) {
        viewCallbacks[routeId] = callback;
    }

    function getCurrentRoute() {
        return currentRoute ? currentRoute.id : DEFAULT_ROUTE;
    }

    function getRoutes() {
        return ROUTES.slice();
    }

    // Build sidebar nav
    function buildNav() {
        var ul = document.getElementById('sdpsNavList');
        if (!ul) return;
        ul.innerHTML = '';
        for (var i = 0; i < ROUTES.length; i++) {
            var r = ROUTES[i];
            var li = document.createElement('li');
            var a = document.createElement('a');
            a.href = r.hash;
            a.setAttribute('data-route', r.id);
            a.innerHTML = '<i class="fas ' + r.icon + '"></i><span>' + r.label + '</span>';
            a.addEventListener('click', (function (routeId) {
                return function (e) {
                    e.preventDefault();
                    navigate(routeId);
                };
            })(r.id));
            li.appendChild(a);
            ul.appendChild(li);
        }
    }

    function init() {
        buildNav();
        var route = getRouteFromHash() || { id: DEFAULT_ROUTE };
        navigate(route.id);

        window.addEventListener('hashchange', function () {
            var r = getRouteFromHash();
            if (r) navigate(r.id);
        });

        // Sidebar toggle
        var toggle = document.getElementById('sdpsSidebarToggle');
        var sidebar = document.getElementById('sdpsSidebar');
        if (toggle && sidebar) {
            toggle.addEventListener('click', function () {
                sidebar.classList.toggle('open');
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    global.SDPSRouter = {
        navigate: navigate,
        onRoute: onRoute,
        getCurrentRoute: getCurrentRoute,
        getRoutes: getRoutes,
    };

})(window);
