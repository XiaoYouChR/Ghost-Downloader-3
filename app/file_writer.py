from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import Buffer
from queue import SimpleQueue

from app.platform.sysio import ftruncate, pwrite

MAX_QUEUED_BYTES = 32 * 1024 * 1024


class FileWriteError(Exception):
    pass


class FileWriter:
    """在独立线程中按提交顺序写入文件，慢速磁盘只阻塞本任务，不阻塞事件循环。

    调用方提交时即视为已写入，可立即推进进度；只有 doneCount 追上提交时的
    submittedCount，对应的数据才真正落盘。写入失败后丢弃后续提交，并在下一次
    提交或等待时抛出 FileWriteError。
    """

    def __init__(self, fd: int, maxQueuedBytes: int = MAX_QUEUED_BYTES) -> None:
        self._fd = fd
        self._maxQueuedBytes = maxQueuedBytes
        self._loop = asyncio.get_running_loop()
        self._jobs: SimpleQueue[tuple[Buffer | None, int] | None] = SimpleQueue()
        self._lock = threading.Lock()
        self._queuedBytes = 0
        self._hasWaiters = False
        self._waiters: list[asyncio.Future] = []
        self.error: FileWriteError | None = None
        self._stopped = self._loop.create_future()
        self.submittedCount = 0
        self.doneCount = 0
        self._thread = threading.Thread(target=self._run, name="FileWriter", daemon=True)
        self._thread.start()

    def write(self, data: Buffer, offset: int) -> None:
        self._raiseError()
        with self._lock:
            self._queuedBytes += len(data)
        self.submittedCount += 1
        self._jobs.put((data, offset))

    def truncate(self, size: int) -> None:
        self._raiseError()
        self.submittedCount += 1
        self._jobs.put((None, size))

    async def waitForRoom(self) -> None:
        while True:
            self._raiseError()
            with self._lock:
                if self._queuedBytes <= self._maxQueuedBytes:
                    return
                self._hasWaiters = True
                waiter = self._loop.create_future()
                self._waiters.append(waiter)
            await waiter

    async def close(self) -> None:
        """等待已提交的数据写完后关闭文件。"""
        self._jobs.put(None)
        try:
            await asyncio.shield(self._stopped)
        finally:
            # 关闭途中被取消时同步等待，保证文件关闭前写完
            self._thread.join()
            os.close(self._fd)

    def _raiseError(self) -> None:
        if self.error is not None:
            raise self.error

    def _run(self) -> None:
        while (job := self._jobs.get()) is not None:
            data, value = job
            if self.error is None:
                try:
                    if data is None:
                        ftruncate(self._fd, value)
                    else:
                        view, written = memoryview(data), 0
                        while written < len(view):
                            written += pwrite(self._fd, view[written:], value + written)
                    self.doneCount += 1
                except OSError as e:
                    error = FileWriteError(str(e))
                    error.__cause__ = e
                    self.error = error
            with self._lock:
                if data is not None:
                    self._queuedBytes -= len(data)
                shouldWake = self._hasWaiters and (
                    self.error is not None or self._queuedBytes <= self._maxQueuedBytes // 2)
                if shouldWake:
                    self._hasWaiters = False
            if shouldWake:
                self._loop.call_soon_threadsafe(self._wakeWaiters)
        self._loop.call_soon_threadsafe(self._setStopped)

    def _wakeWaiters(self) -> None:
        with self._lock:
            waiters, self._waiters = self._waiters, []
        for waiter in waiters:
            if not waiter.done():
                waiter.set_result(None)

    def _setStopped(self) -> None:
        if not self._stopped.done():
            self._stopped.set_result(None)
