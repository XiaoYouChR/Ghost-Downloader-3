from secrets import token_urlsafe

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtNetwork import QHostAddress
from PySide6.QtWebSockets import QWebSocketServer
from orjson import dumps, loads

# 浏览器扩展桥（gui 端，像剪贴板/托盘那样是本机存在）：跑本地 WebSocket，把扩展发来的下载意图转成 backend 命令。
# 协议沿用旧 BrowserService（hello 握手 + 配对令牌 + create_task），但不再耦 coreService/taskService/QtWidgets——只认 backend。
# 端口/版本对齐旧实现，扩展无需改。真实扩展握手需真浏览器验；dispatch 逻辑可单测（喂假 session）。
SERVER_PORT = 14370
PROTOCOL_VERSION = 1


def pairToken() -> str:
    # 配对令牌：cfg 里有就用、没有就生成并存住（扩展记住它、下次握手要对上）。main() 调，喂给 BrowserService。
    from app.supports.config import cfg
    if not cfg.browserExtensionPairToken.value:
        cfg.set(cfg.browserExtensionPairToken, token_urlsafe(16))
    return str(cfg.browserExtensionPairToken.value)


class _Session:
    def __init__(self, socket) -> None:
        self.socket = socket
        self.authenticated = False

    def send(self, payload: dict) -> None:
        self.socket.sendTextMessage(dumps(payload).decode("utf-8"))


class BrowserService(QObject):
    # 配对请求 → QML 弹框问用户；用户答 approvePair/rejectPair。参数是给用户看的来源信息。
    pairRequested = Signal("QVariant")

    def __init__(self, backend, token: str, parent=None) -> None:
        super().__init__(parent)
        self._backend = backend
        self._token = token  # 配对令牌由 main() 从 cfg 取/生成传入——服务本身不碰 cfg，可单测
        self._sessions: dict[int, _Session] = {}
        self._pendingPair: tuple[_Session, str] | None = None  # (session, requestId) 等用户答配对
        self._server = QWebSocketServer("Ghost Downloader Browser Socket", QWebSocketServer.SslMode.NonSecureMode, self)
        self._server.newConnection.connect(self._onNewConnection)

    @Slot(bool)
    def setEnabled(self, enabled: bool) -> None:
        if enabled and not self._server.isListening():
            self._server.listen(QHostAddress.SpecialAddress.LocalHost, SERVER_PORT)
        elif not enabled and self._server.isListening():
            for session in list(self._sessions.values()):
                session.socket.close()
            self._sessions.clear()
            self._server.close()

    @Slot()
    def _onNewConnection(self) -> None:
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        session = _Session(socket)
        self._sessions[id(socket)] = session
        socket.textMessageReceived.connect(self._onMessage)
        socket.disconnected.connect(self._onDisconnected)

    @Slot(str)
    def _onMessage(self, message: str) -> None:
        session = self._sessions.get(id(self.sender()))
        if session is None:
            return
        try:
            data = loads(message)
        except Exception:
            return
        if isinstance(data, dict):
            self.dispatch(session, data)

    @Slot()
    def _onDisconnected(self) -> None:
        self._sessions.pop(id(self.sender()), None)

    def dispatch(self, session: _Session, data: dict) -> None:
        kind = data.get("type")
        if kind == "pair_request":
            self._onPairRequest(session, data)
        elif kind == "hello":
            self._onHello(session, data)
        elif not session.authenticated:
            session.send({"type": "error", "code": "unauthorized", "message": "请先完成握手认证"})
        elif kind == "create_task":
            self._onCreateTask(session, data)

    def _onHello(self, session: _Session, data: dict) -> None:
        if data.get("token") != self._token:
            session.send({"type": "error", "code": "unauthorized", "message": "配对令牌无效"})
            return
        session.authenticated = True
        session.send({"type": "hello_ack", "protocolVersion": PROTOCOL_VERSION})

    def _onPairRequest(self, session: _Session, data: dict) -> None:
        # 异步配对：记下待答的 session，弹框问用户，答完走 approvePair/rejectPair
        self._pendingPair = (session, data.get("requestId", ""))
        self.pairRequested.emit({
            "extensionVersion": data.get("extensionVersion", "未知"),
            "clientKind": data.get("clientKind", "浏览器扩展"),
        })

    @Slot()
    def approvePair(self) -> None:
        if self._pendingPair is None:
            return
        session, requestId = self._pendingPair
        self._pendingPair = None
        session.send({"type": "pair_result", "requestId": requestId, "ok": True, "token": self._token})

    @Slot()
    def rejectPair(self) -> None:
        if self._pendingPair is None:
            return
        session, requestId = self._pendingPair
        self._pendingPair = None
        session.send({"type": "pair_result", "requestId": requestId, "ok": False, "message": "已拒绝配对请求"})

    def _onCreateTask(self, session: _Session, data: dict) -> None:
        requestId = data.get("requestId", "")
        payload = data.get("payload")
        url = payload.get("url") if isinstance(payload, dict) else None
        if not url:
            session.send({"type": "create_task_result", "requestId": requestId, "ok": False, "message": "缺少下载链接"})
            return
        options = {}
        if payload.get("headers"):
            options["headers"] = payload["headers"]
        if payload.get("path"):
            options["path"] = payload["path"]
        self._backend.addTaskWithOptions(url, options)
        session.send({"type": "create_task_result", "requestId": requestId, "ok": True})
