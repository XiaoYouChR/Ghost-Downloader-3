import asyncio
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication
from qfluentwidgets import (
    ConfigItem,
    FluentIcon,
    FolderValidator,
    InfoBar,
    InfoBarPosition,
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


def _linuxInstallCommand() -> str:
    """检测可用包管理器；都没命中时 fallback 到 apt 命令文本（让用户自行替换）。"""
    candidates = (
        ("apt", "sudo apt install ffmpeg"),
        ("dnf", "sudo dnf install ffmpeg"),
        ("pacman", "sudo pacman -S ffmpeg"),
        ("zypper", "sudo zypper install ffmpeg"),
        ("apk", "sudo apk add ffmpeg"),
    )
    return next((cmd for pm, cmd in candidates if shutil.which(pm)), candidates[0][1])


def ffmpegPaths() -> tuple[str, str]:
    installFolder = Path(ffmpegConfig.installFolder.value)
    return (
        findExecutable(installFolder, "ffmpeg", "bin"),
        findExecutable(installFolder, "ffprobe", "bin"),
    )


async def probeFFmpegRuntime() -> dict[str, str]:
    ffmpegPath, ffprobePath = ffmpegPaths()
    runtimeInfo = {
        "ffmpegPath": ffmpegPath,
        "ffprobePath": ffprobePath,
        "version": "",
        "installPath": "",
    }
    if not ffmpegPath or not ffprobePath:
        return runtimeInfo

    process = await asyncio.create_subprocess_exec(
        ffmpegPath,
        "-version",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await process.communicate()
    if process.returncode != 0:
        return runtimeInfo

    lines = stdout.decode("utf-8", errors="ignore").splitlines()
    versionLine = lines[0].strip() if lines else ""
    version = versionLine.removeprefix("ffmpeg version ").split(" Copyright", 1)[0].strip()
    runtimeInfo["version"] = version or versionLine
    binPath = Path(ffmpegPath)
    installRoot = binPath.parent.parent if binPath.parent.name.lower() == "bin" else binPath.parent
    runtimeInfo["installPath"] = toPosixPath(installRoot)
    return runtimeInfo


class FFmpegRuntimeCard(SettingCard):
    def __init__(self, parent=None):
        super().__init__(FluentIcon.INFO, self.tr("当前 FFmpeg"), self.tr("正在检测 FFmpeg 运行时..."), parent)
        self.installButton = PrimaryPushButton(self)
        self.refreshButton = ToolButton(FluentIcon.SYNC, self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self):
        if sys.platform == "win32":
            self.installButton.setText(self.tr("一键安装"))
            self._installAction = self._downloadFFmpeg
        elif sys.platform == "darwin" and not shutil.which("brew"):
            self.installButton.setText(self.tr("打开 brew.sh"))
            self._installAction = lambda: QDesktopServices.openUrl(QUrl("https://brew.sh"))
        else:
            command = "brew install ffmpeg" if sys.platform == "darwin" else _linuxInstallCommand()
            self.installButton.setText(self.tr("复制安装命令"))
            self._installAction = lambda: self._copyCommand(command)

    def _initLayout(self):
        self.hBoxLayout.addWidget(self.installButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.refreshButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _bind(self):
        self.installButton.clicked.connect(self._installAction)
        self.refreshButton.clicked.connect(self.refreshStatus)

    def refreshStatus(self):
        self.refreshButton.setEnabled(False)
        self.setContent(self.tr("正在检测 FFmpeg 运行时..."))
        coreService.runCoroutine(probeFFmpegRuntime(), self._onRuntimeLoaded)

    def _onRuntimeLoaded(self, result, error: str | None):
        self.refreshButton.setEnabled(True)
        if error:
            self.setContent(self.tr("检测 FFmpeg 运行时失败"))
            return

        runtimeInfo = result or {}
        ffmpegPath = runtimeInfo.get("ffmpegPath", "")
        ffprobePath = runtimeInfo.get("ffprobePath", "")
        if ffmpegPath and ffprobePath:
            version = runtimeInfo.get("version", "")
            installPath = runtimeInfo.get("installPath", "")
            self.setContent(self.tr("版本: {0}\n安装路径: {1}").format(version or self.tr("未知"), installPath or ffmpegPath))
        else:
            self.setContent(self.tr("未检测到可用的 ffmpeg 和 ffprobe"))

    def _downloadFFmpeg(self):
        from .pack import createInstallTask
        self.installButton.setEnabled(False)
        self.installButton.setText(self.tr("准备中..."))
        coreService.runCoroutine(createInstallTask(), self._onInstallTaskCreated)

    def _copyCommand(self, command: str):
        QApplication.clipboard().setText(command)
        InfoBar.success(
            self.tr("已复制安装命令"), command,
            duration=2000, position=InfoBarPosition.BOTTOM_RIGHT, parent=self.window(),
        )

    def _onInstallTaskCreated(self, result, error: str | None):
        self.installButton.setEnabled(True)
        self.installButton.setText(self.tr("一键安装"))

        mainWindow: "MainWindow" = self.window()
        if error or result is None:
            InfoBar.error(self.tr("安装 FFmpeg 失败"), error or self.tr("无法创建安装任务"), duration=-1, parent=mainWindow)
            return
        mainWindow.addTask(result)


class FFmpegConfig(PackConfig):
    installFolder = ConfigItem("FFmpeg", "InstallFolder", f"{APP_DATA_DIR}/FFmpeg", FolderValidator())

    settingsTitle = "FFmpeg"

    def settingsSchema(self) -> list[dict]:
        # 安装目录是普通设置；运行时检测只读显；一键安装是交互流程，后续单独补
        ffmpeg, _ = ffmpegPaths()
        return [
            {"kind": "status", "label": "FFmpeg",
             "value": (f"已检测到 @ {ffmpeg}" if ffmpeg else "未检测到——部分流可能无法自动混流")},
            {"kind": "folder", "label": "FFmpeg 安装目录", "key": "installFolder", "value": self.installFolder.value},
        ]

    def setupSettings(self, settingPage: "SettingPage"):
        self.ffmpegGroup = CollapsibleSettingCardGroup(self.tr("FFmpeg"), "ffmpeg", settingPage.container)
        self.installFolderCard = InstallFolderCard(
            ffmpegConfig.installFolder,
            f"{APP_DATA_DIR}/FFmpeg",
            self.tr("FFmpeg 安装目录"),
            self.tr("选择 FFmpeg 安装目录"),
            self.ffmpegGroup,
        )
        self.runtimeCard = FFmpegRuntimeCard(self.ffmpegGroup)

        self.installFolderCard.pathChanged.connect(lambda _: self.runtimeCard.refreshStatus())

        self.ffmpegGroup.addSettingCard(self.installFolderCard)
        self.ffmpegGroup.addSettingCard(self.runtimeCard)
        settingPage.addSettingGroup(self.ffmpegGroup)

        self.runtimeCard.refreshStatus()


ffmpegConfig = FFmpegConfig()
