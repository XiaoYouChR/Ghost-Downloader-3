from collections.abc import Callable

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
        self._socket.readyRead.connect(self._onReadyRead)

    def connect(self, gui: Callable[[Event], None]) -> None:
        self._gui = gui

    def connectToServer(self) -> None:
        self._socket.connectToServer(self._name)

    def toEngine(self, command: Command) -> None:
        self._socket.write(frame(command.toBytes()))

    def _onReadyRead(self) -> None:
        for raw in self._unframer.feed(bytes(self._socket.readAll())):
            self._gui(Event.fromBytes(raw))
