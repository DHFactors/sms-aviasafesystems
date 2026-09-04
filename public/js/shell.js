/* ============================================================================
   FILE: shell.js
   PATH: public/js/shell.js
   VERSION: 1.0.0
   PURPOSE: Shared dashboard shell. Renders the fixed left sidebar navigation,
            the top header (brand + tenant info + user + logout), a hero showing
            the tenant title + department subtitle, a clean single-line footer,
            and scroll-spy active states. Used by all tenant dashboards and the
            CAAN dashboard.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

(function (global) {
    'use strict';

    // Shell configuration is supplied by each page BEFORE this script loads:
    //   window.SHELL_CONFIG = {
    //     brand: 'AviaSAFE',
    //     roleLabel: 'Airline Safety Manager',     // shown under brand in sidebar
    //     tenantTitle: 'SITA AIR',                 // optional (tenant scope)
    //     tenantMeta: 'ICAO: STA · Nepal',         // optional additional info
    //     heroSubtitle: 'Corporate Safety Dept',   // optional hero subtitle override
    //                                                (defaults to department label)
    //     nav: [ { id: 'overview', label: 'Overview', icon: 'fa-gauge-high' }, ... ],
    //     links: [ { href, label }, ... ]          // optional footer links
    //   }
    //
    // Pages may set SHELL_CONFIG either before or after this script runs (in a
    // script that executes before DOMContentLoaded). We re-read it at init time
    // so the sidebar/header always reflect the latest config.
    let cfg = global.SHELL_CONFIG || { nav: [] };

    function refreshCfg() {
        if (global.SHELL_CONFIG) cfg = global.SHELL_CONFIG;
        return cfg;
    }

    // Hide/show sidebar items that declare a restricted set of roles.
    // A nav item may specify `roles: ['AIRLINE_ADMIN', ...]` to be shown
    // only to users whose role is in that list.
    function applyNavVisibility(role) {
        document.querySelectorAll('.sidebar-nav li[data-roles]').forEach(function (li) {
            const allowed = (li.dataset.roles || '').split(',').filter(function (r) { return r; });
            li.style.display = allowed.indexOf(role) !== -1 ? '' : 'none';
        });
    }

    // ---- Shared navigation config for the fixed header tabs (Phase 5) ----
    const HEADER_LINKS = [
        { href: '/dashboard/sms-maturity.html', label: 'SMS Maturity', match: 'sms-maturity' },
        { href: '/risk-trends.html',           label: 'Risk & Trends', match: 'risk-trends' },
        { href: '/top-hazards.html',           label: 'Top Hazards',  match: 'top-hazards' },
        { href: '/dashboard/spi-dashboard.html', label: 'SPI/SPT',    match: 'spi-dashboard' },
        { href: '/administration.html',        label: 'Administration', match: 'administration' }
    ];

    // ---- Sidebar secondary links (Phase 5) ----
    const SIDEBAR_LINKS = [
        { icon: 'fa-users',    href: '/settings/team.html', label: 'Team' },
        { icon: 'fa-question-circle', href: '/help.html',   label: 'Help' },
        { icon: 'fa-comment-dots',    href: '/feedback.html', label: 'Feedback' }
    ];

    const VERSION_LINE = 'AviaSAFE SMS v1.0 · © 2026 AviaSafe Systems';

    // Set the active header tab based on the current page path.
    function setActiveHeaderLink() {
        const path = window.location.pathname || '';
        document.querySelectorAll('.app-header .nav-tabs a').forEach(function (a) {
            const href = a.getAttribute('href') || '';
            const matchItem = HEADER_LINKS.find(function (item) { return href.indexOf(item.href) !== -1; }) || {};
            const match = matchItem.match || '';
            const active = match && path.indexOf(match) !== -1;
            a.classList.toggle('active', active);
        });
    }

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

    global.closeSidebar = function () {
        const sb = document.getElementById('shellSidebar');
        const ov = document.getElementById('sidebarOverlay');
        if (sb) sb.classList.remove('open');
        if (ov) ov.classList.remove('active');
    };

    global.toggleSidebar = function () {
        const sb = document.getElementById('shellSidebar');
        const ov = document.getElementById('sidebarOverlay');
        if (!sb) return;
        const open = sb.classList.toggle('open');
        if (ov) ov.classList.toggle('active', open);
    };

    function bindShellInteractions() {
        // Hamburger toggles sidebar
        const hamb = document.getElementById('shellHamburger');
        if (hamb) hamb.addEventListener('click', function () { global.toggleSidebar(); });

        // Overlay click closes sidebar
        const ov = document.getElementById('sidebarOverlay');
        if (ov) ov.addEventListener('click', function () { global.closeSidebar(); });

        // Escape closes sidebar
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') global.closeSidebar();
        });

        // Resize >= 769px auto-closes mobile sidebar
        window.addEventListener('resize', function () {
            if (window.innerWidth >= 769) global.closeSidebar();
        });
    }

    function buildSidebar() {
        const aside = document.createElement('aside');
        aside.className = 'shell-sidebar';
        aside.id = 'shellSidebar';

        // Brand/logo
        const brand = document.createElement('a');
        brand.className = 'sidebar-brand';
        brand.href = '/safety.html';
        brand.innerHTML = '<i class="fas fa-shield-alt"></i><span>' +
            (cfg.brand || 'AviaSAFE') + '</span>';
        aside.appendChild(brand);

        // Tenant info block (name + department)
        if (cfg.tenantTitle || cfg.roleLabel) {
            const tenant = document.createElement('div');
            tenant.className = 'sidebar-tenant';
            tenant.innerHTML =
                (cfg.tenantTitle ? '<div class="tenant-name">' + cfg.tenantTitle + '</div>' : '') +
                (cfg.roleLabel ? '<div class="tenant-dept">' + cfg.roleLabel + '</div>' : '');
            aside.appendChild(tenant);
        } else if (cfg.tenantTitle) {
            const tenant = document.createElement('div');
            tenant.className = 'sidebar-tenant';
            tenant.innerHTML = '<div class="tenant-name">' + cfg.tenantTitle + '</div>';
            aside.appendChild(tenant);
        }

        // User email + logout (secondary)
        const user = document.createElement('div');
        user.className = 'sidebar-user';
        user.id = 'sidebarUser';
        user.innerHTML = '<span class="sidebar-email">—</span>';
        aside.appendChild(user);

        // Secondary links (Team, Help, Feedback)
        const navWrap = document.createElement('nav');
        navWrap.className = 'sidebar-nav';
        const ul = document.createElement('ul');
        SIDEBAR_LINKS.forEach(function (item) {
            const li = document.createElement('li');
            const a = document.createElement('a');
            a.href = item.href;
            a.innerHTML = '<i class="fas ' + item.icon + '"></i><span>' + item.label + '</span>';
            li.appendChild(a);
            ul.appendChild(li);
        });
        navWrap.appendChild(ul);
        aside.appendChild(navWrap);

        // Version footer
        const foot = document.createElement('div');
        foot.className = 'sidebar-footer';
        foot.textContent = VERSION_LINE;
        aside.appendChild(foot);

        return aside;
    }

    function buildHeader() {
        const header = document.createElement('header');
        header.className = 'app-header';
        header.id = 'shellHeader';

        // Left: hamburger (mobile) + brand/logo → /safety.html
        const left = document.createElement('div');
        left.className = 'shell-hamburger-area';
        const hamb = document.createElement('button');
        hamb.type = 'button';
        hamb.id = 'shellHamburger';
        hamb.className = 'hamburger-btn';
        hamb.setAttribute('aria-label', 'Toggle navigation');
        hamb.innerHTML = '<i class="fas fa-bars"></i>';
        left.appendChild(hamb);
        const brand = document.createElement('a');
        brand.className = 'brand-link';
        brand.href = '/safety.html';
        brand.innerHTML = '<i class="fas fa-shield-alt"></i><span>Avia' +
            '<span style="color:#0d9488;">SAFE</span></span>';
        left.appendChild(brand);
        header.appendChild(left);

        // Center: navigation tabs (primary modules)
        const nav = document.createElement('nav');
        nav.className = 'nav-tabs';
        HEADER_LINKS.forEach(function (item) {
            const a = document.createElement('a');
            a.href = item.href;
            a.textContent = item.label;
            nav.appendChild(a);
        });
        header.appendChild(nav);

        // Right: user email (desktop) + logout
        const actions = document.createElement('div');
        actions.className = 'header-actions';
        const user = document.createElement('span');
        user.className = 'header-user';
        user.id = 'shellUser';
        user.textContent = '—';
        actions.appendChild(user);
        const logout = document.createElement('button');
        logout.type = 'button';
        logout.className = 'btn-logout';
        logout.id = 'shellLogoutBtn';
        logout.innerHTML = '<i class="fas fa-sign-out-alt"></i> Logout';
        logout.addEventListener('click', function () { global.handleLogout(); });
        actions.appendChild(logout);
        header.appendChild(actions);

        return header;
    }

    // Uniform page title block: centered tenant/page title + department label
    // (mapped from the signed-in user's role / custom claims).
    function buildHero() {
        const hero = document.createElement('section');
        hero.className = 'shell-hero';
        hero.id = 'shellHero';
        const title = document.createElement('h1');
        title.className = 'shell-hero-title';
        title.id = 'shellHeroTitle';
        title.textContent = cfg.heroTitle || cfg.tenantTitle || cfg.roleLabel || (cfg.brand || 'AviaSAFE');
        const user = document.createElement('div');
        user.className = 'shell-hero-user';
        user.id = 'shellHeroUser';
        user.textContent = cfg.heroSubtitle || '—';
        hero.appendChild(title);
        hero.appendChild(user);
        return hero;
    }

    // Footer: three lines on desktop, single line ("Made with ❤️ from Nepal")
    // on mobile (handled by CSS media queries).
    function buildFooter() {
        const footer = document.createElement('footer');
        footer.className = 'app-footer';
        footer.id = 'shellFooter';

        const l1 = document.createElement('div');
        l1.className = 'footer-line1';
        l1.textContent = 'AviaSAFE SMS v1.0';
        const l2 = document.createElement('div');
        l2.className = 'footer-line2';
        l2.innerHTML = 'Made with <span class="heart">&hearts;</span> from Nepal';
        const l3 = document.createElement('div');
        l3.className = 'footer-line3';
        l3.textContent = '© 2026 AviaSafe Systems';
        footer.appendChild(l1);
        footer.appendChild(l2);
        footer.appendChild(l3);
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

    function attachScrollSpy() {
        const links = document.querySelectorAll('.sidebar-nav li a');
        const navWrap = document.querySelector('.sidebar-nav');
        const targets = (cfg.nav || [])
            .map(function (n) { return document.getElementById(n.id); })
            .filter(Boolean);

        function onScroll() {
            const pos = window.scrollY + 120;
            let current = null;
            targets.forEach(function (el) {
                if (el.offsetParent === null) return;
                if (el.offsetTop <= pos) current = el.id;
            });
            if (!current && targets.length) current = targets[0].id;
            if (navWrap) {
                // Dim every section except the one currently in view.
                if (current) navWrap.classList.add('has-active');
                else navWrap.classList.remove('has-active');
            }
            links.forEach(function (a) {
                if (a.dataset.target === current) a.classList.add('active');
                else a.classList.remove('active');
            });
        }

        links.forEach(function (a) {
            a.addEventListener('click', function (e) {
                const el = document.getElementById(a.dataset.target);
                if (el) {
                    e.preventDefault();
                    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            });
        });

        window.addEventListener('scroll', onScroll, { passive: true });
        onScroll();
    }

    function loadInterFont() {
        if (document.querySelector('link[href*="Inter"]')) return;
        const link = document.createElement('link');
        link.href = 'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap';
        link.rel = 'stylesheet';
        document.head.appendChild(link);
    }

    function initShell() {
        if (document.getElementById('shellSidebar')) return;
        loadInterFont();
        const shell = document.querySelector('.app-shell');
        if (!shell) return;

        // Demo: hide N-HRC dashboard link until full Supabase migration is complete
        // This keeps the sidebar clean for the demo; revisit after migration.
        try {
            const style = document.createElement('style');
            style.textContent = 'a[href*="nhrc-dashboard.html"]{display:none !important;} a[href*="/dashboard/nhrc"]{display:none !important;}';
            document.head.appendChild(style);
        } catch (e) {}

        // Re-read SHELL_CONFIG in case it was assigned after this script loaded.
        refreshCfg();

        const sidebar = buildSidebar();
        const main = document.createElement('div');
        main.className = 'shell-main';

        // Wrap existing children into .shell-content
        const content = document.createElement('div');
        content.className = 'shell-content';
        while (shell.firstChild) content.appendChild(shell.firstChild);
        const header = buildHeader();
        header.classList.add('is-fixed');
        main.appendChild(header);
        main.appendChild(buildHero());
        main.appendChild(content);
        // Pages that ship their own complete static footer (the single-line
        // .app-footer with "Made with love") must not also receive the shell
        // footer — that stacked two footers.
        if (!document.querySelector('footer.app-footer')) {
            main.appendChild(buildFooter());
        }
        shell.appendChild(sidebar);
        shell.appendChild(main);

        // Overlay backdrop (mobile sidebar)
        const overlay = document.createElement('div');
        overlay.id = 'sidebarOverlay';
        overlay.className = 'sidebar-overlay';
        shell.appendChild(overlay);

        // Wire hamburger / overlay / escape / resize interactions.
        bindShellInteractions();

        setActiveHeaderLink();
        attachScrollSpy();

        // Populate user email (header + sidebar) + department (hero subtitle)
        // once auth is ready.
        if (typeof firebase !== 'undefined' && firebase.auth) {
            firebase.auth().onAuthStateChanged(function (user) {
                const email = user ? user.email : '—';
                currentUserState.email = user ? user.email : null;
                const el = document.getElementById('shellUser');
                if (el) el.textContent = email;
                const sidebarUser = document.getElementById('sidebarUser');
                if (sidebarUser) {
                    sidebarUser.innerHTML = user
                        ? '<i class="fas fa-user-cog"></i><span class="sidebar-email">' + email + '</span>'
                        : '<span class="sidebar-email">—</span>';
                }
                const heroUser = document.getElementById('shellHeroUser');
                if (heroUser) heroUser.textContent = '—';
                if (user && user.getIdTokenResult) {
                    user.getIdTokenResult(true).then(function (tokenResult) {
                        const claims = (tokenResult && tokenResult.claims) || {};
                        applyNavVisibility(claims.role || 'USER');
                        if (claims.tenant_id) applyTenantToSurveyLinks(claims.tenant_id);
                        currentUserState.tenant = claims.tenant_id || null;
                        if (heroUser && typeof getDepartmentLabel === 'function') {
                            heroUser.textContent = cfg.heroSubtitle || getDepartmentLabel(claims) || '—';
                        }
                    }).catch(function () {
                        if (heroUser) heroUser.textContent = '—';
                    });
                } else {
                    applyNavVisibility('USER');
                }
            });
        }
    }

    // Allow pages to update the sidebar tenant info + hero title after auth resolves.
    global.updateShellTenant = function (title, meta) {
        cfg.tenantTitle = title || cfg.tenantTitle;
        cfg.tenantMeta = meta || cfg.tenantMeta;
        const tenantEl = document.querySelector('.sidebar-tenant');
        if (tenantEl) {
            const nameEl = tenantEl.querySelector('.tenant-name');
            if (nameEl) nameEl.textContent = title || '';
        }
        const heroTitle = document.getElementById('shellHeroTitle');
        if (heroTitle) heroTitle.textContent = cfg.tenantTitle || cfg.roleLabel || '';
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initShell);
    } else {
        initShell();
    }
})(window);
