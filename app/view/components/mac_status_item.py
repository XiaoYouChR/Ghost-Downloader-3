from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, QResource
from PySide6.QtWidgets import QApplication

from app.supports.config import cfg
from app.supports.signal_bus import signalBus
from app.supports.utils import toReadableSize

from AppKit import (
    NSObject,
    NSStatusBar,
    NSVariableStatusItemLength,
    NSImage,
    NSImageLeft,
    NSMenu,
    NSMenuItem,
)
from Foundation import NSData

if TYPE_CHECKING:
    from app.view.windows.main_window import MainWindow


def _tr(text: str) -> str:
    # 复用现有 SystemTrayIcon 上下文的译文 (.ts 按 context + source 匹配)
    return QCoreApplication.translate("SystemTrayIcon", text)


class _MenuTarget(NSObject):
    """原生菜单的 target-action 接收者; mainWindow 在创建后注入"""

    def showDashboard_(self, sender):
        signalBus.showMainWindow.emit()

    def startAll_(self, sender):
        self.mainWindow.taskPage.startAllTasks()

    def pauseAll_(self, sender):
        self.mainWindow.taskPage.pauseAllTasks()

    def quitApp_(self, sender):
        QApplication.instance().quit()


class MacStatusItem:
    """macOS 菜单栏常驻项: 原生 NSStatusItem + NSMenu, 可选叠加实时速度文字。
    在 macOS 上替换 SystemTrayIcon, 对外保持 .show() 形态以便 main_window 平替。"""

    _ICON_PT = 16  # 菜单栏字形点尺寸 (状态栏厚约 22pt, 留约 6pt 边距)

    def __init__(self, mainWindow: "MainWindow"):
        self._statusItem = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        self._button = self._statusItem.button()
        self._button.setImage_(self._toMenuBarTemplate())
        self._button.setImagePosition_(NSImageLeft)

        self._target = _MenuTarget.alloc().init()
        self._target.mainWindow = mainWindow
        self._statusItem.setMenu_(self._buildMenu())

        signalBus.globalSpeedChanged.connect(self._onGlobalSpeedChanged)
        cfg.showMenuBarSpeed.valueChanged.connect(self._onShowMenuBarSpeedChanged)

    def show(self) -> None:
        # NSStatusItem 创建即可见; 保留方法以对齐 SystemTrayIcon 接口
        self._statusItem.setVisible_(True)

    def _buildMenu(self) -> NSMenu:
        menu = NSMenu.alloc().init()
        for title, selector in (
            (_tr("仪表盘"), "showDashboard:"),
            (_tr("全部开始"), "startAll:"),
            (_tr("全部暂停"), "pauseAll:"),
            (_tr("退出程序"), "quitApp:"),
        ):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector, "")
            item.setTarget_(self._target)
            menu.addItem_(item)
        return menu

    def _toMenuBarTemplate(self) -> NSImage:
        raw = QResource(":/image/logo_menubar_template.png").data()
        image = NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(raw, len(raw)))
        size = image.size()
        image.setSize_((self._ICON_PT * size.width / size.height, self._ICON_PT))
        image.setTemplate_(True)
        return image

    def _onGlobalSpeedChanged(self, speed: int) -> None:
        if cfg.showMenuBarSpeed.value and speed > 0:
            self._button.setTitle_(f" {toReadableSize(speed)}/s")
        else:
            self._button.setTitle_("")

    def _onShowMenuBarSpeedChanged(self, enabled: bool) -> None:
        if not enabled:
            self._button.setTitle_("")
