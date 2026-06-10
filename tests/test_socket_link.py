from PySide6.QtNetwork import QLocalSocket

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
