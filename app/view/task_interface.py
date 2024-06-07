from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QFrame
from qfluentwidgets import SmoothScrollArea, ExpandLayout, TitleLabel

from ..common.signal_bus import signalBus
from ..components.task_card import TaskCard


class TaskInterface(SmoothScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setObjectName("TaskInterface")
        self.cards: list[TaskCard] = []
        self.setupUi()

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
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 新增Label防止expandLayout被内存回收
        self.noTaskLabel = TitleLabel("暂无任务", self.scrollWidget)
        self.noTaskLabel.setObjectName("noTaskLabel")
        self.noTaskLabel.setAlignment(Qt.AlignCenter)
        self.expandLayout.addWidget(self.noTaskLabel)
        self.scrollWidget.setMinimumWidth(816)

    def addDownloadTask(self, url: str, path: str, block_num: int, name: str, pixmap: QPixmap,
                        autoCreated: bool = False):
        _ = TaskCard(url, path, block_num, pixmap, name, self.scrollWidget, autoCreated)

        self.cards.append(_)

        self.expandLayout.addWidget(_)

        _.show()

        # 如果 self.noTaskLabel 存在，则移除
        if self.noTaskLabel.parent():
            self.expandLayout.removeWidget(self.noTaskLabel)
            self.noTaskLabel.hide()
            self.noTaskLabel.setParent(None)
