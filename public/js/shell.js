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

    function buildSidebar() {
        const aside = document.createElement('aside');
        aside.className = 'shell-sidebar';
        aside.id = 'shellSidebar';

        const brand = document.createElement('div');
        brand.className = 'sidebar-brand';
        brand.innerHTML = '<i class="fas fa-shield-alt"></i><span>' +
            (cfg.brand || 'AviaSAFE') + '</span>';
        aside.appendChild(brand);

        if (cfg.roleLabel) {
            const role = document.createElement('div');
            role.className = 'sidebar-role';
            role.textContent = cfg.roleLabel;
            aside.appendChild(role);
        }

        const navWrap = document.createElement('nav');
        navWrap.className = 'sidebar-nav';
        const ul = document.createElement('ul');
        (cfg.nav || []).forEach(function (item) {
            const li = document.createElement('li');
            if (Array.isArray(item.roles) && item.roles.length) {
                li.dataset.roles = item.roles.join(',');
            }
            const a = document.createElement('a');
            if (item.href) {
                a.href = item.href;
            } else {
                a.href = '#' + item.id;
                a.dataset.target = item.id;
            }
            a.innerHTML = '<i class="fas ' + (item.icon || 'fa-circle') + '"></i>' +
                '<span>' + item.label + '</span>';
            li.appendChild(a);
            ul.appendChild(li);
        });
        navWrap.appendChild(ul);
        aside.appendChild(navWrap);

        const foot = document.createElement('div');
        foot.className = 'sidebar-footer';
        foot.textContent = 'ICAO Annex 19 · Doc 9859 · Doc 10159';
        aside.appendChild(foot);

        return aside;
    }

    function buildHeader() {
        const header = document.createElement('header');
        header.className = 'shell-header';
        header.id = 'shellHeader';

        const brand = document.createElement('div');
        brand.className = 'shell-brand';
        brand.innerHTML = '<i class="fas fa-shield-alt"></i><span>Avia' +
            '<span style="color:#34a853;">SAFE</span>system</span>';
        header.appendChild(brand);

        if (cfg.tenantTitle) {
            const tenant = document.createElement('div');
            tenant.className = 'shell-tenant';
            tenant.innerHTML = '<div class="tenant-name">' + cfg.tenantTitle + '</div>' +
                (cfg.tenantMeta ? '<div class="tenant-meta">' + cfg.tenantMeta + '</div>' : '');
            header.appendChild(tenant);
        }

        const actions = document.createElement('div');
        actions.className = 'shell-actions';
        const user = document.createElement('span');
        user.className = 'shell-user';
        user.id = 'shellUser';
        user.textContent = '—';
        actions.appendChild(user);
        const logout = document.createElement('button');
        logout.className = 'btn-logout';
        logout.id = 'shellLogoutBtn';
        logout.innerHTML = '<i class="fas fa-sign-out-alt"></i> Logout';
        logout.addEventListener('click', function () {
            if (typeof firebase !== 'undefined' && firebase.auth) {
                firebase.auth().signOut().then(function () {
                    window.location.href = '/login.html';
                });
            } else {
                window.location.href = '/login.html';
            }
        });
        actions.appendChild(logout);
        header.appendChild(actions);

        return header;
    }

    // Uniform top section: centered tenant name (title) + department label
    // (mapped from the signed-in user's role / custom claims).
    function buildHero() {
        const hero = document.createElement('section');
        hero.className = 'shell-hero';
        hero.id = 'shellHero';
        const title = document.createElement('h1');
        title.className = 'shell-hero-title';
        title.id = 'shellHeroTitle';
        title.textContent = cfg.tenantTitle || cfg.roleLabel || (cfg.brand || 'AviaSAFE');
        const user = document.createElement('div');
        user.className = 'shell-hero-user';
        user.id = 'shellHeroUser';
        user.textContent = cfg.heroSubtitle || '—';
        hero.appendChild(title);
        hero.appendChild(user);
        return hero;
    }

    // Clean single-line footer. The user's email and department live in the
    // header; the floating "Send Feedback" widget is injected separately by
    // feedback.js and stays untouched.
    function buildFooter() {
        const footer = document.createElement('footer');
        footer.className = 'dashboard-footer text-center py-3';
        footer.id = 'shellFooter';

        const links = document.createElement('div');
        links.style.fontSize = '0.875rem';
        links.style.marginBottom = '0.5rem';
        links.innerHTML =
            '<a href="/privacy.html" style="color: rgba(255,255,255,0.75); text-decoration: none;">Privacy Policy</a>' +
            '<span style="margin: 0 0.5rem; color: rgba(255,255,255,0.4);">|</span>' +
            '<a href="/terms.html" style="color: rgba(255,255,255,0.75); text-decoration: none;">Terms of Service</a>';
        footer.appendChild(links);

        const p = document.createElement('p');
        p.className = 'mb-0 text-muted';
        p.style.fontSize = '0.875rem';
        p.style.fontWeight = '500';
        p.style.marginTop = '0.25rem';
        p.innerHTML = 'A Project by <strong>Ghanshyam Acharya</strong>';
        footer.appendChild(p);

        const cr = document.createElement('p');
        cr.className = 'mb-0 text-muted';
        cr.style.fontSize = '0.75rem';
        cr.style.opacity = '0.7';
        cr.style.marginTop = '0.25rem';
        cr.textContent = '\u00A9 2026 AviaSAFE Systems. Engineered for ICAO Annex 19 (3rd Ed.), Doc 9859 & Doc 10159 Compliance.';
        footer.appendChild(cr);
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

        // Re-read SHELL_CONFIG in case it was assigned after this script loaded.
        refreshCfg();

        const sidebar = buildSidebar();
        const main = document.createElement('div');
        main.className = 'shell-main';

        // Wrap existing children into .shell-content
        const content = document.createElement('div');
        content.className = 'shell-content';
        while (shell.firstChild) content.appendChild(shell.firstChild);
        main.appendChild(buildHeader());
        main.appendChild(buildHero());
        main.appendChild(content);
        main.appendChild(buildFooter());
        shell.appendChild(sidebar);
        shell.appendChild(main);

        attachScrollSpy();

        // Populate user email (top-right header) + department (hero subtitle)
        // once auth is ready.
        if (typeof firebase !== 'undefined' && firebase.auth) {
            firebase.auth().onAuthStateChanged(function (user) {
                const el = document.getElementById('shellUser');
                if (el) el.textContent = user ? user.email : '—';
                const heroUser = document.getElementById('shellHeroUser');
                if (heroUser) heroUser.textContent = '—';
                if (user && user.getIdTokenResult) {
                    user.getIdTokenResult(true).then(function (tokenResult) {
                        const claims = (tokenResult && tokenResult.claims) || {};
                        applyNavVisibility(claims.role || 'USER');
                        if (claims.tenant_id) applyTenantToSurveyLinks(claims.tenant_id);
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

    // Allow pages to update the header tenant info after auth resolves.
    global.updateShellTenant = function (title, meta) {
        cfg.tenantTitle = title || cfg.tenantTitle;
        cfg.tenantMeta = meta || cfg.tenantMeta;
        const tenantEl = document.querySelector('.shell-tenant');
        if (tenantEl) {
            const nameEl = tenantEl.querySelector('.tenant-name');
            const metaEl = tenantEl.querySelector('.tenant-meta');
            if (nameEl) nameEl.textContent = title || '';
            if (metaEl) metaEl.textContent = meta || '';
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
