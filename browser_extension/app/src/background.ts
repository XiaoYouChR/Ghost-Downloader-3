import type {
    CommandResult,
    TaskSummary,
    PopupState,
    PopupView,
} from "./shared/types";
import type {PopupCommand} from "./shared/popup-protocol";
import {createDesktopBridge} from "./background/desktop-bridge";
import {createFeatureBridge} from "./background/feature-bridge";
import {createMediaBridge} from "./background/media-bridge";
import {createResourceBridge} from "./background/resource-bridge";
import {
    BYPASS_MODIFIER_KEY,
    IS_MEDIA_BUTTON_ENABLED_KEY,
    MIN_TAKE_SIZE_KB_KEY,
    SHOULD_SKIP_IMAGES_KEY,
    SHOULD_TAKE_UNKNOWN_SIZE_KEY,
    SHOULD_TAKE_DOWNLOADS_KEY,
} from "./background/constants";
import {
    cancelDownload,
    eraseDownloadFromHistory,
    findTab,
    loadLocalState,
    openActionPopup,
    queryTabs,
} from "./background/chrome-helpers";
import {onSendHeadersExtraInfoSpec, supportsDownloadDeterminingFilename,} from "./shared/browser";
import {loadBaseIcons, updateIconForTasks} from "./background/icon-progress";
import {enqueue, flush, pendingCount} from "./background/task-queue";

async function flushQueue(): Promise<void> {
  const sent = await flush((payload) => desktopBridge.sendRequest(payload));
  if (sent > 0) {
    await openActionPopup();
  }
}

async function sendTaskOrEnqueue<T extends CommandResult>(payload: Record<string, unknown>, timeoutMs?: number): Promise<T> {
  if (desktopBridge.isReady()) {
    try {
      return await desktopBridge.sendRequest<T>(payload, timeoutMs);
    } catch (error) {
      if (desktopBridge.isReady()) {
        throw error;
      }
    }
  }
  await enqueue(payload);
  return { ok: true, message: chrome.i18n.getMessage("taskQueued") } as T;
}

const openWhenDoneIds = new Set<string>();

function onTaskSnapshotChanged(tasks: TaskSummary[]): void {
  updateIconForTasks(tasks);
  for (const task of tasks) {
    if (task.status === "completed" && openWhenDoneIds.has(task.taskId)) {
      openWhenDoneIds.delete(task.taskId);
      void desktopBridge.sendRequest({
        type: "task_action",
        taskId: task.taskId,
        action: "open_file",
      });
    }
  }
}

const desktopBridge = createDesktopBridge({
  onTaskSnapshotChanged,
  onConnected: () => void flushQueue(),
});
const resourceBridge = createResourceBridge({
  sendDesktopRequest: (payload) => sendTaskOrEnqueue(payload),
});
const featureBridge = createFeatureBridge();
const mediaBridge = createMediaBridge();

let shouldTakeDownloads = true;
let isMediaButtonEnabled = true;
let minTakeSizeKB = 0;
let shouldTakeUnknownSize = true;
let shouldSkipImages = false;

function imageFilename(url: string, alt: string): string {
  try {
    const pathname = new URL(url).pathname;
    const basename = decodeURIComponent(pathname.split("/").pop() || "");
    if (basename && /\.\w{2,5}$/.test(basename)) {
      return basename.slice(0, 160);
    }
  } catch { /* invalid URL */ }
  const safe = (alt || "image").replace(/[<>:"/\\|?*\x00-\x1f]+/g, " ").trim().slice(0, 120);
  return safe || "image";
}

async function injectMediaButton(tabId: number) {
  if (!isMediaButtonEnabled) {
    return;
  }
  const tab = await findTab(tabId);
  if (!tab?.url || !/^https?:/i.test(tab.url)) {
    return;
  }

  try {
    await chrome.scripting.executeScript({
      files: ["page-media-overlay.js"],
      injectImmediately: false,
      target: { tabId, allFrames: true },
    });
  } catch {
    // chrome:// and similar reject injection.
  }
}

async function setMediaButtonEnabled(enabled: boolean) {
  isMediaButtonEnabled = enabled;
  await chrome.storage.local.set({ [IS_MEDIA_BUTTON_ENABLED_KEY]: enabled });

  const tabs = await queryTabs({});
  for (const tab of tabs) {
    if (!tab.id || !tab.url || !/^https?:/i.test(tab.url)) {
      continue;
    }
    chrome.tabs.sendMessage(tab.id, {
      type: "media_button_set_enabled",
      enabled,
    }, () => {
      const lastError = chrome.runtime.lastError;
      if (enabled && lastError && tab.id) {
        void injectMediaButton(tab.id);
      }
    });
  }
}

function buildTaskCounters(tasks: TaskSummary[]) {
  return {
    total: tasks.length,
    active: tasks.filter((task) => task.status !== "completed").length,
    completed: tasks.filter((task) => task.status === "completed").length,
  };
}

async function buildPopupState(options: {
  preferredTabId?: number | null;
  currentView?: PopupView;
} = {}): Promise<PopupState> {
  const activeTabId = await resourceBridge.currentTabId(options.preferredTabId ?? null);
  const activeTab = activeTabId != null ? await findTab(activeTabId) : null;
  const desktopState = desktopBridge.buildSnapshot();
  const resourceState = resourceBridge.buildPopupStateData(activeTabId, activeTab);

  const mediaPanelState = await mediaBridge.buildPanelState(
    options.currentView === "advanced" ? activeTabId : null,
  );

  return {
    connectionState: desktopState.connectionState,
    connectionMessage: desktopState.connectionMessage,
    desktopVersion: desktopState.desktopVersion,
    token: desktopState.token,
    serverUrl: desktopState.serverUrl,
    shouldTakeDownloads,
    isMediaButtonEnabled,
    tasks: desktopState.tasks.map((t) => ({ ...t, shouldOpenWhenDone: openWhenDoneIds.has(t.taskId) })),
    taskCounters: buildTaskCounters(desktopState.tasks),
    tabId: activeTabId,
    featureStates: featureBridge.createFeatureStateMap(activeTabId),
    mediaItems: mediaPanelState.mediaItems,
    mediaPlaybackState: mediaPanelState.playbackState,
    pendingTaskCount: await pendingCount(),
    ...resourceState,
  };
}

async function setupBackground() {
  const localState = await loadLocalState<{
    [SHOULD_TAKE_DOWNLOADS_KEY]: boolean;
    [IS_MEDIA_BUTTON_ENABLED_KEY]: boolean;
    [MIN_TAKE_SIZE_KB_KEY]: number;
    [SHOULD_TAKE_UNKNOWN_SIZE_KEY]: boolean;
    [SHOULD_SKIP_IMAGES_KEY]: boolean;
  }>({
    [SHOULD_TAKE_DOWNLOADS_KEY]: true,
    [IS_MEDIA_BUTTON_ENABLED_KEY]: true,
    [MIN_TAKE_SIZE_KB_KEY]: 0,
    [SHOULD_TAKE_UNKNOWN_SIZE_KEY]: true,
    [SHOULD_SKIP_IMAGES_KEY]: false,
  });

  shouldTakeDownloads = Boolean(localState[SHOULD_TAKE_DOWNLOADS_KEY] ?? true);
  isMediaButtonEnabled = Boolean(localState[IS_MEDIA_BUTTON_ENABLED_KEY] ?? true);
  minTakeSizeKB = Number(localState[MIN_TAKE_SIZE_KB_KEY]) || 0;
  shouldTakeUnknownSize = Boolean(localState[SHOULD_TAKE_UNKNOWN_SIZE_KEY] ?? true);
  shouldSkipImages = Boolean(localState[SHOULD_SKIP_IMAGES_KEY] ?? false);

  try {
    const selfInfo = await chrome.management.getSelf();
    desktopBridge.setInstallType(selfInfo.installType);
  } catch {
    desktopBridge.setInstallType("normal");
  }

  await loadBaseIcons();
  await desktopBridge.loadPersistentState();
  await resourceBridge.loadPersistentState();
  await featureBridge.loadPersistentState();
  const activeTabId = await resourceBridge.currentTabId();
  if (activeTabId != null) {
    void injectMediaButton(activeTabId);
  }

  if (desktopBridge.buildSnapshot().token) {
    void desktopBridge.connect();
  }

  desktopBridge.setupReconnectAlarm();
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "gd-download",
    title: chrome.i18n.getMessage("downloadWithGhostDownloader"),
    contexts: ["link", "image", "video", "audio"],
  });
  chrome.contextMenus.create({
    id: "gd-save-as",
    title: chrome.i18n.getMessage("saveAsWithGhostDownloader"),
    contexts: ["link", "image", "video", "audio"],
  });
});

chrome.contextMenus.onClicked.addListener((info) => {
  const url = info.linkUrl || info.srcUrl;
  if (!url) { return; }
  const draft = info.menuItemId === "gd-save-as";
  const headers = resourceBridge.headersForPage(info.pageUrl ?? "");
  if (!headers.referer && info.pageUrl) {
    headers.referer = info.pageUrl;
  }
  void sendTaskOrEnqueue({
    type: "create_task",
    source: "download",
    draft,
    title: "",
    payload: { url, headers, filename: "", size: 0, supportsRange: false },
  }).then((result) => {
    if (result.ok) { void openActionPopup(); }
  });
});

chrome.alarms.onAlarm.addListener((alarm) => {
  desktopBridge.onReconnectAlarm(alarm);
});

chrome.runtime.onConnect.addListener((port) => {
  if (port.name === "HeartBeat") {
    port.postMessage("HeartBeat");
  }
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local") {
    return;
  }
  desktopBridge.onLocalStorageChanged(changes);
  if (changes[SHOULD_TAKE_DOWNLOADS_KEY]) {
    shouldTakeDownloads = Boolean(changes[SHOULD_TAKE_DOWNLOADS_KEY].newValue ?? true);
  }
  if (changes[IS_MEDIA_BUTTON_ENABLED_KEY]) {
    isMediaButtonEnabled = Boolean(changes[IS_MEDIA_BUTTON_ENABLED_KEY].newValue ?? true);
  }
  if (changes[MIN_TAKE_SIZE_KB_KEY]) {
    minTakeSizeKB = Number(changes[MIN_TAKE_SIZE_KB_KEY].newValue) || 0;
  }
  if (changes[SHOULD_TAKE_UNKNOWN_SIZE_KEY]) {
    shouldTakeUnknownSize = Boolean(changes[SHOULD_TAKE_UNKNOWN_SIZE_KEY].newValue ?? true);
  }
  if (changes[SHOULD_SKIP_IMAGES_KEY]) {
    shouldSkipImages = Boolean(changes[SHOULD_SKIP_IMAGES_KEY].newValue ?? false);
  }
});

chrome.tabs.onActivated.addListener((activeInfo) => {
  void resourceBridge.setLastActiveTab(activeInfo.tabId);
  void injectMediaButton(activeInfo.tabId);
});

chrome.windows.onFocusChanged.addListener((windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) {
    return;
  }
  void resourceBridge.refreshActiveTabFromBrowser().then((tabId) => {
    if (tabId != null) {
      void injectMediaButton(tabId);
    }
  });
});

chrome.tabs.onRemoved.addListener((tabId) => {
  resourceBridge.onTabRemoved(tabId);
  mediaBridge.onTabRemoved(tabId);
  featureBridge.onTabRemoved(tabId);
});

chrome.webNavigation.onCommitted.addListener((details) => {
  resourceBridge.onNavigationCommitted(details);
  featureBridge.onNavigationCommitted(details);
});

chrome.webRequest.onSendHeaders.addListener(
  (details) => {
    resourceBridge.onRequestHeaders(details);
    void resourceBridge.captureRequestResource(details);
  },
  { urls: ["<all_urls>"] },
  onSendHeadersExtraInfoSpec(),
);

chrome.webRequest.onResponseStarted.addListener(
  (details) => {
    void resourceBridge.captureNetworkResource(details);
  },
  { urls: ["<all_urls>"] },
  ["responseHeaders"],
);

let bypassNextDownload = false;
let bypassTimer = 0;
let autoLaunchPending = false;

async function takeBrowserDownload(
  downloadItem: chrome.downloads.DownloadItem,
  options: { eraseFromHistory?: boolean } = {},
) {
  if (bypassNextDownload) {
    bypassNextDownload = false;
    clearTimeout(bypassTimer);
    return;
  }

  const finalUrl = downloadItem.finalUrl || downloadItem.url;
  if (!shouldTakeDownloads || !/^https?:/i.test(finalUrl)) {
    return;
  }

  if (shouldSkipImages && downloadItem.mime?.startsWith("image/")) {
    return;
  }

  if (minTakeSizeKB > 0) {
    const totalBytes = downloadItem.totalBytes ?? -1;
    if (totalBytes < 0 && !shouldTakeUnknownSize) { return; }
    if (totalBytes >= 0 && totalBytes < minTakeSizeKB * 1024) { return; }
  }

  const wasReady = desktopBridge.isReady();

  try {
    await cancelDownload(downloadItem.id);
    if (options.eraseFromHistory) {
      await eraseDownloadFromHistory(downloadItem.id);
    }
  } catch {
    // Cleanup failed but the browser will still finish the download as fallback.
  }

  if (!wasReady) {
    autoLaunchPending = true;
  }

  await resourceBridge.routeBrowserDownload(downloadItem);
}

function sendReply(sendResponse: (response?: unknown) => void, response: Promise<unknown>) {
  void response.then(sendResponse);
  return true;
}

if (supportsDownloadDeterminingFilename()) {
  chrome.downloads.onDeterminingFilename.addListener((downloadItem, suggest) => {
    suggest();
    void takeBrowserDownload(downloadItem);
  });
} else if (chrome.downloads.onCreated?.addListener) {
  chrome.downloads.onCreated.addListener((downloadItem) => {
    void takeBrowserDownload(downloadItem, { eraseFromHistory: true });
  });
}

// The typed receiver half of the popup command seam (shared/popup-protocol.ts): one
// exhaustive switch over the command union. Each case narrows the command to its own shape
// (no cast); the never-typed default makes a missing case a compile error.
async function runPopupCommand(command: PopupCommand): Promise<PopupState | CommandResult> {
  switch (command.type) {
    case "popup_get_state":
      return buildPopupState({
        preferredTabId: typeof command.tabId === "number" ? command.tabId : null,
        currentView: command.view,
      });
    case "popup_set_token":
      await desktopBridge.setToken(command.token.trim());
      return buildPopupState({ currentView: command.view });
    case "popup_set_server_url":
      await desktopBridge.setServerUrl(command.serverUrl);
      return buildPopupState({ currentView: command.view });
    case "popup_refresh_connection":
      await desktopBridge.connect(true);
      return buildPopupState({ currentView: command.view });
    case "popup_set_take_downloads":
      shouldTakeDownloads = command.enabled;
      await chrome.storage.local.set({ [SHOULD_TAKE_DOWNLOADS_KEY]: shouldTakeDownloads });
      return buildPopupState({ currentView: command.view });
    case "popup_set_media_button":
      await setMediaButtonEnabled(command.enabled);
      return buildPopupState({ currentView: command.view });
    case "popup_set_media_index":
      await mediaBridge.setMediaIndex(command.tabId, command.index);
      return buildPopupState({ currentView: "advanced" });
    case "popup_request_pairing":
      void desktopBridge.requestPairing().catch(() => {
        // The bridge snapshot carries the user-facing pairing failure message.
      });
      return { ok: true, message: chrome.i18n.getMessage("confirmPairing") };
    case "popup_task_action":
      if (command.action === "open_when_done") {
        if (openWhenDoneIds.has(command.taskId)) {
          openWhenDoneIds.delete(command.taskId);
        } else {
          openWhenDoneIds.add(command.taskId);
        }
        return { ok: true };
      }
      try {
        return await desktopBridge.sendRequest<CommandResult>({
          type: "task_action",
          taskId: command.taskId,
          action: command.action,
        });
      } catch (error) {
        return { ok: false, message: error instanceof Error ? error.message : chrome.i18n.getMessage("errorTaskActionFailed") };
      }
    case "popup_send_resource":
      return resourceBridge.sendResource(command.resourceId);
    case "popup_merge_resources":
      return resourceBridge.mergeResources(command.resourceIds);
    case "popup_toggle_feature":
      try {
        const infoMessage = await featureBridge.toggleFeature(command.feature, command.tabId);
        return { ok: true, message: infoMessage };
      } catch (error) {
        return { ok: false, message: error instanceof Error ? error.message : chrome.i18n.getMessage("errorFeatureToggleFailed") };
      }
    case "popup_media_action":
      try {
        const playbackState = await mediaBridge.runAction(command.action, command.value);
        return { ok: true, message: "", playbackState };
      } catch (error) {
        return { ok: false, message: error instanceof Error ? error.message : chrome.i18n.getMessage("errorMediaActionFailed") };
      }
    case "popup_send_images": {
      let count = 0;
      for (const image of command.images) {
        const filename = imageFilename(image.src, image.alt);
        await sendTaskOrEnqueue({
          type: "create_task",
          source: "download",
          title: filename,
          payload: {
            url: image.src,
            headers: { referer: command.pageUrl },
            filename,
            size: 0,
            supportsRange: false,
          },
        });
        count += 1;
      }
      return { ok: true, message: chrome.i18n.getMessage("imagesProcessed", [String(count)]) };
    }
    default:
      return unknownPopupCommand(command);
  }
}

// Reached only by a popup_ message whose type is not a known command. The `never` parameter
// makes the switch above exhaustive at compile time; at runtime it returns a structured
// error instead of throwing, so the caller still gets a response.
function unknownPopupCommand(command: never): CommandResult {
  return { ok: false, message: chrome.i18n.getMessage("errorUnknownCommand", [String((command as { type?: string }).type ?? "")]) };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || typeof message !== "object") {
    return;
  }

  if (message.Message === "addMedia" && typeof message.url === "string") {
    void resourceBridge.capturePageResource(sender, {
      url: message.url,
      href: message.href,
      mime: message.mime,
      ext: message.extraExt,
      requestHeaders: message.requestHeaders,
    });
    sendResponse("ok");
    return true;
  }

  if (typeof message.type !== "string") {
    return;
  }

  if (message.type === "bridge_page_command") {
    void featureBridge.onBridgeScriptCommand(message.payload, sender);
    sendResponse({ ok: true });
    return true;
  }

  if (message.type === "page_download_media") {
    return sendReply(sendResponse, resourceBridge.downloadPageMedia(sender, {
      selection: message.selection,
      href: String(message.href ?? ""),
      title: String(message.title ?? ""),
    }));
  }

  if (message.type === "media_metadata" && Array.isArray(message.urls)) {
    const meta = {
      duration: message.duration,
      videoWidth: message.videoWidth,
      videoHeight: message.videoHeight,
      posterUrl: message.posterUrl,
    };
    resourceBridge.enrichResource(message.urls, meta);
    if (sender.tab?.id && meta.posterUrl) {
      resourceBridge.enrichTabPoster(sender.tab.id, meta.posterUrl);
    }
    return;
  }

  if (message.type === "page_poster" && message.posterUrl && sender.tab?.id) {
    resourceBridge.enrichTabPoster(sender.tab.id, String(message.posterUrl));
    return;
  }

  if (message.type === "bypass_next_download") {
    bypassNextDownload = true;
    clearTimeout(bypassTimer);
    bypassTimer = self.setTimeout(() => { bypassNextDownload = false; }, 3000);
    return;
  }

  if (message.type === "popup_mounted") {
    const shouldLaunch = autoLaunchPending;
    autoLaunchPending = false;
    sendResponse({ autoLaunch: shouldLaunch });
    return;
  }

  if (message.type === "page_media_button_state") {
    sendResponse({ enabled: isMediaButtonEnabled });
    return;
  }

  // popup_ commands are privileged (set token / server URL / merge resources). A page can
  // forward arbitrary runtime messages through cat-catch's content script, so the sender —
  // not just the type prefix — is the guard: only the extension's own popup (a
  // chrome-extension:// page, never a tab) may reach the dispatcher. That lets the cast trust
  // the payload, since the popup is the sole, typed caller.
  if (message.type.startsWith("popup_")) {
    if (!sender.url?.startsWith("chrome-extension://") && !sender.url?.startsWith("moz-extension://")) { return; }
    return sendReply(sendResponse, runPopupCommand(message as PopupCommand));
  }
});

chrome.runtime.onSuspend.addListener(() => {
  void resourceBridge.flushState();
});

void setupBackground();
