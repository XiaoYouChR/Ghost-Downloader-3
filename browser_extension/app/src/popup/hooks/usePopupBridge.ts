import type {Dispatch, SetStateAction} from "react";
import {useCallback, useEffect, useMemo, useRef, useState} from "react";

import {ADVANCED_FEATURES} from "../../shared/constants";
import type {
    AdvancedFeatureKey,
    DesktopRequestResult,
    FeatureStateMap,
    MediaPlaybackState,
    PopupStatePayload,
    PopupView,
    TaskAction,
} from "../../shared/types";
import {sortTasks} from "../../shared/utils";

const REFRESH_INTERVAL_MS = 1000;
const FLASH_TIMEOUT_MS = 2800;
const MEDIA_COMMAND_TIMEOUT_MS = 300;

type FlashTone = "neutral" | "success" | "error";

function sendRuntimeMessage<T>(message: unknown): Promise<T> {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response: T) => {
      const lastError = chrome.runtime.lastError;
      if (lastError) {
        reject(new Error(lastError.message));
        return;
      }
      resolve(response);
    });
  });
}

function createEmptyFeatureStates(): FeatureStateMap {
  const state = {} as FeatureStateMap;
  for (const { key } of ADVANCED_FEATURES) {
    state[key] = false;
  }
  return state;
}

function createEmptyMediaState(): MediaPlaybackState {
  return {
    available: false,
    message: "",
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

function createEmptyPayload(): PopupStatePayload {
  return {
    connectionState: "missing_token",
    connectionMessage: "待配对",
    desktopVersion: "",
    token: "",
    serverUrl: "",
    interceptDownloads: true,
    mediaDownloadOverlayEnabled: true,
    tasks: [],
    taskCounters: { total: 0, active: 0, completed: 0 },
    resourceState: "restoring",
    resourceStateMessage: "正在恢复已捕获的资源",
    currentResources: [],
    otherResources: [],
    tabId: null,
    activePageDomain: "",
    featureStates: createEmptyFeatureStates(),
    mediaItems: [],
    mediaPlaybackState: createEmptyMediaState(),
  };
}

function updateBusyState<T>(
  setter: Dispatch<SetStateAction<ReadonlySet<T>>>,
  value: T,
  active: boolean,
) {
  setter((current) => {
    const next = new Set(current);
    if (active) {
      next.add(value);
    } else {
      next.delete(value);
    }
    return next;
  });
}

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

async function sendDesktopCommand(message: unknown, fallback: string) {
  const result = await sendRuntimeMessage<DesktopRequestResult>(message);
  if (!result.ok) {
    throw new Error(result.message || fallback);
  }
  return result;
}

async function sendMediaMessage(tabId: number, message: Record<string, unknown>) {
  return new Promise<void>((resolve, reject) => {
    const timeout = window.setTimeout(resolve, MEDIA_COMMAND_TIMEOUT_MS);

    chrome.tabs.sendMessage(tabId, message, () => {
      window.clearTimeout(timeout);
      const lastError = chrome.runtime.lastError;
      if (lastError && !/message port closed before a response/i.test(lastError.message ?? "")) {
        reject(new Error(lastError.message));
        return;
      }
      resolve();
    });
  });
}

async function sendFullscreenMessage(tabId: number, index: number) {
  return new Promise<void>((resolve, reject) => {
    chrome.tabs.get(tabId, (tab) => {
      const tabError = chrome.runtime.lastError;
      if (tabError || typeof tab.index !== "number" || typeof tab.windowId !== "number") {
        reject(new Error(tabError?.message || "目标标签页不存在"));
        return;
      }

      chrome.tabs.highlight({ windowId: tab.windowId, tabs: tab.index }, () => {
        const highlightError = chrome.runtime.lastError;
        if (highlightError) {
          reject(new Error(highlightError.message));
          return;
        }

        chrome.tabs.sendMessage(tabId, { Message: "fullScreen", index }, () => {
          void chrome.runtime.lastError;
          window.close();
        });
        resolve();
      });
    });
  });
}

export function usePopupBridge(activeView: PopupView) {
  const [payload, setPayload] = useState<PopupStatePayload>(createEmptyPayload);
  const [busyTaskIds, setBusyTaskIds] = useState<ReadonlySet<string>>(() => new Set());
  const [busyResourceIds, setBusyResourceIds] = useState<ReadonlySet<string>>(() => new Set());
  const [busyFeatureKeys, setBusyFeatureKeys] = useState<ReadonlySet<AdvancedFeatureKey>>(() => new Set());
  const [flashMessage, setFlashMessage] = useState("");
  const [flashTone, setFlashTone] = useState<FlashTone>("neutral");
  const [isSavingToken, setIsSavingToken] = useState(false);
  const [isSavingServerUrl, setIsSavingServerUrl] = useState(false);
  const [isRefreshingConnection, setIsRefreshingConnection] = useState(false);
  const [isRequestingPairing, setIsRequestingPairing] = useState(false);
  const [isUpdatingIntercept, setIsUpdatingIntercept] = useState(false);
  const [isUpdatingMediaDownloadOverlay, setIsUpdatingMediaDownloadOverlay] = useState(false);
  const [isUpdatingMedia, setIsUpdatingMedia] = useState(false);

  const mountedRef = useRef(true);
  const flashTimerRef = useRef<number | null>(null);
  const refreshPromiseRef = useRef<Promise<void> | null>(null);
  const lastContentViewRef = useRef<Exclude<PopupView, "settings">>("tasks");
  const activeViewRef = useRef(activeView);

  const requestView = useCallback((view: PopupView): Exclude<PopupView, "settings"> => {
    return view === "settings" ? lastContentViewRef.current : view;
  }, []);

  const applyPopupState = useCallback((next: PopupStatePayload) => {
    if (!mountedRef.current) {
      return;
    }
    setPayload(next);
  }, []);

  const setFlash = useCallback((message: string, tone: FlashTone = "neutral") => {
    if (!mountedRef.current) {
      return;
    }
    setFlashMessage(message);
    setFlashTone(tone);
    if (flashTimerRef.current !== null) {
      window.clearTimeout(flashTimerRef.current);
    }
    flashTimerRef.current = window.setTimeout(() => {
      if (!mountedRef.current) {
        return;
      }
      setFlashMessage("");
      flashTimerRef.current = null;
    }, FLASH_TIMEOUT_MS);
  }, []);

  const refreshState = useCallback(
    async (view: PopupView) => {
      if (refreshPromiseRef.current) {
        return refreshPromiseRef.current;
      }

      refreshPromiseRef.current = (async () => {
        const next = await sendRuntimeMessage<PopupStatePayload>({
          type: "popup_get_state",
          view: requestView(view),
        });
        applyPopupState(next);
      })();

      try {
        await refreshPromiseRef.current;
      } finally {
        refreshPromiseRef.current = null;
      }
    },
    [applyPopupState, requestView],
  );

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (flashTimerRef.current !== null) {
        window.clearTimeout(flashTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    activeViewRef.current = activeView;
    if (activeView !== "settings") {
      lastContentViewRef.current = activeView;
    }
    void refreshState(activeView).catch(() => {
      // Ignore transient popup refresh failures.
    });
  }, [activeView, refreshState]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refreshState(activeViewRef.current).catch(() => {
        // Ignore transient popup polling failures.
      });
    }, REFRESH_INTERVAL_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, [refreshState]);

  const setBusyFeature = useCallback((feature: AdvancedFeatureKey, active: boolean) => {
    updateBusyState(setBusyFeatureKeys, feature, active);
  }, []);

  const requestPopupState = useCallback(
    (message: Record<string, unknown>) =>
      sendRuntimeMessage<PopupStatePayload>({
        ...message,
        view: requestView(activeViewRef.current),
      }),
    [requestView],
  );

  const saveToken = useCallback(
    async (value: string) => {
      setIsSavingToken(true);
      try {
        const next = await requestPopupState({
          type: "popup_set_token",
          token: value.trim(),
        });
        applyPopupState(next);
        setFlash(
          next.connectionState === "connected" ? "配对令牌已保存" : next.connectionMessage,
          next.connectionState === "connected" ? "success" : "neutral",
        );
        return true;
      } catch (error) {
        setFlash(getErrorMessage(error, "保存配对令牌失败"), "error");
        return false;
      } finally {
        if (mountedRef.current) {
          setIsSavingToken(false);
        }
      }
    },
    [applyPopupState, requestPopupState, setFlash],
  );

  const saveServerUrl = useCallback(
    async (value: string) => {
      setIsSavingServerUrl(true);
      try {
        const next = await requestPopupState({
          type: "popup_set_server_url",
          serverUrl: value,
        });
        applyPopupState(next);
        setFlash(
          next.connectionState === "connected" ? "地址已保存" : next.connectionMessage,
          next.connectionState === "connected" ? "success" : "neutral",
        );
        return true;
      } catch (error) {
        setFlash(getErrorMessage(error, "保存服务地址失败"), "error");
        return false;
      } finally {
        if (mountedRef.current) {
          setIsSavingServerUrl(false);
        }
      }
    },
    [applyPopupState, requestPopupState, setFlash],
  );

  const refreshConnection = useCallback(async () => {
    setIsRefreshingConnection(true);
    try {
      const next = await requestPopupState({
        type: "popup_refresh_connection",
      });
      applyPopupState(next);
      setFlash(next.connectionMessage, next.connectionState === "connected" ? "success" : "neutral");
      return true;
    } catch (error) {
      setFlash(getErrorMessage(error, "重新连接失败"), "error");
      return false;
    } finally {
      if (mountedRef.current) {
        setIsRefreshingConnection(false);
      }
    }
  }, [applyPopupState, requestPopupState, setFlash]);

  const requestPairing = useCallback(async () => {
    setIsRequestingPairing(true);
    try {
      const result = await sendRuntimeMessage<DesktopRequestResult>({
        type: "popup_request_pairing",
      });
      if (!result.ok) {
        throw new Error(result.message || "自动配对失败");
      }
      setFlash(result.message || "配对请求已发送，请在桌面端确认");
      void refreshState(activeViewRef.current).catch(() => {
        // Ignore transient popup refresh failures.
      });
      return true;
    } catch (error) {
      setFlash(getErrorMessage(error, "自动配对失败"), "error");
      return false;
    } finally {
      if (mountedRef.current) {
        setIsRequestingPairing(false);
      }
    }
  }, [refreshState, setFlash]);

  const setInterceptDownloads = useCallback(
    async (enabled: boolean) => {
      setIsUpdatingIntercept(true);
      try {
        const next = await requestPopupState({
          type: "popup_set_intercept_downloads",
          enabled,
        });
        applyPopupState(next);
      } catch (error) {
        setFlash(getErrorMessage(error, "更新拦截下载失败"), "error");
      } finally {
        if (mountedRef.current) {
          setIsUpdatingIntercept(false);
        }
      }
    },
    [applyPopupState, requestPopupState, setFlash],
  );

  const setMediaDownloadOverlay = useCallback(
    async (enabled: boolean) => {
      setIsUpdatingMediaDownloadOverlay(true);
      try {
        const next = await requestPopupState({
          type: "popup_set_media_download_overlay",
          enabled,
        });
        applyPopupState(next);
      } catch (error) {
        setFlash(getErrorMessage(error, "更新下载按钮失败"), "error");
      } finally {
        if (mountedRef.current) {
          setIsUpdatingMediaDownloadOverlay(false);
        }
      }
    },
    [applyPopupState, requestPopupState, setFlash],
  );

  const performTaskAction = useCallback(
    async (taskId: string, action: TaskAction) => {
      updateBusyState(setBusyTaskIds, taskId, true);
      try {
        await sendDesktopCommand({
          type: "popup_task_action",
          taskId,
          action,
        }, "任务操作失败");
        await refreshState(activeViewRef.current);
        setFlash("任务操作已发送", "success");
      } catch (error) {
        setFlash(getErrorMessage(error, "任务操作失败"), "error");
      } finally {
        updateBusyState(setBusyTaskIds, taskId, false);
      }
    },
    [refreshState, setFlash],
  );

  const sendResource = useCallback(
    async (resourceId: string) => {
      updateBusyState(setBusyResourceIds, resourceId, true);
      try {
        const result = await sendDesktopCommand({
          type: "popup_send_resource",
          resourceId,
        }, "发送资源失败");
        await refreshState(activeViewRef.current);
        setFlash(result.message || "资源处理成功", "success");
      } catch (error) {
        setFlash(getErrorMessage(error, "发送资源失败"), "error");
      } finally {
        updateBusyState(setBusyResourceIds, resourceId, false);
      }
    },
    [refreshState, setFlash],
  );

  const mergeResources = useCallback(
    async (resourceIds: string[]) => {
      const ids = [...new Set(resourceIds.map((value) => String(value || "")).filter(Boolean))];
      ids.forEach((resourceId) => updateBusyState(setBusyResourceIds, resourceId, true));
      try {
        const result = await sendDesktopCommand({
          type: "popup_merge_resources",
          resourceIds: ids,
        }, "在线合并失败");
        await refreshState(activeViewRef.current);
        setFlash(result.message || "资源已发送到 Ghost Downloader", "success");
        return true;
      } catch (error) {
        setFlash(getErrorMessage(error, "在线合并失败"), "error");
        return false;
      } finally {
        ids.forEach((resourceId) => updateBusyState(setBusyResourceIds, resourceId, false));
      }
    },
    [refreshState, setFlash],
  );

  const toggleFeature = useCallback(
    async (feature: AdvancedFeatureKey) => {
      if (payload.tabId == null) {
        setFlash("当前没有可操作的标签页", "error");
        return;
      }
      setBusyFeature(feature, true);
      try {
        const result = await sendDesktopCommand({
          type: "popup_toggle_feature",
          feature,
          tabId: payload.tabId,
        }, "功能切换失败");
        await refreshState(activeViewRef.current);
        setFlash(result.message || "功能状态已更新", "success");
      } catch (error) {
        setFlash(getErrorMessage(error, "功能切换失败"), "error");
      } finally {
        setBusyFeature(feature, false);
      }
    },
    [payload.tabId, refreshState, setBusyFeature, setFlash],
  );

  const setMediaIndex = useCallback(
    async (index: number) => {
      const tabId = payload.mediaPlaybackState.tabId;
      if (!tabId) {
        return;
      }
      try {
        const next = await sendRuntimeMessage<PopupStatePayload>({
          type: "popup_set_media_index",
          tabId,
          index,
        });
        applyPopupState(next);
      } catch (error) {
        setFlash(getErrorMessage(error, "切换媒体失败"), "error");
      }
    },
    [applyPopupState, payload.mediaPlaybackState.tabId, setFlash],
  );

  const performMediaAction = useCallback(
    async (action: string, value?: number | boolean) => {
      setIsUpdatingMedia(true);
      try {
        const tabId = payload.mediaPlaybackState.tabId;
        const index = payload.mediaPlaybackState.mediaIndex;
        if (!tabId || index < 0) {
          throw new Error("当前没有可控制的媒体");
        }

        if (action === "fullscreen") {
          await sendFullscreenMessage(tabId, index);
          return;
        }

        const mediaMessage: Record<string, unknown> = { index };
        switch (action) {
          case "toggle_play":
            mediaMessage.Message = payload.mediaPlaybackState.paused ? "play" : "pause";
            break;
          case "set_speed":
            mediaMessage.Message = "speed";
            mediaMessage.speed = Number(value ?? 1);
            break;
          case "pip":
            mediaMessage.Message = "pip";
            break;
          case "screenshot":
            mediaMessage.Message = "screenshot";
            break;
          case "toggle_loop":
            mediaMessage.Message = "loop";
            mediaMessage.action = Boolean(value);
            break;
          case "toggle_muted":
            mediaMessage.Message = "muted";
            mediaMessage.action = Boolean(value);
            break;
          case "set_volume":
            mediaMessage.Message = "setVolume";
            mediaMessage.volume = Number(value ?? 1);
            break;
          case "set_time":
            mediaMessage.Message = "setTime";
            mediaMessage.time = Number(value ?? 0);
            break;
          default:
            throw new Error("未知的媒体操作");
        }

        if (
          action === "set_volume"
          && typeof value === "number"
          && value > 0
          && payload.mediaPlaybackState.muted
        ) {
          await sendMediaMessage(tabId, { Message: "muted", action: false, index });
        }

        await sendMediaMessage(tabId, mediaMessage);
        await refreshState("advanced");
      } catch (error) {
        setFlash(getErrorMessage(error, "媒体控制失败"), "error");
      } finally {
        if (mountedRef.current) {
          setIsUpdatingMedia(false);
        }
      }
    },
    [
      payload.mediaPlaybackState.muted,
      payload.mediaPlaybackState.paused,
      payload.mediaPlaybackState.tabId,
      payload.mediaPlaybackState.mediaIndex,
      refreshState,
      setFlash,
    ],
  );

  const sortedTasks = useMemo(() => sortTasks(payload.tasks), [payload.tasks]);

  return {
    ...payload,
    flashMessage,
    flashTone,
    isConnected: payload.connectionState === "connected",
    isSavingToken,
    isSavingServerUrl,
    isRefreshingConnection,
    isRequestingPairing,
    isUpdatingIntercept,
    isUpdatingMediaDownloadOverlay,
    isUpdatingMedia,
    saveToken,
    saveServerUrl,
    refreshConnection,
    requestPairing,
    setInterceptDownloads,
    setMediaDownloadOverlay,
    performTaskAction,
    sendResource,
    mergeResources,
    toggleFeature,
    setMediaIndex,
    performMediaAction,
    sortedTasks,
    isTaskBusy: (taskId: string) => busyTaskIds.has(taskId),
    isResourceBusy: (resourceId: string) => busyResourceIds.has(resourceId),
    isFeatureBusy: (featureKey: AdvancedFeatureKey) => busyFeatureKeys.has(featureKey),
  };
}
