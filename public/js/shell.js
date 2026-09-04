/* ============================================================================
   FILE: shell.js
   PATH: public/js/shell.js
   VERSION: 2.0.0
   PURPOSE: Shared dashboard shell. Renders the fixed top header (brand + nav
            with WordPress-style dropdowns + user + logout), a clean page hero
            (airline name + department subtitle), and a single-line footer.
            No sidebar, no hamburger, no overlay — content is full width.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

(function (global) {
    'use strict';

    // Returns a mock user for local development (localhost / 127.0.0.1) so the
    // shell can render tenant info, user email and role without Firebase auth.
    // Set localStorage 'mockEmail' to override the default email.
    function getLocalUser() {
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            return {
                email: localStorage.getItem('mockEmail') || 'safety@fixedwing.com',
                role: 'safety_manager',
                tenant: 'fixedwing'
            };
        }
        return null;
    }
    global.getLocalUser = getLocalUser;

    // Returns the current user email: from an authenticated session if present,
    // otherwise the local mock user (localhost), otherwise a safe default.
    function getUserEmail() {
        try {
            if (typeof firebase !== 'undefined' && firebase.auth && firebase.auth().currentUser) {
                return firebase.auth().currentUser.email;
            }
        } catch (e) {}
        const local = getLocalUser();
        if (local) return local.email;
        return null;
    }
    global.getUserEmail = getUserEmail;

    // Derive a human-friendly airline/company name from an email domain.
    // 'safety@fixedwing.com' -> 'Fixedwing'
    function airlineNameFromEmail(email) {
        if (!email) return 'Unknown';
        const domain = String(email).split('@')[1] || '';
        const seg = domain.split('.')[0] || 'Unknown';
        return seg.charAt(0).toUpperCase() + seg.slice(1);
    }
    global.airlineNameFromEmail = airlineNameFromEmail;

    // Shell configuration is supplied by each page BEFORE this script loads:
    //   window.SHELL_CONFIG = {
    //     brand: 'AviaSAFE',
    //     roleLabel: 'Operator Safety Dashboard',   // shown under the page title
    //     tenantTitle: 'SITA AIR',                  // optional (tenant scope)
    //     heroTitle: 'Custom Page Title',           // optional page title override
    //     heroSubtitle: 'Custom subtitle',          // optional subtitle override
    //   }
    let cfg = global.SHELL_CONFIG || {};

    function refreshCfg() {
        if (global.SHELL_CONFIG) cfg = global.SHELL_CONFIG;
        return cfg;
    }

    // ---- Header navigation: [Home] + direct links + Administration dropdown ----
    const NAV_ITEMS = [
        { label: 'SMS Maturity', href: '/dashboard/sms-maturity.html' },
        { label: 'Risk & Trends', href: '/risk-trends.html' },
        { label: 'Top Hazards', href: '/top-hazards.html' },
        { label: 'SPI/SPT', href: '/dashboard/spi-dashboard.html' },
        {
            label: 'Administration',
            dropdown: [
                { href: '/administration.html', label: 'System Settings' },
                { href: '/settings/team.html', label: 'Team Management' },
                { href: '/admin/super-admin.html', label: 'Super Admin' }
            ]
        }
    ];

    // Persistent user session surface so static pages can share tenant/user info.
    const currentUserState = { email: null, tenant: null, dept: null };

    global.handleLogout = function () {
        try {
            if (typeof TenantResolver !== 'undefined' && TenantResolver.clearTenantSession) {
                TenantResolver.clearTenantSession();
            } else if (typeof TenantResolver !== 'undefined' && TenantResolver.clearDemoTenant) {
                TenantResolver.clearDemoTenant();
            }
        } catch (e) {}
        try {
            window.__AUTH_TENANT_ID = null;
        } catch (e2) {}
        if (typeof firebase !== 'undefined' && firebase.auth) {
            firebase.auth().signOut().then(function () {
                window.location.href = '/login.html';
            }).catch(function () {
                window.location.href = '/login.html';
            });
        } else {
            window.location.href = '/login.html';
        }
    };

    // Set the active nav link based on the current page path.
    function setActiveNav() {
        const path = window.location.pathname || '';
        const base = path.split('/').pop() || '';
        document.querySelectorAll('.app-header .header-nav a.nav-link[href]').forEach(function (a) {
            const href = a.getAttribute('href') || '';
            const hrefBase = href.split('/').pop().split('#')[0] || '';
            a.classList.toggle('active', hrefBase === base && href !== '#');
        });
    }

    function buildHeader() {
        const email = getUserEmail() || 'Unknown';

        const header = document.createElement('header');
        header.className = 'app-header';
        header.id = 'shellHeader';

        // ---- Top Row: Brand + User ----
        const top = document.createElement('div');
        top.className = 'header-top';

        const left = document.createElement('div');
        left.className = 'header-left';
        const brand = document.createElement('a');
        brand.className = 'header-brand';
        brand.href = '/safety.html';
        brand.innerHTML = '<span class="logo-icon">\u2708\uFE0F</span> AviaSAFE';
        left.appendChild(brand);
        top.appendChild(left);

        const right = document.createElement('div');
        right.className = 'header-right';
        const user = document.createElement('span');
        user.className = 'user-email';
        user.id = 'shellUser';
        user.textContent = email;
        right.appendChild(user);
        const logout = document.createElement('button');
        logout.type = 'button';
        logout.className = 'logout-btn';
        logout.id = 'shellLogoutBtn';
        logout.textContent = 'Logout';
        logout.addEventListener('click', function () {
            try { localStorage.removeItem('mockEmail'); } catch (e) {}
            global.handleLogout();
        });
        right.appendChild(logout);
        top.appendChild(right);

        header.appendChild(top);

        // ---- Yellow Separator Line ----
        const divider = document.createElement('div');
        divider.className = 'header-divider';
        header.appendChild(divider);

        // ---- Bottom Row: Navigation ----
        const nav = document.createElement('nav');
        nav.className = 'header-nav';

        // Conditional Home link - show on all pages except landing (safety.html)
        const path = window.location.pathname || '';
        const isLandingPage = path === '/safety.html' || path === '/' || path === '/index.html' || path.endsWith('/safety.html');
        if (!isLandingPage) {
            const homeLink = document.createElement('a');
            homeLink.href = '/safety.html';
            homeLink.className = 'nav-link nav-home';
            const homeIcon = document.createElement('span');
            homeIcon.className = 'home-icon';
            homeIcon.textContent = '\uD83C\uDFE0'; // 🏠
            homeIcon.setAttribute('aria-hidden', 'true');
            const homeText = document.createElement('span');
            homeText.className = 'home-text';
            homeText.textContent = 'Home';
            homeLink.appendChild(homeIcon);
            homeLink.appendChild(document.createTextNode(' '));
            homeLink.appendChild(homeText);
            nav.appendChild(homeLink);
        }

        NAV_ITEMS.forEach(function (item) {
            if (item.dropdown) {
                const dd = document.createElement('div');
                dd.className = 'nav-dropdown';
                const link = document.createElement('a');
                link.href = '#';
                link.className = 'nav-link';
                link.textContent = item.label + ' ';
                const caret = document.createElement('span');
                caret.className = 'caret';
                caret.textContent = '\u25BC';
                link.appendChild(caret);
                const content = document.createElement('div');
                content.className = 'dropdown-content';
                item.dropdown.forEach(function (d) {
                    const da = document.createElement('a');
                    da.href = d.href;
                    da.textContent = d.label;
                    content.appendChild(da);
                });
                dd.appendChild(link);
                dd.appendChild(content);
                nav.appendChild(dd);
            } else {
                const a = document.createElement('a');
                a.href = item.href;
                a.className = 'nav-link';
                a.textContent = item.label;
                nav.appendChild(a);
            }
        });
        header.appendChild(nav);

        return header;
    }

    // Clean page hero: airline name (from email) + department subtitle.
    function buildHero() {
        const email = getUserEmail() || 'Unknown';
        const airlineName = cfg.heroTitle || cfg.tenantTitle || airlineNameFromEmail(email);

        const hero = document.createElement('div');
        hero.className = 'page-hero';

        const title = document.createElement('h1');
        title.id = 'pageTitle';
        title.textContent = airlineName;

        const subtitle = document.createElement('p');
        subtitle.className = 'subtitle';
        subtitle.id = 'pageSubtitle';
        subtitle.textContent = cfg.heroSubtitle || cfg.roleLabel || (airlineNameFromEmail(email) + ' - Safety Department');

        hero.appendChild(title);
        hero.appendChild(subtitle);
        return hero;
    }

    function buildFooter() {
        const footer = document.createElement('footer');
        footer.className = 'app-footer';
        footer.id = 'shellFooter';
        const content = document.createElement('div');
        content.className = 'footer-content';
        content.appendChild(document.createTextNode('Made with '));
        const heart = document.createElement('span');
        heart.className = 'heart';
        heart.textContent = '❤️';
        content.appendChild(heart);
        content.appendChild(document.createTextNode(' from Nepal'));
        footer.appendChild(content);
        return footer;
    }

    function applyTenantToSurveyLinks(tenantId) {
        if (!tenantId) return;
        document.querySelectorAll('a[href*="/survey"]').forEach(function (a) {
            const href = a.getAttribute('href') || '';
            if (href.indexOf('/survey') === -1) return;
            if (href.indexOf('tenant=') !== -1) return;
            const sep = href.indexOf('?') === -1 ? '?' : '&';
            a.setAttribute('href', href + sep + 'tenant=' + encodeURIComponent(tenantId));
        });
    }

    function loadInterFont() {
        if (document.querySelector('link[href*="Inter"]')) return;
        const link = document.createElement('link');
        link.href = 'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap';
        link.rel = 'stylesheet';
        document.head.appendChild(link);
    }

    function initShell() {
        if (document.getElementById('shellHeader')) return;
        loadInterFont();
        const shell = document.querySelector('.app-shell');
        if (!shell) return;

        // Re-read SHELL_CONFIG in case it was assigned after this script loaded.
        refreshCfg();

        const main = document.createElement('main');
        main.className = 'main-content';

        // Wrap existing children into the main content area.
        const content = document.createElement('div');
        content.className = 'shell-content';
        while (shell.firstChild) content.appendChild(shell.firstChild);

        main.appendChild(buildHeader());
        main.appendChild(buildHero());
        main.appendChild(content);
        if (!document.querySelector('footer.app-footer')) {
            main.appendChild(buildFooter());
        }

        shell.appendChild(main);

        setActiveNav();

        // Mobile dropdown: click-to-toggle (hover is unreliable on touch). On
        // narrow screens every .nav-dropdown .nav-link becomes a toggle; on
        // desktop the CSS :hover handles it (we keep open-class in sync so the
        // panel stays open if the window is resized down while hovered).
        function bindDropdownToggles() {
            document.querySelectorAll('.nav-dropdown').forEach(function (dd) {
                const link = dd.querySelector('.nav-link');
                if (!link) return;
                link.onclick = function (e) {
                    if (link.getAttribute('href') === '#') e.preventDefault();
                    const content = dd.querySelector('.dropdown-content');
                    if (!content) return;
                    if (window.innerWidth < 768) {
                        const willOpen = !content.classList.contains('open');
                        document.querySelectorAll('.dropdown-content.open').forEach(function (o) {
                            if (o !== content) o.classList.remove('open');
                        });
                        content.classList.toggle('open', willOpen);
                    } else {
                        content.classList.remove('open');
                    }
                };
            });
        }
        bindDropdownToggles();
        window.addEventListener('resize', bindDropdownToggles);

        // Populate the header user email once auth is ready.
        if (typeof firebase !== 'undefined' && firebase.auth) {
            firebase.auth().onAuthStateChanged(function (user) {
                const email = user ? user.email : (getUserEmail() || 'Unknown');
                currentUserState.email = user ? user.email : null;
                const el = document.getElementById('shellUser');
                if (el) el.textContent = email;
                const pageSubtitle = document.getElementById('pageSubtitle');
                if (user && user.getIdTokenResult) {
                    user.getIdTokenResult(true).then(function (tokenResult) {
                        const claims = (tokenResult && tokenResult.claims) || {};
                        if (claims.tenant_id) applyTenantToSurveyLinks(claims.tenant_id);
                        currentUserState.tenant = claims.tenant_id || null;
                        if (pageSubtitle && typeof getDepartmentLabel === 'function') {
                            pageSubtitle.textContent = cfg.heroSubtitle || getDepartmentLabel(claims) || '—';
                        }
                    }).catch(function () {});
                }
            });
        } else {
            applyLocalUserToShell();
        }
    }

    // Local development: populate the header user email from the mock user
    // (so pages render without Firebase auth on localhost).
    function applyLocalUserToShell() {
        const local = getLocalUser();
        if (!local) return;
        currentUserState.email = local.email;
        const el = document.getElementById('shellUser');
        if (el) el.textContent = local.email;
    }

    // Allow pages to update the page hero title after auth resolves.
    global.updateShellTenant = function (title, meta) {
        cfg.tenantTitle = title || cfg.tenantTitle;
        cfg.tenantMeta = meta || cfg.tenantMeta;
        const pageTitle = document.getElementById('pageTitle');
        if (pageTitle) pageTitle.textContent = cfg.tenantTitle || pageTitle.textContent;
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initShell);
    } else {
        initShell();
    }
})(window);