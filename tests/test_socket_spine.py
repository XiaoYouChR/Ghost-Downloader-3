from PySide6.QtNetwork import QLocalSocket

from app.engine.config import Config
from app.engine.engine import Engine
from app.engine.settings import GLOBAL_SETTINGS
from app.gui.backend import Backend
from app.gui.task_list import TaskList
from app.protocol.message import Command
from app.protocol.socket_link import SocketClient, SocketServer
from fakes import FakeDownloads, FakeStore


def test_fullSpine_overSocket(qtbot):
    # 整条脊柱跑在真 socket 上：addTask 经 socket 到 engine、taskAdded 经 socket 回 gui。
    # 证明换成 SocketLink（拆进程的前提）后 Engine/Backend 一行不改即可工作。
    server = SocketServer("gd3_spine_test")
    engine = Engine(server, FakeDownloads(), FakeStore(), Config(GLOBAL_SETTINGS))
    server.connect(engine.receive)
    server.listen()

    client = SocketClient("gd3_spine_test")
    taskList = TaskList()
    backend = Backend(client, taskList)
    client.connect(backend.receive)
    client.connectToServer()
    qtbot.waitUntil(
        lambda: client._socket.state() == QLocalSocket.LocalSocketState.ConnectedState,
        timeout=2000,
    )

    backend.attach()
    backend.addTask("https://example.com/movie.mp4")
    qtbot.waitUntil(lambda: taskList.rowCount() == 1, timeout=2000)

    assert taskList.data(taskList.index(0, 0), TaskList.TitleRole) == "movie.mp4"


def test_engineDetachesWhenGuiGone(qtbot):
    # gui 退出/崩（socket 断）时 engine 当作 detach：停泵、不再发事件（省 CPU/内存）。
    server = SocketServer("gd3_gone_test")
    engine = Engine(server, FakeDownloads(), FakeStore(), Config(GLOBAL_SETTINGS))
    server.connect(engine.receive)
    server.listen()

    client = SocketClient("gd3_gone_test")
    client.connect(lambda event: None)
    client.connectToServer()
    qtbot.waitUntil(lambda: server._socket is not None, timeout=2000)

    client.toEngine(Command("attach"))
    qtbot.waitUntil(lambda: engine._attached, timeout=2000)
    assert engine._pump.isActive()

    # gui 没了：客户端断开 → server 察觉 → engine 停泵停发
    client._socket.disconnectFromServer()
    qtbot.waitUntil(lambda: not engine._attached, timeout=2000)
    assert not engine._pump.isActive()
