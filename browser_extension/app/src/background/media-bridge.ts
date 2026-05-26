import {filenameFromUrl, shorten} from "../shared/utils";
import type {MediaItemOption, MediaPlaybackState} from "../shared/types";
import {MAIN_FRAME_ID} from "./constants";
import {sendMessageToTab, type TabMessageResult,} from "./chrome-helpers";

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
};

type MediaTarget = {
  tabId: number;
  index: number;
};

type BuiltMediaPanelState = {
  mediaItems: MediaItemOption[];
  playbackState: MediaPlaybackState;
};

export function createMediaBridge() {
  let mediaControlTarget: MediaTarget = { tabId: 0, index: -1 };

  function createEmptyPlaybackState(message = "当前未检测到可控制媒体"): MediaPlaybackState {
    return {
      available: false,
      message,
      tabId: null,
      mediaIndex: -1,
      currentTime: 0,
      duration: 0,
      progress: 0,
      volume: 1,
      paused: true,
      loop: false,
      muted: false,
      speed: 1,
    };
  }

  function createEmptyMediaPanelState(message: string): BuiltMediaPanelState {
    return {
      mediaItems: [],
      playbackState: createEmptyPlaybackState(message),
    };
  }

  function createMediaItems(srcList: string[], count: number): MediaItemOption[] {
    return Array.from({ length: count }, (_unused, index) => {
      const src = srcList[index] ?? `media-${index + 1}`;
      return {
        index,
        label: shorten(filenameFromUrl(src) || src.split("/").pop() || src, 48),
      };
    });
  }

  function mediaFailureMessage(result: TabMessageResult<unknown>): string {
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

  async function requestMediaState(tabId: number, index: number): Promise<TabMessageResult<RawMediaState>> {
    return sendMessageToTab<RawMediaState>(
      tabId,
      { Message: "getVideoState", index },
      { frameId: MAIN_FRAME_ID },
    );
  }

  async function buildPanelState(activeTabId: number | null): Promise<BuiltMediaPanelState> {
    const tabId = activeTabId;
    let mediaIndex = mediaControlTarget.tabId === tabId ? mediaControlTarget.index : 0;

    if (!tabId) {
      return createEmptyMediaPanelState("当前没有可操作的标签页");
    }

    const result = await requestMediaState(tabId, mediaIndex >= 0 ? mediaIndex : 0);

    const state = result.response;
    if (result.status !== "ok" || !state?.count) {
      return createEmptyMediaPanelState(mediaFailureMessage(result));
    }

    const count = Number(state.count ?? 0);
    mediaIndex = mediaIndex >= 0 && mediaIndex < count ? mediaIndex : 0;
    const srcList = Array.isArray(state.src) ? state.src : [];

    const playbackState: MediaPlaybackState = {
      available: true,
      message: "",
      tabId,
      mediaIndex,
      currentTime: Number(state.currentTime ?? 0),
      duration: Number(state.duration ?? 0),
      progress: Number(state.time ?? 0),
      volume: Number(state.volume ?? 1),
      paused: Boolean(state.paused ?? true),
      loop: Boolean(state.loop ?? false),
      muted: Boolean(state.muted ?? false),
      speed: Number(state.speed ?? 1),
    };

    if (mediaControlTarget.tabId !== tabId || mediaControlTarget.index !== mediaIndex) {
      mediaControlTarget = { tabId, index: mediaIndex };
    }

    return {
      mediaItems: createMediaItems(srcList, count),
      playbackState,
    };
  }

  function setMediaIndex(tabId: number, index: number) {
    mediaControlTarget = { tabId, index };
  }

  function handleTabRemoved(tabId: number) {
    if (mediaControlTarget.tabId === tabId) {
      mediaControlTarget = { tabId: 0, index: -1 };
    }
  }

  return {
    buildPanelState,
    handleTabRemoved,
    setMediaIndex,
  };
}
