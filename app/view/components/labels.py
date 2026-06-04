import typing
from collections.abc import Callable

from PySide6.QtCore import Property, QPropertyAnimation, QEasingCurve, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap
from qfluentwidgets import BodyLabel, StrongBodyLabel, isDarkTheme

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
        self.setIndent(self.iconSize + 4 if icon is not None else 0)
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


class EditableLabel(StrongBodyLabel):
    """可编辑文本标签：hover 时从左生长出下划线以提示可编辑，双击触发编辑"""

    def __init__(self, text: str = "", parent=None, onEdit: Callable[[], None] | None = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self._onEdit = onEdit
        self._underlineProgress = 0.0
        self._underlineAnim = QPropertyAnimation(self, b"underlineProgress", self)
        self._underlineAnim.setDuration(150)
        self._underlineAnim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @Property(float)
    def underlineProgress(self) -> float:
        return self._underlineProgress

    @underlineProgress.setter
    def underlineProgress(self, value: float) -> None:
        self._underlineProgress = value
        self.update()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._animateUnderlineTo(1.0)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._animateUnderlineTo(0.0)

    def hideEvent(self, event) -> None:
        # 隐藏后鼠标落在 LineEdit 上不再触发 leaveEvent，需主动归零
        self._underlineAnim.stop()
        self._underlineProgress = 0.0
        super().hideEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._onEdit:
            self._onEdit()
            return
        super().mouseDoubleClickEvent(event)

    def _animateUnderlineTo(self, end: float) -> None:
        self._underlineAnim.stop()
        self._underlineAnim.setStartValue(self._underlineProgress)
        self._underlineAnim.setEndValue(end)
        self._underlineAnim.start()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._underlineProgress <= 0:
            return

        rect = self.contentsRect()
        fm = self.fontMetrics()
        width = min(fm.horizontalAdvance(self.text()), rect.width())
        y = rect.top() + (rect.height() - fm.height()) // 2 + fm.ascent() + 2

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(255, 255, 255) if isDarkTheme() else QColor(0, 0, 0), 1))
        painter.drawLine(rect.left(), y, rect.left() + int(width * self._underlineProgress), y)
