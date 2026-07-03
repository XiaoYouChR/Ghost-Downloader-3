from __future__ import annotations

import platform
import sys
from pathlib import Path

from PySide6.QtWidgets import QWidget
from qfluentwidgets import BoolValidator, ConfigItem, FolderValidator, OptionsConfigItem, OptionsValidator, RangeConfigItem, RangeValidator

from app.config.paths import APP_DATA_DIR
from app.models.pack import BinaryRuntime, PackConfig
from app.models.task import Task
from app.platform.android import IS_ANDROID
from app.platform.filesystem import findExecutable


class YtDlpConfig(PackConfig):
    installFolder = ConfigItem("YtDlp", "InstallFolder", f"{APP_DATA_DIR}/YtDlp", FolderValidator())
    parallelFragments = RangeConfigItem("YtDlp", "ParallelFragments", 4, RangeValidator(1, 16))
    loginBrowser = OptionsConfigItem(
        "YtDlp", "LoginBrowser", "",
        OptionsValidator(["", "chrome", "firefox", "edge", "safari"]),
    )
    shouldPreferMp4 = ConfigItem("YtDlp", "PreferMp4", True, BoolValidator())
    subtitleLanguages = ConfigItem("YtDlp", "SubtitleLanguages", "en")
    shouldEmbedThumbnail = ConfigItem("YtDlp", "EmbedThumbnail", True, BoolValidator())
    shouldEmbedChapters = ConfigItem("YtDlp", "EmbedChapters", True, BoolValidator())
    shouldEmbedMetadata = ConfigItem("YtDlp", "EmbedMetadata", True, BoolValidator())

    def settingGroups(self, parent: QWidget) -> list:
        from qfluentwidgets import ComboBoxSettingCard, FluentIcon, SwitchSettingCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup
        from app.view.components.setting_cards import SelectFolderSettingCard, RuntimeCard, SpinBoxSettingCard

        from features.yt_dlp_pack.icons import YTIcon
        group = CollapsibleSettingCardGroup(YTIcon.YOUTUBE, self.tr("YouTube 下载"), "ytdlp", parent)
        installFolderCard = SelectFolderSettingCard(
            ytDlpConfig.installFolder, f"{APP_DATA_DIR}/YtDlp",
            self.tr("yt-dlp 安装目录"),
            group,
        )
        runtimeCard = RuntimeCard(ytDlpRuntime, group)
        installFolderCard.pathChanged.connect(runtimeCard._onInstallFolderChanged)

        group.addSettingCards([
            installFolderCard,
            runtimeCard,
            SpinBoxSettingCard(
                FluentIcon.SPEED_HIGH,
                self.tr("并行分片数"),
                self.tr("同时下载的视频分片数量，越高越快但可能被限流"),
                configItem=self.parallelFragments,
                parent=group,
            ),
            ComboBoxSettingCard(
                self.loginBrowser,
                FluentIcon.PEOPLE,
                self.tr("登录浏览器"),
                self.tr("从指定浏览器读取 YouTube 登录状态，用于下载需要登录的内容"),
                texts=[self.tr("不使用"), "Chrome", "Firefox", "Edge", "Safari"],
                parent=group,
            ),
            SwitchSettingCard(
                FluentIcon.VIDEO,
                self.tr("优先 MP4 格式"),
                self.tr("优先选择 H.264/MP4 编码，避免输出 WebM/MKV"),
                self.shouldPreferMp4,
                group,
            ),
            SwitchSettingCard(
                FluentIcon.PHOTO,
                self.tr("嵌入缩略图"),
                self.tr("下载完成后通过 FFmpeg 将封面嵌入文件"),
                self.shouldEmbedThumbnail,
                group,
            ),
            SwitchSettingCard(
                FluentIcon.BOOK_SHELF,
                self.tr("嵌入章节"),
                self.tr("下载完成后通过 FFmpeg 将章节标记嵌入文件"),
                self.shouldEmbedChapters,
                group,
            ),
            SwitchSettingCard(
                FluentIcon.INFO,
                self.tr("嵌入元数据"),
                self.tr("下载完成后通过 FFmpeg 将标题、作者等信息嵌入文件"),
                self.shouldEmbedMetadata,
                group,
            ),
        ])
        runtimeCard.refreshStatus()
        return [group]


ytDlpConfig = YtDlpConfig()


class YtDlpRuntime(BinaryRuntime):
    name = "yt-dlp"
    canInstall = not IS_ANDROID

    def path(self) -> str:
        return findExecutable(Path(ytDlpConfig.installFolder.value), "yt-dlp")

    async def installTask(self) -> Task:
        from app.services.feature_service import featureService
        from app.models.task import BinaryInstallOptions

        machine = platform.machine().lower()
        if sys.platform == "win32":
            asset = "yt-dlp.exe"
        elif sys.platform == "darwin":
            asset = "yt-dlp_macos"
        elif machine in {"arm64", "aarch64"}:
            asset = "yt-dlp_linux_aarch64"
        else:
            asset = "yt-dlp_linux"

        binaryName = "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp"
        url = f"https://github.com/yt-dlp/yt-dlp/releases/latest/download/{asset}"
        return await featureService.parse(BinaryInstallOptions(
            url=url,
            outputFolder=Path(ytDlpConfig.installFolder.value),
            name=f"yt-dlp 安装 ({asset})",
            executableNames=(binaryName,),
        ))


ytDlpRuntime = YtDlpRuntime()
