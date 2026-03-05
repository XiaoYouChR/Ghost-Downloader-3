import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout
from qfluentwidgets import SettingCardGroup, RangeSettingCard, FluentIcon, SwitchSettingCard

from app.supports.config import cfg
from app.view.components.setting_cards import SpinBoxSettingCard, SelectFolderSettingCard, ProxySettingCard
from features.http_pack.config import httpConfig

if sys.platform != "darwin":
    from qfluentwidgets import SmoothScrollArea as ScrollArea
else:
    from qfluentwidgets import ScrollArea


class SettingPage(ScrollArea):
    """设置页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Initialize
        self.container = QWidget()
        self.vBoxLayout = QVBoxLayout(self.container)
        self.generalDownloadGroup = SettingCardGroup(self.tr("综合下载设置"), self.container)

        self.initWidget()
        self.initCards()
        self.initLayout()
        self.connectSignalToSlot()

        # TODO Through Feature Service to load setting cards
        httpConfig.loadSettingCards(self)

    def initWidget(self):
        self.setWidget(self.container)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setObjectName("SettingPage")
        self.enableTransparentBackground()

    def initCards(self):
        # General Download
        self.maxTaskNumCard = RangeSettingCard(
            cfg.maxTaskNum,
            FluentIcon.TRAIN,
            self.tr("最大任务数"),
            self.tr("最多能同时进行的任务数量"),
            self.generalDownloadGroup,
        )
        self.generalDownloadGroup.addSettingCard(self.maxTaskNumCard)
        self.speedLimitationCard = SpinBoxSettingCard(
            FluentIcon.SPEED_OFF,
            self.tr("下载限速"),
            self.tr("限制每秒全局下载速度, 0 为不限速"),
            " KB/s",
            cfg.speedLimitation,
            self.generalDownloadGroup,
            512,
            1 / 1024,
        )
        self.generalDownloadGroup.addSettingCard(self.speedLimitationCard)
        self.SSLVerifyCard = SwitchSettingCard(
            FluentIcon.DEVELOPER_TOOLS,
            self.tr("下载时验证 SSL 证书"),
            self.tr("文件无法下载时，可尝试关闭该选项"),
            cfg.SSLVerify,
            self.generalDownloadGroup,
        )
        self.generalDownloadGroup.addSettingCard(self.SSLVerifyCard)
        self.downloadFolderCard = SelectFolderSettingCard(
            cfg.downloadFolder.value, cfg.memoryDownloadFolders, self.generalDownloadGroup
        )
        self.generalDownloadGroup.addSettingCard(self.downloadFolderCard)
        self.proxyServerCard = ProxySettingCard(
            cfg.proxyServer, self.generalDownloadGroup
        )
        self.generalDownloadGroup.addSettingCard(self.proxyServerCard)
        # TODO Headers Setting Card

    def initLayout(self):
        self.vBoxLayout.addWidget(self.generalDownloadGroup)

    def connectSignalToSlot(self):
        self.downloadFolderCard.pathChanged.connect(lambda x: cfg.set(cfg.downloadFolder, x))
