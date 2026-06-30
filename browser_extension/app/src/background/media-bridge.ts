import {filenameFromUrl, truncate} from "../shared/utils";
import type {MediaAction, MediaItemOption, MediaPlaybackState} from "../shared/types";
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

type BuiltMediaPanelState = {
  mediaItems: MediaItemOption[];
  playbackState: MediaPlaybackState;
};

// Single source of truth for "which media are we controlling". Built by buildPanelState
// (popup-driven poll) and refreshed by runAction (re-probe before commanding). Merging
// tabId/index/playbackState into one snapshot eliminates the split where index came from
// mediaControlTarget but isPaused came from lastPlaybackState — they could disagree about
// which video they described, sending toggle_play in the wrong direction.
type MediaSnapshot = {
  tabId: number;
  index: number;
  playbackState: MediaPlaybackState;
};

export function createMediaBridge() {
  let mediaSnapshot: MediaSnapshot | null = null;

  function createEmptyPlaybackState(message = "当前未检测到可控制媒体"): MediaPlaybackState {
    return {
      isAvailable: false,
      message,
      tabId: null,
      mediaIndex: -1,
      currentTime: 0,
      duration: 0,
      progress: 0,
      volume: 1,
      isPaused: true,
      shouldLoop: false,
      isMuted: false,
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
        label: truncate(filenameFromUrl(src) || src.split("/").pop() || src, 48),
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

  // Pure builder — the deep module that turns a raw getVideoState response into the
  // canonical playback state. Shared by buildPanelState (popup poll) and runAction
  // (pre-command re-probe) so both see the same shape.
  function buildPlaybackState(tabId: number, index: number, state: RawMediaState): MediaPlaybackState {
    return {
      isAvailable: true,
      message: "",
      tabId,
      mediaIndex: index,
      currentTime: Number(state.currentTime ?? 0),
      duration: Number(state.duration ?? 0),
      progress: Number(state.time ?? 0),
      volume: Number(state.volume ?? 1),
      isPaused: Boolean(state.paused ?? true),
      shouldLoop: Boolean(state.loop ?? false),
      isMuted: Boolean(state.muted ?? false),
      speed: Number(state.speed ?? 1),
    };
  }

  async function requestMediaState(tabId: number, index: number): Promise<TabMessageResult<RawMediaState>> {
    return sendMessageToTab<RawMediaState>(
      tabId,
      { Message: "getVideoState", index },
      { frameId: MAIN_FRAME_ID },
    );
  }

  // Fire-and-forget a cat-catch command to the content script. The content script executes
  // synchronously and never calls sendResponse, so no_response and runtime_error (port closed
  // before a response) are expected successes. Only no_receiver is a real failure — it means
  // the content script isn't loaded on this tab.
  async function sendMediaCommand(tabId: number, message: Record<string, unknown>): Promise<void> {
    const result = await sendMessageToTab<void>(tabId, message, { frameId: MAIN_FRAME_ID });
    if (result.status === "no_receiver") {
      throw new Error("当前页面的媒体桥接还没有准备好");
    }
  }

  function buildMediaMessage(
    action: MediaAction,
    value: number | boolean | undefined,
    snapshot: MediaSnapshot,
  ): Record<string, unknown> | null {
    const {index, playbackState} = snapshot;
    switch (action) {
      case "toggle_play":
        return { Message: playbackState.isPaused ? "play" : "pause", index };
      case "set_speed":
        return { Message: "speed", speed: Number(value ?? 1), index };
      case "pip":
        return { Message: "pip", index };
      case "screenshot":
        return { Message: "screenshot", index };
      case "toggle_loop":
        return { Message: "loop", action: Boolean(value), index };
      case "toggle_muted":
        return { Message: "muted", action: Boolean(value), index };
      case "set_volume":
        return { Message: "setVolume", volume: Number(value ?? 1), index };
      case "set_time":
        return { Message: "setTime", time: Number(value ?? 0), index };
      case "fullscreen":
        // Owned by the popup (needs window.close); the SW never receives this action.
        return null;
      default: {
        const exhaustive: never = action;
        void exhaustive;
        return null;
      }
    }
  }

  async function buildPanelState(activeTabId: number | null): Promise<BuiltMediaPanelState> {
    const tabId = activeTabId;
    // When the popup isn't on the advanced view, activeTabId is null. Don't touch the
    // snapshot — the user may switch back and expect their video selection to persist.
    if (!tabId) {
      return createEmptyMediaPanelState("当前没有可操作的标签页");
    }

    let mediaIndex = mediaSnapshot?.tabId === tabId ? mediaSnapshot.index : 0;
    const result = await requestMediaState(tabId, mediaIndex >= 0 ? mediaIndex : 0);

    const state = result.response;
    if (result.status !== "ok" || !state?.count) {
      mediaSnapshot = null;
      return createEmptyMediaPanelState(mediaFailureMessage(result));
    }

    const count = Number(state.count ?? 0);
    mediaIndex = mediaIndex >= 0 && mediaIndex < count ? mediaIndex : 0;
    const srcList = Array.isArray(state.src) ? state.src : [];

    const playbackState = buildPlaybackState(tabId, mediaIndex, state);
    mediaSnapshot = { tabId, index: mediaIndex, playbackState };

    return {
      mediaItems: createMediaItems(srcList, count),
      playbackState,
    };
  }

  // Re-probe before commanding. The snapshot from buildPanelState (or setMediaIndex) may be
  // stale: the video list could have shrunk, leaving index pointing past the end — which
  // makes upstream content-script.js throw on videoObj[index].currentTime. Refreshing here
  // also gives toggle_play a fresh isPaused, so play/pause direction matches the live state
  // rather than what the popup last polled.
  async function runAction(action: MediaAction, value?: number | boolean): Promise<MediaPlaybackState> {
    if (!mediaSnapshot) {
      throw new Error("当前没有可控制的媒体");
    }

    const tabId = mediaSnapshot.tabId;
    const index = mediaSnapshot.index;
    const current = mediaSnapshot.playbackState;

    // Only toggle_play needs a fresh isPaused — all other actions use the cached snapshot.
    if (action === "toggle_play") {
      const probe = await requestMediaState(tabId, index);
      if (probe.status === "ok" && probe.response?.count) {
        const fresh = buildPlaybackState(tabId, index, probe.response);
        mediaSnapshot = { tabId, index, playbackState: fresh };
      }
    }

    const message = buildMediaMessage(action, value, mediaSnapshot);
    if (!message) {
      return current;
    }

    if (
      action === "set_volume"
      && typeof value === "number"
      && value > 0
      && mediaSnapshot.playbackState.isMuted
    ) {
      await sendMediaCommand(tabId, { Message: "muted", action: false, index });
    }

    await sendMediaCommand(tabId, message);

    // Optimistic update — predict the new state from the action.
    const optimistic = { ...mediaSnapshot.playbackState };
    switch (action) {
      case "toggle_play": optimistic.isPaused = !mediaSnapshot.playbackState.isPaused; break;
      case "set_speed": optimistic.speed = Number(value ?? 1); break;
      case "set_volume": optimistic.volume = Number(value ?? 1); optimistic.isMuted = false; break;
      case "set_time": optimistic.currentTime = Number(value ?? 0); break;
      case "toggle_loop": optimistic.shouldLoop = Boolean(value); break;
      case "toggle_muted": optimistic.isMuted = Boolean(value); break;
    }
    mediaSnapshot = { tabId, index, playbackState: optimistic };
    return optimistic;
  }

  function setMediaIndex(tabId: number, index: number) {
    if (!mediaSnapshot || mediaSnapshot.tabId !== tabId) {
      return;
    }
    mediaSnapshot.index = index;
    mediaSnapshot.playbackState.mediaIndex = index;
  }

  function onTabRemoved(tabId: number) {
    if (mediaSnapshot?.tabId === tabId) {
      mediaSnapshot = null;
    }
  }

  return {
    buildPanelState,
    runAction,
    onTabRemoved,
    setMediaIndex,
  };
}
