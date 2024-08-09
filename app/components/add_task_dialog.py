import os
import re
from typing import Union
from pathlib import Path

from loguru import logger
from PySide6.QtCore import Signal, QDir, Qt, QTimer, QThread
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import QVBoxLayout, QFileDialog, QHBoxLayout, QSizePolicy, QDialog
from qfluentwidgets import PushSettingCard, SettingCardGroup, RangeSettingCard, RangeConfigItem, RangeValidator, \
    PushButton, PrimaryPushButton, TextEdit, \
    MessageBox, isDarkTheme, InfoBar, InfoBarPosition
from qfluentwidgets.common.icon import FluentIcon as FIF
from qfluentwidgets.components.dialog_box.mask_dialog_base import MaskDialogBase

from ..common.config import cfg
from ..common.signal_bus import signalBus
from app.common.methods import getWindowsProxy
from app.common.utils import UrlUtils

urlRe = UrlUtils.urlRe


class GetUrlInformationThread(QThread):
    information = Signal(dict)
    def __init__(self, url: str, headers: Union[dict, None] = None):
        super().__init__()
        self.url = url
        self.headers = headers

    def run(self) -> None:
        result = {}
        # 以/filename.xxx 结尾的文件，默认为真实链接
        if not re.search(r'/(.+)\.\w+$', self.url):
            # 获取真实URL
            logger.debug(f"获取: {self.url} 的真实URL")
            self.url = UrlUtils.getRealUrl(self.url, getWindowsProxy())
        result["resposeTime"] = UrlUtils.responseTime(self.url)
        self.information.emit(result)


class SystemPasteboardContent(QDialog):
    """获取剪贴板内容"""
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        # 获取剪贴板内容，并 检查是否为链接
        _content = urlRe.search(self.getSystemPasteboardContent())
        if _content:
            self.content = _content.group()
            self.inspectUrl()
        else:
            logger.warning("剪贴板内容链接不合法！")
            self.content = ""

    def inspectUrl(self) -> None:
        """检查url状态"""
        self.informationThread = GetUrlInformationThread(self.content)
        self.informationThread.information.connect(lambda r: self.information(r))
        self.informationThread.start()

    def information(self, info: dict) -> None:
        """the information thread callback function."""
        responseTime = info.get("resposeTime")
        content = ""
        if responseTime:
            logger.info(f"响应时间: {responseTime}ms")
            content += f"响应时间: {responseTime}ms\n"
        InfoBar.success(
            title='成功获取链接信息',
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self.parent()
        )

    def getSystemPasteboardContent(self) -> str:
        """
        获取系统粘贴板内容
        :return: str
        """
        clipboard = QGuiApplication.clipboard()  # 获取剪贴板对象
        return clipboard.text()  # 获取剪贴板中的文本


class AddTaskOptionDialog(MaskDialogBase):
    startSignal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 50))
        self.setMaskColor(QColor(0, 0, 0, 76))

        self.VBoxLayout = QVBoxLayout(self.widget)
        self.VBoxLayout.setContentsMargins(18, 18, 18, 18)

        self.widget.setLayout(self.VBoxLayout)

        self.widget.setMinimumSize(510, 420)
        self.widget.setMaximumSize(680, 430)
        if isDarkTheme():
            # C = ThemeColor.DARK_3.color()
            self.widget.setStyleSheet(".QFrame{border-radius:10px;background-color:rgb(39,39,39)}")
        else:
            self.widget.setStyleSheet(".QFrame{border-radius:10px;background-color:white}")

        # 下载链接组
        self.linkGroup = SettingCardGroup(
            "新建任务", self.widget)

        self.linkTextEdit = TextEdit(self.linkGroup)
        self.linkTextEdit.setPlaceholderText("添加多个下载链接时, 请确保每行只有一个链接.")
        self.linkTextEdit.setMinimumHeight(100)
        sizePolicy = QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        self.linkTextEdit.setSizePolicy(sizePolicy)

        # self.taskTableView = TableView(self.linkGroup)
        # self.taskTableView.setObjectName("taskTableView")
        # self.taskTableView.setMinimumHeight(200)
        # self.taskTableView.setSizePolicy(sizePolicy)
        #
        # # 初始化
        # self.taskTableView.setBorderVisible(True)
        # self.taskTableView.setBorderRadius(8)
        #
        # self.taskTableView.setWordWrap(False)
        # self.taskTableView.setRowCount(0)
        # self.taskTableView.setColumnCount(3)
        #
        # self.taskTableView.verticalHeader().hide()
        # self.taskTableView.setHorizontalHeaderLabels(['文件名', '类型', '大小'])
        #
        # self.taskList = []

        self.linkGroup.addSettingCard(self.linkTextEdit)
        # self.linkGroup.addSettingCard(self.taskTableView)

        # 下载设置组
        self.settingGroup = SettingCardGroup(
            "下载设置", self.widget)

        # Choose Folder Card
        self.downloadFolderCard = PushSettingCard(
            "选择下载目录",
            FIF.DOWNLOAD,
            "下载目录",
            cfg.downloadFolder.value,
            self.settingGroup
        )

        # Choose Threading Card
        self.blockNumCard = RangeSettingCard(
            cfg.maxBlockNum,
            FIF.CLOUD,
            "下载线程数",
            '下载线程越多，下载越快，同时也越吃性能',
            self.settingGroup
        )

        self.buttonLayout = QHBoxLayout()

        self.yesButton = PrimaryPushButton(self)
        self.yesButton.setObjectName("yesButton")
        self.yesButton.setDisabled(True)
        self.yesButton.setText("开始下载")
        self.noButton = PushButton(self)
        self.noButton.setObjectName("noButton")
        self.noButton.setText("取消下载")

        self.buttonLayout.addWidget(self.noButton)
        self.buttonLayout.addWidget(self.yesButton)
        self.buttonLayout.setSpacing(18)

        self.settingGroup.addSettingCards([self.downloadFolderCard, self.blockNumCard])

        self.VBoxLayout.addWidget(self.linkGroup)
        self.VBoxLayout.addWidget(self.settingGroup)
        self.VBoxLayout.addLayout(self.buttonLayout)

        self.__connectSignalToSlot()
        self.__getSystemPasteboardContent()

    def __connectSignalToSlot(self):
        self.downloadFolderCard.clicked.connect(
            self.__onDownloadFolderCardClicked)
        self.noButton.clicked.connect(self.close)

        self.yesButton.clicked.connect(self.startTask)

        self.linkTextEdit.textChanged.connect(self.__onLinkTextChanged)

    def startTask(self):
        path = Path(self.downloadFolderCard.contentLabel.text())

        # 检测路径是否有权限写入
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                MessageBox("错误", str(e), self)
        else:
            if not os.access(path, os.W_OK):
                MessageBox("错误", "似乎是没有权限向此目录写入文件", self)

        text = self.linkTextEdit.toPlainText().split("\n")
        for url in text:
            _ = urlRe.search(url)
            if _:
                signalBus.addTaskSignal.emit(url,
                                             str(path), self.blockNumCard.configItem.value,
                                             "", "working", None, False)

        self.close()

    def __onDownloadFolderCardClicked(self):
        """ download folder card clicked slot """
        folder = QFileDialog.getExistingDirectory(
            self, "选择文件夹", "./")
        if not folder or self.downloadFolderCard.contentLabel.text() == folder:
            return

        self.downloadFolderCard.setContent(folder)


    def __onLinkTextChanged(self):
        if hasattr(self, '_timer'):
            self._timer.stop()

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.__processTextChange)
        self._timer.start(1000)  # 1秒后处理

    def __processTextChange(self):
        """ link text changed slot """
        text: list = self.linkTextEdit.toPlainText().split("\n")

        for index, url in enumerate(text, start=1):

            _ = urlRe.search(url)

            if _:
                self.yesButton.setEnabled(True)
            else:
                InfoBar.warning(
                    title='警告',
                    content=f"第{index}个链接可能无效!",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    # position='Custom',   # NOTE: use custom info bar manager
                    duration=1000,
                    parent=self.parent()
                )

    def __getSystemPasteboardContent(self) -> str:
        spc = SystemPasteboardContent(self.parent())
        if spc.content:
            self.linkTextEdit.setText(spc.content)
            self.yesButton.setDisabled(False)
