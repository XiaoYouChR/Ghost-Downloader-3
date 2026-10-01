"""TaskDrawer 的关闭路径。

Seam: TaskDrawer（qtbot，真实动画）
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget
from shiboken6 import isValid

from app.signal import Signal
from tests.test_task_service import makeTask


class FakeTaskService:
    taskRemoved = Signal(str)


class FakeFeatureService:
    def detailCards(self, task, parent=None):
        return []


class FakeCategoryService:
    def categoryById(self, categoryId):
        return None


@pytest.fixture()
def opened(qtbot):
    from app.view.dialogs.task_drawer import TaskDrawer
    window = QWidget()
    qtbot.addWidget(window)
    window.resize(1000, 700)
    window.show()
    taskService = FakeTaskService()
    task = makeTask()
    drawer = TaskDrawer(task, taskService, FakeFeatureService(), FakeCategoryService(), window)
    drawer.show()
    qtbot.waitExposed(drawer)
    yield drawer, taskService, task
    window.close()


def test_close_slides_out_then_destroys(opened, qtbot):
    drawer, _, _ = opened

    drawer.reject()

    assert isValid(drawer) and drawer.isVisible()
    qtbot.waitUntil(lambda: not isValid(drawer), timeout=2000)


def test_removing_the_task_closes_drawer(opened, qtbot):
    drawer, taskService, task = opened

    taskService.taskRemoved.emit(task.taskId)

    qtbot.waitUntil(lambda: not isValid(drawer), timeout=2000)


def test_other_task_removed_keeps_drawer(opened, qtbot):
    drawer, taskService, _ = opened

    taskService.taskRemoved.emit("tsk_other")
    qtbot.wait(500)

    assert isValid(drawer) and drawer.isVisible()
