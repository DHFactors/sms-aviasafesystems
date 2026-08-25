/* ============================================================================
   FILE: aviasdcps-router.js
   PATH: public/js/aviasdcps-router.js
   VERSION: 1.0.0-beta.1
   PURPOSE: aviaSDCPS Client-Side Dynamic Router — comprehensive 13-route registry
            mapping partials to PascalCase global controllers with DOM mounting,
            hash navigation, active link state handling, and error boundaries.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

const AviaSDCPSRouter = (function () {
  'use strict';

  // Master 13-module route registry
  const ROUTE_REGISTRY = {
    // Analytics & Operations Core
    'home': {
      template: 'views/home.html',
      controllerName: 'AviaSDCPSHome',
      title: 'Home Dashboard'
    },
    'sdc': {
      template: 'views/sdc.html',
      controllerName: 'AviaSDCPSSdc',
      title: 'Safety Data Collection (SDC)'
    },
    'hazard': {
      template: 'views/hazard.html',
      controllerName: 'AviaSDCPSHazard',
      title: 'Hazard Master Register'
    },
    'occurrence': {
      template: 'views/occurrence.html',
      controllerName: 'AviaSDCPSOccurrence',
      title: 'Occurrence Register (MOR/VSR)'
    },
    'hrc': {
      template: 'views/hrc.html',
      controllerName: 'AviaSDCPSHrc',
      title: 'High Risk Categories (HRC)'
    },
    'hazard-analysis': {
      template: 'views/hazard-analysis.html',
      controllerName: 'AviaSDCPSHazardAnalysis',
      title: 'Hazard Analysis & Root Cause Trends'
    },
    'occurrence-analysis': {
      template: 'views/occurrence-analysis.html',
      controllerName: 'AviaSDCPSOccurrenceAnalysis',
      title: 'Occurrence Analysis & Phase Breakdown'
    },

    // Safety Performance & Tools
    'spis': {
      template: 'views/spis.html',
      controllerName: 'AviaSDCPSSpis',
      title: 'Safety Performance Indicators & Targets'
    },
    'tools': {
      template: 'views/tools.html',
      controllerName: 'AviaSDCPSTools',
      title: 'Safety Risk Assessment & Bow-Tie Tools'
    },

    // Query, Reporting & Standards
    'data': {
      template: 'views/data.html',
      controllerName: 'AviaSDCPSData',
      title: 'Universal Safety Data Query Engine'
    },
    'reports': {
      template: 'views/reports.html',
      controllerName: 'AviaSDCPSReports',
      title: 'Executive Safety Performance Reporting'
    },
    'taxonomy': {
      template: 'views/taxonomy.html',
      controllerName: 'AviaSDCPSTaxonomy',
      title: 'ICAO ADREP & CAR-19 Taxonomy Management'
    },

    // Administration
    'preferences': {
      template: 'views/preferences.html',
      controllerName: 'AviaSDCPSPreferences',
      title: 'System Preferences & Matrix Calibration'
    }
  };

  /**
   * Loads view partial and initializes the corresponding controller.
   * @param {string} routeKey
   */
  async function navigate(routeKey) {
    const activeKey = ROUTE_REGISTRY[routeKey] ? routeKey : 'home';
    const config = ROUTE_REGISTRY[activeKey];
    const viewport = document.getElementById('aviasdcpsViewport');
    const titleEl = document.getElementById('currentViewTitle');

    if (titleEl) {
      titleEl.textContent = config.title;
    }

    document.querySelectorAll('#aviasdcpsSidebarNav .nav-item').forEach(link => {
      const match = link.getAttribute('data-route') === activeKey;
      link.classList.toggle('active', match);
    });

    if (!viewport) {
      console.error('[AviaSDCPSRouter] Viewport element #aviasdcpsViewport not found.');
      return;
    }

    try {
      viewport.innerHTML = `
        <div class="aviasdcps-card p-4 text-muted">
          <i class="fa-solid fa-spinner fa-spin"></i> Loading ${config.title}...
        </div>
      `;

      const response = await fetch(config.template);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: Failed to load ${config.template}`);
      }

      const htmlContent = await response.text();
      viewport.innerHTML = htmlContent;

      const controllerInstance = window[config.controllerName];
      if (controllerInstance && typeof controllerInstance.init === 'function') {
        controllerInstance.init();
      } else {
        console.warn(`[AviaSDCPSRouter] Controller ${config.controllerName} not initialized or missing .init() method.`);
      }
    } catch (error) {
      console.error(`[AviaSDCPSRouter] Navigation error for [${activeKey}]:`, error);
      viewport.innerHTML = `
        <div class="aviasdcps-card p-4">
          <h4 class="text-danger"><i class="fa-solid fa-triangle-exclamation"></i> View Load Failed</h4>
          <p class="text-muted">${error.message}</p>
        </div>
      `;
    }
  }

  /**
   * Resolves hash changes.
   */
  function handleHashChange() {
    const rawHash = window.location.hash.replace(/^#\/?/, '').trim();
    navigate(rawHash);
  }

  return {
    init() {
      window.addEventListener('hashchange', handleHashChange);
      handleHashChange();
    },
    goTo(routeKey) {
      window.location.hash = `#${routeKey}`;
    }
  };
})();

window.AviaSDCPSRouter = AviaSDCPSRouter;
document.addEventListener('DOMContentLoaded', () => AviaSDCPSRouter.init());
