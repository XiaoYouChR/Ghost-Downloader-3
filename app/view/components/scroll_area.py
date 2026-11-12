from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QObject, Qt

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

    class DirectWheelFilter(QObject):
        """滚轮直接改原生滚动条，不经 SmoothScrollBar 的逐帧动画。

        高刷屏上 QUnifiedTimer 每帧只推进 1~2 逻辑像素，而整物理像素对齐
        要求 4 逻辑像素（DPR=1.25），多数动画帧被量化吞掉，列表阶梯跳动。
        """
        STEP = 120

        def __init__(self, area, step: int):
            super().__init__(area)
            self.area = area
            self.step = step
            self.pending = 0.0

        def eventFilter(self, obj, e) -> bool:
            if e.type() != QEvent.Type.Wheel:
                return False

            angle, pixel = e.angleDelta(), e.pixelDelta()
            dy, dx = angle.y() or pixel.y(), angle.x() or pixel.x()
            if not (dy or dx):
                return False

            vertical = abs(dy) >= abs(dx)
            bar = self.area.verticalScrollBar() if vertical else self.area.horizontalScrollBar()
            if bar.maximum() <= bar.minimum():
                return False

            delta = dy if vertical else dx
            # 与 QFW 委托一致：滚到尽头时放行，让父级滚动区域接手
            if (delta < 0 and bar.value() == bar.maximum()) or (delta > 0 and bar.value() == bar.minimum()):
                return False

            px = pixel.y() if vertical else pixel.x()
            if px:
                self.pending += -px
            else:
                self.pending += -delta / 120 * self.STEP

            move = int(self.pending / self.step) * self.step
            if move:
                self.pending -= move
                before = bar.value()
                bar.setValue(before + move)
                if bar.value() == before:
                    self.pending = 0.0
            e.setAccepted(True)
            return True

    class FastScrollArea(ScrollArea):
        """视口背后的画面须沿纵向一致，否则平移会拖出残影。"""

        def __init__(self, parent=None):
            super().__init__(parent)
            # 滚动条盖住视口时 Qt 不平移
            self.setViewportMargins(0, 0, SCROLL_BAR_WIDTH, 0)
            bar = self.delegate.vScrollBar
            bar.valueChanged.disconnect(self.verticalScrollBar().setValue)
            bar.valueChanged.connect(self._onScrollValueChanged)

            ratio = self.devicePixelRatioF()
            step = next((n for n in (1, 2, 4) if (n * ratio).is_integer()), 1)
            # 整物理像素需要多逻辑像素时才会吞帧；后装的过滤器先收到事件
            if step > 1:
                self.wheelFilter = DirectWheelFilter(self, step)
                self.viewport().installEventFilter(self.wheelFilter)

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
