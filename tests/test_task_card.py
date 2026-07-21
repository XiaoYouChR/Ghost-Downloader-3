"""TaskCard.refresh() 回归测试 — 历史上断过 2 次。

Seam S10: refresh() 在所有状态 × fileSize 组合下不抛异常。
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.models.task import Task, TaskStep, TaskStatus, StepError


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


class StubTaskService:
    def pause(self, task): pass
    def start(self, task): pass
    def delete(self, task, **kw): pass
    def redownload(self, task): pass
    def setCategory(self, task, cat): pass


class StubFeatureService:
    def editCards(self, task, parent=None):
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

    def categoryById(self, cid):
        return None

    def categories(self):
        return []


_stubCategoryService = None

def makeCard(qapp, status, fileSize=1000, withError=False):
    from app.view.cards.task_cards import TaskCard
    global _stubCategoryService
    if _stubCategoryService is None:
        _stubCategoryService = StubCategoryService()

    step = StubStep(stepIndex=0, status=status)
    if status == TaskStatus.COMPLETED:
        step.progress = 100
        step.receivedBytes = fileSize
    if withError:
        step.error = StepError("测试错误")

    task = Task(name="test.txt", url="http://test", packId="test",
                steps=[step], fileSize=fileSize)
    step._bindTask(task)
    task.updateStatus()

    card = TaskCard(task, StubTaskService(), StubFeatureService(), _stubCategoryService)
    return card


ALL_STATUSES = [
    TaskStatus.WAITING,
    TaskStatus.RUNNING,
    TaskStatus.PAUSED,
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
]


class TestRefreshNoCrash:

    @pytest.mark.parametrize("status", ALL_STATUSES, ids=lambda s: s.name)
    def test_refresh_with_filesize(self, qapp, status):
        card = makeCard(qapp, status, fileSize=1024)
        card.refresh()
        card.refresh(force=True)

    @pytest.mark.parametrize("status", ALL_STATUSES, ids=lambda s: s.name)
    def test_refresh_zero_filesize(self, qapp, status):
        card = makeCard(qapp, status, fileSize=0)
        card.refresh()
        card.refresh(force=True)

    def test_refresh_failed_with_error(self, qapp):
        card = makeCard(qapp, TaskStatus.FAILED, withError=True)
        card.refresh()

    def test_refresh_failed_without_error(self, qapp):
        card = makeCard(qapp, TaskStatus.FAILED, withError=False)
        card.refresh()

    def test_refresh_skips_unchanged_non_running(self, qapp):
        card = makeCard(qapp, TaskStatus.PAUSED)
        card.refresh()
        card.refresh()

    def test_refresh_always_runs_for_running(self, qapp):
        card = makeCard(qapp, TaskStatus.RUNNING)
        card.refresh()
        card.refresh()

    def test_progress_bar_visible_when_created_during_running(self, qapp):
        card = makeCard(qapp, TaskStatus.RUNNING)
        card.refresh()
        assert not card.progressBar.isHidden()
        assert card.statusLabel.isHidden()

    def test_progress_bar_hidden_when_completed(self, qapp):
        card = makeCard(qapp, TaskStatus.COMPLETED)
        card.refresh()
        assert card.progressBar.isHidden()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
