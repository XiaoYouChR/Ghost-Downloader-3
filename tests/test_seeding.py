from __future__ import annotations

import json
from pathlib import Path

from app.config.cfg import cfg
from app.config.paths import APP_DATA_DIR
from app.models.task import Task, TaskFile, TaskStatus
from tests.conftest import FakeSeedingTask, FakeStep
from tests.helpers import waitUntil


def buildSeedingTask(seedingOutcome: str = "hang", files: list[TaskFile] | None = None) -> FakeSeedingTask:
    steps = [FakeStep(stepIndex=index, fileIndex=file.index) for index, file in enumerate(files)] if files \
        else [FakeStep(stepIndex=0)]
    return FakeSeedingTask(name="a.iso", url="magnet:?xt=urn:btih:a", packId="test", steps=steps, files=files,
                           seedingOutcome=seedingOutcome)


async def addSeeding(engine, task: FakeSeedingTask | None = None) -> FakeSeedingTask:
    task = task or buildSeedingTask()
    engine.taskService.add(task)
    await waitUntil(lambda: task.isSeeding)
    return task


async def resume(startEngine, task: Task) -> Task:
    engine = startEngine()
    await waitUntil(lambda: engine.taskService.taskById(task.taskId) is not None)
    return engine.taskService.taskById(task.taskId)


async def test_run_finished_task_seeds_without_task_slot(engine):
    cfg.set(cfg.maxTaskNum, 1)
    seeding = buildSeedingTask()
    other = Task(name="b.zip", url="http://test/b.zip", packId="test", steps=[FakeStep(stepIndex=0, outcome="hang")])

    engine.taskService.add(seeding)
    engine.taskService.add(other)

    await waitUntil(lambda: seeding.isSeeding and other.status == TaskStatus.RUNNING)
    assert seeding.status == TaskStatus.COMPLETED
    assert seeding.seedingRuns == [False]


async def test_run_never_seeds_unseedable_task(engine):
    task = Task(name="a.zip", url="http://test/a.zip", packId="test", steps=[FakeStep(stepIndex=0)])

    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)

    assert not task.isSeeding


async def test_stop_stays_after_restart(engine, startEngine):
    task = await addSeeding(engine)

    engine.taskService.stopSeeding(task)

    assert (task.isSeeding, task.status) == (False, TaskStatus.COMPLETED)
    assert not (await resume(startEngine, task)).isSeeding


async def test_start_by_hand_is_manual(engine):
    task = await addSeeding(engine)
    engine.taskService.stopSeeding(task)

    engine.taskService.startSeeding(task)

    await waitUntil(lambda: task.seedingRuns == [False, True])
    assert task.isSeeding


async def test_resume_skips_seeding_that_ended_by_itself(engine, startEngine):
    task = buildSeedingTask("end")
    engine.taskService.add(task)
    await waitUntil(lambda: task.seedingRuns == [False] and not task.isSeeding)

    assert not (await resume(startEngine, task)).isSeeding


async def test_resume_failed_seeding(engine, startEngine):
    task = buildSeedingTask("fail")
    engine.taskService.add(task)
    await waitUntil(lambda: task.seedingRuns == [False] and not task.isSeeding)

    restoredTask = await resume(startEngine, task)

    await waitUntil(lambda: restoredTask.seedingRuns == [False])


async def test_delete_stops_seeding(engine):
    stopped = []
    engine.taskService.seedingStopped.connect(stopped.append)
    task = await addSeeding(engine)

    engine.taskService.delete(task, shouldDeleteFiles=False)

    await waitUntil(lambda: stopped == [task])


async def test_redownload_seeds_again(engine):
    task = await addSeeding(engine)
    engine.taskService.stopSeeding(task)

    engine.taskService.redownload(task)

    await waitUntil(lambda: task.isSeeding and task.seedingRuns == [False, False])


async def test_edit_selection_stops_seeding_and_downloads(engine, downloadFolder):
    files = [TaskFile(index=0, relativePath="a.iso"), TaskFile(index=1, relativePath="b.iso", selected=False)]
    task = await addSeeding(engine, buildSeedingTask(files=files))

    engine.taskService.updateSelection(task, {0, 1})

    await waitUntil(lambda: (downloadFolder / "a.iso" / "b.iso").exists() and task.isSeeding)
    assert task.seedingRuns == [False, False]


async def test_resume_after_restart(engine, startEngine):
    task = await addSeeding(engine)

    restoredTask = await resume(startEngine, task)

    await waitUntil(lambda: restoredTask.isSeeding)


async def test_resume_skips_task_with_missing_file(engine, startEngine):
    task = await addSeeding(engine)
    Path(task.outputPath).unlink()

    restoredTask = await resume(startEngine, task)

    assert not restoredTask.isSeeding


async def test_resume_seeding_stopped_by_missing_file(engine, startEngine, fileWatcher):
    task = await addSeeding(engine)

    Path(task.outputPath).unlink()
    fileWatcher.fileChanged.emit(task.outputPath)

    await waitUntil(lambda: not task.isSeeding)
    Path(task.outputPath).write_text("downloaded")
    assert (await resume(startEngine, task)).isSeeding


async def test_load_old_record_does_not_seed(startEngine, downloadFolder):
    task = FakeSeedingTask(name="a.iso", url="magnet:?xt=urn:btih:a", packId="test", status=TaskStatus.COMPLETED,
                           steps=[FakeStep(stepIndex=0, status=TaskStatus.COMPLETED)], outputFolder=downloadFolder)
    (downloadFolder / "a.iso").write_text("downloaded")
    record = task.toDict()
    record.pop("shouldSeed")
    (APP_DATA_DIR / "tasks.jsonl").write_text(json.dumps(record) + "\n")

    restoredTask = await resume(startEngine, task)

    assert not restoredTask.isSeeding
