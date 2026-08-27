from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, CheckBox, FluentIcon, IconWidget, ToolTipFilter,
    isDarkTheme, themeColor,
)

from app.view.cards.task_cards import TaskCard
from app.view.components.option_cards import OptionCard, SubworkerCountCard
from .task import HttpTaskStep

FILL_EASING = 0.25


class SingleSubworkerCard(OptionCard):

    def __init__(self, subworkerCountCard: SubworkerCountCard, parent=None, *, initial: bool = False):
        super().__init__(parent)
        self._subworkerCountCard = subworkerCountCard
        self._previousCount = subworkerCountCard.slider.value()
        self._initial = initial

        self._initWidget()
        self._initLayout()
        self._bind()
        self._setSingleSubworker(initial)

    def _initWidget(self) -> None:
        self.setFixedHeight(50)
        self.iconWidget = IconWidget(FluentIcon.SPEED_OFF, self)
        self.iconWidget.setFixedSize(16, 16)
        self.titleLabel = BodyLabel(self.tr("单线程下载"), self)
        self.titleLabel.setToolTip(self.tr("强制以单线程下载此任务，避免反爬及限流"))
        self.titleLabel.installEventFilter(ToolTipFilter(self.titleLabel))
        self.checkBox = CheckBox(self)
        self.checkBox.setChecked(self._initial)

    def _initLayout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 5, 40, 5)
        layout.setSpacing(15)
        layout.addWidget(self.iconWidget)
        layout.addWidget(self.titleLabel)
        layout.addStretch(1)
        layout.addWidget(self.checkBox)

    def _bind(self) -> None:
        self.checkBox.toggled.connect(self._setSingleSubworker)

    def options(self) -> dict:
        return {"isSingleSubworker": self.checkBox.isChecked()}

    def reset(self) -> None:
        self.checkBox.setChecked(False)

    def _setSingleSubworker(self, isSingleSubworker: bool) -> None:
        if isSingleSubworker:
            self._previousCount = self._subworkerCountCard.slider.value()
            self._subworkerCountCard.slider.setValue(1)
        else:
            self._subworkerCountCard.slider.setValue(self._previousCount)
        self._subworkerCountCard.setEnabled(not isSingleSubworker)


class SegmentedProgressBar(QWidget):
    def __init__(self, step: HttpTaskStep, parent=None):
        super().__init__(parent)
        self._step = step
        self._isPaused = False
        self._isError = False
        self._fillProgress: dict[int, float] = {}
        self._spans: list[tuple[float, float]] = []
        self._fillTimer = QTimer(self, interval=16)
        self._fillTimer.timeout.connect(self._onFillTimeout)

    def setValue(self, value: float):
        self._fillTimer.start()
        self._onFillTimeout()

    def _onFillTimeout(self):
        live = {sw.start: sw.position for sw in list(self._step.subworkers)}
        fresh = not self._fillProgress
        settled = True
        for start, target in live.items():
            shown = self._fillProgress.get(start, target if fresh else start)
            if target - shown > 1:
                self._fillProgress[start] = shown + (target - shown) * FILL_EASING
                settled = False
            else:
                self._fillProgress[start] = target
        self._fillProgress = {start: self._fillProgress[start] for start in live}
        self._spans = self._toMergedSpans()
        if not self._spans and self._step.receivedBytes > 0:
            self._spans = [(0, self._step.receivedBytes)]
        if settled:
            self._fillTimer.stop()
        self.update()

    def setError(self, isError: bool):
        self._isError = isError
        if not isError:
            self._isPaused = False
        self.update()

    def pause(self):
        self._isPaused = True
        self.update()

    def barColor(self) -> QColor:
        if self._isPaused:
            return QColor(252, 225, 0) if isDarkTheme() else QColor(157, 93, 0)
        if self._isError:
            return QColor(255, 153, 164) if isDarkTheme() else QColor(196, 43, 28)
        return themeColor()

    def _toMergedSpans(self) -> list[tuple[float, float]]:
        intervals = sorted(
            (start, shown) for start, shown in self._fillProgress.items() if shown > start
        )
        merged: list[tuple[float, float]] = []
        for start, end in intervals:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged

    def paintEvent(self, event: QPaintEvent):
        fileSize = self._step.fileSize
        if fileSize <= 0 or not self._spans:
            return

        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.barColor())

        width = self.width()
        height = self.height()
        radius = height / 2
        for start, end in self._spans:
            x = start / fileSize * width
            w = (end - start) / fileSize * width
            painter.drawRoundedRect(QRectF(x, 0, w, height), radius, radius)


class HttpTaskCard(TaskCard):
    def _createProgressBar(self) -> QWidget:
        step = self.task.steps[0] if self.task.steps else None
        if isinstance(step, HttpTaskStep) and step.canUseRangeRequests and step.fileSize > 0 and step.subworkerCount > 1:
            return SegmentedProgressBar(step, self)
        return super()._createProgressBar()
