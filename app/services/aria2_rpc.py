from __future__ import annotations

import asyncio
import json
import socket
from functools import partial
from pathlib import Path
from secrets import token_hex
from typing import TYPE_CHECKING, Any

from app.signal import Signal
from loguru import logger

from app.config.cfg import cfg
from app.config.constants import VERSION

if TYPE_CHECKING:
    from app.models.task import Task

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601


class Aria2RpcServer:
    taskDraftRequested = Signal(list)

    def __init__(self, coroutineRunner, parse, addTask) -> None:
        self._coroutineRunner = coroutineRunner
        self._parse = parse
        self._addTask = addTask
        self._serveWorkId: str | None = None

    @property
    def isRunning(self) -> bool:
        return self._serveWorkId is not None

    def start(self) -> None:
        if self._serveWorkId is not None:
            return
        port = cfg.aria2RpcPort.value
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(('127.0.0.1', port))
            sock.listen()
        except OSError as e:
            logger.error("Aria2 RPC compat server failed to start on port {}: {}", port, e)
            sock.close()
            return
        sock.setblocking(False)
        self._serveWorkId = self._coroutineRunner.submit(
            self._run(sock), failed=self._onServeFailed)
        logger.info("Aria2 RPC compat server started on port {}", port)

    def stop(self) -> None:
        if self._serveWorkId is None:
            return
        self._coroutineRunner.cancel(self._serveWorkId)
        self._serveWorkId = None

    def _onServeFailed(self, error) -> None:
        self._serveWorkId = None
        logger.error("Aria2 RPC compat server crashed: {}", error)

    def setEnabled(self, enabled: bool) -> None:
        if enabled:
            self.start()
        else:
            self.stop()

    async def _run(self, sock: socket.socket) -> None:
        try:
            server = await asyncio.start_server(self._onConnection, sock=sock)
        except Exception:
            sock.close()
            raise
        async with server:
            await server.serve_forever()

    async def _onConnection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            header = await reader.readuntil(b"\r\n\r\n")
            contentLength = 0
            for line in header.split(b"\r\n"):
                if line.lower().startswith(b"content-length:"):
                    contentLength = int(line.split(b":", 1)[1].strip())
                    break
            body = await reader.readexactly(contentLength)
            response = self._dispatchRpc(body)
            payload = json.dumps(response, ensure_ascii=False).encode("utf-8")
            httpHeader = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(payload)}\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            ).encode("utf-8")
            writer.write(httpHeader + payload)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ValueError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    def _dispatchRpc(self, body: bytes) -> dict:
        try:
            data = json.loads(body)
        except Exception:
            return {"jsonrpc": "2.0", "id": None, "error": {"code": JSONRPC_PARSE_ERROR, "message": "Parse error"}}

        if not isinstance(data, dict):
            return {"jsonrpc": "2.0", "id": None, "error": {"code": JSONRPC_INVALID_REQUEST, "message": "Invalid Request"}}

        rpcId = data.get("id")
        method = data.get("method", "")
        params = data.get("params", [])

        if not isinstance(params, list):
            return {"jsonrpc": "2.0", "id": rpcId, "error": {"code": JSONRPC_INVALID_REQUEST, "message": "params must be array"}}

        token = cfg.aria2RpcToken.value
        if token:
            if params and isinstance(params[0], str) and params[0].startswith("token:"):
                if params[0] != f"token:{token}":
                    return {"jsonrpc": "2.0", "id": rpcId, "error": {"code": 1, "message": "Unauthorized"}}
                params = params[1:]
            else:
                return {"jsonrpc": "2.0", "id": rpcId, "error": {"code": 1, "message": "Unauthorized"}}
        elif params and isinstance(params[0], str) and params[0].startswith("token:"):
            params = params[1:]

        if method == "aria2.addUri":
            return self._addUri(rpcId, params)
        elif method == "aria2.getVersion":
            return {"jsonrpc": "2.0", "id": rpcId, "result": {"version": VERSION, "enabledFeatures": ["HTTPS"]}}
        else:
            return {"jsonrpc": "2.0", "id": rpcId, "error": {"code": JSONRPC_METHOD_NOT_FOUND, "message": "Method not found"}}

    def _addUri(self, rpcId: Any, params: list) -> dict:
        uris = params[0] if params and isinstance(params[0], list) else []
        options = params[1] if len(params) > 1 and isinstance(params[1], dict) else {}

        if not uris:
            return {"jsonrpc": "2.0", "id": rpcId, "error": {"code": 1, "message": "No URI provided"}}

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

        ua = options.get("user-agent", "")
        if isinstance(ua, str) and ua:
            headers.setdefault("User-Agent", ua)
        referer = options.get("referer", "")
        if isinstance(referer, str) and referer:
            headers.setdefault("Referer", referer)

        gid = token_hex(8)

        from app.models.task import TaskOptions

        outputFolder = Path(directory) if directory else Path(cfg.downloadFolder.value)
        clientProfile = "" if cfg.aria2RpcEmulateFingerprint.value else "raw"
        taskOptions = TaskOptions(
            url=url,
            headers=headers,
            outputFolder=outputFolder,
            clientProfile=clientProfile,
        )
        self._coroutineRunner.submit(
            self._parse(taskOptions),
            done=partial(self._onTaskParsed, filename=filename),
            failed=self._onTaskParseFailed,
        )

        return {"jsonrpc": "2.0", "id": rpcId, "result": gid}

    def _onTaskParsed(self, task: Task, filename: str = "") -> None:
        if filename:
            task.setName(filename)

        if cfg.shouldDraftTakenDownload.value:
            self.taskDraftRequested.emit([task])
            return

        self._addTask(task)

    def _onTaskParseFailed(self, error: str) -> None:
        logger.warning("Aria2 RPC task parse failed: {}", error)
