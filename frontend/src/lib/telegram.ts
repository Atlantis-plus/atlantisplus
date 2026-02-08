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
