import base64
import json

import requests
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout
from loguru import logger
from qfluentwidgets import ScrollArea, TitleLabel

from ..common.tool_hub import getWindowsProxy
from ..components.system_info_card import SystemInfoCard


class getInfoThread(QThread):
    gotInfo = Signal(list)
    def __init__(self, parent=None):
        super().__init__(parent=parent)

    def run(self):
        # with open("./Content.json", "r", encoding="utf-8") as f:
        #     self.json = json.loads(f.read())["OS"]
        #     f.close()

        self.gotInfo.emit(json.loads(requests.get(
            url="https://seelevollerei-my.sharepoint.com/personal/jackyao_xn--7et36u_cn/_layouts/52/download.aspx?share=Ecm5kLYVJedKlw60gcDkxPEB1PlS5Y-P-ttDSit_V8KuLw",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64"},
            proxies=getWindowsProxy()).content)["OS"])

class HomeInterface(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setObjectName("HomeInterface")
        self.cards = []
        self.setupUi()

        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)

        # Apply QSS
        self.setStyleSheet("""QScrollArea, .QWidget {
                                border: none;
                                background-color: transparent;
                            }""")

    def setupUi(self):
        self.setMinimumWidth(816)
        self.setFrameShape(QFrame.NoFrame)
        self.scrollWidget = QWidget()
        self.scrollWidget.setMinimumWidth(816)
        self.expandLayout = QVBoxLayout(self.scrollWidget)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.loadingLabel = TitleLabel("正在加载", self.scrollWidget)
        self.loadingLabel.setObjectName("noTaskLabel")
        self.loadingLabel.setAlignment(Qt.AlignCenter)
        self.expandLayout.addWidget(self.loadingLabel)
        self.scrollWidget.setMinimumWidth(816)

        self.GetInfoThread = getInfoThread(self)
        self.GetInfoThread.gotInfo.connect(self.loadInfoCards)
        self.GetInfoThread.start()

    def loadInfoCards(self, json:list):

        self.json = json

        for i in self.json:
            # Create Card
            _ = SystemInfoCard(self.scrollWidget)
            self.cards.append(SystemInfoCard)
            _.List = i["List"]

            _.TitleLabel.setText(i["Name"])

            logger.debug(f'Loading System Card: {i["Name"]}')

            # 将字符串转换为字节数据
            data = base64.b64decode(i["Icon"])

            # 从字节数据中创建QPixmap对象
            _.pixmap = QPixmap()
            _.pixmap.loadFromData(data)

            _.LogoPixmapLabel.setPixmap(_.pixmap)
            _.LogoPixmapLabel.setFixedSize(101, 101)

            _.BodyLabel.setText(i["Intro"].replace(r"\n", "\n"))

            _.Video = i["Video"]

            _.connect_signal_to_slot()

            self.expandLayout.addWidget(_)

            _.show()

        self.expandLayout.removeWidget(self.loadingLabel)
        self.loadingLabel.hide()
        self.loadingLabel.setParent(None)