# coding: utf-8
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap

class SignalBus(QObject):
    """ Signal bus """

    addTaskSignal = Signal(str,str,int,str,QPixmap)
    TaskList = []


signalBus = SignalBus()