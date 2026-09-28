from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
import websockets
from websockets.exceptions import InvalidStatus

from app.config.cfg import cfg
from app.config.constants import VERSION
from app.models.task import TaskError
from app.services.aria2_rpc import Aria2RpcService
from app.services.coroutine_runner import CoroutineRunner
from app.services.loopback_server import ListenStatus, LoopbackServer
from tests.test_loopback_server import FakeItem, findFreePort, waitFor

pytestmark = pytest.mark.asyncio(loop_factories=["asyncio", "uvloop"])


@dataclass
class FakeTask:
    options: object
    name: str = ""

    def setName(self, name: str) -> None:
        self.name = name


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> dict:
        return json.loads(self.body)


class Aria2Client:
    def __init__(self, port: int, added: list, drafted: list, failed: list):
        self.port = port
        self.added = added
        self.drafted = drafted
        self.failed = failed

    async def send(self, raw: bytes) -> Response | None:
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

    async def post(self, payload, path: str = "/jsonrpc") -> Response:
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        return await self.send(
            f"POST {path} HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n\r\n".encode() + body
        )

    async def call(self, method: str, params: list) -> dict:
        return (await self.post({"jsonrpc": "2.0", "id": "t", "method": method, "params": params})).json()

    def connect(self, path: str = "/jsonrpc"):
        return websockets.connect(f"ws://127.0.0.1:{self.port}{path}")


@pytest.fixture
async def aria2(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg.aria2RpcToken, "value", "")
    monkeypatch.setattr(cfg.shouldDraftTakenDownload, "value", False)
    monkeypatch.setattr(cfg.downloadFolder, "value", str(tmp_path))
    loop = asyncio.get_running_loop()
    runner = CoroutineRunner(loop.call_soon, loop=loop)
    added, drafted, failed = [], [], []

    async def parse(options):
        if "fail" in options.url:
            raise ValueError("unreachable")
        return FakeTask(options)

    rpc = Aria2RpcService(runner, parse=parse, addTask=added.append)
    rpc.taskDraftRequested.connect(drafted.extend)
    rpc.parseFailed.connect(lambda url, error: failed.append((url, error)))
    server = LoopbackServer(runner, rpc.handle, isEnabled=FakeItem(True), port=FakeItem(findFreePort()))
    server.start()
    await waitFor(lambda: server.state.status == ListenStatus.LISTENING)

    yield Aria2Client(server.state.port, added, drafted, failed)

    server.stop()
    await asyncio.sleep(0.05)


def isGid(value) -> bool:
    return isinstance(value, str) and len(value) == 16 and all(c in "0123456789abcdef" for c in value)


class TestTransport:
    async def test_getVersion_over_http(self, aria2):
        response = await aria2.post({"jsonrpc": "2.0", "id": "a", "method": "aria2.getVersion", "params": []})

        assert response.status == 200
        assert response.headers["content-type"] == "application/json-rpc"
        assert response.headers["access-control-allow-origin"] == "*"
        assert response.json() == {"jsonrpc": "2.0", "id": "a",
                                   "result": {"version": VERSION, "enabledFeatures": ["HTTPS"]}}

    async def test_getGlobalOption_over_http(self, aria2, tmp_path):
        response = await aria2.post({"jsonrpc": "2.0", "id": "g", "method": "aria2.getGlobalOption",
                                     "params": ["token:"]})

        assert response.status == 200
        assert response.headers["content-type"] == "application/json-rpc"
        assert response.headers["access-control-allow-origin"] == "*"
        assert response.json() == {"jsonrpc": "2.0", "id": "g", "result": {"dir": str(tmp_path)}}

    async def test_getVersion_over_websocket(self, aria2):
        async with aria2.connect() as ws:
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": "w", "method": "aria2.getVersion", "params": []}))
            assert json.loads(await ws.recv())["result"]["version"] == VERSION

    async def test_preflight_is_answered_without_token(self, aria2, monkeypatch):
        monkeypatch.setattr(cfg.aria2RpcToken, "value", "secret")
        response = await aria2.send(
            b"OPTIONS /jsonrpc HTTP/1.1\r\nHost: x\r\nOrigin: https://pdpb.cn\r\n"
            b"Access-Control-Request-Method: POST\r\nAccess-Control-Request-Headers: content-type\r\n\r\n"
        )

        assert response.status == 200
        assert response.body == b""
        assert response.headers["access-control-allow-origin"] == "*"
        assert response.headers["access-control-allow-methods"] == "POST, GET, OPTIONS"
        assert response.headers["access-control-allow-headers"] == "content-type"

    async def test_other_path_is_not_found(self, aria2):
        assert (await aria2.post(b"{}", path="/rpc")).status == 404

    async def test_websocket_on_other_path_is_not_found(self, aria2):
        with pytest.raises(InvalidStatus) as error:
            async with aria2.connect("/other"):
                pass
        assert error.value.response.status_code == 404

    async def test_client_leaving_mid_head_does_not_stall_server(self, aria2):
        _, writer = await asyncio.open_connection("127.0.0.1", aria2.port)
        writer.write(b"POST /jsonrpc HTTP/1.1\r\nHost: x\r\n")
        writer.close()

        result = await asyncio.wait_for(aria2.call("aria2.getVersion", []), 1)
        assert result["result"]["version"] == VERSION

    async def test_body_over_2m_is_dropped_without_response(self, aria2):
        response = await aria2.send(
            b"POST /jsonrpc HTTP/1.1\r\nHost: x\r\nContent-Length: 3000000\r\n\r\n{}"
        )
        assert response is None


class TestRequestErrors:
    @pytest.mark.parametrize("body, status, code", [
        (b"{not json", 500, -32700),
        (b"[]", 400, -32600),
        (b'{"jsonrpc":"2.0","method":"aria2.getVersion"}', 400, -32600),
        (b'{"jsonrpc":"2.0","id":"x","method":"aria2.getVersion","params":{}}', 500, -32602),
    ])
    async def test_malformed_request(self, aria2, body, status, code):
        response = await aria2.post(body)

        assert response.status == status
        assert response.json()["error"]["code"] == code

    async def test_unknown_method(self, aria2):
        response = await aria2.post({"jsonrpc": "2.0", "id": "x", "method": "aria2.tellStatus", "params": ["g"]})

        assert response.status == 400
        assert response.json()["error"] == {"code": 1, "message": "No such method: aria2.tellStatus"}


class TestToken:
    async def test_missing_token_is_unauthorized_after_a_second(self, aria2, monkeypatch):
        monkeypatch.setattr(cfg.aria2RpcToken, "value", "secret")
        started = time.monotonic()
        response = await aria2.post({"jsonrpc": "2.0", "id": "x", "method": "aria2.addUri", "params": [[]]})

        assert time.monotonic() - started >= 1
        assert response.status == 400
        assert response.json()["error"] == {"code": 1, "message": "Unauthorized"}

    async def test_wrong_token_is_unauthorized(self, aria2, monkeypatch):
        monkeypatch.setattr(cfg.aria2RpcToken, "value", "secret")
        result = await aria2.call("aria2.getVersion", ["token:guess"])

        assert result["error"]["message"] == "Unauthorized"

    async def test_right_token_is_accepted(self, aria2, monkeypatch):
        monkeypatch.setattr(cfg.aria2RpcToken, "value", "secret")
        result = await aria2.call("aria2.getVersion", ["token:secret"])

        assert result["result"]["version"] == VERSION

    async def test_token_param_is_stripped_when_no_token_is_set(self, aria2):
        result = await aria2.call("aria2.addUri", ["token:", ["https://a.test/f.zip"]])

        assert isGid(result["result"])


class TestAddUri:
    async def test_task_is_created_from_aria2_options(self, aria2, tmp_path):
        result = await aria2.call("aria2.addUri", [
            ["https://a.test/f.zip", "https://mirror.test/f.zip"],
            {"dir": str(tmp_path / "sub"), "out": "renamed.zip",
             "header": ["Cookie: a=b", "User-Agent: from-header"],
             "user-agent": "from-option", "referer": "https://a.test/"},
        ])
        await waitFor(lambda: aria2.added)

        assert isGid(result["result"])
        task = aria2.added[0]
        assert task.options.url == "https://a.test/f.zip"
        assert task.options.outputFolder == tmp_path / "sub"
        assert task.options.headers == {"Cookie": "a=b", "User-Agent": "from-header", "Referer": "https://a.test/"}
        assert task.name == "renamed.zip"

    async def test_header_may_be_a_single_string(self, aria2):
        await aria2.call("aria2.addUri", [["https://a.test/f"], {"header": "Cookie: a=b"}])
        await waitFor(lambda: aria2.added)

        assert aria2.added[0].options.headers == {"Cookie": "a=b"}

    async def test_wrongly_typed_options_are_ignored(self, aria2, tmp_path):
        async with aria2.connect() as ws:
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "aria2.addUri", "params": [
                ["https://a.test/f"], {"dir": 123, "out": ["x"], "header": 5, "user-agent": None}]}))
            assert isGid(json.loads(await ws.recv())["result"])

            await ws.send(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "aria2.addUri", "params": [
                ["https://a.test/g"], {"dir": None}]}))
            assert isGid(json.loads(await ws.recv())["result"])

        await waitFor(lambda: len(aria2.added) == 2)
        assert aria2.added[0].options.outputFolder == Path(tmp_path)
        assert aria2.added[0].options.headers == {}
        assert aria2.added[0].name == ""

    @pytest.mark.parametrize("params, message", [
        ([], "The parameter at 0 is required but missing."),
        (["https://a.test/f"], "The parameter at 0 has wrong type."),
        ([[]], "URI is not provided."),
        ([[1, None]], "URI is not provided."),
        ([["https://a.test/f"], "dir"], "The parameter at 1 has wrong type."),
    ])
    async def test_invalid_uris_or_options(self, aria2, params, message):
        response = await aria2.post({"jsonrpc": "2.0", "id": "x", "method": "aria2.addUri", "params": params})

        assert response.status == 400
        assert response.json()["error"] == {"code": 1, "message": message}
        assert aria2.added == []

    async def test_task_goes_to_draft_when_drafting_is_on(self, aria2, monkeypatch):
        monkeypatch.setattr(cfg.shouldDraftTakenDownload, "value", True)
        await aria2.call("aria2.addUri", [["https://a.test/f"]])
        await waitFor(lambda: aria2.drafted)

        assert aria2.added == []
        assert aria2.drafted[0].options.url == "https://a.test/f"

    async def test_parse_failure_is_reported_after_gid_is_returned(self, aria2):
        result = await aria2.call("aria2.addUri", [["https://fail.test/f"]])
        await waitFor(lambda: aria2.failed)

        assert isGid(result["result"])
        assert aria2.added == []
        [(url, error)] = aria2.failed
        assert url == "https://fail.test/f"
        assert isinstance(error, TaskError)
        assert (error.message, error.params) == ("发生了意外错误：{detail}", {"detail": "unreachable"})
