import os
import sys

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFileDialog, QApplication
from qfluentwidgets import CheckBox, MessageBox, ComboBox, MessageBoxBase, SubtitleLabel, InfoBar, InfoBarPosition

from app.common.methods import openFile
from app.common.signal_bus import signalBus
from app.components.Ui_PlanTaskDialog import Ui_PlanTaskDialog
from app.components.custom_components import DisabledRichTextEdit


class DelDialog(MessageBox):
    def __init__(self, parent=None):
        super().__init__(title="删除下载任务", content="确定要删除下载任务吗？", parent=parent)
        self.setClosableOnMaskClicked(True)

        self.checkBox = CheckBox("彻底删除", self)
        self.textLayout.addWidget(self.checkBox)

    @classmethod
    def getCompletely(cls, parent=None):
        dialog = cls(parent)
        _ = dialog.exec()
        completely = dialog.checkBox.isChecked()
        dialog.deleteLater()
        return _, completely


class CustomInputDialog(MessageBox):
    def __init__(self, title, content, items, parent=None):
        super().__init__(title, content, parent)
        self.widget.setFixedSize(300, 150)
        self.setClosableOnMaskClicked(True)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self.comboBox = ComboBox(self)
        self.comboBox.addItems(items)

        self.textLayout.addWidget(self.comboBox)

    def get_item(self):
        _ = self.exec()
        return self.comboBox.currentText(), _


class EditHeadersDialog(MessageBoxBase):
    headersUpdated = Signal(dict)

    def __init__(self, parent=None, initialHeaders=None):
        super().__init__(parent=parent)
        self.setClosableOnMaskClicked(True)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self.widget.setFixedSize(400, 500)

        self.titleLabel = SubtitleLabel("编辑请求标头", self.widget)
        self.viewLayout.addWidget(self.titleLabel)

        self.headersTextEdit = DisabledRichTextEdit(self.widget)
        self.headersTextEdit.setPlaceholderText('请输入请求标头，每行一个键值对，格式为 "key: value"')
        if initialHeaders:
            self.headersTextEdit.setPlainText("\n".join([f"{k}: {v}" for k, v in initialHeaders.items()]))
        self.viewLayout.addWidget(self.headersTextEdit)

    def validate(self):
        self.headersDict = self.__parseHeaders(self.headersTextEdit.toPlainText())
        if self.headersDict is not None:
            return True
        else:
            InfoBar.error(
                title="错误",
                content='请输入格式正确的请求标头, 格式为 "key: value"',
                position=InfoBarPosition.TOP,
                parent=self.parent(),
                duration=3000,
            )
            return False

    def __parseHeaders(self, headers_text) -> dict:
        headersDict = {}
        lines = headers_text.strip().split('\n')
        for line in lines:
            if line.strip():
                parts = line.split(':', 1)
                if len(parts) != 2:
                    return None
                key, value = parts
                headersDict[key.strip()] = value.strip()
        return headersDict

    def getHeaders(self):
        _ = self.exec()
        if _:
            return self.headersDict, _
        else:
            return None, _


class PlanTaskDialog(MessageBoxBase, Ui_PlanTaskDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setupUi(self.viewLayout)
        self.widget.setFixedSize(410, 275)

        self.setAttribute(Qt.WA_DeleteOnClose)
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
