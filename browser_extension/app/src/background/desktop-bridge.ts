import {CANDIDATE_PORTS, DEFAULT_SERVER_URL} from "../shared/constants";
import type {DesktopConnectionState, CommandResult, TaskSummary,} from "../shared/types";
import {
  PAIR_TOKEN_KEY,
  PROTOCOL_VERSION,
  RECONNECT_ALARM,
  SERVER_URL_KEY,
  SHOULD_AUTO_SELECT_PORT_KEY,
} from "./constants";
import {loadLocalState, saveLocalState} from "./chrome-helpers";

type PendingRequest = {
  resolve: (value: any) => void;
  reject: (reason?: unknown) => void;
  timeoutId: number;
};

type PairingResponse = {
  type?: string;
  ok?: boolean;
  token?: string;
  message?: string;
};

const PAIRING_TIMEOUT_MS = 60000;
const DEFAULT_REQUEST_TIMEOUT_MS = 12000;
const HAPPY_EYEBALLS_DELAY_MS = 150;
const MISSING_PAIRING_MESSAGE = chrome.i18n.getMessage("pendingPairing");

function toFallbackUrls(primaryUrl: string, shouldAutoSelect: boolean): string[] {
  if (!shouldAutoSelect) {
    return [];
  }
  try {
    const parsed = new URL(primaryUrl);
    if (parsed.hostname !== "127.0.0.1" && parsed.hostname !== "localhost") {
      return [];
    }
    const primaryPort = Number(parsed.port);
    const suffix = `${parsed.pathname === "/" && !primaryUrl.endsWith("/") ? "" : parsed.pathname}${parsed.search}`;
    return CANDIDATE_PORTS
      .filter((port) => port !== primaryPort)
      .map((port) => `${parsed.protocol}//${parsed.hostname}:${port}${suffix}`);
  } catch {
    return [];
  }
}

export type DesktopBridgeSnapshot = {
  connectionState: DesktopConnectionState;
  connectionMessage: string;
  desktopVersion: string;
  token: string;
  serverUrl: string;
  tasks: TaskSummary[];
};

export interface DesktopBridgeOptions {
  onTaskSnapshotChanged?: (tasks: TaskSummary[]) => void;
  onConnected?: () => void;
}

export function createDesktopBridge(options: DesktopBridgeOptions = {}) {
  let desktopSocket: WebSocket | null = null;
  let reconnectTimer: number | null = null;
  let installType = "";

  let connectionState: DesktopConnectionState = "missing_token";
  let connectionMessage = MISSING_PAIRING_MESSAGE;
  let desktopVersion = "";
  let pairToken = "";
  let serverUrl = DEFAULT_SERVER_URL;
  let shouldAutoSelectPort = true;
  let taskSnapshot: TaskSummary[] = [];

  const pendingRequests = new Map<string, PendingRequest>();
  let shouldRetryPairing = false;
  let cancelProbe: (() => void) | null = null;

  // Runtime fact about the extension (read once from chrome.management.getSelf in setupBackground).
  // Owned by the bridge instance, not the module, since only connect() consumes it.
  function setInstallType(type: string) {
    installType = type;
  }

  function buildRequestId(): string {
    return crypto.randomUUID();
  }

  function setConnectionState(state: DesktopConnectionState, message: string) {
    connectionState = state;
    connectionMessage = message;
  }

  function rejectPendingRequests(message: string) {
    for (const [requestId, pending] of pendingRequests.entries()) {
      clearTimeout(pending.timeoutId);
      pending.reject(new Error(message));
      pendingRequests.delete(requestId);
    }
  }

  function isReady(): boolean {
    return connectionState === "connected" && desktopSocket?.readyState === WebSocket.OPEN;
  }

  function clearReconnectTimer() {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  function scheduleReconnect() {
    if (!pairToken || reconnectTimer !== null) {
      return;
    }
    reconnectTimer = self.setTimeout(() => {
      reconnectTimer = null;
      void connect();
    }, 2500);
  }

  function onDesktopMessage(rawData: string) {
    let message: Record<string, any>;
    try {
      message = JSON.parse(rawData) as Record<string, any>;
    } catch {
      return;
    }

    if (message.type === "hello_ack") {
      desktopVersion = String(message.appVersion ?? "");
      setConnectionState("connected", chrome.i18n.getMessage("connected"));
      desktopSocket?.send(JSON.stringify({ type: "subscribe_tasks" }));
      options.onConnected?.();
      return;
    }

    if (message.type === "reload") {
      chrome.runtime.reload();
      return;
    }

    if (message.type === "task_snapshot" && Array.isArray(message.tasks)) {
      taskSnapshot = message.tasks as TaskSummary[];
      options.onTaskSnapshotChanged?.(taskSnapshot);
      return;
    }

    if (message.type === "task_action_result") {
      const requestId = String(message.requestId ?? "");
      const pending = pendingRequests.get(requestId);
      if (!pending) {
        return;
      }
      clearTimeout(pending.timeoutId);
      pendingRequests.delete(requestId);
      pending.resolve(message);
      return;
    }

    if (message.type === "create_task_result") {
      const requestId = String(message.requestId ?? "");
      const pending = pendingRequests.get(requestId);
      if (!pending) {
        return;
      }
      clearTimeout(pending.timeoutId);
      pendingRequests.delete(requestId);

      const ok = message.status === "created" || message.status === "drafted";
      pending.resolve({
        ok,
        isDrafted: message.status === "drafted",
        taskId: String(message.taskId ?? ""),
        message: String(message.message ?? ""),
      });
      return;
    }

    if (message.type === "error" && connectionState === "authenticating") {
      const text = String(message.message ?? chrome.i18n.getMessage("errorInvalidPairToken"));
      desktopVersion = "";
      taskSnapshot = [];
      setConnectionState("unauthorized", text);
      rejectPendingRequests(text);
      desktopSocket?.close();
      desktopSocket = null;
    }
  }

  async function connect(force = false): Promise<void> {
    if (!pairToken) {
      cancelProbe?.();
      cancelProbe = null;
      desktopVersion = "";
      taskSnapshot = [];
      setConnectionState("missing_token", MISSING_PAIRING_MESSAGE);
      return;
    }

    if (((desktopSocket && desktopSocket.readyState === WebSocket.OPEN) || cancelProbe !== null) && !force) {
      return;
    }

    clearReconnectTimer();
    cancelProbe?.();
    cancelProbe = null;
    if (desktopSocket) {
      desktopSocket.close();
      desktopSocket = null;
    }

    setConnectionState("connecting", chrome.i18n.getMessage("connecting"));
    const primaryUrl = serverUrl;
    const fallbackUrls = toFallbackUrls(primaryUrl, shouldAutoSelectPort);
    const activeSockets = new Set<WebSocket>();
    let fallbacksStarted = false;
    let headStartTimer: number | null = null;
    let hasFailedError = false;
    let aborted = false;

    const clearHeadStart = () => {
      if (headStartTimer !== null) {
        self.clearTimeout(headStartTimer);
        headStartTimer = null;
      }
    };

    const closeProbes = (except?: WebSocket) => {
      clearHeadStart();
      for (const s of activeSockets) {
        if (s !== except) {
          s.close();
        }
      }
      activeSockets.clear();
    };

    cancelProbe = () => {
      aborted = true;
      closeProbes();
    };

    const rememberUrl = (url: string) => {
      if (url !== serverUrl) {
        serverUrl = url;
        void saveLocalState({ [SERVER_URL_KEY]: serverUrl });
      }
    };

    const startFallbacks = () => {
      if (fallbacksStarted || aborted || desktopSocket !== null) {
        return;
      }
      fallbacksStarted = true;
      clearHeadStart();
      for (const url of fallbackUrls) {
        probe(url, false);
      }
    };

    const probe = (url: string, isPrimary: boolean) => {
      const socket = new WebSocket(url);
      activeSockets.add(socket);

      socket.addEventListener("open", () => {
        if (aborted || !activeSockets.has(socket)) {
          return;
        }
        if (connectionState === "connecting") {
          setConnectionState("authenticating", chrome.i18n.getMessage("authenticating"));
        }
        socket.send(
          JSON.stringify({
            type: "hello",
            protocolVersion: PROTOCOL_VERSION,
            token: pairToken,
            extensionVersion: chrome.runtime.getManifest().version,
            clientKind: "browser_extension",
            installType,
          }),
        );
      });

      socket.addEventListener("message", (event) => {
        const raw = String(event.data ?? "");
        if (desktopSocket === socket) {
          onDesktopMessage(raw);
          return;
        }
        if (aborted || !activeSockets.has(socket)) {
          return;
        }
        let message: Record<string, any>;
        try {
          message = JSON.parse(raw) as Record<string, any>;
        } catch {
          return;
        }
        if (message.type === "hello_ack" || message.type === "error") {
          cancelProbe = null;
          closeProbes(socket);
          desktopSocket = socket;
          rememberUrl(url);
          onDesktopMessage(raw);
        }
      });

      socket.addEventListener("close", () => {
        if (desktopSocket === socket) {
          desktopSocket = null;
          rejectPendingRequests(chrome.i18n.getMessage("connectionClosed"));
          taskSnapshot = [];
          options.onTaskSnapshotChanged?.([]);
          if (connectionState !== "unauthorized" && connectionState !== "missing_token") {
            desktopVersion = "";
            setConnectionState("disconnected", chrome.i18n.getMessage("disconnected"));
            scheduleReconnect();
          }
          return;
        }
        if (aborted || !activeSockets.delete(socket)) {
          return;
        }
        if (isPrimary) {
          startFallbacks();
        }
        if (
          activeSockets.size === 0
          && desktopSocket === null
          && connectionState !== "unauthorized"
          && connectionState !== "missing_token"
        ) {
          cancelProbe = null;
          desktopVersion = "";
          setConnectionState(
            "disconnected",
            chrome.i18n.getMessage(hasFailedError ? "errorConnectionFailed" : "disconnected"),
          );
          scheduleReconnect();
        }
      });

      socket.addEventListener("error", () => {
        if (desktopSocket === socket) {
          if (connectionState !== "unauthorized") {
            desktopVersion = "";
            setConnectionState("disconnected", chrome.i18n.getMessage("errorConnectionFailed"));
          }
          return;
        }
        if (aborted || !activeSockets.has(socket)) {
          return;
        }
        hasFailedError = true;
        if (isPrimary) {
          startFallbacks();
        }
      });
    };

    if (fallbackUrls.length > 0) {
      headStartTimer = self.setTimeout(startFallbacks, HAPPY_EYEBALLS_DELAY_MS);
    }
    probe(primaryUrl, true);
  }

  async function requestPairing(): Promise<void> {
    clearReconnectTimer();
    cancelProbe?.();
    cancelProbe = null;
    setConnectionState("connecting", chrome.i18n.getMessage("pairing"));

    let desktopReached = false;
    try {
      const token = await new Promise<string>((resolve, reject) => {
        const primaryUrl = serverUrl;
        const fallbackUrls = toFallbackUrls(primaryUrl, shouldAutoSelectPort);
        const activeSockets = new Set<WebSocket>();
        let fallbacksStarted = false;
        let headStartTimer: number | null = null;
        let settled = false;
        let hasFailedError = false;
        let timeoutId = 0;

        const clearHeadStart = () => {
          if (headStartTimer !== null) {
            self.clearTimeout(headStartTimer);
            headStartTimer = null;
          }
        };

        const finish = (done: () => void) => {
          if (settled) {
            return;
          }
          settled = true;
          cancelProbe = null;
          clearHeadStart();
          self.clearTimeout(timeoutId);
          for (const s of activeSockets) {
            s.close();
          }
          activeSockets.clear();
          done();
        };

        cancelProbe = () => {
          finish(() => reject(new Error(chrome.i18n.getMessage("errorPairingDisconnected"))));
        };

        timeoutId = self.setTimeout(() => {
          finish(() => reject(new Error(chrome.i18n.getMessage("errorPairingTimeout"))));
        }, PAIRING_TIMEOUT_MS);

        const startFallbacks = () => {
          if (fallbacksStarted || settled) {
            return;
          }
          fallbacksStarted = true;
          clearHeadStart();
          for (const url of fallbackUrls) {
            openCandidate(url, false);
          }
        };

        const openCandidate = (url: string, isPrimary: boolean) => {
          const socket = new WebSocket(url);
          activeSockets.add(socket);

          socket.addEventListener("open", () => {
            if (settled || !activeSockets.has(socket)) {
              return;
            }
            desktopReached = true;
            if (isPrimary) {
              clearHeadStart();
            }
            socket.send(
              JSON.stringify({
                type: "pair_request",
                requestId: buildRequestId(),
                protocolVersion: PROTOCOL_VERSION,
                extensionVersion: chrome.runtime.getManifest().version,
                clientKind: "browser_extension",
              }),
            );
          });

          socket.addEventListener("message", (event) => {
            let response: PairingResponse;
            try {
              response = JSON.parse(String(event.data ?? "")) as PairingResponse;
            } catch {
              return;
            }
            if (response.type !== "pair_result") {
              return;
            }

            if (url !== serverUrl) {
              serverUrl = url;
              void saveLocalState({ [SERVER_URL_KEY]: serverUrl });
            }

            if (!response.ok) {
              finish(() => reject(new Error(response.message || chrome.i18n.getMessage("errorPairingRejected"))));
              return;
            }

            const nextToken = String(response.token ?? "").trim();
            if (!nextToken) {
              finish(() => reject(new Error(chrome.i18n.getMessage("errorNoTokenReturned"))));
              return;
            }

            finish(() => resolve(nextToken));
          });

          socket.addEventListener("close", () => {
            if (settled || !activeSockets.delete(socket)) {
              return;
            }
            if (isPrimary && !desktopReached) {
              startFallbacks();
            }
            if (activeSockets.size === 0) {
              finish(() =>
                reject(
                  new Error(
                    chrome.i18n.getMessage(
                      desktopReached
                        ? "errorPairingDisconnected"
                        : hasFailedError
                          ? "errorConnectionFailed"
                          : "errorPairingDisconnected",
                    ),
                  ),
                ),
              );
            }
          });

          socket.addEventListener("error", () => {
            if (settled || !activeSockets.has(socket)) {
              return;
            }
            hasFailedError = true;
            if (isPrimary && !desktopReached) {
              startFallbacks();
            }
          });
        };

        if (fallbackUrls.length > 0) {
          headStartTimer = self.setTimeout(startFallbacks, HAPPY_EYEBALLS_DELAY_MS);
        }
        openCandidate(primaryUrl, true);
      });
      shouldRetryPairing = false;
      await setToken(token);
    } catch (error: unknown) {
      shouldRetryPairing = !desktopReached;
      const message = error instanceof Error ? error.message : chrome.i18n.getMessage("errorAutoPairingFailed");
      setConnectionState(pairToken ? "disconnected" : "missing_token", message);
      throw error;
    }
  }

  async function sendRequest<T extends CommandResult>(
    payload: Record<string, unknown>,
    timeoutMs?: number,
  ): Promise<T> {
    if (!isReady() || !desktopSocket) {
      throw new Error(chrome.i18n.getMessage("disconnected"));
    }

    const requestId = String(payload.requestId ?? buildRequestId());
    const message = { ...payload, requestId };
    const effectiveTimeout = timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;

    return new Promise<T>((resolve, reject) => {
      const timeoutId = self.setTimeout(() => {
        pendingRequests.delete(requestId);
        reject(new Error(chrome.i18n.getMessage("errorResponseTimeout")));
      }, effectiveTimeout);

      pendingRequests.set(requestId, {
        resolve: (value) => resolve(value as T),
        reject,
        timeoutId,
      });

      desktopSocket?.send(JSON.stringify(message));
    });
  }

  async function loadPersistentState() {
    const localState = await loadLocalState<{
      [PAIR_TOKEN_KEY]: string;
      [SERVER_URL_KEY]: string;
      [SHOULD_AUTO_SELECT_PORT_KEY]: boolean;
    }>({
      [PAIR_TOKEN_KEY]: "",
      [SERVER_URL_KEY]: DEFAULT_SERVER_URL,
      [SHOULD_AUTO_SELECT_PORT_KEY]: true,
    });

    pairToken = String(localState[PAIR_TOKEN_KEY] ?? "").trim();
    serverUrl = String(localState[SERVER_URL_KEY] ?? DEFAULT_SERVER_URL).trim() || DEFAULT_SERVER_URL;
    shouldAutoSelectPort = Boolean(localState[SHOULD_AUTO_SELECT_PORT_KEY] ?? true);
  }

  async function setToken(token: string) {
    pairToken = String(token ?? "").trim();
    await saveLocalState({ [PAIR_TOKEN_KEY]: pairToken });
    if (pairToken) {
      await connect(true);
      return;
    }

    desktopVersion = "";
    taskSnapshot = [];
    if (desktopSocket) {
      desktopSocket.close();
      desktopSocket = null;
    }
    setConnectionState("missing_token", MISSING_PAIRING_MESSAGE);
  }

  async function setServerUrl(nextServerUrl: string) {
    serverUrl = String(nextServerUrl ?? DEFAULT_SERVER_URL).trim() || DEFAULT_SERVER_URL;
    await saveLocalState({ [SERVER_URL_KEY]: serverUrl });
    await connect(true);
  }

  function onLocalStorageChanged(changes: { [key: string]: chrome.storage.StorageChange }) {
    if (changes[PAIR_TOKEN_KEY]) {
      pairToken = String(changes[PAIR_TOKEN_KEY].newValue ?? "").trim();
    }
    if (changes[SERVER_URL_KEY]) {
      serverUrl = String(changes[SERVER_URL_KEY].newValue ?? DEFAULT_SERVER_URL).trim() || DEFAULT_SERVER_URL;
    }
    if (changes[SHOULD_AUTO_SELECT_PORT_KEY]) {
      shouldAutoSelectPort = Boolean(changes[SHOULD_AUTO_SELECT_PORT_KEY].newValue ?? true);
      if (shouldAutoSelectPort && connectionState !== "connected") {
        void connect(true);
      }
    }
  }

  function buildSnapshot(): DesktopBridgeSnapshot {
    return {
      connectionState,
      connectionMessage,
      desktopVersion,
      token: pairToken,
      serverUrl,
      tasks: taskSnapshot,
    };
  }

  function setupReconnectAlarm() {
    chrome.alarms.create(RECONNECT_ALARM, { periodInMinutes: 1 });
  }

  function onReconnectAlarm(alarm: chrome.alarms.Alarm) {
    if (alarm.name !== RECONNECT_ALARM || connectionState === "connected") {
      return;
    }
    if (!pairToken && shouldRetryPairing) {
      void requestPairing().catch(() => {});
      return;
    }
    void connect();
  }

  return {
    buildSnapshot,
    connect,
    setupReconnectAlarm,
    onReconnectAlarm,
    isReady,
    loadPersistentState,
    requestPairing,
    sendRequest,
    setInstallType,
    setServerUrl,
    setToken,
    onLocalStorageChanged,
  };
}
