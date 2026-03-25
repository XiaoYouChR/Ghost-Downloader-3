import { domainFromUrl, filenameFromUrl, shorten } from "../shared/utils";
import type { MediaItemOption, MediaPlaybackState, MediaTabOption } from "../shared/types";
import {
  MAIN_FRAME_ID,
  MEDIA_FAILURE_THRESHOLD,
  MEDIA_SCAN_INTERVAL_MS,
  MEDIA_TARGET_KEY,
} from "./constants";
import {
  activateTab,
  getTab,
  localStorageGet,
  localStorageSet,
  queryTabs,
  sendMessageToTab,
  type TabMessageResult,
} from "./chrome-helpers";

type RawMediaState = {
  count: number;
  src?: string[];
  currentTime?: number;
  duration?: number;
  time?: number;
  volume?: number;
  paused?: boolean;
  loop?: boolean;
  speed?: number;
  muted?: boolean;
  type?: string;
};

type MediaTarget = {
  tabId: number;
  index: number;
  frameId: number;
};

type MediaInventoryEntry = {
  tabId: number;
  title: string;
  domain: string;
  count: number;
  src: string[];
  mediaType: "video" | "audio";
};

type CachedMediaSnapshot = {
  mediaItems: MediaItemOption[];
  playbackState: MediaPlaybackState;
  updatedAt: number;
};

type BuiltMediaPanelState = {
  mediaTabs: MediaTabOption[];
  mediaItems: MediaItemOption[];
  selectedMediaTabId: number | null;
  selectedMediaIndex: number;
  playbackState: MediaPlaybackState;
};

type HydratedMediaSnapshot =
  | {
      ok: true;
      selectedIndex: number;
      mediaItems: MediaItemOption[];
      playbackState: MediaPlaybackState;
      entry: MediaInventoryEntry;
    }
  | {
      ok: false;
      message: string;
      status: "ok" | "no_receiver" | "runtime_error" | "no_response";
    };

export function createMediaBridge() {
  let mediaControlTarget: MediaTarget = { tabId: 0, index: -1, frameId: MAIN_FRAME_ID };
  let mediaInventory = new Map<number, MediaInventoryEntry>();
  let mediaInventoryScannedAt = 0;
  let mediaInventoryReady = false;
  let mediaPanelInitialized = false;
  let lastMediaPanelState = createEmptyMediaPanelState("");

  const mediaFailureCounts = new Map<number, number>();
  const cachedMediaSnapshots = new Map<number, CachedMediaSnapshot>();

  function sleep(ms: number) {
    return new Promise<void>((resolve) => {
      self.setTimeout(resolve, ms);
    });
  }

  function isCapturableUrl(rawUrl: string): boolean {
    return /^https?:/i.test(rawUrl);
  }

  function isCapturableTab(tab: chrome.tabs.Tab | null): boolean {
    return Boolean(tab?.url && isCapturableUrl(tab.url));
  }

  function createEmptyPlaybackState(message = "当前未检测到可控制媒体"): MediaPlaybackState {
    return {
      available: false,
      stale: false,
      message,
      tabId: null,
      mediaIndex: -1,
      frameId: MAIN_FRAME_ID,
      count: 0,
      currentTime: 0,
      duration: 0,
      progress: 0,
      volume: 1,
      paused: true,
      loop: false,
      muted: false,
      speed: 1,
      mediaType: "",
    };
  }

  function createEmptyMediaPanelState(message: string): BuiltMediaPanelState {
    return {
      mediaTabs: [],
      mediaItems: [],
      selectedMediaTabId: null,
      selectedMediaIndex: -1,
      playbackState: createEmptyPlaybackState(message),
    };
  }

  function shortMediaLabel(src: string): string {
    const candidate = filenameFromUrl(src) || src.split("/").pop() || src;
    return shorten(candidate, 48);
  }

  function normalizeMediaType(type: string | undefined): "video" | "audio" {
    return type === "audio" ? "audio" : "video";
  }

  function createMediaItems(srcList: string[], count: number, mediaType: "video" | "audio"): MediaItemOption[] {
    return Array.from({ length: count }, (_unused, index) => ({
      index,
      label: shortMediaLabel(srcList[index] ?? `${mediaType}-${index + 1}`),
      type: mediaType,
    }));
  }

  function mediaTabsFromInventory(): MediaTabOption[] {
    return [...mediaInventory.values()]
      .sort((left, right) => left.title.localeCompare(right.title))
      .map((entry) => ({
        tabId: entry.tabId,
        title: entry.title,
        domain: entry.domain,
      }));
  }

  function chooseMediaTabId(activeTabId: number | null): number {
    if (mediaControlTarget.tabId > 0 && mediaInventory.has(mediaControlTarget.tabId)) {
      return mediaControlTarget.tabId;
    }
    if (activeTabId != null && mediaInventory.has(activeTabId)) {
      return activeTabId;
    }
    return mediaTabsFromInventory()[0]?.tabId ?? 0;
  }

  function mediaFailureMessage(result: TabMessageResult<unknown> | null): string {
    if (!result) {
      return "当前媒体状态暂时不可读";
    }
    switch (result.status) {
      case "no_receiver":
        return "当前页面的媒体桥接还没有准备好";
      case "runtime_error":
        return result.message || "读取媒体状态失败";
      case "no_response":
        return "页面没有返回媒体状态";
      default:
        return "当前页面未检测到可控制媒体";
    }
  }

  function responseHasExplicitFailure(response: unknown): string | null {
    if (!response || typeof response !== "object" || !("ok" in response)) {
      return null;
    }
    if ((response as { ok?: boolean }).ok !== false) {
      return null;
    }
    return String((response as { message?: string }).message ?? "页面操作失败");
  }

  async function requestMediaState(tabId: number, index: number): Promise<TabMessageResult<RawMediaState>> {
    return sendMessageToTab<RawMediaState>(
      tabId,
      {
        Message: "getVideoState",
        index,
      },
      { frameId: MAIN_FRAME_ID },
    );
  }

  async function scanMediaTabs(force = false) {
    if (!force && mediaInventoryReady && Date.now() - mediaInventoryScannedAt < MEDIA_SCAN_INTERVAL_MS) {
      return;
    }

    const tabs = await queryTabs({ windowType: "normal" });
    const next = new Map<number, MediaInventoryEntry>();

    for (const tab of tabs) {
      if (!tab.id || !isCapturableTab(tab)) {
        continue;
      }
      const result = await requestMediaState(tab.id, 0);
      if (result.status !== "ok" || !result.response?.count) {
        continue;
      }
      const state = result.response;
      next.set(tab.id, {
        tabId: tab.id,
        title: tab.title || "未命名标签页",
        domain: domainFromUrl(tab.url || ""),
        count: Number(state.count ?? 0),
        src: Array.isArray(state.src) ? state.src : [],
        mediaType: normalizeMediaType(state.type),
      });
    }

    mediaInventory = next;
    mediaInventoryReady = true;
    mediaInventoryScannedAt = Date.now();
  }

  async function hydrateMediaSnapshot(tabId: number, index: number): Promise<HydratedMediaSnapshot> {
    const result = await requestMediaState(tabId, index >= 0 ? index : 0);
    if (result.status !== "ok") {
      return {
        ok: false,
        message: mediaFailureMessage(result),
        status: result.status,
      };
    }

    const state = result.response;
    if (!state?.count) {
      return {
        ok: false,
        message: "当前页面未检测到可控制媒体",
        status: "ok",
      };
    }

    const count = Number(state.count ?? 0);
    const selectedIndex = index >= 0 && index < count ? index : 0;
    const srcList = Array.isArray(state.src) ? state.src : [];
    const mediaType = normalizeMediaType(state.type);
    const mediaItems = createMediaItems(srcList, count, mediaType);
    const playbackState: MediaPlaybackState = {
      available: true,
      stale: false,
      message: "",
      tabId,
      mediaIndex: selectedIndex,
      frameId: MAIN_FRAME_ID,
      count,
      currentTime: Number(state.currentTime ?? 0),
      duration: Number(state.duration ?? 0),
      progress: Number(state.time ?? 0),
      volume: Number(state.volume ?? 1),
      paused: Boolean(state.paused ?? true),
      loop: Boolean(state.loop ?? false),
      muted: Boolean(state.muted ?? false),
      speed: Number(state.speed ?? 1),
      mediaType,
    };

    const tab = await getTab(tabId);
    return {
      ok: true,
      selectedIndex,
      mediaItems,
      playbackState,
      entry: {
        tabId,
        title: tab?.title || "未命名标签页",
        domain: domainFromUrl(tab?.url || ""),
        count,
        src: srcList,
        mediaType,
      },
    };
  }

  function cacheMediaSnapshot(tabId: number, mediaItems: MediaItemOption[], playbackState: MediaPlaybackState) {
    cachedMediaSnapshots.set(tabId, {
      mediaItems,
      playbackState: { ...playbackState, stale: false, message: "" },
      updatedAt: Date.now(),
    });
  }

  async function loadPersistentState() {
    const localState = await localStorageGet<{
      [MEDIA_TARGET_KEY]: MediaTarget;
    }>({
      [MEDIA_TARGET_KEY]: { tabId: 0, index: -1, frameId: MAIN_FRAME_ID },
    });

    mediaControlTarget = {
      tabId: Number(localState[MEDIA_TARGET_KEY]?.tabId ?? 0),
      index: Number(localState[MEDIA_TARGET_KEY]?.index ?? -1),
      frameId: MAIN_FRAME_ID,
    };
  }

  async function buildPanelState(
    activeTabId: number | null,
    options: { refreshInventory?: boolean; refreshTarget?: boolean } = {},
  ): Promise<BuiltMediaPanelState> {
    if (options.refreshInventory || !mediaInventoryReady || Date.now() - mediaInventoryScannedAt >= MEDIA_SCAN_INTERVAL_MS) {
      await scanMediaTabs(Boolean(options.refreshInventory));
    }

    let selectedMediaTabId = chooseMediaTabId(activeTabId);
    let selectedMediaIndex = mediaControlTarget.index;
    let mediaTabs = mediaTabsFromInventory();

    if (!selectedMediaTabId) {
      const empty = createEmptyMediaPanelState(mediaInventoryReady ? "当前未检测到可控制媒体" : "正在恢复媒体状态");
      lastMediaPanelState = { ...empty, mediaTabs };
      mediaPanelInitialized = true;
      return lastMediaPanelState;
    }

    const shouldRefreshTarget =
      options.refreshTarget ||
      !mediaPanelInitialized ||
      lastMediaPanelState.selectedMediaTabId !== selectedMediaTabId ||
      lastMediaPanelState.selectedMediaIndex !== selectedMediaIndex;

    if (!shouldRefreshTarget) {
      const reused = {
        ...lastMediaPanelState,
        mediaTabs,
      };
      lastMediaPanelState = reused;
      mediaPanelInitialized = true;
      return reused;
    }

    let snapshot = await hydrateMediaSnapshot(selectedMediaTabId, selectedMediaIndex);
    if (!snapshot.ok) {
      const failures = (mediaFailureCounts.get(selectedMediaTabId) ?? 0) + 1;
      mediaFailureCounts.set(selectedMediaTabId, failures);

      const cached = cachedMediaSnapshots.get(selectedMediaTabId);
      if (cached && failures < MEDIA_FAILURE_THRESHOLD) {
        const staleState: BuiltMediaPanelState = {
          mediaTabs,
          mediaItems: cached.mediaItems,
          selectedMediaTabId,
          selectedMediaIndex: cached.playbackState.mediaIndex,
          playbackState: {
            ...cached.playbackState,
            stale: true,
            message: snapshot.message,
          },
        };
        lastMediaPanelState = staleState;
        mediaPanelInitialized = true;
        return staleState;
      }

      await scanMediaTabs(true);
      mediaTabs = mediaTabsFromInventory();
      selectedMediaTabId = chooseMediaTabId(activeTabId);
      selectedMediaIndex = mediaControlTarget.index;

      if (!selectedMediaTabId) {
        const empty = createEmptyMediaPanelState(snapshot.message);
        lastMediaPanelState = { ...empty, mediaTabs };
        mediaPanelInitialized = true;
        return lastMediaPanelState;
      }

      snapshot = await hydrateMediaSnapshot(selectedMediaTabId, selectedMediaIndex);
      if (!snapshot.ok) {
        const empty = createEmptyMediaPanelState(snapshot.message);
        lastMediaPanelState = { ...empty, mediaTabs, selectedMediaTabId, selectedMediaIndex };
        mediaPanelInitialized = true;
        return lastMediaPanelState;
      }
    }

    mediaFailureCounts.delete(selectedMediaTabId);
    selectedMediaIndex = snapshot.selectedIndex;
    mediaInventory.set(selectedMediaTabId, snapshot.entry);
    mediaTabs = mediaTabsFromInventory();
    cacheMediaSnapshot(selectedMediaTabId, snapshot.mediaItems, snapshot.playbackState);

    const nextState: BuiltMediaPanelState = {
      mediaTabs,
      mediaItems: snapshot.mediaItems,
      selectedMediaTabId,
      selectedMediaIndex,
      playbackState: snapshot.playbackState,
    };

    if (
      mediaControlTarget.tabId !== selectedMediaTabId ||
      mediaControlTarget.index !== selectedMediaIndex ||
      mediaControlTarget.frameId !== MAIN_FRAME_ID
    ) {
      mediaControlTarget = {
        tabId: selectedMediaTabId,
        index: selectedMediaIndex,
        frameId: MAIN_FRAME_ID,
      };
      await localStorageSet({ [MEDIA_TARGET_KEY]: mediaControlTarget });
    }

    lastMediaPanelState = nextState;
    mediaPanelInitialized = true;
    return nextState;
  }

  async function setMediaTarget(tabId: number, index: number) {
    mediaControlTarget = {
      tabId,
      index,
      frameId: MAIN_FRAME_ID,
    };
    mediaInventoryScannedAt = 0;
    await localStorageSet({ [MEDIA_TARGET_KEY]: mediaControlTarget });
  }

  async function performAction(action: string, value?: number | boolean): Promise<{ ok: boolean; message?: string }> {
    const tabId = mediaControlTarget.tabId;
    const index = mediaControlTarget.index;
    if (!tabId || index < 0) {
      return { ok: false, message: "当前没有可控制的媒体" };
    }

    const payload: Record<string, unknown> = { index };
    switch (action) {
      case "toggle_play": {
        const stateResult = await requestMediaState(tabId, index);
        if (stateResult.status === "ok" && stateResult.response?.count) {
          payload.Message = stateResult.response.paused ? "play" : "pause";
        } else {
          const cached = cachedMediaSnapshots.get(tabId);
          if (!cached) {
            return { ok: false, message: mediaFailureMessage(stateResult) };
          }
          payload.Message = cached.playbackState.paused ? "play" : "pause";
        }
        break;
      }
      case "set_speed":
        payload.Message = "speed";
        payload.speed = Number(value ?? 1);
        break;
      case "pip":
        payload.Message = "pip";
        break;
      case "fullscreen":
        payload.Message = "fullScreen";
        await activateTab(tabId);
        await sleep(120);
        break;
      case "screenshot":
        payload.Message = "screenshot";
        break;
      case "toggle_loop":
        payload.Message = "loop";
        payload.action = Boolean(value);
        break;
      case "toggle_muted":
        payload.Message = "muted";
        payload.action = Boolean(value);
        break;
      case "set_volume":
        payload.Message = "setVolume";
        payload.volume = Number(value ?? 1);
        break;
      case "set_time":
        payload.Message = "setTime";
        payload.time = Number(value ?? 0);
        break;
      default:
        return { ok: false, message: "未知的媒体操作" };
    }

    const result = await sendMessageToTab(tabId, payload, { frameId: MAIN_FRAME_ID });
    if (result.status !== "ok") {
      return { ok: false, message: mediaFailureMessage(result) };
    }

    const responseError = responseHasExplicitFailure(result.response);
    if (responseError) {
      return { ok: false, message: responseError };
    }

    return { ok: true };
  }

  function handleTabRemoved(tabId: number) {
    mediaInventory.delete(tabId);
    mediaFailureCounts.delete(tabId);
    cachedMediaSnapshots.delete(tabId);

    if (mediaControlTarget.tabId === tabId) {
      mediaControlTarget = { tabId: 0, index: -1, frameId: MAIN_FRAME_ID };
      void localStorageSet({ [MEDIA_TARGET_KEY]: mediaControlTarget });
      lastMediaPanelState = createEmptyMediaPanelState("当前未检测到可控制媒体");
      mediaPanelInitialized = false;
    }
  }

  function handleNavigationCommitted(details: chrome.webNavigation.WebNavigationFramedCallbackDetails) {
    if (details.tabId <= 0 || details.frameId !== MAIN_FRAME_ID) {
      return;
    }
    mediaFailureCounts.delete(details.tabId);
    cachedMediaSnapshots.delete(details.tabId);
    if (mediaControlTarget.tabId === details.tabId) {
      mediaInventory.delete(details.tabId);
      mediaInventoryScannedAt = 0;
    }
  }

  return {
    buildPanelState,
    getLastPanelState: () => lastMediaPanelState,
    handleNavigationCommitted,
    handleTabRemoved,
    loadPersistentState,
    performAction,
    setMediaTarget,
  };
}
