from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import IndeterminateProgressRing, PrimaryPushButton, ProgressRing, isDarkTheme

RING_SIZE = 16
STOP_SIZE = 6
QWIDGETSIZE_MAX = (1 << 24) - 1


class InstallButton(PrimaryPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ring = ProgressRing(self, useAni=False)
        self.spinner = IndeterminateProgressRing(self, start=False)
        self._isInstalling = False

        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        for ring in (self.ring, self.spinner):
            ring.setFixedSize(RING_SIZE, RING_SIZE)
            ring.setStrokeWidth(2)
            ring.setCustomBarColor(QColor(255, 255, 255), QColor(0, 0, 0))
            ring.setCustomBackgroundColor(QColor(255, 255, 255, 90), QColor(0, 0, 0, 60))
            ring.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            ring.hide()

    def _initLayout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignCenter)

    def setInstalling(self, isInstalling: bool) -> None:
        if isInstalling == self._isInstalling:
            return
        self._isInstalling = isInstalling
        if isInstalling:
            self.setFixedWidth(self.sizeHint().width())
            self.setText("")
            return
        self.setMinimumWidth(0)
        self.setMaximumWidth(QWIDGETSIZE_MAX)
        self.ring.hide()
        self.spinner.stop()
        self.spinner.hide()

    def setProgress(self, progress: int) -> None:
        isDownloading = 0 < progress < 100
        self.ring.setValue(progress)
        self.ring.setVisible(isDownloading)
        if isDownloading:
            self.spinner.stop()
            self.spinner.hide()
        elif self.spinner.isHidden():
            self.spinner.show()
            self.spinner.start()

    def paintEvent(self, e):
        super().paintEvent(e)
        if not self._isInstalling:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0) if isDarkTheme() else QColor(255, 255, 255))
        rect = QRectF((self.width() - STOP_SIZE) / 2, (self.height() - STOP_SIZE) / 2, STOP_SIZE, STOP_SIZE)
        painter.drawRoundedRect(rect, 1.5, 1.5)
