"""TaskService 生命周期的逐分支测试。

Seam S7: TaskService.add/pause/delete/redownload/edit/queue
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from app.models.task import Task, TaskStep, TaskStatus


@dataclass(kw_only=True)
class StubStep(TaskStep):
    stepIndex: int = 0

    @property
    def outputPath(self) -> str:
        return self.task.outputPath

    async def run(self, reportSpeed, waitForSpeedLimit):
        pass


class StubCoroutineRunner:
    def __init__(self):
        self.submitted: list[tuple[str, object, object]] = []
        self.cancelled: list[str] = []
        self._counter = 0

    def submit(self, work, done=None, failed=None, **kwargs) -> str:
        self._counter += 1
        workId = f"wrk_{self._counter}"
        self.submitted.append((workId, done, failed))
        return workId

    def cancel(self, workId: str, finished=None) -> bool:
        self.cancelled.append(workId)
        if finished is not None:
            finished()
        return True

    def post(self, callback, *args, **kwargs):
        callback(*args, **kwargs)

    def addSpeed(self, n):
        pass

    async def waitForSpeedLimit(self):
        pass

    @property
    def dispatched(self) -> list[tuple[str, object, object]]:
        return [(wid, done, failed) for wid, done, failed in self.submitted if done is not None]


class StubCategoryService:
    def outputFolderOf(self, task):
        return task.category, task.outputFolder


class StubSpeedMeter:
    def __init__(self):
        self.calls: list[str] = []

    @property
    def isRunning(self) -> bool:
        return bool(self.calls) and self.calls[-1] == "start"

    def addSpeed(self, n):
        pass

    async def waitForSpeedLimit(self):
        pass

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")


class StubFileWatcher:
    class _Signal:
        def connect(self, _): pass
    fileChanged = _Signal()

    def addPath(self, _): pass
    def removePath(self, _): pass


class StubPlatform:
    def __init__(self):
        self.choice = NameConflictChoice.KEEP_BOTH
        self.canTrash = True
        self.trashed: list[Path] = []

    def deleteRecoverably(self, path: Path) -> bool:
        if not self.canTrash:
            return False
        self.trashed.append(path)
        path.unlink()
        return True


@pytest.fixture()
def platform():
    return StubPlatform()


@pytest.fixture()
def speedMeter():
    return StubSpeedMeter()


@pytest.fixture()
def service(qapp, monkeypatch, tmp_path, platform, speedMeter):
    from app.config.cfg import cfg
    monkeypatch.setattr(cfg.maxTaskNum, "value", 3)
    monkeypatch.setattr(cfg.isCategoryEnabled, "value", False)
    monkeypatch.setattr(cfg.downloadFolder, "value", str(tmp_path))

    runner = StubCoroutineRunner()
    category = StubCategoryService()
    svc = TaskService(runner, category, speedMeter, StubFileWatcher(),
                      deleteRecoverably=platform.deleteRecoverably,
                      nameConflictChoice=lambda: platform.choice)
    return svc, runner


def makeTask(taskId: str = "t1", name: str = "test.zip") -> Task:
    step = StubStep(stepIndex=0)
    task = Task(name=name, url="http://test/file.zip", packId="http",
                taskId=taskId, steps=[step])
    step._bindTask(task)
    return task


from app.services.task_service import NameConflictChoice, TaskService


@dataclass(kw_only=True, eq=False)
class FolderOutputTask(Task):
    """Simulates a multi-file task whose outputPath is a folder (like BilibiliTask)."""
    @property
    def outputPath(self) -> str:
        return str(self.outputFolder / Path(self.name).stem)


def makeFolderTask(taskId: str, name: str = "video.mp4") -> Task:
    step = StubStep(stepIndex=0)
    task = FolderOutputTask(name=name, url="http://test/video", packId="bili",
                            taskId=taskId, steps=[step])
    step._bindTask(task)
    return task


class TestDeduplicateOutput:

    def test_no_conflict(self, service):
        svc, _ = service
        task = makeTask("dd1", name="unique.zip")
        svc.add(task)
        assert task.name == "unique.zip"

    def test_store_conflict_renames(self, service):
        svc, _ = service
        svc.add(makeTask("s1", name="same.zip"))
        t2 = makeTask("s2", name="same.zip")
        svc.add(t2)
        assert t2.name == "same(1).zip"

    def test_store_conflict_increments(self, service):
        svc, _ = service
        svc.add(makeTask("i1", name="file.zip"))
        svc.add(makeTask("i2", name="file.zip"))
        t3 = makeTask("i3", name="file.zip")
        svc.add(t3)
        assert t3.name == "file(2).zip"

    def test_disk_conflict_renames(self, service, tmp_path):
        svc, _ = service
        (tmp_path / "existing.zip").touch()
        task = makeTask("dk1", name="existing.zip")
        svc.add(task)
        assert task.name == "existing(1).zip"

    def test_batch_all_unique(self, service):
        svc, _ = service
        names = []
        for i in range(5):
            t = makeTask(f"b{i}", name="s-l1600.jpg")
            svc.add(t)
            names.append(t.name)
        assert len(set(names)) == 5
        assert names[0] == "s-l1600.jpg"
        assert names[1] == "s-l1600(1).jpg"

    def test_different_folder_no_conflict(self, service, tmp_path):
        svc, _ = service
        t1 = makeTask("df1", name="file.zip")
        svc.add(t1)
        t2 = makeTask("df2", name="file.zip")
        t2.outputFolder = tmp_path / "other"
        svc.add(t2)
        assert t2.name == "file.zip"

    def test_folder_output_store_conflict(self, service):
        svc, _ = service
        t1 = makeFolderTask("fo1", "video.mp4")
        svc.add(t1)
        t2 = makeFolderTask("fo2", "video.mp4")
        svc.add(t2)
        assert "video(1)" in t2.outputPath

    def test_folder_output_disk_conflict(self, service, tmp_path):
        svc, _ = service
        (tmp_path / "existing_video").mkdir()
        task = makeFolderTask("fd1", "existing_video.mp4")
        svc.add(task)
        assert "existing_video(1)" in task.outputPath

    def test_disk_and_store_combined(self, service, tmp_path):
        svc, _ = service
        (tmp_path / "combo.zip").touch()
        svc.add(makeTask("cs1", name="combo(1).zip"))
        task = makeTask("cs2", name="combo.zip")
        svc.add(task)
        assert task.name == "combo(2).zip"

    def test_compound_ext_tar_gz(self, service):
        svc, _ = service
        svc.add(makeTask("cg1", name="archive.tar.gz"))
        t2 = makeTask("cg2", name="archive.tar.gz")
        svc.add(t2)
        assert t2.name == "archive(1).tar.gz"

    def test_multi_dot_name(self, service):
        svc, _ = service
        svc.add(makeTask("md1", name="my.report.v2.pdf"))
        t2 = makeTask("md2", name="my.report.v2.pdf")
        svc.add(t2)
        assert t2.name == "my.report.v2(1).pdf"

    def test_dotfile(self, service):
        svc, _ = service
        svc.add(makeTask("df1", name=".gitignore"))
        t2 = makeTask("df2", name=".gitignore")
        svc.add(t2)
        assert t2.name == ".gitignore(1)"

    def test_no_extension(self, service):
        svc, _ = service
        svc.add(makeTask("ne1", name="README"))
        t2 = makeTask("ne2", name="README")
        svc.add(t2)
        assert t2.name == "README(1)"


@dataclass(kw_only=True)
class SubtitleStep(TaskStep):
    stepIndex: int = 1

    @property
    def outputPath(self) -> str:
        return str(self.task.outputFolder / f"{Path(self.task.name).stem}.en.srt")

    async def run(self, reportSpeed, waitForSpeedLimit):
        pass


def makeVideoTask(taskId: str, name: str = "a.mp4") -> Task:
    return Task(name=name, url="http://test/a", packId="test", taskId=taskId,
                steps=[StubStep(stepIndex=0), SubtitleStep()])


class TestNameConflict:

    def test_record_whose_file_was_deleted_gives_up_its_name(self, service, tmp_path):
        svc, _ = service
        old = makeTask("old", name="same.zip")
        svc.add(old)
        old.setStatus(TaskStatus.COMPLETED)
        (tmp_path / "same.zip").unlink()

        new = makeTask("new", name="same.zip")
        svc.add(new)

        assert new.name == "same.zip"
        assert svc.taskById("old") is None

    def test_new_task_never_starts_from_progress_of_paused_task_whose_file_was_deleted(self, service, tmp_path):
        svc, _ = service
        old = makeTask("old", name="same.zip")
        svc.add(old)
        old.setStatus(TaskStatus.PAUSED)
        (tmp_path / "same.zip.ghd").write_bytes(b"old progress")
        (tmp_path / "same.zip").unlink()

        new = makeTask("new", name="same.zip")
        svc.add(new)

        assert not (tmp_path / f"{new.name}.ghd").exists()

    def test_new_task_never_starts_from_leftover_progress(self, service, tmp_path):
        svc, _ = service
        (tmp_path / "same.zip.ghd").write_bytes(b"leftover progress")

        new = makeTask("new", name="same.zip")
        svc.add(new)

        assert not (tmp_path / f"{new.name}.ghd").exists()

    def test_saved_unfinished_task_still_holds_its_name_after_restart(self, qapp, monkeypatch, platform, speedMeter, tmp_path):
        import app.services.task_service as taskServiceModule
        monkeypatch.setattr(taskServiceModule, "APP_DATA_DIR", tmp_path / "data")

        def startService():
            svc = TaskService(StubCoroutineRunner(), StubCategoryService(), speedMeter, StubFileWatcher(),
                              deleteRecoverably=platform.deleteRecoverably,
                              nameConflictChoice=lambda: platform.choice)
            svc.resumeSaved()
            return svc

        before = startService()
        saved = makeTask("saved", name="same.zip")
        saved.outputFolder = tmp_path
        before.add(saved, autoStart=False)
        saved.setStatus(TaskStatus.PAUSED)
        before.flush()

        after = startService()
        platform.choice = NameConflictChoice.OVERWRITE
        new = makeTask("new", name="same.zip")
        new.outputFolder = tmp_path
        after.add(new)

        assert new.name == "same(1).zip"
        assert platform.trashed == []

    def test_ask_hands_foreign_file_conflict_to_user(self, service, platform, tmp_path, qtbot):
        svc, _ = service
        platform.choice = NameConflictChoice.ASK
        (tmp_path / "setup.exe").write_bytes(b"mine")
        task = makeTask("ask", name="setup.exe")

        with qtbot.waitSignal(svc.nameConflicted, timeout=1000) as blocker:
            isAdded = svc.add(task)

        assert not isAdded
        assert blocker.args == [task]
        assert svc.taskById("ask") is None
        assert sorted(p.name for p in tmp_path.iterdir()) == ["setup.exe"]

    def test_unfinished_task_holding_name_always_keeps_both(self, service, platform, qtbot):
        svc, _ = service
        platform.choice = NameConflictChoice.ASK
        svc.add(makeTask("first", name="same.zip"))
        second = makeTask("second", name="same.zip")

        with qtbot.assertNotEmitted(svc.nameConflicted):
            isAdded = svc.add(second)

        assert isAdded
        assert second.name == "same(1).zip"

    def test_overwrite_recycles_old_file_and_replaces_its_record(self, service, platform, tmp_path):
        svc, _ = service
        old = makeTask("old", name="setup.exe")
        svc.add(old)
        old.setStatus(TaskStatus.COMPLETED)
        (tmp_path / "setup.exe").write_bytes(b"v1")
        platform.choice = NameConflictChoice.OVERWRITE

        new = makeTask("new", name="setup.exe")
        svc.add(new)

        assert new.name == "setup.exe"
        assert platform.trashed == [tmp_path / "setup.exe"]
        assert svc.taskById("old") is None

    def test_overwrite_keeps_both_when_recycle_bin_is_unavailable(self, service, platform, tmp_path, qtbot):
        svc, _ = service
        (tmp_path / "setup.exe").write_bytes(b"mine")
        platform.choice = NameConflictChoice.OVERWRITE
        platform.canTrash = False
        task = makeTask("new", name="setup.exe")

        with qtbot.waitSignal(svc.overwriteFailed, timeout=1000) as blocker:
            svc.add(task)

        assert blocker.args == [task]
        assert task.name == "setup(1).exe"
        assert (tmp_path / "setup.exe").read_bytes() == b"mine"

    def test_probeConflict_reports_taken_side_file_without_creating_anything(self, service, tmp_path):
        svc, _ = service
        (tmp_path / "a.en.srt").write_bytes(b"mine")
        svc.add(makeTask("busy", name="b.zip"))

        assert svc.probeConflict(makeVideoTask("v")) == tmp_path / "a.en.srt"
        assert svc.probeConflict(makeTask("b", name="b.zip")) is None
        assert sorted(p.name for p in tmp_path.iterdir()) == ["a.en.srt", "b.zip"]

    def test_probeConflict_looks_where_the_category_puts_the_task(self, service, tmp_path):
        svc, _ = service
        categoryFolder = tmp_path / "video"
        categoryFolder.mkdir()
        (categoryFolder / "a.zip").write_bytes(b"mine")
        svc._categoryService.outputFolderOf = lambda task: (task.category, categoryFolder)

        assert svc.probeConflict(makeTask("c", name="a.zip")) == categoryFolder / "a.zip"

    def test_taken_side_file_numbers_whole_group(self, service, tmp_path):
        svc, _ = service
        (tmp_path / "a.en.srt").write_bytes(b"mine")
        task = makeVideoTask("v")

        svc.add(task)

        assert task.name == "a(1).mp4"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["a(1).en.srt", "a(1).mp4", "a.en.srt"]


class TestAdd:

    def test_add_emits_signal(self, service, qtbot):
        svc, runner = service
        with qtbot.waitSignal(svc.taskAdded, timeout=1000) as blocker:
            task = makeTask()
            svc.add(task)
        assert blocker.args == [task]

    def test_add_schedules_task(self, service):
        svc, runner = service
        task = makeTask()
        svc.add(task)
        assert len(runner.dispatched) == 1

    def test_add_duplicate_rejected(self, service, qtbot):
        svc, runner = service
        task = makeTask("dup")
        svc.add(task)
        with qtbot.assertNotEmitted(svc.taskAdded):
            svc.add(task)

    def test_task_in_store_after_add(self, service):
        svc, runner = service
        task = makeTask("stored")
        svc.add(task)
        assert svc.taskById("stored") is task

    def test_add_deferred_does_not_schedule(self, service):
        svc, runner = service
        task = makeTask("deferred")
        svc.add(task, autoStart=False)
        assert len(runner.dispatched) == 0
        assert svc.taskById("deferred") is task


class TestPause:

    def test_pause_emits_signal(self, service, qtbot):
        svc, runner = service
        task = makeTask("p1")
        svc.add(task)
        with qtbot.waitSignal(svc.taskPaused, timeout=1000) as blocker:
            svc.pause(task)
        assert blocker.args == [task]

    def test_pause_cancels_work(self, service):
        svc, runner = service
        task = makeTask("p2")
        svc.add(task)
        workId = runner.dispatched[-1][0]
        svc.pause(task)
        assert workId in runner.cancelled

    def test_pause_sets_status(self, service):
        svc, runner = service
        task = makeTask("p3")
        svc.add(task)
        svc.pause(task)
        assert task.status == TaskStatus.PAUSED


class TestStartAll:

    def test_covers_paused_waiting_and_failed_but_not_completed(self, service):
        svc, runner = service
        paused = makeTask("sa-paused")
        waiting = makeTask("sa-waiting")
        failed = makeTask("sa-failed")
        completed = makeTask("sa-completed")
        for task in (paused, waiting, failed, completed):
            svc.add(task, autoStart=False)
        paused.setStatus(TaskStatus.PAUSED)
        failed.setStatus(TaskStatus.FAILED)
        completed.setStatus(TaskStatus.COMPLETED)

        svc.startAll()

        assert len(runner.dispatched) == 3
        assert completed.status == TaskStatus.COMPLETED


class TestDelete:

    def test_delete_emits_signal(self, service, qtbot):
        svc, runner = service
        task = makeTask("d1")
        svc.add(task)
        with qtbot.waitSignal(svc.taskRemoved, timeout=1000) as blocker:
            svc.delete(task, shouldDeleteFiles=False)
        assert blocker.args == ["d1"]

    def test_delete_releases_placeholder_of_unfinished_task(self, service, tmp_path):
        svc, _ = service
        task = makeTask("d3", name="a.zip")
        svc.add(task)

        svc.delete(task, shouldDeleteFiles=False)

        assert list(tmp_path.iterdir()) == []

    def test_delete_removes_half_downloaded_product_of_unfinished_task(self, service, tmp_path):
        svc, _ = service
        task = makeTask("d6", name="a.zip")
        svc.add(task)
        (tmp_path / "a.zip").write_bytes(b"half")
        (tmp_path / "a.zip.ghd").write_bytes(b"offsets")

        svc.delete(task, shouldDeleteFiles=False)

        assert list(tmp_path.iterdir()) == []

    def test_delete_without_files_keeps_completed_product(self, service, tmp_path):
        svc, _ = service
        task = makeTask("d4", name="a.zip")
        svc.add(task)
        task.setStatus(TaskStatus.COMPLETED)
        (tmp_path / "a.zip").write_bytes(b"product")

        svc.delete(task, shouldDeleteFiles=False)

        assert (tmp_path / "a.zip").read_bytes() == b"product"

    def test_delete_with_files_removes_product_and_placeholder(self, service, tmp_path):
        svc, _ = service
        task = makeTask("d5", name="a.zip")
        svc.add(task)
        task.setStatus(TaskStatus.COMPLETED)
        (tmp_path / "a.zip").write_bytes(b"product")

        svc.delete(task, shouldDeleteFiles=True)

        assert list(tmp_path.iterdir()) == []

    def test_delete_removes_from_store(self, service):
        svc, runner = service
        task = makeTask("d2")
        svc.add(task)
        svc.delete(task, shouldDeleteFiles=False)
        assert svc.taskById("d2") is None


class TestQueue:

    def test_max_parallel_respected(self, service, monkeypatch):
        from app.config.cfg import cfg
        svc, runner = service
        monkeypatch.setattr(cfg.maxTaskNum, "value", 2)
        for i in range(5):
            svc.add(makeTask(f"q{i}"))
        assert svc.runningCount() == 2

    def test_pump_on_complete(self, service, monkeypatch):
        from app.config.cfg import cfg
        svc, runner = service
        monkeypatch.setattr(cfg.maxTaskNum, "value", 1)
        t1 = makeTask("pmp1")
        t2 = makeTask("pmp2")
        svc.add(t1)
        svc.add(t2)
        assert svc.runningCount() == 1
        _, done, _ = runner.dispatched[0]
        done(None)
        assert svc.runningCount() == 1
        assert len(runner.dispatched) == 2

    def test_all_completed_signal(self, service, monkeypatch, qtbot):
        from app.config.cfg import cfg
        svc, runner = service
        monkeypatch.setattr(cfg.maxTaskNum, "value", 1)
        task = makeTask("ac1")
        svc.add(task)
        with qtbot.waitSignal(svc.tasksAllCompleted, timeout=1000):
            _, done, _ = runner.dispatched[-1]
            done(None)


class TestTaskQueueMoveToFront:

    def make_queue(self, *ids):
        from app.services.task_service import TaskQueue
        q = TaskQueue()
        for tid in ids:
            q.wait(tid)
        return q

    def test_single_task_moved_to_front(self):
        q = self.make_queue("a", "b", "c")
        assert q.moveToFront(["c"])
        assert q.waitingOrder() == ["c", "a", "b"]

    def test_multiple_tasks_preserve_relative_order(self):
        q = self.make_queue("a", "b", "c", "d", "e")
        assert q.moveToFront(["c", "e"])
        assert q.waitingOrder() == ["c", "e", "a", "b", "d"]

    def test_already_at_front_is_noop(self):
        q = self.make_queue("a", "b", "c")
        assert q.moveToFront(["a"])
        assert q.waitingOrder() == ["a", "b", "c"]

    def test_none_in_queue_returns_false(self):
        q = self.make_queue("a", "b")
        assert not q.moveToFront(["x", "y"])
        assert q.waitingOrder() == ["a", "b"]

    def test_empty_ids_returns_false(self):
        q = self.make_queue("a", "b")
        assert not q.moveToFront([])
        assert q.waitingOrder() == ["a", "b"]

    def test_mix_of_queued_and_unknown_ids(self):
        q = self.make_queue("a", "b", "c")
        assert q.moveToFront(["x", "c", "z"])
        assert q.waitingOrder() == ["c", "a", "b"]

    def test_all_tasks_moved_preserves_order(self):
        q = self.make_queue("a", "b", "c")
        assert q.moveToFront(["a", "b", "c"])
        assert q.waitingOrder() == ["a", "b", "c"]

    def test_empty_queue_returns_false(self):
        q = self.make_queue()
        assert not q.moveToFront(["a"])

    def test_nextWaiting_respects_new_order(self):
        q = self.make_queue("a", "b", "c")
        q.moveToFront(["c"])
        assert q.nextWaiting() == "c"
        assert q.nextWaiting() == "a"
        assert q.nextWaiting() == "b"


class TestMoveToFront:

    def test_emits_queueChanged(self, service, monkeypatch, qtbot):
        from app.config.cfg import cfg
        svc, runner = service
        monkeypatch.setattr(cfg.maxTaskNum, "value", 1)
        t1 = makeTask("mf1")
        t2 = makeTask("mf2")
        t3 = makeTask("mf3")
        svc.add(t1)
        svc.add(t2)
        svc.add(t3)
        with qtbot.waitSignal(svc.queueChanged, timeout=1000):
            svc.moveToFront(["mf3"])

    def test_no_signal_when_none_in_queue(self, service, qtbot):
        svc, runner = service
        svc.add(makeTask("ns1"))
        with qtbot.assertNotEmitted(svc.queueChanged):
            svc.moveToFront(["nonexistent"])

    def test_next_dispatched_is_moved_task(self, service, monkeypatch):
        from app.config.cfg import cfg
        svc, runner = service
        monkeypatch.setattr(cfg.maxTaskNum, "value", 1)
        t1 = makeTask("nd1")
        t2 = makeTask("nd2")
        t3 = makeTask("nd3")
        svc.add(t1)
        svc.add(t2)
        svc.add(t3)
        svc.moveToFront(["nd3"])
        _, done, _ = runner.dispatched[0]
        done(None)
        assert len(runner.dispatched) >= 2
        dispatched_task = svc.taskById("nd3")
        assert dispatched_task.status == TaskStatus.RUNNING

    def test_waitingOrder_reflects_move(self, service, monkeypatch):
        from app.config.cfg import cfg
        svc, runner = service
        monkeypatch.setattr(cfg.maxTaskNum, "value", 1)
        svc.add(makeTask("wo1"))
        svc.add(makeTask("wo2"))
        svc.add(makeTask("wo3"))
        assert svc.waitingOrder() == ["wo2", "wo3"]
        svc.moveToFront(["wo3"])
        assert svc.waitingOrder() == ["wo3", "wo2"]

    def test_mixed_running_and_waiting_only_moves_waiting(self, service, monkeypatch):
        from app.config.cfg import cfg
        svc, runner = service
        monkeypatch.setattr(cfg.maxTaskNum, "value", 2)
        svc.add(makeTask("mx1"))
        svc.add(makeTask("mx2"))
        svc.add(makeTask("mx3"))
        svc.add(makeTask("mx4"))
        assert svc.waitingOrder() == ["mx3", "mx4"]
        svc.moveToFront(["mx1", "mx4"])
        assert svc.waitingOrder() == ["mx4", "mx3"]

    def test_all_running_no_signal(self, service, monkeypatch, qtbot):
        from app.config.cfg import cfg
        svc, runner = service
        monkeypatch.setattr(cfg.maxTaskNum, "value", 3)
        svc.add(makeTask("ar1"))
        svc.add(makeTask("ar2"))
        with qtbot.assertNotEmitted(svc.queueChanged):
            svc.moveToFront(["ar1", "ar2"])


class TestRedownload:

    def test_redownload_keeps_name_held(self, service, tmp_path):
        svc, _ = service
        task = makeTask("rd0", name="a.zip")
        svc.add(task)
        task.setStatus(TaskStatus.COMPLETED)
        (tmp_path / "a.zip").write_bytes(b"product")

        svc.redownload(task)

        assert (tmp_path / "a.zip").read_bytes() == b""

    def test_redownload_resets_and_reschedules(self, service):
        svc, runner = service
        task = makeTask("rd1")
        svc.add(task)
        initial_count = len(runner.submitted)
        task.steps[0].progress = 50
        task.steps[0].receivedBytes = 1024
        svc.redownload(task)
        assert task.steps[0].progress == 0
        assert task.steps[0].receivedBytes == 0
        assert len(runner.submitted) > initial_count


@dataclass(kw_only=True)
class LanguageStep(TaskStep):
    language: str = "en"

    @property
    def outputPath(self) -> str:
        return str(self.task.outputFolder / f"{Path(self.task.name).stem}.{self.language}.vtt")

    async def run(self, reportSpeed, waitForSpeedLimit):
        pass


@dataclass(kw_only=True, eq=False)
class SubtitledTask(Task):
    def setOptions(self, options: dict) -> None:
        super().setOptions(options)
        if "languages" in options:
            self.steps = [s for s in self.steps if not isinstance(s, LanguageStep)]
            for i, language in enumerate(options["languages"]):
                self.addStep(LanguageStep(stepIndex=10 + i, language=language))


def makeSubtitledTask(taskId: str) -> SubtitledTask:
    return SubtitledTask(name="a.mp4", url="http://test/a", packId="test", taskId=taskId,
                         steps=[StubStep(stepIndex=0), LanguageStep(stepIndex=10)])


class TestEdit:

    def test_edit_holds_side_file_of_added_language(self, service, tmp_path):
        svc, _ = service
        task = makeSubtitledTask("lang1")
        svc.add(task)

        svc.edit(task, {"languages": ["en", "fr"]})

        assert task.name == "a.mp4"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["a.en.vtt", "a.fr.vtt", "a.mp4"]

    def test_edit_numbers_whole_group_when_added_side_file_is_taken(self, service, tmp_path):
        svc, _ = service
        task = makeSubtitledTask("lang2")
        svc.add(task)
        task.setStatus(TaskStatus.COMPLETED)
        (tmp_path / "a.mp4").write_bytes(b"video")
        (tmp_path / "a.fr.vtt").write_bytes(b"mine")

        svc.edit(task, {"languages": ["en", "fr"]})

        assert task.name == "a(1).mp4"
        assert (tmp_path / "a(1).mp4").read_bytes() == b"video"
        assert (tmp_path / "a.fr.vtt").read_bytes() == b"mine"
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "a(1).en.vtt", "a(1).fr.vtt", "a(1).mp4", "a.fr.vtt"]

    def test_edit_move_releases_old_name_and_holds_new_one(self, service, platform, tmp_path, qtbot):
        svc, _ = service
        platform.choice = NameConflictChoice.ASK
        moved = makeTask("moved", name="a.zip")
        svc.add(moved)
        newFolder = tmp_path / "new"

        svc.edit(moved, {"outputFolder": newFolder})
        besideOld = makeTask("old", name="a.zip")
        besideNew = makeTask("new", name="a.zip")
        besideNew.outputFolder = newFolder
        with qtbot.assertNotEmitted(svc.nameConflicted):
            svc.add(besideOld)
            svc.add(besideNew)

        assert besideOld.name == "a.zip"
        assert besideNew.name == "a(1).zip"
        assert svc.taskById("moved") is moved

    def test_edit_releases_side_file_of_removed_language(self, service, tmp_path):
        svc, _ = service
        task = makeSubtitledTask("lang3")
        svc.add(task)

        svc.edit(task, {"languages": []})

        assert sorted(p.name for p in tmp_path.iterdir()) == ["a.mp4"]

    def test_edit_moves_product_into_new_folder_beside_existing_file(self, service, tmp_path):
        svc, _ = service
        task = makeTask("mv", name="a.zip")
        svc.add(task)
        task.setStatus(TaskStatus.COMPLETED)
        (tmp_path / "a.zip").write_bytes(b"product")
        newFolder = tmp_path / "new"
        newFolder.mkdir()
        (newFolder / "a.zip").write_bytes(b"mine")

        svc.edit(task, {"outputFolder": str(newFolder)})

        assert task.name == "a(1).zip"
        assert (newFolder / "a(1).zip").read_bytes() == b"product"
        assert (newFolder / "a.zip").read_bytes() == b"mine"
        assert not (tmp_path / "a.zip").exists()

    def test_edit_moves_unfinished_product_with_its_record(self, service, tmp_path):
        svc, _ = service
        task = makeTask("mv2", name="a.zip")
        svc.add(task)
        (tmp_path / "a.zip").write_bytes(b"half")
        (tmp_path / "a.zip.ghd").write_bytes(b"offsets")
        newFolder = tmp_path / "new"

        svc.edit(task, {"outputFolder": str(newFolder)})

        assert (newFolder / "a.zip").read_bytes() == b"half"
        assert (newFolder / "a.zip.ghd").read_bytes() == b"offsets"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["new"]

    def test_edit_applies_options(self, service):
        svc, runner = service
        task = makeTask("ed1")
        task.category = "audio"
        svc.add(task)
        svc.edit(task, {"category": "document"})
        assert task.category == "document"

    def test_edit_reschedules(self, service):
        svc, runner = service
        task = makeTask("ed2")
        svc.add(task)
        initial_count = len(runner.submitted)
        svc.edit(task, {})
        assert len(runner.submitted) > initial_count


@dataclass(kw_only=True, eq=False)
class SeedTask(Task):
    canSeed = True

    def __post_init__(self):
        super().__post_init__()
        self.seedingCalls: list[bool] = []

    def runSeeding(self, isManual):
        self.seedingCalls.append(isManual)
        return StubStep(stepIndex=0).run(None, None)


def makeSeedTask(taskId: str, tmp_path: Path) -> SeedTask:
    task = SeedTask(name=f"{taskId}.bin", url="magnet:?xt=urn:btih:x", packId="bt",
                    taskId=taskId, steps=[StubStep(stepIndex=0)], outputFolder=tmp_path)
    return task


def finishRun(runner, task):
    workId, done, _ = runner.dispatched[-1]
    task.setStatus(TaskStatus.COMPLETED)
    done(None)
    return workId


class TestSeeding:

    def test_completed_run_frees_slot_and_starts_seeding(self, service, tmp_path, qtbot):
        svc, runner = service
        task = makeSeedTask("sd1", tmp_path)
        svc.add(task)
        with qtbot.waitSignal(svc.seedingStarted, timeout=1000), \
                qtbot.waitSignal(svc.tasksAllCompleted, timeout=1000):
            finishRun(runner, task)
        assert task.status == TaskStatus.COMPLETED
        assert task.isSeeding
        assert task.seedingCalls == [False]
        assert svc.runningCount() == 0

    def test_seeding_does_not_block_queue(self, service, tmp_path, monkeypatch):
        from app.config.cfg import cfg
        svc, runner = service
        monkeypatch.setattr(cfg.maxTaskNum, "value", 1)
        seed = makeSeedTask("sd2", tmp_path)
        other = makeTask("sd2-other")
        svc.add(seed)
        svc.add(other)
        finishRun(runner, seed)
        assert other.status == TaskStatus.RUNNING

    def test_task_that_cannot_seed_does_not_seed(self, service):
        svc, runner = service
        task = makeTask("sd3")
        svc.add(task)
        count = len(runner.dispatched)
        finishRun(runner, task)
        assert not task.isSeeding
        assert len(runner.dispatched) == count

    def test_should_not_seed_skips_seeding(self, service, tmp_path):
        svc, runner = service
        task = makeSeedTask("sd4", tmp_path)
        svc.add(task)
        task.shouldSeed = False
        finishRun(runner, task)
        assert not task.isSeeding
        assert task.seedingCalls == []

    def test_stop_seeding_cancels_and_remembers(self, service, tmp_path, qtbot):
        svc, runner = service
        task = makeSeedTask("sd5", tmp_path)
        svc.add(task)
        finishRun(runner, task)
        seedingWorkId = runner.submitted[-1][0]
        with qtbot.waitSignal(svc.seedingStopped, timeout=1000):
            svc.stopSeeding(task)
        assert seedingWorkId in runner.cancelled
        assert not task.isSeeding
        assert not task.shouldSeed
        assert task.status == TaskStatus.COMPLETED

    def test_start_seeding_is_manual(self, service, tmp_path):
        svc, runner = service
        task = makeSeedTask("sd6", tmp_path)
        svc.add(task)
        task.shouldSeed = False
        finishRun(runner, task)
        svc.startSeeding(task)
        assert task.isSeeding
        assert task.shouldSeed
        assert task.seedingCalls == [True]
        assert svc.runningCount() == 0

    def test_seeding_ending_by_itself_is_remembered(self, service, tmp_path, qtbot):
        svc, runner = service
        task = makeSeedTask("sd7", tmp_path)
        svc.add(task)
        finishRun(runner, task)
        _, done, _ = runner.submitted[-1]
        with qtbot.waitSignal(svc.seedingStopped, timeout=1000):
            done(None)
        assert not task.isSeeding
        assert not task.shouldSeed

    def test_seeding_failure_keeps_wish(self, service, tmp_path):
        svc, runner = service
        task = makeSeedTask("sd8", tmp_path)
        svc.add(task)
        finishRun(runner, task)
        _, _, failed = runner.submitted[-1]
        failed(RuntimeError("tracker"))
        assert not task.isSeeding
        assert task.shouldSeed
        assert task.status == TaskStatus.COMPLETED

    def test_delete_stops_seeding(self, service, tmp_path):
        svc, runner = service
        task = makeSeedTask("sd9", tmp_path)
        svc.add(task)
        finishRun(runner, task)
        seedingWorkId = runner.submitted[-1][0]
        svc.delete(task, shouldDeleteFiles=False)
        assert seedingWorkId in runner.cancelled

    def test_redownload_stops_seeding_and_restores_wish(self, service, tmp_path):
        svc, runner = service
        task = makeSeedTask("sd10", tmp_path)
        svc.add(task)
        finishRun(runner, task)
        svc.stopSeeding(task)
        svc.startSeeding(task)
        seedingWorkId = runner.submitted[-1][0]
        task.shouldSeed = False
        svc.redownload(task)
        assert seedingWorkId in runner.cancelled
        assert task.shouldSeed
        assert task.status == TaskStatus.RUNNING

    def test_revive_stops_seeding_before_run(self, service, tmp_path):
        from app.models.task import TaskFile
        svc, runner = service
        task = makeSeedTask("sd11", tmp_path)
        task.files = [TaskFile(index=0, relativePath="a", completed=True),
                      TaskFile(index=1, relativePath="b", selected=False)]
        svc.add(task)
        finishRun(runner, task)
        seedingWorkId = runner.submitted[-1][0]
        task.setSelection = lambda indexes: setattr(task.files[1], "selected", True)
        svc.updateSelection(task, {0, 1})
        assert seedingWorkId in runner.cancelled
        assert not task.isSeeding
        assert runner.submitted[-1][0] != seedingWorkId

    def test_saved_seeding_task_resumes_seeding(self, service, tmp_path):
        svc, runner = service
        task = makeSeedTask("sd12", tmp_path)
        task.shouldSeed = True
        task.setStatus(TaskStatus.COMPLETED)
        (tmp_path / task.name).touch()
        svc._store.loadSaved = lambda: [task]
        svc.resumeSaved()
        assert task.isSeeding
        assert task.seedingCalls == [False]

    def test_saved_task_with_missing_file_does_not_seed(self, service, tmp_path):
        svc, runner = service
        task = makeSeedTask("sd13", tmp_path)
        task.setStatus(TaskStatus.COMPLETED)
        svc._store.loadSaved = lambda: [task]
        svc.resumeSaved()
        assert not task.isSeeding

    def test_file_disappearing_stops_seeding(self, service, tmp_path):
        svc, runner = service
        task = makeSeedTask("sd14", tmp_path)
        svc.add(task)
        finishRun(runner, task)
        seedingWorkId = runner.submitted[-1][0]
        Path(task.outputPath).unlink()
        svc._onWatchedFileChanged(task.outputPath)
        assert seedingWorkId in runner.cancelled
        assert not task.isSeeding
        assert task.shouldSeed

    def test_seeding_state_is_not_persisted(self, tmp_path):
        task = makeSeedTask("sd15", tmp_path)
        task.shouldSeed = True
        task.isSeeding = True
        data = task.toDict()
        assert "isSeeding" not in data
        assert data["shouldSeed"] is True

    def test_new_task_wants_seeding(self, service, tmp_path):
        svc, runner = service
        task = makeSeedTask("sd16", tmp_path)
        svc.add(task)
        assert task.shouldSeed

    def test_record_from_before_seeding_existed_does_not_seed(self, service, tmp_path):
        svc, runner = service
        old = makeSeedTask("sd17", tmp_path)
        old.setStatus(TaskStatus.COMPLETED)
        record = old.toDict()
        record.pop("shouldSeed")
        restored = SeedTask.fromDict(record)
        (tmp_path / restored.name).touch()
        svc._store.loadSaved = lambda: [restored]
        svc.resumeSaved()
        assert not restored.shouldSeed
        assert not restored.isSeeding

    def test_stale_run_done_after_revive_does_not_seed(self, service, tmp_path):
        from app.models.task import TaskFile
        svc, runner = service
        task = makeSeedTask("sd18", tmp_path)
        task.files = [TaskFile(index=0, relativePath="a", completed=True),
                      TaskFile(index=1, relativePath="b", selected=False)]
        svc.add(task)
        _, staleDone, _ = runner.dispatched[-1]
        task.setStatus(TaskStatus.COMPLETED)

        def select(indexes):
            task.files[1].selected = True
            task.steps[0].status = TaskStatus.WAITING
            task.updateStatus()
        task.setSelection = select
        svc.updateSelection(task, {0, 1})
        assert task.status == TaskStatus.RUNNING

        staleDone(None)
        assert not task.isSeeding


class TestSpeedMeter:
    """速度表在有任务下载或做种时走表，驱动速度显示和任务进度推送。"""

    def test_meter_stops_when_last_running_task_is_paused(self, service, speedMeter):
        svc, runner = service
        task = makeTask("sm0")
        svc.add(task)
        assert speedMeter.isRunning
        svc.pause(task)
        assert not speedMeter.isRunning

    def test_meter_keeps_running_while_seeding(self, service, speedMeter, tmp_path):
        svc, runner = service
        task = makeSeedTask("sm1", tmp_path)
        svc.add(task)
        finishRun(runner, task)
        assert task.isSeeding
        assert speedMeter.isRunning
        assert "stop" not in speedMeter.calls

    def test_meter_stops_when_seeding_stops_and_nothing_runs(self, service, speedMeter, tmp_path):
        svc, runner = service
        task = makeSeedTask("sm2", tmp_path)
        svc.add(task)
        finishRun(runner, task)
        svc.stopSeeding(task)
        assert not speedMeter.isRunning

    def test_meter_keeps_running_when_seeding_stops_but_a_download_runs(self, service, speedMeter, tmp_path):
        svc, runner = service
        seed = makeSeedTask("sm3", tmp_path)
        svc.add(seed)
        finishRun(runner, seed)
        svc.add(makeTask("sm3-other"))
        svc.stopSeeding(seed)
        assert speedMeter.isRunning

    def test_meter_starts_for_seeding_restored_at_launch(self, service, speedMeter, tmp_path):
        svc, runner = service
        task = makeSeedTask("sm4", tmp_path)
        task.shouldSeed = True
        task.setStatus(TaskStatus.COMPLETED)
        (tmp_path / task.name).touch()
        svc._store.loadSaved = lambda: [task]
        svc.resumeSaved()
        assert speedMeter.isRunning
