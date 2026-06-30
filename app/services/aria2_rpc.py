from __future__ import annotations

import json
from pathlib import Path
from secrets import token_hex
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtNetwork import QHostAddress, QTcpServer, QTcpSocket
from loguru import logger

from app.config.cfg import cfg
from app.config.constants import VERSION

if TYPE_CHECKING:
    from app.models.task import Task

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601


class Aria2RpcServer(QObject):
    taskDraftRequested = Signal(list)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._server = QTcpServer(self)
        self._buffers: dict[int, bytes] = {}

        self._server.newConnection.connect(self._onNewConnection)

    def start(self) -> None:
        if self._server.isListening():
            return
        port = cfg.aria2RpcPort.value
        if self._server.listen(QHostAddress.SpecialAddress.LocalHost, port):
            logger.info("Aria2 RPC compat server started on port {}", port)
        else:
            logger.error("Aria2 RPC compat server failed to start: {}", self._server.errorString())

    def stop(self) -> None:
        if not self._server.isListening():
            return
        for child in self.findChildren(QTcpSocket):
            child.disconnectFromHost()
        self._server.close()
        self._buffers.clear()

    def setEnabled(self, enabled: bool) -> None:
        if enabled:
            self.start()
        else:
            self.stop()

    def setPort(self, _port: int) -> None:
        if not self._server.isListening():
            return
        self.stop()
        self.start()

    @Slot()
    def _onNewConnection(self) -> None:
        while True:
            socket = self._server.nextPendingConnection()
            if socket is None:
                break
            socket.setParent(self)
            socket.readyRead.connect(self._onReadyRead)
            socket.disconnected.connect(self._onDisconnected)

    @Slot()
    def _onReadyRead(self) -> None:
        socket: QTcpSocket = self.sender()
        if socket is None:
            return

        key = id(socket)
        self._buffers[key] = self._buffers.get(key, b"") + socket.readAll().data()

        buf = self._buffers[key]
        headerEnd = buf.find(b"\r\n\r\n")
        if headerEnd < 0:
            return

        bodyStart = headerEnd + 4
        contentLength = 0
        for line in buf[:headerEnd].split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                contentLength = int(line.split(b":", 1)[1].strip())
                break

        body = buf[bodyStart:]
        if len(body) < contentLength:
            return

        del self._buffers[key]
        self._dispatchRpc(socket, body[:contentLength])

    @Slot()
    def _onDisconnected(self) -> None:
        socket: QTcpSocket = self.sender()
        if socket is None:
            return
        self._buffers.pop(id(socket), None)
        socket.deleteLater()

    def _dispatchRpc(self, socket: QTcpSocket, body: bytes) -> None:
        try:
            data = json.loads(body)
        except Exception:
            self._respondError(socket, None, JSONRPC_PARSE_ERROR, "Parse error")
            return

        if not isinstance(data, dict):
            self._respondError(socket, None, JSONRPC_INVALID_REQUEST, "Invalid Request")
            return

        rpcId = data.get("id")
        method = data.get("method", "")
        params = data.get("params", [])

        if not isinstance(params, list):
            self._respondError(socket, rpcId, JSONRPC_INVALID_REQUEST, "params must be array")
            return

        token = cfg.aria2RpcToken.value
        if token:
            if params and isinstance(params[0], str) and params[0].startswith("token:"):
                if params[0] != f"token:{token}":
                    self._respondError(socket, rpcId, 1, "Unauthorized")
                    return
                params = params[1:]
            else:
                self._respondError(socket, rpcId, 1, "Unauthorized")
                return
        elif params and isinstance(params[0], str) and params[0].startswith("token:"):
            params = params[1:]

        if method == "aria2.addUri":
            self._addUri(socket, rpcId, params)
        elif method == "aria2.getVersion":
            self._respond(socket, rpcId, {"version": VERSION, "enabledFeatures": ["HTTPS"]})
        else:
            self._respondError(socket, rpcId, JSONRPC_METHOD_NOT_FOUND, "Method not found")

    def _addUri(self, socket: QTcpSocket, rpcId: Any, params: list) -> None:
        uris = params[0] if params and isinstance(params[0], list) else []
        options = params[1] if len(params) > 1 and isinstance(params[1], dict) else {}

        if not uris:
            self._respondError(socket, rpcId, 1, "No URI provided")
            return

        url = uris[0]
        filename = options.get("out", "")
        directory = options.get("dir", "")
        rawHeaders = options.get("header", [])

        headers: dict[str, str] = {}
        if isinstance(rawHeaders, str):
            rawHeaders = [rawHeaders]
        if isinstance(rawHeaders, list):
            for h in rawHeaders:
                if isinstance(h, str) and ":" in h:
                    k, v = h.split(":", 1)
                    headers[k.strip()] = v.strip()

        gid = token_hex(8)
        self._respond(socket, rpcId, gid)

        from app.models.task import TaskOptions
        from app.services.coroutine_runner import coroutineRunner
        from app.services.feature_service import featureService

        outputFolder = Path(directory) if directory else Path(cfg.downloadFolder.value)
        taskOptions = TaskOptions(
            url=url,
            headers=headers,
            outputFolder=outputFolder,
        )
        coroutineRunner.submit(
            featureService.parse(taskOptions),
            done=self._onTaskParsed,
            failed=self._onTaskParseFailed,
            filename=filename,
        )

    def _onTaskParsed(self, task: Task, filename: str = "") -> None:
        from app.services.task_service import taskService

        if filename:
            task.setName(filename)

        if cfg.shouldRaiseWindowOnBrowserTask.value:
            self.taskDraftRequested.emit([task])
            return

        taskService.add(task)

    def _onTaskParseFailed(self, error: str) -> None:
        logger.warning("Aria2 RPC task parse failed: {}", error)

    def _respond(self, socket: QTcpSocket, rpcId: Any, result: Any) -> None:
        self._sendJson(socket, {"jsonrpc": "2.0", "id": rpcId, "result": result})

    def _respondError(self, socket: QTcpSocket, rpcId: Any, code: int, message: str) -> None:
        self._sendJson(socket, {"jsonrpc": "2.0", "id": rpcId, "error": {"code": code, "message": message}})

    def _sendJson(self, socket: QTcpSocket, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode("utf-8")
        socket.write(header + body)
        socket.flush()
        socket.disconnectFromHost()


aria2RpcServer = Aria2RpcServer()
