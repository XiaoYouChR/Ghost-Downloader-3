import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
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
    SwitchSettingCard,
    ToolButton,
)

from app.bases.models import PackConfig
from app.services.core_service import coreService
from app.supports.paths import APP_DATA_DIR
from app.supports.utils import findExecutable, toPosixPath
from app.view.components.setting_card_group import CollapsibleSettingCardGroup
from app.view.components.setting_cards import InstallFolderCard, LineEditSettingCard, SelectFileCard, SpinBoxSettingCard

if TYPE_CHECKING:
    from app.view.pages.setting_page import SettingPage
    from app.view.windows.main_window import MainWindow

try:
    from ffmpeg_pack.config import ffmpegPaths
except ImportError:
    from features.ffmpeg_pack.config import ffmpegPaths


def downloaderPath() -> str:
    return findExecutable(Path(m3u8Config.installFolder.value), "N_m3u8DL-RE")


async def probeM3U8Runtime() -> dict[str, str]:
    execPath = downloaderPath()
    ffmpegPath, _ = ffmpegPaths()
    runtimeInfo = {
        "downloaderPath": execPath,
        "version": "",
        "installPath": "",
        "ffmpegPath": ffmpegPath,
    }
    if not execPath:
        return runtimeInfo

    process = await asyncio.create_subprocess_exec(
        execPath,
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
    runtimeInfo["installPath"] = toPosixPath(Path(execPath).parent)
    return runtimeInfo


class M3U8RuntimeCard(SettingCard):
    def __init__(self, parent=None):
        super().__init__(FluentIcon.INFO, self.tr("当前 N_m3u8DL-RE"), self.tr("正在检测运行时..."), parent)
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
        coreService.runCoroutine(probeM3U8Runtime(), self._onRuntimeLoaded)

    def _onRuntimeLoaded(self, result, error: str | None):
        self.refreshButton.setEnabled(True)
        if error:
            self.setContent(self.tr("检测运行时失败"))
            return

        runtimeInfo = result or {}
        executablePath = runtimeInfo.get("downloaderPath", "")
        version = runtimeInfo.get("version", "")
        installPath = runtimeInfo.get("installPath", "")
        ffmpegPath = runtimeInfo.get("ffmpegPath", "")

        if executablePath:
            ffmpegText = ffmpegPath if ffmpegPath else self.tr("未检测到，部分流可能无法自动混流")
            content = self.tr("版本: {0}\n安装路径: {1}\nFFmpeg: {2}").format(
                version or self.tr("未知"),
                installPath or executablePath,
                ffmpegText,
            )
        else:
            content = self.tr("未检测到可用的 N_m3u8DL-RE")
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
            InfoBar.error(self.tr("安装 N_m3u8DL-RE 失败"), error or self.tr("无法创建安装任务"), duration=-1, parent=mainWindow)
            return

        mainWindow.addTask(result)


class M3U8Config(PackConfig):
    installFolder = ConfigItem(
        "M3U8",
        "InstallFolder",
        f"{APP_DATA_DIR}/M3U8DL",
        FolderValidator(),
    )
    associateFileTypes = ConfigItem("M3U8", "AssociateFileTypes", False, BoolValidator())

    outputFormat = OptionsConfigItem("M3U8", "OutputFormat", "mp4", OptionsValidator(["mp4", "mkv"]))
    threadCount = RangeConfigItem("M3U8", "ThreadCount", 8, RangeValidator(1, 64))
    retryCount = RangeConfigItem("M3U8", "RetryCount", 3, RangeValidator(0, 20))
    requestTimeout = RangeConfigItem("M3U8", "RequestTimeout", 100, RangeValidator(5, 600))
    autoSelect = ConfigItem("M3U8", "AutoSelect", True, BoolValidator())
    concurrentDownload = ConfigItem("M3U8", "ConcurrentDownload", True, BoolValidator())
    appendUrlParams = ConfigItem("M3U8", "AppendUrlParams", False, BoolValidator())
    binaryMerge = ConfigItem("M3U8", "BinaryMerge", False, BoolValidator())
    checkSegmentsCount = ConfigItem("M3U8", "CheckSegmentsCount", True, BoolValidator())

    # 直播（real-time-merge 对直播恒开，不设开关）
    liveKeepSegments = ConfigItem("M3U8", "LiveKeepSegments", False, BoolValidator())
    livePipeMux = ConfigItem("M3U8", "LivePipeMux", False, BoolValidator())
    liveFixVtt = ConfigItem("M3U8", "LiveFixVtt", False, BoolValidator())
    liveWaitTime = RangeConfigItem("M3U8", "LiveWaitTime", 0, RangeValidator(0, 100000))
    liveTakeCount = RangeConfigItem("M3U8", "LiveTakeCount", 0, RangeValidator(0, 1000))

    decryptionEngine = OptionsConfigItem(
        "M3U8", "DecryptionEngine", "FFmpeg",
        OptionsValidator(["FFmpeg", "MP4Decrypt", "Shaka Packager"]),
    )
    decryptionBinaryPath = ConfigItem("M3U8", "DecryptionBinaryPath", "")
    mp4RealTimeDecryption = ConfigItem("M3U8", "MP4RealTimeDecryption", True, BoolValidator())

    maxSpeed = RangeConfigItem("M3U8", "MaxSpeed", -1, RangeValidator(-1, 1000000))
    speedUnit = OptionsConfigItem("M3U8", "SpeedUnit", "Mbps", OptionsValidator(["Mbps", "Kbps"]))
    adKeyword = ConfigItem("M3U8", "AdKeyword", "")
    subtitleFormat = OptionsConfigItem("M3U8", "SubtitleFormat", "SRT", OptionsValidator(["SRT", "VTT"]))
    noDateInfo = ConfigItem("M3U8", "NoDateInfo", False, BoolValidator())
    keepImageSegments = ConfigItem("M3U8", "KeepImageSegments", False, BoolValidator())
    delAfterDone = ConfigItem("M3U8", "DelAfterDone", True, BoolValidator())
    customMuxAfterDone = ConfigItem("M3U8", "CustomMuxAfterDone", "")
    selectAllAudioSubtitle = ConfigItem("M3U8", "SelectAllAudioSubtitle", True, BoolValidator())

    settingsTitle = "流媒体下载"

    def settingsSchema(self) -> list[dict]:
        # 普通设置全进 schema；一键安装/运行时检测是交互流程（单独补）。combo 选项 value==label 的直接取串。
        def combo(label, key, item, options):
            return {"kind": "combo", "label": label, "key": key, "value": item.value,
                    "options": [{"label": o, "value": o} for o in options]}

        def switch(label, key, item):
            return {"kind": "switch", "label": label, "key": key, "value": item.value}

        def number(label, key, item, low, high):
            return {"kind": "int", "label": label, "key": key, "value": item.value, "min": low, "max": high}

        binary = downloaderPath()
        return [
            {"kind": "status", "label": "N_m3u8DL-RE",
             "value": (f"已检测到 @ {binary}" if binary else "未检测到——点下方一键安装")},
            {"kind": "action", "label": "一键安装 N_m3u8DL-RE", "actionId": "install"},
            {"kind": "folder", "label": "N_m3u8DL-RE 安装目录", "key": "installFolder", "value": self.installFolder.value},
            switch("关联 M3U8/MPD 文件", "associateFileTypes", self.associateFileTypes),
            combo("输出容器", "outputFormat", self.outputFormat, ["mp4", "mkv"]),
            number("分片线程数", "threadCount", self.threadCount, 1, 64),
            number("分片重试次数", "retryCount", self.retryCount, 0, 20),
            number("请求超时(秒)", "requestTimeout", self.requestTimeout, 5, 600),
            switch("自动选择最佳轨道", "autoSelect", self.autoSelect),
            switch("并发下载音视频", "concurrentDownload", self.concurrentDownload),
            switch("下载全部音轨与字幕", "selectAllAudioSubtitle", self.selectAllAudioSubtitle),
            switch("追加 URL 参数", "appendUrlParams", self.appendUrlParams),
            switch("二进制合并", "binaryMerge", self.binaryMerge),
            switch("校验分片数量", "checkSegmentsCount", self.checkSegmentsCount),
            switch("完成后删除临时文件", "delAfterDone", self.delAfterDone),
            combo("字幕格式", "subtitleFormat", self.subtitleFormat, ["SRT", "VTT"]),
            combo("解密引擎", "decryptionEngine", self.decryptionEngine, ["FFmpeg", "MP4Decrypt", "Shaka Packager"]),
            {"kind": "text", "label": "解密引擎二进制路径", "key": "decryptionBinaryPath", "value": self.decryptionBinaryPath.value,
             "placeholder": "留空则用 FFmpeg"},
            switch("MP4 实时解密", "mp4RealTimeDecryption", self.mp4RealTimeDecryption),
            number("限速(-1 不限)", "maxSpeed", self.maxSpeed, -1, 1000000),
            combo("限速单位", "speedUnit", self.speedUnit, ["Mbps", "Kbps"]),
            {"kind": "text", "label": "广告过滤(正则)", "key": "adKeyword", "value": self.adKeyword.value, "placeholder": "正则表达式"},
            switch("不写入日期信息", "noDateInfo", self.noDateInfo),
            switch("保留图形分片", "keepImageSegments", self.keepImageSegments),
            {"kind": "text", "label": "自定义混流参数", "key": "customMuxAfterDone", "value": self.customMuxAfterDone.value,
             "placeholder": "format=mp4"},
            switch("直播保留原始分片", "liveKeepSegments", self.liveKeepSegments),
            switch("直播管道混流", "livePipeMux", self.livePipeMux),
            switch("直播校正 VTT 字幕", "liveFixVtt", self.liveFixVtt),
            number("直播刷新等待时间(秒,0 自动)", "liveWaitTime", self.liveWaitTime, 0, 100000),
            number("直播每次取片数(0 自动)", "liveTakeCount", self.liveTakeCount, 0, 1000),
        ]

    def setupSettings(self, settingPage: "SettingPage"):
        self.m3u8Group = CollapsibleSettingCardGroup(self.tr("流媒体下载"), "m3u8", settingPage.container)
        self.installFolderCard = InstallFolderCard(
            self.installFolder,
            f"{APP_DATA_DIR}/M3U8DL",
            self.tr("N_m3u8DL-RE 安装目录"),
            self.tr("选择 N_m3u8DL-RE 安装目录"),
            self.m3u8Group,
        )
        self.runtimeCard = M3U8RuntimeCard(self.m3u8Group)

        cards = [self.installFolderCard, self.runtimeCard]
        # macOS 的文件关联在构建时烘进 Info.plist, 运行时开关无意义, 不创建也不显示
        if sys.platform != "darwin":
            cards.append(SwitchSettingCard(
                FluentIcon.LINK,
                self.tr("关联 M3U8/MPD 文件"),
                self.tr("把 .m3u8/.m3u/.mpd 文件的打开方式设为 Ghost Downloader"),
                self.associateFileTypes,
                self.m3u8Group,
            ))
        cards += [
            ComboBoxSettingCard(
                self.outputFormat, FluentIcon.VIDEO, self.tr("输出容器"),
                self.tr("点播下载完成后优先使用 ffmpeg 混流为指定容器"),
                texts=["MP4", "MKV"], parent=self.m3u8Group,
            ),
            RangeSettingCard(
                self.threadCount, FluentIcon.CLOUD, self.tr("分片线程数"),
                self.tr("传给 N_m3u8DL-RE 的下载线程数"), self.m3u8Group,
            ),
            RangeSettingCard(
                self.retryCount, FluentIcon.SYNC, self.tr("分片重试次数"),
                self.tr("单个分片下载失败时的最大重试次数"), self.m3u8Group,
            ),
            SpinBoxSettingCard(
                FluentIcon.HISTORY, self.tr("请求超时"), self.tr("HTTP 请求超时时间"),
                " s", self.requestTimeout, self.m3u8Group, 5,
            ),
            SwitchSettingCard(
                FluentIcon.ACCEPT, self.tr("自动选择最佳轨道"),
                self.tr("默认选择最佳音视频轨道，避免每个链接都手动挑选"),
                self.autoSelect, self.m3u8Group,
            ),
            SwitchSettingCard(
                FluentIcon.PAUSE, self.tr("并发下载音视频"),
                self.tr("同时下载已选择的音频、视频和字幕轨道"),
                self.concurrentDownload, self.m3u8Group,
            ),
            SwitchSettingCard(
                FluentIcon.LINK, self.tr("追加 URL 参数"),
                self.tr("把输入链接上的 Query 参数追加到分片请求"),
                self.appendUrlParams, self.m3u8Group,
            ),
            SwitchSettingCard(
                FluentIcon.ALIGNMENT, self.tr("二进制合并"),
                self.tr("让 N_m3u8DL-RE 使用二进制方式合并分片"),
                self.binaryMerge, self.m3u8Group,
            ),
            SwitchSettingCard(
                FluentIcon.SEARCH, self.tr("校验分片数量"),
                self.tr("下载完成后检查实际分片数是否与预期一致"),
                self.checkSegmentsCount, self.m3u8Group,
            ),
            SwitchSettingCard(
                FluentIcon.SAVE, self.tr("直播保留原始分片"),
                self.tr("实时合并录制时仍保留下载的原始分片"),
                self.liveKeepSegments, self.m3u8Group,
            ),
            SwitchSettingCard(
                FluentIcon.CODE, self.tr("直播管道混流"),
                self.tr("录制时通过管道交给 ffmpeg 实时混流为封装容器"),
                self.livePipeMux, self.m3u8Group,
            ),
            SwitchSettingCard(
                FluentIcon.FONT, self.tr("直播校正 VTT 字幕"),
                self.tr("根据音频起始时间校正 VTT 字幕时间轴"),
                self.liveFixVtt, self.m3u8Group,
            ),
            SpinBoxSettingCard(
                FluentIcon.STOP_WATCH, self.tr("直播刷新等待时间"),
                self.tr("两次拉取直播清单之间的等待秒数，0 为自动"),
                " s", self.liveWaitTime, self.m3u8Group, 1,
            ),
            SpinBoxSettingCard(
                FluentIcon.DOWNLOAD, self.tr("直播每次取片数"),
                self.tr("每次刷新最多取走的分片数量，0 为自动"),
                "", self.liveTakeCount, self.m3u8Group, 1,
            ),
            ComboBoxSettingCard(
                self.decryptionEngine, FluentIcon.CERTIFICATE, self.tr("解密引擎"),
                self.tr("调用的第三方解密程序"),
                texts=["FFmpeg", "MP4Decrypt", "Shaka Packager"], parent=self.m3u8Group,
            ),
            SelectFileCard(
                self.decryptionBinaryPath, FluentIcon.COMMAND_PROMPT, self.tr("解密引擎二进制路径"),
                self.tr("MP4Decrypt / Shaka Packager 可执行文件路径，留空则使用 FFmpeg"),
                self.tr("选择解密引擎可执行文件"), self.m3u8Group,
            ),
            SwitchSettingCard(
                FluentIcon.FINGERPRINT, self.tr("MP4 实时解密"),
                self.tr("下载 MP4 分片时实时解密"),
                self.mp4RealTimeDecryption, self.m3u8Group,
            ),
            SpinBoxSettingCard(
                FluentIcon.SPEED_HIGH, self.tr("限速"),
                self.tr("最大下载速度，-1 为不限速"),
                "", self.maxSpeed, self.m3u8Group, 1,
            ),
            ComboBoxSettingCard(
                self.speedUnit, FluentIcon.TAG, self.tr("限速单位"),
                self.tr("限速数值的单位"), texts=["Mbps", "Kbps"], parent=self.m3u8Group,
            ),
            LineEditSettingCard(
                FluentIcon.REMOVE, self.tr("广告过滤"),
                self.tr("匹配广告分片 URL 的正则表达式"),
                self.adKeyword, self.m3u8Group, placeholder=self.tr("正则表达式"),
            ),
            ComboBoxSettingCard(
                self.subtitleFormat, FluentIcon.DICTIONARY, self.tr("字幕格式"),
                self.tr("字幕输出格式"), texts=["SRT", "VTT"], parent=self.m3u8Group,
            ),
            SwitchSettingCard(
                FluentIcon.DATE_TIME, self.tr("不写入日期信息"),
                self.tr("混流时不写入日期信息"), self.noDateInfo, self.m3u8Group,
            ),
            SwitchSettingCard(
                FluentIcon.PHOTO, self.tr("保留图形分片"),
                self.tr("把图形字幕转图片后保留原始分片"),
                self.keepImageSegments, self.m3u8Group,
            ),
            SwitchSettingCard(
                FluentIcon.DELETE, self.tr("完成后删除临时文件"),
                self.tr("下载完成后删除分片临时目录"), self.delAfterDone, self.m3u8Group,
            ),
            SwitchSettingCard(
                FluentIcon.MUSIC, self.tr("下载全部音轨与字幕"),
                self.tr("默认拉取全部音频与字幕轨道，而非仅最佳"),
                self.selectAllAudioSubtitle, self.m3u8Group,
            ),
            LineEditSettingCard(
                FluentIcon.VIDEO, self.tr("自定义混流参数"),
                self.tr("自定义 --mux-after-done，留空则按输出容器自动混流"),
                self.customMuxAfterDone, self.m3u8Group, placeholder="format=mp4",
            ),
        ]
        self.m3u8Group.addSettingCards(cards)

        self.installFolderCard.pathChanged.connect(lambda _: self.runtimeCard.refreshStatus())
        settingPage.addSettingGroup(self.m3u8Group)
        self.runtimeCard.refreshStatus()


m3u8Config = M3U8Config()
