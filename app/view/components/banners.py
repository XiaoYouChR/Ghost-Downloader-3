from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget
from qfluentwidgets import isDarkTheme


class WarningBanner(QWidget):

    def __init__(self, parent: QWidget | None = None, radius: float = 4):
        super().__init__(parent)
        self._radius = radius

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        if isDarkTheme():
            painter.setBrush(QColor(67, 53, 25))
        else:
            painter.setBrush(QColor(255, 244, 206))
        painter.drawRoundedRect(QRectF(self.contentsRect()), self._radius, self._radius)
