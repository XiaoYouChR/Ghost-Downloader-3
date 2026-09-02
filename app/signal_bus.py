from PySide6.QtCore import QObject, Signal


class SignalBus(QObject):
    activationRequested = Signal()
    openUriRequested = Signal(list)
    exceptionCaught = Signal(str)


signalBus = SignalBus()
