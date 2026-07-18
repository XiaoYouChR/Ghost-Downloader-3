from __future__ import annotations

from PySide6.QtCore import QLocale, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QFrame, QHBoxLayout, QScrollArea, QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel, CardWidget, FluentIcon, IconWidget, PrimaryPushButton,
    RadioButton, TitleLabel, isDarkTheme, qconfig,
)

from app.config.cfg import LANGUAGE_TEXTS, Language, cfg


def preferredLanguage(locale: QLocale | None = None) -> Language:
    """Choose a supported language for an Android locale, defaulting to English."""
    locale = locale or QLocale.system()
    supported = [language for language in cfg.language.options if language != Language.AUTO]

    if locale.territory() == QLocale.Country.HongKong:
        return Language.CANTONESE

    for language in supported:
        candidate = language.value
        if (
            candidate.language() == locale.language()
            and candidate.territory() == locale.territory()
        ):
            return language

    for language in supported:
        if language.value.language() == locale.language():
            return language

    return Language.ENGLISH_UNITED_STATES


class LanguageCard(CardWidget):

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.radioButton = RadioButton(text, self)
        self.setClickEnabled(True)
        self.setFixedHeight(56)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.addWidget(self.radioButton, 1)

        self.clicked.connect(lambda: self.radioButton.setChecked(True))


class MobileLanguageDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._languages = [
            language for language in cfg.language.options if language != Language.AUTO
        ]

        self.iconWidget = IconWidget(FluentIcon.LANGUAGE, self)
        self.titleLabel = TitleLabel("Choose your language", self)
        self.descriptionLabel = BodyLabel(
            "Select the language used by Ghost Downloader. You can change it "
            "later in Settings.",
            self,
        )
        self.scrollArea = QScrollArea(self)
        self.scrollWidget = QWidget(self.scrollArea)
        self.languageLayout = QVBoxLayout(self.scrollWidget)
        self.languageGroup = QButtonGroup(self)
        self.continueButton = PrimaryPushButton("Continue", self)
        self.contentWidget = QWidget(self)
        self.contentLayout = QVBoxLayout(self.contentWidget)

        self._initWidget()
        self._initLayout()
        self.continueButton.clicked.connect(self.accept)

    def _initWidget(self) -> None:
        self.setWindowTitle("Ghost Downloader")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
        self.contentWidget.setMaximumWidth(560)
        self.iconWidget.setFixedSize(42, 42)
        self.descriptionLabel.setWordWrap(True)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setWidget(self.scrollWidget)
        self.scrollArea.setFrameShape(QFrame.Shape.NoFrame)
        self.scrollArea.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scrollArea.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        self.scrollWidget.setObjectName("languageScrollWidget")
        self.scrollWidget.setStyleSheet(
            "QWidget#languageScrollWidget { background: transparent; }"
        )
        self.continueButton.setMinimumHeight(48)

        selected = (
            cfg.language.value
            if cfg.language.value != Language.AUTO
            else preferredLanguage()
        )

        for index, language in enumerate(self._languages):
            card = LanguageCard(LANGUAGE_TEXTS[language], self.scrollWidget)
            self.languageGroup.addButton(card.radioButton, index)
            self.languageLayout.addWidget(card)
            if language == selected:
                card.radioButton.setChecked(True)

        qconfig.themeChanged.connect(self.update)

    def _initLayout(self) -> None:
        self.languageLayout.setContentsMargins(4, 4, 4, 4)
        self.languageLayout.setSpacing(4)
        self.languageLayout.addStretch(1)

        self.contentLayout.setContentsMargins(24, 36, 24, 24)
        self.contentLayout.setSpacing(14)
        self.contentLayout.addWidget(self.iconWidget)
        self.contentLayout.addSpacing(6)
        self.contentLayout.addWidget(self.titleLabel)
        self.contentLayout.addWidget(self.descriptionLabel)
        self.contentLayout.addSpacing(10)
        self.contentLayout.addWidget(self.scrollArea, 1)
        self.contentLayout.addSpacing(10)
        self.contentLayout.addWidget(self.continueButton)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(
            self.contentWidget,
            1,
            Qt.AlignmentFlag.AlignHCenter,
        )

    def selectedLanguage(self) -> Language:
        index = self.languageGroup.checkedId()
        if 0 <= index < len(self._languages):
            return self._languages[index]
        return Language.ENGLISH_UNITED_STATES

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        color = QColor(32, 32, 32) if isDarkTheme() else QColor(243, 243, 243)
        painter.fillRect(self.rect(), color)
