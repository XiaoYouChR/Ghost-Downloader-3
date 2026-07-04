from __future__ import annotations

import asyncio
from typing import Callable
from uuid import uuid4

from PySide6.QtCore import QObject, QThread, QTimer
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid
from loguru import logger


class CoroutineRunner(QThread):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._pending: dict[str, tuple] = {}
        self._running: dict[str, asyncio.Task] = {}

    def run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
        self._loop.close()

    def submit(
        self,
        work,
        done: Callable = None,
        failed: Callable = None,
        *args,
        owner: QObject = None,
        **kwargs,
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
                logger.opt(exception=e).error("async work failed: {}", workId)
                error = str(e) or repr(e)
            finally:
                self._running.pop(workId, None)

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
            self._running[workId] = self._loop.create_task(execute())

        self._loop.call_soon_threadsafe(schedule)
        return workId

    def cancel(self, workId: str) -> bool:
        self._pending.pop(workId, None)
        task = self._running.pop(workId, None)
        if task is not None:
            self._loop.call_soon_threadsafe(task.cancel)
            return True
        return False

    def post(self, callback: Callable, *args, **kwargs) -> None:
        def wrapper():
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.opt(exception=e).error("callback failed")

        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app, wrapper)
        else:
            wrapper()

    def _guard(self, owner: QObject, callback: Callable) -> Callable | None:
        if callback is None:
            return None

        def guarded(*args, **kwargs):
            if isValid(owner):
                callback(*args, **kwargs)

        return guarded

    def stop(self) -> None:
        for task in list(self._running.values()):
            task.cancel()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._pending.clear()
        self._running.clear()


coroutineRunner = CoroutineRunner()
