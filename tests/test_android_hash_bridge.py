from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Thread

import pytest

from app.services.coroutine_runner import CoroutineRunner
from tests.helpers import StubFlows


@dataclass
class StubTask:
    taskId: str
    outputPath: str


class StubTaskService:
    def __init__(self, tasks):
        self._tasks = {task.taskId: task for task in tasks}

    def taskById(self, taskId):
        return self._tasks.get(taskId)


@pytest.fixture
def engine(bridge):
    instance = bridge.Engine.__new__(bridge.Engine)
    instance._loop = asyncio.new_event_loop()
    thread = Thread(target=instance._loop.run_forever, daemon=True)
    thread.start()

    instance._coroutineRunner = CoroutineRunner(
        dispatcher=instance._loop.call_soon_threadsafe, isAlive=None, loop=instance._loop)
    instance._flows = StubFlows()
    instance._hashState = bridge.HashState()
    instance._hashWorkId = None

    yield instance

    instance._loop.call_soon_threadsafe(instance._loop.stop)
    thread.join(timeout=2)
    instance._loop.close()


def buildTask(path: Path, name: str) -> StubTask:
    return StubTask(taskId=f"tsk_{name}", outputPath=str(path))


def test_idle_state_sends_null_error_never_an_empty_string(engine):
    engine._emitHashState()

    payload = json.loads(engine._flows.states["hashState"])
    assert payload == {"taskId": "", "algorithm": "", "progress": 0, "digest": "", "error": None}
    assert payload["error"] is None


def waitFor(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("条件没有在超时前成立")


def test_digest_matches_hashlib(engine, tmp_path):
    payload = bytes(range(256)) * 400
    path = tmp_path / "blob.bin"
    path.write_bytes(payload)
    task = buildTask(path, "blob.bin")
    engine._taskService = StubTaskService([task])

    engine.startFileHash(task.taskId, "sha256")
    waitFor(lambda: engine._hashState.digest != "")

    assert engine._hashState.digest == hashlib.sha256(payload).hexdigest()
    assert engine._hashState.progress == 100
    assert engine._hashState.error is None


def test_missing_file_reports_error_instead_of_crashing(engine, tmp_path):
    task = buildTask(tmp_path / "gone.bin", "gone.bin")
    engine._taskService = StubTaskService([task])

    engine.startFileHash(task.taskId, "md5")
    waitFor(lambda: engine._hashState.error is not None)

    assert engine._hashState.digest == ""
    # Kotlin 的 HashState.error 是 TaskError?，字符串会在这里炸成 JsonDecodingException
    assert isinstance(engine._hashState.error, dict)
    assert set(engine._hashState.error) == {"message", "params"}


def test_starting_a_second_task_never_reports_under_the_first(engine, tmp_path):
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    first.write_bytes(b"a" * (64 * 1024 * 1024))
    second.write_bytes(b"b" * (64 * 1024 * 1024))
    taskA = buildTask(first, "first.bin")
    taskB = buildTask(second, "second.bin")
    engine._taskService = StubTaskService([taskA, taskB])

    digestA = hashlib.sha256(b"a" * (64 * 1024 * 1024)).hexdigest()

    engine.startFileHash(taskA.taskId, "sha256")
    waitFor(lambda: 0 < engine._hashState.progress < 100)
    engine.startFileHash(taskB.taskId, "sha256")
    waitFor(lambda: engine._hashState.digest != "")

    assert engine._hashState.taskId == taskB.taskId
    assert engine._hashState.digest != digestA
    assert engine._hashState.digest == hashlib.sha256(b"b" * (64 * 1024 * 1024)).hexdigest()


def test_cancel_after_restart_still_stops_the_new_job(engine, tmp_path):
    path = tmp_path / "big.bin"
    path.write_bytes(b"c" * (64 * 1024 * 1024))
    task = buildTask(path, "big.bin")
    engine._taskService = StubTaskService([task])

    engine.startFileHash(task.taskId, "md5")
    waitFor(lambda: engine._hashState.progress > 0)
    engine.startFileHash(task.taskId, "sha512")
    waitFor(lambda: engine._hashState.algorithm == "sha512")
    engine.cancelFileHash()

    time.sleep(0.5)
    assert engine._hashState.taskId == ""
    assert engine._hashState.digest == ""
