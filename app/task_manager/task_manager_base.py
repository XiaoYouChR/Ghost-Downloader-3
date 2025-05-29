import abc
from typing import List, Dict, TYPE_CHECKING, Optional  # Added Optional

from PySide6.QtCore import QObject, Signal

from app.common.dto import OverallProgressInfo, TaskUIData

if TYPE_CHECKING:
    from app.download.download_task_base import DownloadTaskBase

class TaskManagerBase(QObject):
    # Signals related to a specific task often include taskId.
    # For a single-task manager, taskId might often be its own managerId or a known ID.
    taskAdded = Signal(str) # taskId of the task added
    taskRemoved = Signal(str) # taskId of the task removed
    taskUiDataUpdated = Signal(str, TaskUIData) # taskId, uiData
    overallProgressUpdated = Signal(OverallProgressInfo) # Overall progress DTO
    taskSpecificError = Signal(str, str) # taskId, errorMessage
    allTasksCompleted = Signal() # Emitted when the managed task(s) reach a terminal state.

    def __init__(self, managerId: str, parent: QObject = None):
        super().__init__(parent)
        self._managerId = managerId # ID of the manager instance itself

    @property
    def managerId(self) -> str:
        """The unique identifier for this task manager instance."""
        return self._managerId

    @abc.abstractmethod
    def addTask(self, downloadTask: 'DownloadTaskBase') -> None:
        """
        Adds a download task to be managed. 
        For single-task managers, this might replace the current task.
        """
        pass

    @abc.abstractmethod
    def removeTask(self, taskId: str) -> None:
        """
        Removes a specific download task. 
        For single-task managers, this would clear the managed task if taskId matches.
        """
        pass

    @abc.abstractmethod
    def getTask(self, taskId: Optional[str] = None) -> Optional['DownloadTaskBase']:
        """
        Retrieves a managed download task. 
        For single-task managers, taskId might be optional or ignored, returning the single task.
        If taskId is provided, it should match the managed task's ID.
        """
        pass

    @abc.abstractmethod
    def getAllTasks(self) -> List['DownloadTaskBase']:
        """
        Returns a list of all tasks managed. 
        For single-task managers, this list would contain zero or one task.
        """
        pass

    @abc.abstractmethod
    def pauseTask(self, taskId: Optional[str] = None) -> None:
        """
        Pauses a specific download task.
        For single-task managers, taskId might be optional.
        """
        pass

    @abc.abstractmethod
    def resumeTask(self, taskId: Optional[str] = None) -> None:
        """
        Resumes a specific download task.
        For single-task managers, taskId might be optional.
        """
        pass

    @abc.abstractmethod
    def cancelTask(self, taskId: Optional[str] = None) -> None:
        """
        Cancels a specific download task.
        For single-task managers, taskId might be optional.
        """
        pass

    @abc.abstractmethod
    def pauseAllTasks(self) -> None:
        """
        Pauses all managed tasks. For single-task manager, pauses its task.
        """
        pass

    @abc.abstractmethod
    def resumeAllTasks(self) -> None:
        """
        Resumes all managed tasks. For single-task manager, resumes its task.
        """
        pass

    @abc.abstractmethod
    def cancelAllTasks(self) -> None:
        """
        Cancels all managed tasks. For single-task manager, cancels its task.
        """
        pass

    @abc.abstractmethod
    def getOverallProgress(self) -> OverallProgressInfo:
        """
        Returns the overall progress, which for a single-task manager is its task's progress.
        """
        pass

    @abc.abstractmethod
    def saveTasksState(self) -> List[Dict]:
        """
        Returns a list of persistent states for all managed tasks.
        For a single-task manager, this list contains one item or is empty.
        """
        pass

    @abc.abstractmethod
    def loadTasksState(self, tasksState: List[Dict]) -> None:
        """
        Loads tasks from a list of persistent states.
        For a single-task manager, expects zero or one item in tasksState.
        """
        pass
        
    @abc.abstractmethod
    def getTaskUiData(self, taskId: Optional[str] = None) -> Optional[TaskUIData]: # Changed from getTaskUIData
        """
        Gets UI-formatted data for a task. taskId might be optional for single-task managers.
        """
        pass
