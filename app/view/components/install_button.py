from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPen
from qfluentwidgets import PrimaryPushButton, isDarkTheme

RING_SIZE = 16
STOP_SIZE = 6
QWIDGETSIZE_MAX = (1 << 24) - 1


class InstallButton(PrimaryPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress: int | None = None
        self._spinAni = QVariantAnimation(self)
        self._spinAni.setStartValue(0.0)
        self._spinAni.setEndValue(2.0)
        self._spinAni.setDuration(2000)
        self._spinAni.setLoopCount(-1)
        self._spinAni.valueChanged.connect(self.update)

    def setProgress(self, progress: int | None) -> None:
        if progress is not None and self._progress is None:
            self.setFixedWidth(self.sizeHint().width())
            self.setText("")
        elif progress is None and self._progress is not None:
            self.setMinimumWidth(0)
            self.setMaximumWidth(QWIDGETSIZE_MAX)
        self._progress = progress
        self._syncSpin()
        self.update()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._syncSpin()

    def hideEvent(self, e) -> None:
        super().hideEvent(e)
        self._syncSpin()

    def _syncSpin(self) -> None:
        isSpinning = self._spinAni.state() == QVariantAnimation.State.Running
        shouldSpin = self._progress is not None and not (0 < self._progress < 100) and self.isVisible()
        if shouldSpin and not isSpinning:
            self._spinAni.start()
        elif not shouldSpin and isSpinning:
            self._spinAni.stop()

    def paintEvent(self, e) -> None:
        super().paintEvent(e)
        if self._progress is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.3628)
        elif self.isPressed:
            painter.setOpacity(0.786)

        isDark = isDarkTheme()
        fgColor = QColor(0, 0, 0) if isDark else QColor(255, 255, 255)
        trackColor = QColor(0, 0, 0, 60) if isDark else QColor(255, 255, 255, 90)

        cx, cy = self.width() / 2, self.height() / 2
        diameter = RING_SIZE - 2
        ringRect = QRectF(cx - diameter / 2, cy - diameter / 2, diameter, diameter)

        pen = QPen(trackColor, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawArc(ringRect, 0, 360 * 16)

        pen.setColor(fgColor)
        painter.setPen(pen)
        if 0 < self._progress < 100:
            painter.drawArc(ringRect, 90 * 16, -round(self._progress / 100 * 360 * 16))
        else:
            t = self._spinAni.currentValue() or 0.0
            if t <= 1.0:
                startDeg, spanDeg = 450.0 * t, 180.0 * t
            else:
                startDeg, spanDeg = 450.0 + 630.0 * (t - 1.0), 180.0 * (2.0 - t)
            painter.drawArc(ringRect, round((-startDeg + 180.0) % 360.0 * 16), -round(spanDeg * 16))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fgColor)
        painter.drawRoundedRect(QRectF(cx - STOP_SIZE / 2, cy - STOP_SIZE / 2, STOP_SIZE, STOP_SIZE), 1.5, 1.5)
