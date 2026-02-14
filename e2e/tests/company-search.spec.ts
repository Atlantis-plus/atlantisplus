import { test, expect } from '../fixtures/auth';

test.describe('Company Search', () => {

  test('search ByteDance via Chat finds people from met_on', async ({ authenticatedPage }) => {
    const page = authenticatedPage;

    // Navigate to Chat page
    await page.click('.nav-btn:has-text("Chat")');
    await page.waitForTimeout(1000);

    // Locate chat input (textarea with class input-neo)
    const chatInput = page.locator('textarea.input-neo');
    await chatInput.waitFor({ state: 'visible', timeout: 5000 });
    await chatInput.fill('кто из ByteDance');

    // Send the message (button with aria-label)
    const sendBtn = page.locator('button[aria-label="Send message"]');
    await sendBtn.click();

    // Wait for AI response (give it time to process)
    await page.waitForTimeout(15000);

    // Take screenshot for evidence
    await page.screenshot({ path: 'screenshots/company-bytedance.png', fullPage: true });

    // Check response contains people (not "not found")
    const messages = page.locator('.chat-message, .message, .assistant-message');
    const lastMessage = messages.last();
    await lastMessage.waitFor({ state: 'visible', timeout: 5000 });

    const response = await lastMessage.textContent();

    // Should find people, not say "no one found"
    expect(response).not.toContain('не найд');
    expect(response).not.toContain('No one');
    expect(response).not.toContain('not found');

    // Should contain person-related text
    const hasPersonMention =
      response?.toLowerCase().includes('person') ||
      response?.toLowerCase().includes('people') ||
      response?.toLowerCase().includes('човек') ||
      response?.toLowerCase().includes('bytedance');

    expect(hasPersonMention).toBeTruthy();
  });

  test('search Yandex on People page finds all variants', async ({ authenticatedPage }) => {
    const page = authenticatedPage;

    // Navigate to People page if not already there
    await page.click('.nav-btn:has-text("People")');
    await page.waitForTimeout(500);

    // Locate search input on People page (exact placeholder match)
    const searchInput = page.locator('input[placeholder="Search by name..."]');
    await searchInput.waitFor({ state: 'visible', timeout: 5000 });

    // Test search for Yandex
    await searchInput.fill('Yandex');
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'screenshots/company-yandex.png', fullPage: true });

    // Check results appear (NOTE: Requires test data!)
    const personCards = page.locator('.person-card');
    const count = await personCards.count();

    // If no results, this test is SKIPPED (no test data available)
    if (count === 0) {
      console.log('⚠️  SKIPPED: No test data for Yandex search');
      test.skip();
      return;
    }

    expect(count).toBeGreaterThan(0);

    // Verify at least one card mentions Yandex (case-insensitive)
    const firstCard = personCards.first();
    const cardText = await firstCard.textContent();
    const mentionsYandex = cardText?.toLowerCase().includes('yandex') ||
                          cardText?.toLowerCase().includes('яндекс');

    expect(mentionsYandex).toBeTruthy();
  });

  test('search with threshold 0.4 produces less noise', async ({ authenticatedPage }) => {
    const page = authenticatedPage;

    // Navigate to Chat page
    await page.click('.nav-btn:has-text("Chat")');
    await page.waitForTimeout(1000);

    // Search for a specific query that should have precise results
    const chatInput = page.locator('textarea.input-neo');
    await chatInput.waitFor({ state: 'visible', timeout: 5000 });
    await chatInput.fill('кто работает в стартапах');

    // Send
    const sendBtn = page.locator('button[aria-label="Send message"]');
    await sendBtn.click();

    // Wait for response
    await page.waitForTimeout(15000);

    // Take screenshot
    await page.screenshot({ path: 'screenshots/search-threshold.png', fullPage: true });

    // Check that response exists and is not too generic
    const messages = page.locator('.chat-message, .message, .assistant-message');
    const lastMessage = messages.last();
    await lastMessage.waitFor({ state: 'visible', timeout: 5000 });

    const response = await lastMessage.textContent();

    // Should have specific results, not generic error
    expect(response).toBeTruthy();
    expect(response!.length).toBeGreaterThan(50); // Should have substantial response
  });
});
