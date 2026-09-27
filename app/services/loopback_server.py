from __future__ import annotations

import asyncio
import errno
import socket
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from loguru import logger

from app.signal import Signal

Handle = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]


class ListenStatus(StrEnum):
    OFF = "off"
    STARTING = "starting"
    LISTENING = "listening"
    FAILED = "failed"


class ListenFailure(StrEnum):
    OCCUPIED = "occupied"
    DENIED = "denied"
    OTHER = "other"


@dataclass(frozen=True)
class ListenState:
    status: ListenStatus = ListenStatus.OFF
    port: int = 0
    failure: ListenFailure | None = None


def toListenFailure(error: OSError) -> ListenFailure:
    if error.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", None)):
        return ListenFailure.OCCUPIED
    if error.errno in (errno.EACCES, getattr(errno, "WSAEACCES", None)):
        return ListenFailure.DENIED
    return ListenFailure.OTHER


def createSocket(host: str, port: int) -> socket.socket:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        # Windows 的 SO_REUSEADDR 允许抢占正在监听的端口，那样端口冲突就检测不到了
        if sys.platform != "win32":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if family == socket.AF_INET6:
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        sock.bind((host, port))
        sock.listen()
        sock.setblocking(False)
    except OSError:
        sock.close()
        raise
    return sock


class LoopbackServer:
    """按 isEnabled/port 配置在 127.0.0.1 与 ::1 上监听，拥有全部连接。

    公开方法只在 dispatcher 线程调用；socket 只在 loop 线程上按提交顺序打开和关闭。
    """

    stateChanged = Signal(object)

    def __init__(self, coroutineRunner, handle: Handle, *, isEnabled, port) -> None:
        self._coroutineRunner = coroutineRunner
        self._handle = handle
        self._isEnabled = isEnabled
        self._port = port
        self._state = ListenState()
        self._servers: list[asyncio.Server] = []
        self._connections: set[asyncio.Task] = set()
        self._lock: asyncio.Lock | None = None

    @property
    def state(self) -> ListenState:
        return self._state

    def start(self) -> None:
        self._isEnabled.valueChanged.connect(self._onConfigChanged)
        self._port.valueChanged.connect(self._onConfigChanged)
        self._onConfigChanged()

    def stop(self) -> None:
        self._isEnabled.valueChanged.disconnect(self._onConfigChanged)
        self._port.valueChanged.disconnect(self._onConfigChanged)
        self._request(None)

    def _onConfigChanged(self, *_) -> None:
        self._request(self._port.value if self._isEnabled.value else None)

    def _request(self, port: int | None) -> None:
        if port is not None:
            self._setState(ListenState(ListenStatus.STARTING, port))
        self._coroutineRunner.submit(self._run(port), done=self._setState)

    def _setState(self, state: ListenState) -> None:
        if state == self._state:
            return
        self._state = state
        self.stateChanged.emit(state)

    async def _run(self, port: int | None) -> ListenState:
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            await self._close()
            if port is None:
                return ListenState()
            return await self._open(port)

    async def _open(self, port: int) -> ListenState:
        try:
            sockets = [createSocket("127.0.0.1", port)]
        except OSError as e:
            logger.error("Loopback server failed to bind 127.0.0.1:{}: {}", port, e)
            return ListenState(ListenStatus.FAILED, port, failure=toListenFailure(e))
        try:
            sockets.append(createSocket("::1", port))
        except OSError as e:
            logger.warning("IPv6 loopback server failed to bind [::1]:{}: {}", port, e)

        for sock in sockets:
            self._servers.append(await asyncio.start_server(self._onConnection, sock=sock))
        return ListenState(ListenStatus.LISTENING, port)

    async def _close(self) -> None:
        servers, self._servers = self._servers, []
        for server in servers:
            server.close()
        connections = list(self._connections)
        for task in connections:
            task.cancel()
        await asyncio.gather(*connections, return_exceptions=True)
        for server in servers:
            await server.wait_closed()

    async def _onConnection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        self._connections.add(task)
        try:
            await self._handle(reader, writer)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.opt(exception=e).warning("Loopback connection failed")
        finally:
            self._connections.discard(task)
            writer.close()
