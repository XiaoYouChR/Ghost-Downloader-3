from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from app.config.cfg import (
    BoolValidator, ConfigItem, RangeConfigItem, RangeValidator, StringListValidator,
)
from app.i18n import N

from app.config.paths import APP_DATA_DIR
from app.models.pack import BinaryRuntime, PackConfig
from app.platform.android import IS_ANDROID, nativeLibraryDir
from app.install import installFile
from app.platform.filesystem import findExecutable
from app.sources import Repo, fetchLatestRelease, fetchReleaseAsset

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from app.view.components.setting_card_group import CollapsibleSettingCardGroup

KELPIE_REPO = Repo("XiaoYouChR/Kelpie", mirrors={"gitcode": "XiaoYouChR/Kelpie"})
DEFAULT_SERVER_LIST_SOURCES = [
    "https://upd.emule-security.org/server.met",
    "https://shortypower.org/server.met",
    "http://www.gruk.org/server.met",
]
DEFAULT_NODE_LIST_SOURCES = ["https://upd.emule-security.org/nodes.dat"]


class ED2kConfig(PackConfig):
    associateUriSchemes = ConfigItem("ED2k", "AssociateUriSchemes", False, BoolValidator())
    installFolder = ConfigItem("ED2k", "InstallFolder", f"{APP_DATA_DIR}/kelpie")
    enableKad = ConfigItem("ED2k", "EnableKad", True, BoolValidator())
    enableUpnp = ConfigItem("ED2k", "EnableUPnP", True, BoolValidator())
    listenPort = RangeConfigItem("ED2k", "ListenPort", 0, RangeValidator(0, 65535), restart=True)
    uploadRateLimit = RangeConfigItem("ED2k", "UploadRateLimit", 0, RangeValidator(0, 1024 * 1024 * 100))
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
        from qfluentwidgets import FluentIcon, PushSettingCard, SwitchSettingCard
        from app.view.components.bootstrap_list import BootstrapListCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup
        from app.view.components.setting_cards import SelectFolderSettingCard, SpinBoxSettingCard
        from .lists import nodeList, serverList
        from .session import ed2kSession

        group = CollapsibleSettingCardGroup(self.tr("eD2k 下载"), "ed2k", parent)
        installFolderCard = SelectFolderSettingCard(
            self.installFolder, self.installFolder.defaultValue,
            self.tr("Kelpie 安装目录"),
            group,
        )
        runtimeCard = self.createRuntimeCard(kelpieRuntime, group)

        installFolderCard.pathChanged.connect(runtimeCard._onInstallFolderChanged)

        def toStopCardContent() -> str:
            if ed2kSession.network is None:
                return self.tr("未运行")
            if not ed2kSession.isIdle:
                return self.tr("有 eD2k 任务正在下载或做种，结束后才能终止")
            return self.tr("开始 eD2k 任务时会自动重新启动")

        stopCard = PushSettingCard(
            self.tr("终止"), FluentIcon.CLOSE, self.tr("终止 Kelpie 进程"), toStopCardContent(), group,
        )

        def refreshStopCard():
            stopCard.button.setEnabled(ed2kSession.network is not None and ed2kSession.isIdle)
            stopCard.setContent(toStopCardContent())

        stopCard.clicked.connect(lambda: self.submit(ed2kSession.stop()))
        ed2kSession.networkChanged.connect(refreshStopCard, owner=stopCard)
        ed2kSession.runsChanged.connect(refreshStopCard, owner=stopCard)
        refreshStopCard()

        serverListCard = BootstrapListCard(
            FluentIcon.GLOBE, self.tr("服务器列表"), serverList,
            self.serverListSources, self.submit, group, probeNetworkText=self._probeServerText,
        )
        nodeListCard = BootstrapListCard(
            FluentIcon.GLOBE, self.tr("KAD 节点列表"), nodeList,
            self.nodeListSources, self.submit, group, probeNetworkText=self._probeKadText,
        )
        for card in (serverListCard, nodeListCard):
            ed2kSession.networkChanged.connect(card.probeNetwork, owner=card)

        group.addSettingCards([
            installFolderCard,
            runtimeCard,
            SwitchSettingCard(
                FluentIcon.SYNC, self.tr("自动更新订阅"),
                self.tr("每天在后台更新一次服务器列表和 KAD 节点列表"),
                self.shouldRefreshLists, group,
            ),
            serverListCard,
            nodeListCard,
            stopCard,
            SwitchSettingCard(
                FluentIcon.WIFI, self.tr("启用 KAD"),
                self.tr("通过 KAD 网络查找来源，关闭后仅使用 eD2k 服务器"),
                self.enableKad, group,
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
                FluentIcon.SHARE, self.tr("上传限速"),
                self.tr("0 表示不限速。上传越多积分越高，在别人的队列里排得越靠前，自己下载也越快"), " KB/s",
                self.uploadRateLimit, group, 64, 1 / 1024,
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
        network = ed2kSession.network
        if network is None:
            return self.tr("未运行")
        if not network.isServerConnected:
            return self.tr("未连接服务器")
        if network.isHighId:
            return self.tr("已连接服务器（HighID）")
        if network.isBehindCarrierNat:
            return self.tr("已连接服务器（LowID，运营商 NAT，无法获得 HighID）")
        return self.tr("已连接服务器（LowID，开启 UPnP 或在路由器转发监听端口可获得 HighID）")

    async def _probeKadText(self) -> str:
        if not self.enableKad.value:
            return self.tr("KAD 已关闭")
        from .session import ed2kSession
        network = ed2kSession.network
        if network is None:
            return self.tr("未运行")
        if network.isKadFirewalled:
            return self.tr("KAD 节点 {0}（处于防火墙后）").format(network.kadNodes)
        return self.tr("KAD 节点 {0}").format(network.kadNodes)


ed2kConfig = ED2kConfig()


class KelpieRuntime(BinaryRuntime):
    name = "Kelpie"
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
            binary = Path(nativeDir) / "libkelpie.so"
            return str(binary) if binary.exists() else ""
        return findExecutable(self.installFolder(), "kelpie")

    async def fetchLatestVersion(self) -> str:
        return (await fetchLatestRelease(KELPIE_REPO)).version

    def installedPaths(self) -> list[Path]:
        return [self.installFolder() / ("kelpie.exe" if sys.platform == "win32" else "kelpie")]

    async def install(self, version: str, onProgress) -> None:
        tag = version or await self.fetchLatestVersion()
        binary = self.installedPaths()[0]
        downloadPath = binary.with_name(f"{binary.name}.download")
        try:
            await fetchReleaseAsset(KELPIE_REPO, tag, buildAssetName(), downloadPath, onProgress)
            downloadPath.chmod(0o755)
            installFile(downloadPath, binary)
        finally:
            downloadPath.unlink(missing_ok=True)


def buildAssetName() -> str:
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "amd64"
    if sys.platform == "win32":
        return f"kelpie-windows-{arch}.exe"
    elif sys.platform == "darwin":
        return f"kelpie-darwin-{arch}"
    else:
        return f"kelpie-linux-{arch}"


kelpieRuntime = KelpieRuntime()
