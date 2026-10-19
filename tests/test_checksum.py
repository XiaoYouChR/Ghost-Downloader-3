from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest

from app.checksum import matchChecksum, parseChecksum
from app.models.task import Task, TaskStatus
from tests.conftest import FakeStep
from tests.helpers import waitUntil


SHA256 = hashlib.sha256(b"downloaded").hexdigest()


async def addFinished(engine) -> Task:
    task = Task(name="a.iso", url="http://test/a.iso", packId="test", steps=[FakeStep(stepIndex=0)])
    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)
    return task


def stopsOf(engine) -> list:
    stops = []
    engine.taskService.checksumStopped.connect(lambda task, error: stops.append((task, error)))
    return stops


async def test_start_saves_checksum_on_task(engine):
    task = await addFinished(engine)
    completed = []
    engine.taskService.checksumCompleted.connect(lambda task, algorithm: completed.append((task, algorithm)))

    engine.taskService.startChecksum(task, "sha256")

    assert engine.taskService.checksumProgress(task) == 0
    await waitUntil(lambda: completed == [(task, "sha256")])
    assert task.checksums == {"sha256": SHA256}
    assert engine.taskService.checksumProgress(task) is None


async def test_start_on_missing_file_reports_error(engine):
    task = await addFinished(engine)
    stops = stopsOf(engine)
    Path(task.outputPath).unlink()

    engine.taskService.startChecksum(task, "sha256")

    await waitUntil(lambda: len(stops) == 1)
    assert stops[0][0] is task
    assert stops[0][1] is not None
    assert task.checksums == {}


@pytest.mark.parametrize("stop", [
    lambda service, task: service.cancelChecksum(task),
    lambda service, task: service.delete(task, shouldDeleteFiles=False),
])
async def test_cancel_saves_nothing(engine, stop):
    task = await addFinished(engine)
    stops = stopsOf(engine)

    engine.taskService.startChecksum(task, "sha256")
    stop(engine.taskService, task)
    await asyncio.sleep(0.1)

    assert stops == [(task, None)]
    assert task.checksums == {}


async def test_redownload_clears_checksums(engine):
    task = await addFinished(engine)
    task.checksums["md5"] = "old"

    engine.taskService.redownload(task)

    await waitUntil(lambda: task.checksums == {})


async def test_resume_keeps_checksums(engine, startEngine):
    task = await addFinished(engine)
    engine.taskService.startChecksum(task, "sha256")
    await waitUntil(lambda: task.checksums == {"sha256": SHA256})

    restarted = startEngine()

    assert restarted.taskService.taskById(task.taskId).checksums == {"sha256": SHA256}


def test_match_ignores_case_and_spaces():
    assert matchChecksum({"md5": "aa11", "sha256": "bb22"}, "  BB22\n") == "sha256"


def test_match_sha256sum_line():
    assert matchChecksum({"sha256": "bb22"}, "BB22  ubuntu.iso\n") == "sha256"


def test_match_rejects_wrong_checksum():
    assert matchChecksum({"md5": "aa11"}, "cc33") is None


def test_parse_sha256sum_line_as_lowercase():
    assert parseChecksum("AB12  ffmpeg.tar.gz\n") == "ab12"
