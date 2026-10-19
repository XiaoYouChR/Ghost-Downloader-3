from __future__ import annotations

import asyncio
import json
import socket

import pytest
import websockets
from websockets.exceptions import ConnectionClosed

from app.config.cfg import cfg
from app.services.port_listener import ListenState, ListenStatus
from tests.helpers import probeFreePort, waitUntil


@pytest.fixture(params=["desktop", "android"])
def engine(request, startEngine):
    return startEngine(request.param)


@pytest.fixture
def listener(engine):
    return engine.aria2RpcListener


async def startListener(port: int) -> None:
    cfg.set(cfg.aria2RpcPort, port)
    await asyncio.sleep(0.05)
    cfg.set(cfg.isAria2RpcEnabled, True)


def createListener(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET)
    sock.bind((host, port))
    sock.listen()
    return sock


async def requestVersion(host: str, port: int) -> int:
    body = json.dumps({"jsonrpc": "2.0", "id": "v", "method": "aria2.getVersion", "params": []}).encode()
    reader, writer = await asyncio.open_connection(host, port)
    writer.write(f"POST /jsonrpc HTTP/1.1\r\nHost: x\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
    statusLine = await asyncio.wait_for(reader.readline(), 3)
    writer.close()
    return int(statusLine.split()[1])


def isListening(listener) -> bool:
    return listener.state.status == ListenStatus.LISTENING


async def test_start_listens_on_ipv4_and_ipv6(listener):
    await startListener(probeFreePort())
    await waitUntil(lambda: isListening(listener))

    assert await requestVersion("127.0.0.1", listener.state.port) == 200
    assert await requestVersion("::1", listener.state.port) == 200


async def test_start_on_taken_port_fails_until_port_changes(listener):
    port = probeFreePort()
    occupier = createListener("127.0.0.1", port)
    await startListener(port)
    await waitUntil(lambda: listener.state.status == ListenStatus.FAILED)

    assert (str(listener.state.error), listener.state.port) == (f"端口 {port} 被占用，请更换端口", port)
    cfg.set(cfg.aria2RpcPort, probeFreePort())
    await waitUntil(lambda: isListening(listener))
    occupier.close()


async def test_start_with_taken_ipv6_listens_on_ipv4(listener):
    port = probeFreePort()
    occupier = createListener("::1", port)
    await startListener(port)
    await waitUntil(lambda: isListening(listener))

    assert await requestVersion("127.0.0.1", port) == 200
    occupier.close()


async def test_start_and_stop_quickly_ends_listening(listener):
    states: list[ListenState] = []
    listener.stateChanged.connect(states.append)
    await startListener(probeFreePort())
    for _ in range(50):
        cfg.set(cfg.isAria2RpcEnabled, False)
        cfg.set(cfg.isAria2RpcEnabled, True)
    await waitUntil(lambda: isListening(listener))
    await asyncio.sleep(0.1)

    assert isListening(listener)
    assert all(state.status != ListenStatus.FAILED for state in states)
    assert await requestVersion("127.0.0.1", listener.state.port) == 200


async def test_stop_closes_served_connections(listener):
    await startListener(probeFreePort())
    await waitUntil(lambda: isListening(listener))

    async with websockets.connect(f"ws://127.0.0.1:{listener.state.port}/jsonrpc") as ws:
        cfg.set(cfg.isAria2RpcEnabled, False)
        with pytest.raises(ConnectionClosed):
            await asyncio.wait_for(ws.recv(), 1)

    await waitUntil(lambda: listener.state.status == ListenStatus.OFF)


async def test_start_is_starting_until_bound(listener):
    port = probeFreePort()

    await startListener(port)

    assert (listener.state.status, listener.state.port) == (ListenStatus.STARTING, port)


async def test_start_announces_each_state_once(listener):
    cfg.set(cfg.aria2RpcPort, probeFreePort())
    await asyncio.sleep(0.05)
    statuses: list[ListenStatus] = []
    listener.stateChanged.connect(lambda state: statuses.append(state.status))

    cfg.set(cfg.isAria2RpcEnabled, True)
    await waitUntil(lambda: isListening(listener))
    await asyncio.sleep(0.05)

    assert statuses == [ListenStatus.STARTING, ListenStatus.LISTENING]
