# coding:utf-8
import sys
import traceback
from typing import List

from PySide6.QtCore import QSharedMemory
from PySide6.QtWidgets import QApplication
from loguru import logger

from .signal_bus import signalBus


class SingletonApplication(QApplication):
    """ Singleton application """

    def __init__(self, argv: List[str], key: str):
        super().__init__(argv)
        self.key = key

        # cleanup (only needed for unix)
        QSharedMemory(key).attach()
        self.memory = QSharedMemory(self)
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
            logger.error(self.memory.errorString())
            raise RuntimeError(self.memory.errorString())

def exception_hook(exception: BaseException, value, tb):
    """ exception callback function """
    message = '\n'.join([''.join(traceback.format_tb(tb)),
                    '{0}: {1}'.format(exception.__name__, value)])
    logger.exception(f"{message}")
    signalBus.appErrorSig.emit(message)

sys.excepthook = exception_hook
