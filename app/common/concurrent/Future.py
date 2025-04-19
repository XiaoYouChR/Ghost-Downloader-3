import enum
from typing import List, Optional, Callable, Iterable, Sized, Tuple, Union

from PySide6.QtCore import QObject, Signal, QMutex, QSemaphore, QCoreApplication


class FutureError(BaseException):
    pass


class State(enum.Enum):
    PENDING = 0
    RUNNING = 1
    FAILED = 2
    SUCCESS = 3


class FutureFailed(FutureError):
    def __init__(self, _exception: Optional[BaseException]):
        super().__init__()
        self.exception = _exception

    def __repr__(self):
        return f"FutureFailed({self.exception})"

    def __str__(self):
        return f"FutureFailed({self.exception})"

    @property
    def original(self):
        return self.exception


class GatheredFutureFailed(FutureError):
    def __init__(self, failures: List[Tuple["QFuture", BaseException]]):
        super().__init__()
        self.failures = failures

    def __repr__(self):
        return f"GatheredFutureFailed({self.failures})"

    def __str__(self):
        return f"GatheredFutureFailed({self.failures})"

    def __iter__(self):
        return iter(self.failures)

    def __len__(self):
        return len(self.failures)


class FutureCancelled(FutureError):
    def __init__(self):
        super().__init__()

    def __repr__(self):
        return "FutureCanceled()"

    def __str__(self):
        return "FutureCanceled()"


class QFuture(QObject):
    result = Signal(object)  # self
    finished = Signal(object)  # self
    failed = Signal(object)  # self
    partialDone = Signal(object)  # child future
    childrenDone = Signal(object)  # self

    def __init__(self, semaphore=0):
        super().__init__()
        self._taskID = -1
        self._failedCallback = lambda e: None
        self._done = False
        self._failed = False
        self._result = None
        self._exception = None
        self._children = []
        self._counter = 0
        self._parent = None
        self._callback = lambda _: None
        self._mutex = QMutex()
        self._extra = {}
        self._state = State.PENDING  # set state by TaskExecutor
        self._semaphore = QSemaphore(semaphore)

    def __onChildFinished(self, childFuture: "QFuture") -> None:
        self._mutex.lock()
        if childFuture.isFailed():
            self._failed = True
        self._counter += 1
        self.partialDone.emit(childFuture)
        try:
            idx = getattr(childFuture, "_idx")
            self._result[idx] = childFuture._result
            self._mutex.unlock()
        except AttributeError:
            self._mutex.unlock()
            raise RuntimeError(
                "Invalid child future: please ensure that the child future is created by method 'Future.setChildren'"
            )
        if self._counter == len(self._children):
            if self._failed:  # set failed
                fails = []
                for i, child in enumerate(self._children):
                    e = child.getException()
                    if isinstance(e, FutureError):
                        fails.append((self._children[i], e))
                self.setFailed(GatheredFutureFailed(fails))
            else:
                self.setResult(self._result)

    def __setChildren(self, children: List["QFuture"]) -> None:
        self._children = children
        self._result = [None] * len(children)
        for i, fut in enumerate(self._children):
            setattr(fut, "_idx", i)
            fut.childrenDone.connect(self.__onChildFinished)
            fut._parent = self
        for fut in self._children:  # check if child is done
            if fut.isDone():
                self.__onChildFinished(fut)

    def unsafeAddChild(self, child: "QFuture") -> None:
        """
        use before your wait the parent future
        """
        i = len(self._children)
        self._children.append(child)
        self._result.append(None)

        setattr(child, "_idx", i)
        child.childrenDone.connect(self.__onChildFinished)
        child._parent = self

        if child.isDone():
            self.__onChildFinished(child)

    def setResult(self, result) -> None:
        """
        :param result: The result to set
        :return: None

        do not set result in thread pool,or it may not set correctly
        please use in main thread,or use signal-slot to set result !!!
        """
        if not self._done:
            self._result = result
            self._done = True
            if self._parent:
                self.childrenDone.emit(self)
            if self._callback:
                self._callback(result)

            self._state = State.SUCCESS
            self.result.emit(result)
            self.finished.emit(self)
        else:
            raise RuntimeError("Future already done")
        # self.deleteLater()  # delete this future object

    def setFailed(self, exception) -> None:
        """
        :param exception: The exception to set
        :return: None
        """
        if not self._done:
            self._exception = FutureFailed(exception)
            self._done = True
            self._failed = True
            if self._parent:
                self.childrenDone.emit(self)
            if self._failedCallback:
                self._failedCallback(self)

            self._state = State.FAILED
            self.failed.emit(self._exception)
            self.finished.emit(self)
        else:
            raise RuntimeError("Future already done")
        # self.deleteLater()

    def setCallback(
        self,
        callback: Callable[
            [
                object,
            ],
            None,
        ],
    ) -> None:
        self._callback = callback

    def setFailedCallback(
        self,
        callback: Callable[
            [
                "QFuture",
            ],
            None,
        ],
    ) -> None:
        self._failedCallback = lambda e: callback(self)

    def then(
        self,
        onSuccess: Callable,
        onFailed: Callable = None,
        onFinished: Callable = None,
    ) -> "QFuture":
        self.result.connect(onSuccess)
        if onFailed:
            self.failed.connect(onFailed)
        if onFinished:
            self.finished.connect(onFinished)
        return self

    def hasException(self) -> bool:
        if self._children:
            return any([fut.hasException() for fut in self._children])
        else:
            return self._exception is not None

    def hasChildren(self) -> bool:
        return bool(self._children)

    def getException(self) -> Optional[BaseException]:
        return self._exception

    def setTaskID(self, _id: int) -> None:
        if self._taskID != -1:
            raise RuntimeError("Task ID can only be set once")

        self._state = State.RUNNING
        self._taskID = _id

    def getTaskID(self) -> int:
        """
        -1 means that the bound task is pending rather running
        """
        return self._taskID

    def getChildren(self) -> List["QFuture"]:
        return self._children

    @staticmethod
    def gather(futures: {Iterable, Sized}) -> "QFuture":
        """
        :param futures: An iterable of Future objects
        :return: A Future object that will be done when all futures are done
        """

        future = QFuture()
        future.__setChildren(futures)
        return future

    @property
    def semaphore(self) -> QSemaphore:
        return self._semaphore

    @property
    def state(self):
        """
        if future is not bound to a task (produced by QFuture.gather),its state will skip state.RUNNING (not really running in thread pool)
        :return: QFuture state.
        """
        return self._state

    def wait(self) -> None:
        if self.hasChildren():
            for child in self.getChildren():
                child.wait()
        else:
            self.semaphore.acquire(1)
            QCoreApplication.processEvents()

    def synchronize(self) -> None:
        self.wait()

    def isDone(self) -> bool:
        return self._done

    def isFailed(self) -> bool:
        return self._failed

    def getResult(self) -> Union[object, List[object]]:
        return self._result

    def setExtra(self, key, value) -> None:
        self._extra[key] = value

    def getExtra(self, key) -> object:
        return self._extra.get(key, None)

    def hasExtra(self, key) -> bool:
        return key in self._extra

    def __getattr__(self, item):
        return self.getExtra(item)

    def __repr__(self):
        return f"Future:({self._result})"

    def __str__(self):
        return f"Future({self._result})"

    def __eq__(self, other):
        return self._result == other.getResult()
