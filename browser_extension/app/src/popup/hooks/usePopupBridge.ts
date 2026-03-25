import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import { ADVANCED_FEATURES } from "../../shared/constants";
import type {
  AdvancedFeatureKey,
  DesktopRequestResult,
  FeatureStateMap,
  MediaPlaybackState,
  PopupStatePayload,
  TaskAction,
  PopupView,
} from "../../shared/types";
import { sortTasks } from "../../shared/utils";

const REFRESH_INTERVAL_MS = 1000;
const FLASH_TIMEOUT_MS = 2800;

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

function sendMessageToTab<T>(
  tabId: number,
  message: Record<string, unknown>,
  options?: chrome.tabs.MessageSendOptions,
): Promise<T> {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, message, options ?? {}, (response: T) => {
      const lastError = chrome.runtime.lastError;
      if (lastError) {
        reject(new Error(lastError.message));
        return;
      }
      resolve(response);
    });
  });
}

async function highlightTab(tabId: number): Promise<void> {
  const tab = await chrome.tabs.get(tabId);
  if (typeof tab.index === "number" && typeof tab.windowId === "number") {
    await chrome.tabs.highlight({ windowId: tab.windowId, tabs: tab.index });
    return;
  }
  await chrome.tabs.update(tabId, { active: true });
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
    stale: false,
    message: "",
    tabId: null,
    mediaIndex: -1,
    frameId: 0,
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

function createEmptyPayload(): PopupStatePayload {
  return {
    connectionState: "missing_token",
    connectionMessage: "请先在扩展设置里填写配对令牌",
    desktopVersion: "",
    token: "",
    serverUrl: "",
    interceptDownloads: true,
    tasks: [],
    taskCounters: { total: 0, active: 0, completed: 0 },
    resourceState: "restoring",
    resourceStateMessage: "正在恢复已捕获的资源",
    currentResources: [],
    otherResources: [],
    tabId: null,
    activePageDomain: "",
    featureStates: createEmptyFeatureStates(),
    mediaTabs: [],
    mediaItems: [],
    selectedMediaTabId: null,
    selectedMediaIndex: -1,
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
  const [isUpdatingIntercept, setIsUpdatingIntercept] = useState(false);
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

  const saveToken = useCallback(
    async (value: string) => {
      setIsSavingToken(true);
      try {
        const next = await sendRuntimeMessage<PopupStatePayload>({
          type: "popup_set_token",
          token: value.trim(),
          view: requestView(activeViewRef.current),
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
    [applyPopupState, requestView, setFlash],
  );

  const saveServerUrl = useCallback(
    async (value: string) => {
      setIsSavingServerUrl(true);
      try {
        const next = await sendRuntimeMessage<PopupStatePayload>({
          type: "popup_set_server_url",
          serverUrl: value,
          view: requestView(activeViewRef.current),
        });
        applyPopupState(next);
        setFlash(
          next.connectionState === "connected" ? "服务地址已保存并重新连接" : next.connectionMessage,
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
    [applyPopupState, requestView, setFlash],
  );

  const refreshConnection = useCallback(async () => {
    setIsRefreshingConnection(true);
    try {
      const next = await sendRuntimeMessage<PopupStatePayload>({
        type: "popup_refresh_connection",
        view: requestView(activeViewRef.current),
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
  }, [applyPopupState, requestView, setFlash]);

  const setInterceptDownloads = useCallback(
    async (enabled: boolean) => {
      setIsUpdatingIntercept(true);
      try {
        const next = await sendRuntimeMessage<PopupStatePayload>({
          type: "popup_set_intercept_downloads",
          enabled,
          view: requestView(activeViewRef.current),
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
    [applyPopupState, requestView, setFlash],
  );

  const performTaskAction = useCallback(
    async (taskId: string, action: TaskAction) => {
      updateBusyState(setBusyTaskIds, taskId, true);
      try {
        const result = await sendRuntimeMessage<DesktopRequestResult>({
          type: "popup_task_action",
          taskId,
          action,
        });
        if (!result.ok) {
          throw new Error(result.message || "任务操作失败");
        }
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
        const result = await sendRuntimeMessage<DesktopRequestResult>({
          type: "popup_send_resource",
          resourceId,
        });
        if (!result.ok) {
          throw new Error(result.message || "发送资源失败");
        }
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
        const result = await sendRuntimeMessage<DesktopRequestResult>({
          type: "popup_merge_resources",
          resourceIds: ids,
        });
        if (!result.ok) {
          throw new Error(result.message || "在线合并失败");
        }
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
        const result = await sendRuntimeMessage<DesktopRequestResult>({
          type: "popup_toggle_feature",
          feature,
          tabId: payload.tabId,
        });
        if (!result.ok) {
          throw new Error(result.message || "功能切换失败");
        }
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

  const setMediaTarget = useCallback(
    async (tabId: number | null, index: number) => {
      if (!tabId) {
        return;
      }
      try {
        const next = await sendRuntimeMessage<PopupStatePayload>({
          type: "popup_set_media_target",
          tabId,
          index,
        });
        applyPopupState(next);
      } catch (error) {
        setFlash(getErrorMessage(error, "切换媒体失败"), "error");
      }
    },
    [applyPopupState, setFlash],
  );

  const performMediaAction = useCallback(
    async (action: string, value?: number | boolean) => {
      setIsUpdatingMedia(true);
      try {
        const sendDesktopMediaAction = async (nextAction: string, nextValue?: number | boolean) => {
          const result = await sendRuntimeMessage<DesktopRequestResult>({
            type: "popup_media_action",
            action: nextAction,
            value: nextValue,
          });
          if (!result.ok) {
            throw new Error(result.message || "媒体控制失败");
          }
        };

        if (action === "pip" || action === "fullscreen") {
          const tabId = payload.selectedMediaTabId;
          const index = payload.selectedMediaIndex;
          if (!tabId || index < 0) {
            throw new Error("当前没有可控制的媒体");
          }

          if (action === "fullscreen") {
            await highlightTab(tabId);
          }

          const response = await sendMessageToTab<{ ok?: boolean; message?: string }>(
            tabId,
            {
              Message: action === "fullscreen" ? "fullScreen" : "pip",
              index,
            },
            { frameId: payload.mediaPlaybackState.frameId ?? 0 },
          );

          if (response?.ok === false) {
            throw new Error(response.message || "媒体控制失败");
          }

          await refreshState("advanced");
          return;
        }

        if (
          action === "set_volume"
          && typeof value === "number"
          && value > 0
          && payload.mediaPlaybackState.muted
        ) {
          await sendDesktopMediaAction("toggle_muted", false);
        }

        await sendDesktopMediaAction(action, value);
        await refreshState("advanced");
      } catch (error) {
        setFlash(getErrorMessage(error, "媒体控制失败"), "error");
      } finally {
        if (mountedRef.current) {
          setIsUpdatingMedia(false);
        }
      }
    },
    [payload.mediaPlaybackState.frameId, payload.selectedMediaIndex, payload.selectedMediaTabId, refreshState, setFlash],
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
    isUpdatingIntercept,
    isUpdatingMedia,
    saveToken,
    saveServerUrl,
    refreshConnection,
    setInterceptDownloads,
    performTaskAction,
    sendResource,
    mergeResources,
    toggleFeature,
    setMediaTarget,
    performMediaAction,
    sortedTasks,
    isTaskBusy: (taskId: string) => busyTaskIds.has(taskId),
    isResourceBusy: (resourceId: string) => busyResourceIds.has(resourceId),
    isFeatureBusy: (featureKey: AdvancedFeatureKey) => busyFeatureKeys.has(featureKey),
  };
}
