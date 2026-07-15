from __future__ import annotations

import ast
import platform
import sys
from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP as N
from PySide6.QtWidgets import QWidget
from qfluentwidgets import BoolValidator, ConfigItem, FluentIcon, FolderValidator, OptionsConfigItem, OptionsValidator

from app.config.paths import APP_DATA_DIR
from app.models.pack import BinaryRuntime, PackConfig
from app.platform.android import IS_ANDROID
from app.platform.filesystem import findExecutable

PYPI_API = "https://pypi.org/pypi/yt-dlp/json"
QJS_RELEASE_BASE = "https://github.com/quickjs-ng/quickjs/releases/latest/download"


class YtDlpConfig(PackConfig):
    installFolder = ConfigItem("YtDlp", "InstallFolder", f"{APP_DATA_DIR}/YtDlp", FolderValidator())
    loginBrowser = OptionsConfigItem(
        "YtDlp", "LoginBrowser", "",
        OptionsValidator(["", "chrome", "firefox", "edge", "safari"]),
    )
    subtitleLanguages = ConfigItem("YtDlp", "SubtitleLanguages", "en")
    shouldPreferMp4 = ConfigItem("YtDlp", "PreferMp4", True, BoolValidator())
    shouldEmbedMetadata = ConfigItem("YtDlp", "EmbedMetadata", True, BoolValidator())
    shouldEmbedChapters = ConfigItem("YtDlp", "EmbedChapters", True, BoolValidator())

    def settingGroups(self, parent: QWidget) -> list:
        from qfluentwidgets import ComboBoxSettingCard, FluentIcon, SwitchSettingCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup
        from app.view.components.setting_cards import SelectFolderSettingCard, RuntimeCard

        group = CollapsibleSettingCardGroup(self.tr("YouTube 下载"), "ytdlp", parent)

        runtimeCard = RuntimeCard(youTubeRuntime, group)
        cards = [runtimeCard]

        if not IS_ANDROID:
            installFolderCard = SelectFolderSettingCard(
                ytDlpConfig.installFolder, f"{APP_DATA_DIR}/YtDlp",
                self.tr("运行环境安装目录"),
                group,
            )
            installFolderCard.pathChanged.connect(runtimeCard._onInstallFolderChanged)
            cards.insert(0, installFolderCard)

            cards.append(ComboBoxSettingCard(
                self.loginBrowser,
                FluentIcon.PEOPLE,
                self.tr("登录浏览器"),
                self.tr("从指定浏览器读取 YouTube 登录状态，用于下载需要登录的内容"),
                texts=[self.tr("不使用"), "Chrome", "Firefox", "Edge", "Safari"],
                parent=group,
            ))

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
    name = "YouTube 运行环境"
    canInstall = True
    title = N("BinaryRuntime", "YouTube 下载")
    description = N("BinaryRuntime", "支持 YouTube、Twitter 等数百个视频网站")
    icon = FluentIcon.GLOBE
    isRecommended = True

    def path(self) -> str:
        folder = Path(ytDlpConfig.installFolder.value)
        if not (folder / "yt_dlp" / "__init__.py").is_file():
            return ""
        return self.qjsPath()

    def ytDlpFolder(self) -> Path:
        return Path(ytDlpConfig.installFolder.value)

    def qjsPath(self) -> str:
        if IS_ANDROID:
            from app.platform.android import nativeLibraryDir
            binary = Path(nativeLibraryDir()) / "libqjs.so"
            return str(binary) if binary.is_file() else ""
        return findExecutable(Path(ytDlpConfig.installFolder.value), "qjs")

    async def probeVersion(self) -> str:
        ytDlpDir = Path(ytDlpConfig.installFolder.value) / "yt_dlp"
        versionFile = ytDlpDir / "version.py"
        if not versionFile.is_file():
            return ""

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

        parts = []
        if ytDlpVersion:
            parts.append(f"yt-dlp {ytDlpVersion}")
        if isQjsOk:
            parts.append("qjs ✓")
        return " | ".join(parts) if parts else ""

    async def installTask(self):
        from app.config.cfg import cfg
        from disk_pack.task import ExtractStep, InstallTask
        from http_pack.task import HttpTaskStep

        whlUrl, whlSize = await self._fetchWhlAsset()

        installFolder = Path(ytDlpConfig.installFolder.value)
        installFolder.mkdir(parents=True, exist_ok=True)
        archiveName = "yt_dlp.zip"

        if IS_ANDROID:
            task = InstallTask(
                name="yt-dlp 安装",
                url=whlUrl,
                packId="disk",
                fileSize=whlSize,
                outputFolder=installFolder,
                installFolder=str(installFolder),
            )
            task.addStep(HttpTaskStep(
                stepIndex=1,
                url=whlUrl,
                fileSize=whlSize,
                headers=dict(cfg.defaultRequestHeaders.value),
                subworkerCount=cfg.preBlockNum.value,
                canUseRangeRequests=True,
                outputFile=str(installFolder / archiveName),
            ))
            task.addStep(ExtractStep(
                stepIndex=2,
                archivePath=str(installFolder / archiveName),
                outputFolder=str(installFolder),
                archiveSize=whlSize,
            ))
            return task

        from disk_pack.task import BinaryInstallStep
        from app.models.task import TaskOptions
        from app.services.feature_service import featureService

        qjsBinaryName = "qjs.exe" if sys.platform == "win32" else "qjs"
        qjsDownload = await featureService.parse(TaskOptions(
            url=f"{QJS_RELEASE_BASE}/{_qjsAssetName()}",
            outputFolder=installFolder,
        ))
        qjsStep = qjsDownload.steps[0]
        qjsStep.stepIndex = 2
        qjsStep.outputFile = str(installFolder / qjsBinaryName)

        task = InstallTask(
            name="YouTube 运行环境安装",
            url=whlUrl,
            packId="disk",
            fileSize=whlSize + max(0, qjsDownload.fileSize),
            outputFolder=installFolder,
            installFolder=str(installFolder),
        )
        task.addStep(HttpTaskStep(
            stepIndex=1,
            url=whlUrl,
            fileSize=whlSize,
            headers=dict(cfg.defaultRequestHeaders.value),
            subworkerCount=cfg.preBlockNum.value,
            canUseRangeRequests=True,
            outputFile=str(installFolder / archiveName),
        ))
        task.addStep(qjsStep)
        task.addStep(ExtractStep(
            stepIndex=3,
            archivePath=str(installFolder / archiveName),
            outputFolder=str(installFolder),
            archiveSize=whlSize,
        ))
        task.addStep(BinaryInstallStep(
            stepIndex=4,
            binaryPath=str(installFolder / qjsBinaryName),
        ))
        return task

    async def _fetchWhlAsset(self) -> tuple[str, int]:
        from app.client import buildClient

        client = buildClient(timeout=15)
        try:
            response = await client.get(PYPI_API)
            response.raise_for_status()
            data = await response.json()
        finally:
            client.close()

        urls = data.get("urls") or []
        for entry in urls:
            if entry.get("packagetype") == "bdist_wheel" and entry.get("filename", "").endswith(".whl"):
                return entry["url"], entry.get("size") or 0
        raise RuntimeError("未找到 yt-dlp wheel 安装包")

def _qjsAssetName() -> str:
    machine = platform.machine().lower()
    if sys.platform == "win32":
        arch = "x86" if machine in {"x86", "i386", "i686"} else "x86_64"
        return f"qjs-windows-{arch}.exe"
    elif sys.platform == "darwin":
        return "qjs-darwin"
    else:
        arch = "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
        return f"qjs-linux-{arch}"


youTubeRuntime = YouTubeRuntime()
