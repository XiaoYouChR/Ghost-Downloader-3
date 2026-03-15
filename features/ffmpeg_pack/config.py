import asyncio
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QStandardPaths, Qt, Signal
from PySide6.QtWidgets import QFileDialog
from qfluentwidgets import (
    ConfigItem,
    ConfigValidator,
    FluentIcon,
    FolderValidator,
    SettingCard,
    SettingCardGroup,
    ToolButton, PrimaryPushButton, InfoBar, ToolTipFilter
)

from app.bases.models import PackConfig
from app.services.core_service import coreService
from app.supports.config import cfg

if TYPE_CHECKING:
    from app.view.pages.setting_page import SettingPage
    from app.view.windows.main_window import MainWindow


class ExecutablePathValidator(ConfigValidator):
    def validate(self, value) -> bool:
        return isinstance(value, str)

    def correct(self, value) -> str:
        if not isinstance(value, str):
            return ""
        return str(Path(value)).replace("\\", "/") if value else ""


def _executableName(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


def _guessInstallRoot(ffmpegPath: str) -> str:
    path = Path(ffmpegPath)
    if path.parent.name.lower() == "bin":
        return str(path.parent.parent).replace("\\", "/")
    return str(path.parent).replace("\\", "/")


def _resolveExecutable(name: str, configuredPath: str) -> str:
    path = Path(configuredPath)
    if configuredPath and path.is_file():
        return str(path).replace("\\", "/")

    installFolder = Path(ffmpegConfig.installFolder.value)
    for candidate in (installFolder / "bin" / _executableName(name), installFolder / _executableName(name)):
        if candidate.is_file():
            return str(candidate).replace("\\", "/")

    found = shutil.which(name)
    return str(found).replace("\\", "/") if found else ""


def resolveFFmpegExecutables() -> tuple[str, str]:
    ffmpegPath = _resolveExecutable("ffmpeg", ffmpegConfig.ffmpegPath.value)
    ffprobePath = _resolveExecutable("ffprobe", ffmpegConfig.ffprobePath.value)
    return ffmpegPath, ffprobePath


def setPreferredFFmpegExecutables(ffmpegPath: str, ffprobePath: str):
    cfg.set(ffmpegConfig.ffmpegPath, ffmpegPath)
    cfg.set(ffmpegConfig.ffprobePath, ffprobePath)


async def queryFFmpegRuntime() -> dict[str, str]:
    ffmpegPath, ffprobePath = resolveFFmpegExecutables()
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
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await process.communicate()
    if process.returncode != 0:
        return runtimeInfo

    firstLine = stdout.decode("utf-8", errors="ignore").splitlines()
    versionLine = firstLine[0].strip() if firstLine else ""
    version = versionLine.removeprefix("ffmpeg version ").split(" Copyright", 1)[0].strip()
    runtimeInfo["version"] = version or versionLine
    runtimeInfo["installPath"] = _guessInstallRoot(ffmpegPath)
    return runtimeInfo


class FFmpegInstallFolderCard(SettingCard):
    pathChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(FluentIcon.FOLDER, self.tr("FFmpeg 安装目录"), ffmpegConfig.installFolder.value, parent)
        self.chooseFolderButton = ToolButton(FluentIcon.FOLDER, self)
        self.restoreDefaultButton = ToolButton(FluentIcon.CANCEL, self)
        self.hBoxLayout.addWidget(self.chooseFolderButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.restoreDefaultButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.chooseFolderButton.clicked.connect(self._chooseFolder)
        self.restoreDefaultButton.clicked.connect(self._restoreDefault)
        self.chooseFolderButton.setToolTip(self.tr("浏览文件夹"))
        self.chooseFolderButton.installEventFilter(ToolTipFilter(self.chooseFolderButton))
        self.restoreDefaultButton.setToolTip(self.tr("恢复默认路径"))
        self.restoreDefaultButton.installEventFilter(ToolTipFilter(self.restoreDefaultButton))

    def _updatePath(self, path: str):
        cfg.set(ffmpegConfig.installFolder, path)
        # 修改安装目录时，清空安装器写入的首选路径，重新回到目录/PATH 探测逻辑
        cfg.set(ffmpegConfig.ffmpegPath, "")
        cfg.set(ffmpegConfig.ffprobePath, "")
        self.setContent(ffmpegConfig.installFolder.value)
        self.pathChanged.emit(ffmpegConfig.installFolder.value)

    def _chooseFolder(self):
        folder = QFileDialog.getExistingDirectory(self.window(), self.tr("选择 FFmpeg 安装目录"))
        if folder:
            self._updatePath(folder)

    def _restoreDefault(self):
        self._updatePath(f"{QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)}/GhostDownloader/FFmpeg")


class FFmpegRuntimeCard(SettingCard):
    def __init__(self, parent=None):
        super().__init__(FluentIcon.INFO, self.tr("当前 FFmpeg"), self.tr("正在检测 FFmpeg 运行时..."), parent)
        self.installButton = PrimaryPushButton(self.tr("一键安装"), self)
        self.refreshButton = ToolButton(FluentIcon.SYNC, self)
        self.hBoxLayout.addWidget(self.installButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.refreshButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.installButton.setVisible(sys.platform == "win32")
        self.installButton.clicked.connect(self._onInstallClicked)
        self.refreshButton.clicked.connect(self.refreshStatus)

    def refreshStatus(self):
        self.refreshButton.setEnabled(False)
        self.setContent(self.tr("正在检测 FFmpeg 运行时..."))
        coreService.runCoroutine(queryFFmpegRuntime(), self._onRuntimeLoaded)

    def _onRuntimeLoaded(self, result, error: str | None):
        self.refreshButton.setEnabled(True)
        if error:
            self.setContent(self.tr("检测 FFmpeg 运行时失败"))
            return

        runtimeInfo = result or {}
        ffmpegPath = str(runtimeInfo.get("ffmpegPath") or "").strip()
        ffprobePath = str(runtimeInfo.get("ffprobePath") or "").strip()
        version = str(runtimeInfo.get("version") or "").strip()
        installPath = str(runtimeInfo.get("installPath") or "").strip()

        if ffmpegPath and ffprobePath:
            content = self.tr("版本: {0}\n安装路径: {1}").format(version or self.tr("未知"), installPath or ffmpegPath)
        else:
            content = self.tr("未检测到可用的 ffmpeg 和 ffprobe")
        self.setContent(content)

    def _onInstallClicked(self):
        if sys.platform != "win32":
            return

        from .task import createWindowsInstallTask

        self.installButton.setEnabled(False)
        self.installButton.setText(self.tr("准备中..."))
        coreService.runCoroutine(createWindowsInstallTask(), self._onInstallTaskCreated)

    def _onInstallTaskCreated(self, result, error: str | None):
        self.installButton.setEnabled(True)
        self.installButton.setText(self.tr("一键安装"))

        mainWindow: "MainWindow" = self.window()

        if error or result is None:
            InfoBar.error(self.tr("安装 FFmpeg 失败"), error or self.tr("无法创建安装任务"), duration=-1, parent=mainWindow)
            return

        mainWindow.addTask(result)


class FFmpegConfig(PackConfig):
    installFolder = ConfigItem("FFmpeg", "InstallFolder", f"{QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)}/GhostDownloader/FFmpeg", FolderValidator())
    ffmpegPath = ConfigItem("FFmpeg", "PreferredFFmpegPath", "", ExecutablePathValidator())
    ffprobePath = ConfigItem("FFmpeg", "PreferredFFprobePath", "", ExecutablePathValidator())

    def loadSettingCards(self, settingPage: "SettingPage"):
        self.ffmpegGroup = SettingCardGroup(self.tr("FFmpeg"), settingPage.container)
        self.installFolderCard = FFmpegInstallFolderCard(self.ffmpegGroup)
        self.runtimeCard = FFmpegRuntimeCard(self.ffmpegGroup)

        self.installFolderCard.pathChanged.connect(lambda _: self.runtimeCard.refreshStatus())

        self.ffmpegGroup.addSettingCard(self.installFolderCard)
        self.ffmpegGroup.addSettingCard(self.runtimeCard)
        settingPage.vBoxLayout.addWidget(self.ffmpegGroup)

        self.runtimeCard.refreshStatus()


ffmpegConfig = FFmpegConfig()
