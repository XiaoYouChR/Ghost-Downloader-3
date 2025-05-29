import uuid
from functools import partial  # Added partial
from typing import List, Dict

from PySide6.QtCore import Qt, Slot, Signal  # Added Signal
from PySide6.QtWidgets import QWidget, QFrame, QHBoxLayout, QVBoxLayout, QSpacerItem, QSizePolicy, \
    QApplication  # Added QApplication
from loguru import logger
from qfluentwidgets import FluentIcon as FIF, SmoothScrollArea, PrimaryPushButton, PushButton, InfoBar, \
    ToggleButton

from app.common.signal_bus import \
    signalBus  # signalBus.allTaskFinished will no longer be used by this class directly for plan
from app.download.default_download_task import DefaultDownloadTask
from app.task_manager.default_task_manager import DefaultTaskManager
from app.ui_components.default_task_card import DefaultTaskCard
from ..common.config import cfg, Headers
from ..components.custom_dialogs import DelDialog, PlanTaskDialog


class TaskInterface(SmoothScrollArea):
    allManagedTasksTerminated = Signal() # New signal for when all managed tasks are done

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setObjectName("TaskInterface")
        self._taskManagers: List[DefaultTaskManager] = []
        self._taskCards: Dict[str, DefaultTaskCard] = {} 
        self._activeManagerTaskIds: set[str] = set() # For tracking active managers
        self._setupUi() 
        
        self.allStartButton.clicked.connect(self.allStartTasks)
        self.allPauseButton.clicked.connect(self.allPauseTasks)
        self.allDeleteButton.clicked.connect(self.allCancelTasks)
        self.planTaskToggleButton.clicked.connect(self._onPlanTaskToggleBtnClicked) # Renamed

        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)

        signalBus.addTaskSignal.connect(self._createManagedTaskFromSignal) # Renamed slot

        self.setStyleSheet("""QScrollArea, .QWidget {
                                border: none;
                                background-color: transparent;
                            }""")

    def _setupUi(self): # Renamed
        self.setMinimumWidth(816)
        self.setFrameShape(QFrame.NoFrame)
        self.scrollWidget = QWidget()
        self.scrollWidget.setObjectName("scrollWidget")
        self.scrollWidget.setMinimumWidth(816)
        self.expandLayout = QVBoxLayout(self.scrollWidget)
        self.expandLayout.setObjectName("expandLayout")
        self.expandLayout.setAlignment(Qt.AlignTop)
        self.expandLayout.setContentsMargins(11, 11, 11, 0)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setContentsMargins(2,2,2,2)

        self.allStartButton = PrimaryPushButton(self)
        self.allStartButton.setObjectName(u"allStartButton")
        self.allStartButton.setIcon(FIF.PLAY)
        self.horizontalLayout.addWidget(self.allStartButton)

        self.allPauseButton = PushButton(self)
        self.allPauseButton.setObjectName(u"allPauseButton")
        self.allPauseButton.setIcon(FIF.PAUSE)
        self.horizontalLayout.addWidget(self.allPauseButton)

        self.allDeleteButton = PushButton(self)
        self.allDeleteButton.setObjectName(u"allDeleteButton")
        self.allDeleteButton.setIcon(FIF.DELETE)
        self.horizontalLayout.addWidget(self.allDeleteButton)

        self.planTaskToggleButton = ToggleButton(self)
        self.planTaskToggleButton.setObjectName(u"planTaskToggleButton")
        self.planTaskToggleButton.setIcon(FIF.CALENDAR)
        self.horizontalLayout.addWidget(self.planTaskToggleButton)

        self.horizontalLayout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.allStartButton.setText(self.tr("全部开始"))
        self.allPauseButton.setText(self.tr("全部暂停"))
        self.allDeleteButton.setText(self.tr("全部删除"))
        self.planTaskToggleButton.setText(self.tr("计划任务"))

        self.expandLayout.addLayout(self.horizontalLayout)
        self.scrollWidget.setMinimumWidth(816)

    @Slot(dict)
    def _createManagedTaskFromSignal(self, taskData: dict):
        url = taskData.get('url')
        fileName = taskData.get('fileName') 
        filePath = taskData.get('filePath')
        headers = taskData.get('headers', Headers) # Use default from cfg if not provided
        preBlockNum = taskData.get('preBlockNum', cfg.preBlockNum.value)
        taskType = taskData.get('taskType', "DefaultDownloadTask") # Default if not specified
        initialStatus = taskData.get('initialStatus', "pending") # "pending" for new, "paused" etc. for loaded
        taskSpecificStateForLoad = taskData.get('taskSpecificStateForLoad') # For loading existing tasks

        if not url or not filePath:
            logger.error(f"TaskInterface: Insufficient data to add task. URL or filePath missing. Data: {taskData}")
            InfoBar.error(title=self.tr('错误'), content=self.tr("无法创建任务：URL或文件路径缺失。"), parent=self)
            return
        
        # Prevent adding duplicate tasks by URL if already managed
        for mgr in self._taskManagers:
            task = mgr.getTask()
            if task and task.getFileInfo() and task.getFileInfo().url == url:
                logger.warning(f"Task with URL {url} already exists. Ignoring.")
                InfoBar.warning(title=self.tr('提示'), content=self.tr("具有相同URL的任务已存在。"), parent=self)
                return

        actualTaskId: str
        if taskSpecificStateForLoad and "taskId" in taskSpecificStateForLoad:
            actualTaskId = taskSpecificStateForLoad["taskId"]
            logger.info(f"Loading existing task with persisted taskId: {actualTaskId}")
        else:
            actualTaskId = str(uuid.uuid4())
            logger.info(f"Creating new task with generated taskId: {actualTaskId}")
        
        managerId = f"dtm-{actualTaskId}" # Ensure managerId is also based on the correct taskId

        if taskType == "DefaultDownloadTask":
            downloadTask = DefaultDownloadTask(
                taskId=actualTaskId, # Use the determined taskId
                url=url,
                headers=headers, 
                filePath=filePath,
                fileName=fileName or "", 
                preBlockNum=preBlockNum,
                autoSpeedUp=cfg.autoSpeedUp.value, 
                fileSize=-1 # DefaultDownloadTask resolves this
            )
        else:
            logger.error(f"Unsupported taskType: {taskType}")
            InfoBar.error(title=self.tr('错误'), content=self.tr("不支持的任务类型: {}").format(taskType), parent=self)
            return

        taskManager = DefaultTaskManager(managerId=managerId)
        taskManager.addTask(downloadTask) 
        self._taskManagers.append(taskManager)

        taskCard = DefaultTaskCard(taskManager=taskManager, parent=self.scrollWidget)
        self._taskCards[actualTaskId] = taskCard # Use actualTaskId as key

        taskCard.requestRemove.connect(self._handleCardRequestRemove) 

        self.expandLayout.addWidget(taskCard)
        taskCard.show()

        self._activeManagerTaskIds.add(taskManager.managerId)
        taskManager.allTasksCompleted.connect(
            partial(self._handleManagerAllTasksCompleted, taskManager.managerId)
        )

        if taskSpecificStateForLoad:
            taskManager.loadTasksState([taskSpecificStateForLoad])
        elif initialStatus in ["pending", "working", "downloading"]:
            taskManager.resumeTask() 
        elif initialStatus == "paused":
            # This case is for brand new tasks added in "paused" state from dialog
            if not taskSpecificStateForLoad: 
                 taskManager.pauseTask() # Ensure it's paused as per initialStatus

        logger.info(f"Managed task {actualTaskId} created with initial status '{initialStatus}'. ManagerID: {managerId}") # Log actualTaskId
        self._checkIfAllManagedTasksTerminated() # Check in case this was the first task and it's already terminal


    @Slot(str) 
    def _handleCardRequestRemove(self, taskId: str):
        logger.info(f"TaskInterface: Received requestRemove for task {taskId}")
        
        managerToRemove = None
        for manager in self._taskManagers:
            task = manager.getTask() 
            if task and task.taskId == taskId:
                managerToRemove = manager
                break
        
        if managerToRemove:
            if managerToRemove.getTask(): 
                 managerToRemove.cancelTask(taskId) 
            
            try:
                # Ensure the same partial is used for disconnection
                managerToRemove.allTasksCompleted.disconnect(
                    partial(self._handleManagerAllTasksCompleted, managerToRemove.managerId)
                )
                logger.debug(f"Disconnected allTasksCompleted for manager {managerToRemove.managerId}")
            except RuntimeError: # pragma: no cover
                logger.warning(f"Could not disconnect allTasksCompleted for manager {managerToRemove.managerId}. Might have already been disconnected.")
            except TypeError: # pragma: no cover
                 logger.warning(f"TypeError disconnecting allTasksCompleted for manager {managerToRemove.managerId}.")


            self._taskManagers.remove(managerToRemove)
            self._activeManagerTaskIds.discard(managerToRemove.managerId)
            logger.info(f"Task manager {managerToRemove.managerId} for task {taskId} removed from TaskInterface.")
            self._checkIfAllManagedTasksTerminated() 
        else:
            logger.warning(f"TaskInterface: Task manager for task {taskId} not found for removal.")

        taskCard = self._taskCards.pop(taskId, None)
        if taskCard:
            self.expandLayout.removeWidget(taskCard)
            taskCard.deleteLater()
            logger.info(f"TaskInterface: Card for task {taskId} removed from UI.")
        else:
            logger.warning(f"TaskInterface: Card for task {taskId} not found for removal.")
    
    @Slot(str)
    def _handleManagerAllTasksCompleted(self, managerId: str):
        logger.info(f"Manager {managerId} reported all its tasks completed.")
        self._activeManagerTaskIds.discard(managerId)
        self._checkIfAllManagedTasksTerminated()

    def _checkIfAllManagedTasksTerminated(self):
        if not self._activeManagerTaskIds:
            logger.info("All managed tasks in TaskInterface have reached a terminal state or been removed.")
            self.allManagedTasksTerminated.emit()
        else:
            logger.info(f"{len(self._activeManagerTaskIds)} active task managers remaining for planned shutdown consideration.")


    def saveAllTaskStates(self) -> List[Dict]:
        allStates = []
        for manager in self._taskManagers:
            taskStateList = manager.saveTasksState() 
            if taskStateList: 
                allStates.extend(taskStateList)
        logger.info(f"Saved states for {len(allStates)} tasks.")
        return allStates

    def allStartTasks(self):
        logger.info("TaskInterface: All Start Tasks requested.")
        for manager in self._taskManagers:
            manager.resumeAllTasks() 

    def allPauseTasks(self):
        logger.info("TaskInterface: All Pause Tasks requested.")
        for manager in self._taskManagers:
            manager.pauseAllTasks()

    def allCancelTasks(self):
        logger.info("TaskInterface: All Cancel Tasks requested.")
        ok, _ = DelDialog.getCompletely(self.window()) 
        if ok:
            for manager in list(self._taskManagers):
                manager.cancelAllTasks()
        
    def _onPlanTaskToggleBtnClicked(self): 
        if not self.planTaskToggleButton.isChecked():  
            try: 
                self.allManagedTasksTerminated.disconnect(QApplication.instance().quit)
                logger.info("Planned shutdown (quit on all tasks finished) disabled.")
            except RuntimeError: # pragma: no cover
                logger.debug("Tried to disconnect quit for planned task, but was not connected.")
        if self.planTaskToggleButton.isChecked():  
            if PlanTaskDialog(self.window()).exec():
                self.planTaskToggleButton.setChecked(True)
                self.allManagedTasksTerminated.connect(QApplication.instance().quit)
                logger.info("Planned shutdown (quit on all tasks finished) enabled.")
                self._checkIfAllManagedTasksTerminated() # Check if all tasks already done
            else:
                self.planTaskToggleButton.setChecked(False)