import sys
import re
from PySide6.QtWidgets import QVBoxLayout, QWidget, QHBoxLayout, QFrame
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import QByteArray, Qt, QObject, Signal
from qfluentwidgets import SmoothScrollArea, ExpandLayout
from ..common.download_engine import DownloadTask
from ..common.signal_bus import signalBus
from ..components.system_info_card import SystemInfoCard
import json
import base64

from ..components.task_card import TaskCard


# 定义一个自定义的类，继承自QObject，用于将sys.stdout重定向到该类
class Supervise(QObject):
    # 定义一个新的信号newText，用于将输出的内容发送给主线程
    newText = Signal(str)

    # 重写write()方法，将输出的内容通过newText信号发送出去
    def write(self, text):
        self.newText.emit(str(text))


class TaskInterface(SmoothScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setObjectName("TaskInterface")
        self.cards = []
        self.setupUi()

        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)

        # 连接信号到槽
        signalBus.addTaskSignal.connect(self.addDownloadTask)

        # Apply QSS
        self.setStyleSheet("""QScrollArea, .QWidget {
                                border: none;
                                background-color: transparent;
                            }""")

        # 重定向打印
    #     sys.stdout = Supervise()
    #     sys.stdout.newText.connect(self.processText)
    #
    # # 处理文本
    # def processText(self,text:str):
    #     _ = text.split("|")
    #     if len(_) == 2: # finished
    #         # 使用 re.findall 函数来匹配字符串中的 [] 里面的内容，并返回一个列表
    #         taskNum = int(re.findall("\[(.*?)\]", _[0])[0])
    #         self.cards[taskNum].changeInfo(100,"","","已完成！")
    #     elif len(_) == 4:
    #         t = re.findall("\[(.*?)\]", _[0])
    #         taskNum = int(t[0])
    #         value = int(t[1])*100
    #         process = t[2]
    #         speed = t[3] + "/s"
    #         self.cards[taskNum].changeInfo(value,process,"",speed)


    def setupUi(self):
        self.setMinimumWidth(816)
        self.setFrameShape(QFrame.NoFrame)
        self.scrollWidget = QWidget()
        self.scrollWidget.setMinimumWidth(816)
        self.expandLayout = ExpandLayout(self.scrollWidget)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def addDownloadTask(self, url: str, path: str, block_num: int, name: str, pixmap: QPixmap):
        number = len(self.cards)
        _ = TaskCard(url, path, block_num, number, name, pixmap, self.scrollWidget)
        self.cards.append(_)
        self.expandLayout.addWidget(_)
