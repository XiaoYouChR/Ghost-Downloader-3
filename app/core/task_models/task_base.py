from _abc import _abc_init
from abc import abstractmethod, ABCMeta

from PySide6.QtCore import Signal, QThread

from app.core.dto import TaskProgressInfo, TaskFileInfo


class TaskABCMeta(ABCMeta, type(QThread)):
    def __new__(mcls, name, bases, ns, **kwargs):
        cls = super().__new__(mcls, name, bases, ns, **kwargs)
        _abc_init(cls)
        return cls
    def __call__(cls, *args, **kwargs):
        if cls.__abstractmethods__:
            raise NotImplementedError
        return super().__call__(*args, **kwargs)


class TaskBase(QThread, metaclass=TaskABCMeta):
    statusChanged = Signal(str) # e.g., "downloading", "paused", "completed", "error", "cancelled"
    progressUpdated = Signal(TaskProgressInfo) # payload same as getProgress()
    finished = Signal() # Emitted when the QThread execution finishes (success, error, or cancellation)
    errorOccurred = Signal(str) # errorMessage
    infoUpdated = Signal(TaskFileInfo) # e.g. when fileName is resolved, or other file metadata
    
    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    def pause(self):
        pass

    @abstractmethod
    def resume(self):
        pass

    @abstractmethod
    def cancel(self):
        pass

    @abstractmethod
    def getProgress(self) -> TaskProgressInfo:
        # Should return a TaskProgressInfo DTO instance.
        pass

    @abstractmethod
    def getFileInfo(self) -> TaskFileInfo:
        # Should return a TaskFileInfo DTO instance.
        pass

    @abstractmethod
    def saveState(self) -> dict:
        # For task-specific state. Common state (like taskId, type) is managed by TaskManager.
        return {}

    @abstractmethod
    def loadState(self, state: dict):
        # For task-specific state.
        pass
