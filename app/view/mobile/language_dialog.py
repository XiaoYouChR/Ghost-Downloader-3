from __future__ import annotations

from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout
from qfluentwidgets import BodyLabel, ComboBox, PrimaryPushButton, SubtitleLabel

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


class MobileLanguageDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._languages = [
            language for language in cfg.language.options if language != Language.AUTO
        ]

        self.titleLabel = SubtitleLabel("Choose your language / 选择语言", self)
        self.descriptionLabel = BodyLabel(
            "Select the language used by Ghost Downloader.\n"
            "请选择 Ghost Downloader 的界面语言。",
            self,
        )
        self.languageCombo = ComboBox(self)
        self.continueButton = PrimaryPushButton("Continue / 继续", self)

        self._initWidget()
        self._initLayout()
        self.continueButton.clicked.connect(self.accept)

    def _initWidget(self) -> None:
        self.setWindowTitle("Ghost Downloader")
        self.setModal(True)
        self.setMinimumWidth(300)
        self.descriptionLabel.setWordWrap(True)

        for language in self._languages:
            self.languageCombo.addItem(LANGUAGE_TEXTS[language])

        selected = (
            cfg.language.value
            if cfg.language.value != Language.AUTO
            else preferredLanguage()
        )
        self.languageCombo.setCurrentIndex(self._languages.index(selected))

    def _initLayout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(self.titleLabel)
        layout.addWidget(self.descriptionLabel)
        layout.addSpacing(8)
        layout.addWidget(self.languageCombo)
        layout.addStretch(1)
        layout.addWidget(
            self.continueButton,
            0,
            Qt.AlignmentFlag.AlignRight,
        )

    def selectedLanguage(self) -> Language:
        index = self.languageCombo.currentIndex()
        if 0 <= index < len(self._languages):
            return self._languages[index]
        return Language.ENGLISH_UNITED_STATES
