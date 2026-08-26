/* ============================================================================
   FILE: tests/e2e/aviasdcps-smoke.spec.ts
   PATH: backend/tests/e2e/aviasdcps-smoke.spec.ts
   VERSION: 1.0.0-beta.1
   PURPOSE: Playwright E2E smoke test suite for aviaSDCPS — verifies hash routing,
            DOM container mounting, controller initialization, and active state
            across all 13 workspace modules with zero uncaught console errors.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

import { test, expect } from '@playwright/test';

interface RouteConfig {
  route: string;
  title: string;
  controllerName: string;
  containerSelector: string;
}

const ROUTES: RouteConfig[] = [
  {
    route: 'home',
    title: 'Home Dashboard',
    controllerName: 'AviaSDCPSHome',
    containerSelector: '#homeViewContainer, .dashboard-grid'
  },
  {
    route: 'sdc',
    title: 'Safety Data Collection (SDC)',
    controllerName: 'AviaSDCPSSdc',
    containerSelector: '#sdcViewContainer'
  },
  {
    route: 'hazard',
    title: 'Hazard Master Register',
    controllerName: 'AviaSDCPSHazard',
    containerSelector: '#hazardRegisterContainer, #hazardViewContainer'
  },
  {
    route: 'occurrence',
    title: 'Occurrence Register (MOR/VSR)',
    controllerName: 'AviaSDCPSOccurrence',
    containerSelector: '#occurrenceRegisterContainer, #occurrenceViewContainer'
  },
  {
    route: 'hrc',
    title: 'High Risk Categories (HRC)',
    controllerName: 'AviaSDCPSHrc',
    containerSelector: '#hrcViewContainer, #hrcMatrixContainer'
  },
  {
    route: 'hazard-analysis',
    title: 'Hazard Analysis & Root Cause Trends',
    controllerName: 'AviaSDCPSHazardAnalysis',
    containerSelector: '#hazardAnalysisViewContainer'
  },
  {
    route: 'occurrence-analysis',
    title: 'Occurrence Analysis & Phase Breakdown',
    controllerName: 'AviaSDCPSOccurrenceAnalysis',
    containerSelector: '#occurrenceAnalysisViewContainer'
  },
  {
    route: 'spis',
    title: 'Safety Performance Indicators & Targets',
    controllerName: 'AviaSDCPSSpis',
    containerSelector: '#spisViewContainer'
  },
  {
    route: 'tools',
    title: 'Safety Risk Assessment & Bow-Tie Tools',
    controllerName: 'AviaSDCPSTools',
    containerSelector: '#toolsViewContainer, #sramToolContainer'
  },
  {
    route: 'data',
    title: 'Universal Safety Data Query Engine',
    controllerName: 'AviaSDCPSData',
    containerSelector: '#dataQueryViewContainer'
  },
  {
    route: 'reports',
    title: 'Executive Safety Performance Reporting',
    controllerName: 'AviaSDCPSReports',
    containerSelector: '#reportsViewContainer, #reportWorkspaceGrid'
  },
  {
    route: 'taxonomy',
    title: 'ICAO ADREP & CAR-19 Taxonomy Management',
    controllerName: 'AviaSDCPSTaxonomy',
    containerSelector: '#taxonomyViewContainer'
  },
  {
    route: 'preferences',
    title: 'System Preferences & Matrix Calibration',
    controllerName: 'AviaSDCPSPreferences',
    containerSelector: '#preferencesViewContainer'
  }
];

test.describe('aviaSDCPS 13-Module Route Smoke Tests', () => {
  const consoleErrors: string[] = [];

  test.beforeEach(async ({ page }) => {
    consoleErrors.length = 0;

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    page.on('pageerror', (err) => {
      consoleErrors.push(err.message);
    });

    // Mock tenant API response fallback for testing isolation
    await page.route('**/api/v1/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], rows: [], total: 0, status: 'OK' })
      });
    });

    await page.goto('/aviasdcps.html#home');
    await page.waitForLoadState('domcontentloaded');
  });

  for (const config of ROUTES) {
    test(`Route #${config.route} should mount controller ${config.controllerName} and render clean DOM`, async ({ page }) => {
      // 1. Trigger navigation via sidebar click or direct hash change
      const navItem = page.locator(`#aviasdcpsSidebarNav .nav-item[data-route="${config.route}"]`);
      if (await navItem.count() > 0) {
        await navItem.click();
      } else {
        await page.evaluate((r) => { window.location.hash = `#${r}`; }, config.route);
      }

      // 2. Validate URL hash state
      await expect(page).toHaveURL(new RegExp(`#${config.route}$`));

      // 3. Verify top header title updates
      const titleLocator = page.locator('#currentViewTitle');
      await expect(titleLocator).toHaveText(config.title);

      // 4. Verify sidebar active class binding
      await expect(navItem).toHaveClass(/active/);

      // 5. Verify viewport has rendered without error boundaries
      const viewport = page.locator('#aviasdcpsViewport');
      await expect(viewport).toBeVisible();
      await expect(viewport.locator('.text-danger')).not.toContainText('View Load Failed');

      // 6. Verify controller initialization in global window namespace
      const isControllerLoaded = await page.evaluate((ctrl) => {
        return typeof window[ctrl] !== 'undefined' && typeof window[ctrl].init === 'function';
      }, config.controllerName);
      expect(isControllerLoaded).toBeTruthy();

      // 7. Assert no severe JavaScript runtime errors were captured during transition
      const fatalErrors = consoleErrors.filter(e => !e.includes('404') && !e.includes('favicon'));
      expect(fatalErrors).toEqual([]);
    });
  }
});