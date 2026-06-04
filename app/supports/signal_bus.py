from PySide6.QtCore import QObject, Signal


class SignalBus(QObject):
    """Signal bus"""

    catchException = Signal(str)
    showMainWindow = Signal()
    openFileRequested = Signal(list)
    globalSpeedChanged = Signal(int)


signalBus = SignalBus()
