import httpx
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QSizePolicy, QHBoxLayout, QListWidgetItem
from loguru import logger
from qfluentwidgets import isDarkTheme, SettingCardGroup, TextEdit, ListWidget, BodyLabel, PrimaryPushButton, \
    PushButton, TitleLabel, SubtitleLabel, InfoBar, InfoBarPosition
from qfluentwidgets.components.dialog_box.mask_dialog_base import MaskDialogBase

from app.common.config import VERSION, cfg
from app.common.methods import getProxy
from app.common.signal_bus import signalBus


class GetUpdateThread(QThread):
    gotResponse = Signal(dict)
    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            content = httpx.get(url="https://api.github.com/repos/XiaoYouChR/Ghost-Downloader-3/releases/latest", headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64"},
                                proxy=getProxy(), follow_redirects=True).json()

            tagName = content["tag_name"][1:]

            latestVersion = list(map(int, tagName.split(".")))
            currentVersion = list(map(int, VERSION.split(".")))

            if latestVersion > currentVersion:
                self.gotResponse.emit(content)
            elif latestVersion <= currentVersion:
                self.gotResponse.emit({"INFO" : "当前版本已是最新版本"})

        except Exception as e:
            logger.error(f"获取更新失败：{e}")
            self.gotResponse.emit({"ERROR" : f"获取更新失败：{str(e)}"})


class UpdateDialog(MaskDialogBase):
    def __init__(self, parent, content: dict):
        super().__init__(parent=parent)

        self.content = content
        self.urls = []

        self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 50))
        self.setMaskColor(QColor(0, 0, 0, 76))

        self.VBoxLayout = QVBoxLayout()
        self.VBoxLayout.setContentsMargins(18, 18, 18, 18)

        self.widget.setLayout(self.VBoxLayout)

        self.widget.setMinimumSize(410, 420)
        self.widget.setMaximumSize(520, 420)

        if isDarkTheme():
            # C = ThemeColor.DARK_3.color()
            self.widget.setStyleSheet(".QFrame{border-radius:10px;background-color:rgb(39,39,39)}")
        else:
            self.widget.setStyleSheet(".QFrame{border-radius:10px;background-color:white}")

        self.titleLabel = SubtitleLabel("检测到新版本", self.widget)
        self.VBoxLayout.addWidget(self.titleLabel)

        self.logTextEdit = TextEdit(self)
        self.logTextEdit.setReadOnly(True)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.logTextEdit.setSizePolicy(sizePolicy)

        self.VBoxLayout.addWidget(self.logTextEdit)

        self.updateTimeLabel = BodyLabel(self)
        self.VBoxLayout.addWidget(self.updateTimeLabel)

        self.fileListWidget = ListWidget(self)
        self.VBoxLayout.addWidget(self.fileListWidget)

        self.buttonLayout = QHBoxLayout()

        self.yesButton = PrimaryPushButton(self)
        self.yesButton.setObjectName("yesButton")
        self.yesButton.setText("下载此版本")
        self.noButton = PushButton(self)
        self.noButton.setObjectName("noButton")
        self.noButton.setText("稍后再说")

        self.buttonLayout.addWidget(self.noButton)
        self.buttonLayout.addWidget(self.yesButton)
        self.buttonLayout.setSpacing(18)

        self.VBoxLayout.addLayout(self.buttonLayout)

        self.__analyzeContent()

        # connect signal to slot
        self.noButton.clicked.connect(self.close)
        self.yesButton.clicked.connect(self.__onYesButtonClicked)

    def __analyzeContent(self):
        assets = self.content["assets"]
        for i in assets:
            _ = QListWidgetItem(i["name"])
            _.setData(1, i["browser_download_url"])
            self.fileListWidget.addItem(_)

        body = self.content["body"]

        self.logTextEdit.setMarkdown(body)
        self.updateTimeLabel.setText(f"更新时间：{self.content['published_at']}")
        self.titleLabel.setText(f"检测到新版本：{self.content['tag_name']}")

    def __onYesButtonClicked(self):
        url = self.fileListWidget.currentItem().data(1)
        signalBus.addTaskSignal.emit(url, cfg.downloadFolder.value, cfg.maxBlockNum.value, None, "working", False)
        self.close()

def __showResponse(parent, content: dict):
    if "INFO" in content:
        InfoBar.info(title="当前已是最新版本", content="", position=InfoBarPosition.TOP_RIGHT, parent=parent, duration=5000)
    elif "ERROR" in content:
        InfoBar.error(title="检查更新失败", content=content["ERROR"], position=InfoBarPosition.TOP_RIGHT, parent=parent, duration=5000)
    else:
        UpdateDialog(parent, content).exec()

def checkUpdate(parent):
    thread = GetUpdateThread(parent)
    thread.gotResponse.connect(lambda content: __showResponse(parent, content))
    thread.start()