from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QStackedWidget


def patchStackedWidgetAnimation() -> None:
    from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QPoint
    from PySide6.QtWidgets import QStackedWidget as _QStackedWidget
    from qfluentwidgets.components.widgets.stacked_widget import PopUpAniStackedWidget

    def setCurrentIndex(self, index, needPopOut=False, showNextWidgetDirectly=True,
                        duration=250, easingCurve=QEasingCurve.OutQuad):
        if index < 0 or index >= self.count():
            raise Exception(f'The index `{index}` is illegal')
        if index == self.currentIndex():
            return
        if not self.isAnimationEnabled:
            return _QStackedWidget.setCurrentIndex(self, index)

        if self._ani and self._ani.state() == QAbstractAnimation.Running:
            self._ani.stop()
            self._ani.finished.disconnect()
            _QStackedWidget.setCurrentIndex(self, self._nextIndex)
            self.aniFinished.emit()

        self._nextIndex = index
        nextAniInfo = self.aniInfos[index]
        currentAniInfo = self.aniInfos[self.currentIndex()]
        currentWidget = self.currentWidget()
        nextWidget = nextAniInfo.widget
        ani = currentAniInfo.ani if needPopOut else nextAniInfo.ani
        self._ani = ani

        if needPopOut:
            deltaX, deltaY = currentAniInfo.deltaX, currentAniInfo.deltaY
            pos = currentWidget.pos() + QPoint(deltaX, deltaY)
            ani.setEasingCurve(easingCurve)
            ani.setStartValue(currentWidget.pos())
            ani.setEndValue(pos)
            ani.setDuration(duration)
            nextWidget.setVisible(showNextWidgetDirectly)
        else:
            deltaX, deltaY = nextAniInfo.deltaX, nextAniInfo.deltaY
            pos = nextWidget.pos() + QPoint(deltaX, deltaY)
            ani.setEasingCurve(easingCurve)
            ani.setStartValue(pos)
            ani.setEndValue(QPoint(nextWidget.x(), 0))
            ani.setDuration(duration)
            currentWidget.hide()
            nextWidget.resize(self.size())
            nextWidget.move(pos)
            nextWidget.setVisible(True)

        def onFinished():
            ani.finished.disconnect(onFinished)
            _QStackedWidget.setCurrentIndex(self, self._nextIndex)
            self.aniFinished.emit()

        ani.finished.connect(onFinished)
        ani.start()
        self.aniStart.emit()

    PopUpAniStackedWidget.setCurrentIndex = setCurrentIndex


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
