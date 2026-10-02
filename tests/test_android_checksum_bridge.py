"""Bridge 的 Checksum 投影：比对、算法分组、进度 tick 启停、notice。

Seam: Bridge 方法与槽（StubTaskService，真实 CoroutineRunner + loop 线程）
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.checksum import COMMON_ALGORITHMS
from app.models.task import TaskError
from tests.test_android_request import engine  # noqa: F401
from tests.test_android_task_push import stubPushes, waitForLoop


@dataclass
class StubTask:
    taskId: str
    name: str = "ubuntu.iso"
    checksums: dict[str, str] = field(default_factory=dict)


class StubTaskService:
    def __init__(self, tasks):
        self.tasks = tasks
        self.progress: dict[str, int] = {}

    def taskById(self, taskId):
        return next((t for t in self.tasks if t.taskId == taskId), None)

    def checksumProgress(self, task):
        return self.progress.get(task.taskId)


def setUp(engine, *tasks):
    stubPushes(engine)
    engine._checksumTickWorkId = None
    engine._taskService = StubTaskService(list(tasks))
    return engine._taskService


def notices(engine) -> list[dict]:
    return [json.loads(value) for key, value in engine._flows.events if key == "notice"]


def test_match_accepts_sha256sum_line(engine):
    setUp(engine, StubTask("t1", checksums={"md5": "aa11", "sha256": "bb22"}))

    assert json.loads(engine.request("matchChecksum", "t1", "BB22  ubuntu.iso")) == "sha256"
    assert json.loads(engine.request("matchChecksum", "t1", "cc33")) is None


def test_algorithms_are_grouped_by_engine(engine):
    groups = json.loads(engine.request("checksumAlgorithms"))

    assert groups["common"] == list(COMMON_ALGORITHMS)
    assert not set(groups["common"]) & set(groups["others"])


def test_tick_runs_until_the_last_checksum_ends(engine):
    a, b = StubTask("a"), StubTask("b")
    service = setUp(engine, a, b)

    service.progress = {"a": 0, "b": 0}
    engine.request("_onChecksumStarted", a)
    engine.request("_onChecksumStarted", b)
    tickId = engine._checksumTickWorkId

    del service.progress["a"]
    engine.request("_onChecksumCompleted", a, "sha256")
    assert engine._checksumTickWorkId == tickId

    del service.progress["b"]
    engine.request("_onChecksumStopped", b, None)
    assert engine._checksumTickWorkId is None


def test_completed_checksum_sends_notice_with_algorithm(engine):
    task = StubTask("t1")
    setUp(engine, task)

    engine.request("_onChecksumCompleted", task, "sha256")
    waitForLoop(engine)

    assert notices(engine) == [
        {"kind": "checksumCompleted", "taskId": "t1", "name": "ubuntu.iso", "algorithm": "sha256"}]


def test_failed_checksum_notice_carries_error_as_fields(engine):
    task = StubTask("t1")
    setUp(engine, task)

    engine.request("_onChecksumStopped", task, TaskError("无法读取文件：{detail}", detail="gone"))
    engine.request("_onChecksumStopped", task, None)
    waitForLoop(engine)

    [notice] = notices(engine)
    assert notice["kind"] == "checksumFailed"
    assert notice["params"] == {"detail": "gone"}
