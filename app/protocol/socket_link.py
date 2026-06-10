from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from app.protocol.framing import Unframer, frame
from app.protocol.message import Command, Event


class SocketServer:
    """engine 侧的连线：监听本地 socket，收 Command 交给 engine，发 Event 给已连的 gui。
    与 MemoryLink 同样暴露 toGui，让 Engine 无感；换 transport 只换它，不动 Engine。"""

    def __init__(self, name: str) -> None:
        self._name = name
        self._server = QLocalServer()
        self._socket: QLocalSocket | None = None
        self._unframer = Unframer()
        self._engine: Callable[[Command], None] | None = None
        self._server.newConnection.connect(self._onNewConnection)

    def connect(self, engine: Callable[[Command], None]) -> None:
        self._engine = engine

    def listen(self) -> None:
        QLocalServer.removeServer(self._name)  # 清掉残留 socket 文件/管道
        self._server.listen(self._name)

    def toGui(self, event: Event) -> None:
        if self._socket is not None:
            self._socket.write(frame(event.toBytes()))

    def _onNewConnection(self) -> None:
        self._socket = self._server.nextPendingConnection()
        self._socket.readyRead.connect(self._onReadyRead)

    def _onReadyRead(self) -> None:
        for raw in self._unframer.feed(bytes(self._socket.readAll())):
            self._engine(Command.fromBytes(raw))


class SocketClient:
    """gui 侧的连线：连本地 socket，发 Command，收 Event 交给 backend。"""

    def __init__(self, name: str) -> None:
        self._name = name
        self._socket = QLocalSocket()
        self._unframer = Unframer()
        self._gui: Callable[[Event], None] | None = None
        self._retries = 0
        self._pending = False
        self._socket.readyRead.connect(self._onReadyRead)
        self._socket.errorOccurred.connect(self._onError)
        self._socket.connected.connect(self._onConnected)
        self._socket.disconnected.connect(self._onDisconnected)

    def connect(self, gui: Callable[[Event], None]) -> None:
        self._gui = gui

    def whenConnected(self, callback: Callable[[], None]) -> None:
        self._socket.connected.connect(callback)

    def whenDisconnected(self, callback: Callable[[], None]) -> None:
        self._socket.disconnected.connect(callback)

    def connectToServer(self) -> None:
        self._socket.connectToServer(self._name)

    def _onConnected(self) -> None:
        self._retries = 0
        self._pending = False

    def _onDisconnected(self) -> None:
        # daemon 断了（崩或退）：重连给足新预算，自己连回来；界面回到“连接中”由 whenDisconnected 接管
        self._retries = 0
        self._reconnectSoon()

    def _onError(self, _error) -> None:
        # daemon 可能还在启动（加载 pack 要几秒），稍后重连，直到连上或放弃
        self._reconnectSoon()

    def _reconnectSoon(self) -> None:
        if self._pending or self._socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
            return  # 已连上或正在连，别叠重连
        if self._retries >= 30:
            return
        self._retries += 1
        self._pending = True
        QTimer.singleShot(300, self._reconnect)

    def _reconnect(self) -> None:
        self._pending = False
        self.connectToServer()

    def toEngine(self, command: Command) -> None:
        self._socket.write(frame(command.toBytes()))

    def _onReadyRead(self) -> None:
        for raw in self._unframer.feed(bytes(self._socket.readAll())):
            self._gui(Event.fromBytes(raw))
