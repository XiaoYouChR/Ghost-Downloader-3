from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QFrame, QHBoxLayout, QVBoxLayout, QSpacerItem, QSizePolicy
from qfluentwidgets import FluentIcon as FIF, SmoothScrollArea, TitleLabel, PrimaryPushButton, PushButton, InfoBar, \
    InfoBarPosition, ToggleButton

from ..common.config import Headers
from ..common.signal_bus import signalBus
from ..components.del_dialog import DelDialog
from ..components.plan_task_dialog import PlanTaskDialog
from ..components.task_card import TaskCard


class TaskInterface(SmoothScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setObjectName("TaskInterface")
        self.cards: list[TaskCard] = []
        self.setupUi()

        # connect signal to slot
        self.allStartButton.clicked.connect(self.allStartTasks)
        self.allPauseButton.clicked.connect(self.allPauseTasks)
        self.allDeleteButton.clicked.connect(self.allCancelTasks)
        self.planTaskToggleButton.clicked.connect(self.__onPlanTaskToggleBtnClicked)

        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)

        # 在这里创建下载任务
        signalBus.addTaskSignal.connect(self.addDownloadTask)

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

        self.noTaskLabel = TitleLabel("暂无任务", self.scrollWidget)
        self.noTaskLabel.setObjectName("noTaskLabel")
        self.noTaskLabel.setAlignment(Qt.AlignCenter)
        self.expandLayout.addWidget(self.noTaskLabel)
        self.scrollWidget.setMinimumWidth(816)

    def addDownloadTask(self, url: str, path: str, block_num: int, name: str = None, status:str = "working",
                        headers: dict = Headers, autoCreated: bool = False):
        # # 任务唯一标识符
        # number = len(self.cards)
        # _ = TaskCard(url, path, block_num, number, pixmap, name, self.scrollWidget, autoCreated)
        # _.removeTaskSignal.connect(self.removeTask)

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

            if card.fileName == name and card.filePath == path:
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


        _ = TaskCard(url, path, block_num, headers, name, status, self.scrollWidget, autoCreated)

        _.taskStatusChanged.connect(self.__sortTask)

        self.cards.append(_)

        self.expandLayout.addWidget(_)

        _.show()

        # 如果 self.noTaskLabel 可见，则隐藏
        self.expandLayout.removeWidget(self.noTaskLabel)
        self.noTaskLabel.hide()

        self.__sortTask()


    def __sortTask(self):  # 将任务按照状态 working waiting paused finished 排序
        statusOrder = {"working": 0, "waiting": 1, "paused": 2, "finished": 3}

        items = []

        for i in range(len(self.cards)):
            _ = self.expandLayout.takeAt(1)  # 跳过 toolsBar
            items.append(_)

        items.sort(key=lambda item: statusOrder[item.widget().status])

        for i in items:
            self.expandLayout.addItem(i)

        if not items:
            self.expandLayout.addWidget(self.noTaskLabel)
            self.noTaskLabel.show()
            return

        if all(card.status == "finished" for card in self.cards):  # 全部任务完成
            signalBus.allTaskFinished.emit()

    def allStartTasks(self):
        for card in self.cards:
            if card.status == "working":
                continue
            if card.status == "paused":
                card.pauseTask()

    def allPauseTasks(self):
        for card in self.cards:
            if card.status == "paused":
                continue
            if card.status == "working":
                card.pauseTask()

    def allCancelTasks(self):
        dialog = DelDialog(self.window())
        if dialog.exec():
            completely = dialog.checkBox.isChecked()

            cards = self.cards.copy()  # 防止列表变化导致迭代器异常

            for card in cards:
                card.cancelTask(True, completely)

            del cards

        dialog.deleteLater()

    def __onPlanTaskToggleBtnClicked(self):
        if not self.planTaskToggleButton.isChecked():  # 取消计划任务
            signalBus.allTaskFinished.disconnect()
        if self.planTaskToggleButton.isChecked():  # 设定计划任务
            if PlanTaskDialog(self.window()).exec():
                self.planTaskToggleButton.setChecked(True)
            else:
                self.planTaskToggleButton.setChecked(False)