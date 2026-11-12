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


def patchMaskDialogAnimation() -> None:
    from qfluentwidgets.components.dialog_box.mask_dialog_base import MaskDialogBase

    from app.view.components import dialog_animation

    # 子类设成 Qt.Edge 时，面板从这条边滑入滑出
    MaskDialogBase.slideEdge = None
    MaskDialogBase.showEvent = dialog_animation.showEvent
    MaskDialogBase.done = dialog_animation.done


def patchLinuxFrameless() -> None:
    # Wayland 无法获取窗口位置，改在 QWindow 上按窗口内坐标判断边框 #508
    from PySide6.QtCore import QEvent, Qt
    from qframelesswindow import linux
    from qframelesswindow.titlebar import TitleBar

    from app.platform import shadow

    Edge = Qt.Edge
    EDGE_CURSORS = {
        Edge.LeftEdge | Edge.TopEdge: Qt.CursorShape.SizeFDiagCursor,
        Edge.RightEdge | Edge.BottomEdge: Qt.CursorShape.SizeFDiagCursor,
        Edge.RightEdge | Edge.TopEdge: Qt.CursorShape.SizeBDiagCursor,
        Edge.LeftEdge | Edge.BottomEdge: Qt.CursorShape.SizeBDiagCursor,
        Edge.TopEdge: Qt.CursorShape.SizeVerCursor,
        Edge.BottomEdge: Qt.CursorShape.SizeVerCursor,
        Edge.LeftEdge: Qt.CursorShape.SizeHorCursor,
        Edge.RightEdge: Qt.CursorShape.SizeHorCursor,
    }

    def _initFrameless(self) -> None:
        self.windowEffect = linux.LinuxWindowEffect(self)
        self.titleBar = TitleBar(self)
        self._isResizeEnabled = True

        self.updateFrameless()
        self.winId()
        self.windowHandle().installEventFilter(self)
        shadow.registerWindow(self.windowHandle())

        self.titleBar.raise_()
        self.resize(500, 500)

    def eventFilter(self, obj, event: QEvent) -> bool:
        eventType = event.type()
        if (eventType not in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress)
                or not self._isResizeEnabled or self.isMaximized() or self.isFullScreen()):
            return False

        pos = event.position()
        border = self.BORDER_WIDTH
        edges = Edge(0)
        if pos.x() < border:
            edges |= Edge.LeftEdge
        elif pos.x() >= self.width() - border:
            edges |= Edge.RightEdge
        if pos.y() < border:
            edges |= Edge.TopEdge
        elif pos.y() >= self.height() - border:
            edges |= Edge.BottomEdge

        if eventType == QEvent.Type.MouseMove:
            self.setCursor(EDGE_CURSORS.get(edges, Qt.CursorShape.ArrowCursor))
            return False

        if edges and event.button() == Qt.MouseButton.LeftButton:
            # 拦截按下事件，否则标题栏发起的移动会覆盖缩放
            return obj.startSystemResize(edges)
        return False

    linux.LinuxFramelessWindowBase._initFrameless = _initFrameless
    linux.LinuxFramelessWindowBase.eventFilter = eventFilter


def unregisterRouter(stacked: QStackedWidget) -> None:
    from qfluentwidgets.common.router import qrouter

    qrouter.history = [item for item in qrouter.history if item.stacked is not stacked]
    qrouter.stackHistories.pop(stacked, None)
    qrouter.emptyChanged.emit(not bool(qrouter.history))
