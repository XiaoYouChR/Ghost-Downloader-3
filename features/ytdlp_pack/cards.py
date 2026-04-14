from typing import Any

from qfluentwidgets import CheckBox, ComboBox, FluentIcon

from app.view.components.cards import ParseSettingCard


class YtDlpModeCard(ParseSettingCard):
    def initCustomWidget(self):
        self.modeCombo = ComboBox(self)
        self.modeCombo.addItem("Best MP4", userData="best_mp4")
        self.modeCombo.addItem("Best (Source)", userData="best")
        self.modeCombo.addItem("Audio Only", userData="audio_only")
        self.modeCombo.currentIndexChanged.connect(lambda _: self.payloadChanged.emit())
        self.hBoxLayout.addWidget(self.modeCombo)

    @property
    def payload(self) -> dict[str, Any]:
        return {"ytdlpMode": self.modeCombo.currentData()}


class YtDlpMaxHeightCard(ParseSettingCard):
    def initCustomWidget(self):
        self.heightCombo = ComboBox(self)
        self.heightCombo.addItem("Best", userData="best")
        self.heightCombo.addItem("2160p", userData="2160")
        self.heightCombo.addItem("1440p", userData="1440")
        self.heightCombo.addItem("1080p", userData="1080")
        self.heightCombo.addItem("720p", userData="720")
        self.heightCombo.addItem("480p", userData="480")
        self.heightCombo.addItem("360p", userData="360")
        self.heightCombo.currentIndexChanged.connect(lambda _: self.payloadChanged.emit())
        self.hBoxLayout.addWidget(self.heightCombo)

    @property
    def payload(self) -> dict[str, Any]:
        return {"ytdlpMaxHeight": self.heightCombo.currentData()}


class YtDlpAudioCard(ParseSettingCard):
    def initCustomWidget(self):
        self.audioCombo = ComboBox(self)
        self.audioCombo.addItem("Best", userData="best")
        self.audioCombo.addItem("MP3", userData="mp3")
        self.audioCombo.addItem("M4A", userData="m4a")
        self.audioCombo.addItem("Opus", userData="opus")
        self.audioCombo.addItem("WAV", userData="wav")

        self.cookieCheck = CheckBox(self.tr("Cookies from browser"), self)

        self.audioCombo.currentIndexChanged.connect(lambda _: self.payloadChanged.emit())
        self.cookieCheck.stateChanged.connect(lambda _: self.payloadChanged.emit())

        self.hBoxLayout.addWidget(self.audioCombo)
        self.hBoxLayout.addSpacing(12)
        self.hBoxLayout.addWidget(self.cookieCheck)

    @property
    def payload(self) -> dict[str, Any]:
        return {
            "ytdlpAudioFormat": self.audioCombo.currentData(),
            "ytdlpUseCookiesFromBrowser": self.cookieCheck.isChecked(),
        }


class YtDlpVideoContainerCard(ParseSettingCard):
    def initCustomWidget(self):
        self.containerCombo = ComboBox(self)
        self.containerCombo.addItem("MP4", userData="mp4")
        self.containerCombo.addItem("WEBM", userData="webm")
        self.containerCombo.addItem("MKV", userData="mkv")
        self.containerCombo.currentIndexChanged.connect(lambda _: self.payloadChanged.emit())
        self.hBoxLayout.addWidget(self.containerCombo)

    @property
    def payload(self) -> dict[str, Any]:
        return {"ytdlpVideoContainer": self.containerCombo.currentData()}


def createDialogCards(parent=None, defaults: dict[str, Any] | None = None) -> list[ParseSettingCard]:
    defaults = defaults or {}
    modeCard = YtDlpModeCard(FluentIcon.VIDEO, "Mode (yt-dlp)", parent)
    heightCard = YtDlpMaxHeightCard(FluentIcon.FIT_PAGE, "Max Height (yt-dlp)", parent)
    containerCard = YtDlpVideoContainerCard(FluentIcon.DOCUMENT, "Container (yt-dlp)", parent)
    audioCard = YtDlpAudioCard(FluentIcon.MUSIC, "Audio (yt-dlp)", parent)

    modeIndex = modeCard.modeCombo.findData(defaults.get("ytdlpMode", "best_mp4"))
    if modeIndex >= 0:
        modeCard.modeCombo.setCurrentIndex(modeIndex)

    heightIndex = heightCard.heightCombo.findData(defaults.get("ytdlpMaxHeight", "best"))
    if heightIndex >= 0:
        heightCard.heightCombo.setCurrentIndex(heightIndex)

    containerIndex = containerCard.containerCombo.findData(defaults.get("ytdlpVideoContainer", "mp4"))
    if containerIndex >= 0:
        containerCard.containerCombo.setCurrentIndex(containerIndex)

    audioIndex = audioCard.audioCombo.findData(defaults.get("ytdlpAudioFormat", "mp3"))
    if audioIndex >= 0:
        audioCard.audioCombo.setCurrentIndex(audioIndex)

    audioCard.cookieCheck.setChecked(bool(defaults.get("ytdlpUseCookiesFromBrowser", False)))

    return [modeCard, heightCard, containerCard, audioCard]
