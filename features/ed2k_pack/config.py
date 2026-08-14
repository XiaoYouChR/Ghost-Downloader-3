from __future__ import annotations

import platform
import sys
from pathlib import Path

from app.config.paths import APP_DATA_DIR
from app.models.pack import BinaryRuntime, PackConfig
from app.platform.filesystem import toPosixPath
from PySide6.QtCore import QT_TRANSLATE_NOOP as N
from qfluentwidgets import ConfigItem, BoolValidator, FluentIcon, RangeConfigItem, RangeValidator

ED2K_REPO = "XiaoYouChR/Python-eD2k"


class ED2kConfig(PackConfig):
    associateUriSchemes = ConfigItem("ED2k", "AssociateUriSchemes", False, BoolValidator())
    installFolder = ConfigItem("ED2k", "InstallFolder", f"{APP_DATA_DIR}/goed2kd")
    enableDht = ConfigItem("ED2k", "EnableDHT", True, BoolValidator())
    enableUpnp = ConfigItem("ED2k", "EnableUPnP", True, BoolValidator())
    listenPort = RangeConfigItem("ED2k", "ListenPort", 0, RangeValidator(0, 65535))
    serverMetSource = ConfigItem("ED2k", "ServerMetSource", "http://upd.emule-security.org/server.met")
    nodesDatSource = ConfigItem("ED2k", "NodesDatSource", "http://upd.emule-security.org/nodes.dat")

    def settingGroups(self, parent: QWidget) -> list[CollapsibleSettingCardGroup]:
        from qfluentwidgets import FluentIcon, SwitchSettingCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup
        from app.view.components.setting_cards import (
            LineEditSettingCard, SelectFolderSettingCard, SpinBoxSettingCard,
        )

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
            LineEditSettingCard(
                FluentIcon.GLOBE, self.tr("服务器列表源"),
                self.tr("eD2k server.met 文件的 URL，留空则不引导"),
                self.serverMetSource, group,
            ),
            LineEditSettingCard(
                FluentIcon.GLOBE, self.tr("DHT 节点源"),
                self.tr("KAD nodes.dat 文件的 URL，留空则不引导"),
                self.nodesDatSource, group,
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
        ])
        runtimeCard.refreshStatus()
        return [group]


ed2kConfig = ED2kConfig()


class ED2kRuntime(BinaryRuntime):
    name = "goed2kd"
    canInstall = True
    title = N("BinaryRuntime", "eD2k / eMule")
    description = N("BinaryRuntime", "支持电驴协议，适合下载经典资源")
    icon = FluentIcon.BOOK_SHELF

    def installFolder(self) -> Path:
        return Path(ed2kConfig.installFolder.value)

    async def fetchLatestVersion(self) -> str:
        from app.sources import fetchLatestTag
        tag, _ = await fetchLatestTag(ED2K_REPO)
        return tag

    async def createInstallTask(self):
        from app.install import FetchStep, InstallTask
        from app.sources import buildDownloadUrl, fetchLatestTag
        from .task import ED2kInstallStep

        tag, source = await fetchLatestTag(ED2K_REPO)
        assetName = _assetName()
        url = buildDownloadUrl(ED2K_REPO, tag, assetName, source=source)
        folder = self.installFolder()
        binaryName = "goed2kd.exe" if sys.platform == "win32" else "goed2kd"
        binaryPath = toPosixPath(folder / binaryName)

        task = InstallTask(
            name=f"goed2kd 安装 ({assetName})",
            url=url,
            packId="ed2k",
            fileSize=0,
            outputFolder=folder,
            installFolder=str(folder),
        )
        task.addStep(FetchStep(stepIndex=1, url=url, outputFile=binaryPath))
        task.addStep(ED2kInstallStep(stepIndex=2, binaryPath=binaryPath))
        return task


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
