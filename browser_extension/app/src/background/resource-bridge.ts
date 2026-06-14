import type {CapturedResource, DesktopRequestResult, ResourceCollectionState} from "../shared/types";
import {
    canUseOnlineMergeSelection,
    domainFromUrl,
    fileExtension,
    filenameFromUrl,
    mimeFromUrl,
    sortResourcesForOnlineMerge,
} from "../shared/utils";
import {isCatCatchMedia} from "../shared/cat-catch";
import type {Selection} from "../page-media/types";
import {
    BRIDGE_HEADER_SNAPSHOTS_KEY,
    BRIDGE_LAST_ACTIVE_TAB_KEY,
    BRIDGE_PERSIST_DEBOUNCE_MS,
    BRIDGE_RESOURCE_CACHE_KEY,
    HEADER_EXPIRATION_MS,
    HEADER_SNAPSHOT_LIMIT,
    RESOURCE_LIMIT,
} from "./constants";
import {bridgeStorageSet, findTab, loadFromBridgeStorage, openActionPopup, queryTabs,} from "./chrome-helpers";
import {buildDownloadSpec, filenameForDesktop, resolveCapturedFilename} from "./download-spec";

type HeaderSnapshot = {
  url: string;
  headers: Record<string, string>;
  capturedAt: number;
  tabId: number | null;
  supportsRange: boolean;
};

// From cat-catch's addMedia path — DOM-side discovery pushed up by capturePageResource.
type CapturePayload = {
  url: string;
  href?: string;
  filename?: string;
  mime?: string;
  ext?: string;
  poster?: string;
  resourceUrls?: string[];
  requestHeaders?: Record<string, string>;
};

// From overlay click — strategy already disambiguated against the right <video>, so
// background just augments with headers and dispatches.
type ClickPayload = {
  selection: Selection;
  href: string;
  title: string;
};

type NetworkResponseMeta = {
  size: number;
  mime: string;
  filename: string;
  supportsRange: boolean;
};

type DesktopRequestSender = <T extends DesktopRequestResult>(payload: Record<string, unknown>) => Promise<T>;
type ResourceBucket = Map<string, CapturedResource>;

const HEADER_WHITELIST = new Set([
  "accept",
  "accept-language",
  "authorization",
  "cookie",
  "origin",
  "referer",
  "sec-ch-ua",
  "sec-ch-ua-arch",
  "sec-ch-ua-bitness",
  "sec-ch-ua-full-version",
  "sec-ch-ua-full-version-list",
  "sec-ch-ua-mobile",
  "sec-ch-ua-model",
  "sec-ch-ua-platform",
  "sec-ch-ua-platform-version",
  "sec-fetch-dest",
  "sec-fetch-mode",
  "sec-fetch-site",
  "user-agent",
  "priority",
]);

export function createResourceBridge(options: {
  sendDesktopRequest: DesktopRequestSender;
}) {
  let bridgePersistTimer: number | null = null;
  let restoredFromStorage = false;
  let lastActiveTabId: number | null = null;

  const resourceCache = new Map<number, ResourceBucket>();
  const resourcesById = new Map<string, CapturedResource>();
  const headerSnapshotsByUrl = new Map<string, HeaderSnapshot>();

  // Lets resolveResourceForUrl wait when click races ahead of webRequest (SW restart).
  const resourceCacheAwaiters = new Map<string, Set<(resource: CapturedResource) => void>>();
  function notifyResourceCached(resource: CapturedResource): void {
    const key = resource.id;
    const set = resourceCacheAwaiters.get(key);
    if (!set || set.size === 0) { return; }
    resourceCacheAwaiters.delete(key);
    for (const resolver of set) {
      try { resolver(resource); } catch { /* swallow */ }
    }
  }
  function awaitResourceCached(key: string, timeoutMs: number): Promise<CapturedResource | null> {
    return new Promise((resolve) => {
      let set = resourceCacheAwaiters.get(key);
      if (!set) { set = new Set(); resourceCacheAwaiters.set(key, set); }
      let settled = false;
      const finish = (value: CapturedResource | null) => {
        if (settled) { return; }
        settled = true;
        set?.delete(resolver);
        if (set && set.size === 0) { resourceCacheAwaiters.delete(key); }
        clearTimeout(timer);
        resolve(value);
      };
      const resolver = (resource: CapturedResource) => finish(resource);
      set.add(resolver);
      const timer = setTimeout(() => finish(null), timeoutMs);
    });
  }

  function selectAllowedHeaders(headers: Record<string, string> | undefined): Record<string, string> {
    const result: Record<string, string> = {};
    for (const [key, value] of Object.entries(headers ?? {})) {
      const name = key.trim().toLowerCase();
      if (!HEADER_WHITELIST.has(name)) { continue; }
      const text = value.trim();
      if (!text) { continue; }
      result[name] = text;
    }
    return result;
  }

  function basenameOf(path: string): string {
    const trimmed = path.trim();
    if (!trimmed) { return ""; }
    const slashIndex = Math.max(trimmed.lastIndexOf("/"), trimmed.lastIndexOf("\\"));
    return slashIndex >= 0 ? trimmed.slice(slashIndex + 1) : trimmed;
  }

  function isCapturableUrl(url: string): boolean {
    return /^https?:/i.test(url);
  }

  function sortResources(resources: Iterable<CapturedResource>): CapturedResource[] {
    return [...resources].sort((left, right) => right.capturedAt - left.capturedAt);
  }

  function urlWithoutHash(value: string, allowBlob = false): string {
    if (!value) { return ""; }
    if (allowBlob && value.startsWith("blob:")) { return value; }
    try {
      const url = new URL(value);
      url.hash = "";
      return url.toString();
    } catch {
      return value.split("#", 1)[0] ?? value;
    }
  }

  // Schema round-trips through JSON cleanly; only the header whitelist needs re-running.
  function resourceFromStorage(resource: CapturedResource): CapturedResource {
    return { ...resource, requestHeaders: selectAllowedHeaders(resource.requestHeaders) };
  }

  function headerSnapshotFromStorage(snapshot: HeaderSnapshot): HeaderSnapshot {
    return { ...snapshot, headers: selectAllowedHeaders(snapshot.headers) };
  }

  function toResponseMeta(headers: chrome.webRequest.HttpHeader[] | undefined): NetworkResponseMeta {
    const meta: NetworkResponseMeta = { size: 0, mime: "", filename: "", supportsRange: false };
    let contentLengthSize = 0;
    let contentRangeSize = 0;
    for (const header of headers ?? []) {
      const name = (header.name ?? "").toLowerCase();
      const value = (header.value ?? "").trim();
      if (name === "content-length") {
        const size = Number.parseInt(value, 10);
        contentLengthSize = Number.isFinite(size) && size > 0 ? size : contentLengthSize;
      } else if (name === "content-type") {
        meta.mime = value.split(";")[0]?.trim().toLowerCase() ?? "";
      } else if (name === "content-disposition") {
        const match = /filename\*\s*=\s*UTF-8''([^;]+)|filename\s*=\s*"?([^";]+)"?/i.exec(value);
        const filename = match?.[1] ?? match?.[2] ?? "";
        try {
          meta.filename = basenameOf(decodeURIComponent(filename));
        } catch {
          meta.filename = basenameOf(filename);
        }
      } else if (name === "accept-ranges") {
        meta.supportsRange = value.toLowerCase().includes("bytes");
      } else if (name === "content-range") {
        const size = Number.parseInt(value.split("/")[1] ?? "", 10);
        contentRangeSize = Number.isFinite(size) && size > 0 ? size : contentRangeSize;
        meta.supportsRange = true;
      }
    }
    meta.size = contentRangeSize || contentLengthSize;
    return meta;
  }

  function shouldCaptureNetworkResource(details: chrome.webRequest.OnResponseStartedDetails, meta: NetworkResponseMeta): boolean {
    if (!isCapturableUrl(details.url)) {
      return false;
    }
    const extension = fileExtension(meta.filename || filenameFromUrl(details.url));
    return details.type === "media" || isCatCatchMedia(extension, meta.mime);
  }

  function shouldCaptureRequestResource(details: chrome.webRequest.OnSendHeadersDetails): boolean {
    if (!isCapturableUrl(details.url)) {
      return false;
    }
    return details.type === "media" || isCatCatchMedia(fileExtension(filenameFromUrl(details.url)), mimeFromUrl(details.url));
  }

  function urlsSharePathPrefix(left: string, right: string): boolean {
    const normalizedLeft = urlWithoutHash(left);
    const normalizedRight = urlWithoutHash(right);
    if (!normalizedLeft || !normalizedRight) {
      return false;
    }
    return normalizedLeft === normalizedRight || normalizedLeft.startsWith(normalizedRight) || normalizedRight.startsWith(normalizedLeft);
  }

  async function resolveTabIdFromPageUrl(pageUrl: string): Promise<number | null> {
    const normalizedPageUrl = urlWithoutHash(pageUrl);
    if (!normalizedPageUrl) {
      return null;
    }

    const tabs = await queryTabs({});
    const exactMatch = tabs.find((tab) => tab.id && tab.url && urlsSharePathPrefix(tab.url, normalizedPageUrl));
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
      const preferredTab = await findTab(preferredTabId);
      if (preferredTab?.id) {
        await setLastActiveTab(preferredTab.id);
        return preferredTab.id;
      }
    }

    const activeTabId = await refreshActiveTabFromBrowser();
    if (activeTabId != null) {
      return activeTabId;
    }

    if (lastActiveTabId != null) {
      const current = await findTab(lastActiveTabId);
      if (current?.id) {
        return current.id;
      }
    }

    return null;
  }

  async function resolveBridgeResourceTabId(sender: chrome.runtime.MessageSender, href?: string): Promise<number | null> {
    if (sender.tab?.id) {
      await setLastActiveTab(sender.tab.id);
      return sender.tab.id;
    }

    const normalizedHref = href?.trim() ?? "";
    if (normalizedHref) {
      const matchedTabId = await resolveTabIdFromPageUrl(normalizedHref);
      if (matchedTabId != null) {
        return matchedTabId;
      }
    }

    return resolveActiveTabId();
  }

  async function resolveNetworkResourceTabId(details: chrome.webRequest.OnResponseStartedDetails): Promise<number | null> {
    if (details.tabId > 0) {
      return details.tabId;
    }
    const snapshotTabId = resolveHeaderSnapshot(details.url)?.tabId;
    if (snapshotTabId != null) {
      return snapshotTabId;
    }
    const matchedTabId = await resolveTabIdFromPageUrl(details.initiator ?? "");
    return matchedTabId ?? resolveActiveTabId();
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
    const bucket = bucketForTab(resource.tabId);
    const existing = bucket.get(resource.id);
    const merged: CapturedResource = existing
      ? {
          ...existing,
          ...resource,
          pageTitle: resource.pageTitle || existing.pageTitle,
          pageUrl: resource.pageUrl || existing.pageUrl,
          filename: resource.filename || existing.filename,
          mime: resource.mime || existing.mime,
          size: resource.size > 0 ? resource.size : existing.size,
          supportsRange: resource.supportsRange || existing.supportsRange,
          referer: resource.referer || existing.referer,
          // Fresh cookies/auth/sec-* override stale ones (per-key, like every field above).
          requestHeaders: {
            ...existing.requestHeaders,
            ...resource.requestHeaders,
          },
          capturedAt: Math.max(existing.capturedAt, resource.capturedAt),
          sentToDesktopAt: existing.sentToDesktopAt ?? resource.sentToDesktopAt,
        }
      : resource;

    bucket.set(merged.id, merged);
    resourcesById.set(merged.id, merged);
    notifyResourceCached(merged);
    const mergedUrl = urlWithoutHash(merged.url, true);
    if (mergedUrl && (merged.size > 0 || merged.mime || merged.supportsRange)) {
      for (const resource of resourcesById.values()) {
        if (resource.id === merged.id || !resource.id.endsWith(`:${mergedUrl}`)) {
          continue;
        }
        resource.size = merged.size > 0 ? merged.size : resource.size;
        resource.mime = merged.mime || resource.mime;
        resource.filename = resource.filename && resource.filename !== "resource" ? resource.filename : merged.filename;
        resource.supportsRange = merged.supportsRange || resource.supportsRange;
      }
    }
    trimBucket(resource.tabId);
    scheduleBridgeStatePersist();
  }

  function findResourceByUrl(url: string, tabId?: number): CapturedResource | null {
    const resourceIdSuffix = `:${urlWithoutHash(url, true)}`;
    let matched: CapturedResource | null = null;
    const resources = tabId == null ? resourcesById.values() : (resourceCache.get(tabId)?.values() ?? []);
    for (const resource of resources) {
      if (!resource.id.endsWith(resourceIdSuffix)) {
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
    const existing = headerSnapshotsByUrl.get(url);
    const mergedHeaders = {
      ...(existing?.headers ?? {}),
      ...headers,
    };
    const mergedSupportsRange = supportsRange || Boolean(existing?.supportsRange);
    if (Object.keys(mergedHeaders).length === 0 && !mergedSupportsRange) {
      return;
    }
    headerSnapshotsByUrl.set(url, {
      url,
      headers: mergedHeaders,
      capturedAt: Date.now(),
      tabId: tabId ?? existing?.tabId ?? null,
      supportsRange: mergedSupportsRange,
    });
    pruneHeaderSnapshots();
    scheduleBridgeStatePersist();
  }

  function resolveHeaderSnapshot(url: string): HeaderSnapshot | null {
    pruneHeaderSnapshots();
    return headerSnapshotsByUrl.get(url) ?? null;
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

  function mergeOutputTitle(resources: CapturedResource[]): string {
    const pageTitle = (resources[0]?.pageTitle ?? "").trim();
    if (pageTitle) {
      return pageTitle;
    }

    const firstFileName = basenameOf(resources[0]?.filename || filenameFromUrl(resources[0]?.url || ""));
    if (firstFileName) {
      const extension = fileExtension(firstFileName);
      return extension ? firstFileName.slice(0, -(extension.length + 1)) : firstFileName;
    }

    return "merged-media";
  }

  async function downloadResourceViaBrowser(resource: CapturedResource): Promise<void> {
    const filename = filenameForDesktop(resource);

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
    const bridgeState = await loadFromBridgeStorage<{
      [BRIDGE_RESOURCE_CACHE_KEY]: Record<string, CapturedResource[]>;
      [BRIDGE_HEADER_SNAPSHOTS_KEY]: HeaderSnapshot[];
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
      for (const resource of sortResources(resources.map(resourceFromStorage)).slice(0, RESOURCE_LIMIT)) {
        bucket.set(resource.id, resource);
        resourcesById.set(resource.id, resource);
      }
      resourceCache.set(tabId, bucket);
    }

    headerSnapshotsByUrl.clear();
    for (const snapshot of bridgeState[BRIDGE_HEADER_SNAPSHOTS_KEY] ?? []) {
      const normalized = headerSnapshotFromStorage(snapshot);
      if (!normalized.url) {
        continue;
      }
      headerSnapshotsByUrl.set(normalized.url, normalized);
    }
    pruneHeaderSnapshots();

    lastActiveTabId = Number(bridgeState[BRIDGE_LAST_ACTIVE_TAB_KEY] ?? 0) || null;
    restoredFromStorage = true;
  }

  function cacheUrlResource(
    url: string,
    tabId: number,
    tab: chrome.tabs.Tab | null,
    pageUrl: string,
    parts: {
      filename: string;
      mime: string;
      size: number;
      supportsRange: boolean;
      extraHeaders?: Record<string, string>;
    },
  ) {
    const headerSnapshot = resolveHeaderSnapshot(url);
    const headers = {
      ...(headerSnapshot?.headers ?? {}),
      ...(parts.extraHeaders ?? {}),
    };
    const referer = headers.referer || pageUrl || tab?.url || "";
    if (referer) { headers.referer = referer; }

    cacheResource({
      id: `${tabId}:${urlWithoutHash(url, true)}`,
      tabId,
      url,
      pageTitle: tab?.title ?? "",
      pageUrl: pageUrl || tab?.url || "",
      filename: parts.filename,
      mime: parts.mime,
      size: parts.size,
      supportsRange: parts.supportsRange || Boolean(headerSnapshot?.supportsRange),
      referer,
      requestHeaders: headers,
      capturedAt: Date.now(),
    });
  }

  // Cross-origin opaque requests get the literal string "null" here.
  function initiatorOf(details: { initiator?: string }): string {
    return details.initiator && details.initiator !== "null" ? details.initiator : "";
  }

  async function capturePageResource(sender: chrome.runtime.MessageSender, payload: CapturePayload) {
    const tabId = await resolveBridgeResourceTabId(sender, payload.href);
    if (!tabId || !/^(https?:|blob:)/i.test(payload.url)) {
      return;
    }

    const tab = await findTab(tabId);
    cacheUrlResource(payload.url, tabId, tab, payload.href ?? tab?.url ?? "", {
      filename: resolveCapturedFilename(payload),
      mime: payload.mime?.toLowerCase() || mimeFromUrl(payload.url),
      size: 0,
      supportsRange: false,
      extraHeaders: selectAllowedHeaders(payload.requestHeaders),
    });
  }

  async function captureNetworkResource(details: chrome.webRequest.OnResponseStartedDetails) {
    const meta = toResponseMeta(details.responseHeaders);
    meta.mime = mimeFromUrl(details.url) || meta.mime;
    const responseSupportsRange = meta.supportsRange || details.statusCode === 206;
    if (responseSupportsRange && isCapturableUrl(details.url)) {
      rememberHeaderSnapshot(details.url, {}, details.tabId > 0 ? details.tabId : lastActiveTabId, true);
    }

    if (!shouldCaptureNetworkResource(details, meta)) {
      return;
    }

    const tabId = await resolveNetworkResourceTabId(details);
    if (!tabId) {
      return;
    }

    const tab = await findTab(tabId);
    cacheUrlResource(details.url, tabId, tab, initiatorOf(details), {
      filename: meta.filename || basenameOf(filenameFromUrl(details.url)) || "resource",
      mime: meta.mime,
      size: meta.size,
      supportsRange: responseSupportsRange,
    });
  }

  async function captureRequestResource(details: chrome.webRequest.OnSendHeadersDetails) {
    if (!shouldCaptureRequestResource(details)) {
      return;
    }

    const tabId = details.tabId > 0 ? details.tabId : (lastActiveTabId ?? await resolveActiveTabId());
    if (!tabId) {
      return;
    }

    const tab = await findTab(tabId);
    cacheUrlResource(details.url, tabId, tab, initiatorOf(details), {
      filename: basenameOf(filenameFromUrl(details.url)) || "resource",
      mime: mimeFromUrl(details.url),
      size: 0,
      supportsRange: false,
    });
  }

  async function handoffBrowserDownload(downloadItem: chrome.downloads.DownloadItem) {
    const finalUrl = downloadItem.finalUrl || downloadItem.url;
    const matchedResource = findResourceByUrl(finalUrl) ?? findResourceByUrl(downloadItem.url);
    const resolvedFilename =
      basenameOf(downloadItem.filename)
      || basenameOf(matchedResource?.filename ?? "")
      || basenameOf(filenameFromUrl(finalUrl))
      || "resource";

    const headerSnapshot = resolveHeaderSnapshot(finalUrl) ?? resolveHeaderSnapshot(downloadItem.url);
    const headers = { ...(headerSnapshot?.headers ?? {}) };
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
          supportsRange: Boolean(
            matchedResource?.supportsRange
            || headerSnapshot?.supportsRange
            || downloadItem.canResume === true,
          ),
        },
      });
      if (result.ok) {
        await openActionPopup();
      }
    } catch {
      // Browser download was already intercepted — the user already lost it from the
      // browser's download tray, so a desktop handoff failure here is unrecoverable anyway.
    }
  }

  async function sendHttpResourceToDesktop(resource: CapturedResource): Promise<DesktopRequestResult> {
    const spec = buildDownloadSpec(resource);
    try {
      const result = await options.sendDesktopRequest<DesktopRequestResult>({
        type: "create_task",
        source: "resource",
        title: spec.filename,
        payload: spec,
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
    const resource = resourcesById.get(resourceId) ?? null;
    if (!resource) {
      return { ok: false, message: "资源不存在" };
    }

    if (resource.url.startsWith("blob:")) {
      try {
        await downloadResourceViaBrowser(resource);
        markResourceSent(resource.id);
        return { ok: true, message: "资源已交给浏览器下载" };
      } catch (error) {
        return { ok: false, message: error instanceof Error ? error.message : "发送资源失败" };
      }
    }

    return sendHttpResourceToDesktop(resource);
  }

  // Twitter / Bilibili CDNs 403 without Referer; cat-catch's addMedia path doesn't carry one.
  function fillMissingReferer(resource: CapturedResource, fallback: string): void {
    if (!fallback || resource.requestHeaders.referer || resource.referer) { return; }
    resource.requestHeaders = { ...resource.requestHeaders, referer: fallback };
    resource.referer = fallback;
  }

  // Strategy already proved this URL belongs to the active video, so we must dispatch
  // something — desktop range-probes whatever metadata we can't fill in. The synthesized
  // row goes into resourceCache so markResourceSent can find it and a later webRequest
  // event can merge real size/headers into it.
  async function resolveResourceForUrl(url: string, tabId: number, fallbackTitle: string, fallbackPageUrl: string): Promise<CapturedResource> {
    const id = `${tabId}:${urlWithoutHash(url, true)}`;

    const direct = resourceCache.get(tabId)?.get(id);
    if (direct) {
      fillMissingReferer(direct, fallbackPageUrl);
      return direct;
    }

    const waited = await awaitResourceCached(id, 1500);
    if (waited) {
      fillMissingReferer(waited, fallbackPageUrl);
      return waited;
    }

    const snapshot = resolveHeaderSnapshot(url);
    const headers: Record<string, string> = { ...(snapshot?.headers ?? {}) };
    const referer = headers.referer || fallbackPageUrl;
    if (referer) { headers.referer = referer; }
    const synthesized: CapturedResource = {
      id,
      tabId,
      url,
      pageTitle: fallbackTitle,
      pageUrl: fallbackPageUrl,
      filename: basenameOf(filenameFromUrl(url)) || "resource",
      mime: mimeFromUrl(url),
      size: 0,
      supportsRange: Boolean(snapshot?.supportsRange),
      referer,
      requestHeaders: headers,
      capturedAt: Date.now(),
    };
    cacheResource(synthesized);
    console.warn(
      "[GD3 Bridge] resolveResourceForUrl synthesized fallback (no webRequest row within 1500ms)",
      { url: synthesized.url, hasSnapshot: Boolean(snapshot), hasReferer: Boolean(referer) },
    );
    return synthesized;
  }

  async function downloadPageMedia(sender: chrome.runtime.MessageSender, payload: ClickPayload): Promise<DesktopRequestResult> {
    const tabId = await resolveBridgeResourceTabId(sender, payload.href);
    if (!tabId) {
      return { ok: false, message: "当前没有可操作的标签页" };
    }

    const selection = payload.selection;
    if (!selection || typeof selection !== "object") {
      return { ok: false, message: "无效的下载请求" };
    }
    const fallbackPageUrl = payload.href || "";

    if (selection.kind === "single" || selection.kind === "stream") {
      if (!selection.url) {
        return { ok: false, message: "无效的下载请求" };
      }
      const resource = await resolveResourceForUrl(selection.url, tabId, payload.title, fallbackPageUrl);
      const result = await sendHttpResourceToDesktop(resource);
      if (result.ok) { await openActionPopup(); }
      return result;
    }

    if (selection.kind === "merge") {
      if (!selection.video || !selection.audio) {
        return { ok: false, message: "无效的合并请求" };
      }
      const [video, audio] = await Promise.all([
        resolveResourceForUrl(selection.video, tabId, payload.title, fallbackPageUrl),
        resolveResourceForUrl(selection.audio, tabId, payload.title, fallbackPageUrl),
      ]);
      const result = await dispatchMergeResources([video, audio]);
      if (result.ok) { await openActionPopup(); }
      return result;
    }

    return { ok: false, message: "未知的下载请求类型" };
  }

  async function dispatchMergeResources(resources: CapturedResource[]): Promise<DesktopRequestResult> {
    if (resources.length !== 2) {
      return { ok: false, message: "在线合并暂时只支持选中 2 个资源" };
    }
    const ordered = sortResourcesForOnlineMerge(resources);
    try {
      const result = await options.sendDesktopRequest<DesktopRequestResult>({
        type: "create_task",
        source: "resource_merge",
        title: mergeOutputTitle(ordered),
        payload: {
          resources: ordered.map((resource) => ({
            url: resource.url,
            filename: filenameForDesktop(resource),
            mime: resource.mime,
            size: resource.size,
            headers: resource.requestHeaders,
            pageTitle: resource.pageTitle,
            supportsRange: resource.supportsRange,
          })),
        },
      });
      if (result.ok) {
        ordered.forEach((resource) => markResourceSent(resource.id));
        return { ...result, message: result.message || "在线合并任务已发送到 Ghost Downloader" };
      }
      return result;
    } catch (error) {
      return { ok: false, message: error instanceof Error ? error.message : "在线合并失败" };
    }
  }

  async function mergeResources(resourceIds: string[]): Promise<DesktopRequestResult> {
    const ids = [...new Set(resourceIds.filter(Boolean))];
    const resources = ids
      .map((resourceId) => resourcesById.get(resourceId) ?? null)
      .filter((resource): resource is CapturedResource => resource != null);

    if (!canUseOnlineMergeSelection(resources)) {
      return { ok: false, message: "当前选中的资源不符合在线合并条件" };
    }

    return dispatchMergeResources(resources);
  }

  function buildPopupStateData(resolvedTabId: number | null, activeTab: chrome.tabs.Tab | null) {
    const canCaptureCurrentTab = Boolean(activeTab?.url && isCapturableUrl(activeTab.url));
    let resourceState: ResourceCollectionState = "ready";
    let resourceStateMessage = "等待 cat-catch 捕获资源";
    if (!restoredFromStorage) {
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

  function onTabRemoved(tabId: number) {
    clearResourcesForTab(tabId);
    clearHeaderSnapshotsForTab(tabId);
    if (lastActiveTabId === tabId) {
      void setLastActiveTab(null);
    }
  }

  function onNavigationCommitted(details: chrome.webNavigation.WebNavigationTransitionCallbackDetails) {
    if (details.tabId <= 0 || details.frameId !== 0) {
      return;
    }
    clearResourcesForTab(details.tabId);
    clearHeaderSnapshotsForTab(details.tabId);
  }

  function onRequestHeaders(details: chrome.webRequest.OnSendHeadersDetails) {
    const headers = selectAllowedHeaders(Object.fromEntries((details.requestHeaders ?? []).map((header) => [header.name ?? "", header.value ?? ""])));
    const supportsRange = (details.requestHeaders ?? []).some((header) => header.name?.toLowerCase() === "range" && String(header.value ?? "").toLowerCase().startsWith("bytes="));
    rememberHeaderSnapshot(details.url, headers, details.tabId > 0 ? details.tabId : lastActiveTabId, supportsRange);
  }

  return {
    buildPopupStateData,
    captureNetworkResource,
    capturePageResource,
    captureRequestResource,
    downloadPageMedia,
    handoffBrowserDownload,
    onNavigationCommitted,
    onRequestHeaders,
    onTabRemoved,
    loadPersistentState,
    refreshActiveTabFromBrowser,
    resolveActiveTabId,
    mergeResources,
    sendResource,
    setLastActiveTab,
  };
}
