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

type ProbeHandlers = {
  onOpen: (socket: WebSocket) => void;
  isAnswer: (message: Record<string, any>) => boolean;
  shouldHoldFallbacksOnPrimaryOpen?: boolean;
  timeoutMs?: number;
};

type ProbeResult =
  | { kind: "answered"; socket: WebSocket; message: Record<string, any>; url: string }
  | { kind: "lost"; reason: "closed" | "timeout" | "aborted"; hasReachedDesktop: boolean; hasFailedError: boolean };

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
  let shouldRetryPairing = true;
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
      void connect(false, false);
    }, 2500);
  }

  /** Settles exactly once; an answered socket is handed back open. A newer probe aborts this one. */
  function probeCandidates(shouldProbeFallbacks: boolean, handlers: ProbeHandlers): Promise<ProbeResult> {
    clearReconnectTimer();
    cancelProbe?.();

    const fallbackUrls = shouldProbeFallbacks ? toFallbackUrls(serverUrl, shouldAutoSelectPort) : [];
    const activeSockets = new Set<WebSocket>();
    let hasStartedFallbacks = false;
    let headStartTimer: number | null = null;
    let timeoutId = 0;
    let hasFailedError = false;
    let hasReachedDesktop = false;
    let isSettled = false;
    let resolve!: (result: ProbeResult) => void;
    const settled = new Promise<ProbeResult>((onSettled) => {
      resolve = onSettled;
    });

    const clearHeadStart = () => {
      if (headStartTimer !== null) {
        self.clearTimeout(headStartTimer);
        headStartTimer = null;
      }
    };

    const startFallbacks = () => {
      if (hasStartedFallbacks || isSettled || fallbackUrls.length === 0) {
        return;
      }
      hasStartedFallbacks = true;
      clearHeadStart();
      for (const url of fallbackUrls) {
        openSocket(url, false);
      }
    };

    const finish = (result: ProbeResult) => {
      if (isSettled) {
        return;
      }
      isSettled = true;
      if (cancelProbe === abort) {
        cancelProbe = null;
      }
      clearHeadStart();
      self.clearTimeout(timeoutId);
      const winner = result.kind === "answered" ? result.socket : null;
      for (const socket of activeSockets) {
        if (socket !== winner) {
          socket.close();
        }
      }
      activeSockets.clear();
      resolve(result);
    };

    const lose = (reason: "closed" | "timeout" | "aborted") => {
      finish({ kind: "lost", reason, hasReachedDesktop, hasFailedError });
    };

    const abort = () => lose("aborted");

    const openSocket = (url: string, isPrimary: boolean) => {
      const socket = new WebSocket(url);
      activeSockets.add(socket);

      socket.addEventListener("open", () => {
        if (isSettled || !activeSockets.has(socket)) {
          return;
        }
        hasReachedDesktop = true;
        if (isPrimary && handlers.shouldHoldFallbacksOnPrimaryOpen) {
          clearHeadStart();
        }
        handlers.onOpen(socket);
      });

      socket.addEventListener("message", (event) => {
        let message: Record<string, any>;
        try {
          message = JSON.parse(String(event.data ?? "")) as Record<string, any>;
        } catch {
          return;
        }
        if (isSettled || !activeSockets.has(socket)) {
          if (desktopSocket === socket) {
            onDesktopMessage(message);
          }
          return;
        }
        if (handlers.isAnswer(message)) {
          finish({ kind: "answered", socket, message, url });
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
        if (isSettled || !activeSockets.delete(socket)) {
          return;
        }
        if (isPrimary) {
          startFallbacks();
        }
        if (activeSockets.size === 0) {
          lose("closed");
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
        if (isSettled || !activeSockets.has(socket)) {
          return;
        }
        hasFailedError = true;
        if (isPrimary) {
          startFallbacks();
        }
      });
    };

    cancelProbe = abort;
    if (handlers.timeoutMs) {
      timeoutId = self.setTimeout(() => lose("timeout"), handlers.timeoutMs);
    }
    if (fallbackUrls.length > 0) {
      headStartTimer = self.setTimeout(startFallbacks, HAPPY_EYEBALLS_DELAY_MS);
    }
    openSocket(serverUrl, true);
    return settled;
  }

  function onDesktopMessage(message: Record<string, any>) {

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

  function saveServerUrl(url: string) {
    if (url !== serverUrl) {
      serverUrl = url;
      void saveLocalState({ [SERVER_URL_KEY]: serverUrl });
    }
  }

  async function connect(isForced = false, shouldProbeFallbacks = true): Promise<void> {
    if (
      (
        (desktopSocket && desktopSocket.readyState === WebSocket.OPEN)
        || cancelProbe !== null
        || connectionState === "unauthorized"
      )
      && !isForced
    ) {
      return;
    }

    if (!pairToken) {
      if (shouldRetryPairing) {
        void requestPairing(shouldProbeFallbacks);
        return;
      }
      cancelProbe?.();
      desktopVersion = "";
      taskSnapshot = [];
      setConnectionState("missing_token", MISSING_PAIRING_MESSAGE);
      return;
    }

    if (desktopSocket) {
      desktopSocket.close();
      desktopSocket = null;
    }

    setConnectionState("connecting", chrome.i18n.getMessage("connecting"));

    const result = await probeCandidates(shouldProbeFallbacks, {
      onOpen: (socket) => {
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
      },
      isAnswer: (message) => message.type === "hello_ack" || message.type === "error",
    });

    if (result.kind === "answered") {
      desktopSocket = result.socket;
      saveServerUrl(result.url);
      onDesktopMessage(result.message);
      return;
    }
    if (result.reason !== "aborted" && connectionState !== "unauthorized" && connectionState !== "missing_token") {
      desktopVersion = "";
      setConnectionState(
        "disconnected",
        chrome.i18n.getMessage(result.hasFailedError ? "errorConnectionFailed" : "disconnected"),
      );
    }
  }

  async function requestPairing(shouldProbeFallbacks = true): Promise<void> {
    setConnectionState("connecting", chrome.i18n.getMessage("pairing"));

    const result = await probeCandidates(shouldProbeFallbacks, {
      onOpen: (socket) => {
        socket.send(
          JSON.stringify({
            type: "pair_request",
            requestId: buildRequestId(),
            protocolVersion: PROTOCOL_VERSION,
            extensionVersion: chrome.runtime.getManifest().version,
            clientKind: "browser_extension",
          }),
        );
      },
      isAnswer: (message) => message.type === "pair_result",
      shouldHoldFallbacksOnPrimaryOpen: true,
      timeoutMs: PAIRING_TIMEOUT_MS,
    });

    // An aborted pairing was superseded; the newer probe owns the connection state.
    if (result.kind === "lost" && result.reason === "aborted") {
      return;
    }
    if (result.kind === "lost") {
      shouldRetryPairing = !result.hasReachedDesktop;
      const messageKey = result.reason === "timeout"
        ? "errorPairingTimeout"
        : result.hasFailedError && !result.hasReachedDesktop
          ? "errorConnectionFailed"
          : "errorPairingDisconnected";
      setConnectionState(pairToken ? "disconnected" : "missing_token", chrome.i18n.getMessage(messageKey));
      return;
    }

    result.socket.close();
    saveServerUrl(result.url);
    shouldRetryPairing = false;
    const response = result.message as PairingResponse;
    const token = String(response.token ?? "").trim();
    if (response.ok && token) {
      await setToken(token);
      return;
    }
    setConnectionState(
      pairToken ? "disconnected" : "missing_token",
      response.ok
        ? chrome.i18n.getMessage("errorNoTokenReturned")
        : response.message || chrome.i18n.getMessage("errorPairingRejected"),
    );
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
    if (alarm.name !== RECONNECT_ALARM) {
      return;
    }
    void connect(false, false);
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
