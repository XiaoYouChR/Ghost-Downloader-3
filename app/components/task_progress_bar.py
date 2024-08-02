from PySide6.QtWidgets import QWidget, QHBoxLayout
from qfluentwidgets import ProgressBar

class TaskProgressBar(QWidget):
    def __init__(self, blockNum: int, parent=None):
        super().__init__(parent)

        self.blockNum = blockNum
        self.progressBarList = []

        # Setup UI
        self.HBoxLayout = QHBoxLayout(self)
        self.HBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.HBoxLayout.setSpacing(0)
        self.setLayout(self.HBoxLayout)

        for i in range(self.blockNum):
            _ = ProgressBar(self)
            self.HBoxLayout.addWidget(_)
            self.progressBarList.append(_)

    def addProgressBar(self):
        _ = ProgressBar(self)
        self.HBoxLayout.addWidget(_)
        self.progressBarList.append(_)
        self.blockNum += 1