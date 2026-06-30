def patchFileDialogs() -> None:
    from urllib.parse import unquote

    from PySide6.QtWidgets import QFileDialog

    def toRealPath(uri: str) -> str:
        if not uri:
            return uri
        if uri.startswith("file://"):
            return unquote(uri[len("file://"):])
        if not uri.startswith("content://"):
            return uri
        for marker in ("/tree/", "/document/"):
            index = uri.find(marker)
            if index < 0:
                continue
            documentId = unquote(uri[index + len(marker):])
            volume, separator, relative = documentId.partition(":")
            if not separator:
                return uri
            base = "/storage/emulated/0" if volume == "primary" else f"/storage/{volume}"
            return f"{base}/{relative}" if relative else base
        return uri

    originalDirectory = QFileDialog.getExistingDirectory
    originalOpenFiles = QFileDialog.getOpenFileNames

    def resolveExistingDirectory(*args, **kwargs) -> str:
        return toRealPath(originalDirectory(*args, **kwargs))

    def resolveOpenFileNames(*args, **kwargs):
        paths, selectedFilter = originalOpenFiles(*args, **kwargs)
        return [toRealPath(path) for path in paths], selectedFilter

    QFileDialog.getExistingDirectory = staticmethod(resolveExistingDirectory)
    QFileDialog.getOpenFileNames = staticmethod(resolveOpenFileNames)


def patchDialogWidth() -> None:
    from qfluentwidgets import MessageBoxBase

    originalShowEvent = MessageBoxBase.showEvent

    def showEventWithWidthLimit(self, event):
        parent = self.parent()
        if parent is not None:
            widthLimit = parent.width() - 24
            if 0 < widthLimit < self.widget.width():
                self.widget.setFixedWidth(widthLimit)
        originalShowEvent(self, event)

    MessageBoxBase.showEvent = showEventWithWidthLimit


def patchIconRendering() -> None:
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


def patchMenus() -> None:
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


def patchOptionCardLayout() -> None:
    from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
    from qfluentwidgets import ComboBox, LineEdit, Slider

    from app.view.components.card_groups import OptionCardGroup

    MAX_WIDGET_SIZE = (1 << 24) - 1
    expandingControls = (LineEdit, Slider, ComboBox)

    def reflowToVertical(card: QWidget) -> None:
        # 窄屏横排会把路径框/滑块挤没
        layout = card.layout()
        title = getattr(card, "titleLabel", None)
        if layout is None or title is None or getattr(card, "_usesMobileLayout", False):
            return

        controls = []
        afterTitle = False
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if widget is title:
                afterTitle = True
            elif afterTitle and widget is not None:
                controls.append(widget)
        if not controls:
            return

        while layout.count():
            layout.takeAt(0)
        QWidget().setLayout(layout)

        outer = QVBoxLayout(card)
        outer.setContentsMargins(24, 8, 24, 8)
        outer.setSpacing(8)

        titleRow = QHBoxLayout()
        titleRow.setSpacing(12)
        icon = getattr(card, "iconWidget", None)
        if icon is not None:
            titleRow.addWidget(icon)
        titleRow.addWidget(title)
        titleRow.addStretch(1)
        outer.addLayout(titleRow)

        controlRow = QHBoxLayout()
        controlRow.setContentsMargins(28, 0, 0, 0)
        controlRow.setSpacing(8)
        hasExpanding = False
        for widget in controls:
            if isinstance(widget, expandingControls):
                widget.setMinimumWidth(0)
                controlRow.addWidget(widget, 1)
                hasExpanding = True
            else:
                controlRow.addWidget(widget, 0)
        if not hasExpanding:
            controlRow.addStretch(1)
        outer.addLayout(controlRow)

        card.setMinimumHeight(0)
        card.setMaximumHeight(MAX_WIDGET_SIZE)
        card._usesMobileLayout = True

    originalAdd = OptionCardGroup.addCard
    originalInsert = OptionCardGroup.insertCard

    def addCard(self, card) -> None:
        reflowToVertical(card)
        originalAdd(self, card)

    def insertCard(self, index, card) -> None:
        reflowToVertical(card)
        originalInsert(self, index, card)

    OptionCardGroup.addCard = addCard
    OptionCardGroup.insertCard = insertCard


def patchGroupTouch() -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    from app.view.components.setting_card_group import CollapsibleSettingCardGroup

    def mousePressEvent(self, event) -> None:
        self._headerPressed = (
            event.button() == Qt.MouseButton.LeftButton
            and event.position().y() < self.cardContainer.geometry().top()
        )
        QWidget.mousePressEvent(self, event)

    def mouseReleaseEvent(self, event) -> None:
        if getattr(self, "_headerPressed", False) and event.button() == Qt.MouseButton.LeftButton:
            self._onExpandClicked()
        self._headerPressed = False
        QWidget.mouseReleaseEvent(self, event)

    CollapsibleSettingCardGroup.mousePressEvent = mousePressEvent
    CollapsibleSettingCardGroup.mouseReleaseEvent = mouseReleaseEvent
