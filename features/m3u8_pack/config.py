from __future__ import annotations

import platform
import sys
from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP as N
from qfluentwidgets import (
    BoolValidator,
    ConfigItem,
    FluentIcon,
    FolderValidator,
    OptionsConfigItem,
    OptionsValidator,
    RangeConfigItem,
    RangeValidator,
)

from app.config.paths import APP_DATA_DIR
from app.models.pack import BinaryRuntime, PackConfig
from app.models.task import Task
from app.platform.android import IS_ANDROID, nativeLibraryDir
from app.platform.filesystem import findExecutable

RELEASE_TAG = "v0.6.0-beta"
RELEASE_DATE = "20260629"
RELEASE_BASE = f"https://github.com/nilaoda/N_m3u8DL-RE/releases/download/{RELEASE_TAG}"


class M3U8Config(PackConfig):
    installFolder = ConfigItem("M3U8", "InstallFolder", f"{APP_DATA_DIR}/M3U8DL", FolderValidator())
    associateFileTypes = ConfigItem("M3U8", "AssociateFileTypes", False, BoolValidator())
    outputFormat = OptionsConfigItem("M3U8", "OutputFormat", "mp4", OptionsValidator(["mp4", "mkv"]))
    threadCount = RangeConfigItem("M3U8", "ThreadCount", 8, RangeValidator(1, 64))
    retryCount = RangeConfigItem("M3U8", "RetryCount", 3, RangeValidator(0, 20))
    requestTimeout = RangeConfigItem("M3U8", "RequestTimeout", 100, RangeValidator(5, 600))
    shouldAutoSelect = ConfigItem("M3U8", "AutoSelect", True, BoolValidator())
    shouldConcurrentDownload = ConfigItem("M3U8", "ConcurrentDownload", True, BoolValidator())
    shouldAppendUrlParams = ConfigItem("M3U8", "AppendUrlParams", False, BoolValidator())
    shouldBinaryMerge = ConfigItem("M3U8", "BinaryMerge", False, BoolValidator())
    shouldCheckSegmentsCount = ConfigItem("M3U8", "CheckSegmentsCount", True, BoolValidator())
    shouldKeepLiveSegments = ConfigItem("M3U8", "LiveKeepSegments", False, BoolValidator())
    shouldUseLivePipeMux = ConfigItem("M3U8", "LivePipeMux", False, BoolValidator())
    shouldFixLiveVtt = ConfigItem("M3U8", "LiveFixVtt", False, BoolValidator())
    liveWaitTime = RangeConfigItem("M3U8", "LiveWaitTime", 0, RangeValidator(0, 100000))
    liveTakeCount = RangeConfigItem("M3U8", "LiveTakeCount", 0, RangeValidator(0, 1000))
    decryptionEngine = OptionsConfigItem(
        "M3U8", "DecryptionEngine", "FFmpeg",
        OptionsValidator(["FFmpeg", "MP4Decrypt", "Shaka Packager"]),
    )
    decryptionBinaryPath = ConfigItem("M3U8", "DecryptionBinaryPath", "")
    shouldUseMp4RealTimeDecryption = ConfigItem("M3U8", "MP4RealTimeDecryption", True, BoolValidator())
    maxSpeed = RangeConfigItem("M3U8", "MaxSpeed", -1, RangeValidator(-1, 1000000))
    speedUnit = OptionsConfigItem("M3U8", "SpeedUnit", "Mbps", OptionsValidator(["Mbps", "Kbps"]))
    adKeyword = ConfigItem("M3U8", "AdKeyword", "")
    subtitleFormat = OptionsConfigItem("M3U8", "SubtitleFormat", "SRT", OptionsValidator(["SRT", "VTT"]))
    shouldOmitDateInfo = ConfigItem("M3U8", "NoDateInfo", False, BoolValidator())
    shouldKeepImageSegments = ConfigItem("M3U8", "KeepImageSegments", False, BoolValidator())
    shouldDeleteTemp = ConfigItem("M3U8", "DelAfterDone", True, BoolValidator())
    customMuxAfterDone = ConfigItem("M3U8", "CustomMuxAfterDone", "")
    shouldSelectAllAudioSubtitle = ConfigItem("M3U8", "SelectAllAudioSubtitle", True, BoolValidator())

    def settingGroups(self, parent: QWidget) -> list[CollapsibleSettingCardGroup]:
        import sys
        from qfluentwidgets import ComboBoxSettingCard, FluentIcon, RangeSettingCard, SwitchSettingCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup
        from app.view.components.setting_cards import (
            SelectFolderSettingCard, LineEditSettingCard, RuntimeCard, SelectFileCard, SpinBoxSettingCard,
        )

        m3u8Group = CollapsibleSettingCardGroup(self.tr("M3U8 下载"), "m3u8", parent)
        installFolderCard = SelectFolderSettingCard(
            self.installFolder, f"{APP_DATA_DIR}/M3U8DL",
            self.tr("N_m3u8DL-RE 安装目录"),
            m3u8Group,
        )
        runtimeCard = RuntimeCard(m3u8Runtime, m3u8Group)

        cards = [installFolderCard, runtimeCard]
        if sys.platform != "darwin":
            cards.append(SwitchSettingCard(
                FluentIcon.LINK, self.tr("关联 M3U8/MPD 文件"),
                self.tr("把 .m3u8/.m3u/.mpd 文件的打开方式设为 Ghost Downloader"),
                self.associateFileTypes, m3u8Group,
            ))
        cards += [
            ComboBoxSettingCard(self.outputFormat, FluentIcon.VIDEO, self.tr("输出容器"),
                self.tr("点播下载完成后优先使用 ffmpeg 混流为指定容器"), texts=["MP4", "MKV"], parent=m3u8Group),
            RangeSettingCard(self.threadCount, FluentIcon.CLOUD, self.tr("分片线程数"),
                self.tr("传给 N_m3u8DL-RE 的下载线程数"), m3u8Group),
            RangeSettingCard(self.retryCount, FluentIcon.SYNC, self.tr("分片重试次数"),
                self.tr("单个分片下载失败时的最大重试次数"), m3u8Group),
            SpinBoxSettingCard(FluentIcon.HISTORY, self.tr("请求超时"), self.tr("HTTP 请求超时时间"),
                " s", self.requestTimeout, m3u8Group, 5),
            SwitchSettingCard(FluentIcon.ACCEPT, self.tr("自动选择最佳轨道"),
                self.tr("默认选择最佳音视频轨道"), self.shouldAutoSelect, m3u8Group),
            SwitchSettingCard(FluentIcon.PAUSE, self.tr("并发下载音视频"),
                self.tr("同时下载已选择的音频、视频和字幕轨道"), self.shouldConcurrentDownload, m3u8Group),
            SwitchSettingCard(FluentIcon.LINK, self.tr("追加 URL 参数"),
                self.tr("把输入链接上的 Query 参数追加到分片请求"), self.shouldAppendUrlParams, m3u8Group),
            SwitchSettingCard(FluentIcon.ALIGNMENT, self.tr("二进制合并"),
                self.tr("让 N_m3u8DL-RE 使用二进制方式合并分片"), self.shouldBinaryMerge, m3u8Group),
            SwitchSettingCard(FluentIcon.SEARCH, self.tr("校验分片数量"),
                self.tr("下载完成后检查实际分片数是否与预期一致"), self.shouldCheckSegmentsCount, m3u8Group),
            SwitchSettingCard(FluentIcon.SAVE, self.tr("直播保留原始分片"),
                self.tr("实时合并录制时仍保留下载的原始分片"), self.shouldKeepLiveSegments, m3u8Group),
            SwitchSettingCard(FluentIcon.CODE, self.tr("直播管道混流"),
                self.tr("录制时通过管道交给 ffmpeg 实时混流为封装容器"), self.shouldUseLivePipeMux, m3u8Group),
            SwitchSettingCard(FluentIcon.FONT, self.tr("直播校正 VTT 字幕"),
                self.tr("根据音频起始时间校正 VTT 字幕时间轴"), self.shouldFixLiveVtt, m3u8Group),
            SpinBoxSettingCard(FluentIcon.STOP_WATCH, self.tr("直播刷新等待时间"),
                self.tr("两次拉取直播清单之间的等待秒数，0 为自动"), " s", self.liveWaitTime, m3u8Group, 1),
            SpinBoxSettingCard(FluentIcon.DOWNLOAD, self.tr("直播每次取片数"),
                self.tr("每次刷新最多取走的分片数量，0 为自动"), "", self.liveTakeCount, m3u8Group, 1),
            ComboBoxSettingCard(self.decryptionEngine, FluentIcon.CERTIFICATE, self.tr("解密引擎"),
                self.tr("调用的第三方解密程序"), texts=["FFmpeg", "MP4Decrypt", "Shaka Packager"], parent=m3u8Group),
            SelectFileCard(FluentIcon.COMMAND_PROMPT, self.tr("解密引擎二进制路径"),
                self.tr("MP4Decrypt / Shaka Packager 可执行文件路径，留空则使用 FFmpeg"),
                configItem=self.decryptionBinaryPath, parent=m3u8Group),
            SwitchSettingCard(FluentIcon.FINGERPRINT, self.tr("MP4 实时解密"),
                self.tr("下载 MP4 分片时实时解密"), self.shouldUseMp4RealTimeDecryption, m3u8Group),
            SpinBoxSettingCard(FluentIcon.SPEED_HIGH, self.tr("限速"),
                self.tr("最大下载速度，-1 为不限速"), "", self.maxSpeed, m3u8Group, 1),
            ComboBoxSettingCard(self.speedUnit, FluentIcon.TAG, self.tr("限速单位"),
                self.tr("限速数值的单位"), texts=["Mbps", "Kbps"], parent=m3u8Group),
            LineEditSettingCard(FluentIcon.REMOVE, self.tr("广告过滤"),
                self.tr("匹配广告分片 URL 的正则表达式"), self.adKeyword, m3u8Group, placeholder=self.tr("正则表达式")),
            ComboBoxSettingCard(self.subtitleFormat, FluentIcon.DICTIONARY, self.tr("字幕格式"),
                self.tr("字幕输出格式"), texts=["SRT", "VTT"], parent=m3u8Group),
            SwitchSettingCard(FluentIcon.DATE_TIME, self.tr("不写入日期信息"),
                self.tr("混流时不写入日期信息"), self.shouldOmitDateInfo, m3u8Group),
            SwitchSettingCard(FluentIcon.PHOTO, self.tr("保留图形分片"),
                self.tr("把图形字幕转图片后保留原始分片"), self.shouldKeepImageSegments, m3u8Group),
            SwitchSettingCard(FluentIcon.DELETE, self.tr("完成后删除临时文件"),
                self.tr("下载完成后删除分片临时目录"), self.shouldDeleteTemp, m3u8Group),
            SwitchSettingCard(FluentIcon.MUSIC, self.tr("下载全部音轨与字幕"),
                self.tr("默认拉取全部音频与字幕轨道"), self.shouldSelectAllAudioSubtitle, m3u8Group),
            LineEditSettingCard(FluentIcon.VIDEO, self.tr("自定义混流参数"),
                self.tr("自定义 --mux-after-done，留空则按输出容器自动混流"),
                self.customMuxAfterDone, m3u8Group, placeholder="format=mp4"),
        ]
        m3u8Group.addSettingCards(cards)
        installFolderCard.pathChanged.connect(runtimeCard._onInstallFolderChanged)
        runtimeCard.refreshStatus()
        return [m3u8Group]


m3u8Config = M3U8Config()


class M3U8Runtime(BinaryRuntime):
    name = "N_m3u8DL-RE"
    canInstall = not IS_ANDROID
    title = N("BinaryRuntime", "M3U8 / 直播下载")
    description = N("BinaryRuntime", "支持 HLS、DASH 等流媒体协议，可录制直播流")
    icon = FluentIcon.MEDIA
    isRecommended = True

    def path(self) -> str:
        if IS_ANDROID:
            nativeDir = nativeLibraryDir()
            if not nativeDir:
                return ""
            binary = Path(nativeDir) / "libnm3u8dlre.so"
            return str(binary) if binary.exists() else ""
        return findExecutable(Path(m3u8Config.installFolder.value), "N_m3u8DL-RE")

    async def installTask(self) -> Task:
        machine = platform.machine().lower()
        if sys.platform == "win32":
            if machine in {"amd64", "x86_64"}:
                target = "win-x64"
            elif machine in {"arm64", "aarch64"}:
                target = "win-arm64"
            else:
                target = "win-NT6.0-x86"
        elif sys.platform == "darwin":
            target = "osx-arm64" if machine in {"arm64", "aarch64"} else "osx-x64"
        elif sys.platform == "linux":
            target = "linux-arm64" if machine in {"arm64", "aarch64"} else "linux-x64"
        else:
            raise RuntimeError(f"当前平台暂不支持一键安装 N_m3u8DL-RE: {sys.platform}")

        from app.services.feature_service import featureService
        from app.models.task import BinaryInstallOptions

        extension = "zip" if sys.platform == "win32" else "tar.gz"
        assetName = f"N_m3u8DL-RE_{RELEASE_TAG}_{target}_{RELEASE_DATE}.{extension}"
        binaryName = "N_m3u8DL-RE.exe" if sys.platform == "win32" else "N_m3u8DL-RE"
        return await featureService.parse(BinaryInstallOptions(
            url=f"{RELEASE_BASE}/{assetName}",
            outputFolder=Path(m3u8Config.installFolder.value),
            name=f"N_m3u8DL-RE 安装 ({target})",
            executableNames=(binaryName,),
        ))


m3u8Runtime = M3U8Runtime()
