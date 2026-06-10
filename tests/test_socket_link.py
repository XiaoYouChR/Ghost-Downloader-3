from PySide6.QtNetwork import QLocalSocket

from app.gui.backend import Backend
from app.gui.task_list import TaskList
from app.protocol.message import Command, Event
from app.protocol.socket_link import SocketClient, SocketServer


def test_socketLink_roundTrip(qtbot):
    # gui 经真 socket 发 Command 到 engine，engine 发 Event 回 gui，两向都对得上。
    commands: list[Command] = []
    events: list[Event] = []

    server = SocketServer("gd3_socket_test")
    server.connect(commands.append)
    server.listen()

    client = SocketClient("gd3_socket_test")
    client.connect(events.append)
    client.connectToServer()
    qtbot.waitUntil(
        lambda: client._socket.state() == QLocalSocket.LocalSocketState.ConnectedState,
        timeout=2000,
    )

    client.toEngine(Command("addTask", {"url": "https://example.com/a.mp4"}))
    qtbot.waitUntil(lambda: len(commands) == 1, timeout=2000)
    assert commands[0] == Command("addTask", {"url": "https://example.com/a.mp4"})

    server.toGui(Event("taskAdded", {"task": {"taskId": "t1"}}))
    qtbot.waitUntil(lambda: len(events) == 1, timeout=2000)
    assert events[0] == Event("taskAdded", {"task": {"taskId": "t1"}})


def test_socketClient_reconnectsAfterDaemonDrops(qtbot):
    # daemon 掉线再回来：连上→server 丢连接→gui 显示断开→server 重开→client 自己连回并重新 attach。
    name = "gd3_reconnect_test"
    server = SocketServer(name)
    server.connect(lambda command: None)
    server.listen()

    taskList = TaskList()
    client = SocketClient(name)
    backend = Backend(client, taskList)
    client.connect(backend.receive)
    client.whenConnected(backend.attach)
    client.whenDisconnected(backend.setDisconnected)
    client.connectToServer()
    # 等两端都就位：client 这边 connected，server 那边也 accept 了（本地 socket 两边异步）
    qtbot.waitUntil(lambda: backend.connected and server._socket is not None, timeout=2000)

    # daemon 崩：server 端丢掉连接并停止监听
    server._socket.disconnectFromServer()
    server._server.close()
    qtbot.waitUntil(lambda: not backend.connected, timeout=2000)

    # daemon 重启：同名重开，client 自己连回来并重新 attach（connected 复位 True）
    revived = SocketServer(name)
    revived.connect(lambda command: None)
    revived.listen()
    qtbot.waitUntil(lambda: backend.connected, timeout=5000)
