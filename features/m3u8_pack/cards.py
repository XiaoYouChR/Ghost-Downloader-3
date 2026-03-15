import shutil
from pathlib import Path

from PySide6.QtCore import QEvent, QFileInfo, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFileIconProvider, QHBoxLayout, QWidget
from qfluentwidgets import BodyLabel, ImageLabel, LineEdit, StrongBodyLabel

from app.bases.models import TaskStatus
from app.supports.utils import getReadableSize, getReadableTime
from app.view.components.cards import ResultCard, UniversalTaskCard

from .task import M3U8InstallTask, M3U8Task


def _removeFile(path: Path):
    try:
        if path.is_file() or path.is_symlink():
            path.unlink()
    except FileNotFoundError:
        pass


class M3U8TaskCard(UniversalTaskCard):
    def _renderTaskState(self):
        division = max(1, len(self.task.stages))
        progress = 0.0
        speed = 0
        receivedBytes = 0

        for stage in self.task.stages:
            progress += stage.progress
            speed += stage.speed
            receivedBytes += stage.receivedBytes

        progress /= division
        self.progressBar.setValue(progress)

        if self.task.fileSize > 1:
            self.progressLabel.setText(f"{getReadableSize(receivedBytes)}/{getReadableSize(self.task.fileSize)}")
        else:
            self.progressLabel.setText(self.tr("{0} / {1:.2f}%").format(getReadableSize(receivedBytes), progress))

        if self.task.status == TaskStatus.RUNNING:
            self.progressBar.setError(False)
            if self.infoLabel.isVisible():
                self.infoLabel.hide()
                self.speedLabel.show()
                self.leftTimeLabel.show()
                self.progressLabel.show()
            self.speedLabel.setText(f"{getReadableSize(speed)}/s")
            if self.task.fileSize > 1 and speed > 0:
                self.leftTimeLabel.setText(getReadableTime(int((self.task.fileSize - receivedBytes) / speed)))
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

    def onTaskDeleted(self, completely: bool = False):
        if not completely:
            return

        task = self.task
        _removeFile(Path(task.resolvePath))
        shutil.rmtree(Path(task.tempDir), ignore_errors=True)

        outputDirectory = Path(task.path)
        if outputDirectory.exists():
            prefix = f"{task.saveName}."
            for candidate in outputDirectory.iterdir():
                if candidate.name == Path(task.resolvePath).name:
                    continue
                if candidate.is_file() and candidate.name.startswith(prefix):
                    _removeFile(candidate)


class M3U8InstallTaskCard(UniversalTaskCard):
    def onTaskDeleted(self, completely: bool = False):
        if not completely:
            return

        if isinstance(self.task, M3U8InstallTask):
            shutil.rmtree(self.task.installFolder, ignore_errors=True)
            return

        super().onTaskDeleted(completely)


class M3U8ResultCard(ResultCard):
    def __init__(self, task: M3U8Task, parent: QWidget = None):
        super().__init__(task, parent)
        self.task = task
        self.iconLabel = ImageLabel(self)
        self.filenameLabel = StrongBodyLabel(self.task.title, self)
        self.filenameEdit = LineEdit(self)
        self.metaLabel = BodyLabel(self._metaText(), self)
        self.mainLayout = QHBoxLayout(self)

        self._initWidget()
        self._initLayout()

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
        self.mainLayout.addWidget(self.filenameLabel)
        self.mainLayout.addWidget(self.filenameEdit)
        self.mainLayout.addStretch()
        self.mainLayout.addWidget(self.metaLabel)

    def _metaText(self) -> str:
        manifestText = "DASH" if self.task.manifestType == "mpd" else "HLS"
        modeText = self.tr("直播") if self.task.isLive else self.tr("点播")
        return f"{manifestText} · {modeText}"

    def _refreshIcon(self):
        icon = QFileIconProvider().icon(QFileInfo(self.task.resolvePath))
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

    def getTask(self) -> M3U8Task:
        return self.task
