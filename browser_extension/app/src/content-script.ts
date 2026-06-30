import {installCatCatchBridge} from "./cat-catch-bridge";
import {startMediaAttribution} from "./page-media/attribution/attribution";
import {MEDIA_SIGNAL_KEY} from "./page-media/attribution/attribution-signal";

installCatCatchBridge();
startMediaAttribution();

window.addEventListener("message", (event) => {
  const data = event.data;
  if (!data || data[MEDIA_SIGNAL_KEY] !== true || data.kind !== "media_metadata") { return; }
  chrome.runtime.sendMessage({
    type: "media_metadata",
    urls: data.urls,
    duration: data.duration,
    videoWidth: data.videoWidth,
    videoHeight: data.videoHeight,
    posterUrl: data.posterUrl,
  });
});

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

let bypassModifier: "alt" | "ctrl" | "shift" = "alt";

chrome.storage.local.get({ bypassModifier: "alt" }, (result) => {
  bypassModifier = (result.bypassModifier as typeof bypassModifier) || "alt";
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === "local" && changes.bypassModifier) {
    bypassModifier = (changes.bypassModifier.newValue as typeof bypassModifier) || "alt";
  }
});

document.addEventListener("click", (event) => {
  const isHeld = bypassModifier === "alt" ? event.altKey
    : bypassModifier === "ctrl" ? event.ctrlKey
    : event.shiftKey;
  if (isHeld) {
    chrome.runtime.sendMessage({ type: "bypass_next_download" });
  }
}, true);
