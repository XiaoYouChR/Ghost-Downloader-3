# coding: utf-8
from PySide6.QtCore import QObject, Signal


class SignalBus(QObject):
    """ Signal bus """
    addTaskSignal = Signal(dict)  # Updated to emit a dictionary
    allTaskFinished = Signal()
    appErrorSig = Signal(str)

signalBus = SignalBus()
