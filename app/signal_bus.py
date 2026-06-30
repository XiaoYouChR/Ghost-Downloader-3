from PySide6.QtCore import QObject, Signal


class SignalBus(QObject):
    activationRequested = Signal()
    openFileRequested = Signal(list)
    exceptionCaught = Signal(str)
    updateAvailable = Signal(object)


signalBus = SignalBus()
