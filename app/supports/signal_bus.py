# coding: utf-8
from PySide6.QtCore import QObject, Signal


class SignalBus(QObject):
    """Signal bus"""

    appErrorSignal = Signal(str)
    addTaskSignal = Signal(dict)    # TODO: Define Task Details
    showMainWindowSignal = Signal()


signalBus = SignalBus()
