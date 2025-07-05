# coding: utf-8
from PySide6.QtCore import QObject, Signal


class SignalBus(QObject):
    """ Signal bus """
    addTaskSignal = Signal(str, str, str, dict, str, int, bool, str)  # url, fileName, filePath, headers, status, preBlockNum, notCreateHistoryFile, fileSize
    allTaskFinished = Signal()
    appErrorSig = Signal(str)
    showMainWindow = Signal()

signalBus = SignalBus()
