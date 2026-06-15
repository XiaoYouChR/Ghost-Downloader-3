import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from qfluentwidgets import (
    ConfigItem,
    FluentIcon,
    FolderValidator,
    InfoBar,
    PrimaryPushButton,
    SettingCard,
    ToolButton,
)

from app.bases.models import PackConfig
from app.services.core_service import coreService
from app.supports.paths import APP_DATA_DIR
from app.supports.utils import findExecutable, toPosixPath
from app.view.components.setting_card_group import CollapsibleSettingCardGroup
from app.view.components.setting_cards import InstallFolderCard

if TYPE_CHECKING:
    from app.view.pages.setting_page import SettingPage
    from app.view.windows.main_window import MainWindow


def downloaderPath() -> str:
    return findExecutable(Path(ytDlpConfig.installFolder.value), "yt-dlp")


async def probeYtDlpRuntime() -> dict[str, str]:
    execPath = downloaderPath()
    info = {"downloaderPath": execPath, "version": "", "installPath": ""}
    if not execPath:
        return info

    process = await asyncio.create_subprocess_exec(
        execPath,
        "--version",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        return info

    output = stdout.decode("utf-8", errors="ignore") or stderr.decode("utf-8", errors="ignore")
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    info["version"] = lines[0] if lines else ""
    info["installPath"] = toPosixPath(Path(execPath).parent)
    return info


class YtDlpRuntimeCard(SettingCard):
    def __init__(self, parent=None):
        super().__init__(FluentIcon.INFO, self.tr("当前 yt-dlp"), self.tr("正在检测运行时..."), parent)
        self.installButton = PrimaryPushButton(self.tr("一键安装"), self)
        self.refreshButton = ToolButton(FluentIcon.SYNC, self)

        self._initLayout()
        self._bind()

    def _initLayout(self):
        self.hBoxLayout.addWidget(self.installButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.refreshButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _bind(self):
        self.installButton.clicked.connect(self._onInstallClicked)
        self.refreshButton.clicked.connect(self.refreshStatus)

    def refreshStatus(self):
        self.refreshButton.setEnabled(False)
        self.setContent(self.tr("正在检测运行时..."))
        coreService.runCoroutine(probeYtDlpRuntime(), self._onRuntimeLoaded)

    def _onRuntimeLoaded(self, result, error: str | None):
        self.refreshButton.setEnabled(True)
        if error:
            self.setContent(self.tr("检测运行时失败"))
            return

        info = result or {}
        executablePath = info.get("downloaderPath", "")
        if executablePath:
            content = self.tr("版本: {0}\n安装路径: {1}").format(
                info.get("version") or self.tr("未知"),
                info.get("installPath") or executablePath,
            )
        else:
            content = self.tr("未检测到可用的 yt-dlp")
        self.setContent(content)

    def _onInstallClicked(self):
        from .pack import createInstallTask

        self.installButton.setEnabled(False)
        self.installButton.setText(self.tr("准备中..."))
        coreService.runCoroutine(createInstallTask(), self._onInstallTaskCreated)

    def _onInstallTaskCreated(self, result, error: str | None):
        self.installButton.setEnabled(True)
        self.installButton.setText(self.tr("一键安装"))

        mainWindow: "MainWindow" = self.window()
        if error or result is None:
            InfoBar.error(self.tr("安装 yt-dlp 失败"), error or self.tr("无法创建安装任务"), duration=-1, parent=mainWindow)
            return

        mainWindow.addTask(result)


class YtDlpConfig(PackConfig):
    installFolder = ConfigItem("YtDlp", "InstallFolder", f"{APP_DATA_DIR}/YtDlp", FolderValidator())

    def setupSettings(self, settingPage: "SettingPage"):
        self.group = CollapsibleSettingCardGroup(self.tr("YouTube 下载"), "ytdlp", settingPage.container)
        self.installFolderCard = InstallFolderCard(
            self.installFolder,
            f"{APP_DATA_DIR}/YtDlp",
            self.tr("yt-dlp 安装目录"),
            self.tr("选择 yt-dlp 安装目录"),
            self.group,
        )
        self.runtimeCard = YtDlpRuntimeCard(self.group)
        self.group.addSettingCards([
            self.installFolderCard,
            self.runtimeCard,
        ])

        self.installFolderCard.pathChanged.connect(lambda _: self.runtimeCard.refreshStatus())
        settingPage.addSettingGroup(self.group)
        self.runtimeCard.refreshStatus()


ytDlpConfig = YtDlpConfig()
