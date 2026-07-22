from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class SignalBus(QObject):
    activationRequested = Signal()
    openFileRequested = Signal(list)
    exceptionCaught = Signal(str)


signalBus = SignalBus()
