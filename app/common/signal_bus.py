# coding: utf-8
from app.common.task_base import TaskManagerBase
from PySide6.QtCore import QObject, Signal



class SignalBus(QObject):
    """ Signal bus """
    addTaskSignal = Signal(object, str, str, str, dict, str, int, bool, str)  # TaskManagerCls, url, fileName, filePath, headers, status, preBlockNum, notCreateHistoryFile, fileSize
    allTaskFinished = Signal()

signalBus = SignalBus()
