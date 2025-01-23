import os
import sys

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFileDialog, QApplication
from qfluentwidgets import FluentStyleSheet, MessageBoxBase

from app.common.methods import openFile
from app.common.signal_bus import signalBus
from app.components.Ui_PlanTaskDialog import Ui_PlanTaskDialog


class PlanTaskDialog(MessageBoxBase, Ui_PlanTaskDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setupUi(self.viewLayout)
        self.widget.setFixedSize(410, 275)

        self.setClosableOnMaskClicked(True)

        # Connect signals to slots
        self.powerOffButton.toggled.connect(self.updateControls)
        self.quitButton.toggled.connect(self.updateControls)
        self.openFileButton.toggled.connect(self.updateControls)
        self.selectFileButton.clicked.connect(self.selectFile)
        self.yesButton.clicked.connect(self.__onYesButtonClicked)
        self.cancelButton.clicked.connect(self.__onNoButtonClicked)

    def updateControls(self):
            # Disable selectFileButton and filePathEdit if powerOffButton or quitButton is selected
            if self.powerOffButton.isChecked() or self.quitButton.isChecked():
                self.selectFileButton.setEnabled(False)
                self.filePathEdit.setEnabled(False)
            else:
                self.selectFileButton.setEnabled(True)
                self.filePathEdit.setEnabled(True)

            # Disable selectFileButton and filePathEdit until openFileButton is checked
            if not self.openFileButton.isChecked():
                self.selectFileButton.setEnabled(False)
                self.filePathEdit.setEnabled(False)

    def selectFile(self):
        # Open file dialog and set file path to filePathEdit
        filePath, _ = QFileDialog.getOpenFileName(None, "选择文件")
        if filePath:
            self.filePathEdit.setText(filePath)

    def __onYesButtonClicked(self):
        self.setEnabled(False)
        if self.powerOffButton.isChecked():
            if sys.platform == "win32":
                signalBus.allTaskFinished.connect(lambda: os.system('shutdown /s /f /t 0'))
            elif sys.platform == "linux":
                signalBus.allTaskFinished.connect(lambda: os.system('shutdown -h now'))
            elif sys.platform == "darwin":
                # 使用 osascript 实现 macOS 关机
                signalBus.allTaskFinished.connect(lambda: os.system('osascript -e \'tell app "System Events" to shut down\''))
        if self.quitButton.isChecked():
            signalBus.allTaskFinished.connect(QApplication.quit)
        if self.openFileButton.isChecked():
            signalBus.allTaskFinished.connect(lambda: openFile(self.filePathEdit.text()))

        self.accept()

    def __onNoButtonClicked(self):
        self.setEnabled(False)
        self.reject()