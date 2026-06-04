from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import QEvent, QFileInfo, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter
from PySide6.QtWidgets import QFileDialog, QFileIconProvider, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    CompactSpinBox,
    FluentIcon,
    IconWidget,
    ImageLabel,
    LineEdit,
    PushButton,
    StrongBodyLabel,
    TransparentToolButton,
    isDarkTheme,
)

from loguru import logger

from app.bases.models import Task, TaskStatus
from app.services.core_service import coreService
from app.services.task_service import taskService
from app.supports.utils import toReadableSize, toReadableTime
from app.view.components.cards import ParseSettingCard, ResultCard, UniversalTaskCard
from app.view.components.editors import AutoSizingEdit

if TYPE_CHECKING:
    from .task import M3U8TaskStage


class M3U8TaskCard(UniversalTaskCard):
    def _renderTaskState(self):
        progress, speed, receivedBytes = self.task.currentSnapshot()
        self.progressBar.setValue(progress)

        if self.task.fileSize > 1:
            self.progressLabel.setText(f"{toReadableSize(receivedBytes)}/{toReadableSize(self.task.fileSize)}")
        else:
            self.progressLabel.setText(self.tr("{0} / {1:.2f}%").format(toReadableSize(receivedBytes), progress))

        if self.task.status == TaskStatus.RUNNING:
            self.progressBar.setError(False)
            if self.infoLabel.isVisible():
                self.infoLabel.hide()
                self.speedLabel.show()
                self.leftTimeLabel.show()
                self.progressLabel.show()
            self.speedLabel.setText(f"{toReadableSize(speed)}/s")
            if self.task.fileSize > 1 and speed > 0:
                self.leftTimeLabel.setText(toReadableTime(int((self.task.fileSize - receivedBytes) / speed)))
            else:
                self.leftTimeLabel.setText("--")
        elif self.task.status == TaskStatus.COMPLETED:
            self.progressBar.setError(False)
            self.progressBar.hide()
            self.showStatusInfo(self.tr("任务已经完成"))
        elif self.task.status == TaskStatus.FAILED:
            self.progressBar.error()
            self.onTaskFailed()
        elif self.task.status == TaskStatus.PAUSED:
            self.progressBar.setError(False)
            self.progressBar.pause()
            self.showStatusInfo(self.tr("任务已经暂停"))
        else:
            self.progressBar.setError(False)
            self.progressBar.pause()
            self.showStatusInfo(self.tr("任务正在等待"))

        self.refreshToggleButton()


class M3U8LiveTaskCard(M3U8TaskCard):
    """直播录制卡：主按钮为「停止并定案」，展示 录制中/等待 与已录时长"""

    def _renderTaskState(self):
        progress, speed, _ = self.task.currentSnapshot()
        self.progressBar.setValue(progress)
        stage = cast("M3U8TaskStage", self.task.stages[0])

        if self.task.status == TaskStatus.RUNNING:
            self.progressBar.setError(False)
            if self.infoLabel.isVisible():
                self.infoLabel.hide()
                self.speedLabel.show()
                self.leftTimeLabel.show()
                self.progressLabel.show()
            self.speedLabel.setText(f"{toReadableSize(speed)}/s")
            self.leftTimeLabel.setText(self._liveTimeText(stage))
            if stage.liveStatus == "Waiting":
                self.progressLabel.setText(self.tr("等待中"))
                self.progressBar.pause()
            else:
                self.progressLabel.setText(self.tr("录制中"))
                self.progressBar.resume()
        elif self.task.status == TaskStatus.COMPLETED:
            self.progressBar.setError(False)
            self.progressBar.hide()
            self.showStatusInfo(self.tr("录制已结束"))
        elif self.task.status == TaskStatus.FAILED:
            self.progressBar.error()
            self.onTaskFailed()
        else:
            self.progressBar.setError(False)
            self.progressBar.pause()
            self.showStatusInfo(self.tr("等待录制"))

        self.refreshToggleButton()

    def _liveTimeText(self, stage: "M3U8TaskStage") -> str:
        elapsed = stage.liveElapsed or "00m00s"
        return f"{elapsed} / {stage.recordLimit}" if stage.recordLimit else elapsed

    def refreshToggleButton(self):
        status = self.task.status
        if status == TaskStatus.RUNNING:
            self.toggleRunningStatusButton.setIcon(FluentIcon.ACCEPT)
            self.toggleRunningStatusButton.setToolTip(self.tr("停止并定案"))
            self.toggleRunningStatusButton.setEnabled(True)
        elif status == TaskStatus.COMPLETED:
            self.toggleRunningStatusButton.setIcon(FluentIcon.ACCEPT)
            self.toggleRunningStatusButton.setEnabled(False)
        else:
            self.toggleRunningStatusButton.setIcon(FluentIcon.PLAY)
            self.toggleRunningStatusButton.setEnabled(True)

        self.verifyHashButton.setVisible(status == TaskStatus.COMPLETED)
        self.verifyHashButton.setEnabled(status == TaskStatus.COMPLETED)

    def toggleRunningStatus(self):
        if self.task.status == TaskStatus.RUNNING:
            self.finalizeRecording()
        else:
            self.resumeTask()

    def finalizeRecording(self):
        # 直播无暂停：停止=取消进程, worker 收尾标 COMPLETED；不走 stopTask 以免 PAUSED 闪烁
        self.toggleRunningStatusButton.setDisabled(True)
        coreService.runCoroutine(coreService._stopTask(self.task), self._onRecordingFinalized)

    def _onRecordingFinalized(self, _result=None, error: str | None = None):
        if error:
            logger.warning("停止直播录制失败 {}: {}", self.task.title, error)
            self._renderTaskState()
            return
        if self.task.status == TaskStatus.COMPLETED and self.cardStatus != TaskStatus.COMPLETED:
            self.onTaskFinished()
        self._renderTaskState()
        if self.task.status != self.cardStatus:
            taskService.scheduleFlush()
            self.cardStatus = self.task.status


class M3U8ResultCard(ResultCard):
    def __init__(self, task: Task, parent: QWidget = None):
        super().__init__(task, parent)
        self.iconLabel = ImageLabel(self)
        self.filenameLabel = StrongBodyLabel(self.task.title, self)
        self.filenameEdit = LineEdit(self)
        self.metaLabel = BodyLabel(self._metaText(), self)
        self.mainLayout = QHBoxLayout(self)

        self._initWidget()
        self._initLayout()
        self._renderCategoryButton()

    def _initWidget(self):
        self.setFixedHeight(35)
        self._refreshIcon()
        self.filenameLabel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.filenameLabel.installEventFilter(self)
        self.filenameEdit.setText(self.task.title)
        self.filenameEdit.editingFinished.connect(self._onEditingFinished)
        self.filenameEdit.hide()

    def _initLayout(self):
        self.mainLayout.setContentsMargins(10, 2, 10, 2)
        self.mainLayout.setSpacing(12)
        self.mainLayout.addWidget(self.iconLabel)
        self.mainLayout.addWidget(self.filenameLabel, 1)
        self.mainLayout.addWidget(self.filenameEdit, 1)
        self.mainLayout.addWidget(self.metaLabel)
        self.mainLayout.addWidget(self.editButton)
        self.mainLayout.addWidget(self.categoryButton)

    def _metaText(self) -> str:
        manifestText = "DASH" if self.task.manifestType == "mpd" else "HLS"
        modeText = self.tr("直播") if self.task.isLive else self.tr("点播")
        return f"{manifestText} · {modeText}"

    def _refreshIcon(self):
        icon = QFileIconProvider().icon(QFileInfo(self.task.outputFolder))
        self.iconLabel.setImage(icon.pixmap(16, 16))
        self.iconLabel.setFixedSize(16, 16)

    def eventFilter(self, obj, event: QEvent):
        if obj is self.filenameLabel:
            if event.type() == QEvent.Type.MouseButtonDblClick and isinstance(event, QMouseEvent):
                if event.button() == Qt.MouseButton.LeftButton:
                    self._enterEditMode()
                    return True
        return super().eventFilter(obj, event)

    def _enterEditMode(self):
        self.filenameLabel.hide()
        self.filenameEdit.show()
        self.filenameEdit.setFocus()
        self.filenameEdit.selectAll()

    def _onEditingFinished(self):
        newFilename = self.filenameEdit.text().strip()
        if newFilename and newFilename != self.task.title:
            self.task.setTitle(newFilename)
            self.filenameLabel.setText(self.task.title)
            self.filenameEdit.setText(self.task.title)
            self._refreshIcon()

        self.filenameEdit.hide()
        self.filenameLabel.show()

    def getTask(self) -> Task:
        return self.task


class _M3U8EditCard(QWidget):
    """编辑对话框里的多行设置卡，提供 payloadChanged 信号与顶部分隔线"""

    payloadChanged = Signal()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(0, 0, 0, 96 if isDarkTheme() else 48))
        painter.drawLine(self.rect().topLeft(), self.rect().topRight())


class M3U8TrackEditCard(ParseSettingCard):
    def __init__(self, icon, title: str, parent=None, *, streams: list, initial: str = "") -> None:
        self._streams = streams
        self._initialExpr = initial
        super().__init__(icon, title, parent)

    def initCustomWidget(self) -> None:
        self.trackCombo = ComboBox(self)
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.trackCombo.setMinimumWidth(220)
        self.trackCombo.addItem(self.tr("默认（最佳）"), userData="")
        selectedIndex = 0
        for index, stream in enumerate(self._streams, start=1):
            expr = stream.get("selectExpr", "")
            self.trackCombo.addItem(stream.get("label", ""), userData=expr)
            if self._initialExpr and expr == self._initialExpr:
                selectedIndex = index
        self.trackCombo.setCurrentIndex(selectedIndex)

    def _initLayout(self) -> None:
        self.hBoxLayout.addWidget(self.trackCombo)
        self.hBoxLayout.addSpacing(16)

    def _bind(self) -> None:
        self.trackCombo.currentIndexChanged.connect(lambda _: self.payloadChanged.emit())

    @property
    def payload(self) -> dict[str, Any]:
        return {"selectVideo": self.trackCombo.currentData() or ""}


class M3U8RecordLimitEditCard(ParseSettingCard):
    def __init__(self, icon, title: str, parent=None, *, initial: str = "") -> None:
        self._initialLimit = initial
        super().__init__(icon, title, parent)

    def initCustomWidget(self) -> None:
        self.hourSpinBox = CompactSpinBox(self)
        self.minuteSpinBox = CompactSpinBox(self)
        self.secondSpinBox = CompactSpinBox(self)
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.hourSpinBox.setRange(0, 99)
        self.minuteSpinBox.setRange(0, 59)
        self.secondSpinBox.setRange(0, 59)
        for box in (self.hourSpinBox, self.minuteSpinBox, self.secondSpinBox):
            box.setFixedWidth(64)
        self._applyLimit(self._initialLimit)

    def _initLayout(self) -> None:
        self.hBoxLayout.addWidget(self.hourSpinBox)
        self.hBoxLayout.addWidget(BodyLabel(":", self))
        self.hBoxLayout.addWidget(self.minuteSpinBox)
        self.hBoxLayout.addWidget(BodyLabel(":", self))
        self.hBoxLayout.addWidget(self.secondSpinBox)
        self.hBoxLayout.addSpacing(16)

    def _bind(self) -> None:
        for box in (self.hourSpinBox, self.minuteSpinBox, self.secondSpinBox):
            box.valueChanged.connect(lambda _: self.payloadChanged.emit())

    def _applyLimit(self, limit: str) -> None:
        parts = limit.split(":") if limit else []
        if len(parts) != 3:
            return
        try:
            hours, minutes, seconds = (int(part) for part in parts)
        except ValueError:
            return
        self.hourSpinBox.setValue(hours)
        self.minuteSpinBox.setValue(minutes)
        self.secondSpinBox.setValue(seconds)

    @property
    def payload(self) -> dict[str, Any]:
        hours = self.hourSpinBox.value()
        minutes = self.minuteSpinBox.value()
        seconds = self.secondSpinBox.value()
        limit = f"{hours:02}:{minutes:02}:{seconds:02}" if hours + minutes + seconds > 0 else ""
        return {"recordLimit": limit}


class M3U8DecryptionEditCard(_M3U8EditCard):
    def __init__(self, icon, title: str, parent=None, *, keys: list | None = None, keyTextFile: str = "") -> None:
        super().__init__(parent)
        self._keyTextFile = keyTextFile

        # instant widget
        self.iconWidget = IconWidget(icon, self)
        self.titleLabel = BodyLabel(title, self)
        self.keyFileButton = TransparentToolButton(FluentIcon.FOLDER_ADD, self)
        self.keysEdit = AutoSizingEdit(self, minimumVisibleLines=3, maximumVisibleLines=10)
        self.keyFileLabel = BodyLabel(self)

        # instant layout
        self.vBoxLayout = QVBoxLayout(self)
        self.titleRowLayout = QHBoxLayout()

        self._initWidget(keys or [])
        self._initLayout()
        self._bind()

    def _initWidget(self, keys: list) -> None:
        self.iconWidget.setFixedSize(16, 16)
        self.keyFileButton.setToolTip(self.tr("选择 KEY 文本文件"))
        self.keysEdit.setPlaceholderText("KID1:KEY1\nKID2:KEY2")
        self.keysEdit.setPlainText("\n".join(keys))
        self._refreshKeyFileLabel()

    def _initLayout(self) -> None:
        self.titleRowLayout.setSpacing(15)
        self.titleRowLayout.addWidget(self.iconWidget)
        self.titleRowLayout.addWidget(self.titleLabel)
        self.titleRowLayout.addStretch(1)
        self.titleRowLayout.addWidget(self.keyFileLabel)
        self.titleRowLayout.addWidget(self.keyFileButton)

        self.vBoxLayout.setContentsMargins(24, 10, 24, 12)
        self.vBoxLayout.setSpacing(10)
        self.vBoxLayout.addLayout(self.titleRowLayout)
        self.vBoxLayout.addWidget(self.keysEdit)

    def _bind(self) -> None:
        self.keysEdit.textChanged.connect(self.payloadChanged.emit)
        self.keyFileButton.clicked.connect(self._onChooseKeyFile)

    def _onChooseKeyFile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.tr("选择 KEY 文本文件"))
        if not path:
            return
        self._keyTextFile = path
        self._refreshKeyFileLabel()
        self.payloadChanged.emit()

    def _refreshKeyFileLabel(self) -> None:
        self.keyFileLabel.setText(Path(self._keyTextFile).name if self._keyTextFile else "")

    @property
    def payload(self) -> dict[str, Any]:
        keys = [line.strip() for line in self.keysEdit.toPlainText().splitlines() if line.strip()]
        return {"decryptionKeys": keys, "keyTextFile": self._keyTextFile}


class M3U8MuxImportEditCard(_M3U8EditCard):
    def __init__(self, icon, title: str, parent=None, *, initial: list | None = None) -> None:
        super().__init__(parent)

        # instant widget
        self.iconWidget = IconWidget(icon, self)
        self.titleLabel = BodyLabel(title, self)
        self.importEdit = AutoSizingEdit(self, minimumVisibleLines=3, maximumVisibleLines=10)

        # instant layout
        self.vBoxLayout = QVBoxLayout(self)
        self.titleRowLayout = QHBoxLayout()

        self._initWidget(initial or [])
        self._initLayout()
        self._bind()

    def _initWidget(self, imports: list) -> None:
        self.iconWidget.setFixedSize(16, 16)
        self.importEdit.setPlaceholderText('path="aud.m4a":lang=eng:name="Audio"')
        self.importEdit.setPlainText("\n".join(imports))

    def _initLayout(self) -> None:
        self.titleRowLayout.setSpacing(15)
        self.titleRowLayout.addWidget(self.iconWidget)
        self.titleRowLayout.addWidget(self.titleLabel)
        self.titleRowLayout.addStretch(1)

        self.vBoxLayout.setContentsMargins(24, 10, 24, 12)
        self.vBoxLayout.setSpacing(10)
        self.vBoxLayout.addLayout(self.titleRowLayout)
        self.vBoxLayout.addWidget(self.importEdit)

    def _bind(self) -> None:
        self.importEdit.textChanged.connect(self.payloadChanged.emit)

    @property
    def payload(self) -> dict[str, Any]:
        imports = [line.strip() for line in self.importEdit.toPlainText().splitlines() if line.strip()]
        return {"muxImports": imports}
