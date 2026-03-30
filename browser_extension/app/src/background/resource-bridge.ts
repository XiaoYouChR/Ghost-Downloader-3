import type { CapturedResource, DesktopRequestResult, PopupStatePayload } from "../shared/types";
import {
  canUseOnlineMergeSelection,
  domainFromUrl,
  fileExtension,
  filenameFromUrl,
  sortResourcesForOnlineMerge,
} from "../shared/utils";
import {
  BRIDGE_HEADER_SNAPSHOTS_KEY,
  BRIDGE_LAST_ACTIVE_TAB_KEY,
  BRIDGE_PERSIST_DEBOUNCE_MS,
  BRIDGE_RESOURCE_CACHE_KEY,
  HEADER_EXPIRATION_MS,
  HEADER_SNAPSHOT_LIMIT,
  RESOURCE_LIMIT,
} from "./constants";
import {
  bridgeStorageGet,
  bridgeStorageSet,
  getTab,
  openActionPopup,
  queryTabs,
} from "./chrome-helpers";

type BridgeHeaderSnapshot = {
  url: string;
  headers: Record<string, string>;
  capturedAt: number;
  tabId: number | null;
  supportsRange: boolean;
};

type BridgeResourcePayload = {
  url: string;
  href?: string;
  filename?: string;
  mime?: string;
  ext?: string;
  requestHeaders?: Record<string, string>;
};

type CatCatchResponseMeta = {
  size: number;
  type: string;
  attachment: string;
  supportsRange: boolean;
};

type DesktopRequestSender = <T extends DesktopRequestResult>(payload: Record<string, unknown>) => Promise<T>;
type ResourceBucket = Map<string, CapturedResource>;

const HEADER_WHITELIST = new Set(["referer", "origin", "cookie", "authorization"]);
const DIRECT_MEDIA_EXTENSIONS = new Set([
  "mp4",
  "mkv",
  "webm",
  "mp3",
  "flac",
  "wav",
  "m4a",
  "mov",
  "m4s",
  "ts",
  "flv",
  "aac",
  "ogg",
  "opus",
]);
const DOWNLOAD_EXTENSIONS = new Set(["zip", "7z", "rar", "pdf", "exe", "msi", "dmg", "pkg", "apk", "iso"]);

export function createResourceBridge(options: {
  sendDesktopRequest: DesktopRequestSender;
  isDesktopReady: () => boolean;
}) {
  let bridgePersistTimer: number | null = null;
  let bridgeStateReady = false;
  let lastActiveTabId: number | null = null;

  const resourceCache = new Map<number, ResourceBucket>();
  const resourcesById = new Map<string, CapturedResource>();
  const headersByRequestId = new Map<string, Record<string, string>>();
  const rangeRequestIds = new Set<string>();
  const headerSnapshotsByUrl = new Map<string, BridgeHeaderSnapshot>();

  function normalizeHeaders(headers: Record<string, string> | undefined): Record<string, string> {
    const result: Record<string, string> = {};
    for (const [key, value] of Object.entries(headers ?? {})) {
      const name = String(key || "").trim().toLowerCase();
      if (!HEADER_WHITELIST.has(name)) {
        continue;
      }
      const text = String(value ?? "").trim();
      if (!text) {
        continue;
      }
      result[name] = text;
    }
    return result;
  }

  function parseHeaderList(headers: chrome.webRequest.HttpHeader[] | undefined): Record<string, string> {
    const result: Record<string, string> = {};
    for (const header of headers ?? []) {
      if (!header.name) {
        continue;
      }
      const name = header.name.toLowerCase();
      if (!HEADER_WHITELIST.has(name)) {
        continue;
      }
      const value = String(header.value ?? "").trim();
      if (!value) {
        continue;
      }
      result[name] = value;
    }
    return result;
  }

  function hasRangeHeader(headers: chrome.webRequest.HttpHeader[] | undefined): boolean {
    return (headers ?? []).some((header) => {
      if (!header.name) {
        return false;
      }
      if (header.name.toLowerCase() !== "range") {
        return false;
      }
      const value = String(header.value ?? "").toLowerCase();
      return value.startsWith("bytes=");
    });
  }

  function trimFilename(value: string): string {
    const text = String(value || "").trim();
    if (!text) {
      return "";
    }
    const slashIndex = Math.max(text.lastIndexOf("/"), text.lastIndexOf("\\"));
    return slashIndex >= 0 ? text.slice(slashIndex + 1) : text;
  }

  function isCapturableUrl(rawUrl: string): boolean {
    return /^https?:/i.test(rawUrl);
  }

  function isBridgeResourceUrl(rawUrl: string): boolean {
    return /^(https?:|blob:)/i.test(rawUrl);
  }

  function isCapturableTab(tab: chrome.tabs.Tab | null): boolean {
    return Boolean(tab?.url && isCapturableUrl(tab.url));
  }

  function sortResources(resources: Iterable<CapturedResource>): CapturedResource[] {
    return [...resources].sort((left, right) => right.capturedAt - left.capturedAt);
  }

  function normalizeUrl(value: string, allowBlob = false): string {
    const text = String(value || "").trim();
    if (!text) {
      return "";
    }

    if (allowBlob && text.startsWith("blob:")) {
      return text;
    }

    try {
      const url = new URL(text);
      url.hash = "";
      return url.toString();
    } catch {
      return text.split("#", 1)[0] ?? text;
    }
  }

  function normalizeResourceUrl(value: string): string {
    return normalizeUrl(value, true);
  }

  function normalizeCapturedResource(resource: CapturedResource): CapturedResource {
    return {
      id: String(resource.id ?? ""),
      tabId: Number(resource.tabId),
      url: String(resource.url ?? ""),
      pageTitle: String(resource.pageTitle ?? ""),
      pageUrl: String(resource.pageUrl ?? ""),
      filename: String(resource.filename ?? ""),
      mime: String(resource.mime ?? "").toLowerCase(),
      size: Number(resource.size ?? 0),
      supportsRange: Boolean(resource.supportsRange),
      referer: String(resource.referer ?? ""),
      requestHeaders: normalizeHeaders(resource.requestHeaders),
      capturedAt: Number(resource.capturedAt ?? Date.now()),
      sentToDesktopAt: resource.sentToDesktopAt ? Number(resource.sentToDesktopAt) : undefined,
    };
  }

  function normalizeBridgeHeaderSnapshot(snapshot: BridgeHeaderSnapshot): BridgeHeaderSnapshot {
    return {
      url: String(snapshot.url ?? ""),
      headers: normalizeHeaders(snapshot.headers),
      capturedAt: Number(snapshot.capturedAt ?? Date.now()),
      tabId: Number.isInteger(snapshot.tabId) ? Number(snapshot.tabId) : null,
      supportsRange: Boolean(snapshot.supportsRange),
    };
  }

  function getResponseHeadersValue(headers: chrome.webRequest.HttpHeader[] | undefined): CatCatchResponseMeta {
    const meta: CatCatchResponseMeta = {
      size: 0,
      type: "",
      attachment: "",
      supportsRange: false,
    };

    for (const header of headers ?? []) {
      if (!header.name) {
        continue;
      }
      const name = header.name.toLowerCase();
      if (name === "content-length") {
        const size = Number.parseInt(String(header.value ?? ""), 10);
        if (meta.size <= 0 && Number.isFinite(size) && size > 0) {
          meta.size = size;
        }
        continue;
      }
      if (name === "content-type") {
        const type = String(header.value ?? "").split(";")[0]?.trim().toLowerCase() ?? "";
        if (type) {
          meta.type = type;
        }
        continue;
      }
      if (name === "content-disposition") {
        meta.attachment = String(header.value ?? "").trim();
        continue;
      }
      if (name === "accept-ranges") {
        const value = String(header.value ?? "").toLowerCase();
        if (value.includes("bytes")) {
          meta.supportsRange = true;
        } else if (value.includes("none")) {
          meta.supportsRange = false;
        }
        continue;
      }
      if (name === "content-range") {
        const size = String(header.value ?? "").split("/")[1];
        if (size && size !== "*") {
          const totalSize = Number.parseInt(size, 10);
          if (Number.isFinite(totalSize) && totalSize > 0) {
            meta.size = totalSize;
          }
        }
        meta.supportsRange = true;
      }
    }

    return meta;
  }

  function filenameFromContentDisposition(value: string): string {
    if (!value) {
      return "";
    }

    const utf8Match = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(value);
    if (utf8Match?.[1]) {
      try {
        return trimFilename(decodeURIComponent(utf8Match[1].trim().replace(/^"|"$/g, "")));
      } catch {
        return trimFilename(utf8Match[1].trim().replace(/^"|"$/g, ""));
      }
    }

    const quotedMatch = /filename\s*=\s*"([^"]+)"/i.exec(value);
    if (quotedMatch?.[1]) {
      return trimFilename(quotedMatch[1]);
    }

    const plainMatch = /filename\s*=\s*([^;]+)/i.exec(value);
    if (plainMatch?.[1]) {
      return trimFilename(plainMatch[1].trim().replace(/^"|"$/g, ""));
    }

    return "";
  }

  function urlsLikelySamePage(left: string, right: string): boolean {
    const normalizedLeft = normalizeUrl(left);
    const normalizedRight = normalizeUrl(right);
    if (!normalizedLeft || !normalizedRight) {
      return false;
    }
    return normalizedLeft === normalizedRight || normalizedLeft.startsWith(normalizedRight) || normalizedRight.startsWith(normalizedLeft);
  }

  async function resolveTabIdFromPageUrl(pageUrl: string): Promise<number | null> {
    const normalizedPageUrl = normalizeUrl(pageUrl);
    if (!normalizedPageUrl) {
      return null;
    }

    const tabs = await queryTabs({});
    const exactMatch = tabs.find((tab) => tab.id && tab.url && urlsLikelySamePage(tab.url, normalizedPageUrl));
    if (exactMatch?.id) {
      return exactMatch.id;
    }

    try {
      const initiatorUrl = new URL(normalizedPageUrl);
      const originMatch = tabs.find((tab) => {
        if (!tab.id || !tab.url) {
          return false;
        }
        try {
          return new URL(tab.url).origin === initiatorUrl.origin;
        } catch {
          return false;
        }
      });
      if (originMatch?.id) {
        return originMatch.id;
      }
    } catch {
      // Ignore invalid page URLs.
    }

    return null;
  }

  function shouldCaptureCatCatchResponse(
    details: chrome.webRequest.OnResponseStartedDetails,
    responseMeta: CatCatchResponseMeta,
  ): boolean {
    if (!isCapturableUrl(details.url)) {
      return false;
    }

    const extension = fileExtension(filenameFromContentDisposition(responseMeta.attachment) || filenameFromUrl(details.url));

    if (details.type === "media") {
      return true;
    }
    if (extension === "m3u8" || extension === "m3u" || extension === "mpd") {
      return true;
    }
    if (DIRECT_MEDIA_EXTENSIONS.has(extension) || DOWNLOAD_EXTENSIONS.has(extension)) {
      return true;
    }
    if (responseMeta.type.startsWith("video/") || responseMeta.type.startsWith("audio/")) {
      return true;
    }
    if (responseMeta.type.includes("mpegurl") || responseMeta.type === "application/dash+xml") {
      return true;
    }

    return Boolean(filenameFromContentDisposition(responseMeta.attachment));
  }

  function resolveNetworkResourceFilename(rawUrl: string, responseMeta: CatCatchResponseMeta): string {
    const fromDisposition = filenameFromContentDisposition(responseMeta.attachment);
    if (fromDisposition) {
      return fromDisposition;
    }

    const fromUrl = trimFilename(filenameFromUrl(rawUrl) || "");
    if (fromUrl) {
      return fromUrl;
    }

    if (responseMeta.type.includes("mpegurl")) {
      return "resource.m3u8";
    }
    if (responseMeta.type === "application/dash+xml") {
      return "resource.mpd";
    }
    return "resource";
  }

  async function persistBridgeState() {
    bridgePersistTimer = null;
    pruneHeaderSnapshots();
    await bridgeStorageSet({
      [BRIDGE_RESOURCE_CACHE_KEY]: serializeResourceCache(),
      [BRIDGE_HEADER_SNAPSHOTS_KEY]: [...headerSnapshotsByUrl.values()],
      [BRIDGE_LAST_ACTIVE_TAB_KEY]: lastActiveTabId ?? 0,
    });
  }

  function scheduleBridgeStatePersist() {
    if (bridgePersistTimer !== null) {
      return;
    }
    bridgePersistTimer = self.setTimeout(() => {
      void persistBridgeState();
    }, BRIDGE_PERSIST_DEBOUNCE_MS);
  }

  function serializeResourceCache(): Record<string, CapturedResource[]> {
    const result: Record<string, CapturedResource[]> = {};
    for (const [tabId, bucket] of resourceCache.entries()) {
      result[String(tabId)] = sortResources(bucket.values()).slice(0, RESOURCE_LIMIT);
    }
    return result;
  }

  function pruneHeaderSnapshots() {
    const now = Date.now();
    const snapshots = [...headerSnapshotsByUrl.values()]
      .map((snapshot) => normalizeBridgeHeaderSnapshot(snapshot))
      .filter((snapshot) => snapshot.url && now - snapshot.capturedAt <= HEADER_EXPIRATION_MS)
      .sort((left, right) => right.capturedAt - left.capturedAt)
      .slice(0, HEADER_SNAPSHOT_LIMIT);

    headerSnapshotsByUrl.clear();
    for (const snapshot of snapshots) {
      headerSnapshotsByUrl.set(snapshot.url, snapshot);
    }
  }

  function clearResourcesForTab(tabId: number) {
    const bucket = resourceCache.get(tabId);
    if (!bucket) {
      return;
    }
    for (const resourceId of bucket.keys()) {
      resourcesById.delete(resourceId);
    }
    resourceCache.delete(tabId);
    scheduleBridgeStatePersist();
  }

  function clearHeaderSnapshotsForTab(tabId: number) {
    let changed = false;
    for (const [url, snapshot] of headerSnapshotsByUrl.entries()) {
      if (snapshot.tabId === tabId) {
        headerSnapshotsByUrl.delete(url);
        changed = true;
      }
    }
    if (changed) {
      scheduleBridgeStatePersist();
    }
  }

  async function setLastActiveTab(tabId: number | null) {
    if (lastActiveTabId === tabId) {
      return;
    }
    lastActiveTabId = tabId;
    scheduleBridgeStatePersist();
  }

  async function refreshActiveTabFromBrowser(): Promise<number | null> {
    const tabs = await queryTabs({ active: true, currentWindow: true });
    const tabId = tabs[0]?.id ?? null;
    await setLastActiveTab(tabId);
    return tabId;
  }

  async function resolveActiveTabId(preferredTabId: number | null = null): Promise<number | null> {
    if (preferredTabId != null) {
      const preferredTab = await getTab(preferredTabId);
      if (preferredTab?.id) {
        await setLastActiveTab(preferredTab.id);
        return preferredTab.id;
      }
    }

    if (lastActiveTabId != null) {
      const current = await getTab(lastActiveTabId);
      if (current?.id) {
        return current.id;
      }
    }

    return refreshActiveTabFromBrowser();
  }

  function filenameWithExtension(baseName: string, extension: string): string {
    const trimmedBaseName = trimFilename(baseName || "") || "resource";
    const normalizedExt = String(extension || "").trim().replace(/^\./, "").toLowerCase();
    if (!normalizedExt) {
      return trimmedBaseName;
    }
    if (fileExtension(trimmedBaseName) === normalizedExt) {
      return trimmedBaseName;
    }
    return `${trimmedBaseName}.${normalizedExt}`;
  }

  function resolveBridgeFilename(payload: BridgeResourcePayload): string {
    const explicit = trimFilename(payload.filename || "");
    if (explicit) {
      return explicit;
    }

    const fromUrl = trimFilename(filenameFromUrl(payload.url) || "");
    const ext = String(payload.ext || "").trim();
    if (fromUrl) {
      return ext ? filenameWithExtension(fromUrl, ext) : fromUrl;
    }

    return ext ? filenameWithExtension("resource", ext) : "resource";
  }

  async function resolveBridgeResourceTabId(sender: chrome.runtime.MessageSender, href?: string): Promise<number | null> {
    const normalizedHref = String(href ?? "").trim();
    if (normalizedHref) {
      const matchedTabId = await resolveTabIdFromPageUrl(normalizedHref);
      if (matchedTabId != null) {
        return matchedTabId;
      }
    }

    if (sender.tab?.id) {
      return sender.tab.id;
    }

    return resolveActiveTabId();
  }

  async function resolveNetworkResourceTabId(details: chrome.webRequest.OnResponseStartedDetails): Promise<number | null> {
    if (details.tabId > 0) {
      return details.tabId;
    }

    const snapshotTabId = headerSnapshotsByUrl.get(details.url)?.tabId;
    if (snapshotTabId != null) {
      return snapshotTabId;
    }

    const matchedTabId = await resolveTabIdFromPageUrl(details.initiator ?? "");
    if (matchedTabId != null) {
      return matchedTabId;
    }

    return resolveActiveTabId();
  }

  function buildResourceId(tabId: number, url: string): string {
    return `${tabId}:${normalizeResourceUrl(url)}`;
  }

  function bucketForTab(tabId: number): ResourceBucket {
    const existing = resourceCache.get(tabId);
    if (existing) {
      return existing;
    }

    const bucket = new Map<string, CapturedResource>();
    resourceCache.set(tabId, bucket);
    return bucket;
  }

  function trimBucket(tabId: number) {
    const bucket = resourceCache.get(tabId);
    if (!bucket || bucket.size <= RESOURCE_LIMIT) {
      return;
    }

    const keepIds = new Set(sortResources(bucket.values()).slice(0, RESOURCE_LIMIT).map((resource) => resource.id));
    for (const resourceId of bucket.keys()) {
      if (keepIds.has(resourceId)) {
        continue;
      }
      bucket.delete(resourceId);
      resourcesById.delete(resourceId);
    }
  }

  function cacheResource(resource: CapturedResource) {
    const normalized = normalizeCapturedResource(resource);
    const bucket = bucketForTab(normalized.tabId);
    const existing = bucket.get(normalized.id);
    const merged: CapturedResource = existing
      ? {
          ...existing,
          ...normalized,
          pageTitle: normalized.pageTitle || existing.pageTitle,
          pageUrl: normalized.pageUrl || existing.pageUrl,
          filename: normalized.filename || existing.filename,
          mime: normalized.mime || existing.mime,
          size: normalized.size > 0 ? normalized.size : existing.size,
          supportsRange: normalized.supportsRange || existing.supportsRange,
          referer: normalized.referer || existing.referer,
          requestHeaders:
            Object.keys(normalized.requestHeaders).length > 0
              ? normalized.requestHeaders
              : existing.requestHeaders,
          capturedAt: Math.max(existing.capturedAt, normalized.capturedAt),
          sentToDesktopAt: existing.sentToDesktopAt ?? normalized.sentToDesktopAt,
        }
      : normalized;

    bucket.set(merged.id, merged);
    resourcesById.set(merged.id, merged);
    trimBucket(normalized.tabId);
    scheduleBridgeStatePersist();
  }

  function findResourceById(resourceId: string): CapturedResource | null {
    return resourcesById.get(resourceId) ?? null;
  }

  function findResourceByUrl(rawUrl: string): CapturedResource | null {
    const normalizedUrl = normalizeResourceUrl(rawUrl);
    let matched: CapturedResource | null = null;
    for (const resource of resourcesById.values()) {
      if (normalizeResourceUrl(resource.url) !== normalizedUrl) {
        continue;
      }
      if (matched == null || resource.capturedAt > matched.capturedAt) {
        matched = resource;
      }
    }
    return matched;
  }

  function markResourceSent(resourceId: string) {
    const resource = resourcesById.get(resourceId);
    if (!resource) {
      return;
    }
    resource.sentToDesktopAt = Date.now();
    scheduleBridgeStatePersist();
  }

  function rememberHeaderSnapshot(
    url: string,
    headers: Record<string, string>,
    tabId: number | null,
    supportsRange: boolean,
  ) {
    const normalized = normalizeHeaders(headers);
    if (Object.keys(normalized).length === 0 && !supportsRange) {
      return;
    }
    headerSnapshotsByUrl.set(url, {
      url,
      headers: normalized,
      capturedAt: Date.now(),
      tabId,
      supportsRange,
    });
    pruneHeaderSnapshots();
    scheduleBridgeStatePersist();
  }

  function resolveHeaderSnapshot(url: string): BridgeHeaderSnapshot | null {
    pruneHeaderSnapshots();
    return headerSnapshotsByUrl.get(url) ?? null;
  }

  function resolveHeadersForDownload(url: string): Record<string, string> {
    return { ...(resolveHeaderSnapshot(url)?.headers ?? {}) };
  }

  function otherResourcesForTab(activeTabId: number | null): CapturedResource[] {
    const result: CapturedResource[] = [];
    for (const [tabId, bucket] of resourceCache.entries()) {
      if (activeTabId != null && tabId === activeTabId) {
        continue;
      }
      result.push(...bucket.values());
    }
    return sortResources(result);
  }

  function deriveMergeOutputTitle(resources: CapturedResource[]): string {
    const pageTitle = String(resources[0]?.pageTitle || "").trim();
    if (pageTitle) {
      return pageTitle;
    }

    const firstFileName = trimFilename(resources[0]?.filename || filenameFromUrl(resources[0]?.url || ""));
    if (firstFileName) {
      const extension = fileExtension(firstFileName);
      return extension ? firstFileName.slice(0, -(extension.length + 1)) : firstFileName;
    }

    return "merged-media";
  }

  async function downloadResourceViaBrowser(resource: CapturedResource): Promise<void> {
    const filename = resolveBridgeFilename({
      url: resource.url,
      filename: resource.filename,
    });

    return new Promise((resolve, reject) => {
      chrome.downloads.download(
        {
          url: resource.url,
          filename,
        },
        (downloadId) => {
          const lastError = chrome.runtime.lastError;
          if (lastError) {
            reject(new Error(lastError.message));
            return;
          }
          if (typeof downloadId !== "number") {
            reject(new Error("浏览器未返回下载任务"));
            return;
          }
          resolve();
        },
      );
    });
  }

  async function loadPersistentState() {
    const bridgeState = await bridgeStorageGet<{
      [BRIDGE_RESOURCE_CACHE_KEY]: Record<string, CapturedResource[]>;
      [BRIDGE_HEADER_SNAPSHOTS_KEY]: BridgeHeaderSnapshot[];
      [BRIDGE_LAST_ACTIVE_TAB_KEY]: number;
    }>({
      [BRIDGE_RESOURCE_CACHE_KEY]: {},
      [BRIDGE_HEADER_SNAPSHOTS_KEY]: [],
      [BRIDGE_LAST_ACTIVE_TAB_KEY]: 0,
    });

    resourceCache.clear();
    resourcesById.clear();
    for (const [tabIdText, resources] of Object.entries(bridgeState[BRIDGE_RESOURCE_CACHE_KEY] ?? {})) {
      const tabId = Number(tabIdText);
      if (!Number.isInteger(tabId) || tabId <= 0 || !Array.isArray(resources)) {
        continue;
      }
      const bucket = new Map<string, CapturedResource>();
      for (const resource of sortResources(resources.map(normalizeCapturedResource)).slice(0, RESOURCE_LIMIT)) {
        bucket.set(resource.id, resource);
        resourcesById.set(resource.id, resource);
      }
      resourceCache.set(tabId, bucket);
    }

    headerSnapshotsByUrl.clear();
    for (const snapshot of bridgeState[BRIDGE_HEADER_SNAPSHOTS_KEY] ?? []) {
      const normalized = normalizeBridgeHeaderSnapshot(snapshot);
      if (!normalized.url) {
        continue;
      }
      headerSnapshotsByUrl.set(normalized.url, normalized);
    }
    pruneHeaderSnapshots();

    lastActiveTabId = Number(bridgeState[BRIDGE_LAST_ACTIVE_TAB_KEY] ?? 0) || null;
    bridgeStateReady = true;
  }

  async function capturePageResource(sender: chrome.runtime.MessageSender, payload: BridgeResourcePayload) {
    const tabId = await resolveBridgeResourceTabId(sender, payload.href);
    if (!tabId || !isBridgeResourceUrl(payload.url)) {
      return;
    }

    const tab = await getTab(tabId);
    const headers = normalizeHeaders(payload.requestHeaders);
    const filename = resolveBridgeFilename(payload);
    const mime = String(payload.mime ?? "").toLowerCase();

    cacheResource({
      id: buildResourceId(tabId, payload.url),
      tabId,
      url: payload.url,
      pageTitle: tab?.title ?? "",
      pageUrl: payload.href ?? tab?.url ?? "",
      filename,
      mime,
      size: 0,
      supportsRange: false,
      referer: headers.referer ?? payload.href ?? tab?.url ?? "",
      requestHeaders: headers,
      capturedAt: Date.now(),
    });
  }

  async function captureNetworkResource(details: chrome.webRequest.OnResponseStartedDetails) {
    const responseMeta = getResponseHeadersValue(details.responseHeaders);
    if (!shouldCaptureCatCatchResponse(details, responseMeta)) {
      headersByRequestId.delete(details.requestId);
      rangeRequestIds.delete(details.requestId);
      return;
    }

    const tabId = await resolveNetworkResourceTabId(details);
    const headerSnapshot = resolveHeaderSnapshot(details.url);
    const requestHadRange = rangeRequestIds.has(details.requestId) || Boolean(headerSnapshot?.supportsRange);
    const requestHeaders = normalizeHeaders(headersByRequestId.get(details.requestId) ?? headerSnapshot?.headers ?? {});
    headersByRequestId.delete(details.requestId);
    rangeRequestIds.delete(details.requestId);

    if (!tabId) {
      return;
    }

    const tab = await getTab(tabId);
    const filename = resolveNetworkResourceFilename(details.url, responseMeta);
    const referer = requestHeaders.referer || details.initiator || tab?.url || "";
    const normalizedRequestHeaders = referer ? { ...requestHeaders, referer } : requestHeaders;

    cacheResource({
      id: buildResourceId(tabId, details.url),
      tabId,
      url: details.url,
      pageTitle: tab?.title ?? "",
      pageUrl: details.initiator ?? tab?.url ?? "",
      filename,
      mime: responseMeta.type,
      size: responseMeta.size,
      supportsRange:
        responseMeta.supportsRange
        || details.statusCode === 206
        || requestHadRange,
      referer,
      requestHeaders: normalizedRequestHeaders,
      capturedAt: Date.now(),
    });
  }

  function shouldHandoffBrowserDownload(
    downloadItem: chrome.downloads.DownloadItem,
    interceptDownloads: boolean,
  ): boolean {
    const finalUrl = downloadItem.finalUrl || downloadItem.url;
    return Boolean(interceptDownloads && options.isDesktopReady() && isCapturableUrl(finalUrl));
  }

  async function handoffBrowserDownload(downloadItem: chrome.downloads.DownloadItem) {
    const finalUrl = downloadItem.finalUrl || downloadItem.url;
    const matchedResource = findResourceByUrl(finalUrl);
    const resolvedFilename =
      trimFilename(downloadItem.filename)
      || trimFilename(matchedResource?.filename ?? "")
      || trimFilename(filenameFromUrl(finalUrl))
      || "resource";

    const headers = resolveHeadersForDownload(finalUrl);
    if (downloadItem.referrer && !headers.referer) {
      headers.referer = downloadItem.referrer;
    }

    try {
      const result = await options.sendDesktopRequest<DesktopRequestResult>({
        type: "create_task",
        source: "download",
        title: resolvedFilename,
        payload: {
          url: finalUrl,
          headers,
          filename: resolvedFilename,
          size:
            typeof downloadItem.totalBytes === "number" && downloadItem.totalBytes > 0
              ? downloadItem.totalBytes
              : matchedResource?.size ?? 0,
          supportsRange: matchedResource?.supportsRange ?? downloadItem.canResume === true,
        },
      });
      if (result.ok) {
        await openActionPopup();
      }
    } catch {
      // Browser download has already been intercepted; ignore desktop handoff failures here.
    }
  }

  async function sendHttpResourceToDesktop(resource: CapturedResource): Promise<DesktopRequestResult> {
    try {
      const result = await options.sendDesktopRequest<DesktopRequestResult>({
        type: "create_task",
        source: "resource",
        title: resource.filename,
        payload: {
          url: resource.url,
          headers: resource.requestHeaders,
          filename: resource.filename,
          size: resource.size,
          supportsRange: resource.supportsRange,
        },
      });

      if (result.ok) {
        markResourceSent(resource.id);
        return {
          ...result,
          message: result.message || "资源已发送到 Ghost Downloader",
        };
      }
      return result;
    } catch (error) {
      return {
        ok: false,
        message: error instanceof Error ? error.message : "发送资源失败",
      };
    }
  }

  async function sendResource(resourceId: string): Promise<DesktopRequestResult> {
    const resource = findResourceById(resourceId);
    if (!resource) {
      return { ok: false, message: "资源不存在" };
    }

    try {
      if (resource.url.startsWith("blob:")) {
        await downloadResourceViaBrowser(resource);
        markResourceSent(resource.id);
        return {
          ok: true,
          message: "资源已交给浏览器下载",
        };
      }

      return await sendHttpResourceToDesktop(resource);
    } catch (error) {
      return {
        ok: false,
        message: error instanceof Error ? error.message : "发送资源失败",
      };
    }
  }

  async function mergeResources(resourceIds: string[]): Promise<DesktopRequestResult> {
    const ids = [...new Set(resourceIds.map((value) => String(value || "")).filter(Boolean))];
    const resources = ids
      .map((resourceId) => findResourceById(resourceId))
      .filter((resource): resource is CapturedResource => resource != null);

    if (resources.length !== 2) {
      return {
        ok: false,
        message: "在线合并暂时只支持选中 2 个资源",
      };
    }

    if (!canUseOnlineMergeSelection(resources)) {
      return {
        ok: false,
        message: "当前选中的资源不符合在线合并条件",
      };
    }

    const orderedResources = sortResourcesForOnlineMerge(resources);

    try {
      const result = await options.sendDesktopRequest<DesktopRequestResult>({
        type: "create_task",
        source: "resource_merge",
        title: deriveMergeOutputTitle(orderedResources),
        payload: {
          resources: orderedResources.map((resource) => ({
            url: resource.url,
            filename: resource.filename,
            mime: resource.mime,
            size: resource.size,
            headers: resource.requestHeaders,
            pageTitle: resource.pageTitle,
            supportsRange: resource.supportsRange,
          })),
        },
      });

      if (result.ok) {
        orderedResources.forEach((resource) => markResourceSent(resource.id));
        return {
          ...result,
          message: result.message || "在线合并任务已发送到 Ghost Downloader",
        };
      }
      return result;
    } catch (error) {
      return {
        ok: false,
        message: error instanceof Error ? error.message : "在线合并失败",
      };
    }
  }

  function buildPopupStateData(resolvedTabId: number | null, activeTab: chrome.tabs.Tab | null): Pick<
    PopupStatePayload,
    "resourceState" | "resourceStateMessage" | "currentResources" | "otherResources" | "activePageDomain"
  > {
    const canCaptureCurrentTab = isCapturableTab(activeTab);
    let resourceState: PopupStatePayload["resourceState"] = "ready";
    let resourceStateMessage = "等待 cat-catch 捕获资源";
    if (!bridgeStateReady) {
      resourceState = "restoring";
      resourceStateMessage = "正在恢复 cat-catch 已捕获的资源";
    } else if (!canCaptureCurrentTab) {
      resourceState = "unavailable";
      resourceStateMessage = "当前标签页不支持 cat-catch 资源桥接";
    }

    return {
      resourceState,
      resourceStateMessage,
      currentResources: resolvedTabId == null ? [] : sortResources(resourceCache.get(resolvedTabId)?.values() ?? []),
      otherResources: otherResourcesForTab(resolvedTabId),
      activePageDomain: domainFromUrl(activeTab?.url ?? ""),
    };
  }

  function handleTabRemoved(tabId: number) {
    clearResourcesForTab(tabId);
    clearHeaderSnapshotsForTab(tabId);
    if (lastActiveTabId === tabId) {
      void setLastActiveTab(null);
    }
  }

  function handleNavigationCommitted(details: chrome.webNavigation.WebNavigationTransitionCallbackDetails) {
    if (details.tabId <= 0 || details.frameId !== 0) {
      return;
    }
    clearResourcesForTab(details.tabId);
    clearHeaderSnapshotsForTab(details.tabId);
  }

  function handleRequestHeaders(details: chrome.webRequest.OnSendHeadersDetails) {
    const headers = parseHeaderList(details.requestHeaders);
    headersByRequestId.set(details.requestId, headers);
    const supportsRange = hasRangeHeader(details.requestHeaders);
    if (supportsRange) {
      rangeRequestIds.add(details.requestId);
    } else {
      rangeRequestIds.delete(details.requestId);
    }
    rememberHeaderSnapshot(details.url, headers, details.tabId > 0 ? details.tabId : lastActiveTabId, supportsRange);
  }

  function clearRequestHeaders(requestId: string) {
    headersByRequestId.delete(requestId);
    rangeRequestIds.delete(requestId);
  }

  return {
    buildPopupStateData,
    captureNetworkResource,
    capturePageResource,
    clearRequestHeaders,
    handoffBrowserDownload,
    shouldHandoffBrowserDownload,
    handleNavigationCommitted,
    handleRequestHeaders,
    handleTabRemoved,
    loadPersistentState,
    refreshActiveTabFromBrowser,
    resolveActiveTabId,
    mergeResources,
    sendResource,
    setLastActiveTab,
  };
}
