from __future__ import annotations

import asyncio
import socket

import pytest

from app.services.coroutine_runner import CoroutineRunner
from app.services.loopback_server import ListenFailure, ListenState, ListenStatus, LoopbackServer
from app.signal import Signal

pytestmark = pytest.mark.asyncio(loop_factories=["asyncio", "uvloop"])


class FakeItem:
    valueChanged = Signal(object)

    def __init__(self, value):
        self.value = value

    def set(self, value):
        self.value = value
        self.valueChanged.emit(value)


def findFreePort() -> int:
    while True:
        with socket.socket(socket.AF_INET) as v4:
            v4.bind(("127.0.0.1", 0))
            port = v4.getsockname()[1]
            with socket.socket(socket.AF_INET6) as v6:
                try:
                    v6.bind(("::1", port))
                except OSError:
                    continue
        return port


def occupy(host: str, port: int) -> socket.socket:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family)
    sock.bind((host, port))
    sock.listen()
    return sock


async def waitFor(predicate, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.01)


async def echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while line := await reader.readline():
        if line == b"boom\n":
            raise RuntimeError("boom")
        writer.write(line)
        await writer.drain()


async def roundTrip(host: str, port: int, text: bytes = b"hello\n") -> bytes:
    reader, writer = await asyncio.open_connection(host, port)
    writer.write(text)
    line = await asyncio.wait_for(reader.readline(), 1)
    writer.close()
    return line


@pytest.fixture
async def build():
    servers = []

    def build(isEnabled=True, port=None):
        loop = asyncio.get_running_loop()
        runner = CoroutineRunner(loop.call_soon, loop=loop)
        isEnabledItem, portItem = FakeItem(isEnabled), FakeItem(port or findFreePort())
        server = LoopbackServer(runner, echo, isEnabled=isEnabledItem, port=portItem)
        servers.append(server)
        return server, isEnabledItem, portItem

    yield build

    for server in servers:
        server.stop()
    await asyncio.sleep(0.05)


def isListening(server: LoopbackServer) -> bool:
    return server.state.status == ListenStatus.LISTENING


async def test_listens_on_ipv4_and_ipv6_loopback(build):
    server, isEnabledItem, portItem = build()
    server.start()
    await waitFor(lambda: isListening(server))

    assert await roundTrip("127.0.0.1", server.state.port) == b"hello\n"
    assert await roundTrip("::1", server.state.port) == b"hello\n"


async def test_occupied_port_fails_and_recovers_after_port_change(build):
    port = findFreePort()
    occupier = occupy("127.0.0.1", port)
    server, isEnabledItem, portItem = build(port=port)
    server.start()
    await waitFor(lambda: server.state.status == ListenStatus.FAILED)

    assert server.state.failure == ListenFailure.OCCUPIED
    assert server.state.port == port

    portItem.set(findFreePort())
    await waitFor(lambda: isListening(server))
    occupier.close()


async def test_occupied_ipv6_still_listens_on_ipv4(build):
    port = findFreePort()
    occupier = occupy("::1", port)
    server, isEnabledItem, portItem = build(port=port)
    server.start()
    await waitFor(lambda: isListening(server))

    assert await roundTrip("127.0.0.1", port) == b"hello\n"
    occupier.close()


async def test_rapid_toggling_ends_listening_without_failure(build):
    server, isEnabledItem, portItem = build()
    states: list[ListenState] = []
    server.stateChanged.connect(states.append)
    server.start()
    for _ in range(50):
        isEnabledItem.set(False)
        isEnabledItem.set(True)
    await waitFor(lambda: isListening(server))
    await asyncio.sleep(0.1)

    assert isListening(server)
    assert all(s.status != ListenStatus.FAILED for s in states)
    assert await roundTrip("127.0.0.1", server.state.port) == b"hello\n"


async def test_disabling_closes_established_connections(build):
    server, isEnabledItem, portItem = build()
    server.start()
    await waitFor(lambda: isListening(server))
    reader, writer = await asyncio.open_connection("127.0.0.1", server.state.port)

    isEnabledItem.set(False)

    assert await asyncio.wait_for(reader.read(), 1) == b""
    await waitFor(lambda: server.state.status == ListenStatus.OFF)
    writer.close()


async def test_stop_then_start_in_same_tick_keeps_listening(build):
    server, isEnabledItem, portItem = build()
    server.start()
    await waitFor(lambda: isListening(server))
    port = server.state.port

    server.stop()
    server.start()
    await asyncio.sleep(0.1)

    assert isListening(server)
    assert await roundTrip("127.0.0.1", port) == b"hello\n"


async def test_failing_connection_does_not_stop_server(build):
    server, isEnabledItem, portItem = build()
    server.start()
    await waitFor(lambda: isListening(server))
    reader, writer = await asyncio.open_connection("127.0.0.1", server.state.port)
    writer.write(b"boom\n")

    assert await asyncio.wait_for(reader.read(), 1) == b""
    assert await roundTrip("127.0.0.1", server.state.port) == b"hello\n"


async def test_enabled_server_is_not_off_before_bind_finishes(build):
    server, isEnabledItem, portItem = build()
    server.start()

    assert server.state.status != ListenStatus.OFF
    assert server.state.port == portItem.value


async def test_state_changes_are_emitted_once_each(build):
    server, isEnabledItem, portItem = build()
    states: list[ListenStatus] = []
    server.stateChanged.connect(lambda s: states.append(s.status))
    server.start()
    await waitFor(lambda: isListening(server))
    await asyncio.sleep(0.05)

    assert states == [ListenStatus.STARTING, ListenStatus.LISTENING]
