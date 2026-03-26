export type BrowserTarget = "chromium" | "firefox";

type RuntimeManifest = chrome.runtime.Manifest & {
  browser_specific_settings?: {
    gecko?: {
      id?: string;
      strict_min_version?: string;
    };
  };
};

const runtimeManifest = chrome.runtime.getManifest() as RuntimeManifest;

export const BROWSER_TARGET: BrowserTarget = runtimeManifest.browser_specific_settings?.gecko
  ? "firefox"
  : "chromium";

export const IS_FIREFOX = BROWSER_TARGET === "firefox";
