from __future__ import annotations

import asyncio
import base64
import os

import pytest
import websockets
from websockets.exceptions import ConnectionClosedError

from app.services.websocket_stream import WebSocketStream, readHead

pytestmark = pytest.mark.asyncio(loop_factories=["asyncio", "uvloop"])


@pytest.fixture
async def serve():
    servers = []
    lateSends = []

    async def start(maxSize: int = 2**20) -> str:
        async def handle(reader, writer):
            head = await readHead(reader)
            stream = await WebSocketStream.open(reader, writer, head, maxSize=maxSize)
            async for message in stream.messages():
                await stream.send(message.decode()[::-1])
            await stream.send("late")
            lateSends.append(True)
            writer.close()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        servers.append(server)
        return f"127.0.0.1:{server.sockets[0].getsockname()[1]}"

    start.lateSends = lateSends
    yield start

    for server in servers:
        server.close()


async def test_text_message_round_trip(serve):
    async with websockets.connect(f"ws://{await serve()}/") as ws:
        await ws.send("hello")
        assert await ws.recv() == "olleh"


async def test_ping_is_answered_with_pong(serve):
    async with websockets.connect(f"ws://{await serve()}/") as ws:
        pong = await ws.ping()
        await asyncio.wait_for(pong, 1)


async def test_close_is_echoed_with_same_code(serve):
    ws = await websockets.connect(f"ws://{await serve()}/")
    await ws.close(code=4000)

    assert ws.protocol.close_rcvd.code == 4000


async def test_fragmented_message_is_reassembled(serve):
    async with websockets.connect(f"ws://{await serve()}/") as ws:
        await ws.send(["hel", "lo"])
        assert await ws.recv() == "olleh"


async def test_oversized_message_closes_with_1009(serve):
    async with websockets.connect(f"ws://{await serve(maxSize=16)}/") as ws:
        await ws.send("x" * 64)
        with pytest.raises(ConnectionClosedError):
            await ws.recv()
        assert ws.protocol.close_rcvd.code == 1009


async def test_unmasked_client_frame_closes_with_1002(serve):
    host, port = (await serve()).split(":")
    reader, writer = await asyncio.open_connection(host, int(port))
    key = base64.b64encode(os.urandom(16))
    writer.write(
        b"GET / HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
        b"Sec-WebSocket-Key: " + key + b"\r\nSec-WebSocket-Version: 13\r\n\r\n"
    )
    await reader.readuntil(b"\r\n\r\n")
    writer.write(b"\x81\x02hi")

    reply = await asyncio.wait_for(reader.read(), 1)

    assert reply[:1] == b"\x88"
    assert int.from_bytes(reply[2:4], "big") == 1002
    writer.close()


async def test_send_after_peer_closed_does_not_raise(serve):
    async with websockets.connect(f"ws://{await serve()}/") as ws:
        await ws.send("bye")
        await ws.recv()
    await asyncio.sleep(0.1)

    assert serve.lateSends == [True]


async def test_client_leaving_before_head_completes_yields_no_head():
    received = []

    async def handle(reader, writer):
        received.append(await readHead(reader))
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    _, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1])
    writer.write(b"GET / HTTP/1.1\r\nHost: x\r\n")
    writer.close()
    await asyncio.sleep(0.1)
    server.close()

    assert received == [None]


async def test_head_over_8k_yields_no_head():
    received = []

    async def handle(reader, writer):
        received.append(await readHead(reader))
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    _, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1])
    writer.write(b"GET / HTTP/1.1\r\nX: " + b"a" * 9000 + b"\r\n\r\n")
    await asyncio.sleep(0.1)
    writer.close()
    server.close()

    assert received == [None]
