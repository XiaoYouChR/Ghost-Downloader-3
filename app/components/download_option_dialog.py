import os
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


class DownloadOptionDialog(MaskDialogBase):
    startSignal = Signal()

    def __init__(self, parent=None, list=None, dict=None):
        super().__init__(parent=parent)

        self.dict = dict
        self.list = list
        self.versions = []

        self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 50))
        self.setMaskColor(QColor(0, 0, 0, 76))

        self.VBoxLayout = QVBoxLayout(self.widget)
        self.VBoxLayout.setContentsMargins(18, 18, 18, 18)

        self.widget.setLayout(self.VBoxLayout)

        self.widget.setMinimumSize(510, 510)
        self.widget.setMaximumSize(680, 520)
        if isDarkTheme():
            # C = ThemeColor.DARK_3.color()
            self.widget.setStyleSheet(".QFrame{border-radius:10px;background-color:rgb(39,39,39)}")
        else:
            self.widget.setStyleSheet(".QFrame{border-radius:10px;background-color:white}")

        # 版本组
        self.versionGroup = SettingCardGroup(
            "选择版本", self.widget)

        for i in self.list:
            self.versions.append(i["Version"])

        versionItem = OptionsConfigItem(
            "Material", "Version", self.versions[0], OptionsValidator(self.versions))

        self.versionCard = ComboBoxSettingCard(
            versionItem,
            FIF.VIEW,
            "选择版本",
            "选择你想下载的版本",
            texts=self.versions,
            parent=self.versionGroup
        )

        self.versionGroup.addSettingCard(self.versionCard)

        self.logGroup = SettingCardGroup(
            "更新日志", self.widget)

        self.logTextEdit = TextEdit(self.versionGroup)
        self.logTextEdit.setReadOnly(True)
        self.logTextEdit.setMinimumHeight(140)
        self.logTextEdit.setText(self.list[0]["Log"])
        sizePolicy = QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        self.logTextEdit.setSizePolicy(sizePolicy)

        self.logGroup.addSettingCard(self.logTextEdit)

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
        self.yesButton.setText("开始下载")
        self.noButton = PushButton(self)
        self.noButton.setObjectName("noButton")
        self.noButton.setText("取消下载")

        self.buttonLayout.addWidget(self.noButton)
        self.buttonLayout.addWidget(self.yesButton)
        self.buttonLayout.setSpacing(18)

        self.settingGroup.addSettingCards([self.downloadFolderCard, self.blockNumCard])

        self.VBoxLayout.addWidget(self.versionGroup)
        self.VBoxLayout.addWidget(self.logGroup)
        self.VBoxLayout.addWidget(self.settingGroup)
        self.VBoxLayout.addLayout(self.buttonLayout)

        self.__connectSignalToSlot()

    def __connectSignalToSlot(self):
        self.downloadFolderCard.clicked.connect(
            self.__onDownloadFolderCardClicked)
        self.noButton.clicked.connect(self.close)

        self.yesButton.clicked.connect(self.startTask)

        self.versionCard.comboBox.currentIndexChanged.connect(self._onCurrentIndexChanged)

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

        signalBus.addTaskSignal.emit(self.list[self.versionCard.comboBox.currentIndex()]["Url"],
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

    def _onCurrentIndexChanged(self, Index: int):
        self.logTextEdit.setText(self.list[Index]["Log"])
