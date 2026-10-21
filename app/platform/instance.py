from __future__ import annotations

import getpass
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QSharedMemory
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from app.config.constants import DESKTOP_ID, DESKTOP_OBJECT_PATH
from app.config.paths import EXECUTABLE_PATH
from app.platform.url_scheme import isWakeUri

if TYPE_CHECKING:
    from app.platform.application import Application

USER_ID = getpass.getuser() if sys.platform == "win32" else str(os.getuid())
INSTANCE_NAME = f"GhostDownloader-{USER_ID}"


@dataclass(frozen=True)
class Reply:
    output: str
    exitCode: int


@dataclass(frozen=True)
class Invocation:
    argv: list[str]
    cwd: str
    reply: Callable[[Reply], None] = lambda _: None


UNAVAILABLE = Reply(json.dumps({"error": {"code": "instanceUnavailable",
                                          "message": "Ghost Downloader did not reply. Check GhostDownloader.log."}}), 1)


def toLine(reply: Reply) -> bytes:
    return json.dumps({"output": reply.output, "exitCode": reply.exitCode}).encode() + b"\n"


def parseReply(data: bytes) -> Reply | None:
    try:
        reply = json.loads(data)
        return Reply(reply["output"], reply["exitCode"])
    except (ValueError, KeyError, TypeError):
        return None


def toTerminal(output: str) -> str:
    try:
        return json.dumps(json.loads(output), indent=2, ensure_ascii=False)
    except ValueError:
        return output


def fetchReply(argv: list[str], cwd: str) -> Reply | None:
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_NAME)
    if not socket.waitForConnected(1000):
        return None
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.AllowSetForegroundWindow(-1)
    socket.write(json.dumps({"argv": argv, "cwd": cwd}).encode() + b"\n")
    socket.waitForBytesWritten(1000)
    data = b""
    while socket.waitForReadyRead(-1):
        data += socket.readAll().data()
    return parseReply(data + socket.readAll().data())


def create() -> subprocess.Popen:
    program = [str(EXECUTABLE_PATH)] if "__compiled__" in globals() else [sys.executable, str(Path(sys.argv[0]).resolve())]
    detach = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS}
              if sys.platform == "win32" else {"start_new_session": True})
    return subprocess.Popen([*program, "--silence"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, **detach)


def request(argv: list[str], cwd: str) -> int | None:
    invocation = ["ghd", *argv[1:]] if Path(argv[0]).stem == "ghd" else argv[1:]
    reply = fetchReply(invocation, cwd)
    if reply is None and invocation[:1] == ["ghd"]:
        process = create()
        for _ in range(1500):
            time.sleep(0.02)
            if reply := fetchReply(invocation, cwd):
                break
            if process.poll() is not None:
                reply = fetchReply(invocation, cwd) or UNAVAILABLE
                break
        else:
            reply = UNAVAILABLE
    if reply is None:
        return None
    if reply.output:
        print(toTerminal(reply.output) if sys.stdout.isatty() else reply.output)
    return reply.exitCode


def open(application: Application, argv: list[str], cwd: str) -> PrimaryInstance | None:
    memory = QSharedMemory(INSTANCE_NAME)
    # 锁先于监听建立、晚于监听释放，这两段间隙里连不上，只能重试
    for _ in range(50):
        if memory.create(1):
            return PrimaryInstance(memory, application, Invocation(argv[1:], cwd))
        if fetchReply(argv[1:], cwd) is not None:
            return None
        time.sleep(0.02)
    from loguru import logger
    logger.error("Another instance holds the lock but does not answer: {}", memory.errorString())
    return None


class PrimaryInstance(QObject):
    def __init__(self, memory: QSharedMemory, application: Application, invocation: Invocation) -> None:
        super().__init__(application)
        self._memory = memory
        self._run: Callable[[Invocation], None] | None = None
        self._pending = [invocation] if invocation.argv or sys.platform != "darwin" else []
        self._isWakeLaunch = False
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not self._server.listen(INSTANCE_NAME):
            QLocalServer.removeServer(INSTANCE_NAME)
            if not self._server.listen(INSTANCE_NAME):
                from loguru import logger
                logger.error("Failed to listen on {}: {}", INSTANCE_NAME, self._server.errorString())
        self._server.newConnection.connect(self._onConnected)
        application.openRequested.connect(self._onOpenRequested)
        application.activated.connect(self._onActivated)
        if sys.platform == "linux":
            from PySide6.QtDBus import QDBusConnection
            bus = QDBusConnection.sessionBus()
            bus.registerObject(DESKTOP_OBJECT_PATH, DesktopBusReceiver(self._receive, self),
                               QDBusConnection.RegisterOption.ExportAllSlots)
            bus.registerService(DESKTOP_ID)

    def start(self, run: Callable[[Invocation], None]) -> None:
        self._run = run
        for invocation in self._pending:
            run(invocation)
        self._pending.clear()

    def close(self) -> None:
        self._server.close()
        self._memory.detach()

    def _receive(self, invocation: Invocation) -> None:
        if self._run is None:
            self._pending.append(invocation)
        else:
            self._run(invocation)

    def _onConnected(self) -> None:
        socket = self._server.nextPendingConnection()

        def onReadyRead() -> None:
            if not socket.canReadLine():
                return
            socket.readyRead.disconnect(onReadyRead)
            try:
                request = json.loads(socket.readLine().data())
                invocation = Invocation(request["argv"], request["cwd"], onReplied)
            except (ValueError, KeyError, TypeError):
                socket.disconnectFromServer()
                socket.deleteLater()
                return
            self._receive(invocation)

        def onReplied(reply: Reply) -> None:
            if socket.state() != QLocalSocket.LocalSocketState.ConnectedState:
                socket.deleteLater()
                return
            socket.disconnected.connect(socket.deleteLater)
            socket.write(toLine(reply))
            socket.disconnectFromServer()

        socket.readyRead.connect(onReadyRead)
        onReadyRead()

    def _onOpenRequested(self, uri: str) -> None:
        if isWakeUri(uri):
            self._isWakeLaunch = True
        if uri:
            self._receive(Invocation([uri], os.getcwd()))

    def _onActivated(self) -> None:
        if self._run is None or self._isWakeLaunch or sys.platform != "darwin":
            return
        self._run(Invocation([], os.getcwd()))


if sys.platform == "linux":
    from PySide6.QtCore import ClassInfo, Slot

    @ClassInfo({"D-Bus Interface": "org.freedesktop.Application"})
    class DesktopBusReceiver(QObject):
        def __init__(self, receive: Callable[[Invocation], None], parent) -> None:
            super().__init__(parent)
            self._receive = receive

        @Slot("QStringList", "QVariantMap")
        def Open(self, uris, platformData):
            if uris := [uri for uri in uris if uri]:
                self._receive(Invocation(uris, os.getcwd()))

        @Slot("QVariantMap")
        def Activate(self, platformData):
            self._receive(Invocation([], os.getcwd()))
