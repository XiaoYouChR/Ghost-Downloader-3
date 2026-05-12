import shutil
from pathlib import Path

from PySide6.QtCore import QEvent, QFileInfo, Qt
from PySide6.QtWidgets import (
    QFileIconProvider,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    IconWidget,
    LineEdit,
    PrimaryPushButton,
    StrongBodyLabel,
    ToolButton,
)

from app.bases.models import TaskStatus
from app.supports.utils import getReadableSize, getReadableTime, openFile, openFolder
from app.view.components.cards import ResultCard, UniversalTaskCard
from app.view.components.dialogs import FileSelectDialog

from .task import FtpTask


def _removePath(path: Path):
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        return
    path.unlink(missing_ok=True)


def _openFileSelection(task: FtpTask, parent) -> set[int] | None:
    dialog = FtpFileSelectDialog(task, parent)
    try:
        if not dialog.exec():
            return None
        selectedIndexes = dialog.selectedIndexes()
        task.updateSelectedFiles(selectedIndexes)
        return selectedIndexes
    finally:
        dialog.deleteLater()


class FtpFileSelectDialog(FileSelectDialog):
    def __init__(self, task: FtpTask, parent=None):
        super().__init__(task, parent)
        self.task: FtpTask = task

    def _fileDisplayPath(self, file) -> str:
        return file.relativePath


class FtpResultCard(ResultCard):
    def __init__(self, task: FtpTask, parent: QWidget = None):
        super().__init__(task, parent)
        self.task = task

        self.mainLayout = QHBoxLayout(self)
        self.textLayout = QVBoxLayout()
        self.iconLabel = IconWidget(self)
        self.titleLabel = StrongBodyLabel(self.task.title, self)
        self.titleEdit = LineEdit(self)
        self.sourceLabel = CaptionLabel(self._sourceText(), self)
        self.summaryLabel = BodyLabel("", self)
        self.selectFilesButton = PrimaryPushButton(self.tr("选择文件"), self)

        self._initWidget()
        self._initLayout()
        self._refreshSummary()

    def _initWidget(self):
        self.setFixedHeight(50)
        icon = (
            QFileIconProvider().icon(QFileIconProvider.IconType.Folder)
            if self.task.isDirectorySource
            else QFileIconProvider().icon(QFileInfo(self.task.outputFolder))
        )
        self.iconLabel.setIcon(icon)
        self.iconLabel.setFixedSize(20, 20)
        self.titleLabel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.titleLabel.installEventFilter(self)
        self.titleEdit.setText(self.task.title)
        self.titleEdit.editingFinished.connect(self._onEditingFinished)
        self.titleEdit.hide()
        self.selectFilesButton.setVisible(self.task.totalFileCount > 1)
        self.selectFilesButton.clicked.connect(self._onSelectFilesClicked)

    def _initLayout(self):
        self.mainLayout.setContentsMargins(10, 6, 10, 6)
        self.mainLayout.setSpacing(12)
        self.textLayout.setContentsMargins(0, 0, 0, 0)
        self.textLayout.setSpacing(2)
        self.textLayout.addWidget(self.titleLabel)
        self.textLayout.addWidget(self.titleEdit)
        self.textLayout.addWidget(self.sourceLabel)
        self.mainLayout.addWidget(self.iconLabel, 0, Qt.AlignmentFlag.AlignCenter)
        self.mainLayout.addLayout(self.textLayout)
        self.mainLayout.addStretch(1)
        self.mainLayout.addWidget(self.summaryLabel)
        self.mainLayout.addSpacing(12)
        self.mainLayout.addWidget(self.selectFilesButton)

    def eventFilter(self, obj, event: QEvent):
        if obj is self.titleLabel:
            if event.type() == QEvent.Type.MouseButtonDblClick:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._enterEditMode()
                    return True
        return super().eventFilter(obj, event)

    def _enterEditMode(self):
        self.titleLabel.hide()
        self.titleEdit.show()
        self.titleEdit.setFocus()
        self.titleEdit.selectAll()

    def _onEditingFinished(self):
        newTitle = self.titleEdit.text().strip()
        if newTitle and newTitle != self.task.title:
            self.task.setTitle(newTitle)
            self.titleLabel.setText(self.task.title)
            self.titleEdit.setText(self.task.title)

        self.titleEdit.hide()
        self.titleLabel.show()
        self.titleLabel.setFocus()

    def _sourceText(self) -> str:
        sourceType = self.tr("FTP 目录") if self.task.isDirectorySource else self.tr("FTP 文件")
        return self.tr("{0} · {1}").format(
            sourceType,
            self.task.connectionInfo.host,
        )

    def _refreshSummary(self):
        if self.task.totalFileCount > 1 or self.task.isDirectorySource:
            self.summaryLabel.setText(
                self.tr("{0}/{1} 个文件 · {2}").format(
                    self.task.selectedFileCount,
                    self.task.totalFileCount,
                    getReadableSize(self.task.fileSize),
                )
            )
            return

        self.summaryLabel.setText(getReadableSize(self.task.fileSize))

    def _onSelectFilesClicked(self):
        if _openFileSelection(self.task, self.window()) is not None:
            self._refreshSummary()

    def getTask(self) -> FtpTask:
        return self.task


class FtpTaskCard(UniversalTaskCard):
    def __init__(self, task: FtpTask, parent=None):
        super().__init__(task, parent)
        self.task = task
        self.selectFilesButton = ToolButton(FluentIcon.LIBRARY, self)
        self.hBoxLayout.insertWidget(
            self.hBoxLayout.indexOf(self.verifyHashButton),
            self.selectFilesButton,
        )
        self.selectFilesButton.clicked.connect(self._onSelectFilesClicked)
        self.openFileButton.clicked.disconnect()
        self.openFolderButton.clicked.disconnect()
        self.openFileButton.clicked.connect(self._openPrimaryTarget)
        self.openFolderButton.clicked.connect(self._openTaskFolder)
        self._refreshIconLabel()

    def _refreshIconLabel(self):
        if self.task.isDirectorySource:
            icon = QFileIconProvider().icon(QFileIconProvider.IconType.Folder)
        else:
            icon = QFileIconProvider().icon(QFileInfo(self.task.outputFolder))
        self.iconLabel.setPixmap(icon.pixmap(48, 48))
        self.iconLabel.setFixedSize(48, 48)

    def _selectedStageStats(self) -> tuple[int, int]:
        receivedBytes = 0
        speed = 0
        for stage in self.task.selectedStages:
            receivedBytes += stage.receivedBytes
            speed += stage.speed
        return receivedBytes, speed

    def _openPrimaryTarget(self):
        openFile(self.task.outputFolder)

    def _openTaskFolder(self):
        target = Path(self.task.outputFolder)
        if target.exists():
            openFolder(str(target))
            return
        openFolder(str(target.parent))

    def statusInfoText(self) -> str | None:
        if self.task.status == TaskStatus.PAUSED:
            return super().statusInfoText()

        if self.task.status in {TaskStatus.WAITING, TaskStatus.COMPLETED}:
            if self.task.totalFileCount > 1 or self.task.isDirectorySource:
                return self.tr("{0}/{1} 个文件").format(
                    self.task.selectedFileCount,
                    self.task.totalFileCount,
                )

        return super().statusInfoText()

    def _renderTaskState(self):
        super()._renderTaskState()

        receivedBytes, speed = self._selectedStageStats()
        if self.task.fileSize > 0:
            self.progressBar.setValue(receivedBytes / self.task.fileSize * 100)
            self.progressLabel.setText(
                f"{getReadableSize(receivedBytes)}/{getReadableSize(self.task.fileSize)}"
            )
        else:
            self.progressLabel.setText(f"{getReadableSize(receivedBytes)}/--")

        if self.task.status == TaskStatus.RUNNING:
            self.speedLabel.setText(f"{getReadableSize(speed)}/s")
            if self.task.fileSize > 0 and speed > 0:
                remaining = max(0, self.task.fileSize - receivedBytes)
                self.leftTimeLabel.setText(getReadableTime(int(remaining / speed)))
            elif self.task.fileSize > 0:
                self.leftTimeLabel.setText("--")

    def _onSelectFilesClicked(self):
        if self.task.status == TaskStatus.RUNNING:
            return

        previousSelected = {
            file.index for file in self.task.files if file.selected
        }
        selectedIndexes = _openFileSelection(self.task, self.window())
        if selectedIndexes is None:
            return

        if (
            self.task.status == TaskStatus.COMPLETED
            and selectedIndexes - previousSelected
            and self.task.reopenForAdditionalFiles()
        ):
            self.resumeTask()
            return

        self.cardStatus = self.task.status
        self._renderTaskState()

    def refresh(self):
        super().refresh()
        self.verifyHashButton.setVisible(
            not self.task.isDirectorySource
            and self.task.selectedFileCount == 1
            and self.task.status == TaskStatus.COMPLETED
            and Path(self.task.outputFolder).is_file()
        )
        self.selectFilesButton.setVisible(self.task.totalFileCount > 1)
        self.selectFilesButton.setEnabled(self.task.status != TaskStatus.RUNNING)

    def onTaskDeleted(self, completely: bool = False):
        if not completely:
            return

        if self.task.isDirectorySource:
            _removePath(Path(self.task.outputFolder))
            return

        for stage in self.task.stages:
            resolvePath = stage.outputFile.strip()
            if not resolvePath:
                continue
            target = Path(resolvePath)
            _removePath(target)
            _removePath(Path(str(target) + ".ghd"))
