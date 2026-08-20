from __future__ import annotations

import asyncio
import platform
import sys
from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP as N
from qfluentwidgets import FluentIcon

from app.config.cfg import ConfigItem
from app.config.paths import APP_DATA_DIR
from app.models.pack import BinaryRuntime, PackConfig, VersionInfo
from app.platform.android import IS_ANDROID, nativeLibraryDir
from app.platform.filesystem import findExecutable
from app.sources import Repo, fetchLatestRelease, probeDownloadUrl
from app.install import createInstallTask


FFMPEG_REPO = Repo("XiaoYouChR/Ghost-Downloader-FFmpeg", mirrors={"gitcode": "XiaoYouChR/Ghost-Downloader-FFmpeg"})


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

    def installFolder(self) -> Path:
        return Path(ffmpegConfig.installFolder.value)

    def path(self) -> str:
        if IS_ANDROID:
            nativeDir = nativeLibraryDir()
            if not nativeDir:
                return ""
            binary = Path(nativeDir) / "libffmpeg.so"
            return str(binary) if binary.exists() else ""
        return findExecutable(self.installFolder(), "ffmpeg", "bin")

    def ffprobePath(self) -> str:
        if IS_ANDROID:
            nativeDir = nativeLibraryDir()
            if not nativeDir:
                return ""
            binary = Path(nativeDir) / "libffprobe.so"
            return str(binary) if binary.exists() else ""
        return findExecutable(self.installFolder(), "ffprobe", "bin")

    async def probeVersion(self) -> VersionInfo:
        path = self.path()
        if not path:
            return VersionInfo("")
        versionFile = self.installFolder() / "VERSION"
        if versionFile.is_file():
            tag = versionFile.read_text().strip()
            if tag:
                return VersionInfo(tag)
        process = await asyncio.create_subprocess_exec(
            path, "-version",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            return VersionInfo("")
        line = stdout.decode("utf-8", errors="ignore").splitlines()[0].strip()
        version = line.removeprefix("ffmpeg version ").split(" Copyright", 1)[0].strip() or line
        return VersionInfo(version)

    async def fetchLatestVersion(self) -> str:
        return (await fetchLatestRelease(FFMPEG_REPO)).version

    async def createInstallTask(self, version: str = ""):
        tag = version or (await fetchLatestRelease(FFMPEG_REPO)).version
        target = ffmpegAssetTarget()
        extension = "zip" if sys.platform == "win32" else "tar.gz"
        asset = f"ffmpeg-{target}.{extension}"
        url = await probeDownloadUrl(FFMPEG_REPO, tag, asset)
        executableNames = (
            ("ffmpeg.exe", "ffprobe.exe") if sys.platform == "win32"
            else ("ffmpeg", "ffprobe")
        )
        return createInstallTask(
            url=url,
            outputFolder=self.installFolder(),
            name=f"FFmpeg 安装 ({target})",
            executableNames=executableNames,
            sha256Url=await probeDownloadUrl(FFMPEG_REPO, tag, f"{asset}.sha256"),
        )


ffmpegRuntime = FFmpegRuntime()
