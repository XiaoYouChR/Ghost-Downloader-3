import type {ScannedImage} from "../shared/types";

const IMAGE_REFERER_RULE_ID = 9999;

function scanPageImages(): ScannedImage[] {
  const seen = new Set<string>();
  const results: ScannedImage[] = [];

  for (const img of Array.from(document.querySelectorAll<HTMLImageElement>("img"))) {
    const src = img.currentSrc || img.src;
    if (!src || src.startsWith("data:") || src.startsWith("blob:") || seen.has(src)) {
      continue;
    }
    const w = img.naturalWidth;
    const h = img.naturalHeight;
    if (w === 0 || h === 0) {
      continue;
    }
    seen.add(src);
    results.push({ src, naturalWidth: w, naturalHeight: h, alt: img.alt || "" });
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
