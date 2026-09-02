import {installCatCatchBridge} from "./cat-catch-bridge";
import {startMediaAttribution} from "./page-media/attribution/attribution";
import {
  type BypassShortcut,
  DEFAULT_BYPASS_SHORTCUT,
  parseBypassShortcut,
} from "./shared/bypass-shortcut";
import {BYPASS_SHORTCUT_KEY} from "./background/constants";

installCatCatchBridge();
startMediaAttribution();

function sendPagePoster(): void {
  const ogImage = document.querySelector<HTMLMetaElement>('meta[property="og:image"]')?.content?.trim();
  if (!ogImage) { return; }

  const img = new Image();
  img.crossOrigin = "anonymous";
  img.onload = () => {
    try {
      const canvas = document.createElement("canvas");
      const scale = Math.min(1, 160 / img.naturalWidth);
      canvas.width = Math.round(img.naturalWidth * scale);
      canvas.height = Math.round(img.naturalHeight * scale);
      const ctx = canvas.getContext("2d");
      if (!ctx) { return; }
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
      chrome.runtime.sendMessage({ type: "page_poster", posterUrl: dataUrl });
    } catch {
      // Tainted canvas on cross-origin images without CORS — silent fallback.
    }
  };
  img.src = ogImage;
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", sendPagePoster);
} else {
  sendPagePoster();
}

let bypassShortcut: BypassShortcut = DEFAULT_BYPASS_SHORTCUT;
let isBypassHeld = false;

chrome.storage.local.get({ [BYPASS_SHORTCUT_KEY]: null }, (result) => {
  bypassShortcut = parseBypassShortcut(result[BYPASS_SHORTCUT_KEY]);
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === "local" && changes[BYPASS_SHORTCUT_KEY]) {
    bypassShortcut = parseBypassShortcut(changes[BYPASS_SHORTCUT_KEY].newValue);
  }
});

function shortcutMatchesEvent(event: KeyboardEvent): boolean {
  if (bypassShortcut.ctrlKey !== event.ctrlKey) return false;
  if (bypassShortcut.altKey !== event.altKey) return false;
  if (bypassShortcut.shiftKey !== event.shiftKey) return false;
  if (bypassShortcut.metaKey !== event.metaKey) return false;
  if (bypassShortcut.code && event.code !== bypassShortcut.code) return false;
  return true;
}

function sendBypassState(pressed: boolean): void {
  chrome.runtime.sendMessage({ type: "bypass_key_state", pressed });
}

document.addEventListener("keydown", (event) => {
  if (!isBypassHeld && shortcutMatchesEvent(event)) {
    isBypassHeld = true;
    sendBypassState(true);
  }
}, true);

document.addEventListener("keyup", (event) => {
  if (!isBypassHeld) return;
  const isModifierReleased =
    (bypassShortcut.ctrlKey && !event.ctrlKey) ||
    (bypassShortcut.altKey && !event.altKey) ||
    (bypassShortcut.shiftKey && !event.shiftKey) ||
    (bypassShortcut.metaKey && !event.metaKey);
  const isKeyReleased = bypassShortcut.code !== "" && event.code === bypassShortcut.code;
  if (isModifierReleased || isKeyReleased) {
    isBypassHeld = false;
    sendBypassState(false);
  }
}, true);

window.addEventListener("blur", () => {
  if (isBypassHeld) {
    isBypassHeld = false;
    sendBypassState(false);
  }
});
