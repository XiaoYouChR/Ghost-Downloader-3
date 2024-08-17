# coding: utf-8
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap


class SignalBus(QObject):
    """ Signal bus """
    addTaskSignal = Signal(str, str, int, str, str, QPixmap, bool)  # url, filePath, maxBlockNum, status, name, icon, autoStart
    Tasks = []


signalBus = SignalBus()
