# E2E Testing Plan for Atlantis Plus

> Полный контекст для Claude Code агентов. Создан 2024.

## Резюме

Цель: автономное E2E тестирование Mini App агентами без участия человека.

### Ключевое открытие

**Существующий dev mode уже работает!** В `useAuth.ts:69-78` есть fallback когда `isTelegramMiniApp()` = false:
```typescript
} else {
  // Not in Telegram Mini App - dev mode
  setState({ session: null, loading: false, ... displayName: 'Dev User' });
}
```

Проблема: в dev mode `session: null`, поэтому `isAuthenticated = false` и UI показывает "Please authenticate first".

### Решение: минимальные изменения

Нужно чтобы dev mode использовал `/auth/telegram/test` (уже реализован на backend) для получения реальной Supabase сессии.

---

## Рекомендованный подход (после review)

### Complexity Score: 3/10 (вместо 7/10 из полного плана)

### Структура файлов (4 файла вместо 15):

```
e2e/
├── playwright.config.ts     # Базовая конфигурация
├── fixtures/
│   └── auth.ts              # Supabase session setup
└── tests/
    ├── smoke.spec.ts        # Все страницы загружаются
    └── flows.spec.ts        # Критические flows: note → extraction → people
```

### Что делать:

1. **Frontend (1 изменение):** Модифицировать `useAuth.ts` чтобы в dev mode вызывать `/auth/telegram/test`
2. **E2E setup:** 4 файла Playwright без Page Objects
3. **API тесты (опционально):** pytest для backend endpoints

### Что НЕ делать:

- Page Object Model (overhead для 4 страниц)
- 15 файлов тестовой инфраструктуры
- Моки Telegram SDK (используем существующий dev mode)
- Сложные fixtures

---

## Детали реализации

### 1. Изменение в useAuth.ts

```typescript
// В функции authenticate(), заменить dev mode блок:

} else {
  // Not in Telegram Mini App - E2E/dev mode with test auth
  try {
    const testSecret = import.meta.env.VITE_TEST_AUTH_SECRET || '';
    const response = await fetch(`${import.meta.env.VITE_API_URL}/auth/telegram/test`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Test-Secret': testSecret,
      },
      body: JSON.stringify({ telegram_id: 999999999 }),
    });

    if (response.ok) {
      const authResponse = await response.json();
      const session = await setSupabaseSession(authResponse.access_token, authResponse.refresh_token);
      api.setAccessToken(authResponse.access_token);
      setState({
        session,
        loading: false,
        error: null,
        telegramId: authResponse.telegram_id,
        displayName: authResponse.display_name
      });
    } else {
      setState({ session: null, loading: false, error: 'Dev auth failed', telegramId: null, displayName: 'Dev User' });
    }
  } catch (e) {
    setState({ session: null, loading: false, error: 'Dev auth error', telegramId: null, displayName: 'Dev User' });
  }
}
```

### 2. Playwright config

```typescript
// e2e/playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: 'results.json' }]],
  use: {
    baseURL: 'http://localhost:5173/atlantisplus/',
    screenshot: 'on',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'cd ../frontend && npm run dev',
    url: 'http://localhost:5173/atlantisplus/',
    reuseExistingServer: true,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
```

### 3. Auth fixture

```typescript
// e2e/fixtures/auth.ts
import { test as base, expect } from '@playwright/test';

export const test = base.extend({
  authenticatedPage: async ({ page }, use) => {
    await page.goto('/');
    // Wait for dev mode auth to complete
    await page.waitForSelector('.bottom-nav', { timeout: 30000 });
    await use(page);
  },
});

export { expect };
```

### 4. Smoke tests

```typescript
// e2e/tests/smoke.spec.ts
import { test, expect } from '../fixtures/auth';

test('app loads and authenticates', async ({ authenticatedPage }) => {
  await expect(authenticatedPage.locator('.bottom-nav')).toBeVisible();
  await authenticatedPage.screenshot({ path: 'screenshots/01-app-loaded.png' });
});

test('navigate all pages', async ({ authenticatedPage }) => {
  const page = authenticatedPage;

  // Notes
  await page.click('.nav-btn:has-text("Notes")');
  await expect(page.locator('h1')).toContainText('Note');
  await page.screenshot({ path: 'screenshots/02-notes.png' });

  // Chat
  await page.click('.nav-btn:has-text("Chat")');
  await page.screenshot({ path: 'screenshots/03-chat.png' });

  // Import
  await page.click('.nav-btn:has-text("Import")');
  await page.screenshot({ path: 'screenshots/04-import.png' });

  // Back to People
  await page.click('.nav-btn:has-text("People")');
  await expect(page.locator('h1')).toContainText('People');
});
```

---

## Запуск тестов

```bash
# Backend (в одном терминале)
cd /Users/evgenyq/Projects/atlantisplus/service
source venv/bin/activate
ENVIRONMENT=development TEST_MODE_ENABLED=true TEST_AUTH_SECRET=***REMOVED*** \
  uvicorn app.main:app --port 8000

# Frontend (в другом терминале)
cd /Users/evgenyq/Projects/atlantisplus/frontend
VITE_TEST_AUTH_SECRET=***REMOVED*** npm run dev

# E2E тесты (в третьем терминале)
cd /Users/evgenyq/Projects/atlantisplus/e2e
npm test
```

---

## Анализ скриншотов

После запуска тестов:
```bash
# Список скриншотов
ls -la /Users/evgenyq/Projects/atlantisplus/e2e/screenshots/

# Прочитать скриншот (Claude Code видит изображения)
# Использовать Read tool на .png файлы
```

---

## Research findings (из Explore агента)

### Best practices:

1. **mockTelegramEnv()** из `@telegram-apps/sdk-react` - стандартный паттерн
2. **TMA-Studio** - desktop app для ручного тестирования
3. **Auth fixtures** с `page.addInitScript()` для инъекции токенов
4. **toHaveScreenshot()** для visual regression

### Источники:
- https://docs.telegram-mini-apps.com/platform/test-environment
- https://github.com/erfanmola/TMA-Studio
- https://github.com/Telegram-Mini-Apps/telegram-apps
- https://playwright.dev/docs/auth

---

## Review findings (из Senior Reviewer)

### Критические замечания:

1. **Page Object Model overkill** для 4 страниц - пропускаем
2. **Существующий dev mode** можно использовать - не нужны изменения в telegram.ts
3. **Test user isolation** важнее чем много тестов
4. **API тесты** имеют более высокий ROI чем UI тесты

### Risk matrix:

| Risk | Mitigation |
|------|------------|
| Tests become stale | Minimal tests, critical paths only |
| Production breakage | Only change useAuth.ts, guarded by `!isTelegramMiniApp()` |
| Flaky tests | Playwright auto-wait, no timing hacks |

---

## Чеклист реализации

- [ ] Изменить `useAuth.ts` для dev mode auth
- [ ] Добавить `VITE_TEST_AUTH_SECRET` в frontend/.env.development
- [ ] Создать `e2e/` директорию с 4 файлами
- [ ] Установить Playwright: `npm init playwright@latest`
- [ ] Запустить smoke тесты
- [ ] Проверить что агенты могут видеть скриншоты
