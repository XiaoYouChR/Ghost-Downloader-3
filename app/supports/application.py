import sys
from pathlib import Path
from signal import signal, SIGINT

from PySide6.QtCore import QSharedMemory, QEvent
from PySide6.QtGui import QFileOpenEvent
from PySide6.QtWidgets import QApplication
from loguru import logger

from app.supports.config import cfg, DESKTOP_ID, DESKTOP_OBJECT_PATH
from app.supports.signal_bus import signalBus

if sys.platform == "darwin":
    from AppKit import (
        NSApp,
        NSApplication,
        NSApplicationActivationPolicyAccessory,
        NSApplicationActivationPolicyRegular,
    )


class SingletonApplication(QApplication):

    def __init__(self, argv: list[str], key: str):
        super().__init__(argv)
        self.key = key
        self._lockSingleInstance()

        try:
            signal(SIGINT, self._onInterrupt)
        except Exception as e:
            logger.warning(f"Failed to register SIGINT handler: {e}")

        if sys.platform == "darwin":
            self._setDockIconVisible(cfg.showDockIcon.value, activate=False)
            cfg.showDockIcon.valueChanged.connect(lambda visible: self._setDockIconVisible(visible, activate=True))
        if sys.platform == "linux":
            self._listenOnDesktopBus()

    def _lockSingleInstance(self) -> None:
        # 清掉 unix 上崩溃残留的共享内存段
        try:
            cleanupMemory = QSharedMemory(self.key)
            if cleanupMemory.attach():
                cleanupMemory.detach()
        except Exception as e:
            logger.warning(f"Failed to cleanup shared memory: {e}")

        self.memory = QSharedMemory()
        self.memory.setKey(self.key)

        if self.memory.attach():  # attach 成功即已有实例: 转交本次启动后自退
            if sys.platform in ("win32", "linux"):
                from app.supports.file_open import sendToRunningInstance
                sendToRunningInstance()
            sys.exit(-1)

        if not self.memory.create(1):
            e = RuntimeError(self.memory.errorString())
            logger.opt(exception=e).error("Failed to create shared memory")
            try:
                self.memory.attach()
                self.memory.detach()
                if not self.memory.create(1):
                    raise RuntimeError(self.memory.errorString())
            except Exception as e:
                logger.opt(exception=e).error("Failed to recover from shared memory error")
                raise RuntimeError(self.memory.errorString())

    def _unlockSingleInstance(self) -> None:
        try:
            if self.memory.isAttached():
                self.memory.detach()
        except Exception as e:
            logger.warning(f"Failed to cleanup shared memory: {e}")

    def exec(self):
        try:
            return super().exec()
        finally:
            self._unlockSingleInstance()

    def quit(self):
        self._unlockSingleInstance()
        super().quit()

    def _onInterrupt(self, _signum, _frame):
        logger.error("KeyboardInterrupt, quitting application")
        self.quit()

    def _setDockIconVisible(self, visible: bool, activate: bool = False):
        if sys.platform != "darwin":
            return

        app = NSApp or NSApplication.sharedApplication()
        policy = (
            NSApplicationActivationPolicyRegular
            if visible
            else NSApplicationActivationPolicyAccessory
        )
        app.setActivationPolicy_(policy)
        if activate:
            app.activateIgnoringOtherApps_(True)

    def _listenOnDesktopBus(self) -> None:
        from PySide6.QtDBus import QDBusConnection
        from app.supports.file_open import DesktopBusReceiver

        bus = QDBusConnection.sessionBus()
        if not bus.registerService(DESKTOP_ID):
            return
        self._dbusObject = DesktopBusReceiver()
        bus.registerObject(
            DESKTOP_OBJECT_PATH,
            self._dbusObject,
            QDBusConnection.RegisterOption.ExportAllSlots,
        )

    def event(self, e: QEvent) -> bool:
        if isinstance(e, QFileOpenEvent):
            uri = e.url().toString() if not e.url().isEmpty() else Path(e.file()).as_uri()
            if uri:
                signalBus.openFileRequested.emit([uri])
            return True

        if sys.platform == "darwin" and e.type() == QEvent.Type.ApplicationActivate:
            signalBus.showMainWindow.emit()

        return super().event(e)
