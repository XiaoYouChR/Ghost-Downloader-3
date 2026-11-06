from __future__ import annotations

from PySide6.QtWidgets import QWidget
from qfluentwidgets import FluentIcon

from app.format import toReadableSize
from app.view.cards.draft_cards import DraftCard
from app.view.components.range_slider import RangeSlider
from app.view.components.track_bar import TrackButton
from .task import FFmpegTask


def parseTimeInput(text: str) -> int:
    text = text.strip()
    if not text:
        return 0
    parts = text.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return int(text)
    except ValueError:
        return 0


class FFmpegDraftCard(DraftCard):
    _task: FFmpegTask

    @property
    def task(self) -> FFmpegTask:
        return self._task

    def _initWidget(self) -> None:
        super()._initWidget()
        task = self._task

        self._trimButton = TrackButton(FluentIcon.CUT, self)
        self._trimButton.setToolTip(self.tr("截取片段"))
        self._trimButton.setChecked(task.isTrimmed)
        self._trimButton.setVisible(task.canTrim)

        self._rangeSlider = RangeSlider(
            self,
            formatter=lambda s: f"{s // 60}:{s % 60:02d}",
            parser=parseTimeInput,
        )
        self._rangeSlider.setVisible(task.isTrimmed)
        if task.duration > 0:
            self._rangeSlider.setRange(0, task.duration)
            self._rangeSlider.setValues(task.startTime, task.endTime or task.duration)
        if task.isTrimmed:
            self.setFixedHeight(87)

    def _initLayout(self) -> None:
        super()._initLayout()
        self.layout().addWidget(self._trimButton)
        if self._task.isTrimmed:
            self.layout().setContentsMargins(10, 2, 10, 54)

    def _bind(self) -> None:
        super()._bind()
        self._trimButton.clicked.connect(self._onTrimToggled)
        self._rangeSlider.rangeChanged.connect(self._onRangeChanged)

    def _onTrimToggled(self) -> None:
        checked = not self._trimButton.isChecked()
        self._trimButton.setChecked(checked)
        self._rangeSlider.setVisible(checked)
        if checked:
            self.setFixedHeight(87)
            self.layout().setContentsMargins(10, 2, 10, 54)
        else:
            self.setFixedHeight(35)
            self.layout().setContentsMargins(10, 2, 10, 2)
            self._rangeSlider.clear()
            self._task.setTimeRange(0, 0)
            self._refreshSummary()
        w: QWidget | None = self
        while w := w.parentWidget():
            w.updateGeometry()

    def _onRangeChanged(self, start: int, end: int) -> None:
        self._task.setTimeRange(start, end)
        self._refreshSummary()

    def _refreshSummary(self) -> None:
        self.sizeLabel.setText(toReadableSize(self._task.fileSize) if self._task.fileSize > 1 else "--")
        self.nameLabel.setText(self._task.name)
        self.nameEdit.setText(self._task.name)
        self._refreshFileIcon()
        self._refreshConflictIcon()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rangeSlider.setGeometry(10, 37, self.width() - 20, 50)
