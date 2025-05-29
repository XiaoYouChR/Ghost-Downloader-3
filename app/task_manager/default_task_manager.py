from functools import partial
from typing import List, Dict, TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, Slot
from loguru import logger

from app.common.dto import TaskProgressInfo, TaskFileInfo, TaskUIData, OverallProgressInfo
from app.download.default_download_task import DefaultDownloadTask
from app.task_manager.task_manager_base import TaskManagerBase  # Already updated

if TYPE_CHECKING:
    from app.download.download_task_base import DownloadTaskBase


class DefaultTaskManager(TaskManagerBase):
    def __init__(self, managerId: str, parent: QObject = None):
        super().__init__(managerId, parent)
        self._downloadTask: Optional['DownloadTaskBase'] = None
        self._overallProgressCache = OverallProgressInfo() # Represents the single task's progress

    def addTask(self, downloadTask: 'DownloadTaskBase') -> None:
        if self._downloadTask and self._downloadTask.taskId == downloadTask.taskId:
            logger.warning(f"Task with ID {downloadTask.taskId} is already managed. Ignoring new task.")
            return
        
        if self._downloadTask:
            logger.info(f"Replacing existing task {self._downloadTask.taskId} with new task {downloadTask.taskId}.")
            self._disconnectSignals(self._downloadTask)
        
        self._downloadTask = downloadTask
        logger.info(f"Task added: {downloadTask.taskId}")

        self._connectSignals(downloadTask)

        self.taskAdded.emit(downloadTask.taskId)
        self._updateOverallProgress()

    def _connectSignals(self, task: 'DownloadTaskBase'):
        # Connect signals from the download task to internal slots
        # Using partial to pass the taskId of the emitting task to the handler
        task.statusChanged.connect(
            partial(self._handleTaskStatusChanged, task.taskId)
        )
        task.progressUpdated.connect(
            partial(self._handleTaskProgressUpdated, task.taskId)
        )
        task.finished.connect(
            partial(self._handleTaskFinished, task.taskId)
        )
        task.errorOccurred.connect(
            partial(self._handleTaskErrorOccurred, task.taskId)
        )
        task.infoUpdated.connect(
            partial(self._handleTaskInfoUpdated, task.taskId)
        )

    def _disconnectSignals(self, task: 'DownloadTaskBase'):
        try:
            task.statusChanged.disconnect()
            task.progressUpdated.disconnect()
            task.finished.disconnect()
            task.errorOccurred.disconnect()
            task.infoUpdated.disconnect()
            logger.debug(f"Disconnected all signals for task {task.taskId} (or attempted to).")
        except RuntimeError as e: # pragma: no cover
            logger.warning(f"Error during generic disconnect for task {task.taskId}: {e}. This might be normal if signals were not connected or already disconnected.")


    def removeTask(self, taskId: str) -> None:
        if self._downloadTask and self._downloadTask.taskId == taskId:
            taskToClear = self._downloadTask
            self._downloadTask = None # Clear the reference
            self._disconnectSignals(taskToClear)
            
            logger.info(f"Task removed: {taskId}")
            self.taskRemoved.emit(taskId)
            self._updateOverallProgress() 
        else:
            logger.warning(f"Task with ID {taskId} not found for removal or does not match current task.")

    def getTask(self, taskId: Optional[str] = None) -> Optional['DownloadTaskBase']:
        if taskId is None: # If no taskId provided, return the current task
            return self._downloadTask
        if self._downloadTask and self._downloadTask.taskId == taskId:
            return self._downloadTask
        return None

    def getAllTasks(self) -> List['DownloadTaskBase']:
        return [self._downloadTask] if self._downloadTask else []

    def pauseTask(self, taskId: Optional[str] = None) -> None:
        currentTask = self.getTask(taskId) # taskId can be None
        if currentTask:
            if taskId is None or currentTask.taskId == taskId:
                currentTask.pause()
            else: # pragma: no cover
                logger.warning(f"Pause failed: Task ID {taskId} does not match current task {currentTask.taskId}.")
        else:
            logger.warning(f"Pause failed: Task {taskId if taskId else 'current'} not found.")


    def resumeTask(self, taskId: Optional[str] = None) -> None:
        currentTask = self.getTask(taskId)
        if currentTask:
            if taskId is None or currentTask.taskId == taskId:
                currentTask.resume()
            else: # pragma: no cover
                logger.warning(f"Resume failed: Task ID {taskId} does not match current task {currentTask.taskId}.")
        else:
            logger.warning(f"Resume failed: Task {taskId if taskId else 'current'} not found.")

    def cancelTask(self, taskId: Optional[str] = None) -> None:
        currentTask = self.getTask(taskId)
        if currentTask:
            if taskId is None or currentTask.taskId == taskId:
                currentTask.cancel()
            else: # pragma: no cover
                logger.warning(f"Cancel failed: Task ID {taskId} does not match current task {currentTask.taskId}.")
        else:
            logger.warning(f"Cancel failed: Task {taskId if taskId else 'current'} not found.")


    def pauseAllTasks(self) -> None: # Operates on the single task
        if self._downloadTask:
            logger.info(f"Pausing task {self._downloadTask.taskId} (via pauseAllTasks).")
            self._downloadTask.pause()
        else:
            logger.info("No task to pause (via pauseAllTasks).")

    def resumeAllTasks(self) -> None: # Operates on the single task
        if self._downloadTask:
            logger.info(f"Resuming task {self._downloadTask.taskId} (via resumeAllTasks).")
            self._downloadTask.resume()
        else:
            logger.info("No task to resume (via resumeAllTasks).")


    def cancelAllTasks(self) -> None: # Operates on the single task
        if self._downloadTask:
            logger.info(f"Cancelling task {self._downloadTask.taskId} (via cancelAllTasks).")
            self._downloadTask.cancel()
        else:
            logger.info("No task to cancel (via cancelAllTasks).")


    def getOverallProgress(self) -> OverallProgressInfo:
        return self._overallProgressCache

    def _updateOverallProgress(self):
        if self._downloadTask:
            progressInfoDto = self._downloadTask.getProgress()
            if progressInfoDto: # Check if DTO is not None
                status = progressInfoDto.statusText.lower()
                activeTasks = 1 if status in ["downloading", "starting", "resuming"] else 0
                
                self._overallProgressCache = OverallProgressInfo(
                    totalTasks=1, # Always 1 if a task exists
                    activeTasks=activeTasks,
                    overallDownloadedBytes=progressInfoDto.downloadedBytes,
                    overallTotalBytes=progressInfoDto.totalBytes if progressInfoDto.totalBytes > 0 else 0,
                    overallSpeedBps=progressInfoDto.speedBps
                )
            else: # pragma: no cover - Task exists but getProgress is None (should ideally not happen)
                self._overallProgressCache = OverallProgressInfo(totalTasks=1, activeTasks=0, overallSpeedBps=0)
        else: # No task
            self._overallProgressCache = OverallProgressInfo(totalTasks=0, activeTasks=0, overallSpeedBps=0)
        
        self.overallProgressUpdated.emit(self._overallProgressCache)


    def saveTasksState(self) -> List[Dict]:
        if self._downloadTask:
            fileInfoDto = self._downloadTask.getFileInfo() 
            progressInfoDto = self._downloadTask.getProgress()
            # Ensure DTOs are valid before trying to access attributes
            if fileInfoDto and progressInfoDto:
                state = {
                    "taskId": self._downloadTask.taskId,
                    "taskType": self._downloadTask.__class__.__name__,  
                    "fileInfo": { 
                        "fileName": fileInfoDto.fileName,
                        "filePath": fileInfoDto.filePath,
                        "url": fileInfoDto.url,
                        "originalUrl": fileInfoDto.originalUrl,
                        "totalBytes": fileInfoDto.totalBytes,
                        "ableToParallelDownload": fileInfoDto.ableToParallelDownload,
                        "contentType": fileInfoDto.contentType,
                    },
                    "taskSpecificState": self._downloadTask.saveState(), 
                    "currentStatus": progressInfoDto.statusText
                }
                return [state]
        return [] # Return empty list if no task or DTOs are invalid

    def loadTasksState(self, tasksState: List[Dict]) -> None:
        if not tasksState:
            logger.info("No tasks state provided to load.")
            if self._downloadTask: # If there's an existing task, remove it
                self.removeTask(self._downloadTask.taskId)
            return

        if len(tasksState) > 1:
            logger.warning(f"DefaultTaskManager is single-task, but received {len(tasksState)} states. Loading the first one.")
        
        stateDict = tasksState[0]
        taskId = stateDict.get("taskId")
        taskType = stateDict.get("taskType")
        fileInfoDict = stateDict.get("fileInfo", {})
        taskSpecificState = stateDict.get("taskSpecificState", {})
        loadedStatus = stateDict.get("currentStatus", "paused") # Default to paused

        if not taskId or not taskType:
            logger.warning(f"Skipping task load due to missing taskId or taskType: {stateDict}")
            return

        # If there's an existing task and its ID is different, remove it first.
        if self._downloadTask and self._downloadTask.taskId != taskId:
            logger.info(f"Removing existing task {self._downloadTask.taskId} before loading new task {taskId}")
            self.removeTask(self._downloadTask.taskId) # This will set self._downloadTask to None
        elif self._downloadTask and self._downloadTask.taskId == taskId:
            # Task already exists, just apply state and status
            logger.info(f"Task {taskId} is already loaded. Applying state and status.")
            self._downloadTask.loadState(taskSpecificState)
            self._applyLoadedStatus(self._downloadTask, loadedStatus)
            return # Finished with this state dict

        # Create and load the new task (self._downloadTask is None or is the same task)
        newTask: Optional['DownloadTaskBase'] = None
        if taskType == "DefaultDownloadTask":
            # Ensure DefaultDownloadTask's __init__ uses camelCase for parameters
            newTask = DefaultDownloadTask(
                taskId=taskId, 
                url=fileInfoDict.get('url'),
                headers=taskSpecificState.get('headers', {}), 
                filePath=fileInfoDict.get('filePath'), 
                fileName=fileInfoDict.get('fileName'), 
                preBlockNum=taskSpecificState.get('preBlockNum', 8), 
                autoSpeedUp=taskSpecificState.get('autoSpeedUp', False), 
                fileSize=fileInfoDict.get('totalBytes', -1) 
            )
        else: # pragma: no cover
            logger.warning(f"Unknown task type '{taskType}' for task ID {taskId}. Cannot load.")
            return

        if newTask:
            newTask.loadState(taskSpecificState) 
            self.addTask(newTask) 
            self._applyLoadedStatus(newTask, loadedStatus)

    def _applyLoadedStatus(self, task: 'DownloadTaskBase', loadedStatus: str):
        """Helper to apply status to a newly loaded/added task, ensuring UI updates."""
        progressInfo = task.getProgress()
        if not progressInfo: # pragma: no cover
            logger.error(f"Cannot apply status for {task.taskId}, progress info unavailable.")
            return

        currentManagerStatus = progressInfo.statusText.lower()
        loadedStatusLower = loadedStatus.lower()
        
        actionTaken = False 

        if loadedStatusLower == "paused":
            if currentManagerStatus != "paused":
                task.pause()
                actionTaken = True
        elif loadedStatusLower in ["downloading", "working", "starting", "resuming"]:
            if currentManagerStatus not in ["downloading", "starting", "resuming"]:
                logger.info(f"Resuming task {task.taskId} from loaded state (status: {loadedStatus})")
                task.resume()
                actionTaken = True
        elif loadedStatusLower == "completed" and currentManagerStatus != "completed":
             logger.info(f"Task {task.taskId} loaded as completed. Ensuring UI reflects this.")
             actionTaken = True 
        elif loadedStatusLower == "error" and currentManagerStatus != "error":
             logger.info(f"Task {task.taskId} loaded with error state. Ensuring UI reflects this.")
             actionTaken = True
        
        if actionTaken: # If an action was taken, or if status might differ ensure UI is up to date
            self._updateOverallProgress() 
            uiDataDto = self.getTaskUiData(task.taskId)
            if uiDataDto:
                self.taskUiDataUpdated.emit(task.taskId, uiDataDto)
        else: # If no specific action, still ensure progress and UI are current
             self._updateOverallProgress()


    def getTaskUiData(self, taskId: Optional[str] = None) -> Optional[TaskUIData]:
        currentTask = self.getTask(taskId) 
        if currentTask:
            fileInfoDto = currentTask.getFileInfo()
            progressInfoDto = currentTask.getProgress()
            errorMessage = None

            if progressInfoDto and progressInfoDto.statusText.lower().startswith("error"):
                errorMessage = progressInfoDto.statusText

            if fileInfoDto and progressInfoDto: 
                return TaskUIData(
                    taskId=currentTask.taskId, 
                    fileInfo=fileInfoDto,
                    progressInfo=progressInfoDto,
                    errorMessage=errorMessage 
                )
            else: # pragma: no cover
                logger.warning(f"Could not get valid DTOs for task {currentTask.taskId} in getTaskUiData.")
        return None

    # Internal Slot Methods
    @Slot(str, str) 
    def _handleTaskStatusChanged(self, eventTaskId: str, status: str):
        if self._downloadTask and self._downloadTask.taskId == eventTaskId:
            logger.debug(f"Task {eventTaskId} status changed to: {status}")
            uiDataDto = self.getTaskUiData(eventTaskId) 
            if uiDataDto:
                self.taskUiDataUpdated.emit(eventTaskId, uiDataDto) 
            self._updateOverallProgress() 

            if status == "error":
                errorMsg = "Unknown error" 
                if uiDataDto: 
                    if uiDataDto.errorMessage:
                        errorMsg = uiDataDto.errorMessage
                    elif uiDataDto.progressInfo and uiDataDto.progressInfo.statusText.lower().startswith("error"):
                        errorMsg = uiDataDto.progressInfo.statusText 
                self.taskSpecificError.emit(eventTaskId, errorMsg)
            
            if status in ["completed", "cancelled", "error"]: 
                self._checkAllTasksCompleted()
        else: # pragma: no cover
            logger.debug(f"Status change from task {eventTaskId} which is not the current managed task or no task is managed.")


    @Slot(str, TaskProgressInfo) 
    def _handleTaskProgressUpdated(self, eventTaskId: str, progressData: TaskProgressInfo):
        if self._downloadTask and self._downloadTask.taskId == eventTaskId:
            uiDataDto = self.getTaskUiData(eventTaskId) 
            if uiDataDto:
                self.taskUiDataUpdated.emit(eventTaskId, uiDataDto) 
            self._updateOverallProgress() 
        else: # pragma: no cover
            logger.debug(f"Progress update from task {eventTaskId} which is not the current managed task or no task is managed.")


    @Slot(str)
    def _handleTaskFinished(self, eventTaskId: str):
        if self._downloadTask and self._downloadTask.taskId == eventTaskId:
            logger.debug(f"Task {eventTaskId} QThread finished (DownloadTaskBase.finished signal).")
            self._checkAllTasksCompleted()
        else: # pragma: no cover
            logger.debug(f"Finished signal from task {eventTaskId} which is not the current managed task or no task is managed.")


    @Slot(str, str)
    def _handleTaskErrorOccurred(self, eventTaskId: str, errorMessage: str):
         if self._downloadTask and self._downloadTask.taskId == eventTaskId:
            logger.error(f"Task {eventTaskId} reported an error: {errorMessage}")
            self.taskSpecificError.emit(eventTaskId, errorMessage) 
            
            uiDataDto = self.getTaskUiData(eventTaskId) 
            if uiDataDto: 
                self.taskUiDataUpdated.emit(eventTaskId, uiDataDto)
                
            self._updateOverallProgress()
            self._checkAllTasksCompleted() 
         else: # pragma: no cover
            logger.debug(f"ErrorOccurred signal from task {eventTaskId} which is not the current managed task or no task is managed.")


    @Slot(str, TaskFileInfo) 
    def _handleTaskInfoUpdated(self, eventTaskId: str, infoData: TaskFileInfo):
        if self._downloadTask and self._downloadTask.taskId == eventTaskId:
            logger.debug(f"Task {eventTaskId} info updated: {infoData.fileName}")
            uiDataDto = self.getTaskUiData(eventTaskId) 
            if uiDataDto:
                self.taskUiDataUpdated.emit(eventTaskId, uiDataDto)
            self._updateOverallProgress() 
        else: # pragma: no cover
            logger.debug(f"Info update from task {eventTaskId} which is not the current managed task or no task is managed.")


    def _checkAllTasksCompleted(self):
        if not self._downloadTask: 
            self.allTasksCompleted.emit()
            return

        progressInfoDto = self._downloadTask.getProgress()
        if progressInfoDto: 
            status = progressInfoDto.statusText.lower()
            if status in ["completed", "error", "cancelled"]: 
                logger.info(f"The task {self._downloadTask.taskId} has reached a terminal state: {status}.")
                self.allTasksCompleted.emit()
        else: # pragma: no cover
            logger.warning(f"Task {self._downloadTask.taskId} exists but getProgress returned None in _checkAllTasksCompleted.")
