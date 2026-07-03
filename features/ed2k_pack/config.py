from __future__ import annotations

import platform
import sys
from pathlib import Path

from app.config.cfg import cfg
from app.config.paths import APP_DATA_DIR
from app.models.pack import BinaryRuntime, PackConfig
from app.platform.filesystem import findExecutable, toPosixPath
from qfluentwidgets import ConfigItem, BoolValidator, RangeConfigItem, RangeValidator

RELEASE_API = "https://api.github.com/repos/XiaoYouChR/Python-eD2k/releases/latest"
RELEASE_HEADERS = {"accept": "application/vnd.github+json"}


class ED2kConfig(PackConfig):
    installFolder = ConfigItem("ED2k", "InstallFolder", f"{APP_DATA_DIR}/goed2kd")
    enableDht = ConfigItem("ED2k", "EnableDHT", True, BoolValidator())
    enableUpnp = ConfigItem("ED2k", "EnableUPnP", True, BoolValidator())
    listenPort = RangeConfigItem("ED2k", "ListenPort", 0, RangeValidator(0, 65535))
    serverMetSource = ConfigItem("ED2k", "ServerMetSource", "")
    nodesDatSource = ConfigItem("ED2k", "NodesDatSource", "")

    def settingGroups(self, parent: QWidget) -> list[CollapsibleSettingCardGroup]:
        from qfluentwidgets import FluentIcon, SwitchSettingCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup
        from app.view.components.setting_cards import SelectFolderSettingCard, RuntimeCard, SpinBoxSettingCard

        from features.ed2k_pack.icons import ED2kIcon
        group = CollapsibleSettingCardGroup(ED2kIcon.P2P, self.tr("eD2k 下载"), "ed2k", parent)
        installFolderCard = SelectFolderSettingCard(
            ed2kConfig.installFolder, f"{APP_DATA_DIR}/goed2kd",
            self.tr("goed2kd 安装目录"),
            group,
        )
        runtimeCard = RuntimeCard(ed2kRuntime, group)

        installFolderCard.pathChanged.connect(runtimeCard._onInstallFolderChanged)
        group.addSettingCards([
            installFolderCard,
            runtimeCard,
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

    def path(self) -> str:
        return findExecutable(Path(ed2kConfig.installFolder.value), "goed2kd")

    async def installTask(self):
        from app.client import buildClient
        from app.update import Release
        from http_pack.task import HttpTaskStep
        from disk_pack.task import InstallTask
        from .task import ED2kInstallStep

        client = buildClient(headers=RELEASE_HEADERS)
        try:
            response = await client.get(RELEASE_API)
            response.raise_for_status()
            release = Release.fromResponse(await response.json())
        finally:
            client.close()

        assetName = _assetName()
        asset = next((a for a in release.assets if a.name == assetName), None)
        if asset is None:
            raise RuntimeError(f"未找到适配当前平台的 goed2kd: {assetName}")
        if not asset.downloadUrl or asset.size <= 0:
            raise RuntimeError("GitHub Release 返回了不完整的安装包信息")

        installFolder = Path(ed2kConfig.installFolder.value)
        binaryName = "goed2kd.exe" if sys.platform == "win32" else "goed2kd"
        binaryPath = toPosixPath(installFolder / binaryName)

        task = InstallTask(
            name=f"goed2kd 安装 ({assetName})",
            url=asset.downloadUrl,
            packId="ed2k",
            fileSize=asset.size,
            outputFolder=installFolder,
            installFolder=str(installFolder),
        )
        task.addStep(HttpTaskStep(
            stepIndex=1,
            url=asset.downloadUrl,
            fileSize=asset.size,
            headers=dict(cfg.defaultRequestHeaders.value),
            subworkerCount=cfg.preBlockNum.value,
            canUseRangeRequests=True,
            outputFile=binaryPath,
        ))
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
