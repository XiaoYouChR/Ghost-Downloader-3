from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QPropertyAnimation, QEasingCurve, Signal, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel
from qfluentwidgets import BodyLabel, StrongBodyLabel, ToolTipFilter, isDarkTheme

if TYPE_CHECKING:
    from qfluentwidgets import FluentIconBase


class ElidedLabel(QLabel):
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        metrics = painter.fontMetrics()
        elided = metrics.elidedText(self.text(), Qt.TextElideMode.ElideRight, self.width())
        painter.drawText(self.rect(), self.alignment(), elided)


class IconLabelBase:
    iconSize: int
    icon: FluentIconBase | None
    _iconCache: dict[int, QPixmap] = {}

    def _initIcon(self, icon: FluentIconBase | None, size: int) -> None:
        self.iconSize = size
        self.icon = None
        self.setMinimumHeight(size)
        self.setIcon(icon)

    def setIcon(self, icon: FluentIconBase | None) -> None:
        self.icon = icon
        self.setIndent(self.iconSize + 4 if icon is not None else 0)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.icon is None:
            return
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        yOffset = (self.height() - self.iconSize) // 2
        pixmap = self._iconCache.get(id(self.icon))
        if pixmap is None:
            pixmap = self.icon.icon().pixmap(self.iconSize, self.iconSize)
            self._iconCache[id(self.icon)] = pixmap
        painter.drawPixmap(0, yOffset, pixmap)

    @classmethod
    def clearCache(cls, *_) -> None:
        cls._iconCache.clear()


class IconBodyLabel(IconLabelBase, BodyLabel):
    def __init__(self, text: str, icon: FluentIconBase, parent=None, size: int = 16) -> None:
        super().__init__(parent)
        self.setText(text)
        self._initIcon(icon, size)


class IconStrongBodyLabel(IconLabelBase, StrongBodyLabel):
    def __init__(self, text: str = "", parent=None, size: int = 16) -> None:
        super().__init__(parent)
        self._fullText = text
        super().setText(text)
        self._initIcon(None, size)
        self.installEventFilter(ToolTipFilter(self))

    def text(self) -> str:
        return self._fullText

    def setText(self, text: str) -> None:
        self._fullText = text
        self._elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        width = self.contentsRect().width() - self.indent()
        if width > 0:
            elided = self.fontMetrics().elidedText(
                self._fullText, Qt.TextElideMode.ElideRight, width)
        else:
            elided = self._fullText
        super().setText(elided)
        self.setToolTip(self._fullText if elided != self._fullText else "")


class EditableLabel(StrongBodyLabel):
    editRequested = Signal()

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._text = text
        super().setText(text)
        self._underlineProgress = 0.0
        self._underlineAnim = QPropertyAnimation(self, b"underlineProgress", self)
        self._underlineAnim.setDuration(150)
        self._underlineAnim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.installEventFilter(ToolTipFilter(self))

    def text(self) -> str:
        return self._text

    def setText(self, text: str) -> None:
        self._text = text
        self._elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        width = self.contentsRect().width()
        if width > 0:
            elided = self.fontMetrics().elidedText(
                self._text, Qt.TextElideMode.ElideRight, width)
        else:
            elided = self._text
        super().setText(elided)
        self.setToolTip(self._text if elided != self._text else "")

    @Property(float)
    def underlineProgress(self) -> float:
        return self._underlineProgress

    @underlineProgress.setter
    def underlineProgress(self, value: float) -> None:
        self._underlineProgress = value
        self.update()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._animateTo(1.0)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._animateTo(0.0)

    def hideEvent(self, event) -> None:
        self._underlineAnim.stop()
        self._underlineProgress = 0.0
        super().hideEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.editRequested.emit()
            return
        super().mouseDoubleClickEvent(event)

    def _animateTo(self, end: float) -> None:
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
        textWidth = min(fm.horizontalAdvance(super().text()), rect.width())
        y = rect.top() + (rect.height() - fm.height()) // 2 + fm.ascent() + 2

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(255, 255, 255) if isDarkTheme() else QColor(0, 0, 0), 1))
        painter.drawLine(rect.left(), y, rect.left() + int(textWidth * self._underlineProgress), y)
