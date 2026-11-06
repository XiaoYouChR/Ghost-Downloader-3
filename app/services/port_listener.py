from __future__ import annotations

import asyncio
import errno
import socket
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from loguru import logger

from app.config.cfg import cfg
from app.models.task import TaskError
from app.signal import Signal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config.cfg import ConfigItem, RangeConfigItem
    from app.services.coroutine_runner import CoroutineRunner

Handle = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]

CONFLICT_ERRNOS = {
    errno.EADDRINUSE,
    errno.EACCES,
    getattr(errno, "WSAEADDRINUSE", None),
    getattr(errno, "WSAEACCES", None),
}


class ListenStatus(StrEnum):
    OFF = "off"
    STARTING = "starting"
    LISTENING = "listening"
    FAILED = "failed"


@dataclass(frozen=True)
class ListenState:
    status: ListenStatus = ListenStatus.OFF
    port: int = 0
    error: TaskError | None = None


def toListenError(error: OSError, port: int) -> TaskError:
    if error.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", None)):
        return TaskError("端口 {port} 被占用，请更换端口", port=port)
    if error.errno in (errno.EACCES, getattr(errno, "WSAEACCES", None)):
        return TaskError("没有权限监听端口 {port}，请更换端口", port=port)
    return TaskError("无法监听端口 {port}，详情见日志", port=port)


def createSocket(host: str, port: int) -> socket.socket:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        if sys.platform == "win32":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
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


class PortListener:
    stateChanged = Signal(object)

    def __init__(
        self,
        coroutineRunner: CoroutineRunner,
        handle: Handle,
        *,
        isEnabled: ConfigItem[bool],
        port: RangeConfigItem,
        shouldAutoSelect: ConfigItem[bool] | None = None,
        fallbackPorts: tuple[int, ...] = (),
    ) -> None:
        self._coroutineRunner = coroutineRunner
        self._handle = handle
        self._isEnabled = isEnabled
        self._port = port
        self._shouldAutoSelect = shouldAutoSelect
        self._fallbackPorts = fallbackPorts
        self._state = ListenState()
        self._servers: list[asyncio.Server] = []
        self._connections: set[asyncio.Task] = set()
        self._lock: asyncio.Lock | None = None

    @property
    def state(self) -> ListenState:
        return self._state

    def start(self) -> None:
        self._isEnabled.valueChanged.connect(self._onConfigChanged)
        self._port.valueChanged.connect(self._onPortChanged)
        if self._shouldAutoSelect is not None:
            self._shouldAutoSelect.valueChanged.connect(self._onAutoSelectChanged)
        self._onConfigChanged()

    def stop(self) -> None:
        self._isEnabled.valueChanged.disconnect(self._onConfigChanged)
        self._port.valueChanged.disconnect(self._onPortChanged)
        if self._shouldAutoSelect is not None:
            self._shouldAutoSelect.valueChanged.disconnect(self._onAutoSelectChanged)
        self._request(None)

    def _onPortChanged(self, port: int) -> None:
        if self._isEnabled.value and self._state == ListenState(ListenStatus.LISTENING, port):
            return
        self._onConfigChanged()

    def _onAutoSelectChanged(self, isAuto: bool) -> None:
        if not self._isEnabled.value:
            return
        if self._state == ListenState(ListenStatus.LISTENING, self._port.value):
            return
        self._onConfigChanged()

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
        if (state.status == ListenStatus.LISTENING
                and self._isEnabled.value
                and self._shouldAutoSelect is not None
                and self._shouldAutoSelect.value
                and self._port.value != state.port):
            cfg.set(self._port, state.port)
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
        if self._shouldAutoSelect is not None and self._shouldAutoSelect.value and self._fallbackPorts:
            candidates = (port, *(p for p in self._fallbackPorts if p != port))
        else:
            candidates = (port,)
        sockets: list[socket.socket] = []
        boundPort = port
        for index, candidate in enumerate(candidates):
            try:
                sockets = [createSocket("127.0.0.1", candidate)]
                boundPort = candidate
                break
            except OSError as e:
                if index + 1 < len(candidates) and e.errno in CONFLICT_ERRNOS:
                    logger.info("Port 127.0.0.1:{} unavailable ({}), trying next fallback port", candidate, e)
                    continue
                logger.error("Port listener failed to bind 127.0.0.1:{}: {}", port, e)
                return ListenState(ListenStatus.FAILED, port, error=toListenError(e, port))
        try:
            sockets.append(createSocket("::1", boundPort))
        except OSError as e:
            logger.warning("Port listener failed to bind [::1]:{}: {}", boundPort, e)

        for sock in sockets:
            self._servers.append(await asyncio.start_server(self._onConnection, sock=sock))
        return ListenState(ListenStatus.LISTENING, boundPort)

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
        if not self._servers:
            writer.close()
            return
        task = asyncio.current_task()
        self._connections.add(task)
        try:
            await self._handle(reader, writer)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.opt(exception=e).warning("Port listener connection failed")
        finally:
            self._connections.discard(task)
            writer.close()
