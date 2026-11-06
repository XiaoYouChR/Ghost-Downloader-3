export type ExtensionBrowserTarget = "chromium" | "firefox";

const REQUEST_HEADERS = "requestHeaders" as chrome.webRequest.OnSendHeadersOptions;
const RESPONSE_HEADERS = "responseHeaders" as chrome.webRequest.OnResponseStartedOptions;
const EXTRA_HEADERS = "extraHeaders" as chrome.webRequest.OnSendHeadersOptions & chrome.webRequest.OnResponseStartedOptions;

let cachedBrowserTarget: ExtensionBrowserTarget | null = null;

export function extensionBrowserTarget(): ExtensionBrowserTarget {
  if (cachedBrowserTarget) {
    return cachedBrowserTarget;
  }

  try {
    const runtimeUrl = chrome.runtime.getURL("/");
    if (runtimeUrl.startsWith("moz-extension://")) {
      cachedBrowserTarget = "firefox";
      return cachedBrowserTarget;
    }
  } catch {
    // Runtime unavailable (e.g. test harness) — Chromium is the safe default.
  }

  cachedBrowserTarget = "chromium";
  return cachedBrowserTarget;
}

export function onSendHeadersExtraInfoSpec(): chrome.webRequest.OnSendHeadersOptions[] {
  return extensionBrowserTarget() === "firefox"
    ? [REQUEST_HEADERS]
    : [REQUEST_HEADERS, EXTRA_HEADERS];
}

export function onResponseStartedExtraInfoSpec(): chrome.webRequest.OnResponseStartedOptions[] {
  return extensionBrowserTarget() === "firefox"
    ? [RESPONSE_HEADERS]
    : [RESPONSE_HEADERS, EXTRA_HEADERS];
}

export function supportsDownloadDeterminingFilename(): boolean {
  return Boolean(chrome.downloads?.onDeterminingFilename?.addListener);
}
