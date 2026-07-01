import type {Resource, CommandResult, ResourceCollectionState} from "../shared/types";
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
} from "./constants";
import {findTab, loadSessionState, openActionPopup, queryTabs, saveSessionState,} from "./chrome-helpers";
import {toResourceTaskOptions, taskNameForResource, resourceNameFromCapture} from "./download-spec";
import {
    ResourceCache,
    selectAllowedHeaders,
    urlWithoutHash,
    type HeaderSnapshot,
} from "./resource-cache";

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

type DesktopRequestSender = <T extends CommandResult>(payload: Record<string, unknown>, timeoutMs?: number) => Promise<T>;

export function createResourceBridge(options: {
  sendDesktopRequest: DesktopRequestSender;
}) {
  let bridgePersistTimer: number | null = null;
  let loadedFromStorage = false;
  let lastActiveTabId: number | null = null;

  const cache = new ResourceCache(scheduleBridgeStateSave);

  function scheduleBridgeStateSave() {
    if (bridgePersistTimer !== null) {
      return;
    }
    bridgePersistTimer = self.setTimeout(() => {
      bridgePersistTimer = null;
      void saveBridgeState();
    }, BRIDGE_PERSIST_DEBOUNCE_MS);
  }

  async function saveBridgeState() {
    const snapshot = cache.toSnapshot();
    await saveSessionState({
      [BRIDGE_RESOURCE_CACHE_KEY]: snapshot.resources,
      [BRIDGE_HEADER_SNAPSHOTS_KEY]: snapshot.headers,
      [BRIDGE_LAST_ACTIVE_TAB_KEY]: lastActiveTabId ?? 0,
    });
  }

  // SW suspension loses all in-memory state; the debounced timer would be abandoned
  // mid-window, dropping whatever was captured since the last flush. Called from
  // chrome.runtime.onSuspend so the latest resources survive the restart.
  async function flushState() {
    if (bridgePersistTimer === null) {
      return;
    }
    clearTimeout(bridgePersistTimer);
    bridgePersistTimer = null;
    await saveBridgeState();
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

  function hasSharedPathPrefix(left: string, right: string): boolean {
    const normalizedLeft = urlWithoutHash(left);
    const normalizedRight = urlWithoutHash(right);
    if (!normalizedLeft || !normalizedRight) {
      return false;
    }
    return normalizedLeft === normalizedRight || normalizedLeft.startsWith(normalizedRight) || normalizedRight.startsWith(normalizedLeft);
  }

  async function tabIdByPageUrl(pageUrl: string): Promise<number | null> {
    const normalizedPageUrl = urlWithoutHash(pageUrl);
    if (!normalizedPageUrl) {
      return null;
    }

    const tabs = await queryTabs({});
    const exactMatch = tabs.find((tab) => tab.id && tab.url && hasSharedPathPrefix(tab.url, normalizedPageUrl));
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

  async function setLastActiveTab(tabId: number | null) {
    if (lastActiveTabId === tabId) {
      return;
    }
    lastActiveTabId = tabId;
    scheduleBridgeStateSave();
  }

  async function refreshActiveTabFromBrowser(): Promise<number | null> {
    const tabs = await queryTabs({ active: true, currentWindow: true });
    const tabId = tabs[0]?.id ?? null;
    await setLastActiveTab(tabId);
    return tabId;
  }

  async function currentTabId(preferredTabId: number | null = null): Promise<number | null> {
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

  async function tabIdForPageMessage(sender: chrome.runtime.MessageSender, href?: string): Promise<number | null> {
    if (sender.tab?.id) {
      await setLastActiveTab(sender.tab.id);
      return sender.tab.id;
    }

    const normalizedHref = href?.trim() ?? "";
    if (normalizedHref) {
      const matchedTabId = await tabIdByPageUrl(normalizedHref);
      if (matchedTabId != null) {
        return matchedTabId;
      }
    }

    return currentTabId();
  }

  async function tabIdForNetworkRequest(details: chrome.webRequest.OnResponseStartedDetails): Promise<number | null> {
    if (details.tabId > 0) {
      return details.tabId;
    }
    const snapshotTabId = cache.headerSnapshotByUrl(details.url)?.tabId;
    if (snapshotTabId != null) {
      return snapshotTabId;
    }
    const matchedTabId = await tabIdByPageUrl(details.initiator ?? "");
    return matchedTabId ?? currentTabId();
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

  // Cross-origin opaque requests get the literal string "null" here.
  function initiatorOf(details: { initiator?: string }): string {
    return details.initiator && details.initiator !== "null" ? details.initiator : "";
  }

  async function downloadResourceViaBrowser(resource: Resource): Promise<void> {
    const filename = taskNameForResource(resource);

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
    const bridgeState = await loadSessionState<{
      [BRIDGE_RESOURCE_CACHE_KEY]: Record<string, Resource[]>;
      [BRIDGE_HEADER_SNAPSHOTS_KEY]: HeaderSnapshot[];
      [BRIDGE_LAST_ACTIVE_TAB_KEY]: number;
    }>({
      [BRIDGE_RESOURCE_CACHE_KEY]: {},
      [BRIDGE_HEADER_SNAPSHOTS_KEY]: [],
      [BRIDGE_LAST_ACTIVE_TAB_KEY]: 0,
    });

    cache.load({
      resources: bridgeState[BRIDGE_RESOURCE_CACHE_KEY] ?? {},
      headers: bridgeState[BRIDGE_HEADER_SNAPSHOTS_KEY] ?? [],
    });

    lastActiveTabId = Number(bridgeState[BRIDGE_LAST_ACTIVE_TAB_KEY] ?? 0) || null;
    loadedFromStorage = true;
  }

  function addResource(
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
    const headerSnapshot = cache.headerSnapshotByUrl(url);
    const headers = {
      ...(headerSnapshot?.headers ?? {}),
      ...(parts.extraHeaders ?? {}),
    };
    const referer = headers.referer || pageUrl || tab?.url || "";
    if (referer) { headers.referer = referer; }

    cache.add({
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

  async function capturePageResource(sender: chrome.runtime.MessageSender, payload: CapturePayload) {
    const tabId = await tabIdForPageMessage(sender, payload.href);
    if (!tabId || !/^(https?:|blob:)/i.test(payload.url)) {
      return;
    }

    const tab = await findTab(tabId);
    addResource(payload.url, tabId, tab, payload.href ?? tab?.url ?? "", {
      filename: resourceNameFromCapture(payload),
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
    if (isCapturableUrl(details.url) && (responseSupportsRange || meta.size > 0)) {
      cache.setHeaderSnapshot(details.url, {}, details.tabId > 0 ? details.tabId : lastActiveTabId, responseSupportsRange, meta.size);
    }

    if (!shouldCaptureNetworkResource(details, meta)) {
      return;
    }

    const tabId = await tabIdForNetworkRequest(details);
    if (!tabId) {
      return;
    }

    const tab = await findTab(tabId);
    addResource(details.url, tabId, tab, initiatorOf(details), {
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

    const tabId = details.tabId > 0 ? details.tabId : (lastActiveTabId ?? await currentTabId());
    if (!tabId) {
      return;
    }

    const tab = await findTab(tabId);
    addResource(details.url, tabId, tab, initiatorOf(details), {
      filename: basenameOf(filenameFromUrl(details.url)) || "resource",
      mime: mimeFromUrl(details.url),
      size: 0,
      supportsRange: false,
    });
  }

  async function routeBrowserDownload(downloadItem: chrome.downloads.DownloadItem) {
    const finalUrl = downloadItem.finalUrl || downloadItem.url;
    const matchedResource = cache.resourceByUrl(finalUrl) ?? cache.resourceByUrl(downloadItem.url);
    const filename =
      basenameOf(downloadItem.filename)
      || basenameOf(matchedResource?.filename ?? "")
      || basenameOf(filenameFromUrl(finalUrl))
      || "resource";

    const headerSnapshot = cache.headerSnapshotByUrl(finalUrl) ?? cache.headerSnapshotByUrl(downloadItem.url);
    const headers = { ...(headerSnapshot?.headers ?? {}) };
    if (downloadItem.referrer && !headers.referer) {
      headers.referer = downloadItem.referrer;
    }

    try {
      const result = await options.sendDesktopRequest<CommandResult>({
        type: "create_task",
        source: "download",
        title: filename,
        payload: {
          url: finalUrl,
          headers,
          filename: filename,
          size:
            typeof downloadItem.totalBytes === "number" && downloadItem.totalBytes > 0
              ? downloadItem.totalBytes
              : matchedResource?.size || headerSnapshot?.size || 0,
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

  async function sendHttpResourceToDesktop(resource: Resource): Promise<CommandResult> {
    const spec = toResourceTaskOptions(resource);
    try {
      const result = await options.sendDesktopRequest<CommandResult>({
        type: "create_task",
        source: "resource",
        title: spec.filename,
        payload: spec,
      });

      if (result.ok) {
        cache.setSent(resource.id);
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

  async function sendResource(resourceId: string): Promise<CommandResult> {
    const resource = cache.resourceById(resourceId) ?? null;
    if (!resource) {
      return { ok: false, message: "资源不存在" };
    }

    if (resource.url.startsWith("blob:")) {
      try {
        await downloadResourceViaBrowser(resource);
        cache.setSent(resource.id);
        return { ok: true, message: "资源已交给浏览器下载" };
      } catch (error) {
        return { ok: false, message: error instanceof Error ? error.message : "发送资源失败" };
      }
    }

    return sendHttpResourceToDesktop(resource);
  }

  // Twitter / Bilibili CDNs 403 without Referer; cat-catch's addMedia path doesn't carry one.
  function setMissingReferer(resource: Resource, fallback: string): void {
    if (!fallback || resource.requestHeaders.referer || resource.referer) { return; }
    resource.requestHeaders = { ...resource.requestHeaders, referer: fallback };
    resource.referer = fallback;
  }

  // Strategy already proved this URL belongs to the active video, so we must dispatch
  // something — desktop range-probes whatever metadata we can't fill in. The synthesized
  // row goes into the cache so setSent can find it and a later webRequest event can merge
  // real size/headers into it.
  async function resourceForMediaUrl(url: string, tabId: number, fallbackTitle: string, fallbackPageUrl: string): Promise<Resource> {
    const id = `${tabId}:${urlWithoutHash(url, true)}`;

    const direct = cache.resourceById(id);
    if (direct) {
      setMissingReferer(direct, fallbackPageUrl);
      return direct;
    }

    const waited = await cache.waitForResource(id, 1500);
    if (waited) {
      setMissingReferer(waited, fallbackPageUrl);
      return waited;
    }

    const snapshot = cache.headerSnapshotByUrl(url);
    const headers: Record<string, string> = { ...(snapshot?.headers ?? {}) };
    const referer = headers.referer || fallbackPageUrl;
    if (referer) { headers.referer = referer; }
    const synthesized: Resource = {
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
    cache.add(synthesized);
    console.warn(
      "[GD Bridge] resourceForMediaUrl synthesized fallback (no webRequest row within 1500ms)",
      { url: synthesized.url, hasSnapshot: Boolean(snapshot), hasReferer: Boolean(referer) },
    );
    return synthesized;
  }

  async function downloadPageMedia(sender: chrome.runtime.MessageSender, payload: ClickPayload): Promise<CommandResult> {
    const tabId = await tabIdForPageMessage(sender, payload.href);
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
      const resource = await resourceForMediaUrl(selection.url, tabId, payload.title, fallbackPageUrl);
      const result = await sendHttpResourceToDesktop(resource);
      if (result.ok) { await openActionPopup(); }
      return result;
    }

    if (selection.kind === "merge") {
      if (!selection.video || !selection.audio) {
        return { ok: false, message: "无效的合并请求" };
      }
      const [video, audio] = await Promise.all([
        resourceForMediaUrl(selection.video, tabId, payload.title, fallbackPageUrl),
        resourceForMediaUrl(selection.audio, tabId, payload.title, fallbackPageUrl),
      ]);
      const result = await sendMergeResources([video, audio]);
      if (result.ok) { await openActionPopup(); }
      return result;
    }

    if (selection.kind === "external") {
      if (!selection.pageUrl) {
        return { ok: false, message: "无效的下载请求" };
      }
      const result = await sendExternalDownload(selection, payload.title, fallbackPageUrl);
      if (result.ok) { await openActionPopup(); }
      return result;
    }

    return { ok: false, message: "未知的下载请求类型" };
  }

  // The desktop's yt-dlp extracts the media from the page URL; forward login cookies for gated videos.
  async function sendExternalDownload(
    selection: { pageUrl: string },
    title: string,
    fallbackPageUrl: string,
  ): Promise<CommandResult> {
    return options.sendDesktopRequest<CommandResult>({
      type: "create_task",
      source: "page_media",
      title: title || "",
      payload: {
        url: selection.pageUrl,
        pageUrl: fallbackPageUrl || selection.pageUrl,
        pageTitle: title || "",
        headers: cache.headersForPage(selection.pageUrl),
      },
    }, 120_000);
  }

  function mergeOutputTitle(resources: Resource[]): string {
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

  async function sendMergeResources(resources: Resource[]): Promise<CommandResult> {
    if (resources.length !== 2) {
      return { ok: false, message: "在线合并暂时只支持选中 2 个资源" };
    }
    const ordered = sortResourcesForOnlineMerge(resources);
    try {
      const result = await options.sendDesktopRequest<CommandResult>({
        type: "create_task",
        source: "resource_merge",
        title: mergeOutputTitle(ordered),
        payload: {
          resources: ordered.map((resource) => ({
            url: resource.url,
            filename: taskNameForResource(resource),
            mime: resource.mime,
            size: resource.size,
            headers: resource.requestHeaders,
            pageTitle: resource.pageTitle,
            supportsRange: resource.supportsRange,
          })),
        },
      });
      if (result.ok) {
        ordered.forEach((resource) => cache.setSent(resource.id));
        return { ...result, message: result.message || "在线合并任务已发送到 Ghost Downloader" };
      }
      return result;
    } catch (error) {
      return { ok: false, message: error instanceof Error ? error.message : "在线合并失败" };
    }
  }

  async function mergeResources(resourceIds: string[]): Promise<CommandResult> {
    const ids = [...new Set(resourceIds.filter(Boolean))];
    const resources = ids
      .map((resourceId) => cache.resourceById(resourceId) ?? null)
      .filter((resource): resource is Resource => resource != null);

    if (!canUseOnlineMergeSelection(resources)) {
      return { ok: false, message: "当前选中的资源不符合在线合并条件" };
    }

    return sendMergeResources(resources);
  }

  function buildPopupStateData(resolvedTabId: number | null, activeTab: chrome.tabs.Tab | null) {
    const canCaptureCurrentTab = Boolean(activeTab?.url && isCapturableUrl(activeTab.url));
    let resourceState: ResourceCollectionState = "ready";
    let resourceStateMessage = "等待 cat-catch 捕获资源";
    if (!loadedFromStorage) {
      resourceState = "restoring";
      resourceStateMessage = "正在恢复 cat-catch 已捕获的资源";
    } else if (!canCaptureCurrentTab) {
      resourceState = "unavailable";
      resourceStateMessage = "当前标签页不支持 cat-catch 资源桥接";
    }

    return {
      resourceState,
      resourceStateMessage,
      currentResources: resolvedTabId == null ? [] : cache.resourcesForTab(resolvedTabId),
      otherResources: cache.otherResources(resolvedTabId),
      activePageDomain: domainFromUrl(activeTab?.url ?? ""),
    };
  }

  function onTabRemoved(tabId: number) {
    cache.clearTab(tabId);
    if (lastActiveTabId === tabId) {
      void setLastActiveTab(null);
    }
  }

  function onNavigationCommitted(details: chrome.webNavigation.WebNavigationTransitionCallbackDetails) {
    if (details.tabId <= 0 || details.frameId !== 0) {
      return;
    }
    cache.clearTab(details.tabId);
  }

  function onRequestHeaders(details: chrome.webRequest.OnSendHeadersDetails) {
    const headers = selectAllowedHeaders(Object.fromEntries((details.requestHeaders ?? []).map((header) => [header.name ?? "", header.value ?? ""])));
    const supportsRange = (details.requestHeaders ?? []).some((header) => header.name?.toLowerCase() === "range" && String(header.value ?? "").toLowerCase().startsWith("bytes="));
    cache.setHeaderSnapshot(details.url, headers, details.tabId > 0 ? details.tabId : lastActiveTabId, supportsRange);
  }

  return {
    buildPopupStateData,
    captureNetworkResource,
    capturePageResource,
    captureRequestResource,
    downloadPageMedia,
    flushState,
    enrichResource: (urls: string[], meta: Parameters<typeof cache.enrichResource>[1]) =>
      cache.enrichResource(urls, meta),
    enrichTabPoster: (tabId: number, posterUrl: string) =>
      cache.enrichTabPoster(tabId, posterUrl),
    headersForPage: (pageUrl: string) => cache.headersForPage(pageUrl),
    routeBrowserDownload,
    onNavigationCommitted,
    onRequestHeaders,
    onTabRemoved,
    loadPersistentState,
    refreshActiveTabFromBrowser,
    currentTabId,
    mergeResources,
    sendResource,
    setLastActiveTab,
  };
}
