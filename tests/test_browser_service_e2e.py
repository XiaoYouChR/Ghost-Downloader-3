"""BrowserService E2E: websockets transport + Signal I/O bridge."""
from __future__ import annotations

import asyncio
import json
import time

import pytest
import websockets

from app.services.browser_service import BrowserService, PROTOCOL_VERSION
from app.services.coroutine_runner import CoroutineRunner


class StubTaskService:
    tasks = []

    def add(self, task):
        pass

    def pause(self, task):
        pass

    def start(self, task):
        pass

    def delete(self, task, shouldDeleteFiles=False):
        pass

    def redownload(self, task):
        pass

    def taskById(self, taskId):
        return None


TEST_TOKEN = "test-pair-token-abc"


def processEventsUntil(qapp, predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture()
def runner(qapp):
    from PySide6.QtCore import QTimer
    from shiboken6 import isValid

    dispatcher = lambda fn: QTimer.singleShot(0, qapp, fn)
    cr = CoroutineRunner(dispatcher, isAlive=isValid)
    cr.start()
    yield cr
    cr.stop()


@pytest.fixture()
def service(qapp, runner, monkeypatch):
    from app.config.cfg import cfg
    monkeypatch.setattr(cfg.browserExtensionPairToken, "value", TEST_TOKEN)
    monkeypatch.setattr(cfg.shouldDraftTakenDownload, "value", False)

    svc = BrowserService(runner, StubTaskService(), parse=lambda opts: None, loadCrx=lambda: b"")
    yield svc
    svc.stop()


def startOnFreePort(service):
    """Start BrowserService on a random free port, bypassing config validation."""
    import socket as _socket
    if service._serveWorkId is not None:
        return
    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    sock.setblocking(False)
    service._boundPort = sock.getsockname()[1]
    service._serveWorkId = service._coroutineRunner.submit(service._run(sock))
    service._snapshotWorkId = service._coroutineRunner.submit(service._broadcastLoop())


class TestBrowserServiceE2E:

    def test_start_binds_port_immediately(self, service):
        startOnFreePort(service)
        assert service.boundPort > 0

    def test_stop_resets_port(self, service):
        startOnFreePort(service)
        assert service.boundPort > 0
        service.stop()
        assert service.boundPort == 0

    def test_restart_after_stop(self, service):
        startOnFreePort(service)
        port1 = service.boundPort
        assert port1 > 0
        service.stop()
        assert service.boundPort == 0
        startOnFreePort(service)
        port2 = service.boundPort
        assert port2 > 0

    def test_websocket_connect(self, qapp, service):
        startOnFreePort(service)
        port = service.boundPort

        connected = [False]

        async def tryConnect():
            async with websockets.connect(f"ws://127.0.0.1:{port}"):
                connected[0] = True

        service._coroutineRunner.submit(tryConnect())
        assert processEventsUntil(qapp, lambda: connected[0])

    def test_hello_handshake(self, qapp, service):
        startOnFreePort(service)
        port = service.boundPort

        result = [None]

        async def doHandshake():
            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(json.dumps({
                    "type": "hello",
                    "protocolVersion": PROTOCOL_VERSION,
                    "token": TEST_TOKEN,
                    "extensionVersion": "1.0.0",
                    "installType": "normal",
                }))
                resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                result[0] = resp

        service._coroutineRunner.submit(doHandshake())
        assert processEventsUntil(qapp, lambda: result[0] is not None)
        assert result[0]["type"] == "hello_ack"
        assert result[0]["protocolVersion"] == PROTOCOL_VERSION

    def test_hello_wrong_token(self, qapp, service):
        startOnFreePort(service)
        port = service.boundPort

        result = [None]

        async def doHandshake():
            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(json.dumps({
                    "type": "hello",
                    "protocolVersion": PROTOCOL_VERSION,
                    "token": "wrong-token",
                    "extensionVersion": "1.0.0",
                    "installType": "normal",
                }))
                resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                result[0] = resp

        service._coroutineRunner.submit(doHandshake())
        assert processEventsUntil(qapp, lambda: result[0] is not None)
        assert result[0]["type"] == "error"
        assert result[0]["code"] == "unauthorized"

    def test_pair_request_flow(self, qapp, service):
        startOnFreePort(service)
        port = service.boundPort

        pairPayload = [None]
        result = [None]

        def onPairRequested(req):
            pairPayload[0] = req
            service.approvePair(req["session"], req["requestId"])

        service.pairRequested.connect(onPairRequested)

        async def doPair():
            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(json.dumps({
                    "type": "pair_request",
                    "requestId": "pr-1",
                    "protocolVersion": PROTOCOL_VERSION,
                    "extensionVersion": "1.0.0",
                    "clientKind": "chrome",
                }))
                resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                result[0] = resp

        service._coroutineRunner.submit(doPair())
        assert processEventsUntil(qapp, lambda: result[0] is not None)
        assert pairPayload[0] is not None
        assert pairPayload[0]["requestId"] == "pr-1"
        assert result[0]["type"] == "pair_result"
        assert result[0]["ok"] is True
        assert result[0]["token"] == TEST_TOKEN

    def test_connection_changed_signal(self, qapp, service):
        startOnFreePort(service)
        port = service.boundPort

        signals = []
        service.connectionChanged.connect(lambda: signals.append("changed"))

        handshakeDone = [False]

        async def doHello():
            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(json.dumps({
                    "type": "hello",
                    "protocolVersion": PROTOCOL_VERSION,
                    "token": TEST_TOKEN,
                    "extensionVersion": "1.0.0",
                    "installType": "normal",
                }))
                await asyncio.wait_for(ws.recv(), timeout=5)
                handshakeDone[0] = True
                await asyncio.sleep(0.2)

        service._coroutineRunner.submit(doHello())
        assert processEventsUntil(qapp, lambda: handshakeDone[0])
        assert "changed" in signals
