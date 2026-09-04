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

    // ---- Header navigation: [Home] + direct links (no dropdowns) ----
    const NAV_ITEMS = [
        { label: 'SMS Maturity', href: '/dashboard/sms-maturity.html' },
        { label: 'Risk & Trends', href: '/risk-trends.html' },
        { label: 'Top Hazards', href: '/top-hazards.html' },
        { label: 'SPI/SPT', href: '/dashboard/spi-dashboard.html' },
        { label: 'Administration', href: '/administration.html' }
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
            const a = document.createElement('a');
            a.href = item.href;
            a.className = 'nav-link';
            a.textContent = item.label;
            nav.appendChild(a);
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

        const feedbackBtn = document.createElement('button');
        feedbackBtn.type = 'button';
        feedbackBtn.className = 'feedback-btn';
        feedbackBtn.textContent = '\uD83D\uDCAC Send Feedback';
        feedbackBtn.setAttribute('aria-label', 'Send feedback');
        feedbackBtn.addEventListener('click', function () {
            global.openFeedbackModal();
        });
        content.appendChild(feedbackBtn);

        footer.appendChild(content);
        return footer;
    }

    function buildFeedbackModal() {
        const modal = document.createElement('div');
        modal.className = 'feedback-modal';
        modal.id = 'feedbackModal';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-labelledby', 'feedbackModalTitle');

        modal.innerHTML = `
            <div class="feedback-modal-content">
                <button class="feedback-close" aria-label="Close feedback modal">&times;</button>
                <h2 id="feedbackModalTitle">Send Feedback</h2>
                <form id="feedbackForm">
                    <div class="feedback-rating">
                        <label>Rating</label>
                        <div class="stars" role="radiogroup" aria-label="Rating">
                            <button type="button" class="star" data-rating="1" aria-label="1 star">\u2605</button>
                            <button type="button" class="star" data-rating="2" aria-label="2 stars">\u2605</button>
                            <button type="button" class="star" data-rating="3" aria-label="3 stars">\u2605</button>
                            <button type="button" class="star" data-rating="4" aria-label="4 stars">\u2605</button>
                            <button type="button" class="star" data-rating="5" aria-label="5 stars">\u2605</button>
                        </div>
                        <input type="hidden" name="rating" id="feedbackRating" value="0">
                    </div>
                    <div class="feedback-field">
                        <label for="feedbackSubject">Subject</label>
                        <input type="text" id="feedbackSubject" name="subject" placeholder="What is this about?" required maxlength="120">
                    </div>
                    <div class="feedback-field">
                        <label for="feedbackMessage">Message</label>
                        <textarea id="feedbackMessage" name="message" placeholder="Your feedback..." required maxlength="2000" rows="5"></textarea>
                    </div>
                    <div class="feedback-actions">
                        <button type="button" class="feedback-btn-cancel">Cancel</button>
                        <button type="submit" class="feedback-btn-submit">Send</button>
                    </div>
                </form>
            </div>
        `;
        return modal;
    }

    let feedbackRating = 0;

    global.openFeedbackModal = function () {
        const modal = document.getElementById('feedbackModal');
        if (modal) {
            modal.classList.add('open');
            document.body.style.overflow = 'hidden';
            const firstInput = modal.querySelector('input, textarea');
            if (firstInput) firstInput.focus();
        }
    };

    global.closeFeedbackModal = function () {
        const modal = document.getElementById('feedbackModal');
        if (modal) {
            modal.classList.remove('open');
            document.body.style.overflow = '';
            resetFeedbackForm();
        }
    };

    global.setRating = function (rating) {
        feedbackRating = rating;
        const ratingInput = document.getElementById('feedbackRating');
        if (ratingInput) ratingInput.value = rating;
        document.querySelectorAll('.feedback-modal .star').forEach(function (star, idx) {
            star.classList.toggle('filled', idx < rating);
            star.setAttribute('aria-pressed', idx < rating);
        });
    };

    function resetFeedbackForm() {
        feedbackRating = 0;
        const form = document.getElementById('feedbackForm');
        if (form) form.reset();
        document.querySelectorAll('.feedback-modal .star').forEach(function (star) {
            star.classList.remove('filled');
            star.setAttribute('aria-pressed', 'false');
        });
        const ratingInput = document.getElementById('feedbackRating');
        if (ratingInput) ratingInput.value = '0';
    }

    global.submitFeedback = function (e) {
        e.preventDefault();
        const form = e.target;
        const formData = new FormData(form);
        const data = {
            rating: parseInt(formData.get('rating')) || 0,
            subject: formData.get('subject') || '',
            message: formData.get('message') || '',
            email: getUserEmail() || 'Unknown',
            page: window.location.pathname,
            timestamp: new Date().toISOString()
        };

        if (data.rating === 0) {
            alert('Please select a rating');
            return;
        }

        const submitBtn = form.querySelector('.feedback-btn-submit');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Sending...';
        }

        fetch('/api/send-feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        })
            .then(function (res) { return res.json(); })
            .then(function (result) {
                if (result.success) {
                    alert('Thank you for your feedback!');
                    global.closeFeedbackModal();
                } else {
                    throw new Error(result.error || 'Failed to send feedback');
                }
            })
            .catch(function (err) {
                console.error('Feedback error:', err);
                alert('Failed to send feedback. Please try again later.');
            })
            .finally(function () {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Send';
                }
            });
    };

    function bindFeedbackModalEvents() {
        const modal = document.getElementById('feedbackModal');
        if (!modal) return;

        // Close button
        const closeBtn = modal.querySelector('.feedback-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', global.closeFeedbackModal);
        }

        // Click overlay to close
        modal.addEventListener('click', function (e) {
            if (e.target === modal) global.closeFeedbackModal();
        });

        // Star rating
        modal.querySelectorAll('.star').forEach(function (star) {
            star.addEventListener('click', function () {
                global.setRating(parseInt(this.dataset.rating, 10));
            });
            star.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    global.setRating(parseInt(this.dataset.rating, 10));
                }
            });
        });

        // Form submit
        const form = modal.querySelector('#feedbackForm');
        if (form) {
            form.addEventListener('submit', global.submitFeedback);
        }

        // Escape key
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && modal.classList.contains('open')) {
                global.closeFeedbackModal();
            }
        });
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

        // Append feedback modal to body
        if (!document.getElementById('feedbackModal')) {
            document.body.appendChild(buildFeedbackModal());
            bindFeedbackModalEvents();
        }

        setActiveNav();

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