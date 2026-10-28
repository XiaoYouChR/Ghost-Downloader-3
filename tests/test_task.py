from __future__ import annotations

from pathlib import Path

from app.config.cfg import cfg
from app.models.task import Task, TaskFile, TaskStatus
from tests.conftest import FakeStep
from tests.helpers import waitUntil


def buildTask(name: str = "a.zip", steps: list[FakeStep] | None = None, files: list[TaskFile] | None = None) -> Task:
    return Task(name=name, url=f"http://test/{name}", packId="test", steps=steps or [FakeStep(stepIndex=0)],
                files=files)


def buildFolderTask(*outcomes: str) -> Task:
    return buildTask("playlist", files=[TaskFile(index=0, relativePath="sub/first.mp4", size=10),
                                        TaskFile(index=1, relativePath="second.mp4", size=20)],
                     steps=[FakeStep(stepIndex=index, fileIndex=index, outcome=outcome)
                            for index, outcome in enumerate(outcomes)])


def namesIn(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())




def test_add_holds_name_with_empty_file(engine, downloadFolder):
    engine.taskService.add(buildTask(), autoStart=False)

    assert (downloadFolder / "a.zip").read_bytes() == b""


def test_add_folder_task_holds_empty_folder(engine, downloadFolder):
    engine.taskService.add(buildFolderTask("complete", "complete"), autoStart=False)

    assert (downloadFolder / "playlist").is_dir()
    assert namesIn(downloadFolder / "playlist") == []


async def test_add_single_file_task_saves_the_file_itself(engine, downloadFolder):
    task = buildTask("a.iso", files=[TaskFile(index=0, relativePath="dir/a.iso")],
                     steps=[FakeStep(stepIndex=0, fileIndex=0)])

    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)

    assert namesIn(downloadFolder) == ["a.iso"]
    assert (downloadFolder / "a.iso").read_bytes() == b"downloaded"


def test_add_holds_side_file_beside_file(engine, downloadFolder):
    task = buildTask("v1.2 intro.mp4", steps=[FakeStep(stepIndex=0), FakeStep(stepIndex=1, sideSuffix="en.srt")])

    engine.taskService.add(task, autoStart=False)

    assert namesIn(downloadFolder) == ["v1.2 intro.en.srt", "v1.2 intro.mp4"]


def test_add_side_file_of_folder_keeps_folder_name(engine, downloadFolder):
    task = buildTask("Ubuntu 22.04", files=[TaskFile(index=0, relativePath="a.iso"),
                                            TaskFile(index=1, relativePath="b.iso")],
                     steps=[FakeStep(stepIndex=0, sideSuffix="torrent")])

    engine.taskService.add(task, autoStart=False)

    assert namesIn(downloadFolder) == ["Ubuntu 22.04", "Ubuntu 22.04.torrent"]


async def test_redownload_keeps_name_held(engine):
    step = FakeStep(stepIndex=0)
    task = buildTask(steps=[step])
    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)

    step.outcome = "hang"
    engine.taskService.redownload(task)
    await waitUntil(lambda: task.status == TaskStatus.RUNNING)
    other = buildTask()
    engine.taskService.add(other, autoStart=False)

    assert other.name == "a(1).zip"


async def test_run_leaves_only_finished_file(engine, downloadFolder):
    task = buildTask("a.mp4", steps=[FakeStep(stepIndex=0, isInPartFolder=True), FakeStep(stepIndex=1)])

    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)

    assert namesIn(downloadFolder) == ["a.mp4"]
    assert (downloadFolder / "a.mp4").read_bytes() == b"downloaded"


async def test_run_keeps_empty_file(engine, downloadFolder):
    task = buildTask(steps=[FakeStep(stepIndex=0, content="")])

    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)

    assert namesIn(downloadFolder) == ["a.zip"]


async def test_run_failure_keeps_finished_files(engine, downloadFolder):
    task = buildFolderTask("complete", "fail")

    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.FAILED)

    assert str(task.lastError) != ""
    assert (downloadFolder / "playlist" / "sub" / "first.mp4").read_bytes() == b"downloaded"


async def test_start_paused_task_finishes(engine, downloadFolder):
    step = FakeStep(stepIndex=0, outcome="hang")
    task = buildTask(steps=[step])
    engine.taskService.add(task)
    await waitUntil(lambda: (downloadFolder / "a.zip").read_bytes() == b"half")

    engine.taskService.pause(task)
    step.outcome = "complete"
    engine.taskService.start(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)

    assert (downloadFolder / "a.zip").read_bytes() == b"downloaded"


async def test_start_failed_task_finishes(engine, downloadFolder):
    task = buildFolderTask("complete", "fail")
    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.FAILED)

    task.steps[1].outcome = "complete"
    engine.taskService.start(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)

    assert (downloadFolder / "playlist" / "second.mp4").read_bytes() == b"downloaded"


async def test_delete_unfinished_keeps_only_user_files(engine, downloadFolder):
    (downloadFolder / "a.nfo").write_bytes(b"mine")
    task = buildTask("a.mp4", steps=[FakeStep(stepIndex=0, isInPartFolder=True, outcome="hang"),
                                     FakeStep(stepIndex=1), FakeStep(stepIndex=2, sideSuffix="en.srt")])
    engine.taskService.add(task)
    await waitUntil(lambda: task.partPath.exists())

    engine.taskService.delete(task, shouldDeleteFiles=True)
    await waitUntil(lambda: namesIn(downloadFolder) == ["a.nfo"])

    assert (downloadFolder / "a.nfo").read_bytes() == b"mine"


async def test_delete_finished_keeps_file(engine, downloadFolder):
    task = buildTask()
    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)

    engine.taskService.delete(task, shouldDeleteFiles=False)
    await waitUntil(lambda: engine.taskService.taskById(task.taskId) is None)

    assert (downloadFolder / "a.zip").read_bytes() == b"downloaded"


async def test_delete_unfinished_releases_name(engine, downloadFolder):
    task = buildTask(steps=[FakeStep(stepIndex=0, outcome="hang")])
    engine.taskService.add(task)
    await waitUntil(lambda: (downloadFolder / "a.zip").read_bytes() == b"half")

    engine.taskService.delete(task, shouldDeleteFiles=False)
    await waitUntil(lambda: namesIn(downloadFolder) == [])


async def test_delete_unfinished_folder_keeps_finished_files(engine, downloadFolder):
    task = buildFolderTask("complete", "fail")
    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.FAILED)

    engine.taskService.delete(task, shouldDeleteFiles=False)
    await waitUntil(lambda: not (downloadFolder / "playlist" / "second.mp4").exists())

    assert (downloadFolder / "playlist" / "sub" / "first.mp4").read_bytes() == b"downloaded"


async def test_redownload_replaces_file(engine, downloadFolder):
    step = FakeStep(stepIndex=0)
    task = buildTask(steps=[step])
    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)

    step.content = "again"
    engine.taskService.redownload(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED
                    and (downloadFolder / "a.zip").read_bytes() == b"again")


async def test_edit_selection_skips_deselected_file(engine, downloadFolder):
    task = buildFolderTask("complete", "complete")
    engine.taskService.add(task, autoStart=False)

    engine.taskService.updateSelection(task, {0})
    engine.taskService.start(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)

    assert task.fileSize == 10
    assert namesIn(downloadFolder / "playlist") == ["sub"]


async def test_edit_folder_onto_taken_name_numbers_task(engine, downloadFolder):
    task = buildTask()
    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)
    newFolder = downloadFolder / "new"
    newFolder.mkdir()
    (newFolder / "a.zip").write_bytes(b"mine")

    engine.taskService.edit(task, {"outputFolder": str(newFolder)})

    assert task.name == "a(1).zip"
    assert (newFolder / "a(1).zip").read_bytes() == b"downloaded"
    assert (newFolder / "a.zip").read_bytes() == b"mine"
    assert namesIn(downloadFolder) == ["new"]


async def test_edit_folder_carries_progress(engine, downloadFolder):
    task = buildTask(steps=[FakeStep(stepIndex=0, outcome="hang")])
    engine.taskService.add(task, autoStart=False)
    task.partPath.write_bytes(b"offsets")
    newFolder = downloadFolder / "new"

    engine.taskService.edit(task, {"outputFolder": str(newFolder)})

    assert (newFolder / "a.zip.ghd").read_bytes() == b"offsets"
    assert namesIn(downloadFolder) == ["new"]


async def test_edit_folder_moves_held_name(engine, downloadFolder):
    moved = buildTask(steps=[FakeStep(stepIndex=0, outcome="hang")])
    engine.taskService.add(moved)
    newFolder = downloadFolder / "new"

    engine.taskService.edit(moved, {"outputFolder": str(newFolder)})
    await waitUntil(lambda: (newFolder / "a.zip").exists())
    besideOld, besideNew = buildTask(), buildTask()
    besideNew.outputFolder = newFolder
    engine.taskService.add(besideOld, autoStart=False)
    engine.taskService.add(besideNew, autoStart=False)

    assert (besideOld.name, besideNew.name) == ("a.zip", "a(1).zip")


async def test_edit_side_file_moves_held_name(engine, downloadFolder):
    task = buildTask("a.mp4", steps=[FakeStep(stepIndex=0), FakeStep(stepIndex=1, sideSuffix="en.vtt")])
    engine.taskService.add(task, autoStart=False)

    engine.taskService.edit(task, {"sideSuffix": "fr.vtt"})

    assert namesIn(downloadFolder) == ["a.fr.vtt", "a.mp4"]


async def test_edit_side_file_onto_taken_name_numbers_task(engine, downloadFolder):
    task = buildTask("a.mp4", steps=[FakeStep(stepIndex=0), FakeStep(stepIndex=1, sideSuffix="en.vtt")])
    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)
    (downloadFolder / "a.fr.vtt").write_bytes(b"mine")

    engine.taskService.edit(task, {"sideSuffix": "fr.vtt"})

    assert task.name == "a(1).mp4"
    assert (downloadFolder / "a(1).mp4").read_bytes() == b"downloaded"
    assert (downloadFolder / "a.fr.vtt").read_bytes() == b"mine"


async def addCompleted(engine, name: str) -> Task:
    task = buildTask(name)
    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)
    return task


async def test_enable_remove_missing_tasks_removes_only_missing(engine):
    missing = await addCompleted(engine, "a.zip")
    kept = await addCompleted(engine, "b.zip")
    Path(missing.outputPath).unlink()

    cfg.set(cfg.shouldRemoveMissingTasks, True)

    assert engine.taskService.taskById(missing.taskId) is None
    assert engine.taskService.taskById(kept.taskId) is kept


async def test_file_disappeared_removes_task_when_enabled(engine, fileWatcher):
    cfg.set(cfg.shouldRemoveMissingTasks, True)
    task = await addCompleted(engine, "a.zip")

    Path(task.outputPath).unlink()
    fileWatcher.fileChanged.emit(task.outputPath)

    assert engine.taskService.taskById(task.taskId) is None


async def test_resume_removes_missing_task_when_enabled(engine, startEngine):
    cfg.set(cfg.shouldRemoveMissingTasks, True)
    task = await addCompleted(engine, "a.zip")
    Path(task.outputPath).unlink()

    restarted = startEngine()

    assert restarted.taskService.tasks == []
