from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QFileDialog, QHBoxLayout, QSizePolicy
from qfluentwidgets import PushSettingCard, SettingCardGroup, RangeSettingCard, RangeConfigItem, RangeValidator, \
    PushButton, PrimaryPushButton, ComboBoxSettingCard, OptionsValidator, OptionsConfigItem, TextEdit, \
    Theme, qconfig
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

        self.widget.setMinimumSize(510, 410)
        self.widget.setMaximumSize(680, 420)
        print(qconfig.themeMode.value)
        if qconfig.themeMode.value == Theme.DARK:
            # C = ThemeColor.DARK_3.color()
            self.widget.setStyleSheet(".QFrame{border-radius:10px;background-color:rgb(39,39,39)}")
        else:
            self.widget.setStyleSheet(".QFrame{border-radius:10px;background-color:white}")

        # 信息组
        self.VersionGroup = SettingCardGroup(
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
            parent=self.VersionGroup
        )

        self.logTextEdit = TextEdit(self.VersionGroup)
        self.logTextEdit.setReadOnly(True)
        self.logTextEdit.setText(self.list[0]["Log"])
        sizePolicy = QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        self.logTextEdit.setSizePolicy(sizePolicy)

        self.VersionGroup.addSettingCards([self.versionCard, self.logTextEdit])

        # 下载设置组
        self.SettingGroup = SettingCardGroup(
            "下载设置", self.widget)

        # Choose Folder Card
        self.downloadFolderCard = PushSettingCard(
            "选择下载目录",
            FIF.DOWNLOAD,
            "下载目录",
            str(Path.cwd()),
            self.SettingGroup
        )

        # Choose Threading Card
        self.blockNumCard = RangeSettingCard(
            RangeConfigItem("Material", "AcrylicBlurRadius", 8, RangeValidator(0, 10)),
            FIF.CHAT,
            "下载线程数",
            '下载线程越多，下载越快，同时也越吃性能',
            self.SettingGroup
        )

        self.ButtonLayout = QHBoxLayout()

        self.yesButton = PrimaryPushButton(self)
        self.yesButton.setObjectName("yesButton")
        self.yesButton.setText("开始下载")
        self.noButton = PushButton(self)
        self.noButton.setObjectName("noButton")
        self.noButton.setText("取消下载")

        self.ButtonLayout.addWidget(self.noButton)
        self.ButtonLayout.addWidget(self.yesButton)
        self.ButtonLayout.setSpacing(18)

        self.SettingGroup.addSettingCards([self.downloadFolderCard, self.blockNumCard])

        self.VBoxLayout.addWidget(self.VersionGroup)
        self.VBoxLayout.addWidget(self.SettingGroup)
        self.VBoxLayout.addLayout(self.ButtonLayout)

        self.__connectSignalToSlot()

    def __connectSignalToSlot(self):
        self.downloadFolderCard.clicked.connect(
            self.__onDownloadFolderCardClicked)
        self.noButton.clicked.connect(self.close)

        self.yesButton.clicked.connect(self.startTask)

        self.versionCard.comboBox.currentIndexChanged.connect(self._onCurrentIndexChanged)

    def startTask(self):
        signalBus.addTaskSignal.emit(self.list[self.versionCard.comboBox.currentIndex()]["Url"],
                                     self.downloadFolderCard.contentLabel.text(), self.blockNumCard.configItem.value,
                                     self.dict["Name"], self.dict["Pixmap"])
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
