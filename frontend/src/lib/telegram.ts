import WebApp from '@twa-dev/sdk';

export const telegram = WebApp;

export const initTelegram = () => {
  if (WebApp.initData) {
    WebApp.ready();
    WebApp.expand();
  }
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
 * Returns person_id if start_param is "person_{uuid}", otherwise null.
 */
export const parsePersonDeeplink = (): string | null => {
  const startParam = getStartParam();
  if (startParam && startParam.startsWith('person_')) {
    return startParam.replace('person_', '');
  }
  return null;
};
