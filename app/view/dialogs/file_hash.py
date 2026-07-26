from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from qfluentwidgets import (
    BodyLabel, ComboBox, MessageBoxBase, ProgressBar, SubtitleLabel,
)


class FileHashWorker(QThread):
    progressChanged = Signal(int)
    hashSucceeded = Signal(str)
    hashFailed = Signal(str)

    def __init__(self, filePath: str, algorithm: str, parent=None):
        super().__init__(parent)
        self._filePath = filePath
        self._algorithm = algorithm

    def run(self):
        try:
            hasher = hashlib.new(self._algorithm)
            fileSize = Path(self._filePath).stat().st_size
            processed = 0
            with open(self._filePath, "rb") as f:
                while chunk := f.read(1048576):
                    hasher.update(chunk)
                    processed += len(chunk)
                    self.progressChanged.emit(min(100, int(processed * 100 / fileSize)) if fileSize else 100)
            self.progressChanged.emit(100)
            self.hashSucceeded.emit(hasher.hexdigest())
        except Exception as e:
            self.hashFailed.emit(repr(e))


class FileHashDialog(MessageBoxBase):
    hashReady = Signal(str, str)

    def __init__(self, filePath: str, parent=None):
        super().__init__(parent)
        self._filePath = filePath
        self._worker: FileHashWorker | None = None

        self.titleLabel = SubtitleLabel(self.tr("校验下载文件"), self)
        self.algorithmCombo = ComboBox(self)
        self.statusLabel = BodyLabel(self.tr("等待开始"), self)
        self.progressBar = ProgressBar(self)

        self.widget.setMinimumWidth(420)
        self.yesButton.setText(self.tr("开始校验"))
        self.cancelButton.setText(self.tr("取消"))

        algorithms = sorted(hashlib.algorithms_available)
        self.algorithmCombo.addItems(algorithms)
        if "sha256" in algorithms:
            self.algorithmCombo.setCurrentText("sha256")

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(BodyLabel(self.tr("选择校验算法"), self))
        self.viewLayout.addWidget(self.algorithmCombo)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.statusLabel)
        self.viewLayout.addWidget(self.progressBar)

    def selectedAlgorithm(self) -> str:
        return self.algorithmCombo.currentText().strip()

    def accept(self) -> None:
        if self._worker is not None:
            return
        algorithm = self.selectedAlgorithm()
        if not algorithm:
            return

        self.algorithmCombo.setEnabled(False)
        self.yesButton.setEnabled(False)
        self.cancelButton.setEnabled(False)
        self.progressBar.setValue(0)
        self.statusLabel.setText(self.tr("正在校验..."))

        self._worker = FileHashWorker(self._filePath, algorithm, self)
        self._worker.progressChanged.connect(self.progressBar.setValue)
        self._worker.hashSucceeded.connect(self._onSucceeded)
        self._worker.hashFailed.connect(self._onFailed)
        self._worker.start()

    def reject(self) -> None:
        if self._worker is not None:
            return
        super().reject()

    def _onSucceeded(self, digest: str) -> None:
        self.statusLabel.setText(self.tr("校验完成"))
        self.hashReady.emit(self.selectedAlgorithm(), digest)
        self._cleanup()
        super().accept()

    def _onFailed(self, error: str) -> None:
        self.statusLabel.setText(self.tr("校验失败：{0}").format(error))
        self.progressBar.error()
        self._cleanup()

    def _cleanup(self) -> None:
        if self._worker:
            self._worker.wait()
            self._worker.deleteLater()
            self._worker = None
