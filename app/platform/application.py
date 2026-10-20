from __future__ import annotations

from pathlib import Path
from signal import signal, SIGINT

from PySide6.QtCore import QEvent, Signal
from PySide6.QtGui import QFileOpenEvent
from PySide6.QtWidgets import QApplication
from loguru import logger


class Application(QApplication):
    openRequested = Signal(str)
    activated = Signal()

    def __init__(self, argv: list[str]):
        super().__init__(argv)
        self.isFileDragActive = False
        self.clipboardListener = None
        signal(SIGINT, self._onInterrupt)

    def event(self, e: QEvent) -> bool:
        if isinstance(e, QFileOpenEvent):
            self.openRequested.emit(e.url().toString() if not e.url().isEmpty() else Path(e.file()).as_uri())
            return True
        if e.type() == QEvent.Type.ApplicationActivate:
            self.activated.emit()
        return super().event(e)

    def _onInterrupt(self, _signum, _frame) -> None:
        logger.error("KeyboardInterrupt, quitting")
        self.quit()
