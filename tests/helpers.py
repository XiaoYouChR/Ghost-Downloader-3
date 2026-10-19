from __future__ import annotations

import asyncio
import socket
import sys
from collections.abc import Callable

import pytest
from aiohttp import web

EXE_SUFFIX = ".exe" if sys.platform == "win32" else ""


def buildFileContent(size: int) -> bytes:
    return bytes(i % 256 for i in range(size))


def buildRangeHandler(content: bytes):
    async def handler(request: web.Request) -> web.Response:
        rangeHeader = request.headers.get("Range")
        if rangeHeader is None:
            return web.Response(
                body=content,
                headers={"Content-Length": str(len(content)),
                          "Accept-Ranges": "bytes"},
            )
        rangeSpec = rangeHeader.replace("bytes=", "")
        parts = rangeSpec.split("-")
        start = int(parts[0])
        end = int(parts[1]) if parts[1] else len(content) - 1
        body = content[start:end + 1]
        return web.Response(
            status=206, body=body,
            headers={
                "Content-Range": f"bytes {start}-{end}/{len(content)}",
                "Content-Length": str(len(body)),
            },
        )
    return handler


async def runStep(step) -> list[int]:
    speeds = []

    def reportSpeed(n):
        speeds.append(n)

    async def waitForSpeedLimit():
        pass

    from app.models.task import TaskStatus
    if step.task.status != TaskStatus.RUNNING:
        step.task.setStatus(TaskStatus.RUNNING)
    await step.task.run(reportSpeed, waitForSpeedLimit)
    return speeds


async def waitUntil(isDone: Callable[[], bool], timeout: float = 5) -> None:
    async with asyncio.timeout(timeout):
        while not isDone():
            await asyncio.sleep(0.01)


def probeFreePort() -> int:
    for _ in range(20):
        with socket.socket(socket.AF_INET) as v4:
            v4.bind(("127.0.0.1", 0))
            port = v4.getsockname()[1]
            with socket.socket(socket.AF_INET6) as v6:
                try:
                    v6.bind(("::1", port))
                except OSError:
                    continue
        return port
    pytest.skip("本机没有可用的 IPv6 回环地址")
