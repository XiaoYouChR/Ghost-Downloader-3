from __future__ import annotations

import re

import pytest

from app.config.cfg import cfg
from app.models.task import Task, TaskError, TaskStatus
from tests.conftest import FakeStep
from tests.helpers import waitUntil


def buildTask(outcome: str = "hang", name: str = "a.zip") -> Task:
    return Task(name=name, url=f"http://test/{name}", packId="test", steps=[FakeStep(stepIndex=0, outcome=outcome)])




async def test_add_without_start_waits(engine):
    task = buildTask("complete")

    engine.taskService.add(task, autoStart=False)

    assert task.status == TaskStatus.WAITING
    engine.taskService.start(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)


def test_add_same_task_twice_keeps_one(engine):
    added = []
    engine.taskService.taskAdded.connect(added.append)
    task = buildTask()

    engine.taskService.add(task, autoStart=False)
    engine.taskService.add(task, autoStart=False)

    assert added == [task]
    assert engine.taskService.tasks == [task]


def test_add_into_blocked_folder_fails_with_reason(engine, blockedFolder):
    task = buildTask()
    task.setOptions({"outputFolder": blockedFolder})

    with pytest.raises(TaskError, match=re.escape(str(blockedFolder))):
        engine.taskService.add(task)

    assert engine.taskService.tasks == []


async def test_start_all_skips_finished_tasks(engine):
    paused, waiting, failed, finished = (buildTask(), buildTask(), buildTask("fail"), buildTask("complete"))
    engine.taskService.add(paused)
    engine.taskService.pause(paused)
    engine.taskService.add(waiting, autoStart=False)
    engine.taskService.add(failed)
    engine.taskService.add(finished)
    await waitUntil(lambda: failed.status == TaskStatus.FAILED)
    await waitUntil(lambda: finished.status == TaskStatus.COMPLETED)
    failed.steps[0].outcome = "hang"

    engine.taskService.startAll()

    await waitUntil(lambda: engine.taskService.runningCount() == 3)
    assert finished.status == TaskStatus.COMPLETED


async def test_start_runs_at_most_set_number(engine):
    cfg.set(cfg.maxTaskNum, 2)
    tasks = [buildTask() for _ in range(3)]

    for task in tasks:
        engine.taskService.add(task)

    await waitUntil(lambda: [task.status for task in tasks] ==
                    [TaskStatus.RUNNING, TaskStatus.RUNNING, TaskStatus.WAITING])


async def test_run_next_waiting_after_one_finishes(engine):
    cfg.set(cfg.maxTaskNum, 1)
    first, second = buildTask("complete"), buildTask()

    engine.taskService.add(first)
    engine.taskService.add(second)

    await waitUntil(lambda: second.status == TaskStatus.RUNNING)
    assert first.status == TaskStatus.COMPLETED


async def test_run_announces_all_finished(engine):
    announced = []
    engine.taskService.tasksAllCompleted.connect(lambda: announced.append(True))
    tasks = [buildTask("complete") for _ in range(2)]

    for task in tasks:
        engine.taskService.add(task)

    await waitUntil(lambda: announced == [True])
    assert [task.status for task in tasks] == [TaskStatus.COMPLETED, TaskStatus.COMPLETED]


async def test_move_to_front_runs_next(engine):
    cfg.set(cfg.maxTaskNum, 1)
    running, second, third = buildTask(), buildTask(), buildTask()
    for task in (running, second, third):
        engine.taskService.add(task)
    await waitUntil(lambda: running.status == TaskStatus.RUNNING)

    engine.taskService.moveToFront([third.taskId])
    engine.taskService.pause(running)

    await waitUntil(lambda: third.status == TaskStatus.RUNNING)
    assert second.status == TaskStatus.WAITING


async def test_move_running_to_front_changes_nothing(engine):
    changed = []
    engine.taskService.queueChanged.connect(lambda: changed.append(True))
    tasks = [buildTask(), buildTask()]
    for task in tasks:
        engine.taskService.add(task)
    await waitUntil(lambda: engine.taskService.runningCount() == 2)

    engine.taskService.moveToFront([task.taskId for task in tasks])

    assert changed == []
