import { DEFAULT_SERVER_URL } from "../shared/constants";
import type {
  DesktopConnectionState,
  DesktopRequestResult,
  GenericTaskSummary,
} from "../shared/types";
import {
  PAIR_TOKEN_KEY,
  PROTOCOL_VERSION,
  RECONNECT_ALARM,
  SERVER_URL_KEY,
} from "./constants";
import { localStorageGet, localStorageSet } from "./chrome-helpers";

type PendingRequest = {
  resolve: (value: any) => void;
  reject: (reason?: unknown) => void;
  timeoutId: number;
};

export type DesktopBridgeSnapshot = {
  connectionState: DesktopConnectionState;
  connectionMessage: string;
  desktopVersion: string;
  token: string;
  serverUrl: string;
  tasks: GenericTaskSummary[];
};

export function createDesktopBridge() {
  let desktopSocket: WebSocket | null = null;
  let reconnectTimer: number | null = null;

  let connectionState: DesktopConnectionState = "missing_token";
  let connectionMessage = "请先在扩展设置里填写配对令牌";
  let desktopVersion = "";
  let pairToken = "";
  let serverUrl = DEFAULT_SERVER_URL;
  let taskSnapshot: GenericTaskSummary[] = [];

  const pendingRequests = new Map<string, PendingRequest>();

  function nextRequestId(): string {
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

  function handleDesktopMessage(rawData: string) {
    let message: Record<string, any>;
    try {
      message = JSON.parse(rawData) as Record<string, any>;
    } catch {
      return;
    }

    if (message.type === "hello_ack") {
      desktopVersion = String(message.appVersion ?? "");
      setConnectionState("connected", "已连接");
      desktopSocket?.send(JSON.stringify({ type: "subscribe_tasks", requestId: nextRequestId() }));
      return;
    }

    if (message.type === "task_snapshot" && Array.isArray(message.tasks)) {
      taskSnapshot = message.tasks as GenericTaskSummary[];
      return;
    }

    if (message.type === "create_task_result" || message.type === "task_action_result") {
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

    if (message.type === "error" && connectionState === "authenticating") {
      const text = String(message.message ?? "配对令牌无效");
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
      desktopVersion = "";
      taskSnapshot = [];
      setConnectionState("missing_token", "请先在扩展设置里填写配对令牌");
      return;
    }

    if (desktopSocket && desktopSocket.readyState === WebSocket.OPEN && !force) {
      return;
    }

    clearReconnectTimer();
    if (force && desktopSocket) {
      desktopSocket.close();
      desktopSocket = null;
    }

    setConnectionState("connecting", "正在连接 Ghost Downloader");
    const socket = new WebSocket(serverUrl);
    desktopSocket = socket;

    socket.addEventListener("open", () => {
      if (desktopSocket !== socket) {
        return;
      }
      setConnectionState("authenticating", "正在校验配对令牌");
      socket.send(
        JSON.stringify({
          type: "hello",
          protocolVersion: PROTOCOL_VERSION,
          token: pairToken,
          extensionVersion: chrome.runtime.getManifest().version,
          clientKind: "chromium_popup",
        }),
      );
    });

    socket.addEventListener("message", (event) => {
      if (desktopSocket !== socket) {
        return;
      }
      handleDesktopMessage(String(event.data ?? ""));
    });

    socket.addEventListener("close", () => {
      if (desktopSocket !== socket) {
        return;
      }
      desktopSocket = null;
      rejectPendingRequests("与 Ghost Downloader 的连接已断开");
      if (connectionState !== "unauthorized" && connectionState !== "missing_token") {
        desktopVersion = "";
        setConnectionState("disconnected", "未连接");
        scheduleReconnect();
      }
    });

    socket.addEventListener("error", () => {
      if (desktopSocket !== socket) {
        return;
      }
      if (connectionState !== "unauthorized") {
        desktopVersion = "";
        setConnectionState("disconnected", "无法连接到 Ghost Downloader");
      }
    });
  }

  async function sendRequest<T extends DesktopRequestResult>(payload: Record<string, unknown>): Promise<T> {
    if (!isReady() || !desktopSocket) {
      throw new Error("Ghost Downloader 未连接");
    }

    const requestId = String(payload.requestId ?? nextRequestId());
    const message = { ...payload, requestId };

    return new Promise<T>((resolve, reject) => {
      const timeoutId = self.setTimeout(() => {
        pendingRequests.delete(requestId);
        reject(new Error("等待 Ghost Downloader 响应超时"));
      }, 12000);

      pendingRequests.set(requestId, {
        resolve: (value) => resolve(value as T),
        reject,
        timeoutId,
      });

      desktopSocket?.send(JSON.stringify(message));
    });
  }

  async function loadPersistentState() {
    const localState = await localStorageGet<{
      [PAIR_TOKEN_KEY]: string;
      [SERVER_URL_KEY]: string;
    }>({
      [PAIR_TOKEN_KEY]: "",
      [SERVER_URL_KEY]: DEFAULT_SERVER_URL,
    });

    pairToken = String(localState[PAIR_TOKEN_KEY] ?? "").trim();
    serverUrl = String(localState[SERVER_URL_KEY] ?? DEFAULT_SERVER_URL).trim() || DEFAULT_SERVER_URL;
  }

  async function setToken(token: string) {
    pairToken = String(token ?? "").trim();
    await localStorageSet({ [PAIR_TOKEN_KEY]: pairToken });
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
    setConnectionState("missing_token", "请先在扩展设置里填写配对令牌");
  }

  async function setServerUrl(nextServerUrl: string) {
    serverUrl = String(nextServerUrl ?? DEFAULT_SERVER_URL).trim() || DEFAULT_SERVER_URL;
    await localStorageSet({ [SERVER_URL_KEY]: serverUrl });
    await connect(true);
  }

  function syncLocalStorageChanges(changes: { [key: string]: chrome.storage.StorageChange }) {
    if (changes[PAIR_TOKEN_KEY]) {
      pairToken = String(changes[PAIR_TOKEN_KEY].newValue ?? "").trim();
    }
    if (changes[SERVER_URL_KEY]) {
      serverUrl = String(changes[SERVER_URL_KEY].newValue ?? DEFAULT_SERVER_URL).trim() || DEFAULT_SERVER_URL;
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

  function ensureReconnectAlarm() {
    chrome.alarms.create(RECONNECT_ALARM, { periodInMinutes: 1 });
  }

  function handleReconnectAlarm(alarm: chrome.alarms.Alarm) {
    if (alarm.name !== RECONNECT_ALARM || connectionState === "connected") {
      return;
    }
    void connect();
  }

  return {
    buildSnapshot,
    connect,
    ensureReconnectAlarm,
    handleReconnectAlarm,
    isReady,
    loadPersistentState,
    sendRequest,
    setServerUrl,
    setToken,
    syncLocalStorageChanges,
  };
}
