import abc

from PySide6.QtCore import Signal

from app.common.dto import TaskProgressInfo, TaskFileInfo  # Import DTOs


class DownloadTaskBase:
    statusChanged = Signal(str) # e.g., "downloading", "paused", "completed", "error", "cancelled"
    progressUpdated = Signal(TaskProgressInfo) # payload same as getProgress()
    finished = Signal() # Emitted when the QThread execution finishes (success, error, or cancellation)
    errorOccurred = Signal(str) # errorMessage
    infoUpdated = Signal(TaskFileInfo) # e.g. when fileName is resolved, or other file metadata

    @property
    def taskId(self) -> str: # Renamed from task_id
        return self._taskId

    @abc.abstractmethod
    def start(self):
        pass

    @abc.abstractmethod
    def pause(self):
        pass

    @abc.abstractmethod
    def resume(self):
        pass

    @abc.abstractmethod
    def cancel(self):
        pass

    @abc.abstractmethod
    def getProgress(self) -> TaskProgressInfo:
        # Should return a TaskProgressInfo DTO instance.
        pass

    @abc.abstractmethod
    def getFileInfo(self) -> TaskFileInfo:
        # Should return a TaskFileInfo DTO instance.
        pass
        
    @abc.abstractmethod
    def saveState(self) -> dict:
        # For task-specific state. Common state (like taskId, type) is managed by TaskManager.
        return {}

    @abc.abstractmethod
    def loadState(self, state: dict):
        # For task-specific state.
        pass
