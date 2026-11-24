from __future__ import annotations

import sys

from PySide6.QtCore import QAbstractAnimation, QEvent, Qt

if sys.platform == "darwin":
    from qfluentwidgets import ScrollArea as FluentScrollArea
else:
    from qfluentwidgets import SmoothScrollArea as FluentScrollArea


class ScrollArea(FluentScrollArea):

    def __init__(self, parent=None):
        super().__init__(parent)
        if sys.platform == "darwin":
            self._smoothBar = self.scrollDelagate.vScrollBar
            self.viewport().installEventFilter(self)
        else:
            self._smoothBar = self.delegate.vScrollBar

    def scrollTo(self, y: int) -> None:
        self._smoothBar.ani.stop()
        self._smoothBar.scrollTo(y)

    def scrollTarget(self) -> int:
        ani = self._smoothBar.ani
        if ani.state() == QAbstractAnimation.State.Running:
            return ani.endValue()
        return self._smoothBar.value()

    if sys.platform == "darwin":
        def eventFilter(self, obj, event) -> bool:
            if event.type() == QEvent.Type.Wheel and obj is self.viewport():
                self._smoothBar.ani.stop()
            return super().eventFilter(obj, event)
    else:
        def enableTransparentBackground(self) -> None:
            self.setStyleSheet("QScrollArea{border: none; background: transparent}")
            self.viewport().setStyleSheet(".QWidget{background: transparent}")

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
