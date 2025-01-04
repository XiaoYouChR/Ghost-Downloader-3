# coding: utf-8
from PySide6.QtCore import QObject, Signal


class SignalBus(QObject):
    """ Signal bus """
    addTaskSignal = Signal(str, str, int, str, str, bool, str)  # url, filePath, maxBlockNum, name, status, autoStart, cookies
    allTaskFinished = Signal()

signalBus = SignalBus()
