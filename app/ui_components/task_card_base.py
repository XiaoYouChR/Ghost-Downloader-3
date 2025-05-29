import abc
from typing import TYPE_CHECKING

from PySide6.QtCore import Slot, Signal
from PySide6.QtWidgets import QWidget
from qfluentwidgets import CardWidget

from app.common.dto import TaskUIData, TaskFileInfo, TaskProgressInfo  # Import DTOs

if TYPE_CHECKING:
    from app.task_manager.task_manager_base import TaskManagerBase

class TaskCardBase(CardWidget):
    """
    Abstract base class for UI task cards.
    It connects to a TaskManagerBase instance to receive updates for a specific task
    and provides methods for user interactions to control the task via the manager.
    """

    # Signal to be emitted when a user action requires the card to be removed from the UI
    # e.g., after a task is cancelled and its removal is confirmed.
    requestRemove = Signal(str) # taskId

    def __init__(self, taskManager: 'TaskManagerBase', parent: QWidget = None):
        super().__init__(parent)
        self._taskManager = taskManager
        self._currentTaskId: str = None 

        # Connect signals from the TaskManager
        # These connections are general; handlers will filter by taskId
        self._taskManager.taskUiDataUpdated.connect(self._handleTaskUIDataUpdated)
        self._taskManager.taskSpecificError.connect(self._handleTaskSpecificError)
        # Consider connecting to taskRemoved if the card needs to react when its task is removed by other means
        self._taskManager.taskRemoved.connect(self._handleTaskRemoved)


    @abc.abstractmethod
    def updateDisplay(self, uiData: TaskUIData) -> None:
        """
        Abstract method to refresh the card's display with new data.
        Subclasses must implement this to update their specific UI elements.
        """
        pass

    def setTaskId(self, taskId: str) -> None:
        """
        Associates this card with a specific task ID.
        Triggers an initial display update.
        """
        self._currentTaskId = taskId
        if self._currentTaskId:
            initialUiData = self._taskManager.getTaskUiData(self._currentTaskId)
            if initialUiData: # This is now a TaskUIData object or None
                self.updateDisplay(initialUiData)
            else:
                # Create a default TaskUIData for "initializing" or "empty" state
                # This ensures updateDisplay always receives the correct type.
                # DefaultTaskCard's updateDisplay will need to handle this gracefully.
                default_file_info = TaskFileInfo(fileName=self.tr("Initializing..."))
                default_progress_info = TaskProgressInfo(statusText="Initializing...")
                self.updateDisplay(TaskUIData(taskId=taskId if taskId else "", 
                                              fileInfo=default_file_info, 
                                              progressInfo=default_progress_info,
                                              errorMessage=None))
        else:
            # Handle case where taskId is cleared
            default_file_info = TaskFileInfo()
            default_progress_info = TaskProgressInfo()
            self.updateDisplay(TaskUIData(taskId="", 
                                          fileInfo=default_file_info, 
                                          progressInfo=default_progress_info,
                                          errorMessage=None))


    def getTaskId(self) -> str:
        """Returns the task ID this card is currently associated with."""
        return self._currentTaskId

    @Slot(str, TaskUIData) # Changed from dict to TaskUIData
    def _handleTaskUIDataUpdated(self, taskId: str, uiData: TaskUIData) -> None:
        """
        Slot for the taskManager's taskUIDataUpdated signal.
        Updates the display if the taskId matches this card's currentTaskId.
        """
        if self.getTaskId() and taskId == self.getTaskId():
            self.updateDisplay(uiData)

    @Slot(str, str)
    def _handleTaskSpecificError(self, taskId: str, errorMessage: str) -> None:
        """
        Slot for the taskManager's taskSpecificError signal.
        Displays an error if the taskId matches.
        Subclasses should provide a more user-friendly error display.
        """
        if self.getTaskId() and taskId == self.getTaskId():
            # Placeholder: Subclasses should implement a better error display
            print(f"TaskCardBase Error for {taskId}: {errorMessage}")
            # Create a TaskUIData object to pass to updateDisplay
            # This assumes that the DefaultTaskCard's updateDisplay can handle an error message
            # by checking uiData.errorMessage or uiData.progressInfo.statusText
            # For now, we'll construct a minimal TaskUIData with the error.
            # The actual fileInfo and progressInfo might be stale or unavailable.
            
            # Try to get existing data, but fallback if task is gone or data is bad
            currentUiData = self._taskManager.getTaskUiData(taskId) if self._taskManager else None
            if not currentUiData: # If task is gone or returns None
                file_info = TaskFileInfo(fileName=self.tr("Error"))
                progress_info = TaskProgressInfo(statusText=f"Error: {errorMessage}")
                currentUiData = TaskUIData(taskId=taskId, fileInfo=file_info, progressInfo=progress_info, errorMessage=errorMessage)
            else:
                currentUiData.errorMessage = errorMessage
                # Optionally, update progressInfo.statusText if that's where the error is primarily displayed
                # currentUiData.progressInfo.statusText = f"Error: {errorMessage}"

            self.updateDisplay(currentUiData)


    @Slot(str)
    def _handleTaskRemoved(self, taskId: str) -> None:
        """
        Slot for the taskManager's taskRemoved signal.
        If the removed task is the one this card is displaying,
        it could emit a signal to have itself removed from the UI.
        """
        if self.getTaskId() and taskId == self.getTaskId():
            print(f"TaskCardBase: Task {taskId} was removed by manager. Requesting UI removal.")
            self.requestRemove.emit(self.getTaskId())


    # --- User Interaction Methods ---
    # These methods are called by UI elements in subclasses (e.g., button clicks)

    def onPauseClicked(self) -> None:
        """Handles a pause request from the UI."""
        if self.getTaskId() and self._taskManager:
            self._taskManager.pauseTask(self.getTaskId())
        else:
            print(f"TaskCardBase: Cannot pause. TaskId: {self.getTaskId()}, Manager: {self._taskManager}")


    def onResumeClicked(self) -> None:
        """Handles a resume request from the UI."""
        if self.getTaskId() and self._taskManager:
            self._taskManager.resumeTask(self.getTaskId())
        else:
            print(f"TaskCardBase: Cannot resume. TaskId: {self.getTaskId()}, Manager: {self._taskManager}")


    def onCancelClicked(self) -> None:
        """Handles a cancel request from the UI."""
        if self.getTaskId() and self._taskManager:
            # The TaskManager's cancelTask might lead to taskRemoved signal,
            # which _handleTaskRemoved would then catch to request UI removal.
            self._taskManager.cancelTask(self.getTaskId())
        else:
            print(f"TaskCardBase: Cannot cancel. TaskId: {self.getTaskId()}, Manager: {self._taskManager}")

    def onOpenFolderClicked(self) -> None:
        """Handles an open folder request from the UI."""
        if self.getTaskId() and self._taskManager:
            taskUiData = self._taskManager.getTaskUiData(self.getTaskId()) # Returns TaskUIData or None
            if taskUiData:
                filePath = taskUiData.fileInfo.filePath
                fileName = taskUiData.fileInfo.fileName
                status = taskUiData.progressInfo.statusText.lower()

                if status == "completed" and filePath and fileName:
                    # Requires a method to actually open the folder, e.g., using QDesktopServices
                    print(f"TaskCardBase: Request to open folder for task {self.getTaskId()} at path: {filePath}")
                    # Actual implementation would call a utility method.
                    # Example: common.methods.openFile(filePath)
                else:
                    print(f"TaskCardBase: Cannot open folder for task {self.getTaskId()}. Status: {status}, Path: {filePath}")
            else:
                print(f"TaskCardBase: Could not retrieve task UI data for folder open: {self.getTaskId()}")
        else:
            print(f"TaskCardBase: Cannot open folder. TaskId: {self.getTaskId()}, Manager: {self._taskManager}")

    def onRetryClicked(self) -> None:
        # This is platform-dependent and should ideally be handled by a utility function.
        # from PySide6.QtGui import QDesktopServices
        # from PySide6.QtCore import QUrl
        # import os
        # QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.join(filePath)))
        # Actual implementation would call a utility method.
        # For now, this is a placeholder.
        """Handles a retry request from the UI, typically for errored tasks."""
        if self.getTaskId() and self._taskManager:
            # Retry might be similar to resume, or might require specific manager logic
            print(f"TaskCardBase: Retry requested for task {self.getTaskId()}. Assuming resume for now.")
            self._taskManager.resumeTask(self.getTaskId()) # Or a specific retry method if available
        else:
            print(f"TaskCardBase: Cannot retry. TaskId: {self.getTaskId()}, Manager: {self._taskManager}")
