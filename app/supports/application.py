from signal import signal, SIGINT
import sys

from PySide6.QtCore import QSharedMemory, QEvent
from PySide6.QtWidgets import QApplication
from loguru import logger

from app.supports.config import cfg
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

        # cleanup (only needed for unix)
        try:
            cleanupMemory = QSharedMemory(key)
            if cleanupMemory.attach():
                cleanupMemory.detach()
        except Exception as e:
            logger.warning(f"Failed to cleanup shared memory: {e}")

        self.memory = QSharedMemory()
        self.memory.setKey(key)

        if self.memory.attach():
            if sys.platform == "win32":
                import win32gui

                hWnd = win32gui.FindWindow(None, "Ghost Downloader")
                win32gui.ShowWindow(hWnd, 1)

                # 发送自定义信息唤醒窗口
                # WM_CUSTOM = win32con.WM_USER + 1
                # win32gui.SendMessage(hWnd, WM_CUSTOM, 0, 0)
                win32gui.SendMessage(hWnd, 1024 + 1, 0, 0)
                win32gui.SetForegroundWindow(hWnd)

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

        try:
            signal(SIGINT, self._handleInterruptSignal)
        except Exception as e:
            logger.warning(f"Failed to register SIGINT handler: {e}")

        if sys.platform == "darwin":
            self._setDockIconVisible(cfg.showDockIcon.value, activate=False)
            cfg.showDockIcon.valueChanged.connect(lambda visible: self._setDockIconVisible(visible, activate=True))

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

    def _handleInterruptSignal(self, _signum, _frame):
        logger.error("KeyboardInterrupt, quitting application")
        self.quit()

    # exit: cleanup shared memory
    def exec(self):
        try:
            return super().exec()
        finally:
            try:
                if self.memory.isAttached():
                    self.memory.detach()
            except Exception as e:
                logger.warning(f"Failed to cleanup shared memory on exit: {e}")

    def quit(self):
        try:
            if self.memory.isAttached():
                self.memory.detach()
        except Exception as e:
            logger.warning(f"Failed to cleanup shared memory on quit: {e}")
        super().quit()

    def event(self, e: QEvent) -> bool:
        if sys.platform == "darwin":
            if e.type() == QEvent.Type.ApplicationActivate:
                signalBus.showMainWindow.emit()

        return super().event(e)
