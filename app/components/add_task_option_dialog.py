import os
import re
from pathlib import Path

from PySide6.QtCore import Signal, QDir
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QFileDialog, QHBoxLayout, QSizePolicy
from qfluentwidgets import PushSettingCard, SettingCardGroup, RangeSettingCard, RangeConfigItem, RangeValidator, \
    PushButton, PrimaryPushButton, ComboBoxSettingCard, OptionsValidator, OptionsConfigItem, TextEdit, \
    MessageBox, isDarkTheme
from qfluentwidgets.common.icon import FluentIcon as FIF
from qfluentwidgets.components.dialog_box.mask_dialog_base import MaskDialogBase

from ..common.signal_bus import signalBus

urlRe = re.compile(r"^" +
                   "((?:https?|ftp)://)" +
                   "(?:\\S+(?::\\S*)?@)?" +
                   "(?:" +
                   "(?:[1-9]\\d?|1\\d\\d|2[01]\\d|22[0-3])" +
                   "(?:\\.(?:1?\\d{1,2}|2[0-4]\\d|25[0-5])){2}" +
                   "(\\.(?:[1-9]\\d?|1\\d\\d|2[0-4]\\d|25[0-4]))" +
                   "|" +
                   "((?:[a-z\\u00a1-\\uffff0-9]-*)*[a-z\\u00a1-\\uffff0-9]+)" +
                   '(?:\\.(?:[a-z\\u00a1-\\uffff0-9]-*)*[a-z\\u00a1-\\uffff0-9]+)*' +
                   "(\\.([a-z\\u00a1-\\uffff]{2,}))" +
                   ")" +
                   "(?::\\d{2,5})?" +
                   "(?:/\\S*)?" +
                   "$", re.IGNORECASE)


class AddTaskOptionDialog(MaskDialogBase):
    startSignal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 50))
        self.setMaskColor(QColor(0, 0, 0, 76))

        self.VBoxLayout = QVBoxLayout(self.widget)
        self.VBoxLayout.setContentsMargins(18, 18, 18, 18)

        self.widget.setLayout(self.VBoxLayout)

        self.widget.setMinimumSize(510, 400)
        self.widget.setMaximumSize(680, 410)
        if isDarkTheme():
            # C = ThemeColor.DARK_3.color()
            self.widget.setStyleSheet(".QFrame{border-radius:10px;background-color:rgb(39,39,39)}")
        else:
            self.widget.setStyleSheet(".QFrame{border-radius:10px;background-color:white}")

        # 下载链接组
        self.linkGroup = SettingCardGroup(
            "新建任务", self.widget)

        self.linkTextEdit = TextEdit(self.linkGroup)
        self.linkTextEdit.setPlaceholderText("请在此键入下载链接")
        self.linkTextEdit.setMinimumHeight(100)
        sizePolicy = QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        self.linkTextEdit.setSizePolicy(sizePolicy)

        self.linkGroup.addSettingCard(self.linkTextEdit)

        # 下载设置组
        self.settingGroup = SettingCardGroup(
            "下载设置", self.widget)

        # Choose Folder Card
        self.downloadFolderCard = PushSettingCard(
            "选择下载目录",
            FIF.DOWNLOAD,
            "下载目录",
            QDir.currentPath(),
            self.settingGroup
        )

        # Choose Threading Card
        self.blockNumCard = RangeSettingCard(
            RangeConfigItem("Material", "AcrylicBlurRadius", 24, RangeValidator(1, 128)),
            FIF.CHAT,
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

        url = self.linkTextEdit.toPlainText()

        signalBus.addTaskSignal.emit(url,
                                     str(path), self.blockNumCard.configItem.value,
                                     "", None, False)
        self.close()

    def __onDownloadFolderCardClicked(self):
        """ download folder card clicked slot """
        folder = QFileDialog.getExistingDirectory(
            self, "选择文件夹", "./")
        if not folder or self.downloadFolderCard.contentLabel.text() == folder:
            return

        self.downloadFolderCard.setContent(folder)

    def __onLinkTextChanged(self):
        """ link text changed slot """
        text: str = self.linkTextEdit.toPlainText()

        _ = urlRe.search(text)

        if _:
            self.yesButton.setEnabled(True)
        else:
            self.yesButton.setDisabled(True)
