from signal import signal, SIGINT
import sys
import traceback
from time import localtime, strftime, time

from PySide6.QtCore import QSharedMemory, QEvent, QStandardPaths
from PySide6.QtWidgets import QApplication
from loguru import logger

from app.supports.config import VERSION
from app.supports.signal_bus import signalBus


class SingletonApplication(QApplication):

    def __init__(self, argv: list[str], key: str):
        super().__init__(argv)
        self.key = key

        appLocalDataLocation = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
        logger.add(f"{appLocalDataLocation}/GhostDownloader/GhostDownloader.log", rotation="512 KB", enqueue=True)
        logger.info(
            f"Ghost Downloader v{VERSION} is Launched at {strftime('%Y-%m-%d %H:%M:%S', localtime(time()))}")

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


        if "__compiled__" in globals():  # 编译后的错误捕捉
            sys.excepthook = exceptionHook

        try:
            signal(SIGINT, self._handleInterruptSignal)
        except Exception as e:
            logger.warning(f"Failed to register SIGINT handler: {e}")

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

def exceptionHook(exception: BaseException, value, tb):
    """ exception callback function """
    message = '\n'.join([''.join(traceback.format_tb(tb)),
                    '{0}: {1}'.format(exception.__name__, value)])
    logger.opt(exception=exception).error("Unhandled application exception")
    signalBus.catchException.emit(message)
