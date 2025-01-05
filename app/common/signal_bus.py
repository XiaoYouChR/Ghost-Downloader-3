# coding: utf-8
from PySide6.QtCore import QObject, Signal


class SignalBus(QObject):
    """ Signal bus """
    addTaskSignal = Signal(str, str, int, str, str, dict, bool)  # url, filePath, maxBlockNum, name, status , headers, autoStart
    allTaskFinished = Signal()

signalBus = SignalBus()
