import functools
from typing import Callable, Optional

from .Future import QFuture
from PySide6.QtCore import QObject, Signal, QRunnable


class _Signal(QObject):
    finished = Signal(object)


class QBaseTask(QRunnable):
    def __init__(self, _id: int, future: QFuture, priority):
        super().__init__()
        self._signal: _Signal = _Signal()  # pyqtSignal(object)
        self._future: QFuture = future
        self._id: int = _id
        self._exception: Optional[BaseException] = None
        self._semaphore = future.semaphore
        self._priority = priority

    @property
    def finished(self):
        return self._signal.finished

    @property
    def signal(self):
        return self._signal

    @property
    def priority(self):
        return self._priority

    @property
    def taskID(self):
        return self._id

    @property
    def future(self):
        return self._future

    @property
    def state(self):
        return self._future.state

    def withPriority(self, priority):
        """
        default:0, higher will be handled more quickly.
        priority only makes sense when the task is waiting to be scheduled
        :param priority:
        :return:
        """
        self._priority = priority
        return self

    def _taskDone(self, **data):
        for d in data.items():
            self._future.setExtra(*d)
        self._signal.finished.emit(self._future)
        self._semaphore.release(1)


class QTask(QBaseTask):
    def __init__(
        self,
        _id: int,
        future: QFuture,
        target: functools.partial,
        priority,
        executor,
        args,
        kwargs,
    ):
        super().__init__(_id=_id, priority=priority, future=future)
        self._executor = executor

        self._target = target
        self._kwargs = kwargs
        self._args = args

    def run(self) -> None:
        """
        use QTask.runTask() instead if you know what are you doing.
        :return:
        """
        try:
            self._taskDone(result=self._target(*self._args, **self._kwargs))
        except Exception as exception:
            self._taskDone(exception=exception)

    def then(
        self,
        onSuccess: Callable,
        onFailed: Callable = None,
        onFinished: Callable = None,
    ) -> "QTask":
        self._future.then(onSuccess, onFailed, onFinished)
        return self

    def runTask(self) -> QFuture:
        return self._executor.runTask(self)
