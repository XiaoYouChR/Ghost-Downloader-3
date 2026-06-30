from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout
from qfluentwidgets import BodyLabel, ComboBox, CompactSpinBox, FluentIcon, TransparentToolButton

from app.format import toReadableSize
from app.models.task import TaskStatus
from app.view.cards.draft_cards import UniversalDraftCard
from app.view.cards.task_cards import UniversalTaskCard
from app.view.components.editors import AutoSizingEdit
from app.view.components.option_cards import OptionCard

if TYPE_CHECKING:
    from .task import M3U8TaskStep


class M3U8DraftCard(UniversalDraftCard):
    pass


class M3U8TaskCard(UniversalTaskCard):

    def refresh(self):
        super().refresh()
        if self._task.status == TaskStatus.RUNNING and self._task.fileSize <= 1:
            step = self._step()
            if step is not None:
                progress = step.progress
                self.sizeLabel.setText(
                    f"{toReadableSize(step.receivedBytes)} / {progress:.1f}%"
                )

    def _step(self) -> M3U8TaskStep | None:
        return self._task.steps[0] if self._task.steps else None


class M3U8LiveTaskCard(UniversalTaskCard):

    def refresh(self):
        super().refresh()
        step = self._step()
        if step is None:
            return
        if self._task.status == TaskStatus.RUNNING:
            elapsed = step.liveElapsed or "00m00s"
            timeText = f"{elapsed} / {step.recordLimit}" if step.recordLimit else elapsed
            self.etaLabel.setText(timeText)
            if step.liveStatus == "Waiting":
                self.sizeLabel.setText(self.tr("等待中"))
            else:
                self.sizeLabel.setText(self.tr("录制中"))
        elif self._task.status == TaskStatus.COMPLETED:
            self._showStatus(self.tr("录制已结束"))

    def _refreshButtons(self) -> None:
        if self._task.status == TaskStatus.RUNNING:
            self.toggleButton.setIcon(FluentIcon.ACCEPT)
            self.toggleButton.setToolTip(self.tr("停止并定案"))
            self.toggleButton.setEnabled(True)
        elif self._task.status == TaskStatus.COMPLETED:
            self.toggleButton.setIcon(FluentIcon.ACCEPT)
            self.toggleButton.setEnabled(False)
        else:
            self.toggleButton.setIcon(FluentIcon.PLAY)
            self.toggleButton.setEnabled(True)
        self.verifyHashButton.setVisible(self._task.status == TaskStatus.COMPLETED)
        self.verifyHashButton.setEnabled(self._task.status == TaskStatus.COMPLETED)

    def _onToggleClicked(self) -> None:
        if self._task.status == TaskStatus.RUNNING:
            self.toggleButton.setEnabled(False)
            step = self._step()
            if step is not None:
                step.terminate()
        else:
            from app.services.task_service import taskService
            taskService.start(self._task)
            self.refresh()

    def _step(self) -> M3U8TaskStep | None:
        return self._task.steps[0] if self._task.steps else None


class StreamSelectCard(OptionCard):
    def __init__(self, parent=None, *, streams: list, initial: str = ""):
        super().__init__(parent)
        self._streams = streams
        self._initial = initial
        self.comboBox = ComboBox(self)

        self._initWidget()
        self._initLayout()

    def _initWidget(self):
        self.comboBox.setMinimumWidth(220)
        self.comboBox.addItem(self.tr("默认（最佳）"), userData="")
        selectedIndex = 0
        for index, stream in enumerate(self._streams, start=1):
            width = stream.get("width", 0)
            height = stream.get("height", 0)
            codecs = stream.get("codecs", "")
            frameRate = stream.get("frameRate")
            label = f"{width}×{height}"
            if codecs:
                label += f" · {codecs}"
            if frameRate:
                label += f" · {frameRate}fps"
            selectExpr = f"res=\"{width}x{height}\""
            if frameRate:
                selectExpr += f":frame=\"{int(frameRate)}*\""
            self.comboBox.addItem(label, userData=selectExpr)
            if self._initial and selectExpr == self._initial:
                selectedIndex = index
        self.comboBox.setCurrentIndex(selectedIndex)

    def _initLayout(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.addWidget(self.comboBox)
        layout.addStretch(1)

    def options(self) -> dict:
        return {"selectVideo": self.comboBox.currentData() or ""}


class RecordLimitCard(OptionCard):
    def __init__(self, parent=None, *, initial: str = ""):
        super().__init__(parent)
        self._initial = initial
        self.hourSpinBox = CompactSpinBox(self)
        self.minuteSpinBox = CompactSpinBox(self)
        self.secondSpinBox = CompactSpinBox(self)

        self._initWidget()
        self._initLayout()

    def _initWidget(self):
        self.hourSpinBox.setRange(0, 99)
        self.minuteSpinBox.setRange(0, 59)
        self.secondSpinBox.setRange(0, 59)
        for box in (self.hourSpinBox, self.minuteSpinBox, self.secondSpinBox):
            box.setFixedWidth(64)
        parts = self._initial.split(":") if self._initial else []
        if len(parts) == 3:
            try:
                self.hourSpinBox.setValue(int(parts[0]))
                self.minuteSpinBox.setValue(int(parts[1]))
                self.secondSpinBox.setValue(int(parts[2]))
            except ValueError:
                pass

    def _initLayout(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.addWidget(self.hourSpinBox)
        layout.addWidget(BodyLabel(":", self))
        layout.addWidget(self.minuteSpinBox)
        layout.addWidget(BodyLabel(":", self))
        layout.addWidget(self.secondSpinBox)
        layout.addStretch(1)

    def options(self) -> dict:
        h, m, s = self.hourSpinBox.value(), self.minuteSpinBox.value(), self.secondSpinBox.value()
        limit = f"{h:02}:{m:02}:{s:02}" if h + m + s > 0 else ""
        return {"recordLimit": limit}


class DecryptionKeyCard(OptionCard):
    def __init__(self, parent=None, *, keys: list | None = None, keyTextFile: str = ""):
        super().__init__(parent)
        self._keyTextFile = keyTextFile
        self.titleLabel = BodyLabel(self.tr("解密密钥"), self)
        self.keyFileButton = TransparentToolButton(FluentIcon.FOLDER_ADD, self)
        self.keyFileLabel = BodyLabel(self)
        self.keysEdit = AutoSizingEdit(self, minimumVisibleLines=3, maximumVisibleLines=10)

        self._initWidget(keys or [])
        self._initLayout()
        self._bind()

    def _initWidget(self, keys: list):
        self.keyFileButton.setToolTip(self.tr("选择 KEY 文本文件"))
        self.keysEdit.setPlaceholderText("KID1:KEY1\nKID2:KEY2")
        self.keysEdit.setPlainText("\n".join(keys))
        self.keyFileLabel.setText(Path(self._keyTextFile).name if self._keyTextFile else "")

    def _initLayout(self):
        titleRow = QHBoxLayout()
        titleRow.setSpacing(15)
        titleRow.addWidget(self.titleLabel)
        titleRow.addStretch(1)
        titleRow.addWidget(self.keyFileLabel)
        titleRow.addWidget(self.keyFileButton)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 10, 24, 12)
        layout.setSpacing(10)
        layout.addLayout(titleRow)
        layout.addWidget(self.keysEdit)

    def _bind(self):
        self.keyFileButton.clicked.connect(self._onChooseKeyFile)

    def _onChooseKeyFile(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("选择 KEY 文本文件"))
        if not path:
            return
        self._keyTextFile = path
        self.keyFileLabel.setText(Path(path).name)

    def options(self) -> dict:
        keys = [line.strip() for line in self.keysEdit.toPlainText().splitlines() if line.strip()]
        return {"decryptionKeys": keys, "decryptionKeyFile": self._keyTextFile}


class MuxImportCard(OptionCard):
    def __init__(self, parent=None, *, initial: list | None = None):
        super().__init__(parent)
        self.titleLabel = BodyLabel(self.tr("导入音轨/字幕"), self)
        self.importEdit = AutoSizingEdit(self, minimumVisibleLines=3, maximumVisibleLines=10)

        self._initWidget(initial or [])
        self._initLayout()

    def _initWidget(self, imports: list):
        self.importEdit.setPlaceholderText('path="aud.m4a":lang=eng:name="Audio"')
        self.importEdit.setPlainText("\n".join(imports))

    def _initLayout(self):
        titleRow = QHBoxLayout()
        titleRow.setSpacing(15)
        titleRow.addWidget(self.titleLabel)
        titleRow.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 10, 24, 12)
        layout.setSpacing(10)
        layout.addLayout(titleRow)
        layout.addWidget(self.importEdit)

    def options(self) -> dict:
        imports = [line.strip() for line in self.importEdit.toPlainText().splitlines() if line.strip()]
        return {"muxImports": imports}
