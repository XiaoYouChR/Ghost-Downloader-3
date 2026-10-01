from __future__ import annotations

import asyncio
import platform
import sys
from pathlib import Path

from app.i18n import N

from app.config.cfg import ConfigItem
from app.config.paths import APP_DATA_DIR
from app.models.pack import BinaryRuntime, PackConfig, VersionInfo
from app.platform.android import IS_ANDROID, nativeLibraryDir
from app.platform.filesystem import deletePath, findExecutable
from app.models.task import TaskError
from app.sources import Repo, fetchLatestRelease, fetchReleaseAsset
from app.install import installArchive, matchSha256


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
    raise TaskError("当前平台暂不支持一键安装 FFmpeg: {platform}", platform=sys.platform)


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
    icon = "VIDEO"
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
        return findExecutable(self.installFolder(), "ffmpeg")

    def ffprobePath(self) -> str:
        if IS_ANDROID:
            nativeDir = nativeLibraryDir()
            if not nativeDir:
                return ""
            binary = Path(nativeDir) / "libffprobe.so"
            return str(binary) if binary.exists() else ""
        return findExecutable(self.installFolder(), "ffprobe")

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

    def installedPaths(self) -> list[Path]:
        folder = self.installFolder()
        suffix = ".exe" if sys.platform == "win32" else ""
        return [folder / f"ffmpeg{suffix}", folder / f"ffprobe{suffix}", folder / "VERSION"]

    async def install(self, version: str, onProgress) -> None:
        tag = version or (await fetchLatestRelease(FFMPEG_REPO)).version
        extension = "zip" if sys.platform == "win32" else "tar.gz"
        asset = f"ffmpeg-{ffmpegAssetTarget()}.{extension}"
        folder = self.installFolder()
        archive = folder / asset
        sha256File = folder / f"{asset}.sha256"
        await fetchReleaseAsset(FFMPEG_REPO, tag, asset, archive, onProgress)
        await fetchReleaseAsset(FFMPEG_REPO, tag, sha256File.name, sha256File)
        isMatched = await matchSha256(archive, sha256File)
        deletePath(sha256File)
        if not isMatched:
            deletePath(archive)
            raise TaskError("安装包校验失败，可能已损坏，请重试")
        await installArchive(archive, folder)


ffmpegRuntime = FFmpegRuntime()
