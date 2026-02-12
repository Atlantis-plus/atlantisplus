import WebApp from '@twa-dev/sdk';

export const telegram = WebApp;

export const initTelegram = () => {
  if (WebApp.initData) {
    WebApp.ready();
    WebApp.expand();

    // Apply theme based on Telegram colorScheme
    applyTelegramTheme();
  }
};

/**
 * Get Telegram's color scheme (light/dark).
 * Falls back to system preference if not in Telegram Mini App.
 */
export const getTelegramColorScheme = (): 'light' | 'dark' => {
  if (WebApp.colorScheme) {
    return WebApp.colorScheme;
  }
  // Fallback to system preference
  if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark';
  }
  return 'light';
};

/**
 * Apply theme to document based on Telegram's colorScheme.
 * Sets data-theme attribute on documentElement for CSS variable switching.
 */
export const applyTelegramTheme = () => {
  const theme = getTelegramColorScheme();
  document.documentElement.setAttribute('data-theme', theme);

  // Listen for theme changes in Telegram
  WebApp.onEvent('themeChanged', () => {
    const newTheme = getTelegramColorScheme();
    document.documentElement.setAttribute('data-theme', newTheme);
  });
};

export const getTelegramInitData = (): string | null => {
  return WebApp.initData || null;
};

export const getTelegramUser = () => {
  return WebApp.initDataUnsafe?.user || null;
};

export const closeTelegramApp = () => {
  WebApp.close();
};

export const showTelegramAlert = (message: string) => {
  WebApp.showAlert(message);
};

export const isTelegramMiniApp = (): boolean => {
  return !!WebApp.initData;
};

export const openExternalLink = (url: string) => {
  if (isTelegramMiniApp()) {
    WebApp.openLink(url);
  } else {
    window.open(url, '_blank');
  }
};

/**
 * Get the start_param from Telegram deeplink.
 * When user opens link like https://t.me/bot/app?startapp=person_abc123
 * this returns "person_abc123"
 */
export const getStartParam = (): string | null => {
  return WebApp.initDataUnsafe?.start_param || null;
};

/**
 * Parse start_param to extract person_id if it's a person deeplink.
 * Checks multiple sources:
 * 1. Telegram SDK start_param (for regular deeplinks like t.me/bot/app?startapp=person_xxx)
 * 2. URL query parameter (for web_app buttons in inline keyboard)
 * 3. URL hash parameter as fallback
 *
 * Returns person_id if found, otherwise null.
 */
export const parsePersonDeeplink = (): string | null => {
  // 1. Try Telegram SDK start_param first (using imported WebApp)
  const tgStartParam = WebApp.initDataUnsafe?.start_param;
  if (tgStartParam && tgStartParam.startsWith('person_')) {
    return tgStartParam.replace('person_', '');
  }

  // 2. Try URL query parameter (for web_app buttons)
  const urlParams = new URLSearchParams(window.location.search);
  const startappParam = urlParams.get('startapp');
  if (startappParam && startappParam.startsWith('person_')) {
    return startappParam.replace('person_', '');
  }

  // 3. Try hash parameter as fallback
  const hash = window.location.hash;
  if (hash.includes('person=')) {
    const match = hash.match(/person=([a-f0-9-]+)/);
    if (match) {
      return match[1];
    }
  }

  return null;
};
