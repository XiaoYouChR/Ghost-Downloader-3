"""Aria2RpcServer 的回调与 tellStatus 测试。

覆盖 #645 回归（解析失败回调收到多余 kwargs 导致 TypeError）。
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import pytest

from app.models.task import Task, TaskStep, TaskStatus
from app.services.aria2_rpc import Aria2RpcServer


# ── Stubs ──


@dataclass(kw_only=True)
class StubStep(TaskStep):
    stepIndex: int = 0

    async def run(self, reportSpeed, waitForSpeedLimit):
        pass


class StubCoroutineRunner:
    """捕获 submit 的回调，由测试手动触发 done/failed。"""

    def __init__(self):
        self.done = None
        self.failed = None
        self.kwargs = {}

    def submit(self, work, done=None, failed=None, **kwargs) -> str:
        if asyncio.iscoroutine(work):
            work.close()  # 不真正执行，避免未 await 警告
        self.done = done
        self.failed = failed
        self.kwargs = kwargs
        return "wrk_1"


class StubSocket:
    def __init__(self):
        self.written = b""

    def write(self, data: bytes):
        self.written += data

    def flush(self):
        pass

    def disconnectFromHost(self):
        pass

    def response(self) -> dict:
        body = self.written.split(b"\r\n\r\n", 1)[1]
        return json.loads(body)


# ── Fixtures ──


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def server(qapp, monkeypatch, tmp_path):
    from app.config.cfg import cfg
    monkeypatch.setattr(cfg.aria2RpcToken, "value", "")
    monkeypatch.setattr(cfg.downloadFolder, "value", str(tmp_path))
    monkeypatch.setattr(cfg.aria2RpcEmulateFingerprint, "value", False)
    monkeypatch.setattr(cfg.shouldDraftTakenDownload, "value", False)

    runner = StubCoroutineRunner()
    added: list[Task] = []

    async def parse(taskOptions):
        raise AssertionError("测试不应真正执行 parse")

    srv = Aria2RpcServer(runner, parse, added.append)
    return srv, runner, added


def makeTask(name: str = "test.zip") -> Task:
    step = StubStep(stepIndex=0)
    task = Task(name=name, url="http://test/file.zip", packId="http", steps=[step])
    step._bindTask(task)
    return task


def addUri(srv, options: dict | None = None, rpcId: int = 1) -> tuple[str, StubSocket]:
    socket = StubSocket()
    params: list = [["http://test/file.zip"]]
    if options is not None:
        params.append(options)
    srv._dispatchRpc(socket, json.dumps({
        "jsonrpc": "2.0", "id": rpcId, "method": "aria2.addUri", "params": params,
    }).encode())
    return socket.response()["result"], socket


# ── #645: 解析失败回调 TypeError ──


class TestParseCallbackBinding:
    def test_filename_not_passed_as_submit_kwarg(self, server):
        srv, runner, _ = server
        addUri(srv, options={"out": "name.zip"})
        # CoroutineRunner 会把 kwargs 同时透传给 done 和 failed，
        # filename 只能绑定在 done 上（#645）
        assert "filename" not in runner.kwargs

    def test_failed_callback_accepts_error_only(self, server):
        srv, runner, _ = server
        addUri(srv, options={"out": "name.zip"})
        runner.failed("boom")  # 不应 TypeError

    def test_done_callback_applies_filename_and_adds_task(self, server):
        srv, runner, added = server
        addUri(srv, options={"out": "renamed.zip"})
        task = makeTask()
        runner.done(task)
        assert task.name == "renamed.zip"
        assert added == [task]


# ── aria2.tellStatus ──


def tellStatus(srv, gid: str, rpcId: int = 2) -> dict:
    socket = StubSocket()
    srv._dispatchRpc(socket, json.dumps({
        "jsonrpc": "2.0", "id": rpcId, "method": "aria2.tellStatus", "params": [gid],
    }).encode())
    return socket.response()


class TestTellStatus:
    def test_parse_pending_is_waiting(self, server):
        srv, _, _ = server
        gid, _ = addUri(srv)
        result = tellStatus(srv, gid)["result"]
        assert result["gid"] == gid
        assert result["status"] == "waiting"
        assert result["totalLength"] == "0"
        assert result["completedLength"] == "0"
        assert result["downloadSpeed"] == "0"

    def test_running_task_is_active(self, server, tmp_path):
        srv, runner, _ = server
        gid, _ = addUri(srv)
        task = makeTask()
        task.outputFolder = tmp_path
        task.fileSize = 200
        step = task.steps[0]
        step.status = TaskStatus.RUNNING
        step.speed = 100
        step.receivedBytes = 50
        task.updateStatus()
        runner.done(task)

        result = tellStatus(srv, gid)["result"]
        assert result["status"] == "active"
        assert result["totalLength"] == "200"
        assert result["completedLength"] == "50"
        assert result["downloadSpeed"] == "100"
        assert result["files"] == [{
            "index": "1",
            "path": str(tmp_path / "test.zip"),
            "length": "200",
            "completedLength": "50",
        }]

    def test_sentinel_file_size_reports_zero_total(self, server):
        srv, runner, _ = server
        gid, _ = addUri(srv)
        task = makeTask()
        task.fileSize = -1  # SpecialFileSize.NOT_SUPPORTED
        step = task.steps[0]
        step.status = TaskStatus.RUNNING
        task.updateStatus()
        runner.done(task)

        result = tellStatus(srv, gid)["result"]
        assert result["totalLength"] == "0"
        assert result["files"][0]["length"] == "0"

    def test_completed_task_is_complete(self, server):
        srv, runner, _ = server
        gid, _ = addUri(srv)
        task = makeTask()
        task.fileSize = 200
        step = task.steps[0]
        step.receivedBytes = 200
        step.setStatus(TaskStatus.COMPLETED)
        runner.done(task)

        result = tellStatus(srv, gid)["result"]
        assert result["status"] == "complete"
        assert result["completedLength"] == "200"
        assert result["downloadSpeed"] == "0"

    def test_parse_failure_is_error_with_message(self, server):
        srv, runner, _ = server
        gid, _ = addUri(srv)
        runner.failed("no parser matched")

        result = tellStatus(srv, gid)["result"]
        assert result["status"] == "error"
        assert result["errorMessage"] == "no parser matched"

    def test_all_values_are_strings(self, server):
        srv, runner, _ = server
        gid, _ = addUri(srv)
        task = makeTask()
        task.fileSize = 200
        step = task.steps[0]
        step.status = TaskStatus.RUNNING
        step.speed = 100
        step.receivedBytes = 50
        task.updateStatus()
        runner.done(task)

        result = tellStatus(srv, gid)["result"]
        for key in ("gid", "status", "totalLength", "completedLength", "downloadSpeed"):
            assert isinstance(result[key], str), key
        for key in ("index", "path", "length", "completedLength"):
            assert isinstance(result["files"][0][key], str), key

    def test_unknown_gid_error(self, server):
        srv, _, _ = server
        response = tellStatus(srv, "deadbeef")
        assert response["error"]["code"] == 1
        assert response["error"]["message"] == "No such download for GID#deadbeef"
