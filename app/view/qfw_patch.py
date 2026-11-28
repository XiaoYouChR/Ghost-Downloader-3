from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


def resizableEdges(window: QWidget, edges: Qt.Edge) -> Qt.Edge:
    if window.minimumWidth() == window.maximumWidth():
        edges &= ~(Qt.Edge.LeftEdge | Qt.Edge.RightEdge)
    if window.minimumHeight() == window.maximumHeight():
        edges &= ~(Qt.Edge.TopEdge | Qt.Edge.BottomEdge)
    return edges


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
        edges = resizableEdges(self, edges)

        if eventType == QEvent.Type.MouseMove:
            self.setCursor(EDGE_CURSORS.get(edges, Qt.CursorShape.ArrowCursor))
            return False

        if edges and event.button() == Qt.MouseButton.LeftButton:
            # 拦截按下事件，否则标题栏发起的移动会覆盖缩放
            return obj.startSystemResize(edges)
        return False

    linux.LinuxFramelessWindowBase._initFrameless = _initFrameless
    linux.LinuxFramelessWindowBase.eventFilter = eventFilter


def patchWindowsFrameless() -> None:
    import win32con
    from qframelesswindow import windows

    Edge = Qt.Edge
    HIT_EDGES = {
        win32con.HTTOPLEFT: Edge.LeftEdge | Edge.TopEdge,
        win32con.HTTOPRIGHT: Edge.RightEdge | Edge.TopEdge,
        win32con.HTBOTTOMLEFT: Edge.LeftEdge | Edge.BottomEdge,
        win32con.HTBOTTOMRIGHT: Edge.RightEdge | Edge.BottomEdge,
        win32con.HTTOP: Edge.TopEdge,
        win32con.HTBOTTOM: Edge.BottomEdge,
        win32con.HTLEFT: Edge.LeftEdge,
        win32con.HTRIGHT: Edge.RightEdge,
    }
    EDGE_HITS = {edges: hit for hit, edges in HIT_EDGES.items()} | {Edge(0): win32con.HTCLIENT}

    _originalNativeEvent = windows.WindowsFramelessWindowBase.nativeEvent

    def nativeEvent(self, eventType, message):
        isHandled, result = _originalNativeEvent(self, eventType, message)
        if result not in HIT_EDGES:
            return isHandled, result
        return True, EDGE_HITS[resizableEdges(self, HIT_EDGES[result])]

    windows.WindowsFramelessWindowBase.nativeEvent = nativeEvent


def patchMacFrameless() -> None:
    import Cocoa
    from PySide6.QtCore import QPoint
    from qframelesswindow.mac import MacFramelessWindowBase
    from qframelesswindow.utils.mac_utils import getNSWindow

    def _extendTitleBarToClientArea(self) -> None:
        nsWindow = getNSWindow(self.winId())
        if nsWindow is None:
            return
        self._MacFramelessWindowBase__nsWindow = nsWindow
        mask = nsWindow.styleMask()
        if not (mask & Cocoa.NSWindowStyleMaskFullSizeContentView):
            nsWindow.setStyleMask_(mask | Cocoa.NSWindowStyleMaskFullSizeContentView)
        if not nsWindow.titlebarAppearsTransparent():
            nsWindow.setTitlebarAppearsTransparent_(True)
        if nsWindow.titleVisibility() != Cocoa.NSWindowTitleHidden:
            nsWindow.setTitleVisibility_(Cocoa.NSWindowTitleHidden)
        nsWindow.setMovableByWindowBackground_(False)
        nsWindow.setMovable_(False)
        if nsWindow.toolbar() is None:
            toolbar = Cocoa.NSToolbar.alloc().initWithIdentifier_("GhostDownloaderTitlebar")
            toolbar.setShowsBaselineSeparator_(False)
            nsWindow.setToolbar_(toolbar)
        if nsWindow.toolbarStyle() != Cocoa.NSWindowToolbarStyleUnified:
            nsWindow.setToolbarStyle_(Cocoa.NSWindowToolbarStyleUnified)
        if nsWindow.titlebarSeparatorStyle() != Cocoa.NSTitlebarSeparatorStyleNone:
            nsWindow.setTitlebarSeparatorStyle_(Cocoa.NSTitlebarSeparatorStyleNone)

    def _updateSystemButtonRect(self) -> None:
        if not self.isSystemButtonVisible():
            return
        nsWindow = getattr(self, "_MacFramelessWindowBase__nsWindow", None) or getNSWindow(self.winId())
        if nsWindow is None:
            return
        left = nsWindow.standardWindowButton_(Cocoa.NSWindowCloseButton)
        mid = nsWindow.standardWindowButton_(Cocoa.NSWindowMiniaturizeButton)
        right = nsWindow.standardWindowButton_(Cocoa.NSWindowZoomButton)
        if not (left and mid and right):
            return
        titlebar = right.superview()
        if titlebar is None:
            return
        titlebarHeight = titlebar.frame().size.height
        spacing = mid.frame().origin.x - left.frame().origin.x
        width = mid.frame().size.width
        height = mid.frame().size.height

        center = QPoint(37, self.titleBar.height() // 2)
        midOrigin = Cocoa.NSPoint(center.x() - width / 2, titlebarHeight - center.y() - height / 2)
        for button, origin in (
            (left, Cocoa.NSPoint(midOrigin.x - spacing, midOrigin.y)),
            (mid, midOrigin),
            (right, Cocoa.NSPoint(midOrigin.x + spacing, midOrigin.y)),
        ):
            if button.frame().origin != origin:
                button.setFrameOrigin_(origin)

    MacFramelessWindowBase._extendTitleBarToClientArea = _extendTitleBarToClientArea
    MacFramelessWindowBase._updateSystemButtonRect = _updateSystemButtonRect
