import {DEFAULT_SERVER_URL} from "../shared/constants";
import type {DesktopConnectionState, CommandResult, TaskSummary,} from "../shared/types";
import {PAIR_TOKEN_KEY, PROTOCOL_VERSION, RECONNECT_ALARM, SERVER_URL_KEY,} from "./constants";
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
const MISSING_PAIRING_MESSAGE = "待配对";

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
  let taskSnapshot: TaskSummary[] = [];

  const pendingRequests = new Map<string, PendingRequest>();

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
      setConnectionState("connected", "已连接");
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
        taskId: String(message.taskId ?? ""),
        message: String(message.message ?? ""),
      });
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
      setConnectionState("missing_token", MISSING_PAIRING_MESSAGE);
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

    setConnectionState("connecting", "连接中");
    const socket = new WebSocket(serverUrl);
    desktopSocket = socket;

    socket.addEventListener("open", () => {
      if (desktopSocket !== socket) {
        return;
      }
      setConnectionState("authenticating", "校验中");
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
      if (desktopSocket !== socket) {
        return;
      }
      onDesktopMessage(String(event.data ?? ""));
    });

    socket.addEventListener("close", () => {
      if (desktopSocket !== socket) {
        return;
      }
      desktopSocket = null;
      rejectPendingRequests("连接断开");
      taskSnapshot = [];
      options.onTaskSnapshotChanged?.([]);
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
        setConnectionState("disconnected", "连接失败");
      }
    });
  }

  async function requestPairing(): Promise<void> {
    clearReconnectTimer();
    setConnectionState("connecting", "配对中");

    try {
      const token = await new Promise<string>((resolve, reject) => {
        const socket = new WebSocket(serverUrl);
        let settled = false;
        let timeoutId = 0;

        const finish = (done: () => void) => {
          if (settled) {
            return;
          }
          settled = true;
          self.clearTimeout(timeoutId);
          socket.close();
          done();
        };

        timeoutId = self.setTimeout(() => {
          finish(() => reject(new Error("配对超时")));
        }, PAIRING_TIMEOUT_MS);

        socket.addEventListener("open", () => {
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

          if (!response.ok) {
            finish(() => reject(new Error(response.message || "已拒绝配对")));
            return;
          }

          const token = String(response.token ?? "").trim();
          if (!token) {
            finish(() => reject(new Error("未返回令牌")));
            return;
          }

          finish(() => resolve(token));
        });

        socket.addEventListener("close", () => {
          finish(() => reject(new Error("配对断开")));
        });

        socket.addEventListener("error", () => {
          finish(() => reject(new Error("连接失败")));
        });
      });
      await setToken(token);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "自动配对失败";
      setConnectionState(pairToken ? "disconnected" : "missing_token", message);
      throw error;
    }
  }

  async function sendRequest<T extends CommandResult>(
    payload: Record<string, unknown>,
    timeoutMs?: number,
  ): Promise<T> {
    if (!isReady() || !desktopSocket) {
      throw new Error("未连接");
    }

    const requestId = String(payload.requestId ?? buildRequestId());
    const message = { ...payload, requestId };
    const effectiveTimeout = timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;

    return new Promise<T>((resolve, reject) => {
      const timeoutId = self.setTimeout(() => {
        pendingRequests.delete(requestId);
        reject(new Error("响应超时"));
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
    }>({
      [PAIR_TOKEN_KEY]: "",
      [SERVER_URL_KEY]: DEFAULT_SERVER_URL,
    });

    pairToken = String(localState[PAIR_TOKEN_KEY] ?? "").trim();
    serverUrl = String(localState[SERVER_URL_KEY] ?? DEFAULT_SERVER_URL).trim() || DEFAULT_SERVER_URL;
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
