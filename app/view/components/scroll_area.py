from __future__ import annotations

import sys

from PySide6.QtCore import QAbstractAnimation, QByteArray, QEasingCurve, QEvent, QPropertyAnimation, Qt
import qfluentwidgets


class ScrollArea(qfluentwidgets.ScrollArea if sys.platform == "darwin" else qfluentwidgets.SmoothScrollArea):

    def __init__(self, parent=None):
        self._viewport = None
        super().__init__(parent)
        self._viewport = self.viewport()
        bar = self.scrollDelagate.vScrollBar if sys.platform == "darwin" else self.delegate.vScrollBar
        self._vBar = bar
        self._scrollAnim = QPropertyAnimation(bar, QByteArray(b"val"), self)
        self._scrollAnim.setDuration(250)
        self._scrollAnim.setEasingCurve(QEasingCurve.Type.OutCubic)
        bar.sliderPressed.connect(self._scrollAnim.stop)
        self._viewport.installEventFilter(self)

    @property
    def isScrolling(self) -> bool:
        return self._scrollAnim.state() == QAbstractAnimation.State.Running

    def scrollTo(self, y: int, *, animate: bool = True) -> None:
        bar = self.verticalScrollBar()
        target = max(bar.minimum(), min(bar.maximum(), y))
        self._scrollAnim.stop()
        self._vBar.ani.stop()
        self._vBar.resetValue(target)
        if not animate or target == bar.value():
            bar.setValue(target)
            return
        self._scrollAnim.setStartValue(bar.value())
        self._scrollAnim.setEndValue(target)
        self._scrollAnim.start()

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Wheel and obj is self._viewport:
            self._scrollAnim.stop()
        return super().eventFilter(obj, event)

    if sys.platform != "darwin":
        def enableTransparentBackground(self) -> None:
            self.setStyleSheet("QScrollArea{border: none; background: transparent}")
            self.viewport().setStyleSheet("background: transparent")

SCROLL_BAR_WIDTH = 13
PAGE_MARGIN = 12

if sys.platform == "win32":
    class FastScrollArea(ScrollArea):
        """视口背后的画面须沿纵向一致，否则平移会拖出残影。"""

        def __init__(self, parent=None):
            super().__init__(parent)
            # 滚动条盖住视口时 Qt 不平移
            self.setViewportMargins(0, 0, SCROLL_BAR_WIDTH, 0)
            bar = self.delegate.vScrollBar
            bar.valueChanged.disconnect(self.verticalScrollBar().setValue)
            bar.valueChanged.connect(self._onScrollValueChanged)

        def scrollContentsBy(self, dx: int, dy: int) -> None:
            # 只在移动时声明不透明：Qt 平移已画好的像素，新露出的一条连背景照常重画
            widget = self.widget()
            widget.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
            super().scrollContentsBy(dx, dy)
            widget.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

        def _onScrollValueChanged(self, value: int) -> None:
            # 滚动距离是整物理像素时 Qt 才平移，滚到底时不对齐
            bar = self.verticalScrollBar()
            if value < bar.maximum():
                ratio = self.devicePixelRatioF()
                value -= value % next((n for n in (1, 2, 4) if (n * ratio).is_integer()), 1)
            bar.setValue(value)
else:
    FastScrollArea = ScrollArea

__all__ = ["FastScrollArea", "PAGE_MARGIN", "ScrollArea"]
