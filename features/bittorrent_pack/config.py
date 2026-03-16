from typing import TYPE_CHECKING

from qfluentwidgets import (
    BodyLabel,
    BoolValidator,
    ComboBoxSettingCard,
    ConfigItem,
    ConfigValidator,
    FluentIcon,
    InfoBar,
    LineEdit,
    MessageBoxBase,
    OptionsConfigItem,
    OptionsValidator,
    PlainTextEdit,
    PrimaryPushButton,
    RangeConfigItem,
    RangeSettingCard,
    RangeValidator,
    SettingCard,
    SettingCardGroup,
    SwitchSettingCard,
    ToolButton,
    ToolTipFilter,
)

from app.bases.models import PackConfig
from app.services.core_service import coreService
from app.supports.config import cfg
from app.view.components.editors import AutoSizingEdit
from app.view.components.setting_cards import SpinBoxSettingCard
from .trackers import fetchWebTrackers, formatTrackers, normalizeTrackerSource, parseTrackerText

if TYPE_CHECKING:
    from app.view.pages.setting_page import SettingPage


DEFAULT_WEB_TRACKER_SOURCE = "https://cf.trackerslist.com/best.txt"


class WebTrackerSourceValidator(ConfigValidator):
    def validate(self, value) -> bool:
        return bool(normalizeTrackerSource(str(value or "")))

    def correct(self, value) -> str:
        source = normalizeTrackerSource(str(value or ""))
        return source or DEFAULT_WEB_TRACKER_SOURCE


class WebTrackerListValidator(ConfigValidator):
    def validate(self, value) -> bool:
        return isinstance(value, str)

    def correct(self, value) -> str:
        return value if isinstance(value, str) else ""


def getCachedWebTrackers() -> list[str]:
    return parseTrackerText(bittorrentConfig.webTrackerList.value)


def saveCachedWebTrackers(trackers: list[str]):
    cfg.set(bittorrentConfig.webTrackerList, formatTrackers(trackers))


async def refreshConfiguredWebTrackers(sourceUrl: str | None = None) -> list[str]:
    source = normalizeTrackerSource(sourceUrl or bittorrentConfig.webTrackerSource.value)
    if not source:
        raise ValueError("Web Tracker 源地址无效")
    trackers = await fetchWebTrackers(source)
    cfg.set(bittorrentConfig.webTrackerSource, source)
    saveCachedWebTrackers(trackers)
    return trackers


class WebTrackerDialog(MessageBoxBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.widget.setMinimumWidth(720)
        self.sourceLabel = BodyLabel(self.tr("Tracker 源地址"), self.widget)
        self.sourceEdit = LineEdit(self.widget)
        self.trackersLabel = BodyLabel(self.tr("当前 Tracker 列表"), self.widget)
        self.trackersEdit = AutoSizingEdit(self.widget)
        self.refreshButton = PrimaryPushButton(self.tr("从源刷新"), self.widget)

        self.yesButton.setText(self.tr("保存"))
        self.cancelButton.setText(self.tr("取消"))
        self.sourceEdit.setPlaceholderText(DEFAULT_WEB_TRACKER_SOURCE)
        self.sourceEdit.setText(bittorrentConfig.webTrackerSource.value)
        self.trackersEdit.setPlainText(bittorrentConfig.webTrackerList.value)
        self.refreshButton.clicked.connect(self._onRefreshClicked)

        self.viewLayout.addWidget(self.sourceLabel)
        self.viewLayout.addWidget(self.sourceEdit)
        self.viewLayout.addWidget(self.trackersLabel)
        self.viewLayout.addWidget(self.trackersEdit)
        self.viewLayout.addWidget(self.refreshButton, 0)

    def _onRefreshClicked(self):
        source = normalizeTrackerSource(self.sourceEdit.text())
        if not source:
            InfoBar.error(self.tr("源地址无效"), self.tr("请输入有效的 HTTP/HTTPS 地址"), parent=self)
            return

        self.refreshButton.setEnabled(False)
        self.refreshButton.setText(self.tr("刷新中..."))
        coreService.runCoroutine(fetchWebTrackers(source), self._onTrackersLoaded)

    def _onTrackersLoaded(self, result, error: str | None):
        self.refreshButton.setEnabled(True)
        self.refreshButton.setText(self.tr("从源刷新"))
        if error:
            InfoBar.error(self.tr("刷新失败"), error, parent=self)
            return
        self.trackersEdit.setPlainText(formatTrackers(result or []))
        InfoBar.success(
            self.tr("刷新完成"),
            self.tr("已加载 {0} 条 Tracker").format(len(result or [])),
            parent=self,
        )

    def validate(self) -> bool:
        source = normalizeTrackerSource(self.sourceEdit.text())
        if not source:
            InfoBar.error(self.tr("源地址无效"), self.tr("请输入有效的 HTTP/HTTPS 地址"), parent=self)
            return False

        cfg.set(bittorrentConfig.webTrackerSource, source)
        saveCachedWebTrackers(parseTrackerText(self.trackersEdit.toPlainText()))
        return True


class WebTrackerCard(SettingCard):
    def __init__(self, parent=None):
        super().__init__(
            FluentIcon.GLOBE,
            self.tr("Web Tracker"),
            self.tr("来源: {0}\n当前缓存: {1} 条 Tracker"),
            parent,
        )
        self.manageButton = PrimaryPushButton(self.tr("管理"), self)
        self.refreshButton = ToolButton(FluentIcon.SYNC, self)
        self.hBoxLayout.addWidget(self.manageButton, 0)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.refreshButton, 0)
        self.hBoxLayout.addSpacing(16)
        self.refreshButton.setToolTip(self.tr("刷新缓存"))
        self.refreshButton.installEventFilter(ToolTipFilter(self.refreshButton))
        self.manageButton.clicked.connect(self._onManageClicked)
        self.refreshButton.clicked.connect(self._onRefreshClicked)
        self.refreshContent()

    def refreshContent(self):
        trackers = getCachedWebTrackers()
        self.setContent(
            self.tr("来源: {0}\n当前缓存: {1} 条 Tracker").format(
                bittorrentConfig.webTrackerSource.value,
                len(trackers),
            )
        )

    def _onManageClicked(self):
        dialog = WebTrackerDialog(self.window())
        try:
            if dialog.exec():
                self.refreshContent()
        finally:
            dialog.deleteLater()

    def _onRefreshClicked(self):
        self.refreshButton.setEnabled(False)
        coreService.runCoroutine(refreshConfiguredWebTrackers(), self._onRefreshFinished)

    def _onRefreshFinished(self, result, error: str | None):
        self.refreshButton.setEnabled(True)
        if error:
            InfoBar.error(self.tr("刷新 Web Tracker 失败"), error, parent=self.window())
            return
        self.refreshContent()
        InfoBar.success(
            self.tr("刷新完成"),
            self.tr("已缓存 {0} 条 Tracker").format(len(result or [])),
            parent=self.window(),
        )


class BitTorrentConfig(PackConfig):
    listenPort = RangeConfigItem("BitTorrent", "ListenPort", 0, RangeValidator(0, 65535))
    metadataTimeout = RangeConfigItem("BitTorrent", "MetadataTimeout", 30, RangeValidator(5, 300))
    connectionsLimit = RangeConfigItem("BitTorrent", "ConnectionsLimit", 200, RangeValidator(20, 2000))
    downloadRateLimit = RangeConfigItem(
        "BitTorrent",
        "DownloadRateLimit",
        0,
        RangeValidator(0, 1024 * 1024 * 100),
    )
    uploadRateLimit = RangeConfigItem(
        "BitTorrent",
        "UploadRateLimit",
        0,
        RangeValidator(0, 1024 * 1024 * 100),
    )
    sequentialDownload = ConfigItem("BitTorrent", "SequentialDownload", False, BoolValidator())
    enableDHT = ConfigItem("BitTorrent", "EnableDHT", True, BoolValidator())
    enableLSD = ConfigItem("BitTorrent", "EnableLSD", True, BoolValidator())
    enableUPnP = ConfigItem("BitTorrent", "EnableUPnP", True, BoolValidator())
    enableNATPMP = ConfigItem("BitTorrent", "EnableNATPMP", True, BoolValidator())
    seedRatioLimitPercent = RangeConfigItem("BitTorrent", "SeedRatioLimitPercent", 0, RangeValidator(0, 10000))
    seedTimeLimitMinutes = RangeConfigItem("BitTorrent", "SeedTimeLimitMinutes", 0, RangeValidator(0, 43200))
    enableWebTrackers = ConfigItem("BitTorrent", "EnableWebTrackers", True, BoolValidator())
    autoRefreshWebTrackers = ConfigItem("BitTorrent", "AutoRefreshWebTrackers", True, BoolValidator())
    webTrackerSource = ConfigItem(
        "BitTorrent",
        "WebTrackerSource",
        DEFAULT_WEB_TRACKER_SOURCE,
        WebTrackerSourceValidator(),
    )
    webTrackerList = ConfigItem("BitTorrent", "WebTrackerList", "", WebTrackerListValidator())
    storageMode = OptionsConfigItem(
        "BitTorrent",
        "StorageMode",
        "sparse",
        OptionsValidator(["sparse", "allocate"]),
    )

    def loadSettingCards(self, settingPage: "SettingPage"):
        self.bittorrentGroup = SettingCardGroup(self.tr("BitTorrent 下载"), settingPage.container)
        self.listenPortCard = SpinBoxSettingCard(
            FluentIcon.GLOBE,
            self.tr("监听端口"),
            self.tr("0 表示交给系统自动分配可用端口"),
            "",
            self.listenPort,
            self.bittorrentGroup,
            1,
        )
        self.metadataTimeoutCard = SpinBoxSettingCard(
            FluentIcon.HISTORY,
            self.tr("元数据超时"),
            self.tr("解析 magnet 链接时等待元数据的最长时间"),
            " s",
            self.metadataTimeout,
            self.bittorrentGroup,
            5,
        )
        self.connectionsLimitCard = RangeSettingCard(
            self.connectionsLimit,
            FluentIcon.PEOPLE,
            self.tr("连接数上限"),
            self.tr("单个 BT 任务对应 session 的最大连接数"),
            self.bittorrentGroup,
        )
        self.downloadRateLimitCard = SpinBoxSettingCard(
            FluentIcon.DOWNLOAD,
            self.tr("下载限速"),
            self.tr("0 表示不限速，单位为 session 级别的 KB/s"),
            " KB/s",
            self.downloadRateLimit,
            self.bittorrentGroup,
            256,
            1 / 1024,
        )
        self.uploadRateLimitCard = SpinBoxSettingCard(
            FluentIcon.SHARE,
            self.tr("上传限速"),
            self.tr("0 表示不限速，单位为 session 级别的 KB/s"),
            " KB/s",
            self.uploadRateLimit,
            self.bittorrentGroup,
            64,
            1 / 1024,
        )
        self.seedRatioLimitCard = SpinBoxSettingCard(
            FluentIcon.SHARE,
            self.tr("自动暂停做种分享率"),
            self.tr("下载完成后继续做种；0 表示不按分享率自动暂停，100% 表示分享率 1.0"),
            " %",
            self.seedRatioLimitPercent,
            self.bittorrentGroup,
            50,
        )
        self.seedTimeLimitCard = SpinBoxSettingCard(
            FluentIcon.STOP_WATCH,
            self.tr("自动暂停做种时长"),
            self.tr("下载完成后继续做种；0 表示不按做种时长自动暂停"),
            " min",
            self.seedTimeLimitMinutes,
            self.bittorrentGroup,
            10,
        )
        self.storageModeCard = ComboBoxSettingCard(
            self.storageMode,
            FluentIcon.SAVE,
            self.tr("文件分配模式"),
            self.tr("稀疏分配更省磁盘写入，预分配更容易提前暴露空间不足"),
            texts=[self.tr("稀疏分配"), self.tr("预分配")],
            parent=self.bittorrentGroup,
        )
        self.sequentialDownloadCard = SwitchSettingCard(
            FluentIcon.LIBRARY,
            self.tr("顺序下载"),
            self.tr("按文件顺序下载内容，适合边下边看但通常会影响整体效率"),
            self.sequentialDownload,
            self.bittorrentGroup,
        )
        self.enableDHTCard = SwitchSettingCard(
            FluentIcon.GLOBE,
            self.tr("启用 DHT"),
            self.tr("允许通过 DHT 网络发现 peers"),
            self.enableDHT,
            self.bittorrentGroup,
        )
        self.enableLSDCard = SwitchSettingCard(
            FluentIcon.HOME,
            self.tr("启用 LSD"),
            self.tr("在局域网中广播并发现同一 torrent 的 peers"),
            self.enableLSD,
            self.bittorrentGroup,
        )
        self.enableUPnPCard = SwitchSettingCard(
            FluentIcon.GLOBE,
            self.tr("启用 UPnP"),
            self.tr("允许自动尝试映射路由器端口"),
            self.enableUPnP,
            self.bittorrentGroup,
        )
        self.enableNATPMPCard = SwitchSettingCard(
            FluentIcon.GLOBE,
            self.tr("启用 NAT-PMP"),
            self.tr("允许自动尝试通过 NAT-PMP 映射端口"),
            self.enableNATPMP,
            self.bittorrentGroup,
        )
        self.enableWebTrackersCard = SwitchSettingCard(
            FluentIcon.LINK,
            self.tr("启用 Web Tracker"),
            self.tr("把配置好的额外 Trackers 合并到新建 BT 任务中"),
            self.enableWebTrackers,
            self.bittorrentGroup,
        )
        self.autoRefreshWebTrackersCard = SwitchSettingCard(
            FluentIcon.SYNC,
            self.tr("新建任务时刷新 Web Tracker"),
            self.tr("创建新的 BT 任务时，先从源地址拉取最新 Tracker；失败时回退到缓存"),
            self.autoRefreshWebTrackers,
            self.bittorrentGroup,
        )
        self.webTrackerCard = WebTrackerCard(self.bittorrentGroup)

        for card in (
            self.listenPortCard,
            self.metadataTimeoutCard,
            self.connectionsLimitCard,
            self.downloadRateLimitCard,
            self.uploadRateLimitCard,
            self.seedRatioLimitCard,
            self.seedTimeLimitCard,
            self.storageModeCard,
            self.sequentialDownloadCard,
            self.enableDHTCard,
            self.enableLSDCard,
            self.enableUPnPCard,
            self.enableNATPMPCard,
            self.enableWebTrackersCard,
            self.autoRefreshWebTrackersCard,
            self.webTrackerCard,
        ):
            self.bittorrentGroup.addSettingCard(card)

        settingPage.vBoxLayout.addWidget(self.bittorrentGroup)


bittorrentConfig = BitTorrentConfig()
