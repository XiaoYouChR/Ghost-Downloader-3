"""TaskPage _runningIds 刷新机制测试。

Seam S11: taskStarted/Stopped → 精确刷新 running cards。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest

from app.models.task import Task, TaskStep, TaskStatus


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@dataclass(kw_only=True)
class StubStep(TaskStep):
    stepIndex: int = 0

    async def run(self, reportSpeed, waitForSpeedLimit):
        pass


def makeTask(taskId="tsk_1", status=TaskStatus.WAITING):
    step = StubStep(stepIndex=0, status=status)
    task = Task(name="test", url="http://test", packId="test",
                taskId=taskId, steps=[step])
    step._bindTask(task)
    task.updateStatus()
    return task


class StubTaskService:
    def __init__(self):
        from PySide6.QtCore import Signal, QObject
        class _Signals(QObject):
            taskAdded = Signal(object)
            taskRemoved = Signal(str)
            taskStarted = Signal(object)
            taskPaused = Signal(object)
            taskCompleted = Signal(object)
            taskFailed = Signal(object)
            tasksAllCompleted = Signal()
            fileDisappeared = Signal(object)
            diskSpaceInsufficient = Signal(int, int)
        self._signals = _Signals()
        self.tasks = []

    def __getattr__(self, name):
        return getattr(self._signals, name)

    def runningCount(self):
        return sum(1 for t in self.tasks if t.status == TaskStatus.RUNNING)

    def runningProgress(self):
        return -1.0


class StubFeatureService:
    def taskCard(self, task, parent=None):
        return None

    def pages(self):
        return []

    def settingGroups(self, parent):
        return []

    def runtimes(self):
        return []


class StubCategoryService:
    def __init__(self):
        from PySide6.QtCore import Signal, QObject
        class _Obj(QObject):
            categoriesChanged = Signal()
        self._obj = _Obj()

    @property
    def categoriesChanged(self):
        return self._obj.categoriesChanged

    def categories(self):
        return []

    def categoryById(self, cid):
        return None


class StubSpeedMeter:
    def __init__(self):
        from PySide6.QtCore import Signal, QObject
        class _Obj(QObject):
            speedChanged = Signal(int)
        self._obj = _Obj()

    @property
    def speedChanged(self):
        return self._obj.speedChanged


class StubCoroutineRunner:
    def submit(self, *a, **kw):
        return "work_1"

    def cancel(self, *a, **kw):
        pass


class TestRunningIds:

    @pytest.fixture
    def page(self, qapp):
        from app.view.pages.task_page import TaskPage
        ts = StubTaskService()
        page = TaskPage(
            taskService=ts,
            featureService=StubFeatureService(),
            categoryService=StubCategoryService(),
            speedMeter=StubSpeedMeter(),
            coroutineRunner=StubCoroutineRunner(),
        )
        return page, ts

    def test_initial_running_ids_empty(self, page):
        p, ts = page
        assert p._runningIds == set()

    def test_task_started_adds_to_running(self, page):
        p, ts = page
        task = makeTask("tsk_a", TaskStatus.RUNNING)
        ts.taskStarted.emit(task)
        assert "tsk_a" in p._runningIds

    def test_task_completed_removes_from_running(self, page):
        p, ts = page
        task = makeTask("tsk_a", TaskStatus.RUNNING)
        ts.taskStarted.emit(task)
        assert "tsk_a" in p._runningIds
        task.setStatus(TaskStatus.COMPLETED)
        ts.taskCompleted.emit(task)
        assert "tsk_a" not in p._runningIds

    def test_task_failed_removes_from_running(self, page):
        p, ts = page
        task = makeTask("tsk_b", TaskStatus.RUNNING)
        ts.taskStarted.emit(task)
        task.setStatus(TaskStatus.FAILED)
        ts.taskFailed.emit(task)
        assert "tsk_b" not in p._runningIds

    def test_task_paused_removes_from_running(self, page):
        p, ts = page
        task = makeTask("tsk_c", TaskStatus.RUNNING)
        ts.taskStarted.emit(task)
        task.setStatus(TaskStatus.PAUSED)
        ts.taskPaused.emit(task)
        assert "tsk_c" not in p._runningIds

    def test_all_completed_clears_running(self, page):
        p, ts = page
        for i in range(3):
            ts.taskStarted.emit(makeTask(f"tsk_{i}", TaskStatus.RUNNING))
        assert len(p._runningIds) == 3
        ts.tasksAllCompleted.emit()
        assert p._runningIds == set()

    def test_timer_started_on_task_start(self, page):
        p, ts = page
        assert not p._cardRefreshTimer.isActive()
        ts.taskStarted.emit(makeTask("tsk_x", TaskStatus.RUNNING))
        assert p._cardRefreshTimer.isActive()

    def test_timer_stopped_when_last_task_stops(self, page):
        p, ts = page
        task = makeTask("tsk_y", TaskStatus.RUNNING)
        ts.taskStarted.emit(task)
        assert p._cardRefreshTimer.isActive()
        task.setStatus(TaskStatus.COMPLETED)
        ts.taskCompleted.emit(task)
        assert not p._cardRefreshTimer.isActive()

    def test_timer_stopped_on_all_completed(self, page):
        p, ts = page
        ts.taskStarted.emit(makeTask("tsk_z", TaskStatus.RUNNING))
        assert p._cardRefreshTimer.isActive()
        ts.tasksAllCompleted.emit()
        assert not p._cardRefreshTimer.isActive()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
