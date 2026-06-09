"""移动端平台差异注入 —— 函数而非类, 在 main.py 构造后调用, 不改共享文件。"""


def setupSystemTheme() -> None:
    import darkdetect
    from qfluentwidgets import setTheme

    from app.supports.android import isSystemDark
    from app.supports.config import cfg, toQFluentTheme

    def themeName() -> str:
        return "Dark" if isSystemDark() else "Light"

    # darkdetect 在 Android 无后端(恒 None → 主题永远浅色), 桥到 uiMode 让 Theme.AUTO 解析正确
    darkdetect.theme = themeName
    darkdetect.isDark = isSystemDark
    setTheme(toQFluentTheme(cfg.customThemeMode.value), save=False)


def setupSystemFont() -> None:
    """探测并启用 OEM 系统字体, 否则 Android 上 qfluentwidgets 默认族缺失会回退到 Roboto。须在建 widget 前调用。"""
    from pathlib import Path

    from loguru import logger
    from PySide6.QtGui import QFontDatabase
    from qfluentwidgets import qconfig

    # 各 OEM 默认字体: 已收录直接用, 否则加载文件取族名
    candidates = [
        ("MiSans VF", "/system/fonts/MiSansVF.ttf"),
        ("MiSans", "/system/fonts/MiSans-Regular.ttf"),
        ("OPPO Sans", "/system/fonts/OPPOSans.ttf"),
        ("OplusSans", "/system/fonts/OplusSans3.0.ttf"),
        ("HarmonyOS Sans SC", "/system/fonts/HarmonyOS_Sans_SC_Regular.ttf"),
        ("vivo Sans", "/system/fonts/VivoFont.ttf"),
    ]
    families = set(QFontDatabase.families())

    picked = None
    for name, path in candidates:
        if name in families:
            picked = name
            break
        if Path(path).exists():
            loaded = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(path))
            if loaded:
                picked = loaded[0]
                break

    logger.info("系统字体: {}", picked or "Roboto(未识别 OEM 字体, 回退)")
    qconfig.set(qconfig.fontFamilies, [picked, "sans-serif"] if picked else ["sans-serif"], save=False)


def setupFluentIconRendering() -> None:
    # qsvg 插件 W^X 下 dlopen 不了 → 图标全空白; 改走 QSvgRenderer。须同 patch FluentIconBase.icon 与 Icon(菜单经 Icon 持图标)
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


def setupAndroidMenuEmbedding() -> None:
    # RoundMenu 默认 Qt.Popup 顶层窗口, 部分机型第二个顶层窗的 EGL surface 撞进程级单飞锁 → qFatal 闪退。
    # 降为主窗子控件画进同一 surface; 子控件无 Popup 自动 grab, 另铺全窗透明遮罩接外部点击关菜单。
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QWidget
    from qfluentwidgets.components.widgets.menu import RoundMenu

    class MenuDismissOverlay(QWidget):
        def __init__(self, host: QWidget, menu: RoundMenu):
            super().__init__(host)
            self._menu = menu
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # 只接事件不遮画面
            self.setGeometry(host.rect())

        def mousePressEvent(self, event) -> None:
            self._menu._hideMenu(False)  # 顶层菜单 → close(): 复位 ComboBox、发 closedSignal
            for menu in self.parent().findChildren(RoundMenu):
                if menu.isVisible():
                    menu.hide()  # 顺带收掉仍开着的子菜单
            event.accept()

    def hostWindow(menu: RoundMenu) -> QWidget | None:
        widget = menu.parent()  # 菜单建时 parent=触发控件(卡片/ComboBox), 由它定位承载主窗
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
            return originalExec(self, pos, *args, **kwargs)  # 定位失败退回原行为, 别让弹不出

        self.setParent(host, Qt.WindowType.Widget)  # 顶层 Popup 降为子控件: 画进主窗 surface, 不再单独建窗
        if not self.isSubMenu:  # 子菜单的消失交给父菜单 hover 逻辑, 只顶层菜单铺遮罩
            self._androidOverlay = MenuDismissOverlay(host, self)
            self._androidOverlay.show()
        self.raise_()
        return originalExec(self, host.mapFromGlobal(pos), *args, **kwargs)

    def hideEventInWindow(self, event) -> None:
        overlay = self.__dict__.pop("_androidOverlay", None)
        if overlay is not None:
            overlay.deleteLater()
        # WA_DeleteOnClose 菜单析构时 view.clearFocus 投焦点事件进销毁中的子树 → 段错误; 趁菜单尚存先把焦点挪回主窗
        focused = QApplication.focusWidget()
        if focused is not None and (focused is self or self.isAncestorOf(focused)):
            host = self.parent()
            if isinstance(host, QWidget):
                host.setFocus(Qt.FocusReason.OtherFocusReason)
        originalHideEvent(self, event)

    RoundMenu.exec = execInWindow
    RoundMenu.hideEvent = hideEventInWindow


def setupNativeDialogPaths() -> None:
    """把 SAF 选择器返回的 content:// URI 转回真实路径 —— 本应用基于真实路径写公共目录(MANAGE_EXTERNAL_STORAGE)。"""
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
            documentId = unquote(uri[index + len(marker):])  # primary:Tencent/MobileQQ
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


def setupMobileDialogWidth() -> None:
    """把 MessageBoxBase 对话框宽度封顶到窗内 —— 桌面写死的固定宽在手机会溢出屏幕。"""
    from qfluentwidgets import MessageBoxBase

    originalShowEvent = MessageBoxBase.showEvent

    def cappedShowEvent(self, e):
        parent = self.parent()
        if parent is not None:
            cap = parent.width() - 24
            if 0 < cap < self.widget.width():
                self.widget.setFixedWidth(cap)
        originalShowEvent(self, e)

    MessageBoxBase.showEvent = cappedShowEvent


def setupCollapsibleGroupTouch() -> None:
    """设置分组头部的展开/收起从按下改到松手 —— 否则触屏滑动按在头部会误触(ScrollClickGuard 只吞 release)。"""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    from app.view.components.setting_card_group import CollapsibleSettingCardGroup

    def mousePressEvent(self, event) -> None:
        self._headerPressed = (
            event.button() == Qt.MouseButton.LeftButton
            and event.position().y() < self.cardContainer.geometry().top()
        )
        QWidget.mousePressEvent(self, event)  # 跳过原 toggle, 仅走默认

    def mouseReleaseEvent(self, event) -> None:
        if getattr(self, "_headerPressed", False) and event.button() == Qt.MouseButton.LeftButton:
            self._onExpandButtonClicked()
        self._headerPressed = False
        QWidget.mouseReleaseEvent(self, event)

    CollapsibleSettingCardGroup.mousePressEvent = mousePressEvent
    CollapsibleSettingCardGroup.mouseReleaseEvent = mouseReleaseEvent


def setupTouchScrolling(window) -> None:
    """QScroller 触摸手势 + 滑动吞点击守卫(Qt Widgets 在 Android 默认无惯性甩动); 跳过 ExpandSettingCard(随页整体滚)。"""
    from PySide6.QtCore import QEvent, QObject, Qt
    from PySide6.QtWidgets import QAbstractScrollArea, QScroller, QScrollerProperties, QWidget
    from qfluentwidgets.components.settings.expand_setting_card import ExpandSettingCard

    class ScrollClickGuard(QObject):
        """松手位置离按下位置超阈值即判为滑动, 吞掉 MouseButtonRelease, 避免触屏滑动误触点击。"""

        def __init__(self, parent):
            super().__init__(parent)
            self._pressPosition = None

        def eventFilter(self, obj, event) -> bool:
            eventType = event.type()
            if eventType == QEvent.Type.MouseButtonPress:
                self._pressPosition = event.globalPosition().toPoint()
            elif eventType == QEvent.Type.MouseButtonRelease and self._pressPosition is not None:
                moved = (event.globalPosition().toPoint() - self._pressPosition).manhattanLength()
                self._pressPosition = None
                if moved > 12:
                    return True
            return False

    guard = ScrollClickGuard(window)
    for scrollArea in window.findChildren(QAbstractScrollArea):
        if isinstance(scrollArea, ExpandSettingCard):
            continue
        QScroller.grabGesture(scrollArea.viewport(), QScroller.ScrollerGestureType.TouchGesture)
        scroller = QScroller.scroller(scrollArea.viewport())
        properties = scroller.scrollerProperties()
        noOvershoot = QScrollerProperties.OvershootPolicy.OvershootAlwaysOff  # 禁用滑到边缘的橡皮筋回弹
        properties.setScrollMetric(QScrollerProperties.ScrollMetric.VerticalOvershootPolicy, noOvershoot)
        properties.setScrollMetric(QScrollerProperties.ScrollMetric.HorizontalOvershootPolicy, noOvershoot)
        scroller.setScrollerProperties(properties)
        for child in scrollArea.findChildren(QWidget):
            child.installEventFilter(guard)
