def patchFluentIconRendering() -> None:
    from PySide6.QtGui import QColor, QIcon
    from qfluentwidgets import Theme
    from qfluentwidgets.common.icon import FluentIconBase, Icon, SvgIconEngine, writeSvg

    def svgBackedIcon(path: str, color=None) -> QIcon:
        if not path.endswith(".svg"):
            return QIcon(path)
        svg = writeSvg(path, fill=QColor(color).name()) if color else writeSvg(path)
        return QIcon(SvgIconEngine(svg))

    def toSvgRendererIcon(self, theme=Theme.AUTO, color=None) -> QIcon:
        return svgBackedIcon(self.path(theme), color)

    def toSvgRendererIconObject(self, fluentIcon) -> None:
        QIcon.__init__(self, svgBackedIcon(fluentIcon.path()))
        self.fluentIcon = fluentIcon

    FluentIconBase.icon = toSvgRendererIcon
    Icon.__init__ = toSvgRendererIconObject

def patchAndroidMenus() -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QWidget
    from qfluentwidgets.components.widgets.menu import RoundMenu

    class MenuDismissOverlay(QWidget):
        def __init__(self, host: QWidget, menu: RoundMenu):
            super().__init__(host)
            self._menu = menu
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setGeometry(host.rect())

        def mousePressEvent(self, event) -> None:
            self._menu._hideMenu(False)
            for menu in self.parent().findChildren(RoundMenu):
                if menu.isVisible():
                    menu.hide()
            event.accept()

    def hostWindow(menu: RoundMenu) -> QWidget | None:
        widget = menu.parent()
        while isinstance(widget, RoundMenu):
            widget = widget.parent()
        if widget is not None:
            return widget.window()
        active = QApplication.activeWindow()
        return active if not isinstance(active, RoundMenu) else None

    originalExec = RoundMenu.exec
    originalHideEvent = RoundMenu.hideEvent

    def execInWindow(self, pos, *args, **kwargs):
        host = hostWindow(self)
        if host is None:
            return originalExec(self, pos, *args, **kwargs)

        self.setParent(host, Qt.WindowType.Widget)
        if not self.isSubMenu:
            self._androidOverlay = MenuDismissOverlay(host, self)
            self._androidOverlay.show()
        self.raise_()
        return originalExec(self, host.mapFromGlobal(pos), *args, **kwargs)

    def hideEventInWindow(self, event) -> None:
        overlay = self.__dict__.pop("_androidOverlay", None)
        if overlay is not None:
            overlay.deleteLater()

        focused = QApplication.focusWidget()
        if focused is not None and (focused is self or self.isAncestorOf(focused)):
            host = self.parent()
            if isinstance(host, QWidget):
                host.setFocus(Qt.FocusReason.OtherFocusReason)
        originalHideEvent(self, event)

    RoundMenu.exec = execInWindow
    RoundMenu.hideEvent = hideEventInWindow
