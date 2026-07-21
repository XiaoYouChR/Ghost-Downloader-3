from PySide6.QtCore import QCoreApplication, QResource
from PySide6.QtWidgets import QApplication

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

from app.config.cfg import cfg
from app.format import toReadableSize
from app.signal_bus import signalBus


def tr(text: str) -> str:
    return QCoreApplication.translate("SystemTrayIcon", text)


class MenuTarget(NSObject):
    owner = None

    def menuNeedsUpdate_(self, menu):
        if self.owner is not None:
            self.owner._refreshMenuItems()

    def showDashboard_(self, sender):
        signalBus.activationRequested.emit()

    def startAll_(self, sender):
        self.owner._taskService.startAll()

    def pauseAll_(self, sender):
        self.owner._taskService.pauseAll()

    def quitApp_(self, sender):
        QApplication.instance().quit()


class MacStatusItem:
    ICON_SIZE = 16

    def __init__(self, taskService):
        self._taskService = taskService
        self._statusItem = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        self._button = self._statusItem.button()
        self._button.setImage_(self._buildMenuBarIcon())
        self._button.setImagePosition_(NSImageLeft)

        self._target = MenuTarget.alloc().init()
        self._target.owner = self

        menu = self._buildMenu()
        self._startAllItem = menu.itemAtIndex_(1)
        self._pauseAllItem = menu.itemAtIndex_(2)
        self._statusItem.setMenu_(menu)

        cfg.shouldShowMenuBarSpeed.valueChanged.connect(self._onShowSpeedChanged)

    def show(self) -> None:
        self._statusItem.setVisible_(True)

    def setSpeed(self, bytesPerSecond: int) -> None:
        if cfg.shouldShowMenuBarSpeed.value and bytesPerSecond > 0:
            self._button.setTitle_(f" {toReadableSize(bytesPerSecond)}/s")
        else:
            self._button.setTitle_("")

    def _buildMenu(self) -> NSMenu:
        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)
        menu.setDelegate_(self._target)
        for title, selector, key, symbol in (
            (tr("仪表盘"), "showDashboard:", "", "gauge.open.with.lines.needle.33percent"),
            (tr("全部开始"), "startAll:", "", "play.fill"),
            (tr("全部暂停"), "pauseAll:", "", "pause.fill"),
            (tr("退出程序"), "quitApp:", "q", "power"),
        ):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector, key)
            item.setTarget_(self._target)
            image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol, None)
            if image:
                item.setImage_(image)
            menu.addItem_(item)
        return menu

    def _refreshMenuItems(self) -> None:
        from app.models.task import TaskStatus

        tasks = self._taskService.tasks
        self._startAllItem.setEnabled_(
            any(t.status in {TaskStatus.PAUSED, TaskStatus.FAILED, TaskStatus.WAITING} for t in tasks)
        )
        self._pauseAllItem.setEnabled_(
            any(t.status == TaskStatus.RUNNING for t in tasks)
        )

    def _buildMenuBarIcon(self) -> NSImage:
        raw = QResource(":/image/logo_menubar_template.png").data()
        image = NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(raw, len(raw)))
        size = image.size()
        image.setSize_((self.ICON_SIZE * size.width / size.height, self.ICON_SIZE))
        image.setTemplate_(True)
        return image

    def _onShowSpeedChanged(self, enabled: bool) -> None:
        if not enabled:
            self._button.setTitle_("")
