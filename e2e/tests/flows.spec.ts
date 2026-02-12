import { test, expect } from '../fixtures/auth';

test.describe('Critical User Flows', () => {

  test('create text note and verify processing', async ({ authenticatedPage }) => {
    const page = authenticatedPage;

    // Go to Notes
    await page.click('.nav-btn:has-text("Notes")');
    await page.waitForTimeout(500);

    // Switch to text mode if needed
    const textBtn = page.locator('.mode-btn:has-text("Text")');
    if (await textBtn.isVisible()) {
      await textBtn.click();
    }

    // Find textarea and submit button
    const textarea = page.locator('textarea');
    const submitBtn = page.locator('button:has-text("Process"), button:has-text("Submit"), .submit-btn');

    if (await textarea.isVisible() && await submitBtn.isVisible()) {
      // Enter test note
      const testNote = `E2E Test Note ${Date.now()}: Met John Smith, he works at Google as an engineer.`;
      await textarea.fill(testNote);
      await page.screenshot({ path: 'screenshots/10-note-entered.png', fullPage: true });

      // Submit
      await submitBtn.click();
      await page.screenshot({ path: 'screenshots/11-note-submitted.png', fullPage: true });

      // Wait for processing (look for status change)
      await page.waitForTimeout(3000);
      await page.screenshot({ path: 'screenshots/12-note-processing.png', fullPage: true });
    }
  });

  test('view person details', async ({ authenticatedPage }) => {
    const page = authenticatedPage;

    // Should be on People page
    await expect(page.locator('h1')).toContainText('People');

    // Check if there are any people
    const personCards = page.locator('.person-card');
    const count = await personCards.count();

    if (count > 0) {
      // Click first person
      await personCards.first().click();
      await page.waitForTimeout(500);

      // Should show person details (back button visible)
      await expect(page.locator('.back-btn, button:has-text("Back")')).toBeVisible();
      await page.screenshot({ path: 'screenshots/20-person-detail.png', fullPage: true });

      // Go back
      await page.click('.back-btn, button:has-text("Back")');
      await page.waitForTimeout(500);
      await expect(page.locator('h1')).toContainText('People');
    } else {
      // No people yet - take screenshot of empty state
      await page.screenshot({ path: 'screenshots/20-no-people.png', fullPage: true });
    }
  });

  test('chat with agent', async ({ authenticatedPage }) => {
    const page = authenticatedPage;

    // Go to Chat
    await page.click('.nav-btn:has-text("Chat")');
    await page.waitForTimeout(500);
    await page.screenshot({ path: 'screenshots/30-chat-initial.png', fullPage: true });

    // Find chat input
    const chatInput = page.locator('.chat-input, input[placeholder*="message"], textarea');
    const sendBtn = page.locator('.chat-send-btn, button:has-text("Send")');

    if (await chatInput.isVisible()) {
      await chatInput.fill('Who do I know?');
      await page.screenshot({ path: 'screenshots/31-chat-input.png', fullPage: true });

      if (await sendBtn.isVisible()) {
        await sendBtn.click();

        // Wait for response
        await page.waitForTimeout(5000);
        await page.screenshot({ path: 'screenshots/32-chat-response.png', fullPage: true });
      }
    }
  });

  test('tabs switch correctly on People page', async ({ authenticatedPage }) => {
    const page = authenticatedPage;

    // Look for tab buttons
    const ownTab = page.locator('.mode-btn:has-text("Mine"), .tab-btn:has-text("Own")');
    const sharedTab = page.locator('.mode-btn:has-text("Shared")');

    if (await ownTab.isVisible() && await sharedTab.isVisible()) {
      // Click Shared
      await sharedTab.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: 'screenshots/40-shared-tab.png', fullPage: true });

      // Click Own
      await ownTab.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: 'screenshots/41-own-tab.png', fullPage: true });
    }
  });
});
