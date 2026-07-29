"""TaskService 生命周期的逐分支测试。

Seam S7: TaskService.add/pause/delete/redownload/edit/queue
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.models.task import Task, TaskStep, TaskStatus


# ── Stubs ──


@dataclass(kw_only=True)
class StubStep(TaskStep):
    stepIndex: int = 0

    async def run(self, reportSpeed, waitForSpeedLimit):
        pass


class StubCoroutineRunner:
    def __init__(self):
        self.submitted: list[tuple[str, object]] = []
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

    def addSpeed(self, n):
        pass

    async def waitForSpeedLimit(self):
        pass


class StubCategoryService:
    def categoryOf(self, task):
        return "video"

    def folderOf(self, categoryId):
        return None


class StubSpeedMeter:
    def addSpeed(self, n):
        pass

    async def waitForSpeedLimit(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass


# ── Fixtures ──


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def service(qapp, monkeypatch, tmp_path):
    from app.config.cfg import cfg
    monkeypatch.setattr(cfg.maxTaskNum, "value", 3)
    monkeypatch.setattr(cfg.isCategoryEnabled, "value", False)
    monkeypatch.setattr(cfg.downloadFolder, "value", str(tmp_path))

    runner = StubCoroutineRunner()
    category = StubCategoryService()
    speed = StubSpeedMeter()
    svc = TaskService(runner, category, speed)
    return svc, runner


def makeTask(taskId: str = "t1", name: str = "test.zip") -> Task:
    step = StubStep(stepIndex=0)
    task = Task(name=name, url="http://test/file.zip", packId="http",
                taskId=taskId, steps=[step])
    step._bindTask(task)
    return task


from app.services.task_service import TaskService


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


# ── S7: _deduplicateOutput ──


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

    def test_ghd_conflict_renames(self, service, tmp_path):
        svc, _ = service
        (tmp_path / "partial.zip.ghd").touch()
        task = makeTask("gh1", name="partial.zip")
        svc.add(task)
        assert task.name == "partial(1).zip"

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


# ── S7: add ──


class TestAdd:

    def test_add_emits_signal(self, service):
        svc, runner = service
        spy = MagicMock()
        svc.taskAdded.connect(spy)
        task = makeTask()
        svc.add(task)
        spy.assert_called_once_with(task)

    def test_add_schedules_task(self, service):
        svc, runner = service
        task = makeTask()
        svc.add(task)
        assert len(runner.submitted) == 1

    def test_add_duplicate_rejected(self, service):
        svc, runner = service
        task = makeTask("dup")
        svc.add(task)
        spy = MagicMock()
        svc.taskAdded.connect(spy)
        svc.add(task)
        spy.assert_not_called()

    def test_task_in_store_after_add(self, service):
        svc, runner = service
        task = makeTask("stored")
        svc.add(task)
        assert svc.taskById("stored") is task

    def test_add_deferred_does_not_schedule(self, service):
        svc, runner = service
        task = makeTask("deferred")
        svc.add(task, autoStart=False)
        assert len(runner.submitted) == 0
        assert svc.taskById("deferred") is task


# ── S7: pause ──


class TestPause:

    def test_pause_emits_signal(self, service):
        svc, runner = service
        task = makeTask("p1")
        svc.add(task)
        spy = MagicMock()
        svc.taskPaused.connect(spy)
        svc.pause(task)
        spy.assert_called_once_with(task)

    def test_pause_cancels_work(self, service):
        svc, runner = service
        task = makeTask("p2")
        svc.add(task)
        workId = runner.submitted[-1][0]
        svc.pause(task)
        assert workId in runner.cancelled

    def test_pause_sets_status(self, service):
        svc, runner = service
        task = makeTask("p3")
        svc.add(task)
        svc.pause(task)
        assert task.status == TaskStatus.PAUSED


# ── S7: delete ──


class TestDelete:

    def test_delete_emits_signal(self, service):
        svc, runner = service
        task = makeTask("d1")
        svc.add(task)
        spy = MagicMock()
        svc.taskRemoved.connect(spy)
        svc.delete(task, shouldDeleteFiles=False)
        spy.assert_called_once_with("d1")

    def test_delete_removes_from_store(self, service):
        svc, runner = service
        task = makeTask("d2")
        svc.add(task)
        svc.delete(task, shouldDeleteFiles=False)
        assert svc.taskById("d2") is None


# ── S7: queue ──


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
        _, done, _ = runner.submitted[0]
        done(None)
        assert svc.runningCount() == 1
        assert len(runner.submitted) == 2

    def test_all_completed_signal(self, service, monkeypatch):
        from app.config.cfg import cfg
        svc, runner = service
        monkeypatch.setattr(cfg.maxTaskNum, "value", 1)
        task = makeTask("ac1")
        svc.add(task)
        spy = MagicMock()
        svc.tasksAllCompleted.connect(spy)
        _, done, _ = runner.submitted[-1]
        done(None)
        spy.assert_called_once()


# ── S7: TaskQueue.moveToFront ──


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


# ── S7: TaskService.moveToFront ──


class TestMoveToFront:

    def test_emits_queueChanged(self, service, monkeypatch):
        from app.config.cfg import cfg
        svc, runner = service
        monkeypatch.setattr(cfg.maxTaskNum, "value", 1)
        t1 = makeTask("mf1")
        t2 = makeTask("mf2")
        t3 = makeTask("mf3")
        svc.add(t1)
        svc.add(t2)
        svc.add(t3)
        spy = MagicMock()
        svc.queueChanged.connect(spy)
        svc.moveToFront(["mf3"])
        spy.assert_called_once()

    def test_no_signal_when_none_in_queue(self, service):
        svc, runner = service
        svc.add(makeTask("ns1"))
        spy = MagicMock()
        svc.queueChanged.connect(spy)
        svc.moveToFront(["nonexistent"])
        spy.assert_not_called()

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
        _, done, _ = runner.submitted[0]
        done(None)
        assert runner.submitted[1][0] is not None
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

    def test_all_running_no_signal(self, service, monkeypatch):
        from app.config.cfg import cfg
        svc, runner = service
        monkeypatch.setattr(cfg.maxTaskNum, "value", 3)
        svc.add(makeTask("ar1"))
        svc.add(makeTask("ar2"))
        spy = MagicMock()
        svc.queueChanged.connect(spy)
        svc.moveToFront(["ar1", "ar2"])
        spy.assert_not_called()


# ── S7: redownload ──


class TestRedownload:

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


# ── S7: edit ──


class TestEdit:

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
