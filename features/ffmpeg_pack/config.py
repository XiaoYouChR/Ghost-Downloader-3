from __future__ import annotations

import asyncio
import platform
import sys
from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP as N
from qfluentwidgets import FluentIcon

from app.config.cfg import ConfigItem
from app.config.paths import APP_DATA_DIR
from app.models.pack import BinaryRuntime, PackConfig
from app.models.task import Task
from app.platform.android import IS_ANDROID, nativeLibraryDir
from app.platform.filesystem import findExecutable


RELEASE_BASE = "https://github.com/XiaoYouChR/Ghost-Downloader-FFmpeg"


def ffmpegAssetTarget() -> str:
    machine = platform.machine().lower()
    isArm = machine in {"arm64", "aarch64"}
    if sys.platform == "win32":
        return "winarm64" if isArm else "win64"
    if sys.platform == "darwin":
        return "macos-arm64" if isArm else "macos-x64"
    if sys.platform == "linux":
        return "linux-arm64" if isArm else "linux-x64"
    raise RuntimeError(f"当前平台暂不支持一键安装 FFmpeg: {sys.platform}")


class FFmpegConfig(PackConfig):
    installFolder = ConfigItem("FFmpeg", "InstallFolder", f"{APP_DATA_DIR}/FFmpeg")

    def settingGroups(self, parent: QWidget) -> list[CollapsibleSettingCardGroup]:
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup
        from app.view.components.setting_cards import SelectFolderSettingCard

        ffmpegGroup = CollapsibleSettingCardGroup(self.tr("FFmpeg"), "ffmpeg", parent)
        installFolderCard = SelectFolderSettingCard(
            ffmpegConfig.installFolder, f"{APP_DATA_DIR}/FFmpeg",
            self.tr("FFmpeg 安装目录"),
            ffmpegGroup,
        )
        runtimeCard = self.createRuntimeCard(ffmpegRuntime, ffmpegGroup)

        installFolderCard.pathChanged.connect(runtimeCard._onInstallFolderChanged)
        ffmpegGroup.addSettingCards([installFolderCard, runtimeCard])
        runtimeCard.refreshStatus()
        return [ffmpegGroup]


ffmpegConfig = FFmpegConfig()


class FFmpegRuntime(BinaryRuntime):
    name = "FFmpeg"
    canInstall = not IS_ANDROID
    title = N("BinaryRuntime", "视频合并")
    description = N("BinaryRuntime", "哔哩哔哩、YouTube 等网站视频下载必备，合并音视频轨道为完整文件")
    icon = FluentIcon.VIDEO
    isRecommended = True

    def path(self) -> str:
        if IS_ANDROID:
            nativeDir = nativeLibraryDir()
            if not nativeDir:
                return ""
            binary = Path(nativeDir) / "libffmpeg.so"
            return str(binary) if binary.exists() else ""
        return findExecutable(Path(ffmpegConfig.installFolder.value), "ffmpeg", "bin")

    def ffprobePath(self) -> str:
        if IS_ANDROID:
            nativeDir = nativeLibraryDir()
            if not nativeDir:
                return ""
            binary = Path(nativeDir) / "libffprobe.so"
            return str(binary) if binary.exists() else ""
        return findExecutable(Path(ffmpegConfig.installFolder.value), "ffprobe", "bin")

    async def probeVersion(self) -> str:
        path = self.path()
        if not path:
            return ""
        process = await asyncio.create_subprocess_exec(
            path, "-version",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            return ""
        line = stdout.decode("utf-8", errors="ignore").splitlines()[0].strip()
        return line.removeprefix("ffmpeg version ").split(" Copyright", 1)[0].strip() or line

    async def installTask(self) -> Task:
        from app.models.task import BinaryInstallOptions

        target = ffmpegAssetTarget()
        extension = "zip" if sys.platform == "win32" else "tar.gz"
        url = f"{RELEASE_BASE}/releases/latest/download/ffmpeg-{target}.{extension}"
        executableNames = (
            ("ffmpeg.exe", "ffprobe.exe") if sys.platform == "win32"
            else ("ffmpeg", "ffprobe")
        )
        return await self.parse(BinaryInstallOptions(
            url=url,
            outputFolder=Path(ffmpegConfig.installFolder.value),
            name=f"FFmpeg 安装 ({target})",
            executableNames=executableNames,
            sha256Url=f"{url}.sha256",
        ))


ffmpegRuntime = FFmpegRuntime()
