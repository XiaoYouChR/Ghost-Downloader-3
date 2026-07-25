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
