import type {ScannedImage} from "../shared/types";

const IMAGE_REFERER_RULE_ID = 9999;

function scanPageImages(): ScannedImage[] {
  const seen = new Set<string>();
  const results: ScannedImage[] = [];

  function add(src: string, w: number, h: number, alt: string): void {
    if (!src || src.startsWith("data:") || src.startsWith("blob:") || seen.has(src)) return;
    seen.add(src);
    results.push({ src, naturalWidth: w, naturalHeight: h, alt });
  }

  // <img> naturalWidth/Height is free here — the page already loaded these images
  for (const img of Array.from(document.querySelectorAll<HTMLImageElement>("img"))) {
    const src = img.currentSrc || img.src;
    add(src, img.naturalWidth, img.naturalHeight, img.alt || "");
  }

  const bgUrlRe = /url\(\s*['"]?\s*(\S+?)\s*['"]?\s*\)/i;
  const pseudos: (string | null)[] = [null, "::before", "::after"];
  for (const el of Array.from(document.querySelectorAll("*"))) {
    for (const pseudo of pseudos) {
      const bg = getComputedStyle(el, pseudo).getPropertyValue("background-image");
      if (bg === "none" || !bg) continue;
      const m = bgUrlRe.exec(bg);
      if (m?.[1]) add(m[1], 0, 0, "");
    }
  }

  const urlRe = /https?:\/\/[-a-zA-Z0-9@:%._+~#=]{2,256}\.[a-z]{2,6}\b[-a-zA-Z0-9@:%_+.~#?&/=]*/gi;
  const imageExtRe = /\.(png|jpg|jpeg|gif|webp|svg|bmp|ico|avif|heic|tif|tiff|apng|jfif)(\?.*)?$/i;
  const html = document.documentElement.outerHTML;
  const urls = html.match(urlRe);
  if (urls) {
    for (const raw of new Set(urls)) {
      const cleaned = raw.replace(/&(quot|lt|gt|amp);?$/i, "");
      if (imageExtRe.test(cleaned)) add(cleaned, 0, 0, "");
    }
  }

  return results;
}

async function setImageRefererRule(pageUrl: string): Promise<void> {
  try {
    const origin = new URL(pageUrl).origin;
    await chrome.declarativeNetRequest.updateSessionRules({
      removeRuleIds: [IMAGE_REFERER_RULE_ID],
      addRules: [{
        id: IMAGE_REFERER_RULE_ID,
        condition: {
          initiatorDomains: [chrome.runtime.id],
          resourceTypes: ["image" as chrome.declarativeNetRequest.ResourceType],
        },
        action: {
          type: "modifyHeaders" as chrome.declarativeNetRequest.RuleActionType,
          requestHeaders: [{
            header: "Referer",
            operation: "set" as chrome.declarativeNetRequest.HeaderOperation,
            value: origin,
          }],
        },
      }],
    });
  } catch {
    // declarativeNetRequest may not be available in all contexts.
  }
}

export async function scanActiveTabImages(): Promise<ScannedImage[]> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url || !/^https?:/i.test(tab.url)) {
    return [];
  }

  await setImageRefererRule(tab.url);

  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: false },
      func: scanPageImages,
    });
    return results[0]?.result ?? [];
  } catch {
    return [];
  }
}
