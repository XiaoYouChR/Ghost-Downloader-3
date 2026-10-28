from __future__ import annotations

import sys

from PySide6.QtCore import Qt

if sys.platform == "darwin":
    from qfluentwidgets import ScrollArea
else:
    from qfluentwidgets import SmoothScrollArea

    class ScrollArea(SmoothScrollArea):
        def enableTransparentBackground(self):
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
