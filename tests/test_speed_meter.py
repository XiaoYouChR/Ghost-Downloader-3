from __future__ import annotations

import asyncio

from app.models.task import Task, TaskStatus
from tests.conftest import FakeSeedingTask, FakeStep
from tests.helpers import waitUntil


def speedsOf(engine) -> list[int]:
    speeds = []
    engine.speedMeter.speedChanged.connect(speeds.append)
    return speeds


async def test_pause_last_task_stops_meter(engine):
    task = Task(name="a.zip", url="http://test/a.zip", packId="test", steps=[FakeStep(stepIndex=0, outcome="hang")])
    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.RUNNING)
    speeds = speedsOf(engine)

    engine.taskService.pause(task)

    assert speeds == [0]
    await asyncio.sleep(1.2)
    assert speeds == [0]


async def test_run_seeding_keeps_meter_ticking(engine):
    task = FakeSeedingTask(name="a.iso", url="magnet:?xt=urn:btih:a", packId="test", steps=[FakeStep(stepIndex=0)])
    engine.taskService.add(task)
    await waitUntil(lambda: task.isSeeding)
    speeds = speedsOf(engine)

    await asyncio.sleep(2.2)

    assert len(speeds) >= 2


async def test_stop_seeding_stops_meter(engine):
    task = FakeSeedingTask(name="a.iso", url="magnet:?xt=urn:btih:a", packId="test", steps=[FakeStep(stepIndex=0)])
    engine.taskService.add(task)
    await waitUntil(lambda: task.isSeeding)
    speeds = speedsOf(engine)

    engine.taskService.stopSeeding(task)

    assert speeds == [0]
    await asyncio.sleep(1.2)
    assert speeds == [0]
