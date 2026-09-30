from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from websockets.frames import CloseCode, Opcode
from websockets.protocol import State
from websockets.server import ServerProtocol

MAX_HEAD_SIZE = 8 * 1024


async def readHead(reader: asyncio.StreamReader) -> bytes | None:
    try:
        head = await reader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        return None
    return head if len(head) <= MAX_HEAD_SIZE else None


class WebSocketStream:
    def __init__(self, protocol: ServerProtocol, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._protocol = protocol
        self._reader = reader
        self._writer = writer

    @classmethod
    async def open(cls, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                   head: bytes, maxSize: int) -> WebSocketStream | None:
        protocol = ServerProtocol(max_size=maxSize)
        protocol.receive_data(head)
        protocol.send_response(protocol.accept(protocol.events_received()[0]))
        stream = cls(protocol, reader, writer)
        await stream._flush()
        return stream if protocol.state is State.OPEN else None

    async def messages(self) -> AsyncIterator[bytes]:
        parts: list[bytes] = []
        while self._protocol.state is not State.CLOSED:
            data = await self._reader.read(65536)
            if data:
                self._protocol.receive_data(data)
            else:
                self._protocol.receive_eof()

            completed = []
            for frame in self._protocol.events_received():
                if frame.opcode not in (Opcode.TEXT, Opcode.BINARY, Opcode.CONT):
                    continue
                parts.append(frame.data)
                if frame.fin:
                    completed.append(b"".join(parts))
                    parts.clear()
            await self._flush()

            for message in completed:
                yield message
            if not data or self._protocol.close_expected():
                return

    async def send(self, text: str) -> None:
        if self._protocol.state is not State.OPEN:
            return
        self._protocol.send_text(text.encode())
        await self._flush()

    async def close(self) -> None:
        if self._protocol.state is not State.OPEN:
            return
        self._protocol.send_close(CloseCode.NORMAL_CLOSURE)
        await self._flush()

    async def _flush(self) -> None:
        for data in self._protocol.data_to_send():
            if data:
                self._writer.write(data)
            elif self._writer.can_write_eof():
                self._writer.write_eof()
        try:
            await self._writer.drain()
        except ConnectionError:
            pass
