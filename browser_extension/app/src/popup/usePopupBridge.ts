import type {Dispatch, SetStateAction} from "react";
import {useCallback, useEffect, useMemo, useRef, useState} from "react";

import {ADVANCED_FEATURES} from "../shared/constants";
import type {
    AdvancedFeatureKey,
    CommandResult,
    FeatureStateMap,
    MediaAction,
    MediaPlaybackState,
    PopupState,
    PopupView,
    ScannedImage,
    TaskAction,
} from "../shared/types";
import {sortTasks} from "../shared/utils";
import type {ActionCommand, PopupCommand, StateCommand} from "../shared/popup-protocol";
import type {ToastIntent} from "./components/ToastHost";

const REFRESH_INTERVAL_MS = 1000;
const TOAST_TIMEOUT_MS = 2800;

function sendRuntimeMessage<T>(message: unknown): Promise<T> {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response: T) => {
      const lastError = chrome.runtime.lastError;
      if (lastError) {
        reject(new Error(lastError.message));
        return;
      }
      if (response == null) {
        reject(new Error(chrome.i18n.getMessage("errorBackgroundNotReady")));
        return;
      }
      resolve(response);
    });
  });
}

function emptyFeatureStates(): FeatureStateMap {
  const state = {} as FeatureStateMap;
  for (const { key } of ADVANCED_FEATURES) {
    state[key] = false;
  }
  return state;
}

function emptyMediaState(): MediaPlaybackState {
  return {
    isAvailable: false,
    message: "",
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

function emptyPopupState(): PopupState {
  return {
    connectionState: "missing_token",
    connectionMessage: chrome.i18n.getMessage("awaitingPairing"),
    desktopVersion: "",
    token: "",
    serverUrl: "",
    shouldTakeDownloads: true,
    isMediaButtonEnabled: true,
    tasks: [],
    taskCounters: { total: 0, active: 0, completed: 0 },
    resourceState: "restoring",
    resourceStateMessage: chrome.i18n.getMessage("restoringCapturedResources"),
    currentResources: [],
    otherResources: [],
    tabId: null,
    activePageDomain: "",
    featureStates: emptyFeatureStates(),
    mediaItems: [],
    mediaPlaybackState: emptyMediaState(),
    pendingTaskCount: 0,
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

function errorMessageOr(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function dispatch(command: StateCommand): Promise<PopupState>;
function dispatch(command: ActionCommand): Promise<CommandResult>;
function dispatch(command: PopupCommand): Promise<PopupState | CommandResult> {
  return sendRuntimeMessage<PopupState | CommandResult>(command);
}

async function sendActionCommand(command: ActionCommand, fallback: string): Promise<CommandResult> {
  const result = await dispatch(command);
  if (!result.ok) {
    throw new Error(result.message || fallback);
  }
  return result;
}

async function sendFullscreenMessage(tabId: number, index: number) {
  return new Promise<void>((resolve, reject) => {
    chrome.tabs.get(tabId, (tab) => {
      const tabError = chrome.runtime.lastError;
      if (tabError || typeof tab.index !== "number" || typeof tab.windowId !== "number") {
        reject(new Error(tabError?.message || chrome.i18n.getMessage("errorTargetTabNotFound")));
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
  const [payload, setPayload] = useState<PopupState>(emptyPopupState);
  const [busyTaskIds, setBusyTaskIds] = useState<ReadonlySet<string>>(() => new Set());
  const [busyResourceIds, setBusyResourceIds] = useState<ReadonlySet<string>>(() => new Set());
  const [busyFeatureKeys, setBusyFeatureKeys] = useState<ReadonlySet<AdvancedFeatureKey>>(() => new Set());
  const [toastMessage, setToastMessage] = useState("");
  const [toastIntent, setToastIntent] = useState<ToastIntent>("info");
  const [isSavingToken, setIsSavingToken] = useState(false);
  const [isSavingServerUrl, setIsSavingServerUrl] = useState(false);
  const [isRefreshingConnection, setIsRefreshingConnection] = useState(false);
  const [isRequestingPairing, setIsRequestingPairing] = useState(false);
  const [isUpdatingTakeDownloads, setIsUpdatingTakeDownloads] = useState(false);
  const [isUpdatingMediaButton, setIsUpdatingMediaButton] = useState(false);

  const mountedRef = useRef(true);
  const toastTimerRef = useRef<number | null>(null);
  const refreshPromiseRef = useRef<Promise<void> | null>(null);
  const lastContentViewRef = useRef<Exclude<PopupView, "settings">>("tasks");
  const activeViewRef = useRef(activeView);

  const requestView = useCallback((view: PopupView): Exclude<PopupView, "settings"> => {
    return view === "settings" ? lastContentViewRef.current : view;
  }, []);

  const applyPopupState = useCallback((next: PopupState) => {
    if (!mountedRef.current) {
      return;
    }
    setPayload(next);
  }, []);

  const showToast = useCallback((message: string, intent: ToastIntent = "info") => {
    if (!mountedRef.current) {
      return;
    }
    setToastMessage(message);
    setToastIntent(intent);
    if (toastTimerRef.current !== null) {
      window.clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = window.setTimeout(() => {
      if (!mountedRef.current) {
        return;
      }
      setToastMessage("");
      toastTimerRef.current = null;
    }, TOAST_TIMEOUT_MS);
  }, []);

  const refreshState = useCallback(
    async (view: PopupView) => {
      if (refreshPromiseRef.current) {
        return refreshPromiseRef.current;
      }

      refreshPromiseRef.current = (async () => {
        const next = await dispatch({
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
      if (toastTimerRef.current !== null) {
        window.clearTimeout(toastTimerRef.current);
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
        const next = await dispatch({
          type: "popup_set_token",
          token: value.trim(),
          view: requestView(activeViewRef.current),
        });
        applyPopupState(next);
        showToast(
          next.connectionState === "connected" ? chrome.i18n.getMessage("pairingTokenSaved") : next.connectionMessage,
          next.connectionState === "connected" ? "success" : "info",
        );
        return true;
      } catch (error) {
        showToast(errorMessageOr(error, chrome.i18n.getMessage("errorSavePairingTokenFailed")), "error");
        return false;
      } finally {
        if (mountedRef.current) {
          setIsSavingToken(false);
        }
      }
    },
    [applyPopupState, requestView, showToast],
  );

  const saveServerUrl = useCallback(
    async (value: string) => {
      setIsSavingServerUrl(true);
      try {
        const next = await dispatch({
          type: "popup_set_server_url",
          serverUrl: value,
          view: requestView(activeViewRef.current),
        });
        applyPopupState(next);
        showToast(
          next.connectionState === "connected" ? chrome.i18n.getMessage("serverUrlSaved") : next.connectionMessage,
          next.connectionState === "connected" ? "success" : "info",
        );
        return true;
      } catch (error) {
        showToast(errorMessageOr(error, chrome.i18n.getMessage("errorSaveServerUrlFailed")), "error");
        return false;
      } finally {
        if (mountedRef.current) {
          setIsSavingServerUrl(false);
        }
      }
    },
    [applyPopupState, requestView, showToast],
  );

  const refreshConnection = useCallback(async () => {
    setIsRefreshingConnection(true);
    try {
      const next = await dispatch({
        type: "popup_refresh_connection",
        view: requestView(activeViewRef.current),
      });
      applyPopupState(next);
      showToast(next.connectionMessage, next.connectionState === "connected" ? "success" : "info");
      return true;
    } catch (error) {
      showToast(errorMessageOr(error, chrome.i18n.getMessage("errorReconnectFailed")), "error");
      return false;
    } finally {
      if (mountedRef.current) {
        setIsRefreshingConnection(false);
      }
    }
  }, [applyPopupState, requestView, showToast]);

  const requestPairing = useCallback(async () => {
    setIsRequestingPairing(true);
    try {
      const result = await dispatch({
        type: "popup_request_pairing",
      });
      if (!result.ok) {
        throw new Error(result.message || chrome.i18n.getMessage("errorAutoPairingFailed"));
      }
      showToast(result.message || chrome.i18n.getMessage("pairingRequestSentConfirmOnDesktop"));
      void refreshState(activeViewRef.current).catch(() => {
        // Ignore transient popup refresh failures.
      });
      return true;
    } catch (error) {
      showToast(errorMessageOr(error, chrome.i18n.getMessage("errorAutoPairingFailed")), "error");
      return false;
    } finally {
      if (mountedRef.current) {
        setIsRequestingPairing(false);
      }
    }
  }, [refreshState, showToast]);

  const setShouldTakeDownloads = useCallback(
    async (enabled: boolean) => {
      setIsUpdatingTakeDownloads(true);
      try {
        const next = await dispatch({
          type: "popup_set_take_downloads",
          enabled,
          view: requestView(activeViewRef.current),
        });
        applyPopupState(next);
      } catch (error) {
        showToast(errorMessageOr(error, chrome.i18n.getMessage("errorUpdateTakeDownloadsFailed")), "error");
      } finally {
        if (mountedRef.current) {
          setIsUpdatingTakeDownloads(false);
        }
      }
    },
    [applyPopupState, requestView, showToast],
  );

  const setMediaButtonEnabled = useCallback(
    async (enabled: boolean) => {
      setIsUpdatingMediaButton(true);
      try {
        const next = await dispatch({
          type: "popup_set_media_button",
          enabled,
          view: requestView(activeViewRef.current),
        });
        applyPopupState(next);
      } catch (error) {
        showToast(errorMessageOr(error, chrome.i18n.getMessage("errorUpdateMediaButtonFailed")), "error");
      } finally {
        if (mountedRef.current) {
          setIsUpdatingMediaButton(false);
        }
      }
    },
    [applyPopupState, requestView, showToast],
  );

  const sendTaskAction = useCallback(
    async (taskId: string, action: TaskAction) => {
      updateBusyState(setBusyTaskIds, taskId, true);
      try {
        await sendActionCommand({
          type: "popup_task_action",
          taskId,
          action,
        }, chrome.i18n.getMessage("errorTaskActionFailed"));
        await refreshState(activeViewRef.current);
        if (action !== "open_when_done") {
          showToast(chrome.i18n.getMessage("taskActionSent"), "success");
        }
      } catch (error) {
        showToast(errorMessageOr(error, chrome.i18n.getMessage("errorTaskActionFailed")), "error");
      } finally {
        updateBusyState(setBusyTaskIds, taskId, false);
      }
    },
    [refreshState, showToast],
  );

  const sendResource = useCallback(
    async (resourceId: string) => {
      updateBusyState(setBusyResourceIds, resourceId, true);
      try {
        const result = await sendActionCommand({
          type: "popup_send_resource",
          resourceId,
        }, chrome.i18n.getMessage("errorSendResourceFailed"));
        await refreshState(activeViewRef.current);
        showToast(result.message || chrome.i18n.getMessage("resourceProcessed"), "success");
      } catch (error) {
        showToast(errorMessageOr(error, chrome.i18n.getMessage("errorSendResourceFailed")), "error");
      } finally {
        updateBusyState(setBusyResourceIds, resourceId, false);
      }
    },
    [refreshState, showToast],
  );

  const mergeResources = useCallback(
    async (resourceIds: string[]) => {
      const ids = [...new Set(resourceIds.map((value) => String(value || "")).filter(Boolean))];
      ids.forEach((resourceId) => updateBusyState(setBusyResourceIds, resourceId, true));
      try {
        const result = await sendActionCommand({
          type: "popup_merge_resources",
          resourceIds: ids,
        }, chrome.i18n.getMessage("errorOnlineMergeFailed"));
        await refreshState(activeViewRef.current);
        showToast(result.message || chrome.i18n.getMessage("resourceSentToDesktop"), "success");
        return true;
      } catch (error) {
        showToast(errorMessageOr(error, chrome.i18n.getMessage("errorOnlineMergeFailed")), "error");
        return false;
      } finally {
        ids.forEach((resourceId) => updateBusyState(setBusyResourceIds, resourceId, false));
      }
    },
    [refreshState, showToast],
  );

  const toggleFeature = useCallback(
    async (feature: AdvancedFeatureKey) => {
      const tabId = payload.tabId;
      if (tabId == null) {
        showToast(chrome.i18n.getMessage("errorNoActiveTab"), "error");
        return;
      }
      setBusyFeature(feature, true);
      try {
        const result = await sendActionCommand({
          type: "popup_toggle_feature",
          feature,
          tabId,
        }, chrome.i18n.getMessage("errorFeatureToggleFailed"));
        await refreshState(activeViewRef.current);
        showToast(result.message || chrome.i18n.getMessage("featureStateUpdated"), "success");
      } catch (error) {
        showToast(errorMessageOr(error, chrome.i18n.getMessage("errorFeatureToggleFailed")), "error");
      } finally {
        setBusyFeature(feature, false);
      }
    },
    [payload.tabId, refreshState, setBusyFeature, showToast],
  );

  const setMediaIndex = useCallback(
    async (index: number) => {
      const tabId = payload.mediaPlaybackState.tabId;
      if (!tabId) {
        return;
      }
      try {
        const next = await dispatch({
          type: "popup_set_media_index",
          tabId,
          index,
        });
        applyPopupState(next);
      } catch (error) {
        showToast(errorMessageOr(error, chrome.i18n.getMessage("errorSwitchMediaFailed")), "error");
      }
    },
    [applyPopupState, payload.mediaPlaybackState.tabId, showToast],
  );

  const sendMediaAction = useCallback(
    async (action: MediaAction, value?: number | boolean) => {
      // Fullscreen and PiP need a user-gesture context that SW routing loses.
      if (action === "fullscreen" || action === "pip") {
        const tabId = payload.mediaPlaybackState.tabId;
        const index = payload.mediaPlaybackState.mediaIndex;
        if (!tabId || index < 0) {
          showToast(chrome.i18n.getMessage("errorNoControllableMedia"), "error");
          return;
        }
        try {
          if (action === "fullscreen") {
            await sendFullscreenMessage(tabId, index);
          } else {
            chrome.tabs.sendMessage(tabId, { Message: "pip", index });
          }
        } catch (error) {
          showToast(errorMessageOr(error, action === "fullscreen" ? chrome.i18n.getMessage("errorFullscreenFailed") : chrome.i18n.getMessage("errorPipFailed")), "error");
        }
        return;
      }

      try {
        const result = await sendActionCommand(
          { type: "popup_media_action", action, value },
          chrome.i18n.getMessage("errorMediaActionFailed"),
        );
        if (result.playbackState && mountedRef.current) {
          setPayload((prev) => ({ ...prev, mediaPlaybackState: result.playbackState! }));
        }
      } catch (error) {
        showToast(errorMessageOr(error, chrome.i18n.getMessage("errorMediaActionFailed")), "error");
      }
    },
    [payload.mediaPlaybackState.tabId, payload.mediaPlaybackState.mediaIndex, showToast],
  );

  const sendImages = useCallback(
    async (images: ScannedImage[]) => {
      try {
        const [tab] = await new Promise<chrome.tabs.Tab[]>((resolve) => {
          chrome.tabs.query({ active: true, currentWindow: true }, resolve);
        });
        const pageUrl = tab?.url ?? "";
        const result = await sendActionCommand({
          type: "popup_send_images",
          images,
          pageUrl,
        }, chrome.i18n.getMessage("errorSendImagesFailed"));
        showToast(result.message || chrome.i18n.getMessage("imagesSent"), "success");
        return true;
      } catch (error) {
        showToast(errorMessageOr(error, chrome.i18n.getMessage("errorSendImagesFailed")), "error");
        return false;
      }
    },
    [showToast],
  );

  const sortedTasks = useMemo(() => sortTasks(payload.tasks), [payload.tasks]);

  return {
    ...payload,
    toastMessage,
    toastIntent,
    isConnected: payload.connectionState === "connected",
    isSavingToken,
    isSavingServerUrl,
    isRefreshingConnection,
    isRequestingPairing,
    isUpdatingTakeDownloads,
    isUpdatingMediaButton,
    saveToken,
    saveServerUrl,
    refreshConnection,
    requestPairing,
    setShouldTakeDownloads,
    setMediaButtonEnabled,
    sendTaskAction,
    sendResource,
    mergeResources,
    toggleFeature,
    setMediaIndex,
    sendMediaAction,
    sortedTasks,
    isTaskBusy: (taskId: string) => busyTaskIds.has(taskId),
    sendImages,
    isResourceBusy: (resourceId: string) => busyResourceIds.has(resourceId),
    isFeatureBusy: (featureKey: AdvancedFeatureKey) => busyFeatureKeys.has(featureKey),
  };
}
