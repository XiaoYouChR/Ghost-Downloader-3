from __future__ import annotations

import asyncio
import json
from unittest.mock import Mock

import pytest
import websockets

from app.services.aria2_rpc import Aria2RpcServer


@pytest.fixture
def mockCoroutineRunner():
    runner = Mock()
    runner.submit = lambda coro, **kwargs: asyncio.create_task(coro)
    return runner


@pytest.fixture
def mockParse():
    async def parse(taskOptions):
        from app.models.task import Task
        task = Task()
        task.url = taskOptions.url
        return task
    return parse


@pytest.fixture
def mockAddTask():
    tasks = []
    def add(task):
        tasks.append(task)
    add.tasks = tasks
    return add


@pytest.fixture
async def aria2Server(mockCoroutineRunner, mockParse, mockAddTask):
    import socket

    server = Aria2RpcServer(mockCoroutineRunner, mockParse, mockAddTask)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    sock.setblocking(False)
    port = sock.getsockname()[1]

    task = asyncio.create_task(server._run(sock))
    await asyncio.sleep(0.1)

    yield f"127.0.0.1:{port}", server, mockAddTask

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


class TestAria2RpcHttp:
    async def test_getVersion_returns_version_and_features(self, aria2Server):
        addr, _, _ = aria2Server

        request = json.dumps({
            "jsonrpc": "2.0",
            "id": "test1",
            "method": "aria2.getVersion",
            "params": []
        }).encode()

        host, port = addr.split(":")
        reader, writer = await asyncio.open_connection(host, int(port))

        writer.write(
            b"POST /jsonrpc HTTP/1.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(request)).encode() + b"\r\n"
            b"\r\n" + request
        )
        await writer.drain()

        response = b""
        while b"\r\n\r\n" not in response:
            response += await reader.read(1024)

        headers = response[:response.index(b"\r\n\r\n")].decode()
        contentLength = next(
            int(line.split(":", 1)[1].strip())
            for line in headers.split("\r\n")
            if line.lower().startswith("content-length:")
        )

        body = response[response.index(b"\r\n\r\n") + 4:]
        while len(body) < contentLength:
            body += await reader.read(1024)

        data = json.loads(body)

        assert data["jsonrpc"] == "2.0"
        assert data["id"] == "test1"
        assert "version" in data["result"]
        assert "enabledFeatures" in data["result"]

        writer.close()
        await writer.wait_closed()


class TestAria2RpcWebSocket:
    async def test_websocket_handshake_succeeds(self, aria2Server):
        addr, _, _ = aria2Server
        async with websockets.connect(f"ws://{addr}/jsonrpc") as ws:
            assert ws.protocol.state.name == "OPEN"

    async def test_getVersion_over_websocket(self, aria2Server):
        addr, _, _ = aria2Server

        async with websockets.connect(f"ws://{addr}/jsonrpc") as ws:
            await ws.send(json.dumps({
                "jsonrpc": "2.0",
                "id": "ws1",
                "method": "aria2.getVersion",
                "params": []
            }))

            data = json.loads(await ws.recv())

            assert data["jsonrpc"] == "2.0"
            assert data["id"] == "ws1"
            assert "version" in data["result"]
