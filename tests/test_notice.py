from __future__ import annotations

import os

# Popup 是真窗口，在 offscreen 平台上测，不打扰桌面；须在 QApplication 创建前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from desktop_notifier.common import Button, Notification, Urgency
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.models.task import Task, TaskError
from app.platform import desktop_notification
from app.platform.desktop_notification import (
    SCREEN_MARGIN, SPACING, Popup, PopupNotifier, Presence, buildDiskSpaceInsufficient, buildParseFailed,
    buildTaskCompleted,
)


def shownPopups() -> list[Popup]:
    return [w for w in QApplication.topLevelWidgets() if isinstance(w, Popup) and w.isVisible() and not w.isExiting]


def isSettled() -> bool:
    return all(p.moveAnimation.state() == p.moveAnimation.State.Stopped for p in shownPopups())


def buildNotice(title: str = "下载完成", timeout: int = 0, **kwargs) -> Notification:
    return Notification(title=title, message="ubuntu.iso\n5.00 GB · /tmp", timeout=timeout, **kwargs)


@pytest.fixture
def popupNotifier(qapp):
    notifier = PopupNotifier(Presence())
    yield notifier
    notifier.clear()


def test_build_task_completed_opens_output(monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr(desktop_notification, "openFile", lambda path: opened.append(("open", path)))
    monkeypatch.setattr(desktop_notification, "revealInFolder", lambda path: opened.append(("reveal", path)))
    task = Task(name="ubuntu.iso", url="https://example.com/ubuntu.iso", packId="http", outputFolder=tmp_path,
                fileSize=5 * 1024 ** 3)

    notification = buildTaskCompleted(task, None)

    assert notification.message.splitlines() == ["ubuntu.iso", f"5.00 GB · {tmp_path}"]
    for button in notification.buttons:
        button.on_pressed()
    notification.on_clicked()
    outputPath = str(tmp_path / "ubuntu.iso")
    assert opened == [("open", outputPath), ("reveal", outputPath), ("open", outputPath)]


def test_build_error_notices_activate_window_on_click():
    activated = []

    diskSpace = buildDiskSpaceInsufficient(1024, 2048, lambda: activated.append("disk"))
    parseFailed = buildParseFailed("https://example.com/a", TaskError("UNKNOWN"), lambda: activated.append("parse"))

    assert diskSpace.message.splitlines()[0] == "任务未自动开始"
    assert parseFailed.message.splitlines()[0] == "https://example.com/a"
    assert diskSpace.urgency == parseFailed.urgency == Urgency.Critical
    diskSpace.on_clicked()
    parseFailed.on_clicked()
    assert activated == ["disk", "parse"]


def test_send_stacks_newest_at_bottom_right(qtbot, popupNotifier):
    for title in ("一", "二", "三"):
        popupNotifier.send(buildNotice(title))

    qtbot.waitUntil(lambda: len(shownPopups()) == 3 and isSettled())
    area = QApplication.primaryScreen().availableGeometry()
    popups = sorted(shownPopups(), key=lambda p: p.y())
    assert [p.titleLabel.text() for p in popups] == ["一", "二", "三"]
    assert popups[-1].geometry().bottom() == area.bottom() - SCREEN_MARGIN
    assert {p.geometry().right() for p in popups} == {area.right() - SCREEN_MARGIN}
    for upper, lower in zip(popups, popups[1:]):
        assert lower.y() - upper.geometry().bottom() - 1 == SPACING


def test_send_beyond_screen_dismisses_oldest(qtbot, popupNotifier):
    dismissed = []
    for index in range(12):
        popupNotifier.send(buildNotice(str(index), on_dismissed=lambda i=index: dismissed.append(i)))

    area = QApplication.primaryScreen().availableGeometry()
    qtbot.waitUntil(lambda: dismissed and isSettled())
    remaining = sorted(int(p.titleLabel.text()) for p in shownPopups())
    assert all(p.y() >= area.top() + SCREEN_MARGIN for p in shownPopups())
    assert remaining == list(range(12 - len(remaining), 12))
    assert sorted(dismissed) == list(range(12 - len(remaining)))


def test_send_with_timeout_dismisses_after_duration(qtbot, popupNotifier):
    dismissed = []
    popupNotifier.send(buildNotice(timeout=1, on_dismissed=lambda: dismissed.append(True)))

    qtbot.waitUntil(lambda: len(shownPopups()) == 1)
    qtbot.waitUntil(lambda: dismissed == [True] and not shownPopups(), timeout=3000)


def test_press_button_runs_action_without_dismissing(qtbot, popupNotifier):
    events = []
    popupNotifier.send(buildNotice(
        buttons=(Button(title="打开文件", on_pressed=lambda: events.append("pressed")),),
        on_dismissed=lambda: events.append("dismissed"),
    ))
    qtbot.waitUntil(lambda: len(shownPopups()) == 1)

    pushButton, _ = shownPopups()[0].buttons[0]
    qtbot.mouseClick(pushButton, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: not shownPopups())
    assert events == ["pressed"]


def test_clear_closes_silently_and_ignores_later_send(qtbot, popupNotifier):
    dismissed = []
    popupNotifier.send(buildNotice(on_dismissed=lambda: dismissed.append(True)))
    qtbot.waitUntil(lambda: len(shownPopups()) == 1)

    popupNotifier.clear()
    popupNotifier.send(buildNotice())

    assert not shownPopups()
    assert dismissed == []
