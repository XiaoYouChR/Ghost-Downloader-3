from typing import TYPE_CHECKING

from qfluentwidgets import (
    BoolValidator,
    ComboBoxSettingCard,
    ConfigItem,
    FluentIcon,
    OptionsConfigItem,
    OptionsValidator,
    SettingCardGroup,
    SwitchSettingCard,
)

from app.bases.models import PackConfig
from .cards import createDialogCards

if TYPE_CHECKING:
    from app.view.pages.setting_page import SettingPage


class YtDlpConfig(PackConfig):
    mode = OptionsConfigItem("YtDlp", "Mode", "best_mp4", OptionsValidator(["best_mp4", "best", "audio_only"]))
    videoContainer = OptionsConfigItem("YtDlp", "VideoContainer", "mp4", OptionsValidator(["mp4", "webm", "mkv"]))
    maxHeight = OptionsConfigItem(
        "YtDlp",
        "MaxHeight",
        "best",
        OptionsValidator(["best", "2160", "1440", "1080", "720", "480", "360"]),
    )
    audioFormat = OptionsConfigItem("YtDlp", "AudioFormat", "mp3", OptionsValidator(["best", "mp3", "m4a", "opus", "wav"]))
    useCookiesFromBrowser = ConfigItem("YtDlp", "UseCookiesFromBrowser", False, BoolValidator())
    cookiesBrowser = OptionsConfigItem(
        "YtDlp",
        "CookiesBrowser",
        "chrome",
        OptionsValidator(["chrome", "edge", "firefox", "brave", "chromium"]),
    )

    def loadSettingCards(self, settingPage: "SettingPage"):
        self.group = SettingCardGroup(self.tr("yt-dlp Downloads"), settingPage.container)

        self.modeCard = ComboBoxSettingCard(
            self.mode,
            FluentIcon.VIDEO,
            self.tr("Mode"),
            self.tr("Best MP4 / Best source / Audio only"),
            texts=["Best MP4", "Best (Source)", "Audio Only"],
            parent=self.group,
        )
        self.maxHeightCard = ComboBoxSettingCard(
            self.maxHeight,
            FluentIcon.FIT_PAGE,
            self.tr("Max Height"),
            self.tr("Limit video height, Best means no limit"),
            texts=["Best", "2160p", "1440p", "1080p", "720p", "480p", "360p"],
            parent=self.group,
        )
        self.videoContainerCard = ComboBoxSettingCard(
            self.videoContainer,
            FluentIcon.DOCUMENT,
            self.tr("Container"),
            self.tr("Default output container for video modes"),
            texts=["MP4", "WEBM", "MKV"],
            parent=self.group,
        )
        self.audioFormatCard = ComboBoxSettingCard(
            self.audioFormat,
            FluentIcon.MUSIC,
            self.tr("Audio Format"),
            self.tr("Target format in audio-only mode"),
            texts=["Best", "MP3", "M4A", "Opus", "WAV"],
            parent=self.group,
        )
        self.useCookiesCard = SwitchSettingCard(
            FluentIcon.CERTIFICATE,
            self.tr("Use Browser Cookies"),
            self.tr("Avoid Cookie header warnings by reading browser cookies"),
            self.useCookiesFromBrowser,
            self.group,
        )
        self.cookiesBrowserCard = ComboBoxSettingCard(
            self.cookiesBrowser,
            FluentIcon.GLOBE,
            self.tr("Cookies Browser"),
            self.tr("Used when browser cookies are enabled"),
            texts=["Chrome", "Edge", "Firefox", "Brave", "Chromium"],
            parent=self.group,
        )

        for card in (
            self.modeCard,
            self.maxHeightCard,
            self.videoContainerCard,
            self.audioFormatCard,
            self.useCookiesCard,
            self.cookiesBrowserCard,
        ):
            self.group.addSettingCard(card)

        settingPage.vBoxLayout.addWidget(self.group)

    def getDialogCards(self, parent):
        return createDialogCards(
            parent,
            {
                "ytdlpMode": self.mode.value,
                "ytdlpMaxHeight": self.maxHeight.value,
                "ytdlpVideoContainer": self.videoContainer.value,
                "ytdlpAudioFormat": self.audioFormat.value,
                "ytdlpUseCookiesFromBrowser": self.useCookiesFromBrowser.value,
                "ytdlpCookiesBrowser": self.cookiesBrowser.value,
            },
        )


ytdlpConfig = YtDlpConfig()
