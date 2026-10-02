from __future__ import annotations

import ast
import platform
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from app.config.cfg import BoolValidator, ConfigItem, FolderValidator
from app.i18n import N

from app.config.paths import APP_DATA_DIR
from app.models.pack import BinaryRuntime, PackConfig, VersionInfo
from app.platform.android import IS_ANDROID
from app.platform.filesystem import findExecutable
from app.models.task import TaskError
from app.install import installArchive, installFile
from app.sources import Repo, fetchLatestRelease, fetchPypiFile, fetchPypiReleases, fetchReleaseAsset
from app.update import parseVersion

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

QJS_REPO = Repo("quickjs-ng/quickjs", mirrors={"gitcode": "XiaoYouChR/quickjs-mirror"})
COOKIE_DOMAIN = ".youtube.com"
AUTH_COOKIE_NAMES = ("LOGIN_INFO", "SAPISID", "__Secure-1PAPISID", "__Secure-3PAPISID")


def cookieFile() -> Path:
    return APP_DATA_DIR / "YtDlp" / "cookies.txt"


def hasCookieFile() -> bool:
    path = cookieFile()
    return path.is_file() and path.stat().st_size > 0


def saveCookies(cookieString: str) -> None:
    lines = ["# Netscape HTTP Cookie File"]
    for pair in cookieString.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, _, value = pair.partition("=")
        lines.append(f"{COOKIE_DOMAIN}\tTRUE\t/\tTRUE\t0\t{name.strip()}\t{value.strip()}")
    path = cookieFile()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def saveCookiesIfBetter(cookieString: str) -> None:
    if any(name in cookieString for name in AUTH_COOKIE_NAMES):
        saveCookies(cookieString)


def loadCookieHeader() -> str:
    path = cookieFile()
    if not path.is_file():
        return ""
    pairs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            pairs.append(f"{parts[5]}={parts[6]}")
    return "; ".join(pairs)


def clearCookies() -> None:
    path = cookieFile()
    if path.is_file():
        path.unlink()


class YtDlpConfig(PackConfig):
    installFolder = ConfigItem("YtDlp", "InstallFolder", f"{APP_DATA_DIR}/YtDlp", FolderValidator())
    subtitleLanguages = ConfigItem("YtDlp", "SubtitleLanguages", "en")
    shouldPreferMp4 = ConfigItem("YtDlp", "PreferMp4", True, BoolValidator())
    shouldEmbedMetadata = ConfigItem("YtDlp", "EmbedMetadata", True, BoolValidator())
    shouldEmbedChapters = ConfigItem("YtDlp", "EmbedChapters", True, BoolValidator())

    def settingGroups(self, parent: QWidget) -> list:
        from qfluentwidgets import FluentIcon, SwitchSettingCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup
        from app.view.components.setting_cards import SelectFolderSettingCard

        group = CollapsibleSettingCardGroup(self.tr("YouTube 下载"), "ytdlp", parent)

        runtimeCard = self.createRuntimeCard(youTubeRuntime, group)
        cards = [runtimeCard]

        if not IS_ANDROID:
            installFolderCard = SelectFolderSettingCard(
                ytDlpConfig.installFolder, f"{APP_DATA_DIR}/YtDlp",
                self.tr("运行环境安装目录"),
                group,
            )
            installFolderCard.pathChanged.connect(runtimeCard._onInstallFolderChanged)
            cards.insert(0, installFolderCard)

        from .setting_cards import CookieSettingCard
        cards.append(CookieSettingCard(group))

        cards.extend([
            SwitchSettingCard(
                FluentIcon.VIDEO,
                self.tr("优先 MP4 格式"),
                self.tr("优先选择 H.264/MP4 编码，避免输出 WebM/MKV"),
                self.shouldPreferMp4,
                group,
            ),
            SwitchSettingCard(
                FluentIcon.INFO,
                self.tr("嵌入元数据"),
                self.tr("下载完成后将标题、作者等信息嵌入文件"),
                self.shouldEmbedMetadata,
                group,
            ),
            SwitchSettingCard(
                FluentIcon.BOOK_SHELF,
                self.tr("嵌入章节"),
                self.tr("下载完成后将章节标记嵌入文件"),
                self.shouldEmbedChapters,
                group,
            ),
        ])

        group.addSettingCards(cards)
        runtimeCard.refreshStatus()
        return [group]


ytDlpConfig = YtDlpConfig()


class YouTubeRuntime(BinaryRuntime):
    name = "yt-dlp"
    canInstall = True
    title = N("BinaryRuntime", "YouTube 下载")
    description = N("BinaryRuntime", "支持 YouTube、Twitter 等数百个视频网站")
    icon = "GLOBE"
    isRecommended = True

    def installFolder(self) -> Path:
        return Path(ytDlpConfig.installFolder.value)

    def path(self) -> str:
        folder = self.installFolder()
        if not (folder / "yt_dlp" / "__init__.py").is_file():
            return ""
        return self.qjsPath()

    def isAppManaged(self) -> bool:
        return (self.installFolder() / "yt_dlp" / "__init__.py").is_file()

    def ytDlpFolder(self) -> Path:
        return self.installFolder()

    def qjsPath(self) -> str:
        if IS_ANDROID:
            from app.platform.android import nativeLibraryDir
            binary = Path(nativeLibraryDir()) / "libqjs.so"
            return str(binary) if binary.is_file() else ""
        return findExecutable(self.installFolder(), "qjs")

    async def probeVersion(self) -> VersionInfo:
        versionFile = self.installFolder() / "yt_dlp" / "version.py"
        if not versionFile.is_file():
            return VersionInfo("")

        ytDlpVersion = ""
        try:
            text = versionFile.read_text(encoding="utf-8")
            for node in ast.walk(ast.parse(text)):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "__version__":
                            if isinstance(node.value, ast.Constant):
                                ytDlpVersion = str(node.value.value)
        except Exception:
            pass

        qjsPath = self.qjsPath()
        if qjsPath:
            import asyncio
            process = await asyncio.create_subprocess_exec(
                qjsPath, "--version",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await process.communicate()
            isQjsOk = process.returncode == 0
        else:
            isQjsOk = False

        return VersionInfo(
            version=ytDlpVersion,
            detail="QuickJS ✓" if isQjsOk else "",
        )

    async def fetchLatestVersion(self) -> str:
        version, _ = await fetchNightlyWheel()
        return version

    def installedPaths(self) -> list[Path]:
        folder = self.installFolder()
        if IS_ANDROID:
            return [folder / "yt_dlp"]
        return [folder / "yt_dlp", folder / ("qjs.exe" if sys.platform == "win32" else "qjs")]

    async def install(self, version: str, onProgress) -> None:
        folder = self.installFolder()
        if not IS_ANDROID:
            qjsTag = (await fetchLatestRelease(QJS_REPO)).version
            qjsPath = folder / ("qjs.exe" if sys.platform == "win32" else "qjs")
            downloadPath = qjsPath.with_name(f"{qjsPath.name}.download")
            try:
                await fetchReleaseAsset(QJS_REPO, qjsTag, _qjsAssetName(), downloadPath)
                if sys.platform != "win32":
                    downloadPath.chmod(downloadPath.stat().st_mode | 0o755)
                installFile(downloadPath, qjsPath)
            finally:
                downloadPath.unlink(missing_ok=True)

        _, wheelUrl = await fetchNightlyWheel()
        archive = folder / "yt_dlp.whl"
        await fetchPypiFile(wheelUrl, archive, onProgress)
        await installArchive(archive, folder, subtree="yt_dlp/")


async def fetchNightlyWheel() -> tuple[str, str]:
    nightlies = {}
    for version, files in (await fetchPypiReleases("yt-dlp")).items():
        if "dev" not in version:
            continue
        wheel = next((f for f in files if f["filename"].endswith("-py3-none-any.whl") and not f.get("yanked")), None)
        if wheel:
            nightlies[parseVersion(version)] = wheel["url"]
    if not nightlies:
        raise TaskError("未找到 yt-dlp nightly")
    latest = max(nightlies)
    year, month, day, time = latest[:4]
    return f"{year}.{month:02d}.{day:02d}.{time:06d}", nightlies[latest]


def _qjsAssetName() -> str:
    machine = platform.machine().lower()
    if sys.platform == "win32":
        arch = "x86" if machine in {"x86", "i386", "i686"} else "x86_64"
        return f"qjs-windows-{arch}.exe"
    elif sys.platform == "darwin":
        return f"qjs-darwin-{machine}"
    else:
        arch = "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
        return f"qjs-linux-{arch}"


youTubeRuntime = YouTubeRuntime()
