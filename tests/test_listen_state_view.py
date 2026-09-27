from __future__ import annotations

import pytest

from app.models.task import TaskError
from app.services.loopback_server import ListenState, ListenStatus
from app.signal import Signal

OCCUPIED = ListenState(ListenStatus.FAILED, 16800, error=TaskError("端口 {port} 被占用，请更换端口", port=16800))
LISTENING = ListenState(ListenStatus.LISTENING, 16800)


class FakeServer:
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


def buildPage(browserService, browserServer, aria2Server):
    from app.view.pages.setting_page import SettingPage

    return SettingPage(FakeFeatureService(), browserService, browserServer, aria2Server,
                       coroutineRunner=None, categoryService=FakeCategoryService(), taskService=None,
                       updateService=FakeUpdateService())


@pytest.fixture
def page(qtbot):
    browserServer, aria2Server = FakeServer(), FakeServer()
    page = buildPage(FakeBrowserService(), browserServer, aria2Server)
    qtbot.addWidget(page)
    page.browserServer, page.aria2Server = browserServer, aria2Server
    return page


def test_aria2_card_shows_listening_port(page):
    page.aria2Server.setState(LISTENING)

    assert page.aria2EnableCard.contentLabel.text() == "正在端口 16800 上监听"


def test_aria2_card_shows_occupied_port(page):
    page.aria2Server.setState(OCCUPIED)

    assert page.aria2EnableCard.contentLabel.text() == "端口 16800 被占用，请更换端口"


def test_browser_card_shows_failure_instead_of_connection(page):
    page.browserServer.setState(ListenState(ListenStatus.FAILED, 14370, error=TaskError("没有权限监听端口 {port}，请更换端口", port=14370)))

    assert page.browserEnableCard.contentLabel.text() == "没有权限监听端口 14370，请更换端口"


def test_browser_card_shows_connection_while_listening(page):
    page.browserServer.setState(LISTENING)

    assert page.browserEnableCard.contentLabel.text() == "未连接"


def test_state_known_before_page_opens_is_shown(qtbot):
    page = buildPage(FakeBrowserService(), FakeServer(), FakeServer(OCCUPIED))
    qtbot.addWidget(page)

    assert page.aria2EnableCard.contentLabel.text() == "端口 16800 被占用，请更换端口"


def test_destroyed_page_no_longer_receives_signals(qtbot):
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    browserService, browserServer, aria2Server = FakeBrowserService(), FakeServer(), FakeServer()
    page = buildPage(browserService, browserServer, aria2Server)
    page.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    browserService.connectionChanged.emit()
    browserServer.setState(LISTENING)
    aria2Server.setState(OCCUPIED)
