from __future__ import annotations

import sys
from pathlib import Path
from signal import SIGINT, signal
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, Signal
from PySide6.QtGui import QFileOpenEvent
from PySide6.QtWidgets import QApplication
from loguru import logger

from app.config.constants import DESKTOP_ID

if TYPE_CHECKING:
    from app.view.shell.clipboard_listener import ClipboardListener


class Application(QApplication):
    openRequested = Signal(str)
    activated = Signal()
    systemPaletteChanged = Signal()
    terminated = Signal()

    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)
        if sys.platform == "linux":
            # 任务栏按 .desktop 文件名认领窗口，LauncherEntry 的进度才会落到对应图标上
            self.setDesktopFileName(DESKTOP_ID)
        self.isFileDragActive: bool = False
        self.clipboardListener: ClipboardListener | None = None
        if sys.platform == "win32":
            signal(SIGINT, self._onInterrupt)
        else:
            import socket
            from signal import SIG_DFL, SIGTERM, set_wakeup_fd
            from PySide6.QtCore import QSocketNotifier

            readSock, writeSock = socket.socketpair()
            readSock.setblocking(False)
            writeSock.setblocking(False)
            prevFd = set_wakeup_fd(writeSock.fileno(), warn_on_full_buffer=False)
            signal(SIGINT, lambda *_: None)
            signal(SIGTERM, lambda *_: None)
            notifier = QSocketNotifier(readSock.fileno(), QSocketNotifier.Type.Read, self)

            def onSignal() -> None:
                try:
                    data = readSock.recv(64)
                except BlockingIOError:
                    return
                if SIGTERM in data:
                    notifier.setEnabled(False)
                    self.terminated.emit()
                    self.quit()
                elif SIGINT in data:
                    notifier.setEnabled(False)
                    self._onInterrupt(SIGINT, None)

            def closeSignals() -> None:
                notifier.setEnabled(False)
                signal(SIGINT, SIG_DFL)
                signal(SIGTERM, SIG_DFL)
                set_wakeup_fd(prevFd)
                readSock.close()
                writeSock.close()

            notifier.activated.connect(onSignal)
            self.aboutToQuit.connect(closeSignals)

    def event(self, e: QEvent) -> bool:
        if isinstance(e, QFileOpenEvent):
            self.openRequested.emit(e.url().toString() if not e.url().isEmpty() else Path(e.file()).as_uri())
            return True
        if e.type() == QEvent.Type.ApplicationActivate:
            self.activated.emit()
        if e.type() == QEvent.Type.ApplicationPaletteChange:
            self.systemPaletteChanged.emit()
        return super().event(e)

    def _onInterrupt(self, _signum, _frame) -> None:
        logger.error("KeyboardInterrupt, quitting")
        self.quit()
