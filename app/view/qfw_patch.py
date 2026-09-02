from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QStackedWidget


def patchStackedWidgetAnimation() -> None:
    # show() 触发 layout activation → setGeometry 把 widget 拉回 (0,0)，DWM 会合成该帧。
    # 禁用 layout 并预移 widget 到动画起点来规避。
    from PySide6.QtCore import QEasingCurve, QPoint
    from PySide6.QtGui import QResizeEvent
    from qfluentwidgets.components.widgets.stacked_widget import PopUpAniStackedWidget

    _originalSetCurrentIndex = PopUpAniStackedWidget.setCurrentIndex
    _originalResizeEvent = PopUpAniStackedWidget.resizeEvent

    def setCurrentIndex(self, index: int, needPopOut: bool = False,
                        showNextWidgetDirectly: bool = True,
                        duration: int = 250,
                        easingCurve: QEasingCurve = QEasingCurve.OutQuad) -> None:
        if not needPopOut and 0 <= index < self.count() and index != self.currentIndex() and self.isAnimationEnabled:
            info = self.aniInfos[index]
            widget = info.widget
            savedDX, savedDY = info.deltaX, info.deltaY
            widget.resize(self.size())
            widget.move(QPoint(widget.x(), 0) + QPoint(savedDX, savedDY))
            # 暂零 delta，让原方法从预移后的 pos 算出正确的动画值
            info.deltaX, info.deltaY = 0, 0
            self.layout().setEnabled(False)
            try:
                _originalSetCurrentIndex(self, index, needPopOut, showNextWidgetDirectly, duration, easingCurve)
            finally:
                info.deltaX, info.deltaY = savedDX, savedDY
        else:
            _originalSetCurrentIndex(self, index, needPopOut, showNextWidgetDirectly, duration, easingCurve)

    def resizeEvent(self, event: QResizeEvent) -> None:
        _originalResizeEvent(self, event)
        # layout 禁用期间不会 resize 子 widget
        current = self.currentWidget()
        if current and current.size() != event.size():
            current.resize(event.size())

    PopUpAniStackedWidget.setCurrentIndex = setCurrentIndex
    PopUpAniStackedWidget.resizeEvent = resizeEvent


def patchFluentLabelThemeChanged() -> None:
    from qfluentwidgets.components.widgets import label

    FluentLabelBase = label.FluentLabelBase

    def _init(self):
        label.FluentStyleSheet.LABEL.apply(self)
        self.setFont(self.getFont())
        self.setTextColor()
        label.qconfig.themeChanged.connect(self._applyThemeColor)
        self.customContextMenuRequested.connect(self._onContextMenuRequested)
        return self

    def _applyThemeColor(self, *_args) -> None:
        self.setTextColor(self.lightColor, self.darkColor)

    FluentLabelBase._init = _init
    FluentLabelBase._applyThemeColor = _applyThemeColor


def unregisterRouter(stacked: QStackedWidget) -> None:
    from qfluentwidgets.common.router import qrouter

    qrouter.history = [item for item in qrouter.history if item.stacked is not stacked]
    qrouter.stackHistories.pop(stacked, None)
    qrouter.emptyChanged.emit(not bool(qrouter.history))
