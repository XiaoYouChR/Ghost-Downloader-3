import { IS_FIREFOX } from "../shared/browser";

type RequestSourceDetails = {
  documentUrl?: string;
  initiator?: string;
  originUrl?: string;
};

const ON_SEND_HEADERS_REQUEST_HEADERS = "requestHeaders" as unknown as chrome.webRequest.OnSendHeadersOptions;
const ON_SEND_HEADERS_EXTRA_HEADERS = "extraHeaders" as unknown as chrome.webRequest.OnSendHeadersOptions;
const ON_RESPONSE_STARTED_RESPONSE_HEADERS =
  "responseHeaders" as unknown as chrome.webRequest.OnResponseStartedOptions;

export function getOnSendHeadersExtraInfoSpec(): chrome.webRequest.OnSendHeadersOptions[] {
  return IS_FIREFOX
    ? [ON_SEND_HEADERS_REQUEST_HEADERS]
    : [
        ON_SEND_HEADERS_REQUEST_HEADERS,
        ON_SEND_HEADERS_EXTRA_HEADERS,
      ];
}

export function getOnResponseStartedExtraInfoSpec(): chrome.webRequest.OnResponseStartedOptions[] {
  return [ON_RESPONSE_STARTED_RESPONSE_HEADERS];
}

export function resolveRequestSourceUrl(details: RequestSourceDetails): string {
  return String(details.documentUrl ?? details.originUrl ?? details.initiator ?? "").trim();
}

export function registerDownloadInterceptionListener(
  listener: (downloadItem: chrome.downloads.DownloadItem) => void,
) {
  if (IS_FIREFOX) {
    chrome.downloads.onCreated.addListener(listener);
    return;
  }

  chrome.downloads.onDeterminingFilename.addListener((downloadItem, suggest) => {
    suggest();
    listener(downloadItem);
  });
}
