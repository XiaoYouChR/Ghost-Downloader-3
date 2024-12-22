# coding: utf-8
from PySide6.QtCore import QObject, Signal


class SignalBus(QObject):
    """ Signal bus """
    addTaskSignal = Signal(str, str, int, str, str, bool)  # url, filePath, maxBlockNum, name, status, autoStart
    allTaskFinished = Signal()

signalBus = SignalBus()
