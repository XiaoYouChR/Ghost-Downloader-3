/**
 * Cross-browser compatibility module for Chrome and Firefox
 * Provides normalized APIs that work across both browsers
 */

export type BrowserType = "chrome" | "firefox";

export function detectBrowser(): BrowserType {
  return typeof (global as any).browser !== "undefined" ? "firefox" : "chrome";
}

export const browserAPI = (() => {
  const isFirefox = detectBrowser() === "firefox";
  const runtime = isFirefox ? (global as any).browser : (global as any).chrome;

  return {
    isFirefox,
    runtime,
    tabs: runtime.tabs,
    storage: runtime.storage,
    downloads: runtime.downloads,
    action: runtime.action,
  };
})();

/**
 * Normalize chrome.runtime.sendMessage to work with browser.runtime.sendMessage
 */
export function sendRuntimeMessage(
  message: Record<string, unknown>,
  options?: any
): Promise<any> {
  return new Promise((resolve, reject) => {
    if (browserAPI.isFirefox) {
      browserAPI.runtime
        .sendMessage(message)
        .then(resolve)
        .catch(reject);
    } else {
      browserAPI.runtime.sendMessage(message, options ?? {}, (response: any) => {
        const lastError = browserAPI.runtime.lastError;
        if (lastError) {
          reject(new Error(lastError.message));
          return;
        }
        resolve(response);
      });
    }
  });
}

/**
 * Add message listener that works for both browsers
 */
export function onRuntimeMessage(
  listener: (
    message: Record<string, unknown>,
    sender: any,
    sendResponse: (response?: any) => void
  ) => void | boolean
): void {
  browserAPI.runtime.onMessage.addListener(
    (message: any, sender: any, sendResponse: any) => {
      const result = listener(message, sender, sendResponse);
      if (result === true) {
        return true;
      }
      return undefined;
    }
  );
}

/**
 * Send message to tab - works for both browsers
 */
export async function sendTabMessage<T>(
  tabId: number,
  message: Record<string, unknown>,
  options?: any
): Promise<T> {
  if (browserAPI.isFirefox) {
    return browserAPI.runtime.sendMessage(
      {
        tabId,
        ...message,
      }
    );
  }

  return new Promise((resolve, reject) => {
    browserAPI.tabs.sendMessage(tabId, message, options ?? {}, (response: T) => {
      const lastError = browserAPI.runtime.lastError;
      if (lastError) {
        reject(new Error(lastError.message));
        return;
      }
      resolve(response);
    });
  });
}

/**
 * Cancel download - works for both browsers
 */
export async function cancelDownload(downloadId: number): Promise<void> {
  return new Promise((resolve, reject) => {
    browserAPI.downloads.cancel(downloadId, () => {
      const lastError = browserAPI.runtime.lastError;
      if (lastError) {
        reject(new Error(lastError.message));
        return;
      }
      resolve();
    });
  });
}

/**
 * Open action popup - works for both browsers
 */
export async function openActionPopup(): Promise<void> {
  if (!browserAPI.action?.openPopup) {
    return;
  }

  try {
    await browserAPI.action.openPopup();
  } catch {
    // Ignore popup open failures
  }
}
