import typing

from PySide6.QtGui import QPainter, QPixmap
from qfluentwidgets import BodyLabel, StrongBodyLabel

if typing.TYPE_CHECKING:
    from qfluentwidgets import FluentIconBase


class IconLabelBase:
    iconSize: int
    icon: "FluentIconBase | None"
    _iconCache: dict[int, QPixmap] = {}

    def _initIcon(self, icon: "FluentIconBase | None", size: int) -> None:
        self.iconSize = size
        self.icon = None
        self.setMinimumHeight(size)
        self.setIcon(icon)

    def setIcon(self, icon: "FluentIconBase | None") -> None:
        self.icon = icon
        leftMargin = self.iconSize + 4 if icon is not None else 0
        self.setContentsMargins(leftMargin, 0, 0, 2)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.icon is None:
            return
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        yOffset = (self.height() - self.iconSize) // 2
        painter.drawPixmap(0, yOffset, self._pixmapOf(self.icon))

    def _pixmapOf(self, icon: "FluentIconBase") -> QPixmap:
        key = id(icon)
        pixmap = self._iconCache.get(key)
        if pixmap is None:
            pixmap = icon.icon().pixmap(self.iconSize, self.iconSize)
            self._iconCache[key] = pixmap
        return pixmap

    @classmethod
    def clearCache(cls) -> None:
        cls._iconCache.clear()


class IconBodyLabel(IconLabelBase, BodyLabel):
    def __init__(self, text: str, icon: "FluentIconBase", parent=None, size: int = 16) -> None:
        super().__init__(parent)
        self.setText(text)
        self._initIcon(icon, size)


class IconStrongBodyLabel(IconLabelBase, StrongBodyLabel):
    def __init__(self, text: str = "", parent=None, size: int = 16) -> None:
        super().__init__(parent)
        self.setText(text)
        self._initIcon(None, size)
