from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import BodyLabel, CheckBox, FluentIcon, IconWidget

from app.format import toReadableSize
from app.view.cards.draft_cards import DraftCard
from app.view.components.option_cards import OptionCard
from app.view.components.track_bar import TrackButton
from .config import arxivConfig
from .task import ArxivTask


class ArxivDraftCard(DraftCard):

    @property
    def task(self) -> ArxivTask:
        return self._task

    def _initWidget(self) -> None:
        super()._initWidget()
        self.sourceButton = TrackButton(FluentIcon.CODE, self)
        self.sourceButton.setToolTip(self.tr("TeX 源码"))
        self.sourceButton.setChecked(self.task.isSourceEnabled)
        self.sourceButton.setVisible(self.task.hasSource)
        self.bibtexButton = TrackButton(FluentIcon.LIBRARY, self)
        self.bibtexButton.setToolTip("BibTeX")
        self.bibtexButton.setChecked(self.task.isBibtexEnabled)

    def _initLayout(self) -> None:
        super()._initLayout()
        self.layout().addWidget(self.sourceButton)
        self.layout().addWidget(self.bibtexButton)

    def _bind(self) -> None:
        super()._bind()
        for button in (self.sourceButton, self.bibtexButton):
            button.clicked.connect(lambda _=False, b=button: b.setChecked(not b.isChecked()))
            button.toggled.connect(self._onSideFileToggled)

    def _onSideFileToggled(self) -> None:
        self.task.setOptions({
            "isSourceEnabled": self.sourceButton.isChecked(),
            "isBibtexEnabled": self.bibtexButton.isChecked(),
        })
        self.sizeLabel.setText(toReadableSize(self.task.fileSize) if self.task.fileSize > 1 else "--")
        self._refreshConflictIcon()


class SideFileCard(OptionCard):

    def __init__(self, parent=None, *, task: ArxivTask):
        super().__init__(parent)
        self._task = task
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        self.setFixedHeight(50)
        self.iconWidget = IconWidget(FluentIcon.DOCUMENT, self)
        self.iconWidget.setFixedSize(16, 16)
        self.titleLabel = BodyLabel(self.tr("附属文件"), self)
        self.sourceCheckBox = CheckBox(self.tr("TeX 源码"), self)
        self.sourceCheckBox.setChecked(self._task.isSourceEnabled)
        self.sourceCheckBox.setVisible(self._task.hasSource)
        self.bibtexCheckBox = CheckBox("BibTeX", self)
        self.bibtexCheckBox.setChecked(self._task.isBibtexEnabled)

    def _initLayout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 5, 24, 5)
        layout.setSpacing(15)
        layout.addWidget(self.iconWidget)
        layout.addWidget(self.titleLabel)
        layout.addStretch(1)
        layout.addWidget(self.sourceCheckBox)
        layout.addWidget(self.bibtexCheckBox)

    def options(self) -> dict:
        return {
            "isSourceEnabled": self._task.hasSource and self.sourceCheckBox.isChecked(),
            "isBibtexEnabled": self.bibtexCheckBox.isChecked(),
        }

    def reset(self) -> None:
        self.sourceCheckBox.setChecked(arxivConfig.shouldDownloadSource.value)
        self.bibtexCheckBox.setChecked(arxivConfig.shouldDownloadBibtex.value)
