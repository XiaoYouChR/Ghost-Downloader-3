export type TabMessageStatus = "ok" | "no_receiver" | "runtime_error" | "no_response";

export type TabMessageResult<T> = {
  status: TabMessageStatus;
  response?: T;
  message?: string;
};

export function bridgeStorageArea() {
  return chrome.storage.session ?? chrome.storage.local;
}

export async function localStorageGet<T extends Record<string, unknown>>(defaults: T): Promise<T> {
  const items = await chrome.storage.local.get(defaults);
  return items as T;
}

export async function localStorageSet(values: Record<string, unknown>): Promise<void> {
  await chrome.storage.local.set(values);
}

export async function bridgeStorageGet<T extends Record<string, unknown>>(defaults: T): Promise<T> {
  const items = await bridgeStorageArea().get(defaults);
  return items as T;
}

export async function bridgeStorageSet(values: Record<string, unknown>): Promise<void> {
  await bridgeStorageArea().set(values);
}

export async function queryTabs(queryInfo: chrome.tabs.QueryInfo): Promise<chrome.tabs.Tab[]> {
  return chrome.tabs.query(queryInfo);
}

export async function getTab(tabId: number): Promise<chrome.tabs.Tab | null> {
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
  const tab = await getTab(tabId);
  if (!tab?.id) {
    return {
      status: "no_receiver",
      message: "目标标签页不存在",
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

export async function createTab(createProperties: chrome.tabs.CreateProperties): Promise<chrome.tabs.Tab> {
  return new Promise((resolve) => {
    chrome.tabs.create(createProperties, (tab) => resolve(tab));
  });
}

export async function activateTab(tabId: number): Promise<void> {
  const tab = await getTab(tabId);
  if (!tab?.id) {
    return;
  }

  if (typeof tab.index === "number" && typeof tab.windowId === "number") {
    await new Promise<void>((resolve) => {
      chrome.tabs.highlight({ windowId: tab.windowId, tabs: tab.index }, () => resolve());
    });
    return;
  }

  await new Promise<void>((resolve) => {
    chrome.tabs.update(tabId, { active: true }, () => resolve());
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
    // Ignore popup open failures so they do not affect the primary action result.
  }
}
