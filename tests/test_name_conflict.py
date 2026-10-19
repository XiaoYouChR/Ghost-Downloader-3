from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.config.cfg import cfg
from app.models.task import Task, TaskStatus
from app.services.task_service import NameConflictChoice
from tests.conftest import FakeStep
from tests.helpers import waitUntil


@pytest.fixture
def conflicts(engine):
    cfg.set(cfg.nameConflict, NameConflictChoice.ASK.value)
    shown = []
    engine.nameConflictQueue.conflictChanged.connect(shown.append)
    return shown


def buildTask(name: str = "a.zip") -> Task:
    return Task(name=name, url=f"http://test/{name}", packId="test", steps=[FakeStep(stepIndex=0)])


def buildVideoTask() -> Task:
    return Task(name="a.mp4", url="http://test/a.mp4", packId="test",
                steps=[FakeStep(stepIndex=0), FakeStep(stepIndex=1, sideSuffix="en.srt")])


def createUserFile(engine, task: Task, name: str | None = None) -> Path:
    _, folder = engine.categoryService.outputFolderOf(task)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name or task.name)
    path.write_bytes(b"mine")
    return path


async def addAll(engine, tasks: list[Task]) -> None:
    for task in tasks:
        engine.taskService.add(task)
    await asyncio.sleep(0)


async def addCompleted(engine, task: Task) -> None:
    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)


async def test_add_asks_conflicts_one_by_one(engine, conflicts,
                                                                                       downloadFolder):
    tasks = [buildTask() for _ in range(3)]
    takenPath = createUserFile(engine, tasks[0])

    await addAll(engine, tasks)

    assert [(c.task, c.takenPath, c.restCount) for c in conflicts] == [(tasks[0], takenPath, 2)]
    assert engine.taskService.tasks == []
    assert [p.name for p in downloadFolder.iterdir()] == ["a.zip"]


async def test_add_asks_about_taken_side_file(engine, conflicts):
    task = buildVideoTask()
    takenPath = createUserFile(engine, task, "a.en.srt")

    await addAll(engine, [task])

    assert [(c.task, c.takenPath) for c in conflicts] == [(task, takenPath)]


async def test_add_while_asking_waits(engine, conflicts):
    first, second = buildTask(), buildTask()
    createUserFile(engine, first)
    await addAll(engine, [first])

    await addAll(engine, [second])

    assert [c.task for c in conflicts] == [first]


async def test_add_skips_conflict_gone_before_its_turn(engine, conflicts):
    first, second = buildTask("a.zip"), buildTask("b.zip")
    createUserFile(engine, first)
    secondPath = createUserFile(engine, second)
    await addAll(engine, [first, second])
    secondPath.unlink()

    engine.nameConflictQueue.setChoice(first.taskId, NameConflictChoice.KEEP_BOTH, False)

    assert second.name == "b.zip"
    assert engine.taskService.taskById(second.taskId) is second
    assert conflicts[-1] is None


async def test_replace_recycles_user_file(engine, conflicts, recycleBin):
    task = buildTask()
    takenPath = createUserFile(engine, task)
    await addAll(engine, [task])

    engine.nameConflictQueue.setChoice(task.taskId, NameConflictChoice.OVERWRITE, False)

    assert recycleBin.paths == [takenPath]
    assert task.name == "a.zip"
    assert engine.taskService.taskById(task.taskId) is task
    assert conflicts[-1] is None


async def test_replace_without_recycle_bin_keeps_both(engine, conflicts, recycleBin):
    recycleBin.isAvailable = False
    overwriteFailed = []
    engine.taskService.overwriteFailed.connect(overwriteFailed.append)
    task = buildTask()
    takenPath = createUserFile(engine, task)
    await addAll(engine, [task])

    engine.nameConflictQueue.setChoice(task.taskId, NameConflictChoice.OVERWRITE, False)

    assert takenPath.read_bytes() == b"mine"
    assert task.name == "a(1).zip"
    assert overwriteFailed == [task]


async def test_add_answer_for_all_covers_shown_conflicts_only(engine, conflicts):
    tasks = [buildTask() for _ in range(3)]
    late = buildTask()
    createUserFile(engine, tasks[0])
    await addAll(engine, tasks)
    await addAll(engine, [late])

    engine.nameConflictQueue.setChoice(tasks[0].taskId, NameConflictChoice.KEEP_BOTH, True)

    assert [task.name for task in tasks] == ["a(1).zip", "a(2).zip", "a(3).zip"]
    assert (conflicts[-1].task, conflicts[-1].restCount) == (late, 0)


async def test_cancel_skips_only_asked_task(engine, conflicts):
    first, second = buildTask(), buildTask()
    createUserFile(engine, first)
    await addAll(engine, [first, second])

    engine.nameConflictQueue.cancel(first.taskId)

    assert engine.taskService.taskById(first.taskId) is None
    assert conflicts[-1].task is second


async def test_add_ignores_late_reply(engine, conflicts):
    first, second = buildTask(), buildTask()
    createUserFile(engine, first)
    await addAll(engine, [first, second])
    engine.nameConflictQueue.setChoice(first.taskId, NameConflictChoice.KEEP_BOTH, False)

    engine.nameConflictQueue.setChoice(first.taskId, NameConflictChoice.OVERWRITE, False)
    engine.nameConflictQueue.cancel(first.taskId)

    assert first.name == "a(1).zip"
    assert conflicts[-1].task is second


async def test_add_keeps_both_when_unfinished_task_holds_name(engine, conflicts):
    first, second = buildTask(), buildTask()
    engine.taskService.add(first, autoStart=False)

    await addAll(engine, [second])

    assert second.name == "a(1).zip"
    assert conflicts == []


async def test_add_numbers_each_new_task(engine):
    tasks = [buildTask() for _ in range(3)]

    await addAll(engine, tasks)

    assert [task.name for task in tasks] == ["a.zip", "a(1).zip", "a(2).zip"]


async def test_add_numbering_skips_taken_names(engine):
    createUserFile(engine, buildTask(), "a.zip")
    await addAll(engine, [buildTask("a(1).zip")])
    task = buildTask()

    await addAll(engine, [task])

    assert task.name == "a(2).zip"


@pytest.mark.parametrize(("name", "numbered"), [
    ("archive.tar.gz", "archive(1).tar.gz"),
    ("my.report.v2.pdf", "my.report.v2(1).pdf"),
    (".gitignore", ".gitignore(1)"),
    ("README", "README(1)"),
])
async def test_add_puts_number_before_extension(engine, name, numbered):
    createUserFile(engine, buildTask(name))
    task = buildTask(name)

    await addAll(engine, [task])

    assert task.name == numbered


async def test_add_keeps_folder_with_same_name(engine):
    task = buildTask("download")
    _, folder = engine.categoryService.outputFolderOf(task)
    (folder / "download").mkdir()

    await addAll(engine, [task])

    assert task.name == "download(1)"
    assert (folder / "download").is_dir()


async def test_add_numbers_whole_task_for_taken_side_file(engine, downloadFolder):
    task = buildVideoTask()
    createUserFile(engine, task, "a.en.srt")

    await addAll(engine, [task])

    assert task.name == "a(1).mp4"
    assert (downloadFolder / "a.en.srt").read_bytes() == b"mine"
    assert (downloadFolder / "a(1).en.srt").exists()


async def test_add_checks_only_category_folder(engine, downloadFolder):
    cfg.set(cfg.isCategoryEnabled, True)
    (downloadFolder / "a.zip").write_bytes(b"mine")
    task = buildTask()

    await addAll(engine, [task])

    assert task.name == "a.zip"
    assert Path(task.outputPath).parent != downloadFolder


async def test_add_takes_name_of_finished_task_with_deleted_file(engine, downloadFolder):
    old = buildTask()
    await addCompleted(engine, old)
    Path(old.outputPath).unlink()
    new = buildTask()

    await addAll(engine, [new])

    assert new.name == "a.zip"
    assert engine.taskService.taskById(old.taskId) is None


async def test_replace_finished_task(engine, recycleBin):
    cfg.set(cfg.nameConflict, NameConflictChoice.OVERWRITE.value)
    old = buildTask()
    await addCompleted(engine, old)
    new = buildTask()

    await addAll(engine, [new])

    assert new.name == "a.zip"
    assert recycleBin.paths == [Path(old.outputPath)]
    assert engine.taskService.taskById(old.taskId) is None


async def test_add_ignores_progress_of_deleted_task(engine):
    old = buildTask()
    engine.taskService.add(old, autoStart=False)
    old.partPath.write_bytes(b"old progress")
    Path(old.outputPath).unlink()
    new = buildTask()

    engine.taskService.add(new, autoStart=False)

    assert new.name == "a.zip"
    assert not new.partPath.exists()


async def test_add_ignores_leftover_progress(engine):
    task = buildTask()
    _, folder = engine.categoryService.outputFolderOf(task)
    (folder / "a.zip.ghd").write_bytes(b"leftover progress")

    engine.taskService.add(task, autoStart=False)

    assert not task.partPath.exists()


async def test_resume_paused_task_keeps_its_name(engine, startEngine, recycleBin):
    cfg.set(cfg.nameConflict, NameConflictChoice.OVERWRITE.value)
    saved = buildTask()
    engine.taskService.add(saved, autoStart=False)
    engine.taskService.pause(saved)
    restarted = startEngine()
    new = buildTask()

    await addAll(restarted, [new])

    assert new.name == "a(1).zip"
    assert recycleBin.paths == []
