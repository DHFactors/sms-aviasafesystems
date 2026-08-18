/* ============================================================================
   FILE: theme-toggle.js
   PATH: public/js/theme-toggle.js
   VERSION: 1.0.0
   DATE CREATED: 2026-08-18
   PURPOSE: Centralized dark/light theme controller for the AviaSAFE platform.
            - Loaded synchronously in <head> so the 'dark' class is applied to
              <html> BEFORE first paint (no flash / FOUC).
            - Persists the user's choice in localStorage 'theme'
              ('dark' | 'light') and falls back to the OS preference via
              prefers-color-scheme when nothing is stored.
            - Exposes window.toggleTheme() and window.AviaTheme helpers and
              dispatches a 'theme-changed' event on window + document after
              every switch.
            - Auto-injects an accessible toggle button into the page header
              (or a fixed floating button on headerless pages) and keeps its
              moon/sun icon in sync with the active theme.
            - Recolors Chart.js v4 canvases (grid / ticks / legend / tooltip)
              whenever the theme changes.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

(function () {
    'use strict';

    var STORAGE_KEY = 'theme';
    var isDark = null;

    function readStored() {
        try {
            var v = localStorage.getItem(STORAGE_KEY);
            if (v === 'dark' || v === 'light') return v;
        } catch (e) { /* private mode / unavailable */ }
        return null;
    }

    function systemPrefersDark() {
        try {
            return window.matchMedia &&
                window.matchMedia('(prefers-color-scheme: dark)').matches;
        } catch (e) {
            return false;
        }
    }

    function apply(theme) {
        isDark = theme === 'dark';
        var root = document.documentElement;
        if (isDark) root.classList.add('dark');
        else root.classList.remove('dark');
        root.setAttribute('data-theme', theme);
        syncButtons();
        return isDark;
    }

    // Apply before first paint: stored choice wins, else OS preference.
    var stored = readStored();
    var initial = stored || (systemPrefersDark() ? 'dark' : 'light');
    apply(initial);

    function getTheme() {
        return isDark ? 'dark' : 'light';
    }

    function syncButtons() {
        var showSun = isDark; /* show sun while dark (switch to light) */
        document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
            var label = isDark ? 'Switch to light mode' : 'Switch to dark mode';
            btn.setAttribute('aria-label', label);
            btn.setAttribute('title', label);
            btn.querySelectorAll('.fa-sun, .fa-moon').forEach(function (icon) {
                var isSun = icon.classList.contains('fa-sun');
                icon.style.display = (isSun === showSun) ? '' : 'none';
            });
        });
    }

    function toggleTheme() {
        var next = isDark ? 'light' : 'dark';
        apply(next);
        try { localStorage.setItem(STORAGE_KEY, next); } catch (e) { /* ignore */ }
        var detail = { theme: next, dark: isDark };
        try {
            window.dispatchEvent(new CustomEvent('theme-changed', { detail: detail }));
            document.dispatchEvent(new CustomEvent('theme-changed', { detail: detail }));
        } catch (e) { /* older browsers */ }
        recolorCharts();
        return next;
    }
    window.toggleTheme = toggleTheme;

    // Chart.js v4: recolour gridlines, tick labels, legend and tooltips so
    // canvas charts follow the active theme without re-creating them.
    function recolorCharts() {
        if (typeof Chart === 'undefined' || typeof Chart.getChart !== 'function') return;
        var grid = isDark ? 'rgba(148,163,184,0.14)' : 'rgba(15,23,42,0.08)';
        var tick = isDark ? '#94a3b8' : '#475569';
        var legend = isDark ? '#cbd5e1' : '#334155';
        var tooltipBg = isDark ? 'rgba(11,18,32,0.95)' : 'rgba(255,255,255,0.97)';
        var tooltipText = isDark ? '#e2e8f0' : '#0f172a';
        var tooltipBorder = isDark ? 'rgba(148,163,184,0.4)' : 'rgba(226,232,240,1)';
        document.querySelectorAll('canvas').forEach(function (canvas) {
            var chart = Chart.getChart(canvas);
            if (!chart) return;
            var scales = (chart.options && chart.options.scales) || {};
            Object.keys(scales).forEach(function (key) {
                var s = scales[key];
                if (!s) return;
                s.grid = s.grid || {};
                s.grid.color = grid;
                s.ticks = s.ticks || {};
                s.ticks.color = tick;
            });
            var pl = chart.options.plugins || {};
            if (pl.legend) {
                pl.legend.labels = pl.legend.labels || {};
                pl.legend.labels.color = legend;
            }
            if (pl.tooltip) {
                pl.tooltip.backgroundColor = tooltipBg;
                pl.tooltip.titleColor = tooltipText;
                pl.tooltip.bodyColor = tooltipText;
                pl.tooltip.borderColor = tooltipBorder;
            }
            chart.update();
        });
    }

    window.AviaTheme = {
        getTheme: getTheme,
        isDark: function () { return isDark; },
        recolorCharts: recolorCharts,
    };

    /* ── Toggle button injection ─────────────────────────────────────────── */

    function makeButton() {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'theme-toggle';
        btn.setAttribute('data-theme-toggle', '');
        var moon = document.createElement('i');
        moon.className = 'fa-solid fa-moon';
        var sun = document.createElement('i');
        sun.className = 'fa-solid fa-sun';
        btn.appendChild(moon);
        btn.appendChild(sun);
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            toggleTheme();
        });
        return btn;
    }

    function findTarget() {
        var c = document.querySelector('[data-theme-toggle-container]');
        if (c) return c;
        var hc = document.querySelector('.app-header .header-content');
        if (hc) return hc;
        var sa = document.querySelector('.shell-actions');
        if (sa) return sa;
        var th = document.querySelector('header');
        if (th) return th;
        var tb = document.querySelector('.topbar');
        if (tb) return tb;
        return null;
    }

    function inject() {
        if (document.querySelector('[data-theme-toggle]')) { syncButtons(); return; }
        var target = findTarget();
        var btn = makeButton();
        if (target) {
            target.appendChild(btn);
        } else {
            btn.classList.add('theme-toggle--floating');
            document.body.appendChild(btn);
        }
        syncButtons();
    }

    function onReady(fn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn);
        } else {
            fn();
        }
    }

    onReady(function () {
        inject();
        recolorCharts();
    });

    // The shell header is built dynamically by shell.js — inject the toggle
    // once it appears (and never duplicate an already-present button).
    if (window.MutationObserver) {
        var observer = new MutationObserver(function () {
            if (document.querySelector('[data-theme-toggle]')) return;
            if (document.querySelector('.shell-actions') || document.querySelector('header')) {
                inject();
            }
        });
        onReady(function () {
            observer.observe(document.documentElement, { childList: true, subtree: true });
        });
    }

    // Follow the OS preference only while the user hasn't made an explicit choice.
    try {
        window.matchMedia('(prefers-color-scheme: dark)')
            .addEventListener('change', function (ev) {
                if (readStored()) return;
                apply(ev.matches ? 'dark' : 'light');
            });
    } catch (e) { /* unsupported */ }
})();