from __future__ import annotations

import asyncio
import json

import pytest
import websockets
from websockets.protocol import State

from app.config.cfg import cfg
from app.config.constants import LATEST_EXTENSION_VERSION, VERSION
from app.config.paths import APP_DATA_DIR
from app.models.task import Task, TaskStatus
from app.services.browser_service import PROTOCOL_VERSION, PairRequest
from app.services.port_listener import ListenStatus
from app.services.task_service import NameConflictChoice
from tests.conftest import FakeStep
from tests.helpers import probeFreePort, waitUntil

TOKEN = "pair-token"


class Browser:
    def __init__(self, engine):
        self.engine = engine
        self.service = engine.browserService
        self.events = []
        self.drafted = []
        self.service.taskDraftRequested.connect(self.drafted.extend)
        self.service.extensionUpdated.connect(lambda version: self.events.append(("extensionUpdated", version)))
        self.service.connectionChanged.connect(lambda: self.events.append("connectionChanged"))
        self.service.protocolMismatched.connect(lambda: self.events.append("protocolMismatched"))
        self.service.pairRequestChanged.connect(self.events.append)

    def open(self):
        return websockets.connect(f"ws://127.0.0.1:{self.engine.browserListener.state.port}/")

    async def requestHello(self, ws, token: str = TOKEN, protocolVersion: int = PROTOCOL_VERSION,
                    extensionVersion: str = "2.2.0", installType: str = "normal") -> dict:
        await ws.send(json.dumps({"type": "hello", "protocolVersion": protocolVersion, "token": token,
                                  "extensionVersion": extensionVersion, "installType": installType}))
        return await receive(ws)


async def receive(ws, messageType: str | None = None) -> dict:
    while True:
        message = json.loads(await asyncio.wait_for(ws.recv(), 3))
        if messageType is None or message["type"] == messageType:
            return message






@pytest.fixture
async def browser(engine):
    cfg.set(cfg.browserExtensionPairToken, TOKEN)
    cfg.set(cfg.browserExtensionPort, probeFreePort())
    await asyncio.sleep(0.05)
    cfg.set(cfg.isBrowserExtensionEnabled, True)
    await waitUntil(lambda: engine.browserListener.state.status == ListenStatus.LISTENING)
    return Browser(engine)


def buildTask(name: str = "a.bin", outcome: str = "hang") -> Task:
    return Task(name=name, url=f"http://test/{name}", packId="test", steps=[FakeStep(stepIndex=0, outcome=outcome)])


async def test_open_with_right_token(browser):
    async with browser.open() as ws:
        ack = await browser.requestHello(ws)
        await waitUntil(lambda: "connectionChanged" in browser.events)
        assert browser.service.connectionSummary == ("normal", "2.2.0")

    assert (ack["type"], ack["protocolVersion"], ack["appVersion"]) == ("hello_ack", PROTOCOL_VERSION, VERSION)


async def test_open_with_wrong_token_is_refused(browser):
    async with browser.open() as ws:
        error = await browser.requestHello(ws, token="guess")
        await waitUntil(lambda: ws.state is State.CLOSED)

    assert error == {"type": "error", "message": "配对令牌无效", "code": "unauthorized"}


async def test_open_with_old_protocol_is_reported(browser):
    async with browser.open() as ws:
        error = await browser.requestHello(ws, protocolVersion=1)
        await waitUntil(lambda: ws.state is State.CLOSED)

    assert error["code"] == "protocol_mismatch"
    assert "protocolMismatched" in browser.events


async def test_request_before_hello_is_refused(browser):
    async with browser.open() as ws:
        await ws.send(json.dumps({"type": "subscribe_tasks"}))
        error = await receive(ws)
        await waitUntil(lambda: ws.state is State.CLOSED)

    assert error["code"] == "unauthorized"


async def test_close_updates_connection_state(browser):
    async with browser.open() as ws:
        await browser.requestHello(ws)
    await waitUntil(lambda: browser.service.connectionSummary == ("", ""))


async def requestPair(ws, requestId: str) -> None:
    await ws.send(json.dumps({"type": "pair_request", "requestId": requestId, "protocolVersion": PROTOCOL_VERSION,
                              "extensionVersion": "2.2.0", "clientKind": "chrome"}))


async def test_request_pair_approved_gets_token(browser):
    async with browser.open() as ws:
        await requestPair(ws, "p1")
        await waitUntil(lambda: browser.service.pairRequest is not None)
        request = browser.service.pairRequest
        browser.service.approvePair("p1")
        result = await receive(ws, "pair_result")

    assert isinstance(request, PairRequest)
    assert (request.requestId, request.extensionVersion, request.clientKind) == ("p1", "2.2.0", "chrome")
    assert request.peerAddress.startswith("127.0.0.1:")
    assert result == {"type": "pair_result", "requestId": "p1", "ok": True, "token": TOKEN, "message": "配对成功"}
    assert browser.service.pairRequest is None
    assert browser.events[-1] is None


async def test_request_pair_rejected(browser):
    async with browser.open() as ws:
        await requestPair(ws, "p1")
        await waitUntil(lambda: browser.service.pairRequest is not None)
        browser.service.rejectPair("p1")
        result = await receive(ws, "pair_result")

    assert result["ok"] is False
    assert "token" not in result


async def test_request_pair_refused_while_one_is_pending(browser):
    async with browser.open() as first, browser.open() as second:
        await requestPair(first, "p1")
        await waitUntil(lambda: browser.service.pairRequest is not None)
        await requestPair(second, "p2")
        result = await receive(second, "pair_result")

        assert result == {"type": "pair_result", "requestId": "p2", "ok": False, "message": "已有配对请求待处理"}
        assert browser.service.pairRequest.requestId == "p1"


async def test_request_pair_again_replaces_request(browser):
    async with browser.open() as ws:
        await requestPair(ws, "p1")
        await waitUntil(lambda: browser.service.pairRequest is not None)
        await requestPair(ws, "p2")
        await waitUntil(lambda: browser.service.pairRequest.requestId == "p2")

        browser.service.approvePair("p1")
        browser.service.approvePair("p2")
        result = await receive(ws, "pair_result")

    assert result["requestId"] == "p2"


async def test_close_withdraws_pending_pair_request(browser):
    async with browser.open() as ws:
        await requestPair(ws, "p1")
        await waitUntil(lambda: browser.service.pairRequest is not None)
    await waitUntil(lambda: browser.service.pairRequest is None)

    browser.service.approvePair("p1")
    assert browser.events[-1] is None


def test_start_creates_token(engine):
    assert len(cfg.browserExtensionPairToken.value) >= 16


async def test_set_new_token_disconnects_clients(browser):
    async with browser.open() as ws:
        await browser.requestHello(ws)
        token = browser.service.regenerateToken()
        await waitUntil(lambda: ws.state is State.CLOSED)

    assert token != TOKEN
    assert cfg.browserExtensionPairToken.value == token


async def createTask(browser, **fields) -> dict:
    async with browser.open() as ws:
        await browser.requestHello(ws)
        await ws.send(json.dumps({"type": "create_task", "requestId": "c1", **fields}))
        return await receive(ws, "create_task_result")


async def test_add_task(browser, downloadFolder):
    result = await createTask(browser, source="download", title="Clip",
                               payload={"url": "http://test/v.mp4", "path": str(downloadFolder / "out")})

    [task] = browser.engine.taskService.tasks
    assert result == {"type": "create_task_result", "requestId": "c1", "status": "created", "taskId": task.taskId}
    assert (task.name, task.outputFolder) == ("Clip.mp4", downloadFolder / "out")


async def test_add_task_with_decryption_keys(browser):
    result = await createTask(browser, source="page_media", payload={
        "url": "http://test/master.m3u8", "decryptionKeys": ["kid:key"]})

    assert result["status"] == "created"
    assert browser.engine.taskService.tasks[0].steps[0].options["decryptionKeys"] == ["kid:key"]


async def test_add_draft_overrides_setting(browser):
    result = await createTask(browser, source="download", draft=True, payload={"url": "http://test/v.mp4"})

    assert result["status"] == "drafted"
    assert browser.engine.taskService.tasks == []
    assert browser.drafted[0].url == "http://test/v.mp4"


async def test_add_drafts_name_conflict_left_to_user(browser, downloadFolder):
    cfg.set(cfg.nameConflict, NameConflictChoice.ASK.value)
    (downloadFolder / "v.mp4").write_bytes(b"mine")

    result = await createTask(browser, source="download", payload={"url": "http://test/v.mp4"})

    assert result["status"] == "drafted"
    assert browser.engine.taskService.tasks == []


async def test_add_reports_parse_failure(browser):
    browser.engine.featureService.packById("test").failingUrls.add("http://test/v.mp4")

    result = await createTask(browser, source="download", payload={"url": "http://test/v.mp4"})

    assert (result["status"], result["message"]) == ("rejected", "network error")


async def requestSnapshot(browser, ws) -> dict:
    await browser.requestHello(ws)
    await ws.send(json.dumps({"type": "subscribe_tasks"}))
    return await receive(ws, "task_snapshot")


async def test_request_snapshot_at_once(browser):
    browser.engine.taskService.add(buildTask(), autoStart=False)
    async with browser.open() as ws:
        first = await requestSnapshot(browser, ws)

    assert [task["name"] for task in first["tasks"]] == ["a.bin"]


async def test_add_sends_snapshot(browser):
    browser.engine.taskService.add(buildTask("a.bin"), autoStart=False)
    async with browser.open() as ws:
        await requestSnapshot(browser, ws)
        browser.engine.taskService.add(buildTask("b.bin"), autoStart=False)
        second = await receive(ws, "task_snapshot")

    assert sorted(task["name"] for task in second["tasks"]) == ["a.bin", "b.bin"]


async def test_run_sends_change_on_next_tick(browser):
    task = buildTask()
    browser.engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.RUNNING)
    async with browser.open() as ws:
        await requestSnapshot(browser, ws)
        task.setName("c.bin")
        second = await receive(ws, "task_snapshot")

    assert [task["name"] for task in second["tasks"]] == ["c.bin"]


async def test_run_sends_one_snapshot_for_burst(browser):
    async with browser.open() as ws:
        await requestSnapshot(browser, ws)
        for index in range(10):
            browser.engine.taskService.add(buildTask(f"{index}.bin"), autoStart=False)
        second = await receive(ws, "task_snapshot")
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(ws.recv(), 0.3)

    assert len(second["tasks"]) == 10


async def requestAction(browser, taskId: str, action: str) -> dict:
    async with browser.open() as ws:
        await browser.requestHello(ws)
        await ws.send(json.dumps({"type": "task_action", "requestId": "t1", "taskId": taskId, "action": action}))
        return await receive(ws, "task_action_result")


async def test_request_toggle_pauses_running_task(browser):
    task = buildTask()
    browser.engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.RUNNING)

    assert (await requestAction(browser, task.taskId, "toggle_pause"))["ok"] is True
    assert task.status == TaskStatus.PAUSED


@pytest.mark.parametrize("outcome, status", [("hang", TaskStatus.PAUSED), ("fail", TaskStatus.FAILED)])
async def test_request_toggle_starts_paused_or_failed_task(browser, outcome, status):
    task = buildTask(outcome=outcome)
    browser.engine.taskService.add(task)
    if status == TaskStatus.PAUSED:
        browser.engine.taskService.pause(task)
    await waitUntil(lambda: task.status == status)
    task.steps[0].outcome = "hang"

    assert (await requestAction(browser, task.taskId, "toggle_pause"))["ok"] is True
    await waitUntil(lambda: task.status == TaskStatus.RUNNING)


async def test_request_toggle_on_finished_task_is_refused(browser):
    task = buildTask(outcome="complete")
    browser.engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)

    result = await requestAction(browser, task.taskId, "toggle_pause")

    assert result == {"type": "task_action_result", "requestId": "t1", "ok": False, "message": "任务已完成"}


@pytest.mark.parametrize("action, isProductKept", [("cancel", False), ("remove", True)])
async def test_cancel_deletes_files_but_remove_keeps_them(browser, downloadFolder, action, isProductKept):
    task = buildTask(outcome="complete")
    browser.engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)

    await requestAction(browser, task.taskId, action)

    await waitUntil(lambda: browser.engine.taskService.taskById(task.taskId) is None)
    assert (downloadFolder / "a.bin").exists() == isProductKept


async def test_request_action_on_missing_task_fails(browser):
    result = await requestAction(browser, "tsk_missing", "redownload")

    assert result["message"] == "任务不存在"


class TestDisabling:
    @pytest.fixture(params=["desktop", "android"])
    def engine(self, request, startEngine):
        return startEngine(request.param)

    async def test_stop_disconnects_extension(self, browser):
        async with browser.open() as ws:
            await browser.requestHello(ws)
            await waitUntil(lambda: browser.service.connectionSummary != ("", ""))
            cfg.set(cfg.isBrowserExtensionEnabled, False)
            await waitUntil(lambda: ws.state is State.CLOSED)
        await waitUntil(lambda: browser.service.connectionSummary == ("", ""))


async def test_install_unpacks_extension(engine):
    folders = []

    engine.coroutineRunner.submit(engine.browserService.install(), done=folders.append)

    await waitUntil(lambda: folders == [APP_DATA_DIR / "browser_extension"])
    assert (folders[0] / "manifest.json").is_file()


async def test_install_updates_outdated_dev_extension(browser):
    async with browser.open() as ws:
        assert (await browser.requestHello(ws, extensionVersion="0.0.1", installType="development"))["type"] == "hello_ack"
        reload = await receive(ws, "reload")

    assert reload == {"type": "reload"}
    assert (APP_DATA_DIR / "browser_extension" / "manifest.json").exists()
    assert ("extensionUpdated", LATEST_EXTENSION_VERSION) in browser.events
