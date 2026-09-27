from __future__ import annotations

import asyncio
import io
import json
import struct
import zipfile
from pathlib import Path

import pytest
import websockets
from websockets.exceptions import ConnectionClosed

from app.config.cfg import cfg
from app.config.constants import LATEST_EXTENSION_VERSION, VERSION
from app.models.task import Task, TaskStatus
from app.services import browser_service
from app.services.browser_service import PROTOCOL_VERSION, BrowserService, PairRequest, installExtension
from app.services.coroutine_runner import CoroutineRunner
from app.services.loopback_server import ListenStatus, LoopbackServer
from app.signal import BoundSignal, Signal
from tests.test_loopback_server import FakeItem, findFreePort, waitFor

pytestmark = pytest.mark.asyncio(loop_factories=["asyncio", "uvloop"])

TOKEN = "pair-token"


class FakeTaskService:
    taskAdded = Signal(object)
    taskRemoved = Signal(str)
    taskStarted = Signal(object)
    taskPaused = Signal(object)
    taskCompleted = Signal(object)
    taskFailed = Signal(object)
    seedingStarted = Signal(object)
    seedingStopped = Signal(object)
    queueChanged = Signal()
    fileDisappeared = Signal(object)

    def __init__(self):
        self.tasks: list[Task] = []
        self.calls: list[tuple] = []
        self.isNameConflictAsked = False

    def add(self, task):
        if self.isNameConflictAsked:
            return False
        self.tasks.append(task)
        self.taskAdded.emit(task)
        return True

    def taskById(self, taskId):
        return next((t for t in self.tasks if t.taskId == taskId), None)

    def pause(self, task):
        self.calls.append(("pause", task.taskId))

    def start(self, task):
        self.calls.append(("start", task.taskId))

    def delete(self, task, shouldDeleteFiles):
        self.calls.append(("delete", task.taskId, shouldDeleteFiles))

    def redownload(self, task):
        self.calls.append(("redownload", task.taskId))


class Harness:
    def __init__(self, service: BrowserService, server: LoopbackServer, taskService: FakeTaskService,
                 speedChanged: BoundSignal, drafted: list, events: list):
        self.service = service
        self.server = server
        self.taskService = taskService
        self.speedChanged = speedChanged
        self.drafted = drafted
        self.events = events

    def connect(self):
        return websockets.connect(f"ws://127.0.0.1:{self.server.state.port}/")

    async def hello(self, ws, token: str = TOKEN, protocolVersion: int = PROTOCOL_VERSION) -> dict:
        await ws.send(json.dumps({"type": "hello", "protocolVersion": protocolVersion, "token": token,
                                  "extensionVersion": "2.2.0", "installType": "normal"}))
        return await receive(ws)


async def receive(ws, messageType: str | None = None) -> dict:
    while True:
        message = json.loads(await asyncio.wait_for(ws.recv(), 2))
        if messageType is None or message["type"] == messageType:
            return message


async def waitClosed(ws) -> None:
    with pytest.raises(ConnectionClosed):
        while True:
            await asyncio.wait_for(ws.recv(), 2)


@pytest.fixture
async def browser(monkeypatch, tmp_path):
    async for harness in startBrowser(monkeypatch, tmp_path, loadCrx=None):
        yield harness


async def startBrowser(monkeypatch, tmp_path, loadCrx):
    monkeypatch.setattr(cfg, "set", lambda item, value, save=True: monkeypatch.setattr(item, "value", value))
    monkeypatch.setattr(cfg.browserExtensionPairToken, "value", TOKEN)
    monkeypatch.setattr(cfg.shouldDraftTakenDownload, "value", False)
    monkeypatch.setattr(cfg.downloadFolder, "value", str(tmp_path))
    loop = asyncio.get_running_loop()
    runner = CoroutineRunner(loop.call_soon, loop=loop)
    taskService = FakeTaskService()
    speedChanged = BoundSignal()
    drafted, events = [], []

    async def parse(options):
        if "fail" in options.url:
            raise ValueError("unreachable")
        return Task(name="video.mp4", url=options.url, packId="http_pack", outputFolder=options.outputFolder)

    service = BrowserService(runner, taskService, speedChanged, parse=parse, loadCrx=loadCrx)
    service.taskDraftRequested.connect(drafted.extend)
    service.extensionUpdated.connect(lambda version: events.append(("extensionUpdated", version)))
    service.connectionChanged.connect(lambda: events.append("connectionChanged"))
    service.protocolMismatched.connect(lambda: events.append("protocolMismatched"))
    service.pairRequestChanged.connect(lambda request: events.append(request))
    server = LoopbackServer(runner, service.handle, isEnabled=FakeItem(True), port=FakeItem(findFreePort()))
    server.start()
    await waitFor(lambda: server.state.status == ListenStatus.LISTENING)

    yield Harness(service, server, taskService, speedChanged, drafted, events)

    server.stop()
    await asyncio.sleep(0.05)


class TestHello:
    async def test_right_token_is_acknowledged(self, browser):
        async with browser.connect() as ws:
            ack = await browser.hello(ws)
            await waitFor(lambda: "connectionChanged" in browser.events)
            assert browser.service.connectionSummary == ("normal", "2.2.0")

        assert ack["type"] == "hello_ack"
        assert ack["protocolVersion"] == PROTOCOL_VERSION
        assert ack["appVersion"] == VERSION

    async def test_wrong_token_is_rejected_and_closed(self, browser):
        async with browser.connect() as ws:
            error = await browser.hello(ws, token="guess")
            await waitClosed(ws)

        assert error == {"type": "error", "message": "配对令牌无效", "code": "unauthorized"}

    async def test_protocol_mismatch_is_reported(self, browser):
        async with browser.connect() as ws:
            error = await browser.hello(ws, protocolVersion=1)
            await waitClosed(ws)

        assert error["code"] == "protocol_mismatch"
        assert "protocolMismatched" in browser.events

    async def test_request_before_hello_is_rejected_and_closed(self, browser):
        async with browser.connect() as ws:
            await ws.send(json.dumps({"type": "subscribe_tasks"}))
            error = await receive(ws)
            await waitClosed(ws)

        assert error["code"] == "unauthorized"

    async def test_disconnect_updates_connection_summary(self, browser):
        async with browser.connect() as ws:
            await browser.hello(ws)
        await waitFor(lambda: browser.service.connectionSummary == ("", ""))


class TestPairing:
    async def requestPair(self, ws, requestId: str) -> None:
        await ws.send(json.dumps({"type": "pair_request", "requestId": requestId, "protocolVersion": PROTOCOL_VERSION,
                                  "extensionVersion": "2.2.0", "clientKind": "chrome"}))

    async def test_approved_pair_request_returns_token(self, browser):
        async with browser.connect() as ws:
            await self.requestPair(ws, "p1")
            await waitFor(lambda: browser.service.pairRequest is not None)
            request = browser.service.pairRequest
            browser.service.approvePair("p1")
            result = await receive(ws, "pair_result")

        assert isinstance(request, PairRequest)
        assert (request.requestId, request.extensionVersion, request.clientKind) == ("p1", "2.2.0", "chrome")
        assert request.peerAddress.startswith("127.0.0.1:")
        assert result == {"type": "pair_result", "requestId": "p1", "ok": True, "token": TOKEN, "message": "配对成功"}
        assert browser.service.pairRequest is None
        assert browser.events[-1] is None

    async def test_rejected_pair_request(self, browser):
        async with browser.connect() as ws:
            await self.requestPair(ws, "p1")
            await waitFor(lambda: browser.service.pairRequest is not None)
            browser.service.rejectPair("p1")
            result = await receive(ws, "pair_result")

        assert result["ok"] is False
        assert "token" not in result

    async def test_second_client_is_turned_away_while_one_is_pending(self, browser):
        async with browser.connect() as first, browser.connect() as second:
            await self.requestPair(first, "p1")
            await waitFor(lambda: browser.service.pairRequest is not None)
            await self.requestPair(second, "p2")
            result = await receive(second, "pair_result")

            assert result == {"type": "pair_result", "requestId": "p2", "ok": False, "message": "已有配对请求待处理"}
            assert browser.service.pairRequest.requestId == "p1"

    async def test_same_client_retrying_replaces_its_request(self, browser):
        async with browser.connect() as ws:
            await self.requestPair(ws, "p1")
            await waitFor(lambda: browser.service.pairRequest is not None)
            await self.requestPair(ws, "p2")
            await waitFor(lambda: browser.service.pairRequest.requestId == "p2")

            browser.service.approvePair("p1")
            browser.service.approvePair("p2")
            result = await receive(ws, "pair_result")

        assert result["requestId"] == "p2"

    async def test_pending_request_is_withdrawn_when_client_leaves(self, browser):
        async with browser.connect() as ws:
            await self.requestPair(ws, "p1")
            await waitFor(lambda: browser.service.pairRequest is not None)
        await waitFor(lambda: browser.service.pairRequest is None)

        browser.service.approvePair("p1")
        assert browser.events[-1] is None


class TestToken:
    async def test_empty_token_is_generated_at_construction(self, monkeypatch):
        monkeypatch.setattr(cfg, "set", lambda item, value, save=True: monkeypatch.setattr(item, "value", value))
        monkeypatch.setattr(cfg.browserExtensionPairToken, "value", "")
        loop = asyncio.get_running_loop()

        BrowserService(CoroutineRunner(loop.call_soon, loop=loop), FakeTaskService(), BoundSignal(), parse=None, loadCrx=None)

        assert len(cfg.browserExtensionPairToken.value) >= 16

    async def test_regenerating_token_closes_sessions(self, browser):
        async with browser.connect() as ws:
            await browser.hello(ws)
            token = browser.service.regenerateToken()
            await waitClosed(ws)

        assert token != TOKEN
        assert cfg.browserExtensionPairToken.value == token


class TestCreateTask:
    async def create(self, browser, **fields) -> dict:
        async with browser.connect() as ws:
            await browser.hello(ws)
            await ws.send(json.dumps({"type": "create_task", "requestId": "c1", **fields}))
            return await receive(ws, "create_task_result")

    async def test_download_is_added(self, browser, tmp_path):
        result = await self.create(browser, source="download", title="Clip",
                                   payload={"url": "https://a.test/v", "path": str(tmp_path / "out")})

        task = browser.taskService.tasks[0]
        assert result == {"type": "create_task_result", "requestId": "c1", "status": "created", "taskId": task.taskId}
        assert task.name == "Clip.mp4"
        assert task.outputFolder == tmp_path / "out"

    async def test_decryption_keys_reach_the_hls_step(self, browser, monkeypatch):
        from m3u8_pack.task import M3U8Task, M3U8TaskStep

        async def parse(options):
            return M3U8Task(name="live.mp4", url=options.url, steps=[M3U8TaskStep(stepIndex=0)])

        monkeypatch.setattr(browser.service, "_parse", parse)
        result = await self.create(browser, source="page_media", payload={
            "url": "https://a.test/master.m3u8", "decryptionKeys": ["kid:key"]})

        assert result["status"] == "created"
        assert browser.taskService.tasks[0].steps[0].decryptionKeys == ["kid:key"]

    async def test_explicit_draft_overrides_setting(self, browser):
        result = await self.create(browser, source="download", draft=True, payload={"url": "https://a.test/v"})

        assert result["status"] == "drafted"
        assert browser.taskService.tasks == []
        assert browser.drafted[0].url == "https://a.test/v"

    async def test_name_conflict_left_to_user_is_drafted(self, browser):
        browser.taskService.isNameConflictAsked = True

        result = await self.create(browser, source="download", payload={"url": "https://a.test/v"})

        assert result["status"] == "drafted"
        assert browser.taskService.tasks == []

    async def test_parse_failure_is_rejected(self, browser):
        result = await self.create(browser, source="download", payload={"url": "https://fail.test/v"})

        assert result["status"] == "rejected"
        assert result["message"] == "unreachable"

    async def test_unknown_source_is_an_error(self, browser):
        async with browser.connect() as ws:
            await browser.hello(ws)
            await ws.send(json.dumps({"type": "create_task", "requestId": "c1", "source": "nope", "payload": {}}))
            error = await receive(ws, "error")

        assert error["message"] == "未知的任务来源"


class TestSnapshots:
    @staticmethod
    def makeTask(name: str, tmp_path) -> Task:
        return Task(name=name, url=f"https://a.test/{name}", packId="http_pack", outputFolder=tmp_path)

    @staticmethod
    async def subscribe(browser, ws) -> dict:
        await browser.hello(ws)
        await ws.send(json.dumps({"type": "subscribe_tasks"}))
        return await receive(ws, "task_snapshot")

    @staticmethod
    async def assertNothingSent(ws) -> None:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(ws.recv(), 0.3)

    async def test_subscriber_gets_snapshot_at_once(self, browser, tmp_path):
        browser.taskService.add(self.makeTask("a.bin", tmp_path))
        async with browser.connect() as ws:
            first = await self.subscribe(browser, ws)

        assert [t["name"] for t in first["tasks"]] == ["a.bin"]

    async def test_task_change_sends_snapshot(self, browser, tmp_path):
        browser.taskService.add(self.makeTask("a.bin", tmp_path))
        async with browser.connect() as ws:
            await self.subscribe(browser, ws)
            browser.taskService.add(self.makeTask("b.bin", tmp_path))
            second = await receive(ws, "task_snapshot")

        assert sorted(t["name"] for t in second["tasks"]) == ["a.bin", "b.bin"]

    async def test_tick_sends_changed_snapshot(self, browser, tmp_path):
        task = self.makeTask("a.bin", tmp_path)
        browser.taskService.add(task)
        async with browser.connect() as ws:
            await self.subscribe(browser, ws)
            task.setName("c.bin")
            browser.speedChanged.emit(0)
            second = await receive(ws, "task_snapshot")

        assert [t["name"] for t in second["tasks"]] == ["c.bin"]

    async def test_tick_without_change_sends_nothing(self, browser, tmp_path):
        browser.taskService.add(self.makeTask("a.bin", tmp_path))
        async with browser.connect() as ws:
            await self.subscribe(browser, ws)
            browser.speedChanged.emit(0)
            await self.assertNothingSent(ws)

    async def test_burst_of_changes_sends_one_snapshot(self, browser, tmp_path):
        async with browser.connect() as ws:
            await self.subscribe(browser, ws)
            for i in range(10):
                browser.taskService.add(self.makeTask(f"{i}.bin", tmp_path))
            second = await receive(ws, "task_snapshot")
            await self.assertNothingSent(ws)

        assert len(second["tasks"]) == 10


class TestTaskAction:
    @pytest.fixture
    def task(self, browser, tmp_path) -> Task:
        task = Task(name="a.bin", url="https://a.test/a", packId="http_pack", outputFolder=tmp_path)
        browser.taskService.add(task)
        return task

    async def act(self, browser, taskId: str, action: str) -> dict:
        async with browser.connect() as ws:
            await browser.hello(ws)
            await ws.send(json.dumps({"type": "task_action", "requestId": "t1", "taskId": taskId, "action": action}))
            return await receive(ws, "task_action_result")

    @pytest.mark.parametrize("status, call", [
        (TaskStatus.RUNNING, "pause"),
        (TaskStatus.PAUSED, "start"),
        (TaskStatus.FAILED, "start"),
    ])
    async def test_toggle_pause(self, browser, task, status, call):
        task.status = status
        result = await self.act(browser, task.taskId, "toggle_pause")

        assert result["ok"] is True
        assert browser.taskService.calls == [(call, task.taskId)]

    async def test_toggle_pause_on_completed_task_is_refused(self, browser, task):
        task.status = TaskStatus.COMPLETED
        result = await self.act(browser, task.taskId, "toggle_pause")

        assert result == {"type": "task_action_result", "requestId": "t1", "ok": False, "message": "任务已完成"}

    @pytest.mark.parametrize("action, shouldDeleteFiles", [("cancel", True), ("remove", False)])
    async def test_cancel_deletes_files_but_remove_keeps_them(self, browser, task, action, shouldDeleteFiles):
        await self.act(browser, task.taskId, action)

        assert browser.taskService.calls == [("delete", task.taskId, shouldDeleteFiles)]

    async def test_missing_task(self, browser):
        result = await self.act(browser, "tsk_missing", "redownload")

        assert result["message"] == "任务不存在"

    async def test_unknown_action(self, browser, task):
        result = await self.act(browser, task.taskId, "explode")

        assert result["message"] == "不支持的操作"


async def test_stopping_server_disconnects_extension(browser):
    async with browser.connect() as ws:
        await browser.hello(ws)
        await waitFor(lambda: browser.service.connectionSummary != ("", ""))
        browser.server.stop()
        await waitClosed(ws)
    await waitFor(lambda: browser.service.connectionSummary == ("", ""))


def buildCrx(files: dict[str, str]) -> bytes:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    header = b"signed-header"
    return b"Cr24" + struct.pack("<II", 3, len(header)) + header + archive.getvalue()


class TestExtensionInstall:
    async def test_crx_is_unpacked_into_folder(self, tmp_path):
        folder = await installExtension(buildCrx({"manifest.json": "{}", "js/background.js": "run()"}), tmp_path / "ext")

        assert (folder / "manifest.json").read_text() == "{}"
        assert (folder / "js/background.js").read_text() == "run()"

    async def test_outdated_development_extension_is_updated_and_reloaded(self, monkeypatch, tmp_path):
        monkeypatch.setattr(browser_service, "EXTENSION_UNPACK_DIR", tmp_path / "ext")
        crx = buildCrx({"manifest.json": "{}"})
        async for browser in startBrowser(monkeypatch, tmp_path, loadCrx=lambda: crx):
            async with browser.connect() as ws:
                await self.helloFromOldDevelopmentBuild(ws)
                reload = await receive(ws, "reload")

            assert reload == {"type": "reload"}
            assert (tmp_path / "ext/manifest.json").exists()
            assert ("extensionUpdated", LATEST_EXTENSION_VERSION) in browser.events

    async def test_no_update_without_bundled_extension(self, browser):
        async with browser.connect() as ws:
            await self.helloFromOldDevelopmentBuild(ws)
            await ws.send(json.dumps({"type": "subscribe_tasks"}))
            snapshot = await receive(ws)

        assert snapshot["type"] == "task_snapshot"
        assert not any(isinstance(e, tuple) and e[0] == "extensionUpdated" for e in browser.events)

    @staticmethod
    async def helloFromOldDevelopmentBuild(ws) -> None:
        await ws.send(json.dumps({"type": "hello", "protocolVersion": PROTOCOL_VERSION, "token": TOKEN,
                                  "extensionVersion": "0.0.1", "installType": "development"}))
        assert (await receive(ws))["type"] == "hello_ack"
