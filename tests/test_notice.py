from __future__ import annotations

import os

# Popup 是真窗口，在 offscreen 平台上测，不打扰桌面；须在 QApplication 创建前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from desktop_notifier.common import Button, Notification, Urgency
from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QApplication

from app.models.task import Task, TaskError
from app.platform import desktop_notification
from app.platform.desktop_notification import (
    SCREEN_MARGIN, SPACING, NotificationPopup, Popup, PopupNotifier, PopupStack, Presence,
    buildDiskSpaceInsufficient, buildParseFailed, buildTaskCompleted,
)


def shownPopups() -> list[Popup]:
    return [w for w in QApplication.topLevelWidgets() if isinstance(w, Popup) and w.isVisible() and not w.isExiting]


def isSettled() -> bool:
    return all(p.moveAnimation.state() == p.moveAnimation.State.Stopped for p in shownPopups())


def buildNotice(title: str = "下载完成", timeout: int = 60, **kwargs) -> Notification:
    return Notification(title=title, message="ubuntu.iso\n5.00 GB · /tmp", timeout=timeout, **kwargs)


@pytest.fixture
def popupStack(qapp):
    stack = PopupStack(Presence())
    yield stack
    stack.clear()


@pytest.fixture
def popupNotifier(popupStack):
    return PopupNotifier(popupStack)


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
    qtbot.waitUntil(lambda: bool(dismissed) and isSettled())
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

    qtbot.waitUntil(lambda: not shownPopups() and events == ["pressed"])


def test_clear_closes_silently_and_ignores_later_send(qtbot, popupStack, popupNotifier):
    dismissed = []
    popupNotifier.send(buildNotice(on_dismissed=lambda: dismissed.append(True)))
    qtbot.waitUntil(lambda: len(shownPopups()) == 1)

    popupStack.clear()
    popupNotifier.send(buildNotice())

    assert not shownPopups()
    assert dismissed == []


def test_send_beyond_screen_keeps_long_lived_at_bottom(qtbot, popupNotifier):
    dismissed = []
    popupNotifier.send(buildNotice("长驻", timeout=0, on_dismissed=lambda: dismissed.append("长驻")))
    for index in range(12):
        popupNotifier.send(buildNotice(str(index), on_dismissed=lambda i=index: dismissed.append(i)))

    qtbot.waitUntil(lambda: bool(dismissed) and isSettled())
    area = QApplication.primaryScreen().availableGeometry()
    bottom = max(shownPopups(), key=lambda p: p.y())
    assert bottom.titleLabel.text() == "长驻"
    assert bottom.geometry().bottom() == area.bottom() - SCREEN_MARGIN
    assert "长驻" not in dismissed


def test_add_replacing_takes_position_without_dismissing(qtbot, popupStack):
    dismissed = []
    old = NotificationPopup(buildNotice("进度", timeout=0, on_dismissed=lambda: dismissed.append(True)))
    popupStack.add(old)
    popupStack.add(NotificationPopup(buildNotice("其他")))
    qtbot.waitUntil(lambda: len(shownPopups()) == 2 and isSettled())
    position = old.pos()

    new = NotificationPopup(buildNotice("完成", timeout=0))
    popupStack.add(new, replacing=old)

    qtbot.waitUntil(lambda: len(shownPopups()) == 2 and isSettled())
    assert new.pos() == position
    assert sorted(p.titleLabel.text() for p in shownPopups()) == ["其他", "完成"]
    assert dismissed == []


def test_minimize_frees_position_until_restored(qtbot, popupStack):
    lower = NotificationPopup(buildNotice("下", timeout=0))
    upper = NotificationPopup(buildNotice("上", timeout=0))
    popupStack.add(upper)
    popupStack.add(lower)
    qtbot.waitUntil(lambda: len(shownPopups()) == 2 and isSettled())
    bottomY = lower.y()

    lower.showMinimized()
    qtbot.waitUntil(lambda: upper.y() == bottomY and isSettled())

    lower.showNormal()
    qtbot.waitUntil(lambda: lower.y() == bottomY and upper.y() < bottomY and isSettled())


def test_click_with_nested_event_loop_closes_without_error(qtbot, popupNotifier):
    def openDialog():
        loop = QEventLoop()
        QTimer.singleShot(500, loop.quit)
        loop.exec()
        events.append("opened")

    events = []
    popupNotifier.send(buildNotice(on_clicked=openDialog))
    qtbot.waitUntil(lambda: len(shownPopups()) == 1 and isSettled())

    qtbot.mouseClick(shownPopups()[0], Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: events == ["opened"] and not shownPopups(), timeout=3000)
