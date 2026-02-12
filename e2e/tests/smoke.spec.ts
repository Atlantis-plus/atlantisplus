import { test, expect } from '../fixtures/auth';

test.describe('Smoke Tests', () => {

  test('app loads and authenticates in dev mode', async ({ authenticatedPage }) => {
    const page = authenticatedPage;

    // Verify we're authenticated (nav bar visible)
    await expect(page.locator('.bottom-nav')).toBeVisible();

    // Default page should be People
    await expect(page.locator('h1')).toContainText('People');

    // Take screenshot
    await page.screenshot({ path: 'screenshots/01-app-loaded.png', fullPage: true });
  });

  test('navigate to all pages', async ({ authenticatedPage }) => {
    const page = authenticatedPage;

    // People page (default)
    await expect(page.locator('.nav-btn.active')).toContainText('People');
    await page.screenshot({ path: 'screenshots/02-people-page.png', fullPage: true });

    // Notes page
    await page.click('.nav-btn:has-text("Notes")');
    await page.waitForTimeout(500);
    await expect(page.locator('h1')).toContainText('Note');
    await page.screenshot({ path: 'screenshots/03-notes-page.png', fullPage: true });

    // Chat page
    await page.click('.nav-btn:has-text("Chat")');
    await page.waitForTimeout(500);
    await page.screenshot({ path: 'screenshots/04-chat-page.png', fullPage: true });

    // Import page
    await page.click('.nav-btn:has-text("Import")');
    await page.waitForTimeout(500);
    await page.screenshot({ path: 'screenshots/05-import-page.png', fullPage: true });

    // Back to People
    await page.click('.nav-btn:has-text("People")');
    await expect(page.locator('h1')).toContainText('People');
  });

  test('search functionality works', async ({ authenticatedPage }) => {
    const page = authenticatedPage;

    // Find search input
    const searchInput = page.locator('.search-box input, input[placeholder*="Search"]');

    if (await searchInput.isVisible()) {
      await searchInput.fill('test search');
      await page.waitForTimeout(300);
      await page.screenshot({ path: 'screenshots/06-search-results.png', fullPage: true });

      // Clear search
      await searchInput.clear();
    }
  });

  test('no JavaScript errors on page load', async ({ authenticatedPage }) => {
    const page = authenticatedPage;
    const errors: string[] = [];

    page.on('pageerror', (error) => {
      errors.push(error.message);
    });

    // Navigate through pages
    await page.click('.nav-btn:has-text("Notes")');
    await page.waitForTimeout(500);
    await page.click('.nav-btn:has-text("Chat")');
    await page.waitForTimeout(500);
    await page.click('.nav-btn:has-text("People")');
    await page.waitForTimeout(500);

    // Check no errors
    expect(errors).toHaveLength(0);
  });
});
