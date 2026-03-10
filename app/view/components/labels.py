import typing

from PySide6.QtGui import QPainter
from qfluentwidgets import BodyLabel

if typing.TYPE_CHECKING:
    from qfluentwidgets import FluentIconBase


class IconBodyLabel(BodyLabel):
    _iconCache = {}

    def __init__(self, text: str, icon: "FluentIconBase", parent=None, size: int = 16):
        super().__init__(parent)
        self.size = size
        self.setText(text)
        self.icon = icon
        self.setContentsMargins(size + 4, 0, 0, 2)  # 给 Icon 和 Text 之间留出 4px 的间距
        self.setMinimumHeight(size)
        self.cachedIconKey = self.preCacheIcon()

    def preCacheIcon(self):
        """预缓存图标并返回缓存键"""
        # iconKey = (id(self.icon), self.size)
        iconKey = id(self.icon)
        if iconKey not in self._iconCache:
            self._iconCache[iconKey] = self.icon.icon().pixmap(self.size, self.size)
        return iconKey

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        yOffset = (self.height() - self.size) // 2
        painter.drawPixmap(0, yOffset, self._iconCache.get(self.cachedIconKey, self.preCacheIcon()))

    @classmethod
    def clearCache(cls):
        cls._iconCache.clear()
