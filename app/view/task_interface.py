from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QFrame, QHBoxLayout, QSpacerItem, QSizePolicy
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import ScrollArea, TitleLabel, PrimaryPushButton, PushButton, ExpandLayout, InfoBar, InfoBarPosition

from ..common.signal_bus import signalBus
from ..components.del_dialog import DelDialog
from ..components.task_card import TaskCard


class ExpandLayout(ExpandLayout):  # 修复 takeAt 方法
    def __init__(self, parent=None):
        super().__init__(parent=parent)

    def takeAt(self, index):
        if 0 <= index < len(self.__widgets):
            return self.__widgets.pop(index)

        return None

class TaskInterface(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setObjectName("TaskInterface")
        self.cards: list[TaskCard] = []
        self.setupUi()

        # connect signal to slot
        self.allStartButton.clicked.connect(self.allStartTasks)
        self.allPauseButton.clicked.connect(self.allPauseTasks)
        self.allDeleteButton.clicked.connect(self.allCancelTasks)

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
        self.expandLayout = ExpandLayout(self.scrollWidget)
        self.expandLayout.setObjectName("expandLayout")

        # Fixed ExpandLayout 向下偏移的问题 (等待上游修复)
        self.expandLayout.setContentsMargins(11, 11, 11, 0)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 全部开始/暂停 全部删除等其它功能区 TODO 计划任务
        self.toolsBar = QWidget(self)
        self.toolsBar.setObjectName("toolsBar")
        self.toolsBar.resize(447, 60)

        self.horizontalLayout = QHBoxLayout(self.toolsBar)

        self.toolsBar.setLayout(self.horizontalLayout)

        self.allStartButton = PrimaryPushButton(self.toolsBar)
        self.allStartButton.setObjectName(u"allStartButton")
        self.allStartButton.setIcon(FIF.PLAY)
        self.horizontalLayout.addWidget(self.allStartButton)

        self.allPauseButton = PushButton(self.toolsBar)
        self.allPauseButton.setObjectName(u"allPauseButton")
        self.allPauseButton.setIcon(FIF.PAUSE)
        self.horizontalLayout.addWidget(self.allPauseButton)

        self.allDeleteButton = PushButton(self.toolsBar)
        self.allDeleteButton.setObjectName(u"allDeleteButton")
        self.allDeleteButton.setIcon(FIF.DELETE)
        self.horizontalLayout.addWidget(self.allDeleteButton)

        self.horizontalSpacer = QSpacerItem(447, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.allStartButton.setText("全部开始")
        self.allPauseButton.setText("全部暂停")
        self.allDeleteButton.setText("全部删除")

        self.expandLayout.addWidget(self.toolsBar)

        # 新增Label防止expandLayout被内存回收
        self.noTaskLabel = TitleLabel("暂无任务", self.scrollWidget)
        self.noTaskLabel.setObjectName("noTaskLabel")
        self.noTaskLabel.setAlignment(Qt.AlignCenter)
        self.expandLayout.addWidget(self.noTaskLabel)
        self.scrollWidget.setMinimumWidth(816)

    def addDownloadTask(self, url: str, path: str, block_num: int, name: str = None, status:str = "working",
                        autoCreated: bool = False):
        # # 任务唯一标识符
        # number = len(self.cards)
        # _ = TaskCard(url, path, block_num, number, pixmap, name, self.scrollWidget, autoCreated)
        # _.removeTaskSignal.connect(self.removeTask)

        # 逐个对照现有任务url, 若重复则不添加
        for card in self.cards:
            if card.status == "canceled":
                continue

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


        _ = TaskCard(url, path, block_num, name, status, self.scrollWidget, autoCreated)

        _.taskStatusChanged.connect(self.__sortTask)

        self.cards.append(_)

        self.expandLayout.addWidget(_)

        _.show()

        self.__sortTask()

        # 如果 self.noTaskLabel 存在，则隐藏
        if self.noTaskLabel.parent():
            self.expandLayout.removeWidget(self.noTaskLabel)
            self.noTaskLabel.hide()

    def __sortTask(self):  # 将任务按照状态 working waiting paused canceled 排序
        statusOrder = {"working": 0, "waiting": 1, "paused": 2, "finished": 3, "canceled": 4}

        items = []

        for i in range(len(self.cards)):
            _ = self.expandLayout.takeAt(2)  # 跳过 toolsBar 和 noTaskLabel

            items.append(_)

        items.sort(key=lambda item: statusOrder[item.status])

        for i in items:
            self.expandLayout.addWidget(i)

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

            for card in self.cards:
                if card.status == "canceled":
                    continue

                card.cancelTask(True, completely)

        dialog.deleteLater()
