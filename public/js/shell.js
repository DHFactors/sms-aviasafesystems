/* ============================================================================
   FILE: shell.js
   PATH: public/js/shell.js
   VERSION: 1.0.0
   PURPOSE: Shared dashboard shell. Renders the fixed left sidebar navigation,
            the top header (brand + tenant/regulator info + user + logout), a
            landing-page style footer, and scroll-spy active states. Used by
            all tenant dashboards and the CAAN dashboard.
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
        foot.textContent = 'ICAO Annex 19 · Doc 9859 · Doc 10951';
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

    // Uniform top section: centered tenant name (title) + logged-in user email.
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
        user.textContent = '—';
        hero.appendChild(title);
        hero.appendChild(user);
        return hero;
    }

    function buildFooter() {
        const footer = document.createElement('footer');
        footer.className = 'shell-footer';
        footer.id = 'shellFooter';

        const container = document.createElement('div');
        container.style.cssText = 'max-width:1200px;margin:0 auto;padding:0 1rem;';

        const links = document.createElement('div');
        links.className = 'footer-links';
        const linkDefs = cfg.links || [
            { href: '/', label: 'Home' },
            { href: '/survey/', label: 'Survey' },
            { href: '/login.html', label: 'Login' },
            { href: '#', label: 'Privacy Policy' },
            { href: '#', label: 'Terms of Service' },
            { href: '#', label: 'Contact' },
        ];
        linkDefs.forEach(function (l, idx) {
            const a = document.createElement('a');
            a.href = l.href;
            a.textContent = l.label;
            links.appendChild(a);
            if (idx < linkDefs.length - 1) {
                const sep = document.createElement('span');
                sep.className = 'footer-divider';
                sep.textContent = '|';
                sep.style.margin = '0 0.25rem';
                links.appendChild(sep);
            }
        });
        container.appendChild(links);

        const p1 = document.createElement('p');
        p1.style.margin = '0.5rem 0 0';
        p1.innerHTML = 'A project by <strong>Ghanshyam Acharya</strong>.';
        container.appendChild(p1);

        const p2 = document.createElement('p');
        p2.style.margin = '0.25rem 0 0';
        p2.textContent = '© ' + new Date().getFullYear() + ' AviaSAFEsystem. All rights reserved.';
        container.appendChild(p2);

        const p3 = document.createElement('p');
        p3.style.margin = '0.25rem 0 0';
        p3.textContent = 'ICAO Annex 19 · Doc 9859 · Doc 10951 — Safety Intelligence Platform';
        container.appendChild(p3);

        footer.appendChild(container);
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

        // Populate user email once auth is ready
        if (typeof firebase !== 'undefined' && firebase.auth) {
            firebase.auth().onAuthStateChanged(function (user) {
                const el = document.getElementById('shellUser');
                if (el && user) el.textContent = user.email;
                const heroUser = document.getElementById('shellHeroUser');
                if (heroUser) heroUser.textContent = user ? user.email : '—';
                if (user && user.getIdTokenResult) {
                    user.getIdTokenResult(true).then(function (tokenResult) {
                        const claims = (tokenResult && tokenResult.claims) || {};
                        if (claims.tenant_id) applyTenantToSurveyLinks(claims.tenant_id);
                    }).catch(function () {});
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
