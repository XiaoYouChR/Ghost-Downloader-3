import typing

from PySide6.QtCore import QSize
from PySide6.QtGui import QPainter, QPixmap
from qfluentwidgets import BodyLabel

if typing.TYPE_CHECKING:
    from qfluentwidgets import FluentIconBase


class IconBodyLabel(BodyLabel):
    _iconCache = {}
    
    def __init__(self, text: str, icon: "FluentIconBase", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.icon = icon
        self.setContentsMargins(20, 0, 0, 2)  # 给 Icon 和 Text 之间留出 4px 的间距
        self.iconSize = QSize(16, 16)
        self.cachedIconKey = self.preCacheIcon()
    
    def preCacheIcon(self):
        """预缓存图标并返回缓存键"""
        iconKey = id(self.icon)
        if iconKey not in self._iconCache:
            self._iconCache[iconKey] = self.icon.icon().pixmap(self.iconSize)
        return iconKey
    
    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        yOffset = (self.height() - self.iconSize.height()) // 2
        painter.drawPixmap(0, yOffset, self._iconCache[self.cachedIconKey])
