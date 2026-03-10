import sys
from base64 import b64decode
from typing import TYPE_CHECKING

import niquests
from PySide6.QtCore import Signal, Qt, QSize, QUrl
from PySide6.QtGui import QPixmap, QColor, QDesktopServices, QPainter
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy, QHBoxLayout, QFileDialog
from loguru import logger
from orjson import loads
from qfluentwidgets import MaskDialogBase, \
    FluentStyleSheet, SettingCardGroup, OptionsConfigItem, OptionsValidator, ComboBoxSettingCard, FluentIcon, \
    PlainTextEdit, PushSettingCard, RangeSettingCard, RangeConfigItem, RangeValidator, PrimaryPushButton, PushButton, \
    PixmapLabel, TitleLabel, BodyLabel, PrimarySplitPushButton, SimpleCardWidget, RoundMenu, Action, IconWidget, \
    CaptionLabel, isDarkTheme

from app.bases.interfaces import FeaturePack
from app.services.core_service import coreService
from app.supports.config import cfg
from app.supports.utils import getProxies

if sys.platform != "darwin":
    from qfluentwidgets import SmoothScrollArea as ScrollArea
else:
    from qfluentwidgets import ScrollArea

if TYPE_CHECKING:
    from app.view.windows.main_window import MainWindow


class JackYaoPack(FeaturePack):

    def load(self, mainWindow:"MainWindow"):
        mainWindow.resourceInterface = ResourceInterface()
        mainWindow.addSubInterface(mainWindow.resourceInterface, FluentIcon.CLOUD_DOWNLOAD, "资源下载")


async def run():
    # with open("./Content.json", "r", encoding="utf-8") as f:
    #     self.json = json.loads(f.read())["OS"]
    #     f.close()
    _ = getProxies()
    client = niquests.AsyncSession(happy_eyeballs=True)
    client.trust_env = False
    result = await client.get(
        url="https://xineko-my.sharepoint.com/personal/os_store_xineko_onmicrosoft_com/_layouts/52/download.aspx?share=IQCK7kKU1-8oSqWDNNPss2xeAbmG3v4cItTXNqW2NG9Hzwc",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64"},
        proxies=_, allow_redirects=True)
    await client.close()
    return loads(result.text)["OS"]


class LoadingStatusWidget(QWidget):
    retrySignal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.iconWidget = IconWidget(FluentIcon.SYNC, self)
        self.label = CaptionLabel("正在加载...", self)
        self.retryButton = PushButton("重试", self)
        self.vBoxLayout = QVBoxLayout(self)
        self.borderRadius = 10

        self.initWidget()

    def initWidget(self):
        self.iconWidget.setFixedSize(64, 64)

        self.label.setTextColor(QColor(96, 96, 96), QColor(216, 216, 216))
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)

        self.retryButton.setVisible(False)
        self.retryButton.clicked.connect(self.onRetryClicked)

        self.vBoxLayout.setSpacing(10)
        self.vBoxLayout.setContentsMargins(16, 20, 16, 20)
        self.vBoxLayout.addWidget(self.iconWidget, 0, Qt.AlignmentFlag.AlignHCenter)
        self.vBoxLayout.addWidget(self.label, 0, Qt.AlignmentFlag.AlignHCenter)
        self.vBoxLayout.addWidget(self.retryButton, 0, Qt.AlignmentFlag.AlignHCenter)

    def setLoading(self):
        """设置为加载状态"""
        self.iconWidget.setIcon(FluentIcon.SYNC)
        self.label.setText("正在加载...")
        self.retryButton.setVisible(False)

    def setError(self, errorText: str):
        """设置为错误状态"""
        self.iconWidget.setIcon(FluentIcon.CANCEL)
        self.label.setText(errorText)
        self.retryButton.setVisible(True)

    def onRetryClicked(self):
        """重试按钮点击事件"""
        self.setLoading()
        self.retrySignal.emit()

    @property
    def backgroundColor(self):
        return QColor(255, 255, 255, 13 if isDarkTheme() else 200)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self.backgroundColor)
        painter.setPen(Qt.PenStyle.NoPen)

        r = self.borderRadius
        painter.drawRoundedRect(self.rect(), r, r)


class ResourceInterface(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setObjectName("ResourceInterface")
        self.cards = []
        self.jsonData = []
        
        self.initWidget()
        self.initLayout()
        self.connectSignalToSlot()
        self.loadData()

    def initWidget(self):
        """初始化UI组件"""
        self.scrollWidget = QWidget()
        self.scrollWidget.setMinimumWidth(816)
        self.expandLayout = QVBoxLayout(self.scrollWidget)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.loadingStatusWidget = LoadingStatusWidget(self.scrollWidget)
        self.expandLayout.addWidget(self.loadingStatusWidget, 0, Qt.AlignmentFlag.AlignCenter)

    def initLayout(self):
        """设置布局"""
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.enableTransparentBackground()

    def connectSignalToSlot(self):
        """初始化信号连接"""
        self.loadingStatusWidget.retrySignal.connect(self.loadData)

    def loadData(self):
        """加载数据"""
        self.loadingStatusWidget.setLoading()
        coreService.runCoroutine(run(), self.loadInfoCards)

    def loadInfoCards(self, jsonData: list, error: str):
        """加载信息卡片"""
        if error:
            self.loadingStatusWidget.setError(f"加载失败: {error}")
            return

        self.jsonData = jsonData

        # 清除现有的卡片
        for card in self.cards:
            self.expandLayout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()

        for item in self.jsonData:
            card = SystemInfoCard(self.scrollWidget)
            self.cards.append(card)
            
            card.listData = item["List"]
            card.titleLabel.setText(item["Name"])
            
            logger.debug(f'Loading System Card: {item["Name"]}')

            # 从字节数据中创建QPixmap对象
            pixmap = QPixmap()
            pixmap.loadFromData(b64decode(item["Icon"]))
            card.logoPixmapLabel.setPixmap(pixmap)
            card.logoPixmapLabel.setFixedSize(71, 71)

            card.bodyLabel.setText(item["Intro"].replace(r"\n", "\n"))
            card.videoUrl = item["Video"]

            card.connectSignalToSlot()
            self.expandLayout.addWidget(card)
            card.show()

        self.hideLoadingStatusWidget()

    def hideLoadingStatusWidget(self):
        """隐藏加载状态控件"""
        self.expandLayout.removeWidget(self.loadingStatusWidget)
        self.loadingStatusWidget.hide()
        self.loadingStatusWidget.setParent(None)
        self.loadingStatusWidget.deleteLater()


class DownloadOptionDialog(MaskDialogBase):
    startSignal = Signal()

    def __init__(self, parent=None, listData=None, cardData=None):
        super().__init__(parent=parent)

        FluentStyleSheet.DIALOG.apply(self.widget)

        self.cardData = cardData
        self.listData = listData
        self.versions = []

        self.initWidget()
        self.initGroups()
        self.initButtons()
        self.initLayout()
        self.connectSignalToSlot()

    def initWidget(self):
        """初始化UI基础设置"""
        self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 50))
        self.setMaskColor(QColor(0, 0, 0, 76))

        self.mainLayout = QVBoxLayout(self.widget)
        self.mainLayout.setContentsMargins(18, 18, 18, 18)
        self.widget.setLayout(self.mainLayout)
        self.widget.setMinimumSize(510, 580)
        self.widget.setMaximumSize(680, 580)

    def initGroups(self):
        """设置各功能组"""
        self.initVersionGroup()
        self.initLogGroup()
        self.initSettingGroup()

    def initVersionGroup(self):
        """设置版本选择组"""
        self.versionGroup = SettingCardGroup("选择版本", self.widget)

        for item in self.listData:
            self.versions.append(item["Version"])

        versionItem = OptionsConfigItem(
            "Material", "Version", self.versions[0], OptionsValidator(self.versions))

        self.versionCard = ComboBoxSettingCard(
            versionItem,
            FluentIcon.VIEW,
            "选择版本",
            "选择你想下载的版本",
            texts=self.versions,
            parent=self.versionGroup
        )

        self.versionGroup.addSettingCard(self.versionCard)

    def initLogGroup(self):
        """设置日志组"""
        self.logGroup = SettingCardGroup("更新日志", self.widget)

        self.logTextEdit = PlainTextEdit(self.logGroup)
        self.logTextEdit.setReadOnly(True)
        self.logTextEdit.setMinimumHeight(140)
        self.logTextEdit.setPlainText(self.listData[0]["Log"])
        
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.logTextEdit.setSizePolicy(sizePolicy)
        self.logGroup.addSettingCard(self.logTextEdit)

    def initSettingGroup(self):
        """设置下载设置组"""
        self.settingGroup = SettingCardGroup("下载设置", self.widget)

        # 下载目录设置卡
        self.downloadFolderCard = PushSettingCard(
            "选择下载目录",
            FluentIcon.DOWNLOAD,
            "下载目录",
            cfg.downloadFolder.value,
            self.settingGroup
        )

        # 下载线程数设置卡
        self.threadCountCard = RangeSettingCard(
            RangeConfigItem("Material", "AcrylicBlurRadius", 24, RangeValidator(1, 256)),
            FluentIcon.CHAT,
            "下载线程数",
            '下载线程越多，下载越快，同时也越吃性能',
            self.settingGroup
        )

        self.settingGroup.addSettingCards([self.downloadFolderCard, self.threadCountCard])

    def initButtons(self):
        """设置按钮"""
        self.buttonLayout = QHBoxLayout()

        self.cancelButton = PushButton(self)
        self.cancelButton.setObjectName("cancelButton")
        self.cancelButton.setText("取消下载")

        self.startButton = PrimaryPushButton(self)
        self.startButton.setObjectName("startButton")
        self.startButton.setText("开始下载")

        self.buttonLayout.addWidget(self.cancelButton)
        self.buttonLayout.addWidget(self.startButton)
        self.buttonLayout.setSpacing(18)

    def initLayout(self):
        """设置整体布局"""
        self.mainLayout.addWidget(self.versionGroup)
        self.mainLayout.addWidget(self.logGroup)
        self.mainLayout.addWidget(self.settingGroup)
        self.mainLayout.addLayout(self.buttonLayout)

    def connectSignalToSlot(self):
        """连接信号槽"""
        self.downloadFolderCard.clicked.connect(self.onDownloadFolderClicked)
        self.cancelButton.clicked.connect(self.close)
        self.startButton.clicked.connect(self.startDownload)
        self.versionCard.comboBox.currentIndexChanged.connect(self.onVersionChanged)

    def startDownload(self):
        """开始下载任务"""
        # path = Path(self.downloadFolderCard.contentLabel.text())
        #
        # # 检测路径是否有权限写入
        # if not path.exists():
        #     try:
        #         path.mkdir(parents=True, exist_ok=True)
        #     except Exception as e:
        #         MessageBox("错误", repr(e), self)
        # else:
        #     if not os.access(path, os.W_OK):
        #         MessageBox("错误", "似乎是没有权限向此目录写入文件", self)
        #
        # addDownloadTask(self.list[self.versionCard.comboBox.currentIndex()]["Url"],
        #                              filePath=str(path), preBlockNum=self.blockNumCard.configItem.value)
        self.close()

    def onDownloadFolderClicked(self):
        """下载目录点击事件"""
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹", "./")
        if not folder or self.downloadFolderCard.contentLabel.text() == folder:
            return

        self.downloadFolderCard.setContent(folder)

    def onVersionChanged(self, index: int):
        """版本选择变化事件"""
        self.logTextEdit.setPlainText(self.listData[index]["Log"])


class SystemInfoCard(SimpleCardWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        
        self.listData = []
        self.videoUrl = ""
        self.pixmap = None
        
        self.initWidget()
        self.initMenu()
        self.initButtonText()

    def initWidget(self):
        """初始化UI组件"""
        self.setObjectName("SystemInfoCard")
        self.setFixedHeight(91)
        
        self.initMainLayout()
        self.initLogoLabel()
        self.initTextLayout()
        self.initTitleLabel()
        self.initBodyLabel()
        self.initDownloadButton()

    def initMainLayout(self):
        """设置主布局"""
        self.horizontalLayout = QHBoxLayout(self)
        self.horizontalLayout.setSpacing(12)
        self.horizontalLayout.setObjectName("horizontalLayout")

    def initLogoLabel(self):
        """设置Logo标签"""
        self.logoPixmapLabel = PixmapLabel(self)
        self.logoPixmapLabel.setObjectName("logoPixmapLabel")
        self.logoPixmapLabel.setMinimumSize(QSize(71, 71))
        self.logoPixmapLabel.setMaximumSize(QSize(71, 71))
        self.logoPixmapLabel.setScaledContents(True)
        self.logoPixmapLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.horizontalLayout.addWidget(self.logoPixmapLabel)

    def initTextLayout(self):
        """设置文本布局"""
        self.bodyVBoxLayout = QVBoxLayout()
        self.bodyVBoxLayout.setSpacing(0)
        self.bodyVBoxLayout.setObjectName("bodyVBoxLayout")

    def initTitleLabel(self):
        """设置标题标签"""
        self.titleLabel = TitleLabel(self)
        self.titleLabel.setObjectName("titleLabel")
        
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.titleLabel.sizePolicy().hasHeightForWidth())
        self.titleLabel.setSizePolicy(sizePolicy)
        self.bodyVBoxLayout.addWidget(self.titleLabel)

    def initBodyLabel(self):
        """设置内容标签"""
        self.bodyLabel = BodyLabel(self)
        self.bodyLabel.setObjectName("bodyLabel")
        
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.bodyLabel.sizePolicy().hasHeightForWidth())
        self.bodyLabel.setSizePolicy(sizePolicy)
        self.bodyLabel.setMaximumSize(QSize(16777215, 61))
        self.bodyLabel.setWordWrap(True)
        self.bodyVBoxLayout.addWidget(self.bodyLabel)
        self.horizontalLayout.addLayout(self.bodyVBoxLayout)

    def initDownloadButton(self):
        """设置下载按钮"""
        self.downloadButton = PrimarySplitPushButton(self)
        self.downloadButton.setObjectName("downloadButton")
        self.downloadButton.setFixedSize(QSize(121, 31))
        self.downloadButton.setText("       下载       ")
        self.horizontalLayout.addWidget(self.downloadButton)

    def initMenu(self):
        """设置菜单"""
        self.menu = RoundMenu(parent=self)
        self.videoAction = Action(FluentIcon.VIDEO, "视频")
        self.menu.addAction(self.videoAction)
        self.downloadButton.setFlyout(self.menu)

    def initButtonText(self):
        """设置按钮文本"""
        self.downloadButton.setText("      下载      ")

    def connectSignalToSlot(self):
        """连接信号槽"""
        self.videoAction.triggered.connect(self.openVideoUrl)
        self.downloadButton.clicked.connect(self.openDownloadDialog)

    def openVideoUrl(self):
        """打开视频链接"""
        QDesktopServices.openUrl(QUrl(self.videoUrl))

    def openDownloadDialog(self):
        """打开下载对话框"""
        dialog = DownloadOptionDialog(
            self.window(),
            self.listData,
            {"pixmap": self.pixmap, "name": self.titleLabel.text()}
        )
        dialog.exec()
