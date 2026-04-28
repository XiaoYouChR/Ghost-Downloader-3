# pyright: reportAny=false, reportExplicitAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportAttributeAccessIssue=false, reportImplicitOverride=false, reportCallIssue=false, reportUnusedCallResult=false, reportArgumentType=false, reportAssignmentType=false, reportUnannotatedClassAttribute=false, reportUninitializedInstanceVariable=false, reportMissingTypeStubs=false, reportMissingTypeArgument=false, reportMissingParameterType=false, reportUnnecessaryIsInstance=false, reportUnreachable=false, reportPrivateUsage=false, reportImplicitStringConcatenation=false, reportIncompatibleMethodOverride=false, reportUnknownLambdaType=false, reportImportCycles=false

import asyncio
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QStandardPaths, Qt, Signal
from PySide6.QtWidgets import QFileDialog
from qfluentwidgets import (
    BoolValidator,
    ComboBoxSettingCard,
    ConfigItem,
    FluentIcon,
    FolderValidator,
    InfoBar,
    OptionsConfigItem,
    OptionsValidator,
    PrimaryPushButton,
    RangeConfigItem,
    RangeSettingCard,
    RangeValidator,
    SettingCard,
    SettingCardGroup,
    SwitchSettingCard,
    ToolButton,
    ToolTipFilter,
)

from app.feature_pack.api import FeaturePackSettings
from app.feature_pack.api.settings import SettingItem
from app.feature_pack.api.settings import SettingSection
from app.services.core_service import coreService
from app.supports.config import cfg
from app.view.components.setting_cards import SpinBoxSettingCard

if TYPE_CHECKING:
    from app.view.pages.setting_page import SettingPage
    from app.view.windows.main_window import MainWindow

try:
    from ffmpeg_pack.config import resolveFFmpegExecutables
except ImportError:
    from features.ffmpeg_pack.config import resolveFFmpegExecutables


def _normalizePath(path: Path | str) -> str:
    return str(Path(path)).replace("\\", "/")


def _executableName(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


def _guessInstallRoot(downloaderPath: str) -> str:
    return _normalizePath(Path(downloaderPath).parent)


def _resolveExecutable() -> str:
    installFolder = Path(m3u8Config.installFolder.value)
    candidate = installFolder / _executableName("N_m3u8DL-RE")
    if candidate.is_file():
        return _normalizePath(candidate)

    found = shutil.which("N_m3u8DL-RE")
    if not found and sys.platform == "win32":
        found = shutil.which("N_m3u8DL-RE.exe")
    return _normalizePath(found) if found else ""


def resolveM3U8DownloaderExecutable() -> str:
    return _resolveExecutable()


async def queryM3U8Runtime() -> dict[str, str]:
    downloaderPath = resolveM3U8DownloaderExecutable()
    ffmpegPath, _ = resolveFFmpegExecutables()
    runtimeInfo = {
        "downloaderPath": downloaderPath,
        "version": "",
        "installPath": "",
        "ffmpegPath": ffmpegPath,
    }
    if not downloaderPath:
        return runtimeInfo

    process = await asyncio.create_subprocess_exec(
        downloaderPath,
        "--version",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        return runtimeInfo

    output = stdout.decode("utf-8", errors="ignore") or stderr.decode("utf-8", errors="ignore")
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    runtimeInfo["version"] = lines[0] if lines else ""
    runtimeInfo["installPath"] = _guessInstallRoot(downloaderPath)
    return runtimeInfo


class M3U8InstallFolderCard(SettingCard):
    pathChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(FluentIcon.FOLDER, self.tr("N_m3u8DL-RE 安装目录"), m3u8Config.installFolder.value, parent)
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
        cfg.set(m3u8Config.installFolder, path)
        self.setContent(m3u8Config.installFolder.value)
        self.pathChanged.emit(m3u8Config.installFolder.value)

    def _chooseFolder(self):
        folder = QFileDialog.getExistingDirectory(self.window(), self.tr("选择 N_m3u8DL-RE 安装目录"))
        if folder:
            self._updatePath(folder)

    def _restoreDefault(self):
        defaultPath = f"{QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)}/GhostDownloader/M3U8DL"
        self._updatePath(defaultPath)


class M3U8RuntimeCard(SettingCard):
    def __init__(self, parent=None):
        super().__init__(FluentIcon.INFO, self.tr("当前 N_m3u8DL-RE"), self.tr("正在检测运行时..."), parent)
        self.installButton = PrimaryPushButton(self.tr("一键安装"), self)
        self.refreshButton = ToolButton(FluentIcon.SYNC, self)
        self.hBoxLayout.addWidget(self.installButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.refreshButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.installButton.clicked.connect(self._onInstallClicked)
        self.refreshButton.clicked.connect(self.refreshStatus)

    def refreshStatus(self):
        self.refreshButton.setEnabled(False)
        self.setContent(self.tr("正在检测运行时..."))
        coreService.runCoroutine(queryM3U8Runtime(), self._onRuntimeLoaded)

    def _onRuntimeLoaded(self, result, error: str | None):
        self.refreshButton.setEnabled(True)
        if error:
            self.setContent(self.tr("检测运行时失败"))
            return

        runtimeInfo = result or {}
        downloaderPath = str(runtimeInfo.get("downloaderPath") or "").strip()
        version = str(runtimeInfo.get("version") or "").strip()
        installPath = str(runtimeInfo.get("installPath") or "").strip()
        ffmpegPath = str(runtimeInfo.get("ffmpegPath") or "").strip()

        if downloaderPath:
            ffmpegText = ffmpegPath if ffmpegPath else self.tr("未检测到，部分流可能无法自动混流")
            content = self.tr("版本: {0}\n安装路径: {1}\nFFmpeg: {2}").format(
                version or self.tr("未知"),
                installPath or downloaderPath,
                ffmpegText,
            )
        else:
            content = self.tr("未检测到可用的 N_m3u8DL-RE")
        self.setContent(content)

    def _onInstallClicked(self):
        from .task import createInstallTask

        self.installButton.setEnabled(False)
        self.installButton.setText(self.tr("准备中..."))
        coreService.runCoroutine(createInstallTask(), self._onInstallTaskCreated)

    def _onInstallTaskCreated(self, result, error: str | None):
        self.installButton.setEnabled(True)
        self.installButton.setText(self.tr("一键安装"))

        mainWindow: "MainWindow" = self.window()
        if error or result is None:
            InfoBar.error(self.tr("安装 N_m3u8DL-RE 失败"), error or self.tr("无法创建安装任务"), duration=-1, parent=mainWindow)
            return

        mainWindow.addTask(result)


class M3U8Config(FeaturePackSettings):
    installFolder = ConfigItem(
        "M3U8",
        "InstallFolder",
        f"{QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)}/GhostDownloader/M3U8DL",
        FolderValidator(),
    )
    outputFormat = OptionsConfigItem("M3U8", "OutputFormat", "mp4", OptionsValidator(["mp4", "mkv"]))
    threadCount = RangeConfigItem("M3U8", "ThreadCount", 8, RangeValidator(1, 64))
    retryCount = RangeConfigItem("M3U8", "RetryCount", 3, RangeValidator(0, 20))
    requestTimeout = RangeConfigItem("M3U8", "RequestTimeout", 100, RangeValidator(5, 600))
    autoSelect = ConfigItem("M3U8", "AutoSelect", True, BoolValidator())
    concurrentDownload = ConfigItem("M3U8", "ConcurrentDownload", True, BoolValidator())
    appendUrlParams = ConfigItem("M3U8", "AppendUrlParams", False, BoolValidator())
    binaryMerge = ConfigItem("M3U8", "BinaryMerge", False, BoolValidator())
    checkSegmentsCount = ConfigItem("M3U8", "CheckSegmentsCount", True, BoolValidator())
    liveRealTimeMerge = ConfigItem("M3U8", "LiveRealTimeMerge", False, BoolValidator())
    liveKeepSegments = ConfigItem("M3U8", "LiveKeepSegments", False, BoolValidator())
    livePipeMux = ConfigItem("M3U8", "LivePipeMux", False, BoolValidator())

    def _createInstallFolderCard(self, group: SettingCardGroup) -> SettingCard:
        self.installFolderCard = M3U8InstallFolderCard(group)
        return self.installFolderCard

    def _createRuntimeCard(self, group: SettingCardGroup) -> SettingCard:
        self.runtimeCard = M3U8RuntimeCard(group)
        installFolderCard = getattr(self, "installFolderCard", None)
        if isinstance(installFolderCard, M3U8InstallFolderCard):
            installFolderCard.pathChanged.connect(lambda _: self.runtimeCard.refreshStatus())
        self.runtimeCard.refreshStatus()
        return self.runtimeCard

    def _createOutputFormatCard(self, group: SettingCardGroup) -> SettingCard:
        self.outputFormatCard = ComboBoxSettingCard(
            self.outputFormat,
            FluentIcon.VIDEO,
            self.tr("输出容器"),
            self.tr("下载完成后优先使用 ffmpeg 混流为指定容器"),
            texts=["MP4", "MKV"],
            parent=group,
        )
        return self.outputFormatCard

    def _createThreadCountCard(self, group: SettingCardGroup) -> SettingCard:
        self.threadCountCard = RangeSettingCard(
            self.threadCount,
            FluentIcon.CLOUD,
            self.tr("分片线程数"),
            self.tr("传给 N_m3u8DL-RE 的下载线程数"),
            group,
        )
        return self.threadCountCard

    def _createRetryCountCard(self, group: SettingCardGroup) -> SettingCard:
        self.retryCountCard = RangeSettingCard(
            self.retryCount,
            FluentIcon.SYNC,
            self.tr("分片重试次数"),
            self.tr("单个分片下载失败时的最大重试次数"),
            group,
        )
        return self.retryCountCard

    def _createRequestTimeoutCard(self, group: SettingCardGroup) -> SettingCard:
        self.requestTimeoutCard = SpinBoxSettingCard(
            FluentIcon.HISTORY,
            self.tr("请求超时"),
            self.tr("HTTP 请求超时时间"),
            " s",
            self.requestTimeout,
            group,
            5,
        )
        return self.requestTimeoutCard

    def _createAutoSelectCard(self, group: SettingCardGroup) -> SettingCard:
        self.autoSelectCard = SwitchSettingCard(
            FluentIcon.ACCEPT,
            self.tr("自动选择最佳轨道"),
            self.tr("默认选择最佳音视频轨道，避免每个链接都手动挑选"),
            self.autoSelect,
            group,
        )
        return self.autoSelectCard

    def _createConcurrentDownloadCard(self, group: SettingCardGroup) -> SettingCard:
        self.concurrentDownloadCard = SwitchSettingCard(
            FluentIcon.PAUSE,
            self.tr("并发下载音视频"),
            self.tr("同时下载已选择的音频、视频和字幕轨道"),
            self.concurrentDownload,
            group,
        )
        return self.concurrentDownloadCard

    def _createAppendUrlParamsCard(self, group: SettingCardGroup) -> SettingCard:
        self.appendUrlParamsCard = SwitchSettingCard(
            FluentIcon.LINK,
            self.tr("追加 URL 参数"),
            self.tr("把输入链接上的 Query 参数追加到分片请求"),
            self.appendUrlParams,
            group,
        )
        return self.appendUrlParamsCard

    def _createBinaryMergeCard(self, group: SettingCardGroup) -> SettingCard:
        self.binaryMergeCard = SwitchSettingCard(
            FluentIcon.ALIGNMENT,
            self.tr("二进制合并"),
            self.tr("让 N_m3u8DL-RE 使用二进制方式合并分片"),
            self.binaryMerge,
            group,
        )
        return self.binaryMergeCard

    def _createCheckSegmentsCountCard(self, group: SettingCardGroup) -> SettingCard:
        self.checkSegmentsCountCard = SwitchSettingCard(
            FluentIcon.SEARCH,
            self.tr("校验分片数量"),
            self.tr("下载完成后检查实际分片数是否与预期一致"),
            self.checkSegmentsCount,
            group,
        )
        return self.checkSegmentsCountCard

    def _createLiveRealTimeMergeCard(self, group: SettingCardGroup) -> SettingCard:
        self.liveRealTimeMergeCard = SwitchSettingCard(
            FluentIcon.CAMERA,
            self.tr("直播实时合并"),
            self.tr("录制直播流时边下边合并"),
            self.liveRealTimeMerge,
            group,
        )
        return self.liveRealTimeMergeCard

    def _createLiveKeepSegmentsCard(self, group: SettingCardGroup) -> SettingCard:
        self.liveKeepSegmentsCard = SwitchSettingCard(
            FluentIcon.SAVE,
            self.tr("直播保留分片"),
            self.tr("实时合并直播时仍保留原始分片"),
            self.liveKeepSegments,
            group,
        )
        return self.liveKeepSegmentsCard

    def _createLivePipeMuxCard(self, group: SettingCardGroup) -> SettingCard:
        self.livePipeMuxCard = SwitchSettingCard(
            FluentIcon.CODE,
            self.tr("直播管道混流"),
            self.tr("直播实时合并时通过管道交给 ffmpeg 混流"),
            self.livePipeMux,
            group,
        )
        return self.livePipeMuxCard

    def _createSettingCards(self, group: SettingCardGroup) -> tuple[SettingCard, ...]:
        return (
            self._createInstallFolderCard(group),
            self._createRuntimeCard(group),
            self._createOutputFormatCard(group),
            self._createThreadCountCard(group),
            self._createRetryCountCard(group),
            self._createRequestTimeoutCard(group),
            self._createAutoSelectCard(group),
            self._createConcurrentDownloadCard(group),
            self._createAppendUrlParamsCard(group),
            self._createBinaryMergeCard(group),
            self._createCheckSegmentsCountCard(group),
            self._createLiveRealTimeMergeCard(group),
            self._createLiveKeepSegmentsCard(group),
            self._createLivePipeMuxCard(group),
        )

    def settingSection(self) -> SettingSection:
        return SettingSection(
            id="m3u8_pack",
            title=self.tr("流媒体下载"),
            items=(
                SettingItem(
                    key="installFolder",
                    label=self.tr("N_m3u8DL-RE 安装目录"),
                    kind="custom",
                    note=self.tr("选择 N_m3u8DL-RE 的安装位置"),
                    extra={"cardFactory": self._createInstallFolderCard},
                ),
                SettingItem(
                    key="runtime",
                    label=self.tr("当前 N_m3u8DL-RE"),
                    kind="custom",
                    note=self.tr("检测或一键安装 N_m3u8DL-RE"),
                    extra={"cardFactory": self._createRuntimeCard},
                ),
                SettingItem(
                    key="outputFormat",
                    label=self.tr("输出容器"),
                    kind="custom",
                    note=self.tr("下载完成后优先使用 ffmpeg 混流为指定容器"),
                    extra={"cardFactory": self._createOutputFormatCard},
                ),
                SettingItem(
                    key="threadCount",
                    label=self.tr("分片线程数"),
                    kind="custom",
                    note=self.tr("传给 N_m3u8DL-RE 的下载线程数"),
                    extra={"cardFactory": self._createThreadCountCard},
                ),
                SettingItem(
                    key="retryCount",
                    label=self.tr("分片重试次数"),
                    kind="custom",
                    note=self.tr("单个分片下载失败时的最大重试次数"),
                    extra={"cardFactory": self._createRetryCountCard},
                ),
                SettingItem(
                    key="requestTimeout",
                    label=self.tr("请求超时"),
                    kind="custom",
                    note=self.tr("HTTP 请求超时时间"),
                    extra={"cardFactory": self._createRequestTimeoutCard},
                ),
                SettingItem(
                    key="autoSelect",
                    label=self.tr("自动选择最佳轨道"),
                    kind="custom",
                    note=self.tr("默认选择最佳音视频轨道，避免每个链接都手动挑选"),
                    extra={"cardFactory": self._createAutoSelectCard},
                ),
                SettingItem(
                    key="concurrentDownload",
                    label=self.tr("并发下载音视频"),
                    kind="custom",
                    note=self.tr("同时下载已选择的音频、视频和字幕轨道"),
                    extra={"cardFactory": self._createConcurrentDownloadCard},
                ),
                SettingItem(
                    key="appendUrlParams",
                    label=self.tr("追加 URL 参数"),
                    kind="custom",
                    note=self.tr("把输入链接上的 Query 参数追加到分片请求"),
                    extra={"cardFactory": self._createAppendUrlParamsCard},
                ),
                SettingItem(
                    key="binaryMerge",
                    label=self.tr("二进制合并"),
                    kind="custom",
                    note=self.tr("让 N_m3u8DL-RE 使用二进制方式合并分片"),
                    extra={"cardFactory": self._createBinaryMergeCard},
                ),
                SettingItem(
                    key="checkSegmentsCount",
                    label=self.tr("校验分片数量"),
                    kind="custom",
                    note=self.tr("下载完成后检查实际分片数是否与预期一致"),
                    extra={"cardFactory": self._createCheckSegmentsCountCard},
                ),
                SettingItem(
                    key="liveRealTimeMerge",
                    label=self.tr("直播实时合并"),
                    kind="custom",
                    note=self.tr("录制直播流时边下边合并"),
                    extra={"cardFactory": self._createLiveRealTimeMergeCard},
                ),
                SettingItem(
                    key="liveKeepSegments",
                    label=self.tr("直播保留分片"),
                    kind="custom",
                    note=self.tr("实时合并直播时仍保留原始分片"),
                    extra={"cardFactory": self._createLiveKeepSegmentsCard},
                ),
                SettingItem(
                    key="livePipeMux",
                    label=self.tr("直播管道混流"),
                    kind="custom",
                    note=self.tr("直播实时合并时通过管道交给 ffmpeg 混流"),
                    extra={"cardFactory": self._createLivePipeMuxCard},
                ),
            ),
        )


m3u8Config = M3U8Config()
