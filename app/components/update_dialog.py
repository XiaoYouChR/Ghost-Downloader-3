import httpx
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidgetItem
from loguru import logger
from qfluentwidgets import InfoBar, InfoBarPosition, FluentStyleSheet
from qfluentwidgets.components.dialog_box.mask_dialog_base import MaskDialogBase

from app.common.config import VERSION, cfg
from app.common.methods import getProxy, getLocalTimeFromGithubApiTime, getReadableSize
from app.common.signal_bus import signalBus
from app.components.Ui_UpdateDialog import Ui_UpdateDialog


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
            self.gotResponse.emit({"ERROR" : f"获取更新失败：{repr(e)}"})


class UpdateDialog(MaskDialogBase, Ui_UpdateDialog):
    def __init__(self, parent, content: dict):
        super().__init__(parent=parent)

        FluentStyleSheet.DIALOG.apply(self.widget)

        self.content = content
        self.tabelViewInfos = []
        self.urls: list[str] = []

        self._hBoxLayout.setContentsMargins(120, 80, 120, 80)

        self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 50))
        self.setMaskColor(QColor(0, 0, 0, 76))
        self.setClosableOnMaskClicked(True)

        self.setupUi(self.widget)

        self.widget.setLayout(self.verticalLayout)

        self.widget.setMinimumSize(520, 450)
        self.widget.setMaximumSize(920, 820)

        self.__analyzeContent()

        # connect signal to slot
        self.noButton.clicked.connect(self.close)
        self.yesButton.clicked.connect(self.__onYesButtonClicked)

    def __analyzeContent(self):

        assets = self.content["assets"]
        for i in assets:
            self.tabelViewInfos.append([i["name"], getReadableSize(i["size"]), str(i["download_count"])])
            self.urls.append(i["browser_download_url"])

        self.tableView.setRowCount(len(assets))

        # 添加数据
        for i, tabelViewInfo in enumerate(self.tabelViewInfos):
            for j in range(3):
                self.tableView.setItem(i, j, QTableWidgetItem(tabelViewInfo[j]))

        self.tableView.setHorizontalHeaderLabels(['文件名', '文件大小', '下载次数'])

        self.logTextEdit.setMarkdown(self.content["body"])
        self.updatedDateLabel.setText(f"Updated Time：{getLocalTimeFromGithubApiTime(self.content['published_at'])}")
        self.versionLabel.setText(f"Version: {self.content['tag_name']} " + ("Pre-Release" if self.content["prerelease"] else "Release"))

    def __onYesButtonClicked(self):
        url = self.urls[self.tableView.currentRow()]
        signalBus.addTaskSignal.emit(url, cfg.downloadFolder.value, cfg.maxBlockNum.value, None, "working", False)
        self.close()

def __showResponse(parent, content: dict):
    if "INFO" in content:
        InfoBar.info(title="当前已是最新版本", content="", position=InfoBarPosition.TOP_RIGHT, parent=parent, duration=5000)
    elif "ERROR" in content:
        InfoBar.error(title="检查更新失败", content=content["ERROR"], position=InfoBarPosition.TOP_RIGHT, parent=parent, duration=5000)
    else:
        UpdateDialog(parent, content).show()

def checkUpdate(parent):
    thread = GetUpdateThread(parent)
    thread.gotResponse.connect(lambda content: __showResponse(parent, content))
    thread.start()