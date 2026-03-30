export type ExtensionBrowserTarget = "chromium" | "firefox";

const REQUEST_HEADERS = "requestHeaders" as chrome.webRequest.OnSendHeadersOptions;
const EXTRA_HEADERS = "extraHeaders" as chrome.webRequest.OnSendHeadersOptions;

let cachedBrowserTarget: ExtensionBrowserTarget | null = null;

export function getExtensionBrowserTarget(): ExtensionBrowserTarget {
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
    // Fall through to the Chromium default when the runtime is not available.
  }

  cachedBrowserTarget = "chromium";
  return cachedBrowserTarget;
}

export function isFirefoxExtension(): boolean {
  return getExtensionBrowserTarget() === "firefox";
}

export function getInstallDirectory(): string {
  return isFirefoxExtension() ? "browser_extension/firefox" : "browser_extension/chromium";
}

export function getOnSendHeadersExtraInfoSpec(): chrome.webRequest.OnSendHeadersOptions[] {
  return isFirefoxExtension()
    ? [REQUEST_HEADERS]
    : [REQUEST_HEADERS, EXTRA_HEADERS];
}

export function supportsDownloadDeterminingFilename(): boolean {
  return Boolean(chrome.downloads?.onDeterminingFilename?.addListener);
}
