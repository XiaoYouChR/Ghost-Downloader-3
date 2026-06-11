import sys
from typing import TYPE_CHECKING

from qfluentwidgets import (
    BoolValidator,
    ComboBoxSettingCard,
    ConfigItem,
    FluentIcon,
    OptionsConfigItem,
    OptionsValidator,
    RangeConfigItem,
    RangeSettingCard,
    RangeValidator,
    SwitchSettingCard,
)

from app.bases.models import PackConfig
from app.supports.config import StringListValidator
from app.view.components.setting_card_group import CollapsibleSettingCardGroup
from app.view.components.setting_cards import SpinBoxSettingCard
from .web_tracker.schema import (
    DEFAULT_WEB_TRACKER_SOURCE,
    SourceCacheSerializer,
    SourceCacheValidator,
)

if TYPE_CHECKING:
    from app.view.pages.setting_page import SettingPage


class BitTorrentConfig(PackConfig):
    listenPort = RangeConfigItem("BitTorrent", "ListenPort", 0, RangeValidator(0, 65535))
    metadataTimeout = RangeConfigItem("BitTorrent", "MetadataTimeout", 30, RangeValidator(5, 300))
    connectionsLimit = RangeConfigItem("BitTorrent", "ConnectionsLimit", 500, RangeValidator(20, 2000))
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
    saveMagnetTorrentFile = ConfigItem("BitTorrent", "SaveMagnetTorrentFile", False, BoolValidator())
    enableWebTrackers = ConfigItem("BitTorrent", "EnableWebTrackers", True, BoolValidator())
    autoRefreshWebTrackers = ConfigItem("BitTorrent", "AutoRefreshWebTrackers", True, BoolValidator())
    associateFileTypes = ConfigItem("BitTorrent", "AssociateFileTypes", False, BoolValidator())
    webTrackerSources = ConfigItem(
        "BitTorrent",
        "WebTrackerSources",
        [DEFAULT_WEB_TRACKER_SOURCE],
        StringListValidator(),
    )
    webTrackerSourceCache = ConfigItem(
        "BitTorrent",
        "WebTrackerSourceCache",
        {},
        SourceCacheValidator(),
        SourceCacheSerializer(),
    )
    webTrackerCustomList = ConfigItem("BitTorrent", "WebTrackerCustomList", "")
    storageMode = OptionsConfigItem(
        "BitTorrent",
        "StorageMode",
        "sparse",
        OptionsValidator(["sparse", "allocate"]),
    )

    settingsTitle = "BitTorrent 下载"

    def settingsSchema(self) -> list[dict]:
        # Web Tracker 源管理是交互流程（单独补）；这里是能进 schema 的普通设置。限速值为 session 级字节数。
        return [
            {"kind": "int", "label": "监听端口", "key": "listenPort", "value": self.listenPort.value, "min": 0, "max": 65535},
            {"kind": "int", "label": "元数据超时(秒)", "key": "metadataTimeout", "value": self.metadataTimeout.value, "min": 5, "max": 300},
            {"kind": "int", "label": "连接数上限", "key": "connectionsLimit", "value": self.connectionsLimit.value, "min": 20, "max": 2000},
            {"kind": "int", "label": "下载限速(字节/秒,0 不限)", "key": "downloadRateLimit", "value": self.downloadRateLimit.value, "min": 0, "max": 1024 * 1024 * 100},
            {"kind": "int", "label": "上传限速(字节/秒,0 不限)", "key": "uploadRateLimit", "value": self.uploadRateLimit.value, "min": 0, "max": 1024 * 1024 * 100},
            {"kind": "int", "label": "自动暂停做种分享率(%,0 不限)", "key": "seedRatioLimitPercent", "value": self.seedRatioLimitPercent.value, "min": 0, "max": 10000},
            {"kind": "int", "label": "自动暂停做种时长(分,0 不限)", "key": "seedTimeLimitMinutes", "value": self.seedTimeLimitMinutes.value, "min": 0, "max": 43200},
            {"kind": "combo", "label": "文件分配模式", "key": "storageMode", "value": self.storageMode.value,
             "options": [{"label": "稀疏分配", "value": "sparse"}, {"label": "预分配", "value": "allocate"}]},
            {"kind": "switch", "label": "保存 Magnet 种子文件", "key": "saveMagnetTorrentFile", "value": self.saveMagnetTorrentFile.value},
            {"kind": "switch", "label": "顺序下载", "key": "sequentialDownload", "value": self.sequentialDownload.value},
            {"kind": "switch", "label": "启用 DHT", "key": "enableDHT", "value": self.enableDHT.value},
            {"kind": "switch", "label": "启用 LSD", "key": "enableLSD", "value": self.enableLSD.value},
            {"kind": "switch", "label": "启用 UPnP", "key": "enableUPnP", "value": self.enableUPnP.value},
            {"kind": "switch", "label": "启用 NAT-PMP", "key": "enableNATPMP", "value": self.enableNATPMP.value},
            {"kind": "switch", "label": "启用 Web Tracker", "key": "enableWebTrackers", "value": self.enableWebTrackers.value},
            {"kind": "switch", "label": "新建任务时刷新 Web Tracker", "key": "autoRefreshWebTrackers", "value": self.autoRefreshWebTrackers.value},
            {"kind": "lines", "label": "Web Tracker 源地址", "key": "webTrackerSources", "value": list(self.webTrackerSources.value),
             "placeholder": "每行一个 tracker 列表源 URL，新建任务时自动拉取合并"},
            {"kind": "switch", "label": "关联 .torrent 文件", "key": "associateFileTypes", "value": self.associateFileTypes.value},
        ]

    def setupSettings(self, settingPage: "SettingPage"):
        from .web_tracker.card import WebTrackerCard

        self.bittorrentGroup = CollapsibleSettingCardGroup(self.tr("BitTorrent 下载"), "bittorrent", settingPage.container)
        # macOS 的文件关联在构建时烘进 Info.plist, 运行时开关无意义, 不创建也不显示
        if sys.platform != "darwin":
            self.associateCard = SwitchSettingCard(
                FluentIcon.LINK,
                self.tr("关联 .torrent 文件"),
                self.tr("把 .torrent 文件的打开方式设为 Ghost Downloader"),
                self.associateFileTypes,
                self.bittorrentGroup,
            )
            self.bittorrentGroup.addSettingCard(self.associateCard)
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
            self.tr("0 表示不限速,单位为 session 级别的 KB/s"),
            " KB/s",
            self.downloadRateLimit,
            self.bittorrentGroup,
            256,
            1 / 1024,
        )
        self.uploadRateLimitCard = SpinBoxSettingCard(
            FluentIcon.SHARE,
            self.tr("上传限速"),
            self.tr("0 表示不限速,单位为 session 级别的 KB/s"),
            " KB/s",
            self.uploadRateLimit,
            self.bittorrentGroup,
            64,
            1 / 1024,
        )
        self.seedRatioLimitCard = SpinBoxSettingCard(
            FluentIcon.SHARE,
            self.tr("自动暂停做种分享率"),
            self.tr("下载完成后继续做种;0 表示不按分享率自动暂停,100% 表示分享率 1.0"),
            " %",
            self.seedRatioLimitPercent,
            self.bittorrentGroup,
            50,
        )
        self.seedTimeLimitCard = SpinBoxSettingCard(
            FluentIcon.STOP_WATCH,
            self.tr("自动暂停做种时长"),
            self.tr("下载完成后继续做种;0 表示不按做种时长自动暂停"),
            " min",
            self.seedTimeLimitMinutes,
            self.bittorrentGroup,
            10,
        )
        self.storageModeCard = ComboBoxSettingCard(
            self.storageMode,
            FluentIcon.SAVE,
            self.tr("文件分配模式"),
            self.tr("稀疏分配更省磁盘写入,预分配更容易提前暴露空间不足"),
            texts=[self.tr("稀疏分配"), self.tr("预分配")],
            parent=self.bittorrentGroup,
        )
        self.saveMagnetTorrentFileCard = SwitchSettingCard(
            FluentIcon.SAVE,
            self.tr("保存 Magnet 种子文件"),
            self.tr("下载 magnet 链接时,在下载目录额外保存解析得到的 .torrent 文件"),
            self.saveMagnetTorrentFile,
            self.bittorrentGroup,
        )
        self.sequentialDownloadCard = SwitchSettingCard(
            FluentIcon.LIBRARY,
            self.tr("顺序下载"),
            self.tr("按文件顺序下载内容,适合边下边看但通常会影响整体效率"),
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
            self.tr("创建新的 BT 任务时,先从源地址拉取最新 Tracker;失败时回退到缓存"),
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
            self.saveMagnetTorrentFileCard,
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

        settingPage.addSettingGroup(self.bittorrentGroup)


bittorrentConfig = BitTorrentConfig()
