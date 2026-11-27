import type {CommandResult} from "../shared/types";
import {filenameFromUrl} from "../shared/utils";
import {openActionPopup} from "./chrome-helpers";
import type {ResourceTaskOptions} from "./download-spec";
import {selectAllowedHeaders} from "./resource-cache";
import {basenameOf, toResponseMeta} from "./response-meta";

const HTTP_OK = 200;
const DOWNLOAD_MIME_TYPES = new Set(["application/octet-stream", "application/zip", "application/x-7z-compressed", "application/vnd.rar", "application/gzip"]);

type ResponseDetails = chrome.webRequest.OnHeadersReceivedDetails & {originUrl?: string; documentUrl?: string};
type Decision = chrome.webRequest.BlockingResponse | undefined;
// Unlike Chromium, Firefox waits for promises returned by blocking listeners.
declare const browser: {webRequest: {onHeadersReceived: {addListener(
  listener: (details: ResponseDetails) => Promise<Decision> | Decision,
  filter: chrome.webRequest.RequestFilter, options: ("blocking" | "responseHeaders")[],
): void}}};

export function registerFirefoxDownloads(
  canTake: (url: string, filename: string, size: number, pageUrl: string) => Promise<boolean>,
  send: (payload: ResourceTaskOptions) => Promise<CommandResult>,
) {
  const navigations: chrome.webRequest.RequestFilter = {urls: ["http://*/*", "https://*/*"], types: ["main_frame", "sub_frame"]};
  const headersByRequest = new Map<string, Record<string, string>>();
  chrome.webRequest.onSendHeaders.addListener(details => {
    const headers = Object.fromEntries((details.requestHeaders ?? []).map(h => [h.name, h.value ?? ""]));
    headersByRequest.set(details.requestId, selectAllowedHeaders(headers));
  }, navigations, ["requestHeaders"]);

  const forget = ({requestId}: {requestId: string}) => { headersByRequest.delete(requestId); };
  chrome.webRequest.onErrorOccurred.addListener(forget, navigations);
  chrome.webRequest.onCompleted.addListener(forget, navigations);

  // Firefox creates DownloadItems after it asks where to save. Hold only identifiable
  // downloads at the response boundary, and keep the original response if handoff fails.
  browser.webRequest.onHeadersReceived.addListener((details) => {
    const headers = headersByRequest.get(details.requestId) ?? {};
    forget(details);
    if (details.method !== "GET" || details.statusCode !== HTTP_OK || details.tabId < 0) {
      return;
    }
    const meta = toResponseMeta(details.responseHeaders);
    if (!meta.isAttachment && !DOWNLOAD_MIME_TYPES.has(meta.mime)) {
      return;
    }

    return (async () => {
      try {
        const filename = meta.filename || basenameOf(filenameFromUrl(details.url)) || "resource";
        const pageUrl = details.documentUrl || details.originUrl || headers.referer || "";
        if (!await canTake(details.url, filename, meta.hasSize ? meta.size : -1, pageUrl)) {
          return;
        }
        const result = await send({url: details.url, filename, size: meta.size, supportsRange: meta.supportsRange, headers});
        if (result.ok) {
          void openActionPopup(result);
          return {cancel: true};
        }
      } catch {
        // Desktop or queue unavailable: let Firefox continue with the same request.
      }
    })();
  }, navigations, ["blocking", "responseHeaders"]);
}
