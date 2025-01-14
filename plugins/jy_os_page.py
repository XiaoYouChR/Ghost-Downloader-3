import base64
import json
import os
from pathlib import Path

import httpx
from PySide6.QtCore import Qt, QThread, Signal, QDir, QUrl, QSize, QCoreApplication
from PySide6.QtGui import QPixmap, QColor, QDesktopServices
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QSizePolicy, QHBoxLayout, QFileDialog
from loguru import logger
from qfluentwidgets import SmoothScrollArea, TitleLabel, SettingCardGroup, OptionsConfigItem, OptionsValidator, \
    ComboBoxSettingCard, FluentIcon as FIF, TextEdit, PushSettingCard, RangeSettingCard, RangeConfigItem, \
    RangeValidator, PrimaryPushButton, PushButton, MessageBox, CardWidget, RoundMenu, Action, PixmapLabel, BodyLabel, \
    PrimarySplitPushButton, NavigationItemPosition, FluentStyleSheet, IndeterminateProgressRing
from qfluentwidgets.components.dialog_box.mask_dialog_base import MaskDialogBase

from app.common.config import Headers
from app.common.methods import getProxy
from app.common.plugin_base import PluginBase
from app.common.signal_bus import signalBus


class JyOSPagePlugin(PluginBase):
    def __init__(self, mainWindow):
        self.name = "杰克姚定制系统下载页面"
        self.version = "1.0.0"
        self.author = "XiaoYouChR"
        self.icon = ":/plugins/JyOSPagePlugin/Logo.png"
        self.description = "官方演示插件: 杰克姚定制系统下载页面插件"
        self.mainWindow = mainWindow

    def load(self):
        self.mainWindow.homeInterface = HomeInterface(self.mainWindow)
        self.mainWindow.addSubInterface(self.mainWindow.homeInterface, FIF.CLOUD_DOWNLOAD, "系统下载", position=NavigationItemPosition.SCROLL)


class getInfoThread(QThread):
    gotInfo = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent=parent)

    def run(self):
        # with open("./Content.json", "r", encoding="utf-8") as f:
        #     self.json = json.loads(f.read())["OS"]
        #     f.close()

        self.gotInfo.emit(json.loads(httpx.get(
            url="https://seelevollerei-my.sharepoint.com/personal/jackyao_xn--7et36u_cn/_layouts/52/download.aspx?share=Ecm5kLYVJedKlw60gcDkxPEB1PlS5Y-P-ttDSit_V8KuLw",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64"},
            proxy=getProxy(), follow_redirects=True).text)["OS"])


class HomeInterface(SmoothScrollArea):
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
        self.loadingRing = IndeterminateProgressRing(self.scrollWidget)
        self.loadingRing.setObjectName("LoadingRing")
        self.expandLayout.addWidget(self.loadingRing, alignment=Qt.AlignCenter)
        self.scrollWidget.setMinimumWidth(816)

        self.GetInfoThread = getInfoThread(self)
        self.GetInfoThread.gotInfo.connect(self.loadInfoCards)
        self.GetInfoThread.start()

    def loadInfoCards(self, json: list):
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
            _.LogoPixmapLabel.setFixedSize(71, 71)

            _.BodyLabel.setText(i["Intro"].replace(r"\n", "\n"))

            _.Video = i["Video"]

            _.connect_signal_to_slot()

            self.expandLayout.addWidget(_)

            _.show()

        self.expandLayout.removeWidget(self.loadingRing)
        self.loadingRing.hide()
        self.loadingRing.setParent(None)
        self.loadingRing.deleteLater()


class DownloadOptionDialog(MaskDialogBase):
    startSignal = Signal()

    def __init__(self, parent=None, list=None, dict=None):
        super().__init__(parent=parent)

        FluentStyleSheet.DIALOG.apply(self.widget)

        self.dict = dict
        self.list = list
        self.versions = []

        self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 50))
        self.setMaskColor(QColor(0, 0, 0, 76))

        self.VBoxLayout = QVBoxLayout(self.widget)
        self.VBoxLayout.setContentsMargins(18, 18, 18, 18)

        self.widget.setLayout(self.VBoxLayout)

        self.widget.setMinimumSize(510, 530)
        self.widget.setMaximumSize(680, 540)

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
            RangeConfigItem("Material", "AcrylicBlurRadius", 24, RangeValidator(1, 256)),
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
                                     "", "working", Headers, False)
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


class Ui_SystemInfoCard(object):
    def setupUi(self, SystemInfoCard):
        if not SystemInfoCard.objectName():
            SystemInfoCard.setObjectName(u"SystemInfoCard")
        SystemInfoCard.resize(793, 91)
        SystemInfoCard.setMinimumSize(QSize(793, 91))
        SystemInfoCard.setMaximumSize(QSize(16777215, 91))
        self.horizontalLayout = QHBoxLayout(SystemInfoCard)
        self.horizontalLayout.setSpacing(12)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.LogoPixmapLabel = PixmapLabel(SystemInfoCard)
        self.LogoPixmapLabel.setObjectName(u"LogoPixmapLabel")
        self.LogoPixmapLabel.setMinimumSize(QSize(71, 71))
        self.LogoPixmapLabel.setMaximumSize(QSize(71, 71))
        self.LogoPixmapLabel.setScaledContents(True)
        self.LogoPixmapLabel.setAlignment(Qt.AlignCenter)

        self.horizontalLayout.addWidget(self.LogoPixmapLabel)

        self.BodyVBoxLayout = QVBoxLayout()
        self.BodyVBoxLayout.setSpacing(0)
        self.BodyVBoxLayout.setObjectName(u"BodyVBoxLayout")
        self.TitleLabel = TitleLabel(SystemInfoCard)
        self.TitleLabel.setObjectName(u"TitleLabel")
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.TitleLabel.sizePolicy().hasHeightForWidth())
        self.TitleLabel.setSizePolicy(sizePolicy)

        self.BodyVBoxLayout.addWidget(self.TitleLabel)

        self.BodyLabel = BodyLabel(SystemInfoCard)
        self.BodyLabel.setObjectName(u"BodyLabel")
        sizePolicy1 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.BodyLabel.sizePolicy().hasHeightForWidth())
        self.BodyLabel.setSizePolicy(sizePolicy1)
        self.BodyLabel.setMaximumSize(QSize(16777215, 61))
        self.BodyLabel.setWordWrap(True)

        self.BodyVBoxLayout.addWidget(self.BodyLabel)

        self.horizontalLayout.addLayout(self.BodyVBoxLayout)

        self.PrimarySplitPushButton = PrimarySplitPushButton(SystemInfoCard)
        self.PrimarySplitPushButton.setObjectName(u"PrimarySplitPushButton")
        self.PrimarySplitPushButton.setMinimumSize(QSize(121, 31))
        self.PrimarySplitPushButton.setMaximumSize(QSize(121, 31))

        self.horizontalLayout.addWidget(self.PrimarySplitPushButton)

        self.retranslateUi(SystemInfoCard)


    # setupUi

    def retranslateUi(self, SystemInfoCard):
        SystemInfoCard.setWindowTitle(QCoreApplication.translate("SystemInfoCard", u"Form", None))
        self.PrimarySplitPushButton.setProperty("text_", QCoreApplication.translate("SystemInfoCard",
                                                                                    u"       \u4e0b\u8f7d       ",
                                                                                    None))
    # retranslateUi


class SystemInfoCard(CardWidget, Ui_SystemInfoCard):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setupUi(self)

        self.List = []
        self.Video = ""
        self.pixmap: QPixmap

        self.PrimarySplitPushButton.setText("      下载      ")
        self.Menu = RoundMenu(parent=self)
        self.VideoAction = Action(FIF.VIDEO, "视频")
        self.Menu.addAction(self.VideoAction)
        self.PrimarySplitPushButton.setFlyout(self.Menu)

    def connect_signal_to_slot(self):
        self.VideoAction.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(self.Video)))
        self.PrimarySplitPushButton.clicked.connect(self.open_download_messagebox)

    def open_download_messagebox(self):
        w = DownloadOptionDialog(self.parent().parent().parent().parent().parent().parent(), self.List,
                                 {"Pixmap": self.pixmap, "Name": self.TitleLabel.text()})
        w.exec()
