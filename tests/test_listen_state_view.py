from __future__ import annotations

import pytest

from app.models.task import TaskError
from app.services.port_listener import ListenState, ListenStatus
from app.signal import Signal

OCCUPIED = ListenState(ListenStatus.FAILED, 16800, error=TaskError("端口 {port} 被占用，请更换端口", port=16800))
LISTENING = ListenState(ListenStatus.LISTENING, 16800)


class FakeListener:
    stateChanged = Signal(object)

    def __init__(self, state: ListenState = ListenState()):
        self.state = state

    def setState(self, state: ListenState) -> None:
        self.state = state
        self.stateChanged.emit(state)


class FakeBrowserService:
    connectionChanged = Signal()
    protocolMismatched = Signal()
    pairRequestChanged = Signal(object)
    connectionSummary = ("", "")


class FakeFeatureService:
    packs = []

    def settingGroups(self, parent):
        return []


class FakeUpdateService:
    changed = Signal()


class FakeCategoryService:
    categoriesChanged = Signal()

    def categories(self):
        return []


def buildPage(browserService, browserListener, aria2RpcListener):
    from app.view.pages.setting_page import SettingPage

    return SettingPage(FakeFeatureService(), browserService, browserListener, aria2RpcListener,
                       coroutineRunner=None, categoryService=FakeCategoryService(), taskService=None,
                       updateService=FakeUpdateService())


@pytest.fixture
def page(qtbot):
    browserListener, aria2RpcListener = FakeListener(), FakeListener()
    page = buildPage(FakeBrowserService(), browserListener, aria2RpcListener)
    qtbot.addWidget(page)
    page.browserListener, page.aria2RpcListener = browserListener, aria2RpcListener
    return page


def test_aria2_card_shows_listening_port(page):
    page.aria2RpcListener.setState(LISTENING)

    assert page.aria2EnableCard.contentLabel.text() == "正在端口 16800 上监听"


def test_aria2_card_shows_occupied_port(page):
    page.aria2RpcListener.setState(OCCUPIED)

    assert page.aria2EnableCard.contentLabel.text() == "端口 16800 被占用，请更换端口"


def test_browser_card_shows_failure_instead_of_connection(page):
    page.browserListener.setState(ListenState(ListenStatus.FAILED, 14370, error=TaskError("没有权限监听端口 {port}，请更换端口", port=14370)))

    assert page.browserEnableCard.contentLabel.text() == "没有权限监听端口 14370，请更换端口"


def test_browser_card_shows_connection_while_listening(page):
    page.browserListener.setState(LISTENING)

    assert page.browserEnableCard.contentLabel.text() == "未连接"


def test_state_known_before_page_opens_is_shown(qtbot):
    page = buildPage(FakeBrowserService(), FakeListener(), FakeListener(OCCUPIED))
    qtbot.addWidget(page)

    assert page.aria2EnableCard.contentLabel.text() == "端口 16800 被占用，请更换端口"


def test_destroyed_page_no_longer_receives_signals(qtbot):
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    browserService, browserListener, aria2RpcListener = FakeBrowserService(), FakeListener(), FakeListener()
    page = buildPage(browserService, browserListener, aria2RpcListener)
    page.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    browserService.connectionChanged.emit()
    browserListener.setState(LISTENING)
    aria2RpcListener.setState(OCCUPIED)
