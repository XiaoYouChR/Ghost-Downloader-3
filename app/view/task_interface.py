from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QWidget, QFrame, QHBoxLayout, QVBoxLayout, QSpacerItem, QSizePolicy
from loguru import logger
from qfluentwidgets import FluentIcon as FIF, SmoothScrollArea, PrimaryPushButton, PushButton, InfoBar, \
    InfoBarPosition, ToggleButton

from ..common.config import cfg
from ..common.signal_bus import signalBus
from ..components.custom_dialogs import DelDialog, PlanTaskDialog
from ..components.task_card import TaskCard


class TaskInterface(SmoothScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setObjectName("TaskInterface")
        self.cards: list[TaskCard] = []
        self.setupUi()
        
        self.__blockSortTask = False
        self.__statusOrder = {"working": 0, "waiting": 1, "paused": 2, "finished": 3}
        
        # connect signal to slot
        self.allStartButton.clicked.connect(self.allStartTasks)
        self.allPauseButton.clicked.connect(self.allPauseTasks)
        self.allDeleteButton.clicked.connect(self.allCancelTasks)
        self.planTaskToggleButton.clicked.connect(self.__onPlanTaskToggleBtnClicked)

        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)

        # 连接新建下载任务信号
        signalBus.addTaskSignal.connect(self.__addDownloadTask)

        # Apply QSS
        self.setStyleSheet("""QScrollArea, .QWidget {
                                border: none;
                                background-color: transparent;
                            }""")

        # # For test
        # signalBus.addTaskSignal.emit("https://jfile-b.jijidown.com:4433/PC/WPF/JiJiDown_setup.exe",
        #                              str(Path.cwd()), 8,
        #                              "", QPixmap())

    def setupUi(self):
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

        # 全部开始/暂停 全部删除等其它功能区 TODO 计划任务
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

        self.allStartButton.setText("全部开始")
        self.allPauseButton.setText("全部暂停")
        self.allDeleteButton.setText("全部删除")
        self.planTaskToggleButton.setText("计划任务")

        self.expandLayout.addLayout(self.horizontalLayout)

        self.scrollWidget.setMinimumWidth(816)

    def __addDownloadTask(self, url: str, fileName: str, filePath: str,
                          headers: dict, status:str, preBlockNum: int, notCreateHistoryFile: bool, fileSize: str="-1"):
        # 逐个对照现有任务url, 若重复则不添加
        for card in self.cards:
            if card.url == url:
                InfoBar.error(
                    title='错误',
                    content="已创建相同下载链接的任务!",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    # position='Custom',   # NOTE: use custom info bar manager
                    duration=3000,
                    parent=self.parent()
                )
                return

            try:
                if card.fileName == fileName and card.filePath == filePath:
                    InfoBar.error(
                        title='错误',
                        content="已创建相同文件名和路径的任务!",
                        orient=Qt.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        # position='Custom',   # NOTE: use custom info bar manager
                        duration=3000,
                        parent=self.parent()
                    )
                    return
            except Exception as e:
                logger.error(f"Error while checking duplicate task: {e}")

        runningTasks = [card for card in self.cards if card.status == "working"]

        if len(runningTasks) >= cfg.maxTaskNum.value and status == "working":
            status = "waiting"

        _ = TaskCard(url, fileName, filePath, preBlockNum, headers, status, notCreateHistoryFile, int(fileSize), self.scrollWidget)

        _.taskStatusChanged.connect(self.__handleTaskStatusChange)

        self.cards.append(_)

        self.expandLayout.addWidget(_)

        _.show()

        # 仅排序, 不考虑任务队列
        items = []

        for i in range(len(self.cards)):
            _ = self.expandLayout.takeAt(1)  # 跳过 toolsBar
            if _:
                items.append(_)

        items.sort(key=lambda item: self.__statusOrder[item.widget().status])

        for i in items:
            self.expandLayout.addItem(i)

    @Slot()
    def __handleTaskStatusChange(self):
        """将任务按照 self.__statusOrder 排序;
           进行任务队列处理;
           并处理计划任务事件."""

        if self.__blockSortTask:
            return

        # 如果 sender 的 status 为 working, 则把 sender 移到第一个
        try:
            # print(self.sender().fileName)
            if self.sender().status == "working":
                self.expandLayout.takeAt(self.expandLayout.indexOf(self.sender()))
                self.expandLayout.insertWidget(1, self.sender())  # 0 是 toolsBar
        except:
            return # sender 不是 TaskCard

        items = []

        for i in range(len(self.cards)):
            _ = self.expandLayout.takeAt(1)  # 跳过 toolsBar
            if _:
                items.append(_)

        runningTasks = 0

        for i in items:
            _ = i.widget()
            if _.status == "working":
                runningTasks += 1
                if runningTasks > cfg.maxTaskNum.value:
                    _.pauseTask()
                    _.status = "waiting"
                    _.infoLabel.setText("排队中...")
                    runningTasks -= 1
                    break

        if runningTasks < cfg.maxTaskNum.value:
            for i in items:
                _ = i.widget()
                if _.status == "waiting":
                    _.pauseTask()
                    break

        items.sort(key=lambda item: self.__statusOrder[item.widget().status])

        for i in items:
            self.expandLayout.addItem(i)

        if all(card.status == "finished" for card in self.cards):  # 全部任务完成
            signalBus.allTaskFinished.emit()

    def allStartTasks(self):
        runningTasks = 0

        self.__blockSortTask = True

        for card in self.cards:
            if card.status == "working":
                runningTasks += 1
                continue
            if card.status == "paused":
                if runningTasks < cfg.maxTaskNum.value:
                    card.pauseTask()
                    runningTasks += 1
                else:
                    card.status = "waiting"
                    card.infoLabel.setText("排队中...")

        self.__blockSortTask = False

    def allPauseTasks(self):
        self.__blockSortTask = True

        for card in self.cards:
            if card.status == "paused":
                continue
            if card.status == "waiting":
                card.status = "paused"
                card.infoLabel.setText("任务已经暂停")
            if card.status == "working":
                card.pauseTask()

        self.__blockSortTask = False

    def allCancelTasks(self):
        self.__blockSortTask = True

        ok, completely = DelDialog.getCompletely(self.window())
        if ok:
            cards = self.cards.copy()  # 防止列表变化导致迭代器异常

            for card in cards:
                card.cancelTask(True, completely)

            del cards

        self.__blockSortTask = False

    def __onPlanTaskToggleBtnClicked(self):
        if not self.planTaskToggleButton.isChecked():  # 取消计划任务
            signalBus.allTaskFinished.disconnect()
        if self.planTaskToggleButton.isChecked():  # 设定计划任务
            if PlanTaskDialog(self.window()).exec():
                self.planTaskToggleButton.setChecked(True)
            else:
                self.planTaskToggleButton.setChecked(False)