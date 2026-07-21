from __future__ import annotations

from app.config.cfg import ConfigItem
from app.models.pack import PackConfig
from qfluentwidgets import (
    BoolValidator,
    OptionsConfigItem,
    OptionsValidator,
    RangeConfigItem,
    RangeValidator,
)

from .web_tracker.schema import (
    DEFAULT_WEB_TRACKER_SOURCE,
    SourceCacheSerializer,
    SourceCacheValidator,
)


class StringListValidator:
    def validate(self, value) -> bool:
        return isinstance(value, list) and all(isinstance(i, str) for i in value)

    def correct(self, value) -> list:
        if not isinstance(value, list):
            return []
        return [i for i in value if isinstance(i, str)]


class BitTorrentConfig(PackConfig):
    enableDht = ConfigItem("BitTorrent", "EnableDHT", True, BoolValidator())
    enableLsd = ConfigItem("BitTorrent", "EnableLSD", True, BoolValidator())
    enableWebTrackers = ConfigItem("BitTorrent", "EnableWebTrackers", True, BoolValidator())
    autoRefreshWebTrackers = ConfigItem("BitTorrent", "AutoRefreshWebTrackers", True, BoolValidator())
    saveMagnetFile = ConfigItem("BitTorrent", "SaveMagnetTorrentFile", False, BoolValidator())
    seedingRatioLimit = RangeConfigItem("BitTorrent", "SeedRatioLimitPercent", 0, RangeValidator(0, 10000))
    seedingTimeLimit = RangeConfigItem("BitTorrent", "SeedTimeLimitMinutes", 0, RangeValidator(0, 43200))
    maxConnections = RangeConfigItem("BitTorrent", "ConnectionsLimit", 500, RangeValidator(20, 2000))
    maxUploadSpeed = RangeConfigItem("BitTorrent", "UploadRateLimit", 0, RangeValidator(0, 1024 * 1024 * 100))
    listenPort = RangeConfigItem("BitTorrent", "ListenPort", 0, RangeValidator(0, 65535))
    metadataTimeout = RangeConfigItem("BitTorrent", "MetadataTimeout", 30, RangeValidator(5, 300))
    enableSequentialDownload = ConfigItem("BitTorrent", "SequentialDownload", False, BoolValidator())
    storageMode = OptionsConfigItem(
        "BitTorrent", "StorageMode", "sparse", OptionsValidator(["sparse", "allocate"]),
    )
    associateFileTypes = ConfigItem("BitTorrent", "AssociateFileTypes", False, BoolValidator())
    webTrackerSources = ConfigItem(
        "BitTorrent", "WebTrackerSources", [DEFAULT_WEB_TRACKER_SOURCE], StringListValidator(),
    )
    webTrackerSourceCache = ConfigItem(
        "BitTorrent", "WebTrackerSourceCache", {}, SourceCacheValidator(), SourceCacheSerializer(),
    )
    webTrackerCustomList = ConfigItem("BitTorrent", "WebTrackerCustomList", "")

    def settingGroups(self, parent: QWidget) -> list[CollapsibleSettingCardGroup]:
        import sys
        from qfluentwidgets import ComboBoxSettingCard, FluentIcon, RangeSettingCard, SwitchSettingCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup
        from app.view.components.setting_cards import SpinBoxSettingCard
        from .web_tracker.card import WebTrackerCard

        btGroup = CollapsibleSettingCardGroup(self.tr("BitTorrent 下载"), "bittorrent", parent)

        cards = []
        if sys.platform != "darwin":
            cards.append(SwitchSettingCard(
                FluentIcon.LINK, self.tr("关联 .torrent 文件"),
                self.tr("把 .torrent 文件的打开方式设为 Ghost Downloader"),
                self.associateFileTypes, btGroup,
            ))
        cards += [
            SpinBoxSettingCard(FluentIcon.GLOBE, self.tr("监听端口"),
                self.tr("0 表示交给系统自动分配可用端口"), "", self.listenPort, btGroup, 1),
            SpinBoxSettingCard(FluentIcon.HISTORY, self.tr("元数据超时"),
                self.tr("解析 magnet 链接时等待元数据的最长时间"), " s", self.metadataTimeout, btGroup, 5),
            RangeSettingCard(self.maxConnections, FluentIcon.PEOPLE, self.tr("连接数上限"),
                self.tr("单个 BT 任务对应 session 的最大连接数"), btGroup),
            SpinBoxSettingCard(FluentIcon.SHARE, self.tr("上传限速"),
                self.tr("0 表示不限速，单位为 session 级别的 KB/s"), " KB/s",
                self.maxUploadSpeed, btGroup, 64, 1 / 1024),
            SpinBoxSettingCard(FluentIcon.SHARE, self.tr("自动暂停做种分享率"),
                self.tr("0 表示不按分享率自动暂停，100% 表示分享率 1.0"), " %",
                self.seedingRatioLimit, btGroup, 50),
            SpinBoxSettingCard(FluentIcon.STOP_WATCH, self.tr("自动暂停做种时长"),
                self.tr("0 表示不按做种时长自动暂停"), " min",
                self.seedingTimeLimit, btGroup, 10),
            ComboBoxSettingCard(self.storageMode, FluentIcon.SAVE, self.tr("文件分配模式"),
                self.tr("稀疏分配更省磁盘写入，预分配更容易提前暴露空间不足"),
                texts=[self.tr("稀疏分配"), self.tr("预分配")], parent=btGroup),
            SwitchSettingCard(FluentIcon.SAVE, self.tr("保存 Magnet 种子文件"),
                self.tr("下载 magnet 链接时额外保存 .torrent 文件"), self.saveMagnetFile, btGroup),
            SwitchSettingCard(FluentIcon.LIBRARY, self.tr("顺序下载"),
                self.tr("按文件顺序下载，适合边下边看但通常会影响整体效率"),
                self.enableSequentialDownload, btGroup),
            SwitchSettingCard(FluentIcon.GLOBE, self.tr("启用 DHT"),
                self.tr("允许通过 DHT 网络发现 peers"), self.enableDht, btGroup),
            SwitchSettingCard(FluentIcon.HOME, self.tr("启用 LSD"),
                self.tr("在局域网中广播并发现同一 torrent 的 peers"), self.enableLsd, btGroup),
            SwitchSettingCard(FluentIcon.LINK, self.tr("启用 Web Tracker"),
                self.tr("把配置好的额外 Trackers 合并到新建 BT 任务中"),
                self.enableWebTrackers, btGroup),
            SwitchSettingCard(FluentIcon.SYNC, self.tr("新建任务时刷新 Web Tracker"),
                self.tr("创建新的 BT 任务时先从源地址拉取最新 Tracker"),
                self.autoRefreshWebTrackers, btGroup),
            WebTrackerCard(self._services.coroutineRunner, btGroup),
        ]
        btGroup.addSettingCards(cards)
        return [btGroup]


bittorrentConfig = BitTorrentConfig()
