"""TaskCard 的名称和信息行热区。

Seam: TaskCard 鼠标事件（qtbot 真实点击）
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt

from app.models.task import TaskStatus
from app.signal import Signal
from tests.test_task_service import makeTask


class FakeTaskService:
    def checksumProgress(self, task):
        return None


class FakeCategoryService:
    categoriesChanged = Signal()

    def categoryById(self, categoryId):
        return None


@pytest.fixture()
def card(qtbot, monkeypatch, tmp_path):
    from app.view.cards import task_cards
    opened: list[str] = []
    monkeypatch.setattr(task_cards, "openFile", opened.append)
    task = makeTask(name="movie.mp4")
    task.outputFolder = tmp_path
    (tmp_path / "movie.mp4").write_bytes(b"x")
    task.steps[0].progress = 100
    task.setStatus(TaskStatus.COMPLETED)
    widget = task_cards.TaskCard(task, FakeTaskService(), None, FakeCategoryService())
    widget.drawers = []
    monkeypatch.setattr(widget, "_openDrawer", lambda: widget.drawers.append(task.taskId))
    widget.opened = opened
    qtbot.addWidget(widget)
    widget.resize(800, widget.ROW_HEIGHT)
    widget.show()
    widget.refresh(force=True)
    qtbot.waitExposed(widget)
    return widget


def namePos(card) -> QPoint:
    return card.nameLabel.geometry().topLeft() + QPoint(card.nameLabel.indent() + 5, card.nameLabel.height() // 2)


def blankNamePos(card) -> QPoint:
    return card.nameLabel.geometry().topRight() + QPoint(-5, card.nameLabel.height() // 2)


def infoPos(card) -> QPoint:
    return card.statusLabel.geometry().center()


def test_click_name_text_opens_file(card, qtbot):
    qtbot.mouseClick(card, Qt.MouseButton.LeftButton, pos=namePos(card))

    assert card.opened == [card.task.outputPath]


def test_click_blank_after_name_selects_instead(card, qtbot):
    with qtbot.waitSignal(card.selectionChanged, timeout=1000):
        qtbot.mouseClick(card, Qt.MouseButton.LeftButton, pos=blankNamePos(card))

    assert card.opened == []


def test_click_info_opens_drawer_without_selecting(card, qtbot):
    with qtbot.assertNotEmitted(card.selectionChanged):
        qtbot.mouseClick(card, Qt.MouseButton.LeftButton, pos=infoPos(card))

    assert card.drawers == [card.task.taskId]


def test_shift_click_on_name_extends_selection(card, qtbot):
    with qtbot.waitSignal(card.selectionChanged, timeout=1000) as blocker:
        qtbot.mouseClick(card, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, pos=namePos(card))

    assert blocker.args == [True, True]
    assert card.opened == []


def test_selection_mode_turns_links_into_plain_area(card, qtbot):
    card.setSelectionMode(True)

    with qtbot.waitSignal(card.selectionChanged, timeout=1000):
        qtbot.mouseClick(card, Qt.MouseButton.LeftButton, pos=namePos(card))
    with qtbot.waitSignal(card.selectionChanged, timeout=1000):
        qtbot.mouseClick(card, Qt.MouseButton.LeftButton, pos=infoPos(card))

    assert card.opened == []
    assert card.drawers == []


def test_name_of_unfinished_task_is_not_a_link(card, qtbot):
    card.task.steps[0].status = TaskStatus.PAUSED
    card.task.updateStatus()
    card.refresh(force=True)

    with qtbot.waitSignal(card.selectionChanged, timeout=1000):
        qtbot.mouseClick(card, Qt.MouseButton.LeftButton, pos=namePos(card))

    assert card.opened == []


def test_hover_shows_hand_only_over_links(card, qtbot):
    qtbot.mouseMove(card, namePos(card))
    assert card.cursor().shape() == Qt.CursorShape.PointingHandCursor

    qtbot.mouseMove(card, blankNamePos(card))
    assert card.cursor().shape() == Qt.CursorShape.ArrowCursor
