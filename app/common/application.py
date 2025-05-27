# coding:utf-8
import sys
import traceback

from PySide6.QtCore import QSharedMemory
from PySide6.QtWidgets import QApplication
from loguru import logger

from .signal_bus import signalBus


class SingletonApplication(QApplication):
    """ Singleton application """

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
            logger.error(f"Failed to create shared memory: {self.memory.errorString()}")
            try:
                self.memory.attach()
                self.memory.detach()
                if not self.memory.create(1):
                    raise RuntimeError(self.memory.errorString())
            except Exception as e:
                logger.error(f"Failed to recover from shared memory error: {e}")
                raise RuntimeError(self.memory.errorString())

        if "__compiled__" in globals():  # 编译后的错误捕捉
            sys.excepthook = exception_hook

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

def exception_hook(exception: BaseException, value, tb):
    """ exception callback function """
    message = '\n'.join([''.join(traceback.format_tb(tb)),
                    '{0}: {1}'.format(exception.__name__, value)])
    logger.exception(f"{message}")
    signalBus.appErrorSig.emit(message)
