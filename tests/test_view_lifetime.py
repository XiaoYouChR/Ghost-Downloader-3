from __future__ import annotations

from unittest.mock import Mock

import pytest
from PySide6.QtCore import QEvent, QTimer, Qt
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


@pytest.mark.parametrize("shouldConfirm", [False, True])
def test_clear_history_dialog_only_clears_after_confirmation(qtbot, monkeypatch, shouldConfirm):
    from qfluentwidgets import MessageBox
    from qfluentwidgets.components.dialog_box.mask_dialog_base import MaskDialogBase

    from app.view.components import dialog_animation
    from app.view.pages.task_page import TaskPage

    monkeypatch.setattr(MaskDialogBase, "slideEdge", None, raising=False)
    monkeypatch.setattr(MaskDialogBase, "showEvent", dialog_animation.showEvent)
    monkeypatch.setattr(MaskDialogBase, "done", dialog_animation.done)
    service = FakeTaskService()
    service.clearHistory = Mock()
    page = TaskPage(service, FakeFeatureService(), FakeCategoryService(), FakeSpeedMeter())
    qtbot.addWidget(page)
    page.resize(960, 540)
    page.show()
    clicked = []

    def onDialogOpened():
        dialog = next(widget for widget in page.findChildren(MessageBox) if widget.isVisible())
        button = dialog.yesButton if shouldConfirm else dialog.cancelButton
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        clicked.append(True)

    QTimer.singleShot(300, onDialogOpened)
    qtbot.mouseClick(page.clearHistoryButton, Qt.MouseButton.LeftButton)

    assert clicked == [True]
    assert page.isVisible()
    if shouldConfirm:
        service.clearHistory.assert_called_once_with()
    else:
        service.clearHistory.assert_not_called()
