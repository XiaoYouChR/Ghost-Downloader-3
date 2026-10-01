from __future__ import annotations

import platform
import sys
from pathlib import Path

from app.config.cfg import (
    BoolValidator, ConfigItem, RangeConfigItem, RangeValidator, StringListValidator,
)
from app.i18n import N

from app.config.paths import APP_DATA_DIR
from app.models.pack import BinaryRuntime, PackConfig
from app.platform.android import IS_ANDROID, nativeLibraryDir
from app.platform.filesystem import findExecutable
from app.sources import Repo, fetchLatestRelease, fetchReleaseAsset

ED2K_REPO = Repo("XiaoYouChR/Python-eD2k", mirrors={"gitcode": "XiaoYouChR/Python-eD2k"})
DEFAULT_SERVER_LIST_SOURCES = [
    "https://upd.emule-security.org/server.met",
    "https://shortypower.org/server.met",
    "http://www.gruk.org/server.met",
]
DEFAULT_NODE_LIST_SOURCES = ["https://upd.emule-security.org/nodes.dat"]


class ED2kConfig(PackConfig):
    associateUriSchemes = ConfigItem("ED2k", "AssociateUriSchemes", False, BoolValidator())
    installFolder = ConfigItem("ED2k", "InstallFolder", f"{APP_DATA_DIR}/goed2kd")
    enableDht = ConfigItem("ED2k", "EnableDHT", True, BoolValidator(), restart=True)
    enableUpnp = ConfigItem("ED2k", "EnableUPnP", True, BoolValidator(), restart=True)
    listenPort = RangeConfigItem("ED2k", "ListenPort", 0, RangeValidator(0, 65535), restart=True)
    serverListSources = ConfigItem(
        "ED2k", "ServerListSources", DEFAULT_SERVER_LIST_SOURCES, StringListValidator(), restart=True,
    )
    nodeListSources = ConfigItem(
        "ED2k", "NodeListSources", DEFAULT_NODE_LIST_SOURCES, StringListValidator(), restart=True,
    )
    shouldRefreshLists = ConfigItem("ED2k", "ShouldRefreshLists", True, BoolValidator())
    seedingRatioLimit = RangeConfigItem("ED2k", "SeedRatioLimitPercent", 0, RangeValidator(0, 10000))
    seedingTimeLimit = RangeConfigItem("ED2k", "SharingTimeLimitMinutes", 0, RangeValidator(0, 43200))

    def settingGroups(self, parent: QWidget) -> list[CollapsibleSettingCardGroup]:
        from qfluentwidgets import FluentIcon, SwitchSettingCard
        from app.view.components.bootstrap_list import BootstrapListCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup
        from app.view.components.setting_cards import SelectFolderSettingCard, SpinBoxSettingCard
        from .lists import nodeList, serverList

        group = CollapsibleSettingCardGroup(self.tr("eD2k 下载"), "ed2k", parent)
        installFolderCard = SelectFolderSettingCard(
            ed2kConfig.installFolder, f"{APP_DATA_DIR}/goed2kd",
            self.tr("goed2kd 安装目录"),
            group,
        )
        runtimeCard = self.createRuntimeCard(ed2kRuntime, group)

        installFolderCard.pathChanged.connect(runtimeCard._onInstallFolderChanged)
        group.addSettingCards([
            installFolderCard,
            runtimeCard,
            SwitchSettingCard(
                FluentIcon.SYNC, self.tr("自动更新订阅"),
                self.tr("每天在后台更新一次服务器列表和 KAD 节点列表"),
                self.shouldRefreshLists, group,
            ),
            BootstrapListCard(
                FluentIcon.GLOBE, self.tr("服务器列表"), serverList,
                self.serverListSources, self.submit, group,
                probeNetworkText=self._probeServerText,
            ),
            BootstrapListCard(
                FluentIcon.GLOBE, self.tr("KAD 节点列表"), nodeList,
                self.nodeListSources, self.submit, group,
                probeNetworkText=self._probeKadText,
            ),
            SwitchSettingCard(
                FluentIcon.WIFI, self.tr("启用 DHT"),
                self.tr("通过分布式哈希表查找节点，关闭后仅使用 eD2k 服务器"),
                self.enableDht, group,
            ),
            SwitchSettingCard(
                FluentIcon.GLOBE, self.tr("启用 UPnP"),
                self.tr("自动配置路由器端口转发"),
                self.enableUpnp, group,
            ),
            SpinBoxSettingCard(
                FluentIcon.LINK, self.tr("监听端口"),
                self.tr("0 表示交给系统自动分配可用端口"), "",
                self.listenPort, group, 1,
            ),
            SpinBoxSettingCard(
                FluentIcon.SHARE, self.tr("自动停止做种分享率"),
                self.tr("0 表示不按分享率自动停止，100% 表示分享率 1.0"), " %",
                self.seedingRatioLimit, group, 50,
            ),
            SpinBoxSettingCard(
                FluentIcon.STOP_WATCH, self.tr("自动停止做种时长"),
                self.tr("0 表示不按做种时长自动停止"), " min",
                self.seedingTimeLimit, group, 10,
            ),
        ])
        runtimeCard.refreshStatus()
        return [group]

    async def _probeServerText(self) -> str:
        from .session import ed2kSession
        network = await ed2kSession.probeNetwork()
        if network is None:
            return ""
        return self.tr("已连接服务器") if network.isServerConnected else self.tr("未连接服务器")

    async def _probeKadText(self) -> str:
        from .session import ed2kSession
        network = await ed2kSession.probeNetwork()
        return "" if network is None else self.tr("KAD 节点 {0}").format(network.kadNodes)


ed2kConfig = ED2kConfig()


class ED2kRuntime(BinaryRuntime):
    name = "goed2kd"
    canInstall = not IS_ANDROID
    title = N("BinaryRuntime", "eD2k / eMule")
    description = N("BinaryRuntime", "支持电驴协议，适合下载经典资源")
    icon = "BOOK_SHELF"

    def installFolder(self) -> Path:
        return Path(ed2kConfig.installFolder.value)

    def path(self) -> str:
        if IS_ANDROID:
            nativeDir = nativeLibraryDir()
            if not nativeDir:
                return ""
            binary = Path(nativeDir) / "libgoed2kd.so"
            return str(binary) if binary.exists() else ""
        return findExecutable(self.installFolder(), "goed2kd")

    async def fetchLatestVersion(self) -> str:
        return (await fetchLatestRelease(ED2K_REPO)).version

    def installedPaths(self) -> list[Path]:
        return [self.installFolder() / ("goed2kd.exe" if sys.platform == "win32" else "goed2kd")]

    async def install(self, version: str, onProgress) -> None:
        tag = version or (await fetchLatestRelease(ED2K_REPO)).version
        binaryPath = self.installedPaths()[0]
        await fetchReleaseAsset(ED2K_REPO, tag, _assetName(), binaryPath, onProgress)
        if sys.platform != "win32":
            binaryPath.chmod(binaryPath.stat().st_mode | 0o755)


def _assetName() -> str:
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "amd64"
    if sys.platform == "win32":
        return f"goed2kd-windows-{arch}.exe"
    elif sys.platform == "darwin":
        return f"goed2kd-darwin-{arch}"
    else:
        return f"goed2kd-linux-{arch}"


ed2kRuntime = ED2kRuntime()
