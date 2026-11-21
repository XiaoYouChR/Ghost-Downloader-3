from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from threading import Thread, current_thread
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger

if TYPE_CHECKING:
    from PySide6.QtCore import QObject


class CoroutineRunner:

    def __init__(
        self,
        dispatcher: Callable[[Callable[[], None]], None],
        isAlive: Callable[[object], bool] | None = None,
        *,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._dispatcher = dispatcher
        self._isAlive = isAlive
        self._loop = loop
        self._thread = Thread(target=self._run, daemon=True)
        self._pending: dict[str, tuple] = {}
        self._running: dict[str, asyncio.Task] = {}

    def _run(self):
        self._loop.run_forever()
        self._loop.close()

    def start(self) -> None:
        self._thread.start()

    def submit(
        self,
        work: Coroutine,
        done: Callable[..., object] | None = None,
        failed: Callable[..., object] | None = None,
        *args: object,
        owner: QObject | None = None,
        **kwargs: object,
    ) -> str:
        workId = f"wrk_{uuid4().hex}"
        if owner is not None:
            done, failed = self._guard(owner, done), self._guard(owner, failed)
            owner.destroyed.connect(lambda *_: self.cancel(workId))
        self._pending[workId] = (done, failed, args, kwargs)

        async def execute():
            result, error = None, None
            try:
                result = await work
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error("async work failed: {} ({})", workId, type(e).__name__)
                error = e
            entry = self._pending.pop(workId, None)
            if entry is None:
                return
            done, failed, args, kwargs = entry
            if error is None:
                if done:
                    self.post(done, result, *args, **kwargs)
            elif failed:
                self.post(failed, error, *args, **kwargs)

        def schedule():
            if workId not in self._pending:
                work.close()
                return
            task = self._loop.create_task(execute())
            self._running[workId] = task

            def onDone(completed: asyncio.Task) -> None:
                self._running.pop(workId, None)
                if completed.cancelled():
                    work.close()

            task.add_done_callback(onDone)

        self._loop.call_soon_threadsafe(schedule)
        return workId

    def cancel(self, workId: str, finished: Callable[[], object] | None = None) -> bool:
        wasPending = self._pending.pop(workId, None) is not None

        def scheduleCancel() -> None:
            task = self._running.get(workId)
            if task is None:
                if finished is not None:
                    self.post(finished)
                return
            if finished is not None:
                task.add_done_callback(lambda _: self.post(finished))
            if not task.cancelling():
                task.cancel()

        self._loop.call_soon_threadsafe(scheduleCancel)
        return wasPending or workId in self._running

    def post(self, callback: Callable[..., object], *args: object, **kwargs: object) -> None:
        def wrapper():
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.opt(exception=e).error("callback failed")

        self._dispatcher(wrapper)

    def _guard(self, owner, callback: Callable) -> Callable | None:
        if callback is None:
            return None
        isAlive = self._isAlive

        def guarded(*args, **kwargs):
            if isAlive is None or isAlive(owner):
                callback(*args, **kwargs)

        return guarded

    def stop(self) -> None:
        self._pending.clear()
        if not self._thread.is_alive():
            return

        async def drain() -> None:
            running = list(self._running.values())
            for task in running:
                if not task.cancelling():
                    task.cancel()
            await asyncio.gather(*running, return_exceptions=True)
            self._loop.stop()

        self._loop.call_soon_threadsafe(lambda: self._loop.create_task(drain()))
        if current_thread() is not self._thread:
            self._thread.join(timeout=5)
