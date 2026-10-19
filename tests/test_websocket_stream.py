from __future__ import annotations

import asyncio

import pytest
import websockets

from app.services.websocket_stream import WebSocketStream, readHead

pytestmark = pytest.mark.asyncio(loop_factories=["asyncio", "uvloop"])


@pytest.fixture
async def startStreamServer():
    servers = []
    lateSends = []

    async def start(maxSize: int = 2**20) -> str:
        async def onConnection(reader, writer):
            head = await readHead(reader)
            stream = await WebSocketStream.open(reader, writer, head, maxSize=maxSize)
            async for message in stream.messages():
                await stream.send(message.decode()[::-1])
            await stream.send("late")
            lateSends.append(True)
            writer.close()

        server = await asyncio.start_server(onConnection, "127.0.0.1", 0)
        servers.append(server)
        return f"127.0.0.1:{server.sockets[0].getsockname()[1]}"

    start.lateSends = lateSends
    yield start

    for server in servers:
        server.close()


async def test_send_text_round_trip(startStreamServer):
    async with websockets.connect(f"ws://{await startStreamServer()}/") as ws:
        await ws.send("hello")
        assert await ws.recv() == "olleh"


async def test_send_pong_for_ping(startStreamServer):
    async with websockets.connect(f"ws://{await startStreamServer()}/") as ws:
        pong = await ws.ping()
        await asyncio.wait_for(pong, 1)


async def test_close_echoes_code(startStreamServer):
    ws = await websockets.connect(f"ws://{await startStreamServer()}/")
    await ws.close(code=4000)

    assert ws.protocol.close_rcvd.code == 4000


async def test_parse_fragmented_message(startStreamServer):
    async with websockets.connect(f"ws://{await startStreamServer()}/") as ws:
        await ws.send(["hel", "lo"])
        assert await ws.recv() == "olleh"


async def test_send_after_client_left(startStreamServer):
    async with websockets.connect(f"ws://{await startStreamServer()}/") as ws:
        await ws.send("bye")
        await ws.recv()
    await asyncio.sleep(0.1)

    assert startStreamServer.lateSends == [True]


async def test_open_aborted_mid_handshake_yields_nothing():
    received = []

    async def onConnection(reader, writer):
        received.append(await readHead(reader))
        writer.close()

    server = await asyncio.start_server(onConnection, "127.0.0.1", 0)
    _, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1])
    writer.write(b"GET / HTTP/1.1\r\nHost: x\r\n")
    writer.close()
    await asyncio.sleep(0.1)
    server.close()

    assert received == [None]

