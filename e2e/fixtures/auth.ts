import { test as base, expect, Page } from '@playwright/test';

// Extended test with authenticated page fixture
export const test = base.extend<{ authenticatedPage: Page }>({
  authenticatedPage: async ({ page }, use) => {
    // Capture console logs for debugging
    page.on('console', msg => {
      if (msg.text().includes('[DEV]') || msg.text().includes('Failed') || msg.text().includes('error')) {
        console.log(`[BROWSER] ${msg.type()}: ${msg.text()}`);
      }
    });

    // Navigate to app - dev mode auth will trigger automatically
    await page.goto('/');

    // Wait a bit for auth to complete
    await page.waitForTimeout(3000);

    // Wait for authentication to complete (nav bar appears)
    try {
      await page.waitForSelector('.bottom-nav', { timeout: 30000 });
      console.log('[AUTH] Successfully authenticated in dev mode');
    } catch (e) {
      // Take screenshot on auth failure for debugging
      await page.screenshot({ path: 'screenshots/auth-failure.png' });
      console.error('[AUTH] Authentication failed - check backend is running with TEST_MODE_ENABLED=true');
      throw e;
    }

    await use(page);
  },
});

export { expect };
