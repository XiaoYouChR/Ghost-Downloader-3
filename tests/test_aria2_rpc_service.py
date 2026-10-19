from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
import websockets

from app.config.cfg import cfg
from app.config.constants import VERSION
from app.services.port_listener import ListenStatus
from tests.helpers import probeFreePort, waitUntil


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> dict:
        return json.loads(self.body)


class Aria2Client:
    def __init__(self, port: int):
        self.port = port

    async def requestRaw(self, raw: bytes) -> Response | None:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(raw)
        data = await asyncio.wait_for(reader.read(), 3)
        writer.close()
        if not data:
            return None
        head, _, body = data.partition(b"\r\n\r\n")
        lines = head.decode().split("\r\n")
        headers = {k.strip().lower(): v.strip() for k, v in (line.split(":", 1) for line in lines[1:])}
        return Response(int(lines[0].split()[1]), headers, body)

    async def requestJson(self, payload, path: str = "/jsonrpc") -> Response:
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        return await self.requestRaw(
            f"POST {path} HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n\r\n".encode() + body
        )

    async def request(self, method: str, params: list) -> dict:
        return (await self.requestJson({"jsonrpc": "2.0", "id": "t", "method": method, "params": params})).json()

    def open(self, path: str = "/jsonrpc"):
        return websockets.connect(f"ws://127.0.0.1:{self.port}{path}")


@pytest.fixture
async def aria2(engine):
    cfg.set(cfg.aria2RpcPort, probeFreePort())
    await asyncio.sleep(0.05)
    cfg.set(cfg.isAria2RpcEnabled, True)
    await waitUntil(lambda: engine.aria2RpcListener.state.status == ListenStatus.LISTENING)
    return Aria2Client(engine.aria2RpcListener.state.port)


@pytest.fixture
def pack(engine):
    return engine.featureService.packById("test")


def addedNames(engine) -> list[str]:
    return [task.name for task in engine.taskService.tasks]


def isGid(value) -> bool:
    return isinstance(value, str) and len(value) == 16 and all(c in "0123456789abcdef" for c in value)


class TestTransport:
    @pytest.fixture(params=["desktop", "android"])
    def engine(self, request, startEngine):
        return startEngine(request.param)

    async def test_request_version_over_http(self, aria2):
        response = await aria2.requestJson({"jsonrpc": "2.0", "id": "a", "method": "aria2.getVersion", "params": []})

        assert response.status == 200
        assert response.headers["content-type"] == "application/json-rpc"
        assert response.headers["access-control-allow-origin"] == "*"
        assert response.json() == {"jsonrpc": "2.0", "id": "a",
                                   "result": {"version": VERSION, "enabledFeatures": ["HTTPS"]}}

    async def test_request_download_folder_over_http(self, aria2, downloadFolder):
        response = await aria2.requestJson({"jsonrpc": "2.0", "id": "g", "method": "aria2.getGlobalOption",
                                     "params": ["token:"]})

        assert response.status == 200
        assert response.headers["content-type"] == "application/json-rpc"
        assert response.headers["access-control-allow-origin"] == "*"
        body = response.json()
        assert Path(body["result"].pop("dir")) == downloadFolder
        assert body == {"jsonrpc": "2.0", "id": "g", "result": {}}

    async def test_request_version_over_websocket(self, aria2):
        async with aria2.open() as ws:
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": "w", "method": "aria2.getVersion", "params": []}))
            assert json.loads(await ws.recv())["result"]["version"] == VERSION

    async def test_request_preflight_without_token(self, aria2):
        cfg.set(cfg.aria2RpcToken, "secret")
        response = await aria2.requestRaw(
            b"OPTIONS /jsonrpc HTTP/1.1\r\nHost: x\r\nOrigin: https://pdpb.cn\r\n"
            b"Access-Control-Request-Method: POST\r\nAccess-Control-Request-Headers: content-type\r\n\r\n"
        )

        assert response.status == 200
        assert response.body == b""
        assert response.headers["access-control-allow-origin"] == "*"
        assert response.headers["access-control-allow-methods"] == "POST, GET, OPTIONS"
        assert response.headers["access-control-allow-headers"] == "content-type"

    async def test_close_mid_request_does_not_block_others(self, aria2):
        _, writer = await asyncio.open_connection("127.0.0.1", aria2.port)
        writer.write(b"POST /jsonrpc HTTP/1.1\r\nHost: x\r\n")
        writer.close()

        result = await asyncio.wait_for(aria2.request("aria2.getVersion", []), 1)
        assert result["result"]["version"] == VERSION


async def test_request_with_wrong_token_is_refused(aria2):
    cfg.set(cfg.aria2RpcToken, "secret")
    result = await aria2.request("aria2.getVersion", ["token:guess"])

    assert result["error"]["message"] == "Unauthorized"


async def test_request_with_right_token(aria2):
    cfg.set(cfg.aria2RpcToken, "secret")
    result = await aria2.request("aria2.getVersion", ["token:secret"])

    assert result["result"]["version"] == VERSION


async def test_request_with_token_when_none_is_set(aria2):
    result = await aria2.request("aria2.addUri", ["token:", ["http://test/f.zip"]])

    assert isGid(result["result"])


async def test_add_task_with_aria2_options(aria2, engine, pack, downloadFolder):
    result = await aria2.request("aria2.addUri", [
        ["http://test/f.zip", "http://mirror.test/f.zip"],
        {"dir": str(downloadFolder / "sub"), "out": "renamed.zip",
         "header": ["Cookie: a=b", "User-Agent: from-header"],
         "user-agent": "from-option", "referer": "http://test/"},
    ])
    await waitUntil(lambda: addedNames(engine) == ["renamed.zip"])

    assert isGid(result["result"])
    [options] = pack.parsedOptions
    assert options.url == "http://test/f.zip"
    assert options.outputFolder == downloadFolder / "sub"
    assert options.headers == {"Cookie": "a=b", "User-Agent": "from-header", "Referer": "http://test/"}


async def test_add_goes_to_draft_when_drafting_is_on(aria2, engine):
    cfg.set(cfg.shouldDraftTakenDownload, True)
    drafted = []
    engine.aria2RpcService.taskDraftRequested.connect(drafted.extend)

    await aria2.request("aria2.addUri", [["http://test/f"]])

    await waitUntil(lambda: [task.url for task in drafted] == ["http://test/f"])
    assert engine.taskService.tasks == []


async def test_add_reports_parse_failure_after_replying(aria2, engine, pack):
    pack.failingUrls.add("http://test/f")
    failed = []
    engine.aria2RpcService.parseFailed.connect(lambda url, error: failed.append((url, str(error))))

    result = await aria2.request("aria2.addUri", [["http://test/f"]])

    assert isGid(result["result"])
    await waitUntil(lambda: failed == [("http://test/f", "network error")])
    assert engine.taskService.tasks == []


async def test_request_multicall_returns_each_result(aria2, engine):
    result = await aria2.request("system.multicall", [[
        {"methodName": "aria2.addUri", "params": [["http://test/1.zip"]]},
        {"methodName": "aria2.addUri", "params": [["http://test/2.zip"]]},
    ]])

    [[first], [second]] = result["result"]
    assert isGid(first) and isGid(second)
    await waitUntil(lambda: sorted(addedNames(engine)) == ["1.zip", "2.zip"])


async def test_request_multicall_checks_token_per_call(aria2):
    cfg.set(cfg.aria2RpcToken, "secret")
    response = await aria2.requestJson({"jsonrpc": "2.0", "id": "x", "method": "system.multicall", "params": [[
        {"methodName": "aria2.getVersion", "params": ["token:secret"]},
        {"methodName": "aria2.getVersion", "params": []},
    ]]})

    assert response.status == 200
    [[version], fault] = response.json()["result"]
    assert version["version"] == VERSION
    assert fault == {"code": 1, "message": "Unauthorized"}


async def test_request_batch_answers_each(aria2):
    response = await aria2.requestJson([
        {"jsonrpc": "2.0", "id": "a", "method": "aria2.getVersion"},
        {"jsonrpc": "2.0", "id": "b", "method": "aria2.tellStatus", "params": ["g"]},
    ])

    assert response.status == 200
    version, error = response.json()
    assert (version["id"], version["result"]["version"]) == ("a", VERSION)
    assert (error["id"], error["error"]) == ("b", {"code": 1, "message": "No such method: aria2.tellStatus"})


async def test_request_batch_over_websocket(aria2):
    async with aria2.open() as ws:
        await ws.send(json.dumps([{"jsonrpc": "2.0", "id": "a", "method": "aria2.getVersion"}]))
        [response] = json.loads(await ws.recv())

    assert response["result"]["version"] == VERSION
