/* ============================================================================
   FILE: tests/e2e/tenant-sms-e2e.spec.ts
   PATH: backend/tests/e2e/tenant-sms-e2e.spec.ts
   VERSION: 1.0.0-beta.1
   PURPOSE: Playwright E2E smoke & role isolation tests for the tenant SMS
            dashboard and CAAN regulator oversight module. Validates:
            - Tenant sessions can access #tenant-dashboard
            - Tenant sessions are intercepted on #caan-oversight
            - Regulator sessions can access #caan-oversight
            - Regulator sessions cannot view tenant CAPA registers
            - 5x5 risk matrix and Chart.js canvases mount correctly
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

import { test, expect } from '@playwright/test';

// ─── Helpers ───────────────────────────────────────────────────────────────────

const BASE = 'aviasdcps.html';

interface MockUser {
  uid: string;
  email: string;
  role: string;
  tenant_id?: string;
}

const TENANT_USER: MockUser = {
  uid: 'uid-tenant-e2e',
  email: 'safety@fishtail.com.np',
  role: 'AIRLINE_ADMIN',
  tenant_id: 'fishtail-air',
};

const REGULATOR_USER: MockUser = {
  uid: 'uid-regulator-e2e',
  email: 'caan@caanepal.gov.np',
  role: 'CAAN_SMD',
};

async function mockAuthAndApi(page: any, user: MockUser) {
  // Mock Firebase auth — intercept verifyCustomToken / token endpoints
  await page.route('**/identitytoolkit.googleapis.com/**', async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ idToken: 'mock-token-e2e', localId: user.uid }),
    });
  });

  // Mock Firestore calls for any tenant/regulator data
  await page.route('**/firestore.googleapis.com/**', async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ fields: {} }),
    });
  });

  // Mock backend API calls
  await page.route('**/api/v1/**', async (route: any) => {
    const url = route.request().url();

    // Tenant SMS summary
    if (url.includes('monthly-summary')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          report: {
            tenant_id: 'fishtail-air',
            operator_name: 'Fishtail Air',
            reporting_year: 2026,
            reporting_month: 8,
            total_hazards: 5,
            open_hazards: 3,
            intolerable_risks: 1,
            safety_reports_submitted: 8,
            open_capas: [
              { source_reference: 'CAN-001', description: 'Brake inspection', responsible_post_holder: 'CP', implementation_status: 'OPEN', priority: 'HIGH' },
            ],
            risk_heatmap: [
              { severity: '5_CATASTROPHIC', likelihood: 'A_FREQUENT', hazard_count: 2, tolerability: 'INTOLERABLE' },
              { severity: '4_HAZARDOUS', likelihood: 'B_OCCASIONAL', hazard_count: 1, tolerability: 'TOLERABLE_WITH_MITIGATION' },
              { severity: '3_MAJOR', likelihood: 'C_REMOTE', hazard_count: 0, tolerability: 'ACCEPTABLE' },
            ],
            spi_metrics: [],
            insights: ['Test insight'],
            recommendations: [],
          },
        }),
      });
      return;
    }

    // Tenant audit logs
    if (url.includes('audit-logs')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, tenant_id: 'fishtail-air', count: 0, logs: [] }),
      });
      return;
    }

    // Default fallback
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], rows: [], total: 0 }),
    });
  });

  // Inject mock user into localStorage so the SPA sees them as authenticated
  await page.addInitScript((u: MockUser) => {
    localStorage.setItem('aviasafe_user', JSON.stringify({
      uid: u.uid,
      email: u.email,
      role: u.role,
      tenant_id: u.tenant_id || null,
    }));
    localStorage.setItem('aviasafe_role', u.role);
  }, user);
}

// ─── Tests: Tenant Dashboard ──────────────────────────────────────────────────

test.describe('Tenant SMS Dashboard — Role Isolation', () => {
  const consoleErrors: string[] = [];

  test.beforeEach(async ({ page }) => {
    consoleErrors.length = 0;
    page.on('console', (msg: any) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', (err: any) => consoleErrors.push(err.message));
  });

  test('Tenant session can navigate to #tenant-dashboard and see dashboard title', async ({ page }) => {
    await mockAuthAndApi(page, TENANT_USER);
    await page.goto(`${BASE}#home`);
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => { window.location.hash = '#tenant-dashboard'; });
    await page.waitForTimeout(500);

    await expect(page).toHaveURL(/#tenant-dashboard$/);

    const title = page.locator('#currentViewTitle');
    await expect(title).toHaveText('Tenant SMS Dashboard');
  });

  test('Tenant dashboard sidebar nav item is visible for operator role', async ({ page }) => {
    await mockAuthAndApi(page, TENANT_USER);
    await page.goto(`${BASE}#home`);
    await page.waitForLoadState('domcontentloaded');

    const navItem = page.locator('#aviasdcpsSidebarNav .nav-item[data-route="tenant-dashboard"]');
    await expect(navItem).toBeAttached();
  });

  test('Tenant dashboard controller is initialized on window', async ({ page }) => {
    await mockAuthAndApi(page, TENANT_USER);
    await page.goto(`${BASE}#home`);
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => { window.location.hash = '#tenant-dashboard'; });
    await page.waitForTimeout(600);

    const isLoaded = await page.evaluate(() => {
      return typeof (window as any).AviaSDCPSTenantDashboard !== 'undefined'
        && typeof (window as any).AviaSDCPSTenantDashboard.init === 'function';
    });
    expect(isLoaded).toBeTruthy();
  });

  test('Tenant dashboard viewport renders without error boundaries', async ({ page }) => {
    await mockAuthAndApi(page, TENANT_USER);
    await page.goto(`${BASE}#home`);
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => { window.location.hash = '#tenant-dashboard'; });
    await page.waitForTimeout(600);

    const viewport = page.locator('#aviasdcpsViewport');
    await expect(viewport).toBeVisible();
    const errorBoundaryCount = await viewport.locator('.text-danger').count();
    expect(errorBoundaryCount).toBe(0);
  });

  test('Tenant session navigating to #caan-oversight is redirected back', async ({ page }) => {
    await mockAuthAndApi(page, TENANT_USER);
    await page.goto(`${BASE}#home`);
    await page.waitForLoadState('domcontentloaded');

    // Attempt to navigate to CAAN oversight (role-restricted to regulator/auditor)
    await page.evaluate(() => { window.location.hash = '#caan-oversight'; });
    await page.waitForTimeout(800);

    // Should either stay on home or show an access denied — not mount caan-oversight
    const url = page.url();
    const isOnCaan = url.includes('#caan-oversight');
    // If router blocks, we should not be on caan-oversight
    // OR the viewport should show an access error
    const viewportText = await page.locator('#aviasdcpsViewport').textContent().catch(() => '');
    const blocked = !isOnCaan || viewportText.includes('Access Denied') || viewportText.includes('Not Authorized') || viewportText.includes('Access Restricted');
    expect(blocked).toBeTruthy();
  });
});

// ─── Tests: CAAN Oversight — Regulator Access ─────────────────────────────────

test.describe('CAAN SSP Oversight — Regulator Access', () => {
  const consoleErrors: string[] = [];

  test.beforeEach(async ({ page }) => {
    consoleErrors.length = 0;
    page.on('console', (msg: any) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', (err: any) => consoleErrors.push(err.message));
  });

  test('Regulator session can navigate to #caan-oversight', async ({ page }) => {
    await mockAuthAndApi(page, REGULATOR_USER);
    await page.goto(`${BASE}#home`);
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => { window.location.hash = '#caan-oversight'; });
    await page.waitForTimeout(600);

    await expect(page).toHaveURL(/#caan-oversight$/);

    const title = page.locator('#currentViewTitle');
    await expect(title).toHaveText('CAAN SSP Oversight Dashboard');
  });

  test('Regulator CAAN oversight controller initializes', async ({ page }) => {
    await mockAuthAndApi(page, REGULATOR_USER);
    await page.goto(`${BASE}#home`);
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => { window.location.hash = '#caan-oversight'; });
    await page.waitForTimeout(600);

    const isLoaded = await page.evaluate(() => {
      return typeof (window as any).AviaSDCPSCaanOversight !== 'undefined'
        && typeof (window as any).AviaSDCPSCaanOversight.init === 'function';
    });
    expect(isLoaded).toBeTruthy();
  });

  test('Regulator session navigating to #tenant-dashboard is blocked', async ({ page }) => {
    await mockAuthAndApi(page, REGULATOR_USER);
    await page.goto(`${BASE}#home`);
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => { window.location.hash = '#tenant-dashboard'; });
    await page.waitForTimeout(800);

    const url = page.url();
    const isOnTenant = url.includes('#tenant-dashboard');
    const viewportText = await page.locator('#aviasdcpsViewport').textContent().catch(() => '');
    const blocked = !isOnTenant || viewportText.includes('Access Denied') || viewportText.includes('Not Authorized') || viewportText.includes('Access Restricted');
    expect(blocked).toBeTruthy();
  });
});

// ─── Tests: DOM Mounting — 5x5 Risk Matrix & Chart.js Canvases ────────────────

test.describe('Tenant Dashboard — DOM Mounting', () => {
  test.beforeEach(async ({ page }) => {
    page.on('pageerror', () => {});
  });

  test('5x5 risk matrix container renders on tenant dashboard', async ({ page }) => {
    await mockAuthAndApi(page, TENANT_USER);
    await page.goto(`${BASE}#home`);
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => { window.location.hash = '#tenant-dashboard'; });
    await page.waitForTimeout(800);

    // The 5x5 matrix is rendered as a grid with data-severity and data-likelihood attrs
    const matrixCells = page.locator('#tenantRiskMatrix .matrix-cell');
    const count = await matrixCells.count();
    expect(count).toBeGreaterThanOrEqual(25);
  });

  test('Chart.js canvas elements mount on tenant dashboard', async ({ page }) => {
    await mockAuthAndApi(page, TENANT_USER);
    await page.goto(`${BASE}#home`);
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => { window.location.hash = '#tenant-dashboard'; });
    await page.waitForTimeout(1000);

    // Chart.js renders into <canvas> elements
    const canvases = page.locator('#tenant-dashboard canvas, #aviasdcpsViewport canvas');
    const count = await canvases.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('CAPA register table renders on tenant dashboard', async ({ page }) => {
    await mockAuthAndApi(page, TENANT_USER);
    await page.goto(`${BASE}#home`);
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => { window.location.hash = '#tenant-dashboard'; });
    await page.waitForTimeout(800);

    const table = page.locator('#tenant-dashboard table, #aviasdcpsViewport table');
    const count = await table.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('KPI strip renders on tenant dashboard', async ({ page }) => {
    await mockAuthAndApi(page, TENANT_USER);
    await page.goto(`${BASE}#home`);
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => { window.location.hash = '#tenant-dashboard'; });
    await page.waitForTimeout(800);

    // KPI strip uses .kpi-card or .kpi-strip class
    const kpis = page.locator('#tenant-dashboard .kpi-card, #aviasdcpsViewport .kpi-card');
    const count = await kpis.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });
});

// ─── Tests: CAAN Oversight — DOM Mounting ──────────────────────────────────────

test.describe('CAAN Oversight — DOM Mounting', () => {
  test('CAAN oversight controller renders without errors', async ({ page }) => {
    await mockAuthAndApi(page, REGULATOR_USER);
    await page.goto(`${BASE}#home`);
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => { window.location.hash = '#caan-oversight'; });
    await page.waitForTimeout(800);

    const viewport = page.locator('#aviasdcpsViewport');
    await expect(viewport).toBeVisible();
    const errorBoundary = viewport.locator('.text-danger:has-text("View Load Failed")');
    await expect(errorBoundary).toHaveCount(0);
  });

  test('CAAN oversight sidebar nav item exists for regulator', async ({ page }) => {
    await mockAuthAndApi(page, REGULATOR_USER);
    await page.goto(`${BASE}#home`);
    await page.waitForLoadState('domcontentloaded');

    const navItem = page.locator('#aviasdcpsSidebarNav .nav-item[data-route="caan-oversight"]');
    await expect(navItem).toBeAttached();
  });
});

// ─── Tests: Zero Console Errors ────────────────────────────────────────────────

test.describe('Cross-Module — Zero Fatal Console Errors', () => {
  const fatalErrors: string[] = [];

  test.beforeEach(async ({ page }) => {
    fatalErrors.length = 0;
    page.on('pageerror', (err: any) => fatalErrors.push(err.message));
  });

  test('No uncaught JS errors when navigating tenant dashboard', async ({ page }) => {
    await mockAuthAndApi(page, TENANT_USER);
    await page.goto(`${BASE}#home`);
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => { window.location.hash = '#tenant-dashboard'; });
    await page.waitForTimeout(1000);

    const errors = fatalErrors.filter(e => !e.includes('favicon'));
    expect(errors).toEqual([]);
  });

  test('No uncaught JS errors when navigating CAAN oversight', async ({ page }) => {
    await mockAuthAndApi(page, REGULATOR_USER);
    await page.goto(`${BASE}#home`);
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => { window.location.hash = '#caan-oversight'; });
    await page.waitForTimeout(1000);

    const errors = fatalErrors.filter(e => !e.includes('favicon'));
    expect(errors).toEqual([]);
  });
});
