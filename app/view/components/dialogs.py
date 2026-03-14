import hashlib
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QButtonGroup, QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    MessageBoxBase, SubtitleLabel, BodyLabel, CheckBox, RadioButton, LineEdit, ToolButton, FluentIcon, ToolTipFilter,
    ComboBox, ProgressBar
)


class DeleteTaskDialog(MessageBoxBase):

    def __init__(self, parent=None, showCheckBox=True, deleteOnClose=True):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(self.tr("删除任务"), self)
        self.contentLabel = BodyLabel(
            self.tr("确定要删除此任务吗？"), self)
        self.deleteFileCheckBox = CheckBox(self.tr("删除文件"), self)

        self.deleteFileCheckBox.setVisible(showCheckBox)

        if deleteOnClose:
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.initWidget()

    def initWidget(self):
        self.deleteFileCheckBox.setChecked(True)
        self.widget.setMinimumWidth(330)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(12)
        self.viewLayout.addWidget(self.contentLabel)
        self.viewLayout.addSpacing(10)
        self.viewLayout.addWidget(self.deleteFileCheckBox)


class PlanTaskDialog(MessageBoxBase):

    SHUTDOWN = 0
    RESTART = 1
    OPEN_FILE = 2

    def __init__(self, parent=None, deleteOnClose=True):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(self.tr("设置计划任务"), self)
        self.contentLabel = BodyLabel(self.tr("所有任务完成后执行以下操作："), self)
        self.radioButtonGroup = QButtonGroup(self)
        self.powerOffButton = RadioButton(self.tr("关机"), self)
        self.restartButton = RadioButton(self.tr("重启"), self)
        self.openFileButton = RadioButton(self.tr("打开文件"), self)
        self.pathContainer = QWidget(self)
        self.pathLayout = QHBoxLayout(self.pathContainer)
        self.lineEdit = LineEdit(self.pathContainer)
        self.selectFolderButton = ToolButton(FluentIcon.FOLDER, self.pathContainer)

        if deleteOnClose:
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.initWidget()
        self.initLayout()
        self.connectSignalToSlot()

    def initWidget(self):
        self.widget.setMinimumWidth(420)
        self.yesButton.setText(self.tr("确认"))
        self.cancelButton.setText(self.tr("取消"))

        self.radioButtonGroup.addButton(self.powerOffButton)
        self.radioButtonGroup.addButton(self.restartButton)
        self.radioButtonGroup.addButton(self.openFileButton)
        self.radioButtonGroup.setExclusive(True)
        self.powerOffButton.setChecked(True)

        self.lineEdit.setPlaceholderText(self.tr("请选择要打开的文件"))
        self.lineEdit.setClearButtonEnabled(True)
        self.selectFolderButton.setToolTip(self.tr("选择文件"))
        self.selectFolderButton.installEventFilter(ToolTipFilter(self.selectFolderButton))

        self.pathLayout.setContentsMargins(0, 0, 0, 0)
        self.pathLayout.setSpacing(8)
        self.pathLayout.addWidget(self.lineEdit, 1)
        self.pathLayout.addWidget(self.selectFolderButton)

        self._syncPathWidgets()

    def initLayout(self):
        optionsLayout = QVBoxLayout()
        optionsLayout.setContentsMargins(0, 0, 0, 0)
        optionsLayout.setSpacing(10)
        optionsLayout.addWidget(self.powerOffButton)
        optionsLayout.addWidget(self.restartButton)
        optionsLayout.addWidget(self.openFileButton)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(2)
        self.viewLayout.addWidget(self.contentLabel)
        self.viewLayout.addSpacing(4)
        self.viewLayout.addLayout(optionsLayout)
        self.viewLayout.addSpacing(2)
        self.viewLayout.addWidget(self.pathContainer)

    def connectSignalToSlot(self):
        self.openFileButton.toggled.connect(self._syncPathWidgets)
        self.selectFolderButton.clicked.connect(self._chooseFile)

    def _syncPathWidgets(self):
        enabled = self.openFileButton.isChecked()
        self.pathContainer.setVisible(enabled)
        if enabled and not self.lineEdit.text().strip():
            self.lineEdit.setFocus()

    def _chooseFile(self):
        filePath, _ = QFileDialog.getOpenFileName(self, self.tr("选择文件"))
        if filePath:
            self.lineEdit.setText(filePath)

    def selectedAction(self) -> int:
        checkedButton = self.radioButtonGroup.checkedButton()
        if checkedButton is self.restartButton:
            return self.RESTART
        if checkedButton is self.openFileButton:
            return self.OPEN_FILE
        return self.SHUTDOWN

    def selectedFilePath(self) -> str:
        return self.lineEdit.text().strip()

    def validate(self) -> bool:
        if self.selectedAction() == self.OPEN_FILE and not self.selectedFilePath():
            return False

        return True


class FileHashWorker(QThread):
    progressChanged = Signal(int)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, filePath: str, algorithm: str, parent=None):
        super().__init__(parent)
        self.filePath = filePath
        self.algorithm = algorithm

    def run(self):
        try:
            hasher = hashlib.new(self.algorithm)
            fileSize = Path(self.filePath).stat().st_size
            processed = 0

            with open(self.filePath, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    hasher.update(chunk)
                    processed += 1024 * 1024
                    progress = 100 if fileSize == 0 else min(100, int(processed * 100 / fileSize))
                    self.progressChanged.emit(progress)

            self.progressChanged.emit(100)
            self.succeeded.emit(hasher.hexdigest())
        except Exception as e:
            message = repr(e)
            self.failed.emit(message)


class FileHashDialog(MessageBoxBase):
    hashReady = Signal(str, str)
    hashFailed = Signal(str)

    def __init__(self, filePath: str, parent=None, deleteOnClose=True):
        super().__init__(parent)
        self.filePath = filePath
        self.worker: FileHashWorker | None = None

        self.titleLabel = SubtitleLabel(self.tr("校验下载文件"), self)
        self.contentLabel = BodyLabel(self.tr("请选择要使用的校验算法"), self)
        self.algorithmComboBox = ComboBox(self)
        self.statusLabel = BodyLabel(self.tr("等待开始"), self)
        self.progressBar = ProgressBar(self)

        if deleteOnClose:
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.initWidget()

    def initWidget(self):
        self.widget.setMinimumWidth(420)
        self.yesButton.setText(self.tr("开始校验"))
        self.cancelButton.setText(self.tr("取消"))

        algorithms = sorted(hashlib.algorithms_available)
        self.algorithmComboBox.addItems(algorithms)
        if "sha256" in algorithms:
            self.algorithmComboBox.setCurrentText("sha256")

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.contentLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.algorithmComboBox)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.statusLabel)
        self.viewLayout.addSpacing(4)
        self.viewLayout.addWidget(self.progressBar)

    def selectedAlgorithm(self) -> str:
        return self.algorithmComboBox.currentText().strip()

    def accept(self):
        if self.worker is not None:
            return

        self._startHash()

    def reject(self):
        if self.worker is not None:
            return

        super().reject()

    def _startHash(self):
        algorithm = self.selectedAlgorithm()
        if not algorithm:
            return

        self.algorithmComboBox.setEnabled(False)
        self.yesButton.setEnabled(False)
        self.cancelButton.setEnabled(False)
        self.progressBar.setError(False)
        self.progressBar.setValue(0)
        self.statusLabel.setText(self.tr("正在校验 {0}").format(algorithm))

        self.worker = FileHashWorker(self.filePath, algorithm, self)
        self.worker.progressChanged.connect(self._onProgressChanged)
        self.worker.succeeded.connect(self._onHashSucceeded)
        self.worker.failed.connect(self._onHashFailed)
        self.worker.start()

    def _finishWorker(self):
        worker = self.worker
        self.worker = None
        if worker is None:
            return

        worker.wait()
        worker.deleteLater()

    def _onProgressChanged(self, value: int):
        self.progressBar.setValue(value)
        self.statusLabel.setText(self.tr("正在校验 {0}%").format(value))

    def _onHashSucceeded(self, digest: str):
        algorithm = self.selectedAlgorithm()
        self.progressBar.setValue(100)
        self.statusLabel.setText(self.tr("校验完成"))
        self.hashReady.emit(algorithm, digest)
        self._finishWorker()
        super().accept()

    def _onHashFailed(self, error: str):
        self.progressBar.error()
        self.statusLabel.setText(self.tr("校验失败：{0}").format(error))
        self.hashFailed.emit(error)
        self._finishWorker()
        self.algorithmComboBox.setEnabled(True)
        self.yesButton.setEnabled(True)
        self.cancelButton.setEnabled(True)
        self.yesButton.setText(self.tr("重新校验"))
