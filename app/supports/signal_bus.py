from PySide6.QtCore import QObject, Signal

from app.bases.models import Task


class SignalBus(QObject):
    """Signal bus"""

    catchException = Signal(str)
    showMainWindow = Signal()


signalBus = SignalBus()
