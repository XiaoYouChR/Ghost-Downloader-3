from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from secrets import token_hex
from typing import TYPE_CHECKING, Any

from loguru import logger

from app.config.cfg import cfg
from app.config.constants import VERSION
from app.models.task import TaskOptions
from app.services.websocket_stream import WebSocketStream, readHead
from app.signal import Signal

if TYPE_CHECKING:
    from app.models.task import Task

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_INVALID_PARAMS = -32602
ARIA2_ERROR = 1
MAX_REQUEST_SIZE = 2 * 1024 * 1024
UNAUTHORIZED_DELAY = 1


class RpcError(Exception):
    pass


@dataclass(frozen=True)
class HttpRequest:
    method: str
    path: str
    headers: dict[str, str]


def parseHead(head: bytes) -> HttpRequest | None:
    lines = head.decode("latin-1").split("\r\n")
    parts = lines[0].split(" ")
    if len(parts) != 3:
        return None
    headers = {}
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if sep:
            headers[name.strip().lower()] = value.strip()
    return HttpRequest(parts[0], parts[1].split("?")[0].split("#")[0], headers)


def buildHttpResponse(status: int, body: bytes = b"", headers: dict[str, str] | None = None) -> bytes:
    lines = [
        f"HTTP/1.1 {status} {HTTPStatus(status).phrase}",
        "Access-Control-Allow-Origin: *",
        f"Content-Length: {len(body)}",
        "Connection: close",
        *(f"{name}: {value}" for name, value in (headers or {}).items()),
    ]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body


def buildPreflightHeaders(request: HttpRequest) -> dict[str, str]:
    if "origin" not in request.headers or "access-control-request-method" not in request.headers:
        return {}
    return {
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": request.headers.get("access-control-request-headers", ""),
        "Access-Control-Max-Age": "1728000",
    }


def buildError(rpcId: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rpcId, "error": {"code": code, "message": message}}


def toHttpStatus(response: dict) -> int:
    if "error" not in response:
        return 200
    return 400 if response["error"]["code"] in (ARIA2_ERROR, JSONRPC_INVALID_REQUEST) else 500


def toText(options: dict, key: str) -> str:
    value = options.get(key)
    return value if isinstance(value, str) else ""


def toHeaders(options: dict) -> dict[str, str]:
    raw = options.get("header")
    lines = [raw] if isinstance(raw, str) else [h for h in raw if isinstance(h, str)] if isinstance(raw, list) else []
    headers: dict[str, str] = {}
    for line in lines:
        name, sep, value = line.partition(":")
        if sep:
            headers[name.strip()] = value.strip()

    names = {name.lower() for name in headers}
    if (userAgent := toText(options, "user-agent")) and "user-agent" not in names:
        headers["User-Agent"] = userAgent
    if (referer := toText(options, "referer")) and "referer" not in names:
        headers["Referer"] = referer
    return headers


class Aria2RpcService:
    """aria2 JSON-RPC 的最小兼容：getVersion 与 addUri，HTTP POST 与 WebSocket 共用 /jsonrpc。

    handle 在 loop 线程运行；解析完成的 Task 在 dispatcher 线程交给 addTask，或经 taskDraftRequested 进草稿。
    """

    taskDraftRequested = Signal(list)

    def __init__(self, coroutineRunner, parse, addTask) -> None:
        self._coroutineRunner = coroutineRunner
        self._parse = parse
        self._addTask = addTask

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await readHead(reader)
        request = parseHead(head) if head else None
        if request is None:
            return

        if request.method == "OPTIONS":
            writer.write(buildHttpResponse(200, headers=buildPreflightHeaders(request)))
        elif request.path != "/jsonrpc":
            writer.write(buildHttpResponse(404))
        elif request.method == "GET" and request.headers.get("upgrade", "").lower() == "websocket":
            await self._runWebSocket(reader, writer, head)
            return
        elif request.method == "POST":
            await self._runHttp(reader, writer, request)
        else:
            writer.write(buildHttpResponse(404))
        await writer.drain()

    async def _runHttp(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, request: HttpRequest) -> None:
        try:
            length = 0 if "transfer-encoding" in request.headers else int(request.headers.get("content-length", "0"))
        except ValueError:
            return
        if length > MAX_REQUEST_SIZE:
            return
        try:
            body = await reader.readexactly(length)
        except asyncio.IncompleteReadError:
            return
        response = await self._run(body)
        payload = json.dumps(response, ensure_ascii=False).encode("utf-8")
        writer.write(buildHttpResponse(toHttpStatus(response), payload, {"Content-Type": "application/json-rpc"}))

    async def _runWebSocket(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, head: bytes) -> None:
        stream = await WebSocketStream.open(reader, writer, head, maxSize=MAX_REQUEST_SIZE)
        if stream is None:
            return
        async for message in stream.messages():
            await stream.send(json.dumps(await self._run(message), ensure_ascii=False))

    async def _run(self, body: bytes) -> dict:
        try:
            data = json.loads(body)
        except ValueError:
            return buildError(None, JSONRPC_PARSE_ERROR, "Parse error.")
        if not isinstance(data, dict):
            return buildError(None, JSONRPC_INVALID_REQUEST, "Invalid Request.")
        rpcId = data.get("id")
        method = data.get("method")
        params = data.get("params", [])
        if "id" not in data or not isinstance(method, str):
            return buildError(rpcId, JSONRPC_INVALID_REQUEST, "Invalid Request.")
        if not isinstance(params, list):
            return buildError(rpcId, JSONRPC_INVALID_PARAMS, "Invalid params.")

        token = ""
        if params and isinstance(params[0], str) and params[0].startswith("token:"):
            token, params = params[0].removeprefix("token:"), params[1:]
        if (secret := cfg.aria2RpcToken.value) and token != secret:
            await asyncio.sleep(UNAUTHORIZED_DELAY)
            return buildError(rpcId, ARIA2_ERROR, "Unauthorized")

        try:
            match method:
                case "aria2.getVersion":
                    result = {"version": VERSION, "enabledFeatures": ["HTTPS"]}
                case "aria2.addUri":
                    result = self._addUri(params)
                case _:
                    raise RpcError(f"No such method: {method}")
        except RpcError as e:
            return buildError(rpcId, ARIA2_ERROR, str(e))
        return {"jsonrpc": "2.0", "id": rpcId, "result": result}

    def _addUri(self, params: list) -> str:
        if not params:
            raise RpcError("The parameter at 0 is required but missing.")
        if not isinstance(params[0], list):
            raise RpcError("The parameter at 0 has wrong type.")
        uris = [uri for uri in params[0] if isinstance(uri, str)]
        if not uris:
            raise RpcError("URI is not provided.")
        options = params[1] if len(params) > 1 else {}
        if not isinstance(options, dict):
            raise RpcError("The parameter at 1 has wrong type.")

        directory = toText(options, "dir")
        taskOptions = TaskOptions(
            url=uris[0],
            headers=toHeaders(options),
            outputFolder=Path(directory or cfg.downloadFolder.value),
            clientProfile="" if cfg.aria2RpcEmulateFingerprint.value else "raw",
        )
        self._coroutineRunner.submit(
            self._parse(taskOptions),
            done=self._onTaskParsed, failed=self._onTaskParseFailed,
            name=toText(options, "out"),
        )
        return token_hex(8)

    def _onTaskParsed(self, task: Task, name: str) -> None:
        if name:
            task.setName(name)
        if cfg.shouldDraftTakenDownload.value:
            self.taskDraftRequested.emit([task])
            return
        self._addTask(task)

    def _onTaskParseFailed(self, error, **_) -> None:
        logger.warning("Aria2 RPC task parse failed: {}", error)
