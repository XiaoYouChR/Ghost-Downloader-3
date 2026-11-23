from __future__ import annotations

import asyncio
import os

import pytest

from app.file_writer import FileWriter, FileWriteError


def openFile(path, flags=os.O_RDWR | os.O_CREAT) -> int:
    return os.open(path, flags | getattr(os, "O_BINARY", 0), 0o666)


async def test_write_lands_in_submission_order(tmp_path):
    path = tmp_path / "file.bin"
    writer = FileWriter(openFile(path))

    writer.write(b"a" * 100, 0)
    writer.write(b"b" * 50, 25)
    writer.truncate(60)
    writer.write(b"c" * 10, 70)
    await writer.close()

    assert path.read_bytes() == b"a" * 25 + b"b" * 35 + b"\0" * 10 + b"c" * 10


async def test_write_keeps_every_byte_when_queue_is_full(tmp_path):
    path = tmp_path / "file.bin"
    content = os.urandom(4 * 1024 * 1024)
    writer = FileWriter(openFile(path), maxQueuedBytes=64 * 1024)

    for offset in range(0, len(content), 16384):
        writer.write(content[offset:offset + 16384], offset)
        await writer.waitForRoom()
    await writer.close()

    assert path.read_bytes() == content


async def test_write_fails_when_file_is_read_only(tmp_path):
    path = tmp_path / "file.bin"
    path.write_bytes(b"original")
    writer = FileWriter(openFile(path, os.O_RDONLY))

    writer.write(b"x" * 1024, 0)
    await writer.close()

    assert writer.error is not None
    with pytest.raises(FileWriteError):
        writer.write(b"y", 0)
    assert path.read_bytes() == b"original"


async def test_wait_for_room_raises_when_write_fails(tmp_path):
    path = tmp_path / "file.bin"
    path.write_bytes(b"")
    writer = FileWriter(openFile(path, os.O_RDONLY), maxQueuedBytes=1024)

    writer.write(b"x" * 4096, 0)
    with pytest.raises(FileWriteError):
        async with asyncio.timeout(5):
            await writer.waitForRoom()
    await writer.close()


async def test_close_finishes_writes_when_cancelled(tmp_path):
    path = tmp_path / "file.bin"
    content = os.urandom(16 * 1024 * 1024)
    writer = FileWriter(openFile(path))
    for offset in range(0, len(content), 65536):
        writer.write(content[offset:offset + 65536], offset)

    closing = asyncio.create_task(writer.close())
    await asyncio.sleep(0)
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing

    assert path.read_bytes() == content
