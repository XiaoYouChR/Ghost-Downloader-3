from typing import Any

from qfluentwidgets import ComboBox

from app.view.components.cards import ParseSettingCard

# label → yt-dlp -f selector. Fixed tiers keep parse offline (no per-video format probe).
_QUALITY_TIERS = (
    ("最佳画质", "bv*+ba/b"),
    ("1080p", "bv*[height<=1080]+ba/b[height<=1080]"),
    ("720p", "bv*[height<=720]+ba/b[height<=720]"),
    ("480p", "bv*[height<=480]+ba/b[height<=480]"),
    ("仅音频", "ba/b"),
)


class YtDlpQualityEditCard(ParseSettingCard):
    def __init__(self, icon, title: str, parent=None, *, initial: str = "") -> None:
        self._initialFormat = initial
        super().__init__(icon, title, parent)

    def initCustomWidget(self) -> None:
        self.qualityCombo = ComboBox(self)
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.qualityCombo.setMinimumWidth(220)
        selectedIndex = 0
        for index, (label, expr) in enumerate(_QUALITY_TIERS):
            self.qualityCombo.addItem(label, userData=expr)
            if self._initialFormat and expr == self._initialFormat:
                selectedIndex = index
        self.qualityCombo.setCurrentIndex(selectedIndex)

    def _initLayout(self) -> None:
        self.hBoxLayout.addWidget(self.qualityCombo)
        self.hBoxLayout.addSpacing(16)

    def _bind(self) -> None:
        self.qualityCombo.currentIndexChanged.connect(lambda _: self.payloadChanged.emit())

    @property
    def payload(self) -> dict[str, Any]:
        return {"videoFormat": self.qualityCombo.currentData() or _QUALITY_TIERS[0][1]}
