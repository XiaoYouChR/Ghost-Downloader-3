export type TabMessageStatus = "ok" | "no_receiver" | "runtime_error" | "no_response";

export type TabMessageResult<T> = {
  status: TabMessageStatus;
  response?: T;
  message?: string;
};

// Bridges store transient state here. Prefer session (cleared at browser close); Firefox
// has no chrome.storage.session, so fall back to local.
const bridgeStorage = chrome.storage.session ?? chrome.storage.local;

export async function loadLocalState<T extends Record<string, unknown>>(defaults: T): Promise<T> {
  const items = await chrome.storage.local.get(defaults);
  return items as T;
}

export async function saveLocalState(values: Record<string, unknown>): Promise<void> {
  await chrome.storage.local.set(values);
}

export async function loadSessionState<T extends Record<string, unknown>>(defaults: T): Promise<T> {
  const items = await bridgeStorage.get(defaults);
  return items as T;
}

export async function saveSessionState(values: Record<string, unknown>): Promise<void> {
  await bridgeStorage.set(values);
}

export async function queryTabs(queryInfo: chrome.tabs.QueryInfo): Promise<chrome.tabs.Tab[]> {
  return chrome.tabs.query(queryInfo);
}

export async function findTab(tabId: number): Promise<chrome.tabs.Tab | null> {
  try {
    return await chrome.tabs.get(tabId);
  } catch {
    return null;
  }
}

export async function sendMessageToTab<T>(
  tabId: number,
  message: Record<string, unknown>,
  options?: chrome.tabs.MessageSendOptions,
): Promise<TabMessageResult<T>> {
  const tab = await findTab(tabId);
  if (!tab?.id) {
    return {
      status: "no_receiver",
      message: chrome.i18n.getMessage("errorTargetTabNotFound"),
    };
  }

  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, message, options ?? {}, (response: T) => {
      const lastError = chrome.runtime.lastError;
      if (lastError) {
        const text = String(lastError.message || "");
        const status = /receiving end does not exist/i.test(text) ? "no_receiver" : "runtime_error";
        resolve({
          status,
          message: text,
        });
        return;
      }
      if (typeof response === "undefined") {
        resolve({
          status: "no_response",
        });
        return;
      }
      resolve({
        status: "ok",
        response,
      });
    });
  });
}

export async function reloadTab(tabId: number): Promise<void> {
  return new Promise((resolve) => {
    chrome.tabs.reload(tabId, { bypassCache: true }, () => resolve());
  });
}

export async function cancelDownload(downloadId: number): Promise<void> {
  return new Promise((resolve, reject) => {
    chrome.downloads.cancel(downloadId, () => {
      const lastError = chrome.runtime.lastError;
      if (lastError) {
        reject(new Error(lastError.message));
        return;
      }
      resolve();
    });
  });
}

export async function eraseDownloadFromHistory(downloadId: number): Promise<void> {
  return new Promise((resolve, reject) => {
    chrome.downloads.erase({ id: downloadId }, () => {
      const lastError = chrome.runtime.lastError;
      if (lastError) {
        reject(new Error(lastError.message));
        return;
      }
      resolve();
    });
  });
}

export async function openActionPopup(): Promise<void> {
  if (!chrome.action?.openPopup) {
    return;
  }

  try {
    await chrome.action.openPopup();
  } catch {
    // The action that called us already succeeded — popup open is best-effort.
  }
}
