# coding: utf-8
from PySide6.QtCore import QObject, Signal

from app.common.config import cfg, Headers


class SignalBus(QObject):
    """ Signal bus """
    addTaskSignal = Signal(str, str, str, dict, str, int, bool, str)  # url, fileName, filePath, headers, status, preBlockNum, notCreateHistoryFile, fileSize
    allTaskFinished = Signal()

signalBus = SignalBus()

def addDownloadTask(url: str, fileName: str = None, filePath: str = None,
                    headers: dict = None, status:str = "working", preBlockNum: int= None, notCreateHistoryFile: bool = False, fileSize: str = "-1"):
    """ Global function to add download task """
    if not filePath:
        filePath = cfg.downloadFolder.value

    if not preBlockNum:
        preBlockNum = cfg.preBlockNum.value

    if not headers:
        headers = Headers

    signalBus.addTaskSignal.emit(url, fileName, filePath, headers, status, preBlockNum, notCreateHistoryFile, fileSize)