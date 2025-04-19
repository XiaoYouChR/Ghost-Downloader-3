import functools
import os
import warnings
from typing import Dict, List, Callable, Iterable

from .Future import QFuture, FutureCancelled, State
from PySide6.QtCore import QThreadPool, QObject
from .Task import QBaseTask, QTask

CPU_COUNTS = os.cpu_count()


class BaseTaskExecutor(QObject):
    def __init__(self, useGlobalThreadPool=True):
        super().__init__()
        self.useGlobalThreadPool = useGlobalThreadPool
        if useGlobalThreadPool:
            self.threadPool = QThreadPool.globalInstance()
        else:
            self.threadPool = QThreadPool()
        self.taskMap = {}
        self.tasks: Dict[int, QBaseTask] = {}
        self.taskCounter = 0

    def deleteLater(self) -> None:
        if not self.useGlobalThreadPool:
            self.threadPool.clear()
            self.threadPool.waitForDone()
            self.threadPool.deleteLater()
        super().deleteLater()

    def _runTask(self, task: QBaseTask) -> QFuture:
        future = task._future
        future.setTaskID(task.taskID)
        future._state = State.RUNNING
        task.signal.finished.connect(self._taskDone)
        self.threadPool.start(task, priority=task.priority)
        return future

    def _createTask(self, target, priority, args, kwargs) -> QTask:
        future = QFuture()
        task = QTask(
            _id=self.taskCounter,
            future=future,
            target=target if target is functools.partial else functools.partial(target),
            priority=priority,
            executor=self,
            args=args,
            kwargs=kwargs,
        )
        self.tasks[self.taskCounter] = task
        self.taskCounter += 1
        return task

    def _asyncRun(self, target: Callable, priority: int, *args, **kwargs) -> QFuture:
        task = self._createTask(target, priority, args, kwargs)
        return self._runTask(task)

    def _asyncMap(
        self, target: Callable, iterable: List[Iterable], priority: int = 0
    ) -> QFuture:
        futures = []
        for args in iterable:
            futures.append(self._asyncRun(target, priority, *args))
        return QFuture.gather(futures)

    def _taskDone(self, fut: QFuture):
        """
        need manually set Future.setFailed() or Future.setResult() to be called!!!
        """
        self.tasks.pop(fut.getTaskID())
        e = fut.getExtra("exception")
        if isinstance(e, Exception):
            fut.setFailed(e)
            fut._state = State.FAILED
        else:
            fut.setResult(fut.getExtra("result"))
            fut._state = State.SUCCESS

    def _taskCancel(self, fut: QFuture) -> None:
        stack: List[QFuture] = [fut]
        while stack:
            f = stack.pop()
            if not f.hasChildren() and not f.isDone():
                self._taskSingleCancel(f)
                f.setFailed(FutureCancelled())
            stack.extend(f.getChildren())

    def _taskSingleCancel(self, fut: QFuture) -> None:
        _id = fut.getTaskID()
        taskRef: QBaseTask = self.tasks[_id]
        if taskRef is not None:
            try:
                taskRef.setAutoDelete(False)
                self.threadPool.tryTake(taskRef)
                taskRef.setAutoDelete(True)
            except RuntimeError:
                print("wrapped C/C++ object of type BaseTask has been deleted")
        del taskRef

    def cancelTask(self, fut: QFuture) -> None:
        """
        currently, this method can not work properly...
        """
        warnings.warn(
            "BaseTaskExecutor.cancelTask: currently, this method can not work properly...",
            DeprecationWarning,
        )
        self._taskCancel(fut)

    @property
    def workers(self) -> int:
        return self.threadPool.maxThreadCount()

    @workers.setter
    def workers(self, workers: int) -> None:
        self.threadPool.setMaxThreadCount(workers)


class TaskExecutor(BaseTaskExecutor):
    _globalInstance = None

    @staticmethod
    def globalInstance() -> "TaskExecutor":
        if TaskExecutor._globalInstance is None:
            TaskExecutor._globalInstance = TaskExecutor()
        return TaskExecutor._globalInstance

    @classmethod
    def run(cls, target: Callable, *args, **kwargs) -> QFuture:
        """
        use the global TaskExecutor instance to avoid task ID conflicts
        :param target:
        :param args: *arg for target
        :param kwargs: **kwargs for target
        :return:
        """
        return cls.globalInstance()._asyncRun(target, 0, *args, **kwargs)

    @classmethod
    def runWithPriority(
        cls, target: Callable, priority: int, *args, **kwargs
    ) -> QFuture:
        """
        use the global TaskExecutor instance to avoid task ID conflicts
        :param target:
        :param priority: Task priority
        :param args: *arg for target
        :param kwargs: **kwargs for target
        :return:
        """
        return cls.globalInstance()._asyncRun(target, priority, *args, **kwargs)

    @classmethod
    def map(cls, target: Callable, iter_: Iterable, priority: int = 0) -> QFuture:
        """
        a simple wrapper for createTask and runTasks.

        iter_ must be like : [1, 2, 3] for [(1, 2), (3, 4)],
        if you need **kwargs in iter_, use createTask instead.
        """
        taskList = []
        for args in iter_:
            if isinstance(args, tuple):
                taskList.append(cls.createTask(target, priority=priority, *args))
            else:
                taskList.append(cls.createTask(target, args, priority=priority))
        return cls.runTasks(taskList)

    @classmethod
    def createTask(cls, target: Callable, *args, **kwargs) -> QTask:
        return cls.globalInstance()._createTask(target, 0, args, kwargs)

    @classmethod
    def runTask(cls, task: QTask) -> QFuture:
        return cls.globalInstance()._runTask(task)

    @classmethod
    def runTasks(cls, tasks: List[QTask]) -> QFuture:
        futs = []
        for task in tasks:
            futs.append(cls.runTask(task))
        return QFuture.gather(futs)


class UniqueTaskExecutor(BaseTaskExecutor):
    def __init__(self, workers: int = CPU_COUNTS):
        super().__init__(useGlobalThreadPool=False)
        self.workers = workers

    def run(self, target: Callable, *args, **kwargs) -> QFuture:
        """
        use the global TaskExecutor instance to avoid task ID conflicts
        :param target:
        :param args: *arg for target
        :param kwargs: **kwargs for target
        :return:
        """
        return self._asyncRun(target, 0, *args, **kwargs)

    def runWithPriority(
        self, target: Callable, priority: int, *args, **kwargs
    ) -> QFuture:
        """
        use the global TaskExecutor instance to avoid task ID conflicts
        :param target:
        :param priority: Task priority
        :param args: *arg for target
        :param kwargs: **kwargs for target
        :return:
        """
        return self._asyncRun(target, priority, *args, **kwargs)

    def map(self, target: Callable, iter_: Iterable, priority: int = 0) -> QFuture:
        """
        a simple wrapper for createTask and runTasks.

        iter_ must be like : [1, 2, 3] for [(1, 2), (3, 4)],
        if you need **kwargs in iter_, use createTask instead.
        """
        taskList = []
        for args in iter_:
            if isinstance(args, tuple):
                taskList.append(self.createTask(target, priority=priority, *args))
            else:
                taskList.append(self.createTask(target, args, priority=priority))
        return self.runTasks(taskList)

    def createTask(self, target: Callable, *args, **kwargs) -> QTask:
        return self._createTask(target, 0, args, kwargs)

    def runTask(self, task: QTask) -> QFuture:
        return self._runTask(task)

    def runTasks(self, tasks: List[QTask]) -> QFuture:
        futs = []
        for task in tasks:
            futs.append(self.runTask(task))
        return QFuture.gather(futs)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.threadPool.waitForDone()
        self.deleteLater()
