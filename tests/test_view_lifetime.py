from __future__ import annotations

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from app.signal import Signal


class FakeTaskService:
    taskAdded = Signal(object)
    taskRemoved = Signal(object)
    taskStarted = Signal(object)
    taskPaused = Signal(object)
    taskCompleted = Signal(object)
    taskFailed = Signal(object)
    seedingStarted = Signal(object)
    seedingStopped = Signal(object)
    checksumStarted = Signal(object)
    checksumCompleted = Signal(object, str)
    checksumStopped = Signal(object, object)
    queueChanged = Signal()
    fileDisappeared = Signal(object)
    fileDeleteDenied = Signal(object)
    nameConflicted = Signal(object)
    overwriteFailed = Signal(object)
    tasks = []

    def waitingOrder(self):
        return []


class FakeSpeedMeter:
    speedChanged = Signal(int)
    currentSpeed = 0


class FakeCategoryService:
    categoriesChanged = Signal()

    def categories(self):
        return []


class FakeFeatureService:
    packs = []


def test_deleted_task_page_kept_alive_by_its_window_ignores_speed_ticks(qapp):
    from app.view.pages.task_page import TaskPage

    speedMeter, categoryService = FakeSpeedMeter(), FakeCategoryService()
    page = TaskPage(FakeTaskService(), FakeFeatureService(), categoryService, speedMeter)
    page.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    speedMeter.speedChanged.emit(100)
    categoryService.categoriesChanged.emit()
