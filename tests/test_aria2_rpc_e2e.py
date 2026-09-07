from __future__ import annotations

import asyncio
import http.client
import json
import time

import pytest

from app.config.cfg import cfg
from app.services.aria2_rpc import Aria2RpcServer
from app.services.coroutine_runner import CoroutineRunner


def _findFreePort() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _rpcRequest(port: int, method: str, params: list | None = None, rpcId: int = 1) -> dict:
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": rpcId,
        "method": method,
        "params": params or [],
    }).encode("utf-8")

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", "/jsonrpc", body=body, headers={
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    })
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    return data


@pytest.fixture
def runner(qapp):
    from PySide6.QtCore import QTimer
    from shiboken6 import isValid

    dispatcher = lambda fn: QTimer.singleShot(0, qapp, fn)
    cr = CoroutineRunner(dispatcher, isAlive=isValid, loop=asyncio.new_event_loop())
    cr.start()
    yield cr
    cr.stop()


@pytest.fixture
def server(runner):
    port = _findFreePort()
    cfg.set(cfg.aria2RpcPort, port)
    cfg.set(cfg.aria2RpcToken, "")

    async def mockParse(options):
        raise RuntimeError("parse not implemented in test")

    srv = Aria2RpcServer(runner, parse=mockParse, addTask=lambda t: None)
    yield srv, port
    srv.stop()


class TestAria2RpcServer:

    def test_start_binds_port(self, server):
        srv, port = server
        srv.start()
        time.sleep(0.2)
        assert srv._serveWorkId is not None

    def test_getVersion(self, server):
        srv, port = server
        srv.start()
        time.sleep(0.2)

        resp = _rpcRequest(port, "aria2.getVersion")
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert "version" in resp["result"]
        assert "enabledFeatures" in resp["result"]

    def test_addUri(self, server):
        srv, port = server
        srv.start()
        time.sleep(0.2)

        resp = _rpcRequest(port, "aria2.addUri", [["https://example.com/file.zip"]])
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert isinstance(resp["result"], str)
        assert len(resp["result"]) == 16

    def test_method_not_found(self, server):
        srv, port = server
        srv.start()
        time.sleep(0.2)

        resp = _rpcRequest(port, "aria2.unknownMethod")
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_stop_and_restart(self, server):
        srv, port = server
        srv.start()
        time.sleep(0.2)

        resp = _rpcRequest(port, "aria2.getVersion")
        assert "result" in resp

        srv.stop()
        time.sleep(0.3)
        assert srv._serveWorkId is None

        cfg.set(cfg.aria2RpcPort, port)
        srv.start()
        time.sleep(0.2)

        resp = _rpcRequest(port, "aria2.getVersion")
        assert "result" in resp

    def test_token_auth(self, server):
        srv, port = server
        cfg.set(cfg.aria2RpcToken, "mysecret")
        srv.start()
        time.sleep(0.2)

        resp = _rpcRequest(port, "aria2.getVersion", ["token:mysecret"])
        assert "result" in resp

        resp = _rpcRequest(port, "aria2.getVersion", ["token:wrong"])
        assert "error" in resp
        assert resp["error"]["message"] == "Unauthorized"

        resp = _rpcRequest(port, "aria2.getVersion", [])
        assert "error" in resp
        assert resp["error"]["message"] == "Unauthorized"
