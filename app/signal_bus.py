from PySide6.QtCore import QObject, Signal


class SignalBus(QObject):
    activationRequested = Signal()
    exceptionCaught = Signal(str)


signalBus = SignalBus()
